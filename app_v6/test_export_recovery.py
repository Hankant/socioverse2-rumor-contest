"""Long real-shaped CSV cells, streaming DB reports and unmasked recovery."""
import copy
import csv
import json
from pathlib import Path
from types import SimpleNamespace

import duckdb
import pytest
from model import dump,read_json,BINARY_SCORE_POLICY
from csv_io import atomic_csv,ensure_large_fields,export_committed_panel,iter_committed_states
from measurement_report import write_measurements
from export_recovery import finalize_exports
from recovery import RunPaused,initialize_quota_recovery_gate,supervise
from llm_client import QuotaPause


def sample(tmp_path,size=160000):
    folder=tmp_path/'saved';trajectory=folder/'trajectory';trajectory.mkdir(parents=True)
    state=dict(current_belief='believe',subjective_credibility=70,
        component_credibility=dict(funds_redirected=71,safety_delayed=72,causal_link=73),
        exposure_summary={'P001':{'first_seen_tick':1}},opaque_state='原文'+('字'*size))
    payload=json.dumps({'comment':{'text':'完整正文'+('x'*size)+'\n最后一句，"引号"'},'observed_posts':[]},ensure_ascii=False)
    roster=[dict(agent_id='A0001',decision_mode='llm',group='inside')]
    return folder,state,payload,roster


def database(folder,state,payload):
    con=duckdb.connect(str(folder/'trajectory/study.duckdb'))
    con.execute('CREATE TABLE panel(agent_id VARCHAR,step INTEGER,state JSON,action_kind VARCHAR,action_payload JSON,action_source VARCHAR)')
    con.execute('INSERT INTO panel VALUES (?,?,?,?,?,?)',['A0001',1,json.dumps(state,ensure_ascii=False),'decide',payload,'llm'])
    con.close()


@pytest.mark.parametrize('size',[154940,300000,1000000])
def test_csv_fallback_reads_large_cells_without_truncation(tmp_path,size):
    folder,state,payload,roster=sample(tmp_path,size)
    with atomic_csv(folder/'trajectory/panel.csv') as stream:
        writer=csv.DictWriter(stream,fieldnames=['agent_id','step','state','action_payload']);writer.writeheader()
        writer.writerow(dict(agent_id='A0001',step=1,state=json.dumps(state,ensure_ascii=False),action_payload=payload))
    previous=csv.field_size_limit()
    try:
        csv.field_size_limit(131072)
        with (folder/'trajectory/panel.csv').open(encoding='utf-8-sig',newline='') as stream:
            with pytest.raises(csv.Error):list(csv.DictReader(stream))
        rows=list(iter_committed_states(folder))
        assert json.loads(rows[0]['state'])==state and rows[0]['action_payload']==payload
        write_measurements(folder,roster,BINARY_SCORE_POLICY)
        assert read_json(folder/'reports/binary_results.json')['results'][0]['believe']==1
    finally:csv.field_size_limit(previous)


def test_database_reader_ignores_broken_csv_and_preserves_large_state(tmp_path):
    folder,state,payload,roster=sample(tmp_path);database(folder,state,payload)
    (folder/'trajectory/panel.csv').write_text('broken derived file',encoding='utf-8')
    assert json.loads(next(iter_committed_states(folder))['state'])==state
    write_measurements(folder,roster,BINARY_SCORE_POLICY)
    assert read_json(folder/'reports/binary_results.json')['results'][0]['judged_n']==1


def test_streaming_export_roundtrip_keeps_full_action_payload(tmp_path):
    folder,state,payload,_=sample(tmp_path,500000);database(folder,state,payload)
    assert export_committed_panel(folder)==1
    previous=csv.field_size_limit()
    try:
        ensure_large_fields()
        with (folder/'trajectory/panel.csv').open(encoding='utf-8-sig',newline='') as stream:rows=list(csv.DictReader(stream))
        assert rows[0]['action_payload']==payload and json.loads(rows[0]['state'])==state
        assert (folder/'trajectory/panel.csv').read_bytes().startswith(b'\xef\xbb\xbf')
    finally:csv.field_size_limit(previous)


def test_atomic_export_does_not_destroy_previous_file_on_error(tmp_path):
    path=tmp_path/'report.csv';path.write_bytes(b'previous-complete')
    with pytest.raises(OSError):
        with atomic_csv(path) as stream:stream.write('incomplete');raise OSError('test file failure')
    assert path.read_bytes()==b'previous-complete' and not list(tmp_path.glob('.csv-*.tmp'))


def test_safe_field_limit_handles_platform_overflow(monkeypatch):
    import csv_io
    current=[131072];attempts=[]
    def fake(value=None):
        if value is None:return current[0]
        attempts.append(value)
        if value>1000000:raise OverflowError()
        old=current[0];current[0]=value;return old
    monkeypatch.setattr(csv_io.csv,'field_size_limit',fake)
    assert 131072<ensure_large_fields()<=1000000 and len(attempts)>1


@pytest.mark.parametrize('original_error',[None,QuotaPause('test known provider refusal')])
@pytest.mark.parametrize('kind',['csv','filesystem','keyboard'])
def test_export_failure_always_enters_recovery_preserving_simulation_reason(tmp_path,monkeypatch,original_error,kind):
    folder,state,payload,roster=sample(tmp_path,0);database(folder,state,payload)
    import measurement_report
    error={'csv':csv.Error('field larger than field limit (131072)'),
           'filesystem':PermissionError('test file busy'),'keyboard':KeyboardInterrupt()}[kind]
    def fail(*args,**kwargs):raise error
    monkeypatch.setattr(measurement_report,'write_measurements',fail)
    state={'status':'paused_quota' if original_error else 'completed_live','last_completed_tick':5,'dry_run':False}
    if original_error:state['error_type']='QuotaPause'
    with pytest.raises(RunPaused) as ex:finalize_exports(folder,roster,{},state,'openai',tmp_path/'latest.json',original_error)
    saved=read_json(folder/'status.json')
    assert saved['export_status']=='failed' and saved['last_completed_tick']==5
    assert saved['error_type']==('QuotaPause' if original_error else 'KeyboardInterrupt' if kind=='keyboard' else 'ExportPause')
    assert ex.value.error_type==saved['error_type'] and not saved['status'].startswith('completed')
    assert read_json(folder/'export_failure_diagnostic.json')['type']==type(error).__name__


def test_successful_exports_then_original_quota_pause_are_both_recorded(tmp_path):
    folder,state,payload,roster=sample(tmp_path);database(folder,state,payload)
    status=dict(status='paused_quota',error_type='QuotaPause',last_completed_tick=5,dry_run=False)
    with pytest.raises(RunPaused) as ex:finalize_exports(folder,roster,{'belief_measurement_policy':BINARY_SCORE_POLICY},status,'openai',tmp_path/'latest.json',QuotaPause('known refusal'))
    assert ex.value.error_type=='QuotaPause' and read_json(folder/'status.json')['export_status']=='complete'
    assert (folder/'trajectory/belief_measurements.csv').exists()


def test_export_only_retry_reuses_completed_simulation_without_api(tmp_path):
    folder,state,payload,roster=sample(tmp_path);database(folder,state,payload)
    status=dict(status='completed_live',last_completed_tick=1,dry_run=False)
    assert finalize_exports(folder,roster,{'belief_measurement_policy':BINARY_SCORE_POLICY},status,'openai',tmp_path/'latest.json')==folder
    assert read_json(folder/'status.json')['export_status']=='complete'


def test_quota_recovery_initial_probe_serial_preserves_other_rate_state(tmp_path):
    state=dict(effective_concurrency=2,cooldown_until=42,next_dispatch_at=45,limit_events=7,success_streak=19)
    dump(tmp_path/'rate-limit-state.json',state);dump(tmp_path/'budget.json',{'requests':1168})
    before=(tmp_path/'budget.json').read_bytes()
    result=initialize_quota_recovery_gate(tmp_path,{'max_concurrency':2})
    updated=read_json(tmp_path/'rate-limit-state.json')
    assert updated['effective_concurrency']==1 and updated['success_streak']==0
    assert all(updated[k]==state[k] for k in ('cooldown_until','next_dispatch_at','limit_events'))
    assert result['configured_ceiling']==2 and (tmp_path/'budget.json').read_bytes()==before


def test_reviewed_maintenance_resumes_without_an_extra_keypress(tmp_path):
    parent=tmp_path/'parent';dump(parent/'status.json',{'status':'paused_quota'})
    calls=[]
    supervise(SimpleNamespace(resume=str(parent),maintenance_migration_manifest='reviewed-parent'),
        lambda args:calls.append(args.resume),lambda args:None,interactive=True,
        reader=lambda p:pytest.fail('reviewed repair already authorized'))
    assert calls==[str(parent)]


def test_real_engine_export_failure_keeps_checkpoint_and_controller_menu(tmp_path,monkeypatch):
    import run,measurement_report
    from test_network_thread import setup
    cfg,_,_=setup(tmp_path/'inputs');config=tmp_path/'config.json';dump(config,cfg)
    for name,suffix in (('RESULTS','runs'),('CONFIGS','runtime/v6/configs'),('LOGS','logs')):
        monkeypatch.setattr(run,name,tmp_path/suffix)
    def fail(*args,**kwargs):raise csv.Error('test field larger than field limit (131072)')
    monkeypatch.setattr(measurement_report,'write_measurements',fail)
    args=SimpleNamespace(config=str(config),live=False,steps=1,max_requests=12200,resume=None,concurrency=None)
    prompts=[]
    result=supervise(args,run.execute,run.check_resume_compatible,interactive=True,
        reader=lambda text:prompts.append(text) or 's',output=lambda *args:None)
    assert result==0 and len(prompts)==1
    folder=Path(read_json(tmp_path/'runs/latest.json')['run_dir']);state=read_json(folder/'status.json')
    assert state['status']=='paused_export' and state['last_completed_tick']==1
    assert len(read_json(folder/'checkpoints/tick-001.json')['actions'])==582
    assert state['export_error_type']=='Error' and not list((tmp_path/'logs').glob('*/request-*.json'))


def maintenance_fixture(tmp_path):
    import run
    from format_migration import file_sha
    from maintenance_migration import protected_run_hashes
    parent=tmp_path/'parent';audit=tmp_path/'audit';code=tmp_path/'code';code.mkdir()
    (code/'run.py').write_text((run.CODE/'run.py').read_text(encoding='utf-8'),encoding='utf-8')
    old=dict(code_sha256={'run.py':'old','model.py':'same'},config={'model':'MiniMax-M3'},
        input_sha256={'case':'same'},mode='openai',upstream_commit='same',total_steps=10,numpy_version='same',audit_dir=str(audit))
    new=copy.deepcopy(old);new['code_sha256']['run.py']='new';new['code_sha256']['csv_io.py']='new'
    dump(parent/'provenance.json',old);dump(audit/'budget.json',{'requests':1168})
    dump(audit/'request-000001.json',{'raw_response':'keep'});dump(audit/'response_cache/valid.json',{'answer':'keep'})
    dump(parent/'checkpoints/tick-001.json',{'actions':'keep'})
    manifest=dict(parent_run=str(parent.resolve()),parent_provenance_sha256=file_sha(parent/'provenance.json'),
        old_code_sha256=old['code_sha256'],new_code_sha256=new['code_sha256'],
        protected_run_function_sha256=protected_run_hashes((code/'run.py').read_text(encoding='utf-8')),
        budget_sha256=file_sha(audit/'budget.json'),audit_request_sha256={'request-000001.json':file_sha(audit/'request-000001.json')},
        valid_cache_sha256={'valid.json':file_sha(audit/'response_cache/valid.json')},
        completed_checkpoint_sha256={'tick-001.json':file_sha(parent/'checkpoints/tick-001.json')})
    return old,new,parent,manifest,code


def test_maintenance_migration_accepts_only_export_recovery_changes(tmp_path):
    from maintenance_migration import validate_maintenance_migration
    old,new,parent,manifest,code=maintenance_fixture(tmp_path)
    validate_maintenance_migration(old,new,parent,manifest,code_dir=code)


@pytest.mark.parametrize('change',['budget','cache','checkpoint','scientific_code','prompt','config','population','protected_run'])
def test_maintenance_migration_rejects_changed_research_or_old_data(tmp_path,change):
    from maintenance_migration import validate_maintenance_migration
    old,new,parent,m,code=maintenance_fixture(tmp_path)
    if change=='budget':dump(Path(old['audit_dir'])/'budget.json',{'requests':0})
    elif change=='cache':dump(Path(old['audit_dir'])/'response_cache/valid.json',{'answer':'bad'})
    elif change=='checkpoint':dump(parent/'checkpoints/tick-001.json',{'actions':'bad'})
    elif change=='scientific_code':new['code_sha256']['model.py']='different';m['new_code_sha256']=new['code_sha256']
    elif change=='prompt':new['code_sha256']['llm_client.py']='different';m['new_code_sha256']=new['code_sha256']
    elif change=='config':new['config']['model']='different'
    elif change=='population':new['input_sha256']['case']='different'
    elif change=='protected_run':m['protected_run_function_sha256']['make_bundles']='bad'
    with pytest.raises(ValueError):validate_maintenance_migration(old,new,parent,m,code_dir=code)
