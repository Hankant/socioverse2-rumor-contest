"""Schema repairs keep all substantive decisions and all eleven real notes."""
import copy
import json
from pathlib import Path

import pytest
from model import dump,read_json,digest
from output_adapter import adapt_condition_output,validation_diagnostic
from llm_client import parse_and_validate,parse_json_object,LiveClient,DecisionConditionsPause
from decision_conditions import CONDITION_LABELS,condition_reference
from format_migration import validate_format_migration,function_hashes,file_sha
from test_shared_thread import setup,answer
from test_recovery import response


def test_context_reference_is_program_metadata_not_an_llm_copying_exam(tmp_path):
    _,_,e=setup(tmp_path);ob=e.observe('A0002',1)
    raw=answer(ob,22);raw['condition_context_ref']='wrong-but-no-decision-changed'
    original=copy.deepcopy(raw)
    fixed=parse_and_validate(json.dumps(raw),ob,ob.local_information['posts'],[])
    assert fixed['condition_context_ref']==condition_reference(ob)
    assert fixed['model_returned_condition_context_ref']==raw['condition_context_ref']
    assert fixed['subjective_credibility']==22 and fixed['component_credibility']==raw['component_credibility']
    assert fixed['comment']==raw['comment'] and fixed['repost']==raw['repost']
    assert fixed['condition_application']==raw['condition_application'] and raw==original
    assert fixed['output_format_repairs']['behavioral_fields_changed'] is False


@pytest.mark.parametrize('alias,canonical',[('source_prior','source_trust'),('government_prior','government_trust'),('mbti','mbti_preferences')])
def test_only_explicit_unambiguous_aliases_are_accepted(tmp_path,alias,canonical):
    _,_,e=setup(tmp_path);ob=e.observe('A0002',1);raw=answer(ob)
    expected=raw['condition_application'].pop(canonical);raw['condition_application'][alias]=expected
    fixed=parse_and_validate(json.dumps(raw),ob,ob.local_information['posts'],[])
    assert set(fixed['condition_application'])==set(CONDITION_LABELS)
    assert fixed['condition_application'][canonical]==expected and alias not in fixed['condition_application']
    assert alias in raw['condition_application']


def test_conflicting_aliases_cannot_choose_a_convenient_note(tmp_path):
    _,_,e=setup(tmp_path);ob=e.observe('A0002',1);raw=answer(ob)
    raw['condition_application']['source_prior']={'affects':['repost'],'note':'和原说明不同，不应自动择一'}
    with pytest.raises(ValueError,match='ambiguous'):parse_and_validate(json.dumps(raw),ob,ob.local_information['posts'],[])


def test_supplementary_fields_preserved_without_removing_required_conditions(tmp_path):
    _,_,e=setup(tmp_path);ob=e.observe('A0002',1);raw=answer(ob)
    extra={'affects':['comment'],'note':'补充说明仍在审计记录中保留'}
    raw['condition_application']['mbti_before']=extra
    fixed=parse_and_validate(json.dumps(raw),ob,ob.local_information['posts'],[])
    assert fixed['supplementary_condition_application']=={'mbti_before':extra}
    assert set(fixed['condition_application'])==set(CONDITION_LABELS)


@pytest.mark.parametrize('key',list(CONDITION_LABELS))
def test_missing_real_condition_is_never_fabricated(tmp_path,key):
    _,_,e=setup(tmp_path);ob=e.observe('A0002',1);raw=answer(ob)
    del raw['condition_application'][key]
    with pytest.raises(ValueError,match='condition coverage'):parse_and_validate(json.dumps(raw),ob,ob.local_information['posts'],[])


@pytest.mark.parametrize('note',['', '已考虑该条件', 'a'*61])
def test_empty_generic_or_overlong_real_notes_still_rejected(tmp_path,note):
    _,_,e=setup(tmp_path);ob=e.observe('A0002',1);raw=answer(ob)
    raw['condition_application']['age']['note']=note
    with pytest.raises(ValueError,match='condition coverage'):parse_and_validate(json.dumps(raw),ob,ob.local_information['posts'],[])


def test_valid_answers_idempotent_and_bad_json_not_repaired(tmp_path):
    _,_,e=setup(tmp_path);ob=e.observe('A0002',1);raw=answer(ob)
    assert adapt_condition_output(raw,ob)==raw
    with pytest.raises(json.JSONDecodeError):parse_and_validate('{"bad": unquoted}',ob,ob.local_information['posts'],[])
    diag=validation_diagnostic('{"bad": unquoted}',ob,ob.local_information['posts'],[])
    assert diag['code']=='invalid_json' and diag['line']==1


def test_stored_bad_reference_recovered_without_api_or_spending(tmp_path,monkeypatch):
    cfg,_,e=setup(tmp_path);ob=e.observe('A0002',1)
    monkeypatch.setenv('RUMOR_LLM_API_KEY','test-not-real')
    c=LiveClient(cfg,tmp_path/'audit')
    bad=answer(ob);bad['condition_context_ref']='missing-character'
    def reply(**kw):return response(bad)
    c.client.chat.completions.create=reply
    c.decide(ob,'{当前观察}')
    record=read_json(c.audit/'request-000001.json')
    assert parse_json_object(record['raw_response'])['condition_context_ref']=='missing-character'
    budget=dict(c.budget)
    for p in c.cache.glob('*.json'):p.unlink()  # Emulate a crash before cache publication.
    fresh=LiveClient(cfg,c.audit)
    fresh.client.chat.completions.create=lambda **kw:pytest.fail('must reuse the durable answer')
    fixed,_,meta=fresh.decide(ob,'{当前观察}')
    assert meta['cached'] and fresh.budget==budget
    assert fixed['condition_context_ref']==condition_reference(ob)
    assert read_json(c.audit/'request-000001.json')==record


def migration_fixture(tmp_path):
    import run
    code=run.CODE
    hashes={p.name:file_sha(p) for p in code.glob('*.py')}
    parent=tmp_path/'parent';audit=tmp_path/'audit'
    current=dict(code_sha256=hashes,input_sha256={'case':'same'},config=run.defaults(),mode='openai',
                 upstream_commit='same',numpy_version='same',total_steps=10)
    previous=copy.deepcopy(current);previous['code_sha256']['llm_client.py']='old'
    previous['audit_dir']=str(audit)
    dump(parent/'provenance.json',previous);dump(audit/'budget.json',{'requests':259})
    dump(audit/'request-000001.json',{'raw_response':'preserve original'})
    dump(audit/'response_cache/success.json',{'answer':'previously valid'})
    dump(parent/'checkpoints/tick-001.json',{'sha256':'test-original'})
    manifest=dict(parent_run=str(parent.resolve()),parent_provenance_sha256=file_sha(parent/'provenance.json'),
        old_code_sha256=previous['code_sha256'],new_code_sha256=current['code_sha256'],budget_sha256=file_sha(audit/'budget.json'),
        unchanged_prompt_function_sha256=function_hashes((code/'llm_client.py').read_text(encoding='utf-8')),
        audit_request_sha256={'request-000001.json':file_sha(audit/'request-000001.json')},
        valid_cache_sha256={'success.json':file_sha(audit/'response_cache/success.json')},
        completed_checkpoint_sha256={'tick-001.json':file_sha(parent/'checkpoints/tick-001.json')})
    return previous,current,parent,manifest


def test_exact_format_migration_accepts_only_reviewed_unchanged_inputs(tmp_path):
    old,new,parent,manifest=migration_fixture(tmp_path)
    validate_format_migration(old,new,parent,manifest)


def test_protected_function_hashes_compare_windows_and_universal_newlines():
    import run
    source=(run.CODE/'llm_client.py').read_text(encoding='utf-8')
    assert function_hashes(source)==function_hashes(source.replace('\n','\r\n'))


def test_reviewed_format_fix_resumes_once_without_requiring_another_r(tmp_path):
    from types import SimpleNamespace
    from recovery import supervise
    parent=tmp_path/'parent'
    dump(parent/'status.json',{'status':'paused_decision_contract'})
    calls=[]
    assert supervise(SimpleNamespace(resume=str(parent),format_migration_manifest='reviewed-exact-parent'),
                     lambda a:calls.append(a.resume),lambda a:None,interactive=True,
                     reader=lambda p:pytest.fail('reviewed repair resumes without another blind retry'))==0
    assert calls==[str(parent)]


@pytest.mark.parametrize('kind',['config','input','rules','prompt','budget','cache','checkpoint'])
def test_format_migration_rejects_behavior_prompt_or_ledger_changes(tmp_path,kind):
    old,new,parent,manifest=migration_fixture(tmp_path)
    if kind=='config':new['config']['government_tick']=7
    elif kind=='input':new['input_sha256']['case']='different'
    elif kind=='rules':
        new['code_sha256']['model.py']='different';manifest['new_code_sha256']=new['code_sha256']
    elif kind=='prompt':manifest['unchanged_prompt_function_sha256']['render_prompt']='different'
    elif kind=='budget':dump(Path(old['audit_dir'])/'budget.json',{'requests':0})
    elif kind=='cache':dump(Path(old['audit_dir'])/'response_cache/success.json',{'answer':'changed'})
    elif kind=='checkpoint':dump(parent/'checkpoints/tick-001.json',{'sha256':'changed'})
    with pytest.raises(ValueError):validate_format_migration(old,new,parent,manifest)
