"""Two-minute recovery for explicit provider refusals; never reissue unknowns."""
from datetime import datetime, timezone, timedelta
import math
import time
from pathlib import Path
from model import dump, read_json

ACTION = 'auto_retry_120s'
HTTP_RETRY = {429, 500, 502, 503, 504, 529}
SERVICE_RETRY = {1000, 1001, 1002, 1024, 1033, 1041, 1045, 2045, 2046, 2047, 2056, 2062, 2064, 2066, 2067}


def eligible(info):
    status, cfg, budget = info['status'], info['provenance']['config'], info['budget']
    if status.get('error_type') != 'QuotaPause' or status.get('export_status') == 'failed' or info['unknown']:
        return False
    if (budget.get('requests', 0) >= cfg['max_requests']
            or max(budget.get('input_reserved_units', 0), budget.get('actual_input_tokens', 0)) >= cfg['max_input_reserved_units']
            or budget.get('output_reserved_tokens', 0) >= cfg['max_output_reserved_tokens']):
        return False
    recent = info.get('recent_request') or {}
    diag = recent.get('diagnostic') or {}
    return diag.get('status_code') in HTTP_RETRY or diag.get('service_status_code') in SERVICE_RETRY


def routing_ready(info, now=None):
    """Preserve provider/key cooldowns; this check makes no network request."""
    cfg = info['provenance']['config']
    if cfg.get('api_routing_policy') != 'round_robin_v1' or cfg.get('api_key_mode') != 'windows_dpapi_failover':
        return True
    from credentials import vault_path
    path = vault_path().parent/'routing-round-robin.json'
    if not path.exists():
        return True
    state = read_json(path); deadlines = [state['blocked_until'][s] for s in state['slots']]
    if not deadlines or any(type(x) not in (int, float) or not math.isfinite(x) for x in deadlines):
        return True  # The client's strict router validation will stop bad state.
    return min(deadlines) <= (time.time() if now is None else now)


def decision_after_wait(info, output, waiter, clock=time.time, ready=routing_ready):
    if not eligible(info):
        return None
    report = Path(info['run_dir'])/'reports/auto_retry.json'
    cycle = 0
    while True:
        cycle += 1
        at = clock()+120
        dump(report, {'status':'waiting_auto_retry', 'interval_seconds':120, 'cycle':cycle,
                      'next_retry_epoch':at, 'request_count':info['budget'].get('requests', 0),
                      'unknown_reissue':False})
        when = datetime.fromtimestamp(at, timezone(timedelta(hours=8))).strftime('%H:%M:%S')
        output(f"临时限流/服务繁忙：进度已保存，120秒后（北京时间 {when}）自动重连；Ctrl+C 返回暂停菜单。")
        if not waiter(2, output=output):
            dump(report, {'status':'cancelled', 'interval_seconds':120, 'cycle':cycle})
            return None
        if not ready(info):
            output('接口仍处于供应商或密钥冷却期；不提前发送请求，2分钟后再次检查。')
            continue
        dump(report, {'status':'retrying', 'interval_seconds':120, 'cycle':cycle,
                      'request_count':info['budget'].get('requests', 0), 'unknown_reissue':False})
        return {'config':dict(info['provenance']['config']), 'authorization':{
            'request_cutoff':info['budget'].get('requests', 0), 'unknown_reissue':[],
            'action':ACTION, 'source_run':str(Path(info['run_dir']).resolve())}}
