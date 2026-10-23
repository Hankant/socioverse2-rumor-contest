"""Common-prefix ordering preserves all input data and cache accounting."""
import copy
import os
from types import SimpleNamespace
from concise_wire import (SHARED_PREFIX_STYLE, extract_data, json_after, transform_pack)
from compact_prompt import unpack_observations
from response_contract import wire_prompt
from llm_client import prepare_prompt, estimated_input_tokens
from model import read_json
from test_latest_comments import setup, comment, template
from test_concise_wire import client


def base(ob):
    return prepare_prompt(template(), ob, limit=2_000_000, encoding='lossless_thread_refs_v1')[0]


def test_every_data_field_roundtrips_and_no_comments_from_other_users(tmp_path):
    cfg, _, e = setup(tmp_path)
    for i in range(150):
        c=comment(i); e.comments[c['comment_id']]=c
    e.advance_to(2); ob=e.observe('A0002', 2); logical=base(ob)
    d=extract_data(logical); sent=wire_prompt(logical, ob, 1536, style=SHARED_PREFIX_STYLE)
    libraries,end=json_after(sent, '【完整可见材料库】')
    profile,end=json_after(sent, '【稳定个人资料】', end)
    score,end=json_after(sent, '【当前信念及评分】', end)
    observed,end=json_after(sent, '【完整观察与个人记忆】', end)
    conditions,end=json_after(sent, '【必须逐项采用的11项条件】', end)
    exposure,end=json_after(sent, '【累计实际接触】', end)
    repetition,end=json_after(sent, '【本轮合成重复接触倾向】', end)
    libs,current,memory=transform_pack(libraries,observed['current'],observed['memory'],decode=True)
    assert (libs,current,memory)==(d['libraries'],d['current'],d['memory'])
    assert (profile,conditions,exposure,repetition)==(d['profile'],d['conditions'],d['exposure'],d['repetition'])
    assert score=={'belief':d['belief'],**d['score']}
    assert d['prefix'] in sent and d['condition_context_ref'] in sent
    full={**libs, 'current_posts':current['posts'], 'memory':memory}
    assert unpack_observations(full)==(ob.local_information['posts'],ob.local_physical['memory'])


def test_different_users_share_long_prefix_without_receiving_unseen_material(tmp_path):
    _,_,e=setup(tmp_path)
    e.advance_to(2)
    aids=[a for a,r in e.by_id.items() if r['decision_mode']=='llm' and r['group']=='inside'][:2]
    obs=[e.observe(a,2) for a in aids]
    prompts=[wire_prompt(base(ob),ob,1536,style=SHARED_PREFIX_STYLE) for ob in obs]
    prefix=os.path.commonprefix(prompts)
    assert estimated_input_tokens(prefix)>512
    assert not e.observe('A0084',1).local_information['posts']
    assert prompts[0].index('【完整可见材料库】') < prompts[0].index('【稳定个人资料】')


def test_provider_cache_and_reasoning_usage_are_logged_without_budget_discount(tmp_path, monkeypatch):
    from test_recovery import response
    from test_shared_thread import answer
    c,ob,_,calls=client(tmp_path,monkeypatch,style=SHARED_PREFIX_STYLE)
    obj=response(answer(ob))
    obj.usage.prompt_tokens_details=SimpleNamespace(cached_tokens=80)
    obj.usage.completion_tokens_details=SimpleNamespace(reasoning_tokens=0)
    c.client.chat.completions.create=lambda **kw:obj
    _,_,metadata=c.decide(ob,template())
    record=read_json(c.audit/'request-000001.json')
    assert record['cached_input_tokens']==metadata['cached_input_tokens']==80
    assert record['reasoning_output_tokens']==0
    assert c.budget['actual_input_tokens']==obj.usage.prompt_tokens
    assert c.budget['input_reserved_units']==estimated_input_tokens(record['prompt'])
