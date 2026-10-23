"""One prepared recovery, gated by explicit human reissue approval. No key files."""
from pathlib import Path
import getpass,hashlib,json,os,subprocess,sys,time
ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'runtime/v6/recovery_prepared/heterogeneity-single-20261022-171233'
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def write(p,d):p.write_text(json.dumps(d,ensure_ascii=False,indent=2),encoding='utf-8')
def activate(plan):
    approval=read(Path(plan['approval_file']))
    expected_numbers=[item['request_number'] for item in plan['pending']]
    if approval.get('plan_id')!=plan['plan_id'] or approval.get('authorize_reissue_request_numbers')!=expected_numbers or approval.get('authorized_by')!='human_user':
        raise ValueError('Explicit reissue authorization does not match the prepared plan')
    if (BASE/'activated.json').exists():return
    audit=Path(plan['audit_copy'])
    for item in plan['pending']:
        p=audit/item['file']
        if hashlib.sha256(p.read_bytes()).hexdigest()!=item['sha256']:raise ValueError('Prepared pending audit changed')
    for item in plan['pending']:
        p=audit/item['file'];record=read(p)
        record.update(status='reissue_authorized_outcome_unknown',original_status='pending_usage_unknown',
                      reissue_authorization=approval,original_request_preserved_at=str(Path(read(Path(plan['original_run'])/'provenance.json')['audit_dir'])/item['file']))
        write(p,record)
    budget=read(audit/'budget.json');budget['usage_unknown_requests']+=len(plan['pending']);write(audit/'budget.json',budget)
    write(BASE/'activated.json',{'authorization':approval,'note':'Only audit copies annotated; original unknown outcomes remain unknown.'})
def main():
    plan=read(BASE/'plan.json')
    print('ONE V6 heterogeneous condition, 10 rounds, API concurrency cap 2.',flush=True)
    print(f"{plan['cached_valid_answers']} valid answers will be reused. Requests {[item['request_number'] for item in plan['pending']]} need explicit reissue approval.",flush=True)
    print('No API call occurs until the approval is received in the chat.',flush=True)
    key=getpass.getpass('MiniMax Token Plan key (hidden; not saved): ').strip()
    if not key.startswith('sk-cp-'):raise ValueError('Expected a subscription key beginning with sk-cp-')
    print('Key received locally. Waiting for explicit approval in the chat...',flush=True)
    while not Path(plan['approval_file']).exists():time.sleep(.5)
    activate(plan)
    os.environ['RUMOR_LLM_API_KEY']=key;key=None
    try:
        return subprocess.call([sys.executable,'-u',str(ROOT/'app_v6/local_cli.py'),'resume','--parent',plan['parent_copy']],cwd=ROOT)
    finally:os.environ.pop('RUMOR_LLM_API_KEY',None)
if __name__=='__main__':
    try:raise SystemExit(main())
    except KeyboardInterrupt:print('Recovery cancelled; no automatic retry.',flush=True);raise SystemExit(130)
