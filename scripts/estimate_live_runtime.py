"""Read-only progress / provisional ETA from durable live request events."""
from pathlib import Path
from datetime import datetime, timezone, timedelta
from collections import Counter
from statistics import mean, median
import json

ROOT=Path(__file__).resolve().parents[1]
latest=ROOT/'runs/v6/latest.json'
now=datetime.now(timezone.utc)
state=json.loads(latest.read_text(encoding='utf-8'))
run=Path(state['run_dir'])
provenance=json.loads((run/'provenance.json').read_text(encoding='utf-8'))
if provenance['mode']!='openai':
    print(json.dumps({'live_started':False,'latest_status':state['status'],'note':'No new live run has reached initialization yet.'},ensure_ascii=False))
    raise SystemExit(0)
audit=Path(provenance['audit_dir'])
events=[]
event_path=audit/'request-events.jsonl'
if event_path.exists():
    for line in event_path.read_text(encoding='utf-8').splitlines():
        try:
            record=json.loads(line)
            record['_time']=datetime.fromisoformat(record['time'])
            events.append(record)
        except (ValueError,KeyError):
            continue
completed={}
for event in events:
    if event.get('stage')=='validation_passed':
        completed[(event.get('agent_id'),event.get('tick'))]=event['_time']
started=min((e['_time'] for e in events),default=now)
elapsed=max(0.,(now-started).total_seconds())
rolling_count=sum((now-t).total_seconds()<=120 for t in completed.values())
rolling_window=min(120.,max(1.,elapsed))
rolling_rate=rolling_count/rolling_window
recent_rates={str(seconds):sum((now-t).total_seconds()<=seconds for t in completed.values())/min(seconds,max(1.,elapsed))*60
              for seconds in (30,60,120)}
latencies=[e['elapsed_seconds'] for e in events if e.get('stage')=='response_body_received' and isinstance(e.get('elapsed_seconds'),(float,int))]
budget=json.loads((audit/'budget.json').read_text(encoding='utf-8')) if (audit/'budget.json').exists() else {}
gate=json.loads((audit/'rate-limit-state.json').read_text(encoding='utf-8')) if (audit/'rate-limit-state.json').exists() else {}
statuses=Counter()
for path in audit.glob('request-*.json'):
    try:
        record=json.loads(path.read_text(encoding='utf-8'))
        statuses[record.get('status','unknown')]+=1
    except ValueError:
        pass
last_tick=state['last_completed_tick']
committed_llm=0
for tick in range(1,last_tick+1):
    data=json.loads((run/f'checkpoints/tick-{tick:03d}.json').read_text(encoding='utf-8'))
    committed_llm+=sum(a['action_payload'].get('api',{}).get('request_number') is not None for a in data['actions'])
upper_decisions=committed_llm+305*(provenance['total_steps']-last_tick)
if last_tick==0:
    upper_decisions=43+305*(provenance['total_steps']-1)
remaining=max(0,upper_decisions-len(completed))
eta_minutes=remaining/rolling_rate/60 if rolling_rate>0 and len(completed)>=20 else None
cfg=provenance['config']
input_used=max(budget.get('input_reserved_units',0),budget.get('actual_input_tokens',0))
mean_reserved=budget.get('input_reserved_units',0)/max(1,budget.get('requests',0))
result=dict(live_started=True,run_dir=str(run),status=state['status'],last_completed_tick=last_tick,
    sampled_at_china=now.astimezone(timezone(timedelta(hours=8))).isoformat(),
    elapsed_minutes=elapsed/60,validated_llm_decisions=len(completed),current_tick=max((e.get('tick',0) for e in events),default=0),
    recent_validated_decisions_per_minute=rolling_rate*60,recent_rates_per_minute=recent_rates,request_statuses=dict(statuses),budget=budget,
    effective_concurrency=gate.get('effective_concurrency'),rate_limit_events=gate.get('limit_events',0),
    mean_request_seconds=mean(latencies) if latencies else None,median_request_seconds=median(latencies) if latencies else None,
    maximum_total_decisions_from_committed_state=upper_decisions,remaining_decisions_upper_estimate=remaining,
    remaining_minutes_if_recent_rate_holds=eta_minutes,
    estimated_completion_china=(now+timedelta(minutes=eta_minutes)).astimezone(timezone(timedelta(hours=8))).isoformat() if eta_minutes is not None else None,
    input_reserved_units_remaining=cfg['max_input_reserved_units']-input_used,
    remaining_input_if_current_mean_holds=remaining*mean_reserved,
    estimate_limitations='Early-round throughput may change with longer memory, retries, rate limits and synchronous round barriers; this is not a guaranteed finish time.')
folder=ROOT/'runtime/v6/launch_requests'
folder.mkdir(parents=True,exist_ok=True)
(folder/'latest_progress_estimate.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(result,ensure_ascii=False,indent=2))
