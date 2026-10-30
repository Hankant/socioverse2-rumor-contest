"""Pinned maintenance upgrade: scientific inputs/config and valid cached answers stay fixed."""
from pathlib import Path
from model import read_json,digest
import time

ALLOWED={'run.py','batch54.py','batch_resources.py','syntax_repair.py','maintenance_recovery.py','llm_client.py',
    'credentials.py','round_robin_router.py','response_contract.py','output_adapter.py'}


def verify_migration(path,previous,current):
    manifest=read_json(path)
    if manifest.get('kind')!='v7-mechanical-recovery-v1':raise ValueError('Invalid maintenance manifest')
    if previous['code_sha256']!=manifest['previous_code_sha256'] or current['code_sha256']!=manifest['current_code_sha256']:
        raise ValueError('Maintenance source hashes do not match pinned manifest')
    changed={k for k in set(previous['code_sha256'])|set(current['code_sha256']) if previous['code_sha256'].get(k)!=current['code_sha256'].get(k)}
    if not changed<=ALLOWED or changed!=set(manifest['changed_files']):raise ValueError('Maintenance exceeded its reviewed scope')
    for key in ('version','input_sha256','numpy_version','total_steps','upstream_commit','mode','config'):
        if previous[key]!=current[key]:raise ValueError('Maintenance cannot change scientific inputs, model, steps or budgets: '+key)
    return dict(kind=manifest['kind'],manifest_path=str(Path(path).resolve()),manifest_sha256=digest(manifest),changed_files=sorted(changed))


def quota_recovery_info(info,shared_diagnostic=None):
    """A later parallel success must not mask the refusal that paused the tick."""
    from auto_retry import eligible
    if eligible(info) or info['status'].get('error_type')!='QuotaPause':return info
    from copy import deepcopy
    candidates=[]
    for p in sorted(Path(info['audit']).glob('request-*.json'),reverse=True):
        row=read_json(p)
        if row.get('status') in ('request_error','quota_paused'):
            diag=row.get('diagnostic') or ({'status_code':200,'service_status_code':row['service_status_code']} if row.get('service_status_code') else {})
            candidates.append(dict(request_number=row.get('request_number'),diagnostic=diag,scope='own_recorded_provider_refusal'))
            break  # Never skip a newer auth/parameter refusal to revive an older rate limit.
    if shared_diagnostic and not candidates:candidates.append(dict(diagnostic=shared_diagnostic,scope='batch_recorded_provider_refusal'))
    for candidate in candidates:
        result=deepcopy(info);result['recent_request']=candidate
        if eligible(result):return result
    return info


def automatic_recovery_decision(info,policy):
    """User-authorized, bounded new attempts; valid answers and ledgers stay fixed.

    Only a recorded network outcome loss or retryable output-contract failure
    qualifies. Arbitrary runtime errors, HTTP422, hard limits, manual pauses and
    provider content refusals remain explicit operator decisions.
    """
    if not policy or policy.get('version')!='user-authorized-batch-recovery-v1' or not policy.get('user_authorization'):return None
    for key in ('max_unknown_reissues_per_decision','max_output_windows_per_decision'):
        if type(policy.get(key)) is not int or not 1<=policy[key]<=3:raise ValueError('Invalid automatic recovery retry allowance')
    if type(policy.get('wait_seconds')) is not int or not 1<=policy['wait_seconds']<=600:raise ValueError('Invalid automatic recovery wait')
    state=info['status'];cfg=info['provenance']['config'];budget=info['budget'];audit=Path(info['audit'])
    if state.get('export_status')!='complete':return None
    if (budget['requests']>=cfg['max_requests'] or max(budget.get('input_reserved_units',0),budget.get('actual_input_tokens',0))>=cfg['max_input_reserved_units']
            or budget.get('output_reserved_tokens',0)>=cfg['max_output_reserved_tokens']):return None
    if state.get('error_type') not in ('UncertainRequest','OutputContractPause','DecisionConditionsPause'):return None
    path=audit/'recovery_authorizations.json';entries=read_json(path)['entries'] if path.exists() else []
    unknown=info['unknown'];signatures=[]
    if unknown:
        for item in unknown:
            record=read_json(audit/item['file']);diagnostic=record.get('diagnostic') or {};sig=item['prompt_sha256']
            if (record.get('status')!='pending_usage_unknown' or record.get('prompt_sha256')!=sig
                    or diagnostic.get('exception_type') not in ('APITimeoutError','APIConnectionError')):return None
            used=sum(r.get('prompt_sha256')==sig for e in entries for r in e.get('unknown_reissue',[]))
            if used>=policy['max_unknown_reissues_per_decision']:return None
            signatures.append(sig)
        kind='unknown_network_response'
    else:
        if state.get('error_type') not in ('OutputContractPause','DecisionConditionsPause'):return None
        if (state.get('error_context') or {}).get('code')=='provider_refusal':return None
        from response_contract import ERROR_LABELS
        for validation in sorted((audit/'validation').glob('request-*.json'),reverse=True):
            report=read_json(validation);sig=report.get('prompt_sha256');diagnostic=report.get('diagnostic') or {}
            if not sig or (audit/'response_cache'/f'{sig}.json').exists():continue
            record=read_json(audit/validation.name)
            if record.get('tick')!=state['last_completed_tick']+1:continue
            if diagnostic.get('code') not in ERROR_LABELS or diagnostic.get('code')=='provider_refusal' or diagnostic.get('retryable') is False:return None
            used=sum(e.get('recovery_kind')=='output_contract' and sig in e.get('recovery_prompt_sha256s',[]) for e in entries)
            if used>=policy['max_output_windows_per_decision']:return None
            signatures=[sig];break
        if not signatures:return None
        kind='output_contract'
    return dict(wait_seconds=policy['wait_seconds'],kind=kind,authorization=dict(
        request_cutoff=budget['requests'],unknown_reissue=unknown,action='user_authorized_automatic_recovery_v1',
        source_run=str(Path(info['run_dir']).resolve()),recovery_kind=kind,recovery_prompt_sha256s=sorted(set(signatures)),
        user_authorization=policy['user_authorization'],policy_version=policy['version'],prepared_at_epoch=time.time()))
