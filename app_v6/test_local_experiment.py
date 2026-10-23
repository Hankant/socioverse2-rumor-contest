import copy
import itertools
from statistics import mean

import pytest
from experiment import source_trust_values, assignment_summary, validate_experiment
from government import select_targets, trust_values
from llm_client import render_prompt, prepare_prompt, PromptBudgetPause, LiveClient
from model import load_rows, V4Environment, V4Decision
from run import defaults, make_bundles, SOURCE, validate_execution_limit_migration


def research(**kwargs):
    return {**defaults(), 'source_trust_gap':.4, 'source_trust_center':.5, 'source_trust_sd':.1,
        'government_tick':2,'government_reach':100,'targeting_inside_ratio':.8,'government_trust_mean':.75,
        'prompt_input_token_limit':32768,'prompt_memory_policy':'preserve',**kwargs}


@pytest.mark.parametrize('gap',[0,.2,.4])
def test_source_trust_exact_means_and_stable_ranks(gap):
    rows=load_rows(SOURCE/'01_Agent基础信息表.csv')
    current=source_trust_values(rows,research(source_trust_gap=gap))
    baseline=source_trust_values(rows,research(source_trust_gap=0))
    assert current==source_trust_values(rows,research(source_trust_gap=gap))
    assert len(current)==582 and all(0<=v<=1 for v in current.values())
    for mode in ['llm','rule']:
        for group,sign in [('inside',1),('outside',-1)]:
            ids=[r['agent_id'] for r in rows if r['decision_mode']==mode and r['group']==group]
            assert mean(current[aid] for aid in ids)==pytest.approx(.5+sign*gap/2,abs=1e-12)
            assert sorted(ids,key=current.get)==sorted(ids,key=baseline.get)
            assert len(set(current[a] for a in ids))==len(ids)


@pytest.mark.parametrize('ratio,inside',[(.8,80),(.2,20)])
def test_hundred_recipients_are_not_believer_filtered(ratio,inside):
    rows=load_rows(SOURCE/'01_Agent基础信息表.csv')
    ids=select_targets(rows,research(targeting_inside_ratio=ratio))
    assert len(ids)==len(set(ids))==100
    assert sum(r['group']=='inside' for r in rows if r['agent_id'] in ids)==inside
    assert ids==select_targets(rows,research(targeting_inside_ratio=ratio))


@pytest.mark.parametrize('tg',[2,4,7])
def test_local_intervention_once_at_confirmed_tick(tg,tmp_path):
    b=make_bundles(SOURCE/'01_Agent基础信息表.csv',SOURCE/'02_Prompt固定提示词.md',research(government_tick=tg),tmp_path)
    assert b[3].n_steps==10
    env=V4Environment(b[1]);env.reset(1)
    for t in range(1,11):
        env.advance_to(t)
        obs=env.observe_batch(sorted(env.by_id),t)
        direct=[o.agent_id for o in obs if any(p['delivery']=='direct_government' for p in o.local_information['posts'])]
        assert len(direct)==(100 if t==tg else 0)


def test_source_and_government_trust_reach_llm_but_do_not_force_belief(tmp_path):
    b=make_bundles(SOURCE/'01_Agent基础信息表.csv',SOURCE/'02_Prompt固定提示词.md',research(),tmp_path)
    env=V4Environment(b[1]);env.reset(1);env.advance_to(1)
    aid=next(a for a in env.by_id if env.by_id[a]['decision_mode']=='llm' and env.by_id[a]['group']=='inside')
    ob=env.observe(aid,1)
    prompt=render_prompt('{稳定个人资料}\n{当前信念}',ob,ob.local_information['posts'],[])
    assert f"{ob.local_physical['source_trust']:.6f}" in prompt
    assert f"{ob.local_physical['government_trust']:.6f}" in prompt
    assert '不是对当前原始主张的相信概率' in prompt
    assert set(env.beliefs.values())=={'unjudged'}
    rule_id=next(a for a in env.by_id if env.by_id[a]['decision_mode']=='rule' and env.by_id[a]['group']=='inside')
    dec=V4Decision(**b[3].decision_args)
    _,draws=dec._rule(env.observe(rule_id,1))
    assert draws[0]['name']=='PB' and draws[0]['probability']==.579


def test_preserve_retains_five_whole_memories_and_never_mutates_observation(tmp_path):
    b=make_bundles(SOURCE/'01_Agent基础信息表.csv',SOURCE/'02_Prompt固定提示词.md',research(),tmp_path)
    env=V4Environment(b[1]);env.reset(1);env.advance_to(1);ob=env.observe('A0002',1)
    ob.local_physical['memory']=[dict(tick=t,observed_posts=copy.deepcopy(ob.local_information['posts']),
        belief_before='unjudged',belief_after='uncertain',comment={'enabled':False,'text':''},repost={'enabled':False,'target_content_id':None,'text':''}) for t in range(1,6)]
    original=copy.deepcopy(ob.model_dump())
    prompt,feed,memory,estimate=prepare_prompt('{个人记忆}\n{当前观察}',ob,limit=32768,memory_policy='preserve')
    assert len(memory)==5 and [m['tick'] for m in memory]==[1,2,3,4,5]
    assert estimate<=32768 and ob.model_dump()==original
    with pytest.raises(PromptBudgetPause):
        prepare_prompt('{个人记忆}\n{当前观察}',ob,limit=100,memory_policy='preserve')
    assert ob.model_dump()==original


def test_prompt_pause_occurs_before_any_request_or_reservation(tmp_path,monkeypatch):
    b=make_bundles(SOURCE/'01_Agent基础信息表.csv',SOURCE/'02_Prompt固定提示词.md',research(),tmp_path/'cfg')
    env=V4Environment(b[1]);env.reset(1);env.advance_to(1);ob=env.observe('A0002',1)
    monkeypatch.setenv('RUMOR_LLM_API_KEY','test-not-real')
    client=LiveClient(research(prompt_input_token_limit=512),tmp_path/'audit')
    monkeypatch.setattr('llm_client.estimated_input_tokens',lambda text:1000)
    with pytest.raises(PromptBudgetPause):client.decide(ob,'{当前观察}')
    assert client.budget['requests']==0
    assert not list((tmp_path/'audit').glob('request-*.json'))


@pytest.mark.parametrize('bad',[
    {'source_trust_gap':.3},{'source_trust_sd':-.1},{'source_trust_center':.99},
    {'source_trust_gap':float('nan')},{'prompt_memory_policy':'drop_everything'},
    {'prompt_input_token_limit':0},{'pbd':.2},{'source_trust_seed':-1},
])
def test_invalid_new_parameters_are_rejected(bad):
    with pytest.raises(ValueError):validate_experiment(research(**bad))


def test_all_54_condition_assignments_are_feasible_and_correct():
    rows=load_rows(SOURCE/'01_Agent基础信息表.csv')
    conditions=set()
    for gap,tg,ratio,gt in itertools.product([0,.2,.4],[2,4,7],[.2,.8],[.25,.5,.75]):
        cfg=research(source_trust_gap=gap,government_tick=tg,targeting_inside_ratio=ratio,government_trust_mean=gt)
        source=source_trust_values(rows,cfg);gov=trust_values(rows,cfg);ids=select_targets(rows,cfg)
        summary=assignment_summary(rows,source,gov)
        assert summary['source_trust']['all/inside']['mean']-summary['source_trust']['all/outside']['mean']==pytest.approx(gap)
        assert summary['government_trust']['all/all']['mean']==pytest.approx(gt)
        assert len(ids)==100
        conditions.add((gap,tg,ratio,gt))
    assert len(conditions)==54


def test_execution_limit_resume_only_accepts_upward_ceilings():
    old={k:'same' for k in ['input_sha256','code_sha256','mode','upstream_commit','total_steps','numpy_version']}
    old['config']=research()
    new=copy.deepcopy(old);new['config']['prompt_input_token_limit']=65536
    validate_execution_limit_migration(old,new)
    for field,val in [('government_tick',4),('source_trust_gap',.2),('prompt_memory_policy','trim_oldest'),('prompt_input_token_limit',1024)]:
        changed=copy.deepcopy(old);changed['config'][field]=val
        with pytest.raises(ValueError):validate_execution_limit_migration(old,changed)


def test_prompt_pause_then_limit_only_resume_without_any_real_api(tmp_path,monkeypatch):
    import json
    from types import SimpleNamespace
    import run
    calls=[]
    answer={'belief':'uncertain','comment':{'enabled':False,'text':''},
        'repost':{'enabled':False,'target_content_id':None,'text':''},'evidence_ids':[]}
    def create(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(model='mock-test',usage=SimpleNamespace(prompt_tokens=100,completion_tokens=20),
            choices=[SimpleNamespace(finish_reason='stop',message=SimpleNamespace(content=json.dumps(answer)))])
    monkeypatch.setattr('openai.OpenAI',lambda **kwargs:SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create))))
    monkeypatch.setenv('RUMOR_LLM_API_KEY','sk-cp-test-not-real')
    for key,suffix in [('RESULTS','runs'),('CONFIGS','configs'),('LOGS','logs')]:monkeypatch.setattr(run,key,tmp_path/suffix)
    cfg=research(model='MiniMax-M3',base_url='https://api.minimax.cn/v1',api_profile='minimax_m3',
        contract_status='authorized_engineering_run',max_concurrency=1,prompt_input_token_limit=512,max_requests=100)
    config_path=tmp_path/'config.json';config_path.write_text(json.dumps(cfg),encoding='utf-8')
    args=SimpleNamespace(config=str(config_path),live=True,token_plan_run=True,max_requests=100,steps=1,
        resume=None,concurrency=None,cost_limit_configured=False)
    with pytest.raises(RuntimeError,match='PromptBudgetPause'):run.execute(args)
    parents=list((tmp_path/'runs').glob('government-*'));assert len(parents)==1
    parent=parents[0]
    state=json.loads((parent/'status.json').read_text(encoding='utf-8'))
    assert state['status']=='paused_prompt_budget' and state['last_completed_tick']==0 and not calls
    cfg['prompt_input_token_limit']=32768;config_path.write_text(json.dumps(cfg),encoding='utf-8')
    args.resume=str(parent);args.execution_limit_migration=True
    resumed=run.execute(args)
    state=json.loads((resumed/'status.json').read_text(encoding='utf-8'))
    assert state['status']=='completed_live' and state['last_completed_tick']==1 and len(calls)==43
    assert 'execution_limit_migration' in json.loads((resumed/'provenance.json').read_text(encoding='utf-8'))


def test_explicit_cli_factor_overrides_json_file(tmp_path):
    import json
    from types import SimpleNamespace
    from local_cli import config_for
    path=tmp_path/'override.json';path.write_text(json.dumps({'government_tick':2}),encoding='utf-8')
    cfg=config_for(SimpleNamespace(config=str(path),tg=4))
    assert cfg['government_tick']==4
