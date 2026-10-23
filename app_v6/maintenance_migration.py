"""Exact-parent export/recovery repair, with identical model inputs and budgets."""
import ast
import hashlib
from pathlib import Path
from model import read_json
from format_migration import file_sha

ALLOWED_FILES={'csv_io.py','export_recovery.py','maintenance_migration.py','measurement_report.py',
               'run.py','recovery.py','local_cli.py','test_export_recovery.py'}
PROTECTED_RUN_FUNCTIONS=('defaults','make_bundles','extract_post_blocks','prepare_replay',
                         'validate_execution_limit_migration','validate_rate_migration')


def protected_run_hashes(source):
    tree=ast.parse(source)
    return {n.name:hashlib.sha256(ast.dump(n,include_attributes=False).encode()).hexdigest()
            for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in PROTECTED_RUN_FUNCTIONS}


def validate_maintenance_migration(previous,current,parent,manifest,code_dir=None):
    parent=Path(parent).resolve();code_dir=Path(code_dir) if code_dir else Path(__file__).parent
    if str(parent)!=manifest['parent_run'] or file_sha(parent/'provenance.json')!=manifest['parent_provenance_sha256']:
        raise ValueError('Maintenance repair parent mismatch')
    if previous['code_sha256']!=manifest['old_code_sha256'] or current['code_sha256']!=manifest['new_code_sha256']:
        raise ValueError('Maintenance repair source mismatch')
    changed={k for k in previous['code_sha256'].keys()|current['code_sha256'].keys() if previous['code_sha256'].get(k)!=current['code_sha256'].get(k)}
    if not changed<=ALLOWED_FILES:raise ValueError('Maintenance cannot change prompts, model, API routing or scientific code')
    for key in ('config','input_sha256','mode','upstream_commit','total_steps','numpy_version'):
        if previous[key]!=current[key]:raise ValueError('Maintenance cannot change '+key)
    protected=protected_run_hashes((code_dir/'run.py').read_text(encoding='utf-8'))
    if protected!=manifest['protected_run_function_sha256'] or set(protected)!=set(PROTECTED_RUN_FUNCTIONS):
        raise ValueError('Maintenance changed protected scientific or replay functions')
    audit=Path(previous['audit_dir'])
    if file_sha(audit/'budget.json')!=manifest['budget_sha256']:raise ValueError('Maintenance spending ledger changed')
    for folder,pattern,key in ((audit,'request-*.json','audit_request_sha256'),
             (audit/'response_cache','*.json','valid_cache_sha256'),(parent/'checkpoints','tick-*.json','completed_checkpoint_sha256')):
        if {p.name:file_sha(p) for p in folder.glob(pattern)}!=manifest[key]:raise ValueError('Maintenance changed original responses/checkpoints')
