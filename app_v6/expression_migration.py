"""Exactly reviewed wording/metadata change, preserving v1 decision identity."""
from pathlib import Path
from format_migration import file_sha, function_hashes
from maintenance_migration import protected_run_hashes, PROTECTED_RUN_FUNCTIONS

ALLOWED_FILES = {'concise_wire.py','expression_migration.py','response_contract.py','llm_client.py',
                 'run.py','local_cli.py','recovery.py','experiment.py','test_concise_wire.py'}


def validate_expression_migration(previous,current,parent,manifest,code_dir=None):
    parent=Path(parent).resolve()
    code_dir=Path(code_dir) if code_dir else Path(__file__).parent
    if str(parent)!=manifest['parent_run'] or file_sha(parent/'provenance.json')!=manifest['parent_provenance_sha256']:
        raise ValueError('Expression migration parent mismatch')
    if previous['code_sha256']!=manifest['old_code_sha256'] or current['code_sha256']!=manifest['new_code_sha256']:
        raise ValueError('Expression migration source mismatch')
    changed={k for k in previous['code_sha256'].keys()|current['code_sha256'].keys()
             if previous['code_sha256'].get(k)!=current['code_sha256'].get(k)}
    if not changed<=ALLOWED_FILES:raise ValueError('Expression migration changed scientific or unreviewed code')
    for key in ('input_sha256','mode','upstream_commit','total_steps','numpy_version'):
        if previous[key]!=current[key]:raise ValueError('Expression migration changed '+key)
    old,new=previous['config'],current['config']
    if old!=manifest['old_config'] or new!=manifest['new_config']:raise ValueError('Expression config mismatch')
    expected={**old,'wire_prompt_style':'concise_lossless_v1'}
    if new!=expected:raise ValueError('Expression migration may only enable concise wire style')
    if function_hashes((code_dir/'llm_client.py').read_text(encoding='utf-8'))!=manifest['protected_prompt_function_sha256']:
        raise ValueError('Expression migration changed original logical prompt/cache identity')
    protected=protected_run_hashes((code_dir/'run.py').read_text(encoding='utf-8'))
    if protected!=manifest['protected_run_function_sha256'] or set(protected)!=set(PROTECTED_RUN_FUNCTIONS):
        raise ValueError('Expression migration changed study/replay functions')
    audit=Path(previous['audit_dir'])
    if file_sha(audit/'budget.json')!=manifest['budget_sha256']:raise ValueError('Expression migration spending changed')
    for folder,pattern,key in ((audit,'request-*.json','audit_request_sha256'),
             (audit/'response_cache','*.json','valid_cache_sha256'),(parent/'checkpoints','tick-*.json','completed_checkpoint_sha256')):
        if {p.name:file_sha(p) for p in folder.glob(pattern)}!=manifest[key]:
            raise ValueError('Expression migration changed original responses/checkpoints')
