import copy,json
from types import SimpleNamespace
import pytest
import run
from conftest import answer
from llm_client import LiveClient,prepare_prompt,request_options,parse_and_validate,OutputContractPause,HardBudgetPause,PromptBudgetPause
from decision_conditions import validate_condition_application,condition_inputs,TRUST_DECISION_INSTRUCTIONS,CONDITION_LABELS
from concise_wire import validate_template
from response_contract import wire_prompt
from model import read_json


def observed(env):return next(o for o in env.observe_batch(list(env.by_id),1) if o.local_information['posts'])


def template():return (run.SOURCE/'02_Prompt固定提示词.md').read_text(encoding='utf-8').split('```text',1)[1].split('```',1)[0].strip()


@pytest.mark.parametrize('style',['standard','concise_lossless_v1','concise_shared_prefix_v1'])
def test_every_wire_style_contains_real_trust_and_correct_policy(setup,style):
    cfg,env=setup;ob=observed(env);source=ob.local_physical['source_trust'];government=ob.local_physical['government_trust']
    validate_template(template());base,feed,memory,units=prepare_prompt(template(),ob,2_000_000,memory_policy='preserve',encoding=cfg['prompt_encoding'])
    wire=wire_prompt(base,ob,1536,style=style)
    assert TRUST_DECISION_INSTRUCTIONS in wire and '最新30条评论' in wire and '3' in wire
    assert '最近5次完整经历' not in wire and '277名' not in wire
    inputs=condition_inputs(ob);assert inputs['source_trust']==source and inputs['government_trust']==government
    for k in CONDITION_LABELS:assert k in wire
    assert str(round(source,6)) in wire or str(source) in wire


@pytest.mark.parametrize('missing',list(CONDITION_LABELS))
def test_all_eleven_conditions_required(setup,missing):
    cfg,env=setup;ob=observed(env);value=answer(ob);value['condition_application'].pop(missing)
    with pytest.raises(ValueError):validate_condition_application(value,ob)


def client(tmp_path,monkeypatch,cfg):
    cfg=dict(cfg,api_key_mode='environment',rate_limit_spacing_seconds=0.,max_concurrency=1)
    monkeypatch.setenv('RUMOR_LLM_API_KEY','sk-test-offline-placeholder')
    return LiveClient(cfg,tmp_path/'audit')


def response(value):
    content=value if isinstance(value,str) else json.dumps(value,ensure_ascii=False)
    return SimpleNamespace(model='MiniMax-M3',choices=[SimpleNamespace(message=SimpleNamespace(content=content,refusal=None),finish_reason='stop')],usage=SimpleNamespace(prompt_tokens=100,completion_tokens=100,prompt_tokens_details=None),id='offline-response')


def test_real_gateway_validates_and_cache_prevents_duplicate_cost(setup,tmp_path,monkeypatch):
    cfg,env=setup;ob=observed(env);c=client(tmp_path,monkeypatch,cfg);calls=[]
    c.client.chat.completions.create=lambda **kw:calls.append(kw) or response(answer(ob))
    raw,feed,meta=c.decide(ob,template());assert raw['subjective_credibility']==61 and len(calls)==1 and not meta['cached']
    budget=copy.deepcopy(c.budget);assert c.decide(ob,template())[2]['cached'] and c.budget==budget and len(calls)==1
    assert calls[0]['extra_body']['thinking']['type']=='disabled'
    c.close()


def test_gateway_bounded_invalid_output_no_fabricated_answer(setup,tmp_path,monkeypatch):
    cfg,env=setup;ob=observed(env);c=client(tmp_path,monkeypatch,cfg);calls=[]
    c.client.chat.completions.create=lambda **kw:calls.append(kw) or response('{"subjective_credibility":62}')
    with pytest.raises(OutputContractPause):c.decide(ob,template())
    assert len(calls)==cfg['format_max_attempts']==4 and len(list(c.cache.glob('*.json')))==0
    assert c.budget['requests']==4;c.close()


@pytest.mark.parametrize('kind',['input','budget'])
def test_preflight_stops_before_api_when_limit_exceeded(setup,tmp_path,monkeypatch,kind):
    cfg,env=setup;c=client(tmp_path,monkeypatch,cfg)
    c.cfg['prompt_input_token_limit']=512 if kind=='input' else cfg['prompt_input_token_limit']
    if kind=='budget':c.cfg['max_requests']=1
    c.client.chat.completions.create=lambda **kw:pytest.fail('no API before whole tick fits')
    with pytest.raises(PromptBudgetPause if kind=='input' else HardBudgetPause):c.preflight_batch(env.observe_batch(list(env.by_id),1),template())
    assert c.budget['requests']==0;c.close()


@pytest.mark.parametrize('suffix',[',','}','])'])
def test_syntax_repairs_do_not_change_behavior(setup,suffix):
    cfg,env=setup;ob=observed(env);raw=answer(ob)
    text=json.dumps(raw,ensure_ascii=False)+suffix
    try:accepted=parse_and_validate(text,ob,ob.local_information['posts'],[])
    except ValueError:
        assert suffix=='])';return
    assert {k:accepted[k] for k in raw}==raw
