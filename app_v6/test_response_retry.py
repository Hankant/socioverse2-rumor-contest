"""Failure recovery for the live all-conditions output contract; no network."""
import copy
import hashlib
import json
from types import SimpleNamespace

import pytest
from model import dump, read_json
from llm_client import (LiveClient, OutputContractPause, HardBudgetPause,
                        PromptBudgetPause, UncertainRequest, estimated_input_tokens)
from response_contract import RETRY_POLICY, response_envelope_diagnostic, wire_prompt
from test_shared_thread import setup, answer
from test_recovery import response


def gateway(tmp_path, monkeypatch):
    cfg, _, env = setup(tmp_path)
    cfg.update(rate_limit_spacing_seconds=0, rate_limit_wait_seconds=0)
    monkeypatch.setenv('RUMOR_LLM_API_KEY', 'test-not-real')
    return LiveClient(cfg, tmp_path/'live'), env.observe('A0002', 1)


def install(client, results):
    calls=[]
    iterator=iter(results)
    def create(**kwargs):
        calls.append(kwargs)
        result=next(iterator)
        if isinstance(result, BaseException):raise result
        return result
    client.client=SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    return calls


def malformed(ob, case):
    raw=answer(ob)
    r=response(raw)
    if case=='length':r.choices[0].finish_reason='length';r.choices[0].message.content='{"evidence_ids":['
    elif case=='empty':r.choices[0].message.content=''
    elif case=='none':r.choices[0].message.content=None
    elif case=='no_choices':r.choices=[]
    elif case=='no_message':r.choices[0].message=None
    elif case=='invalid_json':r.choices[0].message.content='{"subjective_credibility": 60,'
    elif case=='root_list':r.choices[0].message.content='[]'
    elif case=='missing':del raw['condition_application']['age']
    elif case=='generic_note':raw['condition_application']['age']['note']='已考虑该条件'
    elif case=='invalid_affects':raw['condition_application']['age']['affects']=[{}]
    elif case=='evidence':raw['evidence_ids']=['not-visible']
    elif case=='comment':raw['comment']={'enabled':True,'target_content_id':'not-visible','text':'这条内容不在视野内'}
    elif case=='repost':raw['repost']={'enabled':True,'target_content_id':'not-visible','text':'不在视野内'}
    elif case=='score':raw['subjective_credibility']=101
    elif case=='action':raw['repost']={'enabled':'yes','target_content_id':None,'text':''}
    elif case=='empty_comment':raw['comment']={'enabled':True,'target_content_id':'P001','text':''}
    elif case=='alias_conflict':raw['condition_application']['source_prior']={'affects':['comment'],'note':'与规范字段不相同'}
    elif case=='unexpected_finish':r.choices[0].finish_reason='tool_calls'
    else:raise AssertionError(case)
    if case in ('missing','generic_note','invalid_affects','evidence','comment','repost','score','action','empty_comment','alias_conflict'):
        r.choices[0].message.content=json.dumps(raw)
    return r


@pytest.mark.parametrize('case,code',[
    ('length','truncated_output'),('empty','empty_response'),('none','empty_response'),
    ('no_choices','empty_response'),('no_message','empty_response'),('invalid_json','invalid_json'),
    ('root_list','json_root_not_object'),('missing','condition_coverage_or_note_invalid'),
    ('generic_note','condition_coverage_or_note_invalid'),('invalid_affects','condition_coverage_or_note_invalid'),
    ('evidence','invisible_evidence'),('comment','invisible_comment_target'),('repost','invisible_repost_target'),
    ('score','invalid_score'),('action','invalid_action_schema'),('empty_comment','empty_comment'),
    ('alias_conflict','conflicting_condition_aliases'),('unexpected_finish','unexpected_finish_reason')])
def test_bad_output_gets_targeted_retry_without_changing_decision(tmp_path,monkeypatch,case,code):
    c,ob=gateway(tmp_path,monkeypatch)
    expected=answer(ob,score=38)
    bad=malformed(ob,case)
    calls=install(c,[bad,response(expected)])
    result,feed,meta=c.decide(ob,'{当前观察}')
    assert result==expected and result['subjective_credibility']==38
    assert len(calls)==2 and meta['attempt']==2
    assert code in calls[1]['messages'][0]['content']
    first=read_json(c.audit/'request-000001.json')
    second=read_json(c.audit/'request-000002.json')
    assert first['base_prompt']==second['base_prompt']
    assert second['prompt'].startswith(first['base_prompt'])
    assert second['actual_prompt_sha256']==hashlib.sha256(second['prompt'].encode()).hexdigest()
    assert c.budget['requests']==2 and c.budget['output_reserved_tokens']==3072
    assert c.budget['input_reserved_units']==sum(estimated_input_tokens(x['messages'][0]['content']) for x in calls)
    validation=read_json(c.audit/'validation/request-000001.json')
    assert validation['diagnostic']['code']==code
    assert validation['retry_policy']==RETRY_POLICY
    saved=next(c.cache.glob('*.json'))
    assert read_json(saved)['answer']==expected
    assert 'base_prompt' not in read_json(saved)['metadata']
    assert len(result['condition_application'])==11


def test_length_is_bounded_and_restart_does_not_reset_attempts(tmp_path,monkeypatch):
    c,ob=gateway(tmp_path,monkeypatch)
    calls=install(c,[malformed(ob,'length') for _ in range(4)])
    with pytest.raises(OutputContractPause,match='被截断') as ex:c.decide(ob,'{当前观察}')
    assert ex.value.safe_details==dict(agent_id=ob.agent_id,tick=1,generation_attempts=4,
        code='truncated_output',finish_reason='length',retryable=True)
    assert len(calls)==4 and not list(c.cache.glob('*.json'))
    before={p.name:p.read_bytes() for p in c.audit.glob('request-*.json')}
    resumed=LiveClient(c.cfg,c.audit)
    more=install(resumed,[response(answer(ob))])
    with pytest.raises(OutputContractPause):resumed.decide(ob,'{当前观察}')
    assert not more and resumed.budget['requests']==4
    assert before=={p.name:p.read_bytes() for p in c.audit.glob('request-*.json')}


def test_saved_length_retries_after_process_restart_preserving_original(tmp_path,monkeypatch):
    c,ob=gateway(tmp_path,monkeypatch)
    c.cfg['format_max_attempts']=1
    install(c,[malformed(ob,'length')])
    with pytest.raises(OutputContractPause):c.decide(ob,'{当前观察}')
    old=(c.audit/'request-000001.json').read_bytes()
    # Test a process that previously stopped on its FIRST truncated response.
    # The production migration retains the existing max_attempts=4 unchanged.
    cfg={**c.cfg,'format_max_attempts':4}
    resumed=LiveClient(cfg,c.audit)
    calls=install(resumed,[response(answer(ob))])
    _,_,meta=resumed.decide(ob,'{当前观察}')
    assert len(calls)==1 and meta['attempt']==2 and resumed.budget['requests']==2
    assert 'truncated_output' in calls[0]['messages'][0]['content']
    assert old==(c.audit/'request-000001.json').read_bytes()


@pytest.mark.parametrize('refusal', ['content_filter','explicit'])
def test_provider_refusal_pauses_without_blind_bypass(tmp_path,monkeypatch,refusal):
    c,ob=gateway(tmp_path,monkeypatch)
    r=response(answer(ob))
    if refusal=='content_filter':r.choices[0].finish_reason='content_filter'
    else:r.choices[0].message.refusal='provider refusal'
    calls=install(c,[r,response(answer(ob))])
    with pytest.raises(OutputContractPause) as ex:c.decide(ob,'{当前观察}')
    assert len(calls)==1 and ex.value.safe_details['code']=='provider_refusal'
    assert not list(c.cache.glob('*.json'))


def test_unknown_outcome_still_requires_explicit_authorization(tmp_path,monkeypatch):
    c,ob=gateway(tmp_path,monkeypatch)
    install(c,[KeyboardInterrupt()])
    with pytest.raises(KeyboardInterrupt):c.decide(ob,'{当前观察}')
    resumed=LiveClient(c.cfg,c.audit)
    calls=install(resumed,[response(answer(ob))])
    with pytest.raises(UncertainRequest):resumed.decide(ob,'{当前观察}')
    assert not calls and resumed.budget['requests']==1


@pytest.mark.parametrize('limit', ['max_requests','max_output_reserved_tokens','max_input_reserved_units'])
def test_retry_cannot_exceed_existing_spending_ceiling(tmp_path,monkeypatch,limit):
    c,ob=gateway(tmp_path,monkeypatch)
    c.cfg[limit]={'max_requests':1,'max_output_reserved_tokens':1536,'max_input_reserved_units':1500}[limit]
    # For the input case, allow exactly one full request, not a partial prompt.
    if limit=='max_input_reserved_units':
        from llm_client import prepare_prompt
        base,*_=prepare_prompt('{当前观察}',ob,limit=c.cfg['prompt_input_token_limit'],memory_policy=c.cfg['prompt_memory_policy'])
        c.cfg[limit]=estimated_input_tokens(wire_prompt(base,ob,1536))
    calls=install(c,[malformed(ob,'length'),response(answer(ob))])
    with pytest.raises(HardBudgetPause):c.decide(ob,'{当前观察}')
    assert len(calls)==1 and c.budget['requests']==1 and not list(c.cache.glob('*.json'))


def test_complete_input_and_all_comments_are_preserved_with_feedback(tmp_path,monkeypatch):
    c,ob=gateway(tmp_path,monkeypatch)
    comments=[dict(comment_id=f'C-test-{i}',text=f'需要完整保留的评论{i}',author_id='A0003',published_tick=0) for i in range(131)]
    ob.local_information['posts'][0]['comments']=comments
    calls=install(c,[malformed(ob,'length'),response(answer(ob))])
    c.decide(ob,'{当前观察}')
    for call in calls:
        prompt=call['messages'][0]['content']
        for comment in comments:assert comment['text'] in prompt and comment['comment_id'] in prompt
    first=read_json(c.audit/'request-000001.json');second=read_json(c.audit/'request-000002.json')
    assert first['base_prompt']==second['base_prompt']
    assert first['trimmed_comment_count']==second['trimmed_comment_count']==0


def test_output_protocol_itself_is_counted_in_input_guard(tmp_path,monkeypatch):
    c,ob=gateway(tmp_path,monkeypatch)
    from llm_client import prepare_prompt
    base,*_=prepare_prompt('{当前观察}',ob,limit=65536,memory_policy=c.cfg['prompt_memory_policy'])
    c.cfg['prompt_input_token_limit']=estimated_input_tokens(base)
    calls=install(c,[response(answer(ob))])
    with pytest.raises(PromptBudgetPause):c.decide(ob,'{当前观察}')
    assert not calls and c.budget['requests']==0


def test_valid_cached_answer_is_reused_with_no_new_request(tmp_path,monkeypatch):
    c,ob=gateway(tmp_path,monkeypatch)
    install(c,[response(answer(ob,91))]);c.decide(ob,'{当前观察}')
    before={p.name:p.read_bytes() for p in c.cache.glob('*.json')}
    resumed=LiveClient(c.cfg,c.audit);calls=install(resumed,[response(answer(ob,10))])
    result,_,meta=resumed.decide(ob,'{当前观察}')
    assert result['subjective_credibility']==91 and meta['cached'] and not calls
    assert before=={p.name:p.read_bytes() for p in c.cache.glob('*.json')}


def test_pause_menu_explains_precise_failure():
    from recovery import print_pause
    # The persisted state carries this string, rather than generic ValueError.
    ex=OutputContractPause('A0326',3,4,dict(code='truncated_output',retryable=True))
    assert 'A0326' in str(ex) and '被截断' in str(ex)
    lines=[]
    print_pause(dict(status=dict(status='paused_output_contract',error_type='OutputContractPause',
        error_details=str(ex),last_completed_tick=2),provenance=dict(total_steps=10,
        config=dict(max_requests=100,max_input_reserved_units=10000,max_output_reserved_tokens=10000)),
        budget={},cached_decisions=5,run_dir='test',audit='test',unknown=[]),output=lines.append)
    assert any('A0326' in line and '被截断' in line for line in lines)
