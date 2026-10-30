import json
from collections import Counter
import pytest
import run
from model import load_rows,make_network,score_to_belief
from experiment import source_trust_values,assignment_summary,validate_experiment
from government import select_targets,trust_values


def test_population_and_balanced_synthetic_profiles():
    rows=load_rows(run.SOURCE/'01_Agent基础信息表.csv')
    assert len(rows)==300 and Counter(r['group'] for r in rows)==dict(inside=48,outside=252)
    assert {r['decision_mode'] for r in rows}=={'llm'}
    counts=Counter(r['synthetic_mbti_type'] for r in rows)
    assert len(counts)==16 and sorted(counts.values())==[18]*4+[19]*12
    assert len({r['source_profile_v6_id'] for r in rows})==300


def test_network_degree_direction_and_source():
    rows=load_rows(run.SOURCE/'01_Agent基础信息表.csv');by_id={r['agent_id']:r for r in rows};edges=make_network(rows)
    assert edges==make_network(rows) and len(edges)==len(set(edges))==3048
    for row in rows:
        neighbors=[b for a,b in edges if a==row['agent_id']]
        assert ('SOURCE' in neighbors)==(row['group']=='inside')
        users=[b for b in neighbors if b!='SOURCE']
        assert len(users)==10 and row['agent_id'] not in users
        assert sum(by_id[b]['group']==row['group'] for b in users)==8


@pytest.mark.parametrize('path',sorted((run.ROOT/'configs/v7/research54').glob('*.json')),ids=lambda p:p.stem)
def test_all_54_factor_designs(path):
    cfg=run.read_config(path);rows=load_rows(run.SOURCE/'01_Agent基础信息表.csv');by_id={r['agent_id']:r for r in rows}
    validate_experiment(cfg);targets=select_targets(rows,cfg)
    assert len(targets)==len(set(targets))==50 and targets==select_targets(rows,cfg)
    assert sum(by_id[a]['group']=='inside' for a in targets)==round(50*cfg['targeting_inside_ratio'])
    s=source_trust_values(rows,cfg);g=trust_values(rows,cfg);summary=assignment_summary(rows,s,g)
    assert summary['source_trust']['inside']['mean']-summary['source_trust']['outside']['mean']==pytest.approx(cfg['source_trust_gap'])
    assert summary['government_trust']['all']['mean']==pytest.approx(cfg['government_trust_mean'])
    assert all(0<=v<=1 for v in [*s.values(),*g.values()])
    assert not set(cfg)&{'PB','PBd','PBc','RC','RF','rule_mode'}


@pytest.mark.parametrize('patch',[{'population_n':582},{'inside_n':80},{'outside_n':277},{'government_reach':100},
    {'comment_window_limit':50},{'memory_window_ticks':5},{'feed_policy':'shared_rumor_all_comments_v1'},{'decision_mode':'rule'}])
def test_reject_incompatible_old_settings(patch):
    with pytest.raises(ValueError):validate_experiment(dict(run.read_config(),**patch))


@pytest.mark.parametrize('score,expected',[(0,'reject'),(49.9,'reject'),(50,'reject'),(50.00001,'believe'),(100,'believe')])
def test_binary_boundary(score,expected):assert score_to_belief(score)==expected


@pytest.mark.parametrize('score',[True,None,'60',-1,101,float('nan'),float('inf')])
def test_invalid_scores(score):
    with pytest.raises(ValueError):score_to_belief(score)
