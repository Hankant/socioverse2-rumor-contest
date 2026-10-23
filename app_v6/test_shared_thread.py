"""Shared rumor, complete separate comment threads, and mandatory conditions."""
import copy
import csv
import json
from types import SimpleNamespace

import pytest
from socioverse.schemas import Action
from model import V4Environment,V4Decision,digest,normalize_answer,BINARY_SCORE_POLICY
from run import defaults,SOURCE,make_bundles
from llm_client import (LiveClient,DecisionConditionsPause,PromptBudgetPause,
                        validate_response,prepare_prompt,render_prompt,is_format_error)
from decision_conditions import (CONDITION_LABELS,condition_inputs,condition_reference,
                                 scripted_condition_application,validate_condition_application)
from test_recovery import response


def setup(tmp_path):
    cfg={**defaults(),'model':'MiniMax-M3','api_profile':'minimax_m3','base_url':'https://api.minimax.cn/v1',
         'feed_policy':'shared_rumor_all_comments_v1','decision_condition_policy':'all_conditions_v1',
         'comment_target':'explicit_visible_root','llm_max_output_tokens':1536,
         'belief_measurement_policy':BINARY_SCORE_POLICY,'government_tick':2,'government_reach':100,
         'targeting_inside_ratio':.8,'government_trust_mean':.75,'source_trust_gap':.4,
         'api_key_mode':'environment'}
    bundles=make_bundles(SOURCE/'01_Agent基础信息表.csv',SOURCE/'02_Prompt固定提示词.md',cfg,tmp_path/'audit')
    env=V4Environment(bundles[1]);env.reset(1);env.advance_to(1)
    return cfg,bundles,env


def answer(ob,score=60):
    return dict(subjective_credibility=score,
        component_credibility={k:score for k in ('funds_redirected','safety_delayed','causal_link')},
        comment={'enabled':False,'target_content_id':None,'text':''},
        repost={'enabled':False,'target_content_id':None,'text':''},evidence_ids=['P001'],
        **scripted_condition_application(ob))


def fake_action(ob,raw):
    return Action(agent_id=ob.agent_id,step=ob.step,kind='decide',source='llm',payload={
        'answer':raw,'raw_answer':copy.deepcopy(raw),'observed_posts':ob.local_information['posts'],
        'used_memory_ticks':[m['tick'] for m in ob.local_physical['memory']]})


def test_everyone_every_tick_sees_one_rumor_without_following_source(tmp_path):
    _,_,e=setup(tmp_path)
    for tick in (1,2,3,4,5,10):
        e.advance_to(tick)
        obs=e.observe_batch(list(e.by_id),tick)
        assert len(obs)==582
        assert all(sum(p['root_content_id']=='P001' for p in ob.local_information['posts'])==1 for ob in obs)
        assert all(len({p['root_content_id'] for p in ob.local_information['posts']})==len(ob.local_information['posts']) for ob in obs)
    assert not e.observe('A0002',0).local_information['posts']


def test_all_comments_including_nonfollowed_and_repost_comments_no_future(tmp_path):
    _,_,e=setup(tmp_path);aid='A0002'
    other=next(a for a in e.by_id if a not in e.following[aid] and a!=aid)
    e.posts['RP-test']={**e.posts['P001'],'content_id':'RP-test','author_id':other,
                        'published_tick':1,'available_tick':2,'repost_text':'peer caption'}
    for i in range(17):
        e.comments[f'CX{i:02d}']=dict(comment_id=f'CX{i:02d}',author_id=other,published_tick=1,
            target_content_id='P001' if i%2 else 'RP-test',text=f'完整评论内容{i}')
    e.comments['future']=dict(comment_id='future',author_id=other,published_tick=2,target_content_id='P001',text='future')
    e.advance_to(2)
    for reader in (aid,other):
        post=next(p for p in e.observe(reader,2).local_information['posts'] if p['root_content_id']=='P001')
        assert len(post['comments'])==17
        assert {c['comment_id'] for c in post['comments']}=={f'CX{i:02d}' for i in range(17)}
    assert all(c['published_tick']<2 for c in post['comments'])


def test_official_is_separate_account_targeted_then_propagates(tmp_path):
    _,b,e=setup(tmp_path);e.advance_to(2)
    obs=e.observe_batch(list(e.by_id),2)
    reached=[ob.agent_id for ob in obs if any(p['root_content_id']=='G001' for p in ob.local_information['posts'])]
    assert set(reached)==set(e.direct_targets) and len(reached)==100
    target=next(a for a in reached if e.by_id[a]['decision_mode']=='llm')
    ob=e.observe(target,2);raw=answer(ob)
    raw['repost']={'enabled':True,'target_content_id':'G001','text':'请看官方说明'}
    e.apply([fake_action(ob,raw)])
    outside=next(a for a in e.by_id if a not in reached and target in e.following[a])
    assert not any(p['root_content_id']=='G001' for p in e.observe(outside,2).local_information['posts'])
    e.advance_to(3)
    feed=e.observe(outside,3).local_information['posts']
    official=next(p for p in feed if p['root_content_id']=='G001')
    assert official['author_id']=='GOVERNMENT' and official['content_id']=='G001'
    assert sum(p['root_content_id']=='P001' for p in feed)==1


def test_official_comment_thread_is_not_merged_with_rumor(tmp_path):
    _,_,e=setup(tmp_path);e.advance_to(2)
    e.comments['on-rumor']=dict(comment_id='on-rumor',author_id='A0001',published_tick=1,target_content_id='P001',text='rumor')
    e.comments['on-official']=dict(comment_id='on-official',author_id='A0001',published_tick=2,target_content_id='G001',text='official')
    aid=e.direct_targets[0]
    # Persist official exposure, as a successfully committed reader would.
    e.seen[aid].add('G001');e.advance_to(3)
    views={p['root_content_id']:p for p in e.observe(aid,3).local_information['posts']}
    assert [c['comment_id'] for c in views['P001']['comments']]==['on-rumor']
    assert [c['comment_id'] for c in views['G001']['comments']]==['on-official']


def test_explicit_comment_target_not_first_post_and_next_tick_visibility(tmp_path):
    _,_,e=setup(tmp_path);e.advance_to(2)
    aid=next(a for a in e.direct_targets if e.by_id[a]['decision_mode']=='llm')
    ob=e.observe(aid,2);assert ob.local_information['posts'][0]['content_id']=='G001'
    raw=answer(ob);raw['comment']={'enabled':True,'target_content_id':'P001','text':'我在原帖下提出疑问'}
    e.apply([fake_action(ob,raw)])
    cid=f'C02-{aid}'
    assert e.comments[cid]['target_content_id']=='P001'
    assert cid not in {c['comment_id'] for p in e.observe(aid,2).local_information['posts'] for c in p['comments']}
    e.advance_to(3)
    post=next(p for p in e.observe('A0002',3).local_information['posts'] if p['content_id']=='P001')
    assert cid in {c['comment_id'] for c in post['comments']}


def test_illegal_comment_target_and_dropped_comments_are_atomic(tmp_path):
    _,_,e=setup(tmp_path);ob=e.observe('A0002',1)
    raw=answer(ob);raw['comment']={'enabled':True,'target_content_id':'G001','text':'不能评论未见官方帖'}
    before=digest(e.snapshot())
    with pytest.raises(ValueError,match='comment target'):e.apply([fake_action(ob,raw)])
    assert digest(e.snapshot())==before
    e.comments['old']=dict(comment_id='old',author_id='A0001',published_tick=1,target_content_id='P001',text='不得删掉')
    e.advance_to(2);ob=e.observe('A0002',2);action=fake_action(ob,answer(ob))
    next(p for p in action.payload['observed_posts'] if p['content_id']=='P001')['comments']=[]
    before=digest(e.snapshot())
    with pytest.raises(ValueError,match='every visible'):e.apply([action])
    assert digest(e.snapshot())==before


@pytest.mark.parametrize('missing',list(CONDITION_LABELS))
def test_missing_any_condition_rejected(tmp_path,missing):
    _,_,e=setup(tmp_path);ob=e.observe('A0002',1);raw=answer(ob)
    del raw['condition_application'][missing]
    with pytest.raises(ValueError,match='condition coverage') as ex:
        validate_response(raw,ob,ob.local_information['posts'],[])
    assert is_format_error(ex.value)


def test_conditions_use_current_assigned_trust_and_individual_profile(tmp_path):
    _,_,e=setup(tmp_path);ob=e.observe('A0002',1);inputs=condition_inputs(ob)
    assert set(inputs)==set(CONDITION_LABELS)
    assert inputs['source_trust']==e.cfg['source_trust']['A0002']
    assert inputs['government_trust']==e.cfg['government_trust']['A0002']
    assert inputs['age']==int(e.by_id['A0002']['synthetic_age'])
    old=condition_reference(ob);ob.local_physical['persona']['synthetic_age']='75'
    assert condition_reference(ob)!=old
    for a,r in e.by_id.items():
        if r['decision_mode']=='llm':assert len(condition_inputs(e.observe(a,1)))==11


def test_condition_context_and_malformed_notes_are_rejected(tmp_path):
    _,_,e=setup(tmp_path);ob=e.observe('A0002',1)
    raw=answer(ob);raw['condition_context_ref']='stale'
    with pytest.raises(ValueError):validate_condition_application(raw,ob)
    raw=answer(ob);raw['condition_application']['age']['affects']=[{}]
    with pytest.raises(ValueError):validate_condition_application(raw,ob)
    raw=answer(ob);raw['condition_application']['age']['note']='已考虑该条件'
    with pytest.raises(ValueError):validate_condition_application(raw,ob)


def test_incomplete_coverage_retries_then_pauses_without_cache(tmp_path,monkeypatch):
    cfg,_,e=setup(tmp_path);monkeypatch.setenv('RUMOR_LLM_API_KEY','test-not-real')
    c=LiveClient(cfg,tmp_path/'live-audit');ob=e.observe('A0002',1);raw=answer(ob)
    del raw['condition_application']['age']
    calls=[]
    def create(**kwargs):calls.append(kwargs);return response(raw)
    c.client.chat.completions.create=create
    with pytest.raises(DecisionConditionsPause):c.decide(ob,'{当前观察}')
    assert len(calls)==4
    assert all(call['messages'][0]['content'].startswith('{"posts":') for call in calls)
    assert 'missing_conditions' not in calls[0]['messages'][0]['content']
    assert all('"missing_conditions": ["age"]' in call['messages'][0]['content'] for call in calls[1:])
    assert c.budget['output_reserved_tokens']==4*1536
    assert not list(c.cache.glob('*.json'))
    with pytest.raises(DecisionConditionsPause):c.decide(ob,'{当前观察}')
    assert len(calls)==4


def test_full_comment_prompt_preserved_or_paused_no_silent_trimming(tmp_path):
    _,b,e=setup(tmp_path);dec=V4Decision(**b[3].decision_args)
    e.comments['test']=dict(comment_id='test',author_id='A0001',published_tick=1,target_content_id='P001',text='保留全部评论'*100)
    e.advance_to(2);ob=e.observe('A0002',2);before=copy.deepcopy(ob)
    prompt,feed,memory,n=prepare_prompt(dec.template,ob)
    assert '保留全部评论'*100 in prompt
    assert set(CONDITION_LABELS)<={k for k in condition_inputs(ob)}
    assert condition_reference(ob) in prompt
    with pytest.raises(PromptBudgetPause):prepare_prompt(dec.template,ob,limit=100)
    with pytest.raises(ValueError,match='cannot be silently trimmed'):
        prepare_prompt(dec.template,ob,memory_policy='trim_oldest')
    assert ob==before


def test_application_notes_committed_and_exported_only_for_completed_states(tmp_path):
    _,_,e=setup(tmp_path);ob=e.observe('A0002',1);raw=answer(ob)
    e.apply([fake_action(ob,raw)])
    s=e.agent_state('A0002');assert len(s['condition_application'])==11
    folder=tmp_path/'export/trajectory';folder.mkdir(parents=True)
    with (folder/'panel.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=['agent_id','step','state']);w.writeheader()
        w.writerow(dict(agent_id='A0002',step=1,state=json.dumps(s)))
        w.writerow(dict(agent_id='A0002',step=2,state=json.dumps(s)))
    from measurement_report import write_measurements
    write_measurements(folder.parent,e.rows,BINARY_SCORE_POLICY)
    with (folder/'condition_applications.csv').open(encoding='utf-8-sig') as f:rows=list(csv.DictReader(f))
    assert len(rows)==11 and {r['step'] for r in rows}=={'1'}


def test_condition_omission_is_atomic_at_commit_not_only_api_validation(tmp_path):
    _,_,e=setup(tmp_path);ob=e.observe('A0002',1);raw=answer(ob)
    del raw['condition_application']['source_trust']
    before=digest(e.snapshot())
    with pytest.raises(ValueError,match='condition coverage'):e.apply([fake_action(ob,raw)])
    assert digest(e.snapshot())==before


def test_shared_thread_warm_replay_preserves_conditions_comments_and_memory(tmp_path,monkeypatch):
    from socioverse.engine import build_simulator
    from socioverse.schemas import WarmStartSpec
    _,bundles,_=setup(tmp_path)
    original=V4Decision._scripted
    def sparse_comments(self,ob):
        raw=original(self,ob)
        if ob.agent_id not in ('A0002','A0003'):
            raw['comment']={'enabled':False,'target_content_id':None,'text':''}
        return raw
    # Small artificial comment volume keeps replay validation cheap. The live
    # policy has no such filter; the separate full-comment test checks all IDs.
    monkeypatch.setattr(V4Decision,'_scripted',sparse_comments)
    _,eb,pb,sc=bundles;sc.n_steps=3
    one=build_simulator(env_bundle=eb,pop_bundle=pb,sim_config=sc,store_path=tmp_path/'one.duckdb');one.run()
    sc.warm_start=WarmStartSpec(source_version='shared-thread-test',source_trajectory=str(tmp_path/'one.duckdb'),resume_from=1)
    two=build_simulator(env_bundle=eb,pop_bundle=pb,sim_config=sc,store_path=tmp_path/'two.duckdb');two.run()
    assert digest(one.env.snapshot())==digest(two.env.snapshot())
    assert sum(v is not None for v in two.env.condition_application.values())==305
    assert all(len(two.env.memory[aid])==3 for aid in two.env.by_id)


def test_verifier_reads_real_checkpoint_shape_and_detects_extra_comments(tmp_path):
    import shutil
    from model import dump
    from verify_run import verify
    cfg,_,e=setup(tmp_path)
    folder=tmp_path/'saved';frozen=tmp_path/'frozen';frozen.mkdir()
    shutil.copy2(SOURCE/'01_Agent基础信息表.csv',frozen/'01_Agent基础信息表.csv')
    dump(folder/'status.json',dict(status='completed_offline',last_completed_tick=1,dry_run=True))
    dump(folder/'simulation/simulation.json',dict(n_steps=1))
    dump(folder/'provenance.json',dict(config=cfg,config_dir=str(frozen)))
    actions=[]
    for aid,row in e.by_id.items():
        ob=e.observe(aid,1)
        raw=answer(ob) if row['decision_mode']=='llm' else dict(comment={'enabled':False,'target_content_id':None,'text':''})
        actions.append(dict(agent_id=aid,step=1,action_kind='decide',action_payload={
            'observed_posts':ob.local_information['posts'],'answer':raw}))
    dump(folder/'checkpoints/tick-001.json',dict(actions=actions,sha256=digest(actions)))
    base=dict(all_unjudged=582,all_believe=0,all_reject=0)
    dump(folder/'trajectory/metrics_history.json',{'rows':[dict(step=0,**base),dict(step=1,**base)]})
    (folder/'trajectory/belief_measurements.csv').write_text('decision_mode,belief,subjective_credibility\n',encoding='utf-8-sig')
    result=verify(folder)
    assert result['shared_thread_checks'][0]['llm_decisions_with_all_11_conditions']==305
    actions[0]['action_payload']['observed_posts'][0]['comments']=[dict(comment_id='extra',published_tick=0)]
    dump(folder/'checkpoints/tick-001.json',dict(actions=actions,sha256=digest(actions)))
    with pytest.raises(AssertionError):verify(folder)
