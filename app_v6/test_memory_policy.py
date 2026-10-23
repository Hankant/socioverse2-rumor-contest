"""Tick-based expiry, unchanged persistent state, wire inputs and replay."""
import copy
import pytest
from socioverse.engine import build_simulator
from socioverse.schemas import WarmStartSpec
from memory_policy import ROLLING, LEGACY, retained_memory
from model import V4Environment, digest
from run import SOURCE, make_bundles
from experiment import validate_experiment
from test_latest_comments import setup as latest_setup, template, comment
from test_network_thread import act
from test_shared_thread import fake_action, answer
from decision_conditions import condition_reference, condition_inputs
from llm_client import prepare_prompt
from response_contract import wire_prompt
from parameter_report import write_parameters


def setup(tmp_path):
    cfg, _, _ = latest_setup(tmp_path, 7)
    cfg.update(memory_retention_policy=ROLLING, memory_window_ticks=3)
    b = make_bundles(SOURCE/'01_Agent基础信息表.csv', SOURCE/'02_Prompt固定提示词.md', cfg, tmp_path/'audit')
    e = V4Environment(b[1]); e.reset(cfg['behavior_seed']); e.advance_to(1)
    return cfg, b, e


def test_three_past_ticks_and_expire_even_without_action(tmp_path):
    _, _, e = setup(tmp_path)
    for tick in (1, 2, 3):
        e.advance_to(tick)
        assert [m['tick'] for m in e.observe('A0002', tick).local_physical['memory']] == list(range(1, tick))
        e.apply([act(e, 'A0002')])
    e.advance_to(4)
    assert [m['tick'] for m in e.memory['A0002']] == [1, 2, 3]
    # No observation/action at ticks 4, 5 or 6: memory still ages by ticks.
    e.advance_to(5)
    assert [m['tick'] for m in e.memory['A0002']] == [2, 3]
    e.advance_to(7)
    assert e.observe('A0002', 7).local_physical['memory'] == []


def test_expiry_does_not_reset_belief_network_or_archive(tmp_path):
    _, _, e = setup(tmp_path)
    e.apply([act(e, 'A0002', repost=True, comment=True)])
    before = {key: copy.deepcopy(getattr(e, key)) for key in
              ('beliefs', 'credibility', 'seen', 'reposted', 'following', 'posts', 'comments', 'exposure_history')}
    e.advance_to(5)
    assert e.memory['A0002'] == []
    for key, value in before.items():
        assert getattr(e, key) == value
    ob = e.observe('A0002', 5)
    assert ob.local_physical['current_belief'] == 'believe'
    assert ob.local_information['posts'][0]['can_repost'] is False


def test_observation_read_only_and_does_not_leak_expired_memory(tmp_path):
    _, _, e = setup(tmp_path)
    e.apply([act(e, 'A0002')])
    before = digest(e.snapshot())
    assert e.observe('A0002', 5).local_physical['memory'] == []
    assert digest(e.snapshot()) == before


def test_prompt_window_conditions_and_all_current_comments(tmp_path):
    cfg, _, e = setup(tmp_path)
    for tick in range(1, 7):
        e.advance_to(tick); e.apply([act(e, 'A0002')])
    for i in range(150):
        c = comment(i, 6); e.comments[c['comment_id']] = c
    e.advance_to(7); ob = e.observe('A0002', 7)
    base, feed, memory, _ = prepare_prompt(template(), ob, limit=2_000_000, encoding='lossless_thread_refs_v1')
    sent = wire_prompt(base, ob, 1536, style=cfg['wire_prompt_style'])
    assert [m['tick'] for m in memory] == [4, 5, 6]
    assert sum(len(p['comments']) for p in feed) == 100
    assert len(condition_inputs(ob)) == 11
    assert condition_inputs(ob)['history_and_memory']['window_ticks'] == 3
    assert '过去3个模拟轮次' in base and '过去3个模拟轮次' in sent
    assert '最近5次' not in sent
    e.apply([fake_action(ob, answer(ob))])
    assert [m['tick'] for m in e.memory['A0002']] == [5, 6, 7]
    write_parameters(tmp_path, cfg, 10)
    assert '过去3个模拟轮次' in (tmp_path/'实验参数.md').read_text(encoding='utf-8')


def test_configuration_enters_context_identity(tmp_path):
    _, _, e = setup(tmp_path)
    ob = e.observe('A0002', 1)
    legacy = copy.deepcopy(ob)
    legacy.local_physical['memory_retention_policy'] = LEGACY
    legacy.local_physical['memory_window_ticks'] = None
    assert condition_reference(ob) != condition_reference(legacy)


@pytest.mark.parametrize('policy,window', [(ROLLING, None), (ROLLING, True), (ROLLING, 0), (ROLLING, 11), (LEGACY, 3), ('other', 3)])
def test_invalid_policy_rejected(tmp_path, policy, window):
    cfg, _, _ = setup(tmp_path)
    cfg.update(memory_retention_policy=policy, memory_window_ticks=window)
    with pytest.raises(ValueError, match='memory'):
        validate_experiment(cfg)


def test_legacy_keeps_five_experiences_including_long_gaps():
    records = [{'tick': t} for t in (1, 3, 4, 7, 8, 9)]
    assert retained_memory(records, 20, {}) == records[-5:]


def test_resume_replay_matches_three_tick_window(tmp_path):
    _, b, _ = setup(tmp_path)
    _, eb, pb, sc = b; sc.n_steps = 5
    one = build_simulator(env_bundle=eb, pop_bundle=pb, sim_config=sc, store_path=tmp_path/'one.duckdb')
    one.run()
    sc.warm_start = WarmStartSpec(source_version='memory3-test', source_trajectory=str(tmp_path/'one.duckdb'), resume_from=3)
    two = build_simulator(env_bundle=eb, pop_bundle=pb, sim_config=sc, store_path=tmp_path/'two.duckdb')
    two.run()
    assert digest(one.env.snapshot()) == digest(two.env.snapshot())
