"""A prompt-format change may resume only an exactly reviewed parent."""
import copy
from pathlib import Path
import pytest
from model import dump
from compact_migration import validate_compact_migration,protected_model_hash,PREFLIGHT_HOOK
from format_migration import file_sha,function_hashes
import run


def fixture(tmp_path):
    code=tmp_path/'code';code.mkdir()
    (code/'llm_client.py').write_text((run.CODE/'llm_client.py').read_text(encoding='utf-8'),encoding='utf-8')
    old_model='class V4Decision:\n    def decide_batch(self, observations, memories):\n        return observations\n\nclass V4Environment:\n    def apply(self, actions):\n        return actions\n'
    model='class V4Decision:\n    def decide_batch(self, observations, memories):\n'+''.join('        '+line+'\n' for line in PREFLIGHT_HOOK.splitlines())+'        return observations\n\nclass V4Environment:\n    def apply(self, actions):\n        return actions\n'
    (code/'model.py').write_text(model,encoding='utf-8')
    parent=tmp_path/'parent';audit=tmp_path/'audit'
    old=dict(code_sha256={'model.py':'old'},config={'prompt_memory_policy':'preserve','prompt_input_token_limit':131072,
        'max_input_reserved_units':49971200,'government_tick':2},input_sha256={'material':'same'},mode='openai',
        upstream_commit='same',total_steps=10,numpy_version='same',audit_dir=str(audit))
    new=copy.deepcopy(old);new['config']['prompt_encoding']='lossless_thread_refs_v1';new['code_sha256']={'model.py':'new','compact_prompt.py':'new'}
    dump(parent/'provenance.json',old);dump(audit/'budget.json',{'requests':806})
    dump(audit/'request-000001.json',{'raw_response':'keep'})
    dump(audit/'response_cache/valid.json',{'answer':'keep'})
    dump(parent/'checkpoints/tick-001.json',{'actions':'keep'})
    manifest=dict(parent_run=str(parent.resolve()),parent_provenance_sha256=file_sha(parent/'provenance.json'),
        old_code_sha256=old['code_sha256'],new_code_sha256=new['code_sha256'],old_config=copy.deepcopy(old['config']),
        new_config=copy.deepcopy(new['config']),budget_sha256=file_sha(audit/'budget.json'),
        protected_model_sha256=protected_model_hash(old_model),protected_prompt_function_sha256=function_hashes((code/'llm_client.py').read_text(encoding='utf-8')),
        audit_request_sha256={'request-000001.json':file_sha(audit/'request-000001.json')},
        valid_cache_sha256={'valid.json':file_sha(audit/'response_cache/valid.json')},
        completed_checkpoint_sha256={'tick-001.json':file_sha(parent/'checkpoints/tick-001.json')})
    return old,new,parent,manifest,code


def test_reviewed_compaction_preserves_environment_and_old_results(tmp_path):
    old,new,parent,manifest,code=fixture(tmp_path)
    validate_compact_migration(old,new,parent,manifest,code_dir=code)


@pytest.mark.parametrize('change',['material','rules','scoring','research_config','budget','cache','checkpoint','code','prompt','unapproved_budget'])
def test_migration_blocks_unreviewed_changes(tmp_path,change):
    old,new,parent,m,code=fixture(tmp_path)
    if change=='material':new['input_sha256']['material']='different'
    elif change in ('rules','scoring'):
        path=code/'model.py';path.write_text(path.read_text().replace('return actions','return []') if change=='rules'
            else path.read_text().replace('return observations','return []'))
    elif change=='research_config':new['config']['government_tick']=4;m['new_config']=copy.deepcopy(new['config'])
    elif change=='budget':dump(Path(old['audit_dir'])/'budget.json',{'requests':0})
    elif change=='cache':dump(Path(old['audit_dir'])/'response_cache/valid.json',{'answer':'changed'})
    elif change=='checkpoint':dump(parent/'checkpoints/tick-001.json',{'actions':'changed'})
    elif change=='code':new['code_sha256']['unreviewed.py']='different';m['new_code_sha256']=new['code_sha256']
    elif change=='prompt':m['protected_prompt_function_sha256']['render_prompt']='different'
    elif change=='unapproved_budget':new['config']['max_input_reserved_units']=500000000;m['new_config']=copy.deepcopy(new['config'])
    with pytest.raises(ValueError):validate_compact_migration(old,new,parent,m,code_dir=code)


def test_budget_changes_require_exact_explicit_values(tmp_path):
    old,new,parent,m,code=fixture(tmp_path)
    new['config']['max_input_reserved_units']=90000000;m['new_config']=copy.deepcopy(new['config'])
    m['explicitly_authorized_limit_changes']={'max_input_reserved_units':[49971200,90000000]}
    validate_compact_migration(old,new,parent,m,code_dir=code)
    m['explicitly_authorized_limit_changes']['max_input_reserved_units'][1]=90000001
    with pytest.raises(ValueError):validate_compact_migration(old,new,parent,m,code_dir=code)


def test_reviewed_input_migration_initial_resume_does_not_require_extra_keypress(tmp_path):
    from types import SimpleNamespace
    from recovery import supervise
    parent=tmp_path/'parent';dump(parent/'status.json',{'status':'paused_prompt_budget'})
    calls=[]
    supervise(SimpleNamespace(resume=str(parent),input_migration_manifest='exact-reviewed'),
        lambda args:calls.append(args.resume),lambda args:None,interactive=True,
        reader=lambda prompt:pytest.fail('Explicitly reviewed migration should resume once'))
    assert calls==[str(parent)]
