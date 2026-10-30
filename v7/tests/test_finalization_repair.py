from pathlib import Path
from types import SimpleNamespace
import hashlib
import pytest
import duckdb
import run
from model import V7Decision, read_json, dump
from conftest import FakeClient
from recovery import RunPaused


def test_failed_finalization_closes_store_and_never_creates_metrics_twice():
    calls=[]
    class Store:
        _con=None
        def open(self):self._con=duckdb.connect(':memory:')
        def finalize(self):
            calls.append('finalize')
            self._con.execute('CREATE TABLE metrics(step INTEGER)')
            raise duckdb.OutOfMemoryException('Injected export allocation failure')
    s=Store();run.bound_store_resources(s);s.open()
    with pytest.raises(duckdb.OutOfMemoryException):s.finalize()
    assert s._con is None
    s.finalize()
    assert calls==['finalize']


@pytest.mark.parametrize('partial',[False,True])
def test_existing_exports_repair_never_calls_api_or_changes_budget_or_database(tmp_path,monkeypatch,partial):
    for key,sub in [('RESULTS','runs'),('CONFIGS','configs'),('LOGS','audit')]:monkeypatch.setattr(run,key,tmp_path/sub)
    monkeypatch.setattr(V7Decision,'client_factory',FakeClient)
    monkeypatch.setattr(FakeClient,'fail_tick',2 if partial else None)
    args=SimpleNamespace(config=None,steps=2,resume=None,concurrency=None,max_requests=None,execution_limit_migration=False)
    if partial:
        with pytest.raises(RunPaused):run.execute(args,test_mode=True)
    else:run.execute(args,test_mode=True)
    folder=Path(read_json(run.RESULTS/'latest.json')['run_dir']);prov=read_json(folder/'provenance.json');audit=Path(prov['audit_dir'])
    state=read_json(folder/'status.json')
    state.update(status='paused_unknown_request' if partial else 'interrupted',error_type='UncertainRequest' if partial else 'OutOfMemoryException')
    state.pop('export_status',None);dump(folder/'status.json',state)
    budget=(audit/'budget.json').read_bytes();database=folder/'trajectory/study.duckdb'
    dbhash=hashlib.sha256(database.read_bytes()).hexdigest()
    monkeypatch.setattr(V7Decision,'client_factory',lambda *a,**k:pytest.fail('repair constructed an API client'))
    result=run.repair_saved_exports(folder)
    assert result['status']==('paused_unknown_request' if partial else 'completed_test')
    assert result['last_completed_tick']==(1 if partial else 2) and result['export_status']=='complete'
    assert (audit/'budget.json').read_bytes()==budget
    assert hashlib.sha256(database.read_bytes()).hexdigest()==dbhash
    assert read_json(folder/'export_repair.json')['api_requests']==0
    if not partial:assert 'error_type' not in result


def test_secondary_catalog_failure_never_masks_original_simulation_error(tmp_path,monkeypatch):
    for key,sub in [('RESULTS','runs'),('CONFIGS','configs'),('LOGS','audit')]:monkeypatch.setattr(run,key,tmp_path/sub)
    monkeypatch.setattr(V7Decision,'client_factory',FakeClient);monkeypatch.setattr(FakeClient,'fail_tick',2)
    def broken_cleanup(store):
        def finalize():raise duckdb.CatalogException('Injected second metrics creation')
        store.finalize=finalize
    monkeypatch.setattr(run,'bound_store_resources',broken_cleanup)
    args=SimpleNamespace(config=None,steps=2,resume=None,concurrency=None,max_requests=None,execution_limit_migration=False)
    with pytest.raises(RunPaused):run.execute(args,test_mode=True)
    folder=Path(read_json(run.RESULTS/'latest.json')['run_dir']);status=read_json(folder/'status.json')
    assert status['error_type']=='RuntimeError' and status['export_status']=='complete'
    assert read_json(folder/'cleanup_failure_diagnostic.json')['error_type']=='CatalogException'


def test_incomplete_batch_returns_nonzero_exit_code(tmp_path,monkeypatch):
    import batch54,sys
    monkeypatch.setattr(run,'CODE',tmp_path)
    # This test covers controller exit codes, independent of local runtime
    # configuration and the Windows-only process-lock implementation.
    monkeypatch.setattr(batch54,'read_json',lambda *a: {})
    monkeypatch.setitem(sys.modules,'msvcrt',SimpleNamespace(
        LK_NBLCK=1,LK_UNLCK=2,locking=lambda *a: None))
    monkeypatch.setattr(batch54,'start',lambda *a:dict(status='needs_attention'))
    monkeypatch.setattr(sys,'argv',['batch54','--batch',str(tmp_path)])
    assert batch54.main()==2
