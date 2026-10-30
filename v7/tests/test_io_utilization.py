import copy
import json
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import llm_client
import run
from conftest import answer, FakeClient
from llm_client import LiveClient
from model import V7Decision, read_json
from test_prompts_and_gateway import observed, template, client, response


def test_restarted_cache_hit_never_reads_original_prompt_json(setup, tmp_path, monkeypatch):
    cfg, env = setup
    ob = observed(env)
    first = client(tmp_path, monkeypatch, cfg)
    first.client.chat.completions.create = lambda **kw: response(answer(ob))
    first.decide(ob, template())
    budget = copy.deepcopy(first.budget)
    first.close()
    resumed = client(tmp_path, monkeypatch, cfg)
    original_read = llm_client.read_json
    reads = []

    def counted(path):
        reads.append(Path(path).name)
        assert not Path(path).name.startswith('request-'), 'cache hit loaded a duplicate full prompt'
        return original_read(path)

    monkeypatch.setattr(llm_client, 'read_json', counted)
    resumed.client.chat.completions.create = lambda **kw: (_ for _ in ()).throw(AssertionError('duplicate API call'))
    value, feed, meta = resumed.decide(ob, template())
    assert value == answer(ob) and meta['cached'] and resumed.budget == budget
    assert any(name.endswith('.json') for name in reads)
    resumed.close()


def test_diagnostic_events_do_not_fsync_but_close_does(tmp_path, monkeypatch):
    c = LiveClient.__new__(LiveClient)
    c.audit = tmp_path
    c.clients = {}
    calls = []
    monkeypatch.setattr(llm_client.os, 'fsync', lambda fd: calls.append(fd))
    c.event('one')
    c.event('two')
    assert calls == []
    assert [json.loads(line)['stage'] for line in (tmp_path/'request-events.jsonl').read_text().splitlines()] == ['one', 'two']
    c.close()
    assert len(calls) == 1


def test_api_gate_released_only_after_raw_response_is_durable_and_before_validation(setup, tmp_path, monkeypatch):
    cfg, env = setup
    ob = observed(env)
    c = client(tmp_path, monkeypatch, cfg)
    active = [0]

    @contextmanager
    def slot():
        active[0] += 1
        try:
            yield
        finally:
            active[0] -= 1

    c._gate = SimpleNamespace(slot=slot, failed=lambda: None, succeeded=lambda: None)

    def send(**kw):
        assert active[0] == 1
        assert read_json(c.budget_path)['requests'] == 1
        assert read_json(c.audit/'request-000001.json')['status'] == 'pending_usage_unknown'
        return response(answer(ob))

    original_validate = llm_client.parse_and_validate

    def validate(*args, **kwargs):
        assert active[0] == 0
        assert read_json(c.audit/'request-000001.json')['status'] == 'response_received'
        return original_validate(*args, **kwargs)

    c.client.chat.completions.create = send
    monkeypatch.setattr(llm_client, 'parse_and_validate', validate)
    assert c.decide(ob, template())[0] == answer(ob)
    assert c.budget['requests'] == 1
    c.close()


def test_exclusive_audit_resume_preserves_cache_budget_and_committed_actions(tmp_path, monkeypatch):
    from recovery import RunPaused
    import pytest
    for name, sub in [('RESULTS','results'),('CONFIGS','configs'),('LOGS','logs')]:
        monkeypatch.setattr(run, name, tmp_path/sub)
    monkeypatch.setattr(V7Decision, 'client_factory', FakeClient)
    monkeypatch.setattr(FakeClient, 'fail_tick', 2)
    args = SimpleNamespace(config=None, steps=2, resume=None, concurrency=None, max_requests=None,
                           execution_limit_migration=False, reuse_audit=True)
    with pytest.raises(RunPaused):
        run.execute(args, test_mode=True)
    parent = Path(read_json(run.RESULTS/'latest.json')['run_dir'])
    audit = Path(read_json(parent/'provenance.json')['audit_dir'])
    cache_before = {p.name: p.read_bytes() for p in (audit/'response_cache').glob('*.json')}
    budget_before = read_json(audit/'budget.json')
    args.resume = str(parent)
    monkeypatch.setattr(FakeClient, 'fail_tick', None)
    child = run.execute(args, test_mode=True)
    prov = read_json(child/'provenance.json')
    assert Path(prov['audit_dir']) == audit
    assert prov['audit_recovery_policy'] == 'exclusive_batch_reuse_v1'
    assert read_json(child/'checkpoints/tick-001.json') == read_json(parent/'checkpoints/tick-001.json')
    assert all((audit/'response_cache'/name).read_bytes() == value for name, value in cache_before.items())
    assert read_json(audit/'budget.json')['requests'] >= budget_before['requests']
    assert len(list(run.LOGS.iterdir())) == 1


def test_store_resource_limits_preserve_round_trip_data(tmp_path):
    from socioverse.io.duckdb_store import DuckDbTrajectoryStore
    store = DuckDbTrajectoryStore(tmp_path/'bounded.duckdb', export_parquet=False)
    run.bound_store_resources(store)
    store.open()
    assert store._con.execute("SELECT current_setting('threads')").fetchone()[0] == 1
    store._con.execute("INSERT INTO panel VALUES ('A0001',1,'{}','decide','{}','llm')")
    assert store._con.execute('SELECT agent_id,step FROM panel').fetchall() == [('A0001',1)]
    store.finalize()
    assert store._con is None


def test_all_54_jobs_can_fill_exactly_four_one_one_one_channels(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    import threading
    from batch_resources import SharedLimiter, SharedRouter
    from model import dump
    limits = dict(primary=4, backup=1, third=1, fourth=1)
    dump(tmp_path/'request_controls.json', dict(max_global_concurrency=7, api_slot_concurrency=limits))
    limiter = SharedLimiter(tmp_path/'global.json', 7)
    router = SharedRouter(tmp_path/'routing.json', lambda *a, **k: None,
                          slots=tuple(limits), limiter=limiter, slot_limits=limits)
    ready, release = threading.Event(), threading.Event()
    lock = threading.Lock()
    seen = []

    def request(number):
        with limiter.slot():
            route = router.acquire()
            with lock:
                seen.append(number)
                if len(seen) == 7:
                    ready.set()
            assert release.wait(10)
            router.succeeded(route)

    with ThreadPoolExecutor(54) as pool:
        futures = [pool.submit(request, i) for i in range(54)]
        try:
            assert ready.wait(5)
            assert router.active == limits and limiter.active == 7
        finally:
            release.set()
        for future in futures:
            future.result()
    assert len(seen) == 54 and router.peak == limits and router.peak_total == 7
    assert limiter.active == 0 and sum(router.active.values()) == 0


def test_two_disk_warmups_release_permits_before_all_54_live_jobs_finish(tmp_path, monkeypatch):
    import threading
    import time
    import batch54, batch_resources, credentials
    from model import dump
    batch = tmp_path/'batch'
    cfg = run.read_config()
    cases = {}
    for i in range(54):
        tag = f'case{i:02d}'
        folder = batch/tag
        dump(folder/'status.json', dict(status='paused_by_user', last_completed_tick=8))
        dump(folder/'provenance.json', dict(audit_dir=str(folder/'audit')))
        cases[tag] = dict(status='paused_by_user', last_completed_tick=8, run_dir=str(folder))
    dump(batch/'batch_status.json', dict(output=str(tmp_path/'output'), cases=cases))
    limiter = SimpleNamespace(ceiling=7, stop=threading.Event())
    router = SimpleNamespace(limits=dict(primary=4,backup=1,third=1,fourth=1),
                             retry_interval=600, fallback=None, fallback_active=False)
    factory = SimpleNamespace(shared_limiter=limiter, shared_router=router)
    monkeypatch.setattr(credentials, 'validate_credentials', lambda cfg: None)
    monkeypatch.setattr(batch_resources, 'client_class', lambda *a: factory)
    monkeypatch.setattr(run, 'read_config', lambda *a: cfg)
    monkeypatch.setattr(batch54, 'load_job', lambda *a: SimpleNamespace(
        main={8:[]}, progress=lambda *a: None, write=lambda *a: None))
    exporter = SimpleNamespace(poll=lambda: None, terminate=lambda: None)
    monkeypatch.setattr(batch54.subprocess, 'Popen', lambda *a,**k: exporter)
    monkeypatch.setattr(batch54.subprocess, 'run', lambda *a,**k: None)
    monkeypatch.setattr(V7Decision, 'client_factory', None)
    lock, ready = threading.Lock(), threading.Event()
    active = 0
    peak = 0
    live = []

    def execute(args, *, run_roots, progress_callback):
        nonlocal active, peak
        folder = Path(args.resume)
        with lock:
            active += 1
            peak = max(peak, active)
        time.sleep(.01)
        with lock:
            active -= 1
        progress_callback(folder, dict(status='running'), cfg, None, 8, {})
        with lock:
            live.append(folder.name)
            if len(live) == 54:
                ready.set()
        assert ready.wait(30), 'startup permits were held during the live experiment'
        dump(folder/'status.json', dict(status='completed_live',last_completed_tick=10))
        return folder

    monkeypatch.setattr(run, 'execute', execute)
    final = batch54.start(batch, dict(node='offline-placeholder'))
    assert peak == 2 and len(live) == 54
    assert final['status'] == 'completed'
    assert all(c['last_completed_tick'] == 10 for c in final['cases'].values())
