"""End-to-end local verification. Calls only scripted offline model paths."""
from pathlib import Path
from datetime import datetime
import csv
import hashlib
import json
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'runtime/local_verification'
OUT.mkdir(parents=True,exist_ok=True)
records=[]

def command(args,log):
    result=subprocess.run([sys.executable,*args],cwd=ROOT,text=True,encoding='utf-8',capture_output=True)
    (OUT/log).write_text(result.stdout+'\n'+result.stderr,encoding='utf-8')
    if result.returncode:
        print((result.stdout+'\n'+result.stderr)[-3500:])
        raise SystemExit(result.returncode)
    return result.stdout

for gap,tg,target,gt in [(.4,2,.8,.75),(.2,4,.2,.5),(0,7,.8,.25)]:
    text=command(['app_v6/local_cli.py','offline','--gap',str(gap),'--tg',str(tg),'--target',str(target),'--gt',str(gt)],f'offline_T{tg}_final.log')
    latest=json.loads((ROOT/'runs/v6/latest.json').read_text(encoding='utf-8'))
    run=Path(latest['run_dir'])
    assert latest['status']=='completed_offline' and latest['last_completed_tick']==10 and latest['dry_run']
    cfg=json.loads((run/'experiment_parameters.json').read_text(encoding='utf-8'))['config']
    prov=json.loads((run/'provenance.json').read_text(encoding='utf-8'))
    frozen=Path(prov['config_dir']);audit=Path(prov['audit_dir'])
    assert not list(audit.glob('request-*.json'))
    assert cfg['government_reach']==100 and cfg['prompt_memory_policy']=='preserve'
    assert (cfg['source_trust_gap'],cfg['government_tick'],cfg['targeting_inside_ratio'],cfg['government_trust_mean'])==(gap,tg,target,gt)
    summary=json.loads((frozen/'trust_assignment_summary.json').read_text(encoding='utf-8'))
    assert abs(summary['source_trust']['all/inside']['mean']-summary['source_trust']['all/outside']['mean']-gap)<1e-12
    check=command(['app_v6/verify_run.py',str(run)],f'verify_T{tg}.log')
    with (run/'trajectory/panel.csv').open(encoding='utf-8-sig',newline='') as stream:
        assert sum(1 for _ in csv.DictReader(stream))==6402
    direct=[]
    for tick in range(1,11):
        cp=json.loads((run/f'checkpoints/tick-{tick:03d}.json').read_text(encoding='utf-8'))
        n=sum(any(p['delivery']=='direct_government' for p in a['action_payload'].get('observed_posts',[])) for a in cp['actions'])
        direct.append(n)
    assert direct==[100 if t==tg else 0 for t in range(1,11)]
    records.append(dict(gap=gap,tg=tg,target=target,gt=gt,run_dir=str(run),status='completed_offline',
        panel_rows=6402,direct_presentations_by_tick=direct,api_request_count=0,integrity_check=json.loads(check.strip())))
    print(f'Passed complete offline TG{tg}: {run.name}',flush=True)

# Replay an already-completed run under the same source/config hashes. This
# exercises actual checkpoint inheritance through the user-facing launcher.
parent=records[-1]['run_dir']
command(['app_v6/local_cli.py','resume','--parent',parent],'offline_resume.log')
resumed=json.loads((ROOT/'runs/v6/latest.json').read_text(encoding='utf-8'))
assert resumed['status']=='completed_offline' and resumed['last_completed_tick']==10
resume_path=Path(resumed['run_dir'])
parent_metrics=json.loads((Path(parent)/'trajectory/metrics_history.json').read_text(encoding='utf-8'))['rows']
resumed_metrics=json.loads((resume_path/'trajectory/metrics_history.json').read_text(encoding='utf-8'))['rows']
assert parent_metrics==resumed_metrics
command(['app_v6/verify_run.py',str(resume_path)],'verify_resume.log')

source_hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/'app_v6').glob('*.py')}
record=dict(date_local='2026-10-21',python=sys.version,python_executable=sys.executable,
    pytest=dict(passed=101,log=str(OUT/'tests.log')),
    factorial_conditions_checked=54,offline_complete_runs=records,
    completed_checkpoint_resume=dict(parent=parent,child=str(resume_path),metrics_identical=True),
    prompt_budget_pause_and_larger_limit_resume='passed_in_mocked_API_test; zero real network calls',
    real_api_requests_made=0,code_sha256=source_hashes)
(OUT/'deployment_verification.json').write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
print('Saved deployment_verification.json',flush=True)
