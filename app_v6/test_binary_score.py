"""Binary score policy boundary, API schema, feedback and export integration."""
import copy,csv,json
from types import SimpleNamespace
import pytest
from model import (BINARY_SCORE_POLICY,COMPONENT_KEYS,V4Decision,V4Environment,V4Metrics,
                   score_to_belief,normalize_answer,digest)
from run import SOURCE,defaults,make_bundles
from llm_client import validate_response,render_prompt,is_format_error

def setup(tmp_path):
    cfg={**defaults(),'belief_measurement_policy':BINARY_SCORE_POLICY,'llm_max_output_tokens':768,
        'government_tick':2,'government_reach':100,'targeting_inside_ratio':.8,'government_trust_mean':.75,'source_trust_gap':.4}
    b=make_bundles(SOURCE/'01_Agent基础信息表.csv',SOURCE/'02_Prompt固定提示词.md',cfg,tmp_path)
    env=V4Environment(b[1]);env.reset(20261020);env.advance_to(1)
    return b,env

def answer(score):
    return dict(subjective_credibility=score,component_credibility={k:50 for k in COMPONENT_KEYS},
                comment={'enabled':False,'text':''},repost={'enabled':False,'target_content_id':None,'text':''},evidence_ids=['P001'])

@pytest.mark.parametrize('score,label',[(0,'reject'),(49.999,'reject'),(50,'reject'),(50.0001,'believe'),(51,'believe'),(100,'believe')])
def test_strict_boundary_no_rounding(score,label):assert score_to_belief(score)==label

@pytest.mark.parametrize('score',[True,False,-.1,100.01,'51',None,float('nan'),float('inf')])
def test_invalid_score_does_not_default_to_reject(score):
    with pytest.raises(ValueError,match='invalid belief measurement'):score_to_belief(score)

def test_score_only_schema_and_raw_audit_unchanged(tmp_path):
    b,e=setup(tmp_path);ob=e.observe('A0002',1);raw=answer(50);original=copy.deepcopy(raw)
    validate_response(raw,ob,ob.local_information['posts'],[])
    result=normalize_answer(raw,ob.local_information['posts'],[],[],belief_policy=BINARY_SCORE_POLICY)
    assert result['belief']=='reject' and raw==original and 'belief' not in raw
    contradictory=answer(80);contradictory['belief']='uncertain'
    assert normalize_answer(contradictory,ob.local_information['posts'],[],[],belief_policy=BINARY_SCORE_POLICY)['belief']=='believe'
    missing=answer(70);missing.pop('subjective_credibility')
    with pytest.raises(ValueError) as ex:validate_response(missing,ob,ob.local_information['posts'],[])
    assert is_format_error(ex.value)

def test_binary_feedback_memory_metrics_and_csv(tmp_path):
    b,e=setup(tmp_path);dec=V4Decision(**b[3].decision_args);dec.mode='openai'
    raw=answer(50)
    class Fake:
        def decide(self,ob,template):return copy.deepcopy(raw),ob.local_information['posts'],{}
    dec.client=Fake();a=dec.decide_batch([e.observe('A0002',1)],{})[0]
    assert a.payload['answer']['belief']=='reject' and 'belief' not in a.payload['raw_answer']
    e.apply([a]);assert e.agent_state('A0002')['current_belief']=='reject'
    assert e.memory['A0002'][-1]['belief_after']=='reject' and e.memory['A0002'][-1]['subjective_credibility_after']==50
    metrics=V4Metrics().collect(e,[a],1)
    assert not any('uncertain' in k for k in metrics)
    assert metrics['llm_judged_n']==1 and metrics['llm_believe_rate_judged']==0
    folder=tmp_path/'export';(folder/'trajectory').mkdir(parents=True)
    with (folder/'trajectory/panel.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=['agent_id','step','state']);w.writeheader()
        for aid in e.by_id:w.writerow({'agent_id':aid,'step':1,'state':json.dumps(e.agent_state(aid))})
    from measurement_report import write_measurements
    write_measurements(folder,e.rows,BINARY_SCORE_POLICY)
    summary=json.loads((folder/'reports/binary_results.json').read_text(encoding='utf-8'))
    allrow=summary['results'][0]
    assert allrow['reject']==1 and allrow['judged_n']==1 and allrow['unjudged_n']==581
    assert allrow['believe_rate_judged']==0 and 'uncertain' not in str(summary)

def test_invalid_score_is_atomic_and_cannot_leak_state(tmp_path):
    b,e=setup(tmp_path);d=V4Decision(**b[3].decision_args)
    a=d.decide_batch([e.observe('A0002',1)],{})[0];a.payload['answer']['subjective_credibility']=101
    before=digest(e.snapshot())
    with pytest.raises(ValueError):e.apply([a])
    assert digest(e.snapshot())==before

def test_prompt_only_requests_scores_and_contains_exact_boundary(tmp_path):
    b,e=setup(tmp_path);d=V4Decision(**b[3].decision_args);ob=e.observe('A0002',1)
    prompt=render_prompt(d.template,ob,ob.local_information['posts'],[])
    assert 'uncertain' not in prompt and '不确定' not in prompt
    assert 'subjective_credibility > 50' in prompt and 'subjective_credibility <= 50' in prompt
    assert '不单独输出belief标签' in prompt and 'G001' not in prompt

def test_binary_checkpoint_replay_keeps_derived_labels(tmp_path):
    from socioverse.engine import build_simulator
    from socioverse.schemas import WarmStartSpec
    b,_=setup(tmp_path);_,eb,pb,sc=b;sc.n_steps=4
    first=build_simulator(env_bundle=eb,pop_bundle=pb,sim_config=sc,store_path=tmp_path/'one.duckdb');first.run()
    sc.warm_start=WarmStartSpec(source_version='binary-test',source_trajectory=str(tmp_path/'one.duckdb'),resume_from=2)
    second=build_simulator(env_bundle=eb,pop_bundle=pb,sim_config=sc,store_path=tmp_path/'two.duckdb');second.run()
    assert digest(first.env.snapshot())==digest(second.env.snapshot())
    assert set(second.env.beliefs.values())<=set(['believe','reject','unjudged'])
    assert all(second.env.beliefs[aid]==score_to_belief(score) for aid,score in second.env.credibility.items() if score is not None)
