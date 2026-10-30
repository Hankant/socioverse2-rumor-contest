"""54 concurrent V7 studies; one shared API queue, per-study budget/cache/checkpoints."""
from concurrent.futures import ThreadPoolExecutor,wait,FIRST_COMPLETED
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
import argparse,copy,json,os,subprocess,sys,threading,time
import run
from model import V7Decision,V7Environment,read_json,dump
from batch_tables import WorkbookJob
from recovery import RunPaused,describe_pause
from auto_retry import eligible,decision_after_wait

DEFAULT_OUTPUT=Path('E:/papers/socioverse 2026/socioverse2_v6_local/Results_V7')


def prepare(output):
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    if any(output.glob('*.xlsx')):raise ValueError('Results_V7 already contains workbooks; resume the existing batch instead of overwriting')
    design=read_json(run.ROOT/'configs/v7/design54.json')
    if len(design)!=54 or len({c['name'] for c in design})!=54:raise ValueError('54 unique designs required')
    batch=output/'_batch54'/datetime.now().strftime('%Y%m%d-%H%M%S');batch.mkdir(parents=True,exist_ok=False);cases={}
    for item in design:
        cfg=run.read_config(run.ROOT/item['config']);tag=item['name'];name=tag+'_N300_IN48_OUT252_R50.xlsx'
        dump(batch/'configs'/f'{tag}.json',cfg)
        job=WorkbookJob(batch/'jobs'/f'{tag}.json',tag,cfg,name)
        _,bundle,_,_=run.make_bundles(run.SOURCE/'01_Agent基础信息表.csv',run.SOURCE/'02_Prompt固定提示词.md',cfg,batch/'preview-unused')
        env=V7Environment(bundle);env.reset(cfg['behavior_seed']);job.progress(None,dict(status='queued',last_completed_tick=0),cfg,env,0,{})
        cases[tag]=dict(status='queued',last_completed_tick=0,filename=name,run_dir=None)
    dump(batch/'batch_status.json',dict(status='prepared',created_at=datetime.now().isoformat(),steps=10,total=54,api_global_concurrency=2,output=str(output),cases=cases))
    dump(output/'LATEST_BATCH.json',dict(batch_dir=str(batch),output=str(output)))
    return batch


def load_job(batch,tag):
    data=read_json(batch/'jobs'/f'{tag}.json');job=WorkbookJob.__new__(WorkbookJob)
    job.path=batch/'jobs'/f'{tag}.json';job.tag=tag;job.cfg=data['config'];job.filename=data['filename'];job.folder=Path(data['run_dir']) if data.get('run_dir') else None
    job.main={};job.detail={};job.transitions=data.get('belief_to_reject_events')
    for key in ('rows','detail'):
        target=job.main if key=='rows' else job.detail
        for row in data[key]:target.setdefault(row['tick'],[]).append(row)
    return job


def start(batch,runtime):
    batch=Path(batch);state=read_json(batch/'batch_status.json');output=Path(state['output']);lock=threading.RLock();stop=threading.Event()
    # Bound disk-heavy checkpoint loading/replay, not live API concurrency.
    # Once a case reaches its inherited tick it releases this startup permit.
    warmups=threading.BoundedSemaphore(2)
    from credentials import validate_credentials
    cfg=run.read_config(batch/'configs'/f"{next(iter(state['cases']))}.json");validate_credentials(cfg)
    from batch_resources import client_class
    factory=client_class(batch,cfg);V7Decision.client_factory=factory
    controls=read_json(batch/'request_controls.json') if (batch/'request_controls.json').exists() else {}
    recovery_policy=controls.get('automatic_recovery')
    node=runtime['node'];script=str(run.ROOT/'scripts/export_batch_xlsx.mjs')
    excel_log=(batch/'excel_export.log').open('a',encoding='utf-8')
    exporter=subprocess.Popen([node,script,'--jobs',str(batch/'jobs'),'--output',str(output),'--watch'],stdout=excel_log,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    state.update(status='running',pid=os.getpid(),started_at=datetime.now().isoformat(),
        api_global_concurrency=factory.shared_limiter.ceiling,api_slot_concurrency=factory.shared_router.limits,
        api_key_retry_interval_seconds=factory.shared_router.retry_interval);dump(batch/'batch_status.json',state)
    def update(tag,**fields):
        with lock:
            if fields.get('status') in ('running','completed_live'):
                for key in ('error_type','error_details','error_context'):state['cases'][tag].pop(key,None)
            state['cases'][tag].update(fields);state['updated_at']=datetime.now().isoformat();dump(batch/'batch_status.json',state)
    def worker(tag):
        job=load_job(batch,tag);item=state['cases'][tag]
        if item['status']=='completed_live':return
        args=SimpleNamespace(config=str(batch/'configs'/f'{tag}.json'),steps=10,resume=item.get('run_dir'),concurrency=None,max_requests=None,execution_limit_migration=False,
            maintenance_migration_manifest=state.get('maintenance_migration_manifest'),reuse_audit=True)
        authorization=state.get('recovery_authorizations',{}).get(tag)
        if args.resume:
            previous=read_json(Path(args.resume)/'provenance.json')
            saved_status=read_json(Path(args.resume)/'status.json')
            if authorization:
                budget=read_json(Path(previous['audit_dir'])/'budget.json')
                if authorization.get('source_run')!=args.resume or authorization.get('request_cutoff')!=budget['requests']:
                    authorization=None
                    with lock:
                        state.get('recovery_authorizations',{}).pop(tag,None);dump(batch/'batch_status.json',state)
            # Avoid reading every old prompt twice for an ordinary saved pause.
            # LiveClient's whole-tick preflight still checks unknown outcomes
            # before dispatch; install_authorization verifies exact retry files.
            needs_review=authorization is None and saved_status.get('error_type') in ('UncertainRequest','OutputContractPause','DecisionConditionsPause')
            if needs_review:
                info=describe_pause(args.resume)
                from maintenance_recovery import automatic_recovery_decision
                decision=automatic_recovery_decision(info,recovery_policy)
                if decision:authorization=decision['authorization']
            if authorization:args.recovery_authorization=authorization
            if needs_review and info['unknown'] and not authorization:
                job.write('paused_unknown_request',item['last_completed_tick'],'UncertainRequest')
                update(tag,status='paused_unknown_request',error_type='UncertainRequest');return
        roots=dict(results=batch/'cases'/tag/'runs',configs=batch/'cases'/tag/'frozen',logs=batch/'cases'/tag/'audit')
        warmup_held=False;warmup_target=0
        def release_warmup():
            nonlocal warmup_held
            if warmup_held:warmup_held=False;warmups.release()
        def progress(folder,status,cfg,env,t,metrics):
            if t>=warmup_target:release_warmup()
            if t<max(job.main,default=0):return  # Replaying must never erase the displayed completed history.
            job.progress(folder,status,cfg,env,t,metrics);update(tag,status='running',last_completed_tick=t,run_dir=str(folder))
        while not stop.is_set():
            while not warmups.acquire(timeout=.5):
                if stop.is_set() or (batch/'PAUSE_REQUESTED.json').exists():return
            warmup_held=True;warmup_target=max(job.main,default=0)
            try:
                folder=run.execute(args,run_roots=roots,progress_callback=progress)
                final=read_json(folder/'status.json');job.folder=folder;job.write(final['status'],final['last_completed_tick']);update(tag,**final,run_dir=str(folder));return
            except RunPaused as exc:
                # A cooperative stop needs no costly scan of every historical
                # prompt. execute() has already saved responses and exports.
                final=read_json(Path(exc.run_dir)/'status.json');job.folder=exc.run_dir;job.write(final['status'],final['last_completed_tick'],final.get('error_type'))
                update(tag,**final,run_dir=str(exc.run_dir))
                if stop.is_set() or (batch/'PAUSE_REQUESTED.json').exists():return
                info=describe_pause(exc.run_dir)
                from maintenance_recovery import quota_recovery_info
                info=quota_recovery_info(info,factory.shared_router.last_refusal)
                if eligible(info):
                    def waiter(minutes,**kw):return not stop.wait(minutes*60)
                    decision=decision_after_wait(info,print,waiter)
                    if decision is None:return
                else:
                    from maintenance_recovery import automatic_recovery_decision
                    decision=automatic_recovery_decision(info,recovery_policy)
                    if decision is None:return
                    update(tag,status='retry_wait',recovery_kind=decision['kind'])
                    print(f"[{tag}] {decision['kind']}: saved outcomes retained; retry through any available API in {decision['wait_seconds']}s.",flush=True)
                    if stop.wait(decision['wait_seconds']) or (batch/'PAUSE_REQUESTED.json').exists():return
                args.resume=str(exc.run_dir);args.recovery_authorization=decision['authorization']
                print(f'[{tag}] reconnecting through shared API router; budget and valid cache retained',flush=True)
            except Exception as exc:
                dump(batch/'controller_errors'/f'{tag}.json',dict(error_type=type(exc).__name__,
                    frames=[dict(file=f.filename,line=f.lineno,function=f.name) for f in __import__('traceback').extract_tb(exc.__traceback__)]))
                update(tag,status='controller_error',error_type=type(exc).__name__);job.write('controller_error',max(job.main,default=0),type(exc).__name__)
                print(f'[{tag}] controller error {type(exc).__name__}; inspect saved state',flush=True);return
            finally:release_warmup()
    print(f'V7 Batch54: starting all 54 conditions, GLOBAL API CONCURRENCY={factory.shared_limiter.ceiling}\n'
        f'Per-key capacity: {factory.shared_router.limits}; recovery probe interval={factory.shared_router.retry_interval}s\n'
        f'Rate-limit fallback: {factory.shared_router.fallback}; activated={factory.shared_router.fallback_active}\n'
        f'Excel output: {output}\nBatch directory: {batch}',flush=True)
    executor=ThreadPoolExecutor(max_workers=54);pending={executor.submit(worker,tag):tag for tag in state['cases']}
    try:
        while pending:
            if (batch/'PAUSE_REQUESTED.json').exists() and not stop.is_set():
                print('Cooperative pause: stopping new requests; saving in-flight responses and checkpoints.',flush=True)
                stop.set();factory.shared_limiter.stop.set()
            done,_=wait(pending,timeout=20,return_when=FIRST_COMPLETED)
            for future in done:future.result();pending.pop(future)
            counts={};total_ticks=0
            with lock:
                state['api_global_concurrency']=factory.shared_limiter.ceiling
                state['api_slot_concurrency']=dict(factory.shared_router.limits)
                state['rate_limit_fallback_active']=factory.shared_router.fallback_active
                for case in state['cases'].values():counts[case['status']]=counts.get(case['status'],0)+1;total_ticks+=case['last_completed_tick']
                dump(batch/'batch_status.json',state)
            print(f'Batch54 progress: complete ticks {total_ticks}/540; states={counts}',flush=True)
            if exporter.poll() is not None:
                exporter=subprocess.Popen([node,script,'--jobs',str(batch/'jobs'),'--output',str(output),'--watch'],stdout=excel_log,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        with lock:state['status']='paused_by_user' if stop.is_set() else 'completed' if all(c['status']=='completed_live' for c in state['cases'].values()) else 'needs_attention';dump(batch/'batch_status.json',state)
        print(f"Batch54 status: {state['status']}; see batch_status.json",flush=True)
    except KeyboardInterrupt:
        print('Stopping new API dispatches; finishing in-flight requests and saving caches.',flush=True)
        stop.set();factory.shared_limiter.stop.set()
        with lock:state['status']='stopping';dump(batch/'batch_status.json',state)
    finally:
        executor.shutdown(wait=True,cancel_futures=True)
        subprocess.run([node,script,'--jobs',str(batch/'jobs'),'--output',str(output)],stdout=excel_log,stderr=subprocess.STDOUT)
        if exporter.poll() is None:exporter.terminate()
        excel_log.close()
    return state


def main():
    p=argparse.ArgumentParser();p.add_argument('--prepare',action='store_true');p.add_argument('--pause',action='store_true');p.add_argument('--output',default=str(DEFAULT_OUTPUT));p.add_argument('--batch');args=p.parse_args()
    if args.prepare:
        print(prepare(args.output));return
    batch=Path(args.batch) if args.batch else Path(read_json(Path(args.output)/'LATEST_BATCH.json')['batch_dir'])
    if args.pause:
        dump(batch/'PAUSE_REQUESTED.json',dict(requested_at=datetime.now().isoformat(),reason='user_requested_cooperative_pause'))
        print('Pause requested: wait for in-flight responses to save; keep the control window open.');return
    import msvcrt
    with (run.CODE/'.simulation.lock').open('a+b') as handle:
        if handle.tell()==0:handle.write(b'0');handle.flush()
        handle.seek(0)
        try:msvcrt.locking(handle.fileno(),msvcrt.LK_NBLCK,1)
        except OSError:raise SystemExit('Another V7 controller is already running')
        try:
            pause=batch/'PAUSE_REQUESTED.json'
            if pause.exists():pause.unlink()
            final=start(batch,read_json(run.ROOT/'runtime/v7/workspace_runtime.json'))
            return 0 if final['status'] in ('completed','paused_by_user') else 2
        finally:handle.seek(0);msvcrt.locking(handle.fileno(),msvcrt.LK_UNLCK,1)


if __name__=='__main__':raise SystemExit(main())
