"""Exact-parent reviewed input-encoding migration; no population/rule changes."""
import ast
import hashlib
from pathlib import Path
from model import read_json
from format_migration import file_sha,function_hashes

ALLOWED_FILES={'compact_prompt.py','compact_migration.py','llm_client.py','model.py','run.py','experiment.py',
               'recovery.py','local_cli.py','parameter_report.py','test_compact_prompt.py','test_compact_migration.py'}
PREFLIGHT_HOOK="if self.mode=='openai' and self.cfg.get('prompt_encoding')=='lossless_thread_refs_v1':\n    self.client.preflight_batch(observations,self.template)"


def protected_model_hash(source,strip_hook=False):
    tree=ast.parse(source)
    if strip_hook:
        expected=ast.dump(ast.parse(PREFLIGHT_HOOK).body[0],include_attributes=False)
        matches=0
        for cls in tree.body:
            if isinstance(cls,ast.ClassDef) and cls.name=='V4Decision':
                for method in cls.body:
                    if isinstance(method,ast.FunctionDef) and method.name=='decide_batch':
                        kept=[]
                        for node in method.body:
                            if ast.dump(node,include_attributes=False)==expected:matches+=1
                            else:kept.append(node)
                        method.body=kept
        if matches!=1:raise ValueError('Input migration requires only the reviewed preflight hook')
    return hashlib.sha256(ast.dump(tree,include_attributes=False).encode()).hexdigest()


def validate_compact_migration(previous,current,parent,manifest,code_dir=None):
    parent=Path(parent).resolve();code_dir=Path(code_dir) if code_dir else Path(__file__).parent
    if str(parent)!=manifest['parent_run'] or file_sha(parent/'provenance.json')!=manifest['parent_provenance_sha256']:
        raise ValueError('Input migration parent mismatch')
    if previous['code_sha256']!=manifest['old_code_sha256'] or current['code_sha256']!=manifest['new_code_sha256']:
        raise ValueError('Input migration source hashes differ')
    changed={k for k in previous['code_sha256'].keys()|current['code_sha256'].keys() if previous['code_sha256'].get(k)!=current['code_sha256'].get(k)}
    if not changed<=ALLOWED_FILES:raise ValueError('Input migration modified an unreviewed source file')
    for k in ('input_sha256','mode','upstream_commit','total_steps','numpy_version'):
        if previous[k]!=current[k]:raise ValueError('Input migration changed '+k)
    old,new=previous['config'],current['config']
    if old!=manifest['old_config'] or new!=manifest['new_config']:raise ValueError('Input migration config differs from reviewed values')
    if old.get('prompt_encoding','full_json_v1')!='full_json_v1' or new.get('prompt_encoding')!='lossless_thread_refs_v1':
        raise ValueError('Input migration must be full JSON to lossless references')
    for key in old.keys()|new.keys():
        if old.get(key)==new.get(key) or key=='prompt_encoding':continue
        if key not in ('prompt_input_token_limit','max_input_reserved_units','max_output_reserved_tokens'):
            raise ValueError('Input migration cannot change research parameter '+key)
        if key not in manifest.get('explicitly_authorized_limit_changes',{}):raise ValueError('Input migration limit increase not authorized')
        if type(new[key]) is not int or new[key]<old[key]:raise ValueError('Input migration limits may only increase')
        if manifest['explicitly_authorized_limit_changes'][key]!=[old[key],new[key]]:raise ValueError('Input migration authorization value mismatch')
    functions=function_hashes((code_dir/'llm_client.py').read_text(encoding='utf-8'))
    for key in ('request_options','browsing_context','render_prompt'):
        if functions[key]!=manifest['protected_prompt_function_sha256'][key]:raise ValueError('Input migration changed protected role/response options')
    if protected_model_hash((code_dir/'model.py').read_text(encoding='utf-8'),strip_hook=True)!=manifest['protected_model_sha256']:
        raise ValueError('Input migration changed environment, scoring, rules or memory')
    audit=Path(previous['audit_dir'])
    if file_sha(audit/'budget.json')!=manifest['budget_sha256']:raise ValueError('Input migration spending changed')
    for folder,pattern,field in ((audit,'request-*.json','audit_request_sha256'),
             (audit/'response_cache','*.json','valid_cache_sha256'),(parent/'checkpoints','tick-*.json','completed_checkpoint_sha256')):
        if {x.name:file_sha(x) for x in folder.glob(pattern)}!=manifest[field]:raise ValueError('Input migration replaced original outcomes')
