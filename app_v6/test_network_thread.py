"""Network-gated first exposure, complete comments, and independent official posts."""
import copy
import json
from types import SimpleNamespace

import pytest
from socioverse.schemas import WarmStartSpec
from socioverse.engine import build_simulator
from model import (V4Environment,V4Decision,V4Metrics,NETWORK_FEED_POLICY,BINARY_SCORE_POLICY,
                   empty_answer,dump,digest,allowed_evidence_ids)
from run import make_bundles,SOURCE
from llm_client import prepare_prompt,validate_response,PromptBudgetPause
from test_shared_thread import setup as shared_setup, answer, fake_action


def setup(tmp_path, government_tick=2):
    cfg,_,_=shared_setup(tmp_path)
    cfg.update(feed_policy=NETWORK_FEED_POLICY,government_tick=government_tick)
    bundles=make_bundles(SOURCE/'01_Agent基础信息表.csv',SOURCE/'02_Prompt固定提示词.md',cfg,tmp_path/'audit')
    env=V4Environment(bundles[1]);env.reset(cfg['behavior_seed']);env.advance_to(1)
    return cfg,bundles,env


def chain(tmp_path):
    cfg,b,e=setup(tmp_path,7)
    e.following={a:({'SOURCE'} if r['group']=='inside' else set()) for a,r in e.by_id.items()}
    e.following['A0084']={'A0002'}
    e.following['A0085']={'A0084'}
    return cfg,b,e


def act(e,aid,*,repost=False,comment=False,root='P001'):
    ob=e.observe(aid,e.t)
    raw=answer(ob) if e.by_id[aid]['decision_mode']=='llm' else empty_answer('reject')
    raw['evidence_ids']=[root]
    if repost:raw['repost']={'enabled':True,'target_content_id':root,'text':'离线测试转发附言'}
    if comment:raw['comment']={'enabled':True,'target_content_id':root,'text':'离线测试完整评论'}
    return fake_action(ob,raw)


def roots(ob):return [p['root_content_id'] for p in ob.local_information['posts']]


def test_initial_82_followers_and_500_unexposed_observe_has_no_side_effect(tmp_path):
    _,_,e=setup(tmp_path)
    before=digest(e.snapshot())
    observed=e.observe_batch(list(e.by_id),1)
    readers=[o.agent_id for o in observed if roots(o)]
    assert len(readers)==82
    assert sum(e.by_id[a]['decision_mode']=='llm' for a in readers)==43
    assert sum(e.by_id[a]['decision_mode']=='rule' for a in readers)==39
    assert all('SOURCE' in e.following[a] for a in readers)
    assert all(not roots(o) for o in observed if e.by_id[o.agent_id]['group']=='outside')
    assert digest(e.snapshot())==before
    assert not roots(e.observe('A0002',0))


def test_no_reposts_no_rumor_diffusion_even_when_comments_exist(tmp_path):
    _,_,e=chain(tmp_path)
    for tick in range(1,7):
        e.advance_to(tick)
        actions=[act(e,a,comment=True) for a,r in e.by_id.items() if r['group']=='inside']
        e.apply(actions)
        assert sum('P001' in e.seen[a] for a in e.by_id)==82
        assert all(not roots(e.observe(a,tick)) for a,r in e.by_id.items() if r['group']=='outside')
    assert len(e.comments)==6*82


def test_directional_multihop_diffusion_one_round_lag_and_single_root(tmp_path):
    _,_,e=chain(tmp_path)
    e.apply([act(e,'A0002',repost=True,comment=True)])
    assert not roots(e.observe('A0084',1))
    e.advance_to(2)
    ob=e.observe('A0084',2)
    assert roots(ob)==['P001'] and not ob.local_information['posts'][0]['is_reread']
    assert ob.local_information['posts'][0]['delivery']=='followee_rumor_repost'
    assert ob.local_information['posts'][0]['relay_context'][0]['author_id']=='A0002'
    assert not roots(e.observe('A0085',2))
    e.apply([act(e,'A0084',repost=True,comment=True)])
    assert not roots(e.observe('A0085',2))
    e.advance_to(3)
    ob=e.observe('A0085',3)
    assert roots(ob)==['P001']
    assert [r['author_id'] for r in ob.local_information['posts'][0]['relay_context']]==['A0084']
    assert len(ob.local_information['posts'][0]['comments'])==2
    assert 'A0002' not in e.following['A0085']  # Its comment is public after root access.
    assert not roots(e.observe('A0086',3))


def test_following_direction_is_not_reversed(tmp_path):
    _,_,e=chain(tmp_path)
    e.following['A0002'].add('A0086')  # SOURCE-follower follows outsider, not vice versa.
    e.apply([act(e,'A0002',repost=True)])
    e.advance_to(2)
    assert not roots(e.observe('A0086',2))


def test_seen_root_revisit_keeps_all_comments_without_current_relay(tmp_path):
    _,_,e=chain(tmp_path)
    e.apply([act(e,'A0002',repost=True)])
    e.advance_to(2);e.apply([act(e,'A0084')])
    e.posts.pop('RP01-A0002');e.following['A0084']=set()
    for i in range(107):
        e.comments[f'C-extra-{i:03d}']=dict(comment_id=f'C-extra-{i:03d}',author_id='A0087',
            published_tick=2,target_content_id='P001',text=f'必须完整保留的评论{i}')
    e.comments['future']=dict(comment_id='future',author_id='A0087',published_tick=3,target_content_id='P001',text='本轮未来评论')
    e.advance_to(3)
    post=e.observe('A0084',3).local_information['posts'][0]
    assert post['is_reread'] and post['delivery']=='rumor_thread_revisit'
    assert len(post['comments'])==107 and post['relay_context']==[]
    assert not roots(e.observe('A0085',3))
    assert e.exposure_history['A0084']['P001']['ticks']==[2]


def test_observation_without_commit_does_not_grant_permanent_access(tmp_path):
    _,_,e=chain(tmp_path)
    e.apply([act(e,'A0002',repost=True)])
    e.advance_to(2)
    assert roots(e.observe('A0084',2))==['P001']
    e.posts.pop('RP01-A0002')
    e.advance_to(3)
    assert not roots(e.observe('A0084',3)) and 'P001' not in e.seen['A0084']


def test_official_only_exposure_does_not_unlock_rumor_or_comments(tmp_path):
    _,_,e=setup(tmp_path)
    outside=next(a for a in e.direct_targets if e.by_id[a]['group']=='outside' and e.by_id[a]['decision_mode']=='llm')
    assert not roots(e.observe(outside,1))
    e.comments['hidden']=dict(comment_id='hidden',author_id='A0002',published_tick=1,target_content_id='P001',text='原帖评论不能提前泄露')
    e.advance_to(2)
    ob=e.observe(outside,2)
    assert roots(ob)==['G001'] and ob.local_information['posts'][0]['comments']==[]
    direct=[o for o in e.observe_batch(list(e.by_id),2) if 'G001' in roots(o)]
    assert len(direct)==100
    assert sum(e.by_id[o.agent_id]['group']=='inside' for o in direct)==80
    e.apply([act(e,outside,comment=True,root='G001')])
    e.advance_to(3)
    assert roots(e.observe(outside,3))==['G001']
    assert e.seen[outside]=={'G001'}
    forged=act(e,outside,root='G001')
    forged.payload['answer']['comment']={'enabled':True,'target_content_id':'P001','text':'不得向未见的原帖评论'}
    with pytest.raises(ValueError,match='comment target'):e.apply([forged])


def test_unexposed_users_are_idle_no_api_no_memory_not_reject(tmp_path):
    cfg,b,e=setup(tmp_path,7)
    cfg['max_concurrency']=1
    dec=V4Decision(cfg,SOURCE/'02_Prompt固定提示词.md',tmp_path/'audit','scripted');dec.mode='openai'
    calls=[]
    def decide(ob,template):
        calls.append(ob.agent_id)
        assert e.by_id[ob.agent_id]['group']=='inside'
        return answer(ob),ob.local_information['posts'],{}
    dec.client=SimpleNamespace(decide=decide)
    actions=dec.decide_batch(e.observe_batch(list(e.by_id),1),{})
    assert len(actions)==582 and len(calls)==43
    assert sum(a.kind=='idle' for a in actions)==500
    e.apply(actions)
    assert all(e.beliefs[a]=='unjudged' and e.memory[a]==[] for a,r in e.by_id.items() if r['group']=='outside')
    m=V4Metrics().collect(e,actions,1)
    assert m['rumor_readers_this_tick']==m['rumor_new_reach']==m['rumor_cumulative_reach']==82
    assert m['all_unjudged']==500 and m['llm_judged_n']==43
    assert m['rumor_coverage_rate']==pytest.approx(82/582)


def test_prompt_matches_actual_network_path_and_visible_relay_is_valid_evidence(tmp_path):
    _,b,e=chain(tmp_path);dec=V4Decision(**b[3].decision_args)
    prompt,_,_,_=prepare_prompt(dec.template,e.observe('A0002',1))
    assert '已经关注' in prompt and '全体用户每轮阅读同一条SOURCE' not in prompt
    e.apply([act(e,'A0002',repost=True)])
    e.advance_to(2);ob=e.observe('A0084',2)
    prompt,feed,memory,_=prepare_prompt(dec.template,ob)
    assert '账号转发' in prompt and 'RP01-A0002' in prompt and '未接触者不会获得' in prompt
    assert 'RP01-A0002' in allowed_evidence_ids(feed,memory)
    raw=answer(ob);raw['evidence_ids']=['RP01-A0002']
    validate_response(raw,ob,feed,memory)
    raw['evidence_ids']=['RP01-not-followed']
    with pytest.raises(ValueError,match='evidence'):validate_response(raw,ob,feed,memory)


def test_full_comment_observation_cannot_be_trimmed_or_tampered(tmp_path):
    _,b,e=setup(tmp_path,7)
    for i in range(19):
        e.comments[f'CC{i}']=dict(comment_id=f'CC{i}',author_id='A0084',published_tick=1,target_content_id='P001',text='长评论必须保留'*20)
    e.advance_to(2);ob=e.observe('A0002',2);dec=V4Decision(**b[3].decision_args)
    prompt,feed,_,_=prepare_prompt(dec.template,ob)
    assert len(feed[0]['comments'])==19
    with pytest.raises(PromptBudgetPause):prepare_prompt(dec.template,ob,limit=100)
    with pytest.raises(ValueError,match='cannot be silently trimmed'):prepare_prompt(dec.template,ob,memory_policy='trim_oldest')
    a=act(e,'A0002');a.payload['observed_posts'][0]['comments'].pop()
    before=digest(e.snapshot())
    with pytest.raises(ValueError,match='every visible'):e.apply([a])
    assert digest(e.snapshot())==before


def test_network_warm_replay_preserves_exposure_comments_and_state(tmp_path,monkeypatch):
    _,b,_=setup(tmp_path)
    original=V4Decision._scripted
    def sparse(self,ob):
        raw=original(self,ob)
        if ob.agent_id not in ('A0002','A0084'):
            raw['comment']={'enabled':False,'target_content_id':None,'text':''}
        return raw
    monkeypatch.setattr(V4Decision,'_scripted',sparse)
    _,eb,pb,sc=b;sc.n_steps=3
    one=build_simulator(env_bundle=eb,pop_bundle=pb,sim_config=sc,store_path=tmp_path/'one.duckdb')
    history=one.run()
    sc.warm_start=WarmStartSpec(source_version='network-test',source_trajectory=str(tmp_path/'one.duckdb'),resume_from=1)
    two=build_simulator(env_bundle=eb,pop_bundle=pb,sim_config=sc,store_path=tmp_path/'two.duckdb');two.run()
    assert digest(one.env.snapshot())==digest(two.env.snapshot())
    assert history.rows[1]['rumor_cumulative_reach']==82
    assert history.rows[2]['rumor_cumulative_reach']>82
    outside_memories=[one.env.memory[a] for a,r in one.env.by_id.items() if r['group']=='outside' and one.env.memory[a]]
    assert outside_memories and all(m[0]['tick']>=2 for m in outside_memories)


def test_active_54_conditions_have_network_policy_and_preserved_design():
    import re
    from run import ROOT,defaults
    from local_cli import load_local_defaults
    from experiment import validate_experiment
    from comment_policy import LATEST_FEED_POLICY,PARTICIPATION_POLICY,MEMORY_POLICY
    assert load_local_defaults()['feed_policy']==LATEST_FEED_POLICY
    paths=[p for p in (ROOT/'configs/research54').glob('*.json') if re.fullmatch(r'D\d{3}_T\d{2}_C\d{3}_G\d{3}',p.stem)]
    assert len(paths)==54
    for p in paths:
        cfg=json.loads(p.read_text(encoding='utf-8'));validate_experiment(cfg)
        assert cfg['feed_policy']==LATEST_FEED_POLICY and cfg['runtime_version']==defaults()['runtime_version']
        assert cfg['comment_window_limit']==50 and cfg['comment_participation_policy']==PARTICIPATION_POLICY
        assert cfg['memory_comment_policy']==MEMORY_POLICY
        assert cfg['government_reach']==100 and cfg['max_requests']==12200 and cfg['prompt_input_token_limit']==32768
