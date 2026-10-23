"""Fifty-comment windows, explicit prompts, archives and legacy compatibility."""
import json
import pytest
from model import V4Environment, digest
from run import make_bundles, SOURCE, ROOT
from experiment import validate_experiment
from test_latest_comments import setup as old_setup, comment, template
from test_network_thread import act
from llm_client import prepare_prompt
from response_contract import wire_prompt
from memory_policy import ROLLING
from concise_wire import extract_data


def setup(tmp_path):
    cfg,_,_=old_setup(tmp_path)
    cfg.update(comment_window_limit=50,memory_retention_policy=ROLLING,memory_window_ticks=3,
               wire_prompt_style='concise_shared_prefix_v1')
    b=make_bundles(SOURCE/'01_Agent基础信息表.csv',SOURCE/'02_Prompt固定提示词.md',cfg,tmp_path/'audit')
    e=V4Environment(b[1]);e.reset(cfg['behavior_seed']);e.advance_to(2)
    aid=next(a for a in e.direct_targets if e.by_id[a]['decision_mode']=='llm' and e.by_id[a]['group']=='inside')
    e.apply([act(e,aid)])
    return cfg,e,aid


def test_fifty_per_root_only_previous_ticks_and_full_local_archive(tmp_path):
    cfg,e,aid=setup(tmp_path)
    for root in ('P001','G001'):
        for i in range(120):
            c=comment(i,2,root);e.comments[c['comment_id']]=c
        for i in range(20):
            c=comment(i,3,root);e.comments[c['comment_id']]=c
    e.advance_to(3);before=digest(e.snapshot());ob=e.observe(aid,3)
    assert {p['content_id'] for p in ob.local_information['posts']}=={'P001','G001'}
    for p in ob.local_information['posts']:
        assert len(p['comments'])==50
        assert all(c['published_tick']==2 for c in p['comments'])
        assert p['comment_scope']=='latest_50_earlier_comments_per_root'
        assert p['comment_window_limit']==50
    assert len(e.comments)==280 and digest(e.snapshot())==before


def test_short_window_keeps_every_comment(tmp_path):
    _,e,aid=setup(tmp_path)
    for i in range(17):
        c=comment(i,2);e.comments[c['comment_id']]=c
    e.advance_to(3)
    p=next(p for p in e.observe(aid,3).local_information['posts'] if p['content_id']=='P001')
    assert len(p['comments'])==17


@pytest.mark.parametrize('style',['standard','concise_lossless_v1','concise_shared_prefix_v1'])
def test_prompts_and_libraries_consistent_with_fifty(tmp_path,style):
    _,e,aid=setup(tmp_path)
    for root in ('P001','G001'):
        for i in range(120):
            c=comment(i,2,root);e.comments[c['comment_id']]=c
    e.advance_to(3);ob=e.observe(aid,3)
    base,feed,memory,_=prepare_prompt(template(),ob,limit=2_000_000,encoding='lossless_thread_refs_v1')
    sent=wire_prompt(base,ob,1536,style=style)
    assert '最新50条' in base and '最新50条' in sent
    assert '最新100条' not in sent
    assert len(extract_data(base)['libraries']['comments']['rows'])==100  # two independent roots
    assert len(memory)<=3


def test_active_configuration_defaults_and_single_condition_are_fifty():
    paths=[ROOT/'configs/local_defaults.json',ROOT/'configs/one_latest50_mbti_test.json',
           ROOT/'configs/one_latest100_mbti_test.json',*sorted((ROOT/'configs/research54').glob('D*_T*_C*_G*.json'))]
    assert len(paths)==57
    for path in paths:
        cfg=json.loads(path.read_text(encoding='utf-8'))
        validate_experiment(cfg)
        assert cfg['comment_window_limit']==50 and cfg['memory_window_ticks']==3
        assert cfg['wire_prompt_style']=='concise_shared_prefix_v1'


def test_old_hundred_configuration_still_has_accurate_prompts(tmp_path):
    cfg,_,e=old_setup(tmp_path)
    validate_experiment(cfg)
    ob=e.observe('A0002',1)
    base,*_=prepare_prompt(template(),ob,limit=2_000_000,encoding='lossless_thread_refs_v1')
    assert '最新100条' in base and '最新50条' not in base
