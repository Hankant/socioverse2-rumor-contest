"""Scenario and exposure fidelity tests; no real model requests."""
import copy
import json
from types import SimpleNamespace

import pytest
from llm_client import browsing_context, render_prompt
from model import V4Environment
from run import SOURCE, defaults, extract_post_blocks, make_bundles

USER_POST = (
    "最近小区业主群里一直在传一件事：老旧小区改造的预算明明是优先解决电线老化、消防通道堵塞这些安全隐患，但据说有些地方临时调整了项目顺序，先把一部分资金安排给了商业街立面改造和景观提升，真正涉及居民安全的问题反而要往后排。\n\n"
    "现在最让人担心的是，到底哪些项目被调整了、为什么调整，普通居民根本看不到完整的预算和排序依据。之前排查出来的问题还没解决，后续施工时间也不明确。钱是纳税人的钱，安全也是大家每天都要面对的事，总得有个说法吧？\n\n"
    "这件事目前还没有得到独立核实，希望有关部门能公开项目预算、调整记录和施工计划。涉及居民安全的问题，不能只靠一句“正在推进”就过去了。"
)


def bundles(tmp_path):
    cfg={**defaults(),'government_tick':2,'government_reach':100,'targeting_inside_ratio':.8,
         'government_trust_mean':.75,'source_trust_gap':.4,'prompt_memory_policy':'preserve',
         'prompt_input_token_limit':32768}
    return make_bundles(SOURCE/'01_Agent基础信息表.csv',SOURCE/'02_Prompt固定提示词.md',cfg,tmp_path)


def test_multiline_user_post_is_preserved_exactly(tmp_path):
    b=bundles(tmp_path);args=b[1].provider_args
    assert args['rumor_text']==USER_POST
    assert '辽宁' not in args['correction_text'] and '商业街' in args['correction_text']
    assert args['correction_mode']=='scripted_claimed_review_no_documents'
    assert b[1].information_program.broadcasts[0].note.startswith(args['correction_mode'])
    assert args['scenario_id']=='budget_priority_20261022_v1'
    assert args['belief_target'] and '后排' in args['belief_target']


def test_legacy_two_single_line_quotes_remain_supported():
    assert extract_post_blocks('标题\n> 第一条\n\n正文\n> 第二条\n')==['第一条','第二条']
    with pytest.raises(ValueError):extract_post_blocks('> 只有一条')


def test_first_inside_prompt_is_casual_and_blind_to_future_correction(tmp_path):
    b=bundles(tmp_path);env=V4Environment(b[1]);env.reset(1);env.advance_to(1)
    ob=env.observe('A0002',1);feed=ob.local_information['posts']
    template=(SOURCE/'02_Prompt固定提示词.md').read_text(encoding='utf-8').split('```text',1)[1].split('```',1)[0].strip()
    prompt=render_prompt(template,ob,feed,[])
    assert '无意间刷到自己平时喜欢阅读、已经关注的博主SOURCE' in prompt
    assert USER_POST in json.loads(prompt.split('【当前观察】',1)[1].split('【任务】',1)[0])['posts'][0]['text']
    assert '谣言' not in prompt and 'G001' not in prompt and '未发现将安全隐患整改资金' not in prompt
    assert '{浏览情境}' not in prompt and '{判断对象}' not in prompt
    assert '不因重复而自动推翻已经接受的纠正' not in prompt
    assert '熟悉不是真实性的证据' not in prompt
    assert '请主动考虑转发' not in prompt
    assert ob.local_physical['current_belief']=='unjudged'


def test_outside_context_does_not_invent_a_source_follow():
    ob=SimpleNamespace(step=2,local_physical={'persona':{'group':'outside'},'exposure_history':{}})
    feed=[{'content_id':'RP01-A0002','root_content_id':'P001'}]
    context=browsing_context(ob,feed)
    assert '关注的账号转发' in context and '没有关注SOURCE' in context
    assert '喜欢阅读、已经关注的博主SOURCE' not in context


def test_reread_is_not_described_as_first_exposure(tmp_path):
    b=bundles(tmp_path);env=V4Environment(b[1]);env.reset(1);env.advance_to(1)
    ob=env.observe('A0002',1);feed=ob.local_information['posts']
    ob=copy.deepcopy(ob)
    ob.local_physical['exposure_history']={'P001':{'root_content_id':'P001','author_id':'SOURCE','tick':1,'ticks':[1]}}
    context=browsing_context(ob,feed)
    assert '再次看到' in context and '第一次' not in context


def test_only_followup_posts_do_not_invent_a_visible_source_post():
    ob=SimpleNamespace(step=3,local_physical={'persona':{'group':'inside'},'exposure_history':{}})
    context=browsing_context(ob,[{'content_id':'G001','root_content_id':'G001'}])
    assert '后续帖子' in context and '第一次' not in context and '喜欢' not in context
