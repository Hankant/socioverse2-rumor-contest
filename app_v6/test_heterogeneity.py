"""Population invariants and end-to-end measurement persistence; no paid calls."""
import copy
import csv
import json
from collections import Counter
from pathlib import Path
import pytest
from socioverse.schemas import Action
from build_heterogeneity import CONFIG,generate,quotas
from llm_client import validate_response,is_format_error,request_options,render_prompt
from model import V4Environment,V4Decision,COMPONENT_KEYS,empty_answer,validate_belief_measurement
from run import SOURCE,defaults,make_bundles

def roster():
    with (SOURCE/'01_Agent基础信息表.csv').open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))

def setup(tmp_path):
    cfg={**defaults(),'belief_measurement_policy':'subjective_credibility_v1','llm_max_output_tokens':768,
         'government_tick':2,'government_reach':100,'targeting_inside_ratio':.8,
         'government_trust_mean':.75,'source_trust_gap':.4}
    b=make_bundles(SOURCE/'01_Agent基础信息表.csv',SOURCE/'02_Prompt固定提示词.md',cfg,tmp_path)
    env=V4Environment(b[1]);env.reset(20261020);env.advance_to(1)
    return b,env

def test_reproducible_profiles_preserve_observations_and_traits():
    old=roster();cfg=json.loads(CONFIG.read_text(encoding='utf-8'));a,_=generate(old,cfg);b,_=generate(old,cfg)
    assert a==b==old
    protected=['agent_id','decision_mode','group','location','sex','followers_count','statuses_count','sharing_propensity','verification_preference','source_prior','government_prior','repetition_sensitivity']
    assert all(all(x[k]==y[k] for k in protected) for x,y in zip(old,a))

def test_quotas_and_stratification():
    rows=roster();counts=Counter(r['synthetic_mbti_type'] for r in rows)
    assert len(rows)==582 and len(counts)==16 and sorted(counts.values())==[36]*10+[37]*6
    for mode in ['llm','rule']:
        counts=Counter(r['synthetic_mbti_type'] for r in rows if r['decision_mode']==mode)
        assert len(counts)==16 and max(counts.values())-min(counts.values())<=1
        for group in ['inside','outside']:
            assert len({r['synthetic_mbti_type'] for r in rows if r['decision_mode']==mode and r['group']==group})==16
    assert sum(quotas(582,{'a':.3,'b':.7}).values())==582

def test_all_ages_occupations_and_synthetic_labels():
    rows=roster();cfg=json.loads(CONFIG.read_text(encoding='utf-8'));jobs={j['label']:j for j in cfg['occupations']}
    for r in rows:
        age=int(r['synthetic_age']);j=jobs[r['synthetic_occupation']]
        assert 18<=age<=75 and j['min_age']<=age<=j['max_age']
        assert r['location'] is not None and r['synthetic_region'] and r['synthetic_personality_description']
        assert '非原账户已核实' in r['synthetic_demographic_basis'] and '非正式测评' in r['synthetic_mbti_basis']
        assert '本次' in r['synthetic_role_experience']

@pytest.mark.parametrize('score',[True,-1,101,float('nan'),float('inf'),'70',None])
def test_invalid_measurements_are_retriable_format_errors(score):
    a=empty_answer('uncertain');a.update(subjective_credibility=score,component_credibility={k:50 for k in COMPONENT_KEYS})
    with pytest.raises(ValueError,match='invalid belief measurement') as exc:validate_belief_measurement(a,required=True)
    assert is_format_error(exc.value)

def test_extended_schema_required_and_legacy_supported(tmp_path):
    b,env=setup(tmp_path);ob=env.observe('A0002',1);a=empty_answer('uncertain')
    with pytest.raises(ValueError,match='invalid belief measurement'):validate_response(a,ob,ob.local_information['posts'],[])
    validate_belief_measurement(a,required=False)
    a.update(subjective_credibility=73.5,component_credibility={k:70 for k in COMPONENT_KEYS})
    validate_response(a,ob,ob.local_information['posts'],[])
    assert a['belief']=='uncertain' # no automatic threshold conversion
    bad=copy.deepcopy(a);bad['component_credibility'].pop('causal_link')
    with pytest.raises(ValueError):validate_belief_measurement(bad)
    assert request_options(b[3].decision_args['config'])['max_tokens']==768

def test_state_memory_and_exports_preserve_self_reports(tmp_path):
    b,env=setup(tmp_path);dec=V4Decision(**b[3].decision_args)
    actions=dec.decide_batch(env.observe_batch(sorted(env.by_id),1),{});env.apply(actions)
    a=next(a for a in actions if a.agent_id=='A0002');score=a.payload['raw_answer']['subjective_credibility']
    assert env.agent_state('A0002')['subjective_credibility']==score
    assert env.observe('A0002',1).local_physical['subjective_credibility']==score
    assert env.memory['A0002'][-1]['subjective_credibility_after']==score
    assert env.snapshot()['subjective_credibility']['A0002']==score
    rule=next(a for a in actions if env.by_id[a.agent_id]['decision_mode']=='rule' and a.kind=='decide')
    assert env.agent_state(rule.agent_id)['subjective_credibility'] is None
    folder=tmp_path/'export';(folder/'trajectory').mkdir(parents=True)
    with (folder/'trajectory/panel.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=['agent_id','step','state']);w.writeheader()
        for aid in ['A0002',rule.agent_id]:w.writerow({'agent_id':aid,'step':1,'state':json.dumps(env.agent_state(aid))})
    from measurement_report import write_measurements
    path=write_measurements(folder,env.rows)
    with path.open(encoding='utf-8-sig') as f:out={r['agent_id']:r for r in csv.DictReader(f)}
    assert float(out['A0002']['subjective_credibility'])==score and out['A0002']['funds_redirected']!=''
    assert out[rule.agent_id]['subjective_credibility']=='' and out[rule.agent_id]['measurement_status']=='not_applicable_rule'

def test_profile_and_measurement_prompt_has_no_future_or_other_private_data(tmp_path):
    b,env=setup(tmp_path);ob=env.observe('A0002',1);dec=V4Decision(**b[3].decision_args)
    p=render_prompt(dec.template,ob,ob.local_information['posts'],[])
    assert 'synthetic_mbti_type' in p and 'subjective_credibility' in p and 'causal_link' in p
    assert 'G001' not in p and '谣言' not in p and 'A0003' not in p
    assert '{当前主观可信度}' not in p


def test_invalid_score_prevents_whole_batch_commit(tmp_path):
    from model import digest
    b,env=setup(tmp_path);dec=V4Decision(**b[3].decision_args)
    actions=dec.decide_batch(env.observe_batch(['A0002','A0003'],1),{})
    bad=copy.deepcopy(actions);bad[0].payload['answer']['subjective_credibility']=101
    before=digest(env.snapshot())
    with pytest.raises(ValueError,match='invalid belief measurement'):env.apply(bad)
    assert digest(env.snapshot())==before


def test_warm_replay_restores_extended_measurements(tmp_path):
    from model import digest
    from socioverse.engine import build_simulator
    from socioverse.schemas import WarmStartSpec
    b,_=setup(tmp_path);_,eb,pb,sc=b;sc.n_steps=4
    first=build_simulator(env_bundle=eb,pop_bundle=pb,sim_config=sc,store_path=tmp_path/'first.duckdb');first.run()
    sc.warm_start=WarmStartSpec(source_version='extended-test',source_trajectory=str(tmp_path/'first.duckdb'),resume_from=3)
    second=build_simulator(env_bundle=eb,pop_bundle=pb,sim_config=sc,store_path=tmp_path/'second.duckdb');second.run()
    assert digest(first.env.snapshot())==digest(second.env.snapshot())
    assert any(v is not None for v in second.env.credibility.values())


def test_768_output_reservation_and_budget_stop_before_dispatch(tmp_path,monkeypatch):
    from types import SimpleNamespace
    from test_recovery import client,observation,response,valid
    c=client(tmp_path,monkeypatch);ob=observation(tmp_path)
    c.cfg.update(llm_max_output_tokens=768,max_output_reserved_tokens=1000,rate_limit_spacing_seconds=0)
    calls=[]
    def create(**kwargs):calls.append(kwargs);return response(valid())
    c.client=SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    c.decide(ob,'{当前观察}')
    assert calls[0]['max_tokens']==768 and c.budget['output_reserved_tokens']==768
    second=copy.deepcopy(ob);second.agent_id='A0003'
    with pytest.raises(RuntimeError,match='hard budget'):c.decide(second,'{当前观察}')
    assert len(calls)==1 and c.budget['requests']==1
