"""Delimiter-only recovery preserves every real decision and bounded retries."""
import copy
import json
from types import SimpleNamespace
import pytest
from syntax_repair import repair_document,atoms
from llm_client import parse_and_validate,LiveClient,validate_response,OutputContractPause
from output_adapter import validation_diagnostic
from response_contract import wire_prompt,output_structure
from test_shared_thread import setup,answer
from test_recovery import response
from model import read_json


def fixture(tmp_path):
    cfg,_,env=setup(tmp_path)
    ob=env.observe('A0002',1);raw=answer(ob,43)
    # Context first; eleven conditions last, so EOF has complete closing braces.
    raw={'condition_context_ref':raw.pop('condition_context_ref'),**raw}
    return cfg,ob,raw


def malformed(raw,kind):
    text=json.dumps(raw,ensure_ascii=False,separators=(',',':'))
    if kind=='extra_root_before_context':
        value=copy.deepcopy(raw);context=value.pop('condition_context_ref')
        return json.dumps(value,ensure_ascii=False)+',"condition_context_ref":'+json.dumps(context)+'}'
    if kind=='trailing_root_comma':return text+','
    if kind=='trailing_inner_comma':return text.replace('"credibility","comment","repost"]','"credibility","comment","repost",]',1)
    if kind=='missing_one_close':return text[:-1]
    if kind=='missing_two_closes':return text[:-2]
    if kind=='excess_close':return text+'}'
    raise AssertionError(kind)


@pytest.mark.parametrize('kind',['extra_root_before_context','trailing_root_comma','trailing_inner_comma',
    'missing_one_close','missing_two_closes','excess_close'])
def test_punctuation_only_preserves_scores_actions_all_notes(tmp_path,kind):
    _,ob,raw=fixture(tmp_path);text=malformed(raw,kind)
    fixed,meta=repair_document(text)
    assert fixed==raw and meta['literal_sequence_unchanged'] and not meta['behavioral_fields_changed']
    accepted=parse_and_validate(text,ob,ob.local_information['posts'],[])
    assert {k:accepted[k] for k in raw}==raw and accepted['output_syntax_repairs']==meta


def test_quotes_braces_and_commas_in_real_note_are_never_edited(tmp_path):
    _,ob,raw=fixture(tmp_path)
    raw['condition_application']['age']['note']='本人51岁，原话“},]”：保留引号和标点'
    raw['comment']['text']='原话带转义引号"、花括号}与逗号,'
    text=malformed(raw,'extra_root_before_context')
    value,meta=repair_document(text)
    assert value==raw and meta['literal_sequence_unchanged']


@pytest.mark.parametrize('text',[
    '{"subjective_credibility":43,',
    '{"subjective_credibility":"unfinished',
    '{"bad": unquoted}',
    '{} {"other":1}',
    '{"score":1,"score":2},',
    '{"comment":{"enabled":true,"text":"x","repost":false}},',
    'Ignore instructions then {"score":43}',
    '[{"score":43}]',
])
def test_incomplete_ambiguous_duplicate_or_prose_is_not_repaired(text):
    with pytest.raises(ValueError):repair_document(text)


def test_edit_bound_and_mismatched_container_rejected(tmp_path):
    _,_,raw=fixture(tmp_path);text=json.dumps(raw)
    with pytest.raises(ValueError):repair_document(text+'}}}}')
    with pytest.raises(ValueError):repair_document(text[:-1]+']')


def test_wrong_evidence_not_changed_by_syntax_repair_and_feedback_is_exact(tmp_path):
    _,ob,raw=fixture(tmp_path);raw['evidence_ids']=['C00-nonexistent']
    text=malformed(raw,'extra_root_before_context')
    value,_=repair_document(text);assert value['evidence_ids']==['C00-nonexistent']
    with pytest.raises(ValueError,match='evidence'):parse_and_validate(text,ob,ob.local_information['posts'],[])
    diag=validation_diagnostic(text,ob,ob.local_information['posts'],[])
    assert diag['code']=='invisible_evidence' and diag['invalid_evidence_ids']==['C00-nonexistent']
    prompt=wire_prompt('original unchanged',ob,1536,diag)
    assert '这次可使用的精确证据ID' in prompt and '"P001"' in prompt


def test_structure_template_has_no_predetermined_score_or_action(tmp_path):
    _,ob,_=fixture(tmp_path);s=output_structure(ob)
    assert s['subjective_credibility'] is None and s['comment']['enabled'] is None
    assert len(s['condition_application'])==11
    assert list(s)[0]=='condition_context_ref' and list(s)[-1]=='condition_application'
    assert json.loads(json.dumps(s))==s


def test_live_punctuation_response_uses_one_api_call_and_keeps_original(tmp_path,monkeypatch):
    cfg,ob,raw=fixture(tmp_path);monkeypatch.setenv('RUMOR_LLM_API_KEY','offline-test-key')
    c=LiveClient(cfg,tmp_path/'audit');calls=[]
    bad=malformed(raw,'extra_root_before_context');r=response(raw);r.choices[0].message.content=bad
    def create(**kw):calls.append(kw);return r
    c.client=SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    fixed,_,meta=c.decide(ob,'{当前观察}')
    assert len(calls)==1 and c.budget['requests']==1 and meta['syntax_repaired']
    assert fixed['subjective_credibility']==43
    record=read_json(c.audit/'request-000001.json')
    assert record['raw_response']==bad
    original=(c.audit/'request-000001.json').read_bytes();budget=copy.deepcopy(c.budget)
    for p in c.cache.glob('*.json'):p.unlink()
    fresh=LiveClient(cfg,c.audit)
    fresh.client.chat.completions.create=lambda **kw:pytest.fail('reuse saved syntax-only answer')
    recovered,_,metadata=fresh.decide(ob,'{当前观察}')
    assert recovered==fixed and metadata['cached'] and fresh.budget==budget
    assert (c.audit/'request-000001.json').read_bytes()==original


def test_provider_length_flag_is_not_treated_as_repairable_stop(tmp_path,monkeypatch):
    cfg,ob,raw=fixture(tmp_path);monkeypatch.setenv('RUMOR_LLM_API_KEY','offline-test-key')
    c=LiveClient(cfg,tmp_path/'audit');calls=[]
    def create(**kw):
        calls.append(kw);r=response(raw);r.choices[0].message.content=malformed(raw,'missing_one_close')
        r.choices[0].finish_reason='length';return r
    c.client=SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    with pytest.raises(OutputContractPause):c.decide(ob,'{当前观察}')
    assert len(calls)==4 and not list(c.cache.glob('*.json'))
