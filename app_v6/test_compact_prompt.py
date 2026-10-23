"""Lossless packing, time boundaries, live validation and whole-tick guards."""
import copy
import json
from types import SimpleNamespace
import pytest

from compact_prompt import (ENCODING,pack_observations,unpack_observations,
                            render_compact_prompt,table,untabulate)
from model import digest,read_json
from llm_client import LiveClient,prepare_prompt,PromptBudgetPause,HardBudgetPause,estimated_input_tokens
from response_contract import wire_prompt
from test_shared_thread import setup,answer
from test_recovery import response
from run import SOURCE


def template():
    return (SOURCE/'02_Prompt固定提示词.md').read_text(encoding='utf-8').split('```text',1)[1].split('```',1)[0].strip()


def fixture(tmp_path):
    cfg,_,env=setup(tmp_path)
    cfg.update(prompt_encoding=ENCODING,rate_limit_spacing_seconds=0,rate_limit_wait_seconds=0)
    ob=env.observe('A0002',1)
    post=ob.local_information['posts'][0]
    for i in range(80):
        post['comments'].append(dict(comment_id=f'C00-{i}',author_id='A0003',published_tick=0,
            target_content_id='P001',text=f'第{i}条完整评论：居民关心消防与电线改造，原始措辞必须保持。'))
    ob.local_physical['memory']=[dict(tick=0,observed_posts=copy.deepcopy(ob.local_information['posts']),
        belief_before='unjudged',belief_after='reject',comment=dict(enabled=False,target_content_id=None,text=''),
        repost=dict(enabled=False,target_content_id=None,text=''),subjective_credibility_after=40)]
    return cfg,env,ob


def live(tmp_path,monkeypatch):
    cfg,env,ob=fixture(tmp_path);monkeypatch.setenv('RUMOR_LLM_API_KEY','offline-not-real')
    return LiveClient(cfg,tmp_path/'audit'),env,ob


def test_roundtrip_exact_deduplicates_text_comments_and_relays(tmp_path):
    _,_,ob=fixture(tmp_path);feed=ob.local_information['posts'];memory=ob.local_physical['memory']
    before=digest((feed,memory));pack=pack_observations(feed,memory)
    assert unpack_observations(pack)==(feed,memory)
    assert len(pack['texts'])==1 and len(pack['comments']['rows'])==80
    assert pack['current_posts'][0]['__comment_refs']==pack['memory'][0]['observed_posts'][0]['__comment_refs']
    assert digest((feed,memory))==before


@pytest.mark.parametrize('records',[
    [],[{'x':None},{}],[{'x':1},{'x':None,'extra':{'v':['中文',False,0]}}],
    [{'text':'原话 "引号" \n换行 {当前观察}','author':'A0002'},{'author':'A0003','text':'原话'}]])
def test_columnar_tables_preserve_absent_null_extra_fields_and_unicode(records):
    assert untabulate(table(records))==records


def test_same_id_different_historical_versions_preserved(tmp_path):
    _,_,ob=fixture(tmp_path)
    ob.local_physical['memory'][0]['observed_posts'][0]['comments'][0]['text']='历史版本完整文字'
    pack=pack_observations(ob.local_information['posts'],ob.local_physical['memory'])
    assert len(pack['comments']['rows'])==81
    assert unpack_observations(pack)==(ob.local_information['posts'],ob.local_physical['memory'])


def test_history_does_not_receive_later_comments_or_new_official_post(tmp_path):
    _,_,ob=fixture(tmp_path)
    current=ob.local_information['posts'][0]
    current['comments'].append(dict(comment_id='NEW',author_id='A0004',published_tick=1,
        target_content_id='P001',text='后来才有的评论'))
    current['relay_context'].append(dict(content_id='NEW-RELAY',author_id='A0005',published_tick=1,repost_text='新附言'))
    pack=pack_observations(ob.local_information['posts'],ob.local_physical['memory'])
    feed,memory=unpack_observations(pack)
    assert feed==ob.local_information['posts'] and memory==ob.local_physical['memory']
    assert 'NEW' not in {c['comment_id'] for c in memory[0]['observed_posts'][0]['comments']}
    assert len(pack['current_posts'][0]['__comment_refs'])==81
    assert len(pack['memory'][0]['observed_posts'][0]['__comment_refs'])==80


def test_prompt_contains_each_comment_body_once_and_all_conditions(tmp_path):
    _,_,ob=fixture(tmp_path);feed=ob.local_information['posts'];memory=ob.local_physical['memory']
    prompt=render_compact_prompt(template(),ob,feed,memory)
    for comment in feed[0]['comments']:assert prompt.count(comment['text'])==1
    assert 'allowed_evidence_ids=' not in prompt and '__comment_refs' in prompt
    from decision_conditions import condition_inputs,condition_reference
    for key in condition_inputs(ob):assert key in prompt
    assert condition_reference(ob) in prompt
    assert ob.local_physical['persona']['synthetic_age'] in prompt


def test_quoted_placeholder_is_data_never_substituted_in_library_or_memory(tmp_path):
    _,_,ob=fixture(tmp_path)
    literal='材料原话：{agent_id} {当前观察} {个人记忆} {条件应用输出要求}'
    ob.local_information['posts'][0]['comments'][0]['text']=literal
    ob.local_physical['memory'][0]['comment']['text']=literal
    prompt=render_compact_prompt(template(),ob,ob.local_information['posts'],ob.local_physical['memory'])
    assert prompt.count(literal)==2 and '\x00' not in prompt


def test_compact_size_lower_preserves_full_feed_and_memory(tmp_path):
    _,_,ob=fixture(tmp_path)
    full=prepare_prompt(template(),ob,limit=1000000)
    packed=prepare_prompt(template(),ob,limit=1000000,encoding=ENCODING)
    assert packed[1:3]==full[1:3] and packed[3]<full[3]
    with pytest.raises(PromptBudgetPause):prepare_prompt(template(),ob,limit=packed[3]-1,encoding=ENCODING)


def test_codec_is_deterministic_and_does_not_share_private_memory_between_users(tmp_path):
    _,_,ob=fixture(tmp_path)
    prompt=render_compact_prompt(template(),ob,ob.local_information['posts'],ob.local_physical['memory'])
    assert prompt==render_compact_prompt(template(),ob,ob.local_information['posts'],ob.local_physical['memory'])
    other=copy.deepcopy(ob);other.local_physical['memory'][0]['comment']['text']='只属于另一个角色的私下记忆'
    changed=render_compact_prompt(template(),other,other.local_information['posts'],other.local_physical['memory'])
    assert '只属于另一个角色的私下记忆' not in prompt and '只属于另一个角色的私下记忆' in changed


def test_reserved_source_fields_are_rejected_instead_of_dropped(tmp_path):
    _,_,ob=fixture(tmp_path);ob.local_information['posts'][0]['__text_ref']='conflict'
    with pytest.raises(ValueError,match='collision'):pack_observations(ob.local_information['posts'],[])


def test_full_json_default_stays_identical(tmp_path):
    _,_,ob=fixture(tmp_path)
    assert prepare_prompt(template(),ob,limit=1000000)==prepare_prompt(template(),ob,limit=1000000,encoding='full_json_v1')


def test_real_gateway_contract_uses_full_original_validation_inputs(tmp_path,monkeypatch):
    c,_,ob=live(tmp_path,monkeypatch);calls=[]
    def create(**kwargs):calls.append(kwargs);return response(answer(ob,68))
    c.client=SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    result,feed,meta=c.decide(ob,template())
    assert feed==ob.local_information['posts'] and len(result['condition_application'])==11
    assert result['subjective_credibility']==68 and meta['prompt_encoding']==ENCODING
    assert len(calls)==1 and c.budget['input_reserved_units']==estimated_input_tokens(calls[0]['messages'][0]['content'])


def test_whole_tick_budget_failure_sends_zero_requests_and_preserves_ledger(tmp_path,monkeypatch):
    c,_,ob=live(tmp_path,monkeypatch);c.cfg['max_input_reserved_units']=512
    before=copy.deepcopy(c.budget)
    with pytest.raises(HardBudgetPause,match='no new request'):c.preflight_batch([ob],template())
    assert c.budget==before and not list(c.audit.glob('request-*.json'))
    report=read_json(c.audit/'preflight-tick-001.json')
    assert report['minimum_new_requests']==1 and report['minimum_new_input_reservation']>512


def test_whole_tick_input_failure_checks_before_any_dispatch(tmp_path,monkeypatch):
    c,_,ob=live(tmp_path,monkeypatch);c.cfg['prompt_input_token_limit']=512
    with pytest.raises(PromptBudgetPause,match='no API dispatched'):c.preflight_batch([ob],template())
    assert c.budget['requests']==0


def test_preflight_counts_full_wire_prompt_and_skips_existing_success(tmp_path,monkeypatch):
    c,_,ob=live(tmp_path,monkeypatch)
    c.preflight_batch([ob],template())
    report=read_json(c.audit/'preflight-tick-001.json')
    base,*_=prepare_prompt(template(),ob,limit=1000000,encoding=ENCODING)
    assert report['minimum_new_input_reservation']==estimated_input_tokens(wire_prompt(base,ob,1536))
    assert c.budget['requests']==0
    c.client.chat.completions.create=lambda **kwargs:response(answer(ob))
    c.decide(ob,template());before=copy.deepcopy(c.budget)
    c.preflight_batch([ob],template());report=read_json(c.audit/'preflight-tick-001.json')
    assert report['cached_or_recoverable']==1 and report['minimum_new_requests']==0 and c.budget==before


def test_legacy_clients_do_not_activate_preflight(tmp_path,monkeypatch):
    c,_,ob=live(tmp_path,monkeypatch);c.cfg['prompt_encoding']='full_json_v1'
    c.preflight_batch([ob],template())
    assert not list(c.audit.glob('preflight-*.json'))


@pytest.mark.parametrize('encoding,limit,valid',[
    (ENCODING,524288,True),(ENCODING,524289,False),('full_json_v1',131072,True),('full_json_v1',131073,False)])
def test_larger_opt_in_ceiling_never_changes_legacy_limits(tmp_path,encoding,limit,valid):
    from experiment import validate_experiment
    cfg,_,_=fixture(tmp_path);cfg.update(prompt_encoding=encoding,prompt_input_token_limit=limit)
    if valid:validate_experiment(cfg)
    else:
        with pytest.raises(ValueError,match='prompt_input_token_limit'):validate_experiment(cfg)
