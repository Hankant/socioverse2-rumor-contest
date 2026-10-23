"""Exact-parent migration for a reviewed output-schema adapter; no rule changes."""
import ast
import hashlib
from pathlib import Path
from model import read_json

ALLOWED_CHANGED_FILES = {"llm_client.py", "output_adapter.py", "format_migration.py", "run.py",
                         "local_cli.py", "recovery.py", "test_output_adapter.py", "response_contract.py",
                         "test_response_retry.py", "test_shared_thread.py"}
ALLOWED_CHANGED_FILES.update({'syntax_repair.py','test_syntax_repair.py','concise_wire.py'})
PROTECTED_FUNCTIONS = ("request_options", "browsing_context", "render_prompt", "prepare_prompt")


def file_sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def function_hashes(source):
    # Python reads source with universal newlines; ZIP bytes may still contain
    # Windows CRLF. Normalize only line endings before comparing function text.
    source=source.replace('\r\n','\n').replace('\r','\n')
    tree = ast.parse(source)
    return {node.name: hashlib.sha256(ast.get_source_segment(source,node).encode()).hexdigest()
            for node in tree.body if isinstance(node,ast.FunctionDef) and node.name in PROTECTED_FUNCTIONS}


def validate_format_migration(previous, current, parent, manifest, code_dir=None):
    parent=Path(parent).resolve()
    if str(parent) != manifest["parent_run"] or file_sha(parent/"provenance.json") != manifest["parent_provenance_sha256"]:
        raise ValueError("Format migration parent/provenance mismatch")
    if previous["code_sha256"] != manifest["old_code_sha256"] or current["code_sha256"] != manifest["new_code_sha256"]:
        raise ValueError("Format migration code hash mismatch")
    changed={k for k in previous['code_sha256'].keys()|current['code_sha256'].keys()
             if previous['code_sha256'].get(k)!=current['code_sha256'].get(k)}
    if not changed <= ALLOWED_CHANGED_FILES:
        raise ValueError("Format migration cannot change environment, behavior or measurement code")
    for key in ("input_sha256","mode","upstream_commit","numpy_version","total_steps"):
        if previous[key]!=current[key]:raise ValueError("Format migration cannot change "+key)
    if previous['config']!=current['config']:
        raise ValueError("Format migration cannot change configuration or execution limits")
    code_dir=Path(code_dir) if code_dir else Path(__file__).parent
    protected=function_hashes((code_dir/'llm_client.py').read_text(encoding='utf-8'))
    if protected != manifest['unchanged_prompt_function_sha256'] or set(protected)!=set(PROTECTED_FUNCTIONS):
        raise ValueError("Format migration cannot change prompts or request options")
    audit=Path(previous['audit_dir'])
    if file_sha(audit/'budget.json')!=manifest['budget_sha256']:
        raise ValueError("Format migration spending ledger changed")
    for sub, pattern, field in ((audit,'request-*.json','audit_request_sha256'),
                               (audit/'response_cache','*.json','valid_cache_sha256'),
                               (parent/'checkpoints','tick-*.json','completed_checkpoint_sha256')):
        if {p.name:file_sha(p) for p in sub.glob(pattern)}!=manifest[field]:
            raise ValueError("Format migration cannot replace requests, caches or checkpoints")
