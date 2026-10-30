"""Audited V7 runs and exact V7-only recovery; every exposed user calls the LLM."""
from __future__ import annotations
import argparse,hashlib,json,shutil,sys,os,re,threading,traceback
from datetime import datetime
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'vendor/SocioVerse2'))
import numpy as np
from socioverse.engine import build_simulator
from socioverse.schemas import StudySpec,EnvironmentBundle,PopulationBundle,SimulationConfig,EnvironmentLayer,InteractionStructure,InformationProgram,Broadcast,ScheduledEvent,WarmStartSpec
from model import load_rows,make_network,dump,digest,read_json,POPULATION_N
from experiment import defaults,validate_experiment,source_trust_values,assignment_summary
from government import select_targets,trust_values
from recovery import RunPaused,install_authorization

SOURCE=ROOT/'materials_v7'
CODE=ROOT/'app_v7'
RESULTS=ROOT/'runs/v7'
CONFIGS=ROOT/'runtime/v7/configs'
LOGS=ROOT/'runtime/v7/logs'
_EXPORT_LOCK=threading.RLock()


def bound_store_resources(store):
    """Bound database workers/buffers without changing observations or actions.

    54 independent DuckDB instances must not each assume they own the machine.
    Large Parquet/CSV exports share a lock; HTTP calls remain concurrent.
    """
    open_original,finalize_original=store.open,store.finalize
    def open_bounded():
        open_original()
        store._con.execute("SET threads=1")
        store._con.execute("SET memory_limit='256MB'")
    def finalize_bounded():
        with _EXPORT_LOCK:
            if store._con is None:return
            con=store._con
            try:
                # Large Parquet string buffers can exceed the per-live-case
                # allowance. Only one finalizer runs, so grant its encoder a
                # separate bounded allowance without raising all 54 instances.
                con.execute("SET memory_limit='1GB'")
                return finalize_original()
            except BaseException:
                # _materialize_metrics may already have created its table.
                # Never run finalize a second time and mask the original error
                # with CREATE TABLE metrics / CatalogException.
                try:con.close()
                except Exception:pass
                finally:store._con=None
                raise
    store.open,store.finalize=open_bounded,finalize_bounded


def repair_saved_exports(folder):
    """Finish existing committed data without building a client or calling LLM.

    Replay verifies every checkpoint/state first. The database and its source
    provenance are retained; only derived files and status are replaced.
    """
    import duckdb,tempfile
    from verify_run import verify
    from export_recovery import finalize_exports
    folder=Path(folder);prov=read_json(folder/'provenance.json');state=read_json(folder/'status.json')
    verified=verify(folder)
    if verified['last_completed_tick']!=state['last_completed_tick']:raise ValueError('Saved tick changed during repair')
    n=state['last_completed_tick'];total=prov['total_steps'];trajectory=folder/'trajectory'
    before_state=dict(state)
    with _EXPORT_LOCK:
        con=duckdb.connect(str(trajectory/'study.duckdb'),read_only=True,config={'threads':1,'memory_limit':'1GB'})
        try:
            if con.execute('SELECT count(*),count(DISTINCT (step,agent_id)) FROM panel').fetchone()!=((n+1)*300,(n+1)*300):
                raise ValueError('Duplicate or incomplete saved panel')
            if con.execute('SELECT count(*),min(step),max(step) FROM metrics').fetchone()!=(n+1,0,n):
                raise ValueError('Incomplete saved metrics; no completion status written')
            for name,query in [('panel.parquet','SELECT agent_id,step,CAST(state AS VARCHAR) AS state,action_kind,CAST(action_payload AS VARCHAR) AS action_payload,action_source FROM panel'),('metrics.parquet','SELECT * FROM metrics')]:
                fd,temp=tempfile.mkstemp(dir=trajectory,prefix='.repair-',suffix='.parquet');os.close(fd)
                try:
                    quoted=temp.replace('\\','/').replace("'","''")
                    con.execute(f"COPY ({query}) TO '{quoted}' (FORMAT PARQUET)")
                    expected=con.execute(f'SELECT count(*) FROM ({query})').fetchone()[0]
                    actual=con.execute('SELECT count(*) FROM read_parquet(?)',[temp]).fetchone()[0]
                    if actual!=expected:raise ValueError('Incomplete repaired Parquet')
                    with open(temp,'r+b') as stream:os.fsync(stream.fileno())
                    os.replace(temp,trajectory/name)
                finally:
                    if os.path.exists(temp):os.unlink(temp)
        finally:con.close()
        if n==total:
            state.update(status='completed_live' if prov['mode']=='openai' else 'completed_test')
            for key in ('error_type','error_details','error_context','export_error_type'):state.pop(key,None)
        dump(folder/'export_repair.json',dict(repaired_at=datetime.now().isoformat(),original_status=before_state,
            panel_rows=verified['panel_rows'],replay=verified['replay'],api_requests=0,
            source_database_preserved=True,repair_code_sha256=current_fingerprint(prov['config'],total,prov['mode'])['code_sha256']))
        try:
            finalize_exports(folder,load_rows(Path(prov['config_dir'])/'01_Agent基础信息表.csv'),prov['config'],state,
                prov['mode'],folder.parent/'latest.json',None if n==total else RuntimeError('Original partial run pause retained'))
        except RunPaused:
            if n==total or read_json(folder/'status.json').get('export_status')!='complete':raise
    return read_json(folder/'status.json')


def read_config(path=None):
    cfg=defaults()
    if path:
        overrides=read_json(path)
        if set(overrides)-set(cfg):raise ValueError('Unknown V7 configuration fields: '+str(sorted(set(overrides)-set(cfg))))
        cfg.update(overrides)
    validate_experiment(cfg);return cfg


def extract_post_blocks(text):
    blocks=[];current=[]
    for line in text.splitlines()+['']:
        if line.startswith('>'):current.append(line[1:].removeprefix(' '))
        elif current:blocks.append('\n'.join(current).strip());current=[]
    if len(blocks)!=2:raise ValueError('V7 requires two experimental post bodies')
    return blocks


def make_bundles(roster,prompt,cfg,audit,study_id='government-rumor-v7',steps=10):
    validate_experiment(cfg);rows=load_rows(roster);folder=Path(roster).parent
    rumor,official=extract_post_blocks((folder/'03_新环境设定.md').read_text(encoding='utf-8'))
    scenario=read_json(folder/'05_案例与判断对象.json');edges=make_network(rows)
    targets=select_targets(rows,cfg);government=trust_values(rows,cfg);source=source_trust_values(rows,cfg);tg=cfg['government_tick']
    study=StudySpec(study_id=study_id,title='V7：300名LLM用户的谣言与官方回应传播',
        research_question='来源信任、政府介入时间、投放圈层比例和政府信任如何伴随300名LLM用户的判断与行动变化？',
        n_steps=steps,seed=cfg['behavior_seed'],time_unit='abstract',step_meaning='一轮同步观察与决策，无现实分钟映射',
        key_attributes=['current_belief','group'],metrics=['all_believe','all_reject','all_unjudged','comments','posts'],
        display_metrics=['all_believe','all_reject','all_unjudged'],metric_descriptions={'all_believe':'相信人数','all_reject':'不相信人数','all_unjudged':'未判断人数','comments':'累计评论数','posts':'累计原帖和转发数'},
        domain='rumor',tags=['V7','LLM-only','300-agents'],provider_refs=['rumor_v7.population','rumor_v7.environment','rumor_v7.decision','rumor_v7.metrics'],status='engineering-only')
    args={k:cfg[k] for k in ('feed_policy','comment_window_limit','comment_participation_policy','memory_comment_policy','memory_retention_policy','memory_window_ticks','decision_condition_policy','belief_measurement_policy','comment_target','belief_update_policy','belief_transition_policy','government_trust_prompt_policy')}
    args.update(roster_csv=str(roster),edges=edges,direct_targets=targets,government_tick=tg,government_trust=government,source_trust=source,
        rumor_text=rumor,correction_text=official,belief_target=scenario['belief_target'],comment_tie_seed=cfg['behavior_seed'])
    env=EnvironmentBundle(study_id=study_id,provider_ref='rumor_v7.environment',provider_args=args,
        layers=[EnvironmentLayer(name='follow_network',modality='physical',scope='local',dynamics='static',description='每人关注8名同圈用户与2名异圈用户；圈内48人另关注SOURCE'),
                EnvironmentLayer(name='post_stream',modality='information',scope='local',dynamics='endogenous',description='网络控制首次接触；官方独立账号向50人投放一次')],
        scheduled_events=[ScheduledEvent(at_step=tg,target_layer='follow_network',op='set',property_name='government_enabled',value=True,note=f'官方独立账号向{len(targets)}人投放一次')],
        information_program=InformationProgram(broadcasts=[Broadcast(message_id='G001',content=official,at_step=tg,ttl=1,audience={'agent_ids':targets},note='实验性官方帖，仅实际展示者算接触')]))
    pop=PopulationBundle(study_id=study_id,provider_ref='rumor_v7.population',provider_args={'roster_csv':str(roster)},materialized_count=300,
        interaction=InteractionStructure(kind='explicit_network',edges=edges),propagation='broadcast_then_local')
    sim=SimulationConfig(study_id=study_id,n_steps=steps,seed=cfg['behavior_seed'],decision_ref='rumor_v7.decision',
        decision_args={'config':cfg,'prompt_file':str(prompt),'audit_dir':str(audit)},collector_ref='rumor_v7.metrics',interaction_rounds=1,engine_args={'memory_window':3})
    return study,env,pop,sim


def current_fingerprint(cfg,steps,mode='openai'):
    return dict(version='V7',input_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in SOURCE.iterdir() if p.is_file()},
        code_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in CODE.glob('*.py')},
        numpy_version=np.__version__,total_steps=steps,upstream_url='https://github.com/sii-research/SocioVerse2',
        upstream_commit=read_json(ROOT/'vendor/UPSTREAM.json')['commit'],mode=mode,dry_run=mode!='openai',config=cfg)


def config_for_args(args):
    cfg=read_config(args.config)
    if getattr(args,'concurrency',None) is not None:cfg['max_concurrency']=args.concurrency
    if getattr(args,'max_requests',None) is not None:cfg['max_requests']=args.max_requests
    validate_experiment(cfg);return cfg


def check_resume_compatible(args):
    previous=read_json(Path(args.resume)/'provenance.json')
    if previous.get('version')!='V7':raise ValueError('V7 cannot resume another population/version')
    cfg=config_for_args(args);current=current_fingerprint(cfg,args.steps,previous['mode'])
    for key in ('input_sha256','code_sha256','numpy_version','total_steps','upstream_commit','mode'):
        if key=='code_sha256' and current[key]!=previous[key] and getattr(args,'maintenance_migration_manifest',None):
            from maintenance_recovery import verify_migration
            verify_migration(args.maintenance_migration_manifest,previous,current);continue
        if current[key]!=previous[key]:raise ValueError('V7 resume requires unchanged '+key)
    oldcfg=previous['config']
    for key in cfg:
        if cfg[key]==oldcfg[key]:continue
        if not getattr(args,'execution_limit_migration',False) or key not in ('prompt_input_token_limit','max_input_reserved_units','max_output_reserved_tokens') or cfg[key]<oldcfg[key]:
            raise ValueError('V7 resume cannot change scientific or execution settings: '+key)


def prepare_replay(parent,destination,upto):
    completed=0;lines=[];expected={f'A{i:04d}' for i in range(1,301)}
    for t in range(1,upto+1):
        path=parent/'checkpoints'/f'tick-{t:03d}.json'
        if not path.exists():break
        data=read_json(path);actions=data['actions']
        if digest(actions)!=data['sha256'] or len(actions)!=300 or {a['agent_id'] for a in actions}!=expected or any(a['step']!=t for a in actions):raise ValueError('V7 incomplete or invalid checkpoint')
        lines.extend(json.dumps(a,ensure_ascii=True) for a in actions);completed=t
    replay=destination/'recovery_actions.jsonl';replay.write_text('\n'.join(lines)+'\n',encoding='utf-8')
    return completed,replay


def copy_recovery_file(source,destination):
    """Reuse immutable audit JSON; mutable ledgers and append logs stay separate.

    All program JSON writes use atomic replacement, so even a later cache write
    creates a separate file. Cross-volume or unsupported links use normal copy.
    """
    path=Path(source)
    immutable=(path.parent.name=='response_cache' and path.suffix=='.json') or re.fullmatch(r'request-\d+\.json',path.name)
    if immutable:
        try:
            os.link(source,destination)
            return str(destination)
        except FileExistsError:raise
        except OSError:pass
    return shutil.copy2(source,destination)


def execute(args,*,test_mode=False,run_roots=None,progress_callback=None):
    roots=run_roots or {}
    results_root=Path(roots.get('results',RESULTS));configs_root=Path(roots.get('configs',CONFIGS));logs_root=Path(roots.get('logs',LOGS))
    cfg=config_for_args(args);mode='test_stub' if test_mode else 'openai'
    if not 1<=args.steps<=40:raise ValueError('steps must be 1..40')
    if args.resume:
        check_resume_compatible(args)
        if read_json(Path(args.resume)/'provenance.json')['mode']!=mode:raise ValueError('cannot mix test and live data')
    if not test_mode:
        from credentials import validate_credentials
        validate_credentials(cfg)
    sid='government-rumor-v7-'+mode+'-'+datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    folder=results_root/sid;audit=logs_root/sid;frozen=configs_root/sid
    reuse_audit=bool(args.resume and getattr(args,'reuse_audit',False))
    if reuse_audit:
        audit=Path(read_json(Path(args.resume)/'provenance.json')['audit_dir'])
        if audit.resolve().parent!=logs_root.resolve() or not audit.is_dir():
            raise ValueError('Shared audit recovery must remain within the same condition log root')
    for p in (folder,frozen):p.mkdir(parents=True,exist_ok=False)
    if not reuse_audit:audit.mkdir(parents=True,exist_ok=False)
    for p in SOURCE.iterdir():
        if p.is_file():shutil.copy2(p,frozen/p.name)
    prov=current_fingerprint(cfg,args.steps,mode);prov.update(audit_dir=str(audit),config_dir=str(frozen))
    if args.resume and getattr(args,'maintenance_migration_manifest',None):
        previous=read_json(Path(args.resume)/'provenance.json')
        if previous['code_sha256']!=prov['code_sha256']:
            from maintenance_recovery import verify_migration
            prov['maintenance_upgrade']=verify_migration(args.maintenance_migration_manifest,previous,prov)
    dump(folder/'provenance.json',prov)
    study,env,pop,simcfg=make_bundles(frozen/'01_Agent基础信息表.csv',frozen/'02_Prompt固定提示词.md',cfg,audit,sid,args.steps)
    if args.resume:
        parent=Path(args.resume);old=read_json(parent/'provenance.json');completed,replay=prepare_replay(parent,folder,args.steps)
        simcfg.warm_start=WarmStartSpec(source_version=parent.name,source_trajectory=str(replay),resume_from=completed)
        if not reuse_audit:
            shutil.copytree(old['audit_dir'],audit,dirs_exist_ok=True,copy_function=copy_recovery_file)
        else:
            prov['audit_recovery_policy']='exclusive_batch_reuse_v1'
            prov['audit_reused_from']=str(parent.resolve())
        if getattr(args,'recovery_authorization',None):install_authorization(audit,args.recovery_authorization)
        if read_json(parent/'status.json').get('error_type')=='QuotaPause':
            from recovery import initialize_quota_recovery_gate
            prov['quota_recovery_gate']=initialize_quota_recovery_gate(audit,cfg)
        prov.update(resumed_from=str(parent.resolve()),inherited_completed_tick=completed);dump(folder/'provenance.json',prov)
    for name,obj in [('study.json',study),('environment/environment.json',env),('population/population.json',pop),('simulation/simulation.json',simcfg)]:dump(folder/name,obj.model_dump(mode='json'))
    for name,value in [('behavior_contract.json',cfg),('network_edges.json',env.provider_args['edges']),('government_targets.json',env.provider_args['direct_targets']),('government_trust.json',env.provider_args['government_trust']),('source_trust.json',env.provider_args['source_trust']),('trust_assignment_summary.json',assignment_summary(load_rows(frozen/'01_Agent基础信息表.csv'),env.provider_args['source_trust'],env.provider_args['government_trust']))]:dump(frozen/name,value)
    state={'status':'running','last_completed_tick':0,'dry_run':test_mode};metrics=[];simulator=None;failed=None
    dump(folder/'status.json',state);dump(results_root/'latest.json',{'run_dir':str(folder),**state})
    from parameter_report import write_parameters
    write_parameters(folder,cfg,args.steps)
    def on_step(t,m):
        metrics.append(m)
        if t:
            rows=simulator.store._con.execute('SELECT agent_id,action_kind,action_payload FROM panel WHERE step=? ORDER BY agent_id',[t]).fetchall()
            if len(rows)!=300 or len({r[0] for r in rows})!=300:raise ValueError('refusing incomplete V7 tick')
            actions=[dict(agent_id=a,step=t,action_kind=k,action_payload=json.loads(p)) for a,k,p in rows]
            dump(folder/'checkpoints'/f'tick-{t:03d}.json',{'actions':actions,'sha256':digest(actions)})
        state['last_completed_tick']=t
        dump(folder/'status.json',state);dump(results_root/'latest.json',{'run_dir':str(folder),**state})
        dump(folder/'trajectory/metrics_history.json',{'study_id':sid,'rows':metrics})
        if simulator.env.belief_tracker:
            from transition_report import write_tracker_report
            try:
                write_tracker_report(simulator.env.belief_tracker,folder/'reports',t)
            except PermissionError:
                dump(folder/'reports/transition_export_pending.json',dict(status='retry_on_next_committed_tick',last_completed_tick=t,
                    reason='derived_transition_csv_locked; authoritative_checkpoints_preserved'))
                print('转换CSV暂时被占用；完整轮次已保存，下轮或结束时重试导出。',flush=True)
        if progress_callback is not None:progress_callback(folder,dict(state),cfg,simulator.env,t,dict(m))
        print(f"tick {t}/{args.steps}: believe={m['all_believe']} reject={m['all_reject']} unjudged={m['all_unjudged']} population=300",flush=True)
    try:
        simulator=build_simulator(env_bundle=env,pop_bundle=pop,sim_config=simcfg,store_path=folder/'trajectory/study.duckdb',on_step=on_step)
        bound_store_resources(simulator.store)
        personas,initial=simulator.materialize_initial()
        (folder/'population/roster.jsonl').write_text('\n'.join(p.model_dump_json() for p in personas)+'\n',encoding='utf-8')
        dump(frozen/'initial_state.json',[r.model_dump() for r in initial])
        history=simulator.run();state['status']='completed_test' if test_mode else 'completed_live'
        dump(folder/'trajectory/metrics_history.json',history.model_dump())
    except (Exception,KeyboardInterrupt) as exc:
        failed=exc
        dump(folder/'failure_diagnostic.json',dict(error_type=type(exc).__name__,
            message=str(exc) if type(exc).__name__ in ('OutOfMemoryException','CatalogException') else 'See typed failure and request audit',
            frames=[dict(file=f.filename,line=f.lineno,function=f.name) for f in traceback.extract_tb(exc.__traceback__)]))
        state.update(status={'QuotaPause':'paused_quota','PromptBudgetPause':'paused_prompt_budget','HardBudgetPause':'paused_hard_budget','UncertainRequest':'paused_unknown_request','KeyboardInterrupt':'paused_by_user','BatchPauseRequested':'paused_by_user','OutputContractPause':'paused_output_contract','DecisionConditionsPause':'paused_decision_contract'}.get(type(exc).__name__,'interrupted'),error_type=type(exc).__name__)
        if type(exc).__name__ in ('PromptBudgetPause','OutputContractPause','HardBudgetPause'):
            state['error_details']=str(exc)
            if getattr(exc,'safe_details',None):state['error_context']=exc.safe_details
        if simulator is not None and simulator.store._con is not None:
            try:simulator.store.finalize()
            except Exception as cleanup:
                dump(folder/'cleanup_failure_diagnostic.json',dict(error_type=type(cleanup).__name__,original_error_type=type(exc).__name__,
                    frames=[dict(file=f.filename,line=f.lineno,function=f.name) for f in traceback.extract_tb(cleanup.__traceback__)]))
                con=simulator.store._con
                try:
                    if con is not None:con.close()
                finally:simulator.store._con=None
    finally:
        if simulator is not None:
            dump(folder/'trajectory/final_snapshot.json',{**simulator.env.snapshot(),'last_completed_tick':state['last_completed_tick']})
            client=getattr(simulator.decision,'client',None)
            if client is not None:client.close()
        dump(folder/'status.json',state);dump(results_root/'latest.json',{'run_dir':str(folder),**state})
    from export_recovery import finalize_exports
    with _EXPORT_LOCK:
        return finalize_exports(folder,load_rows(frozen/'01_Agent基础信息表.csv'),cfg,state,mode,results_root/'latest.json',failed)


def main():
    parser=argparse.ArgumentParser(description='V7：300名LLM用户，48圈内、252圈外')
    parser.add_argument('--config',default=str(ROOT/'configs/v7/local_defaults.json'));parser.add_argument('--steps',type=int,default=10)
    parser.add_argument('--max-requests',type=int);parser.add_argument('--concurrency',type=int)
    parser.add_argument('--resume');parser.add_argument('--execution-limit-migration',action='store_true')
    parser.add_argument('--no-interactive-recovery',action='store_true');parser.add_argument('--auto-retry-seconds',type=int,choices=(0,120),default=120)
    args=parser.parse_args()
    import msvcrt
    with (CODE/'.simulation.lock').open('a+b') as lock:
        if lock.tell()==0:lock.write(b'0');lock.flush()
        lock.seek(0)
        try:msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
        except OSError:raise SystemExit('Another V7 simulation is running')
        try:
            from recovery import supervise
            return supervise(args,execute,check_resume_compatible,interactive=sys.stdin.isatty() and not args.no_interactive_recovery)
        finally:lock.seek(0);msvcrt.locking(lock.fileno(),msvcrt.LK_UNLCK,1)


if __name__=='__main__':
    try:raise SystemExit(main())
    except KeyboardInterrupt:print('V7已取消；已有进度保留。',flush=True);raise SystemExit(130)
    except (ValueError,FileNotFoundError) as exc:print('V7配置/续跑错误：'+str(exc),file=sys.stderr);raise SystemExit(2)
