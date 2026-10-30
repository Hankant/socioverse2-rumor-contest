import json,threading,time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import pytest
from model import dump,read_json
from llm_client import LiveClient
from batch_resources import SharedLimiter,SharedRouter

SLOTS=('primary','backup','third','fourth')
LOWER=dict(primary=2,backup=1,third=1,fourth=1)
NORMAL=dict(primary=3,backup=1,third=1,fourth=1)


def make_router(tmp_path,now):
    limiter=SharedLimiter(tmp_path/'global.json',5)
    router=SharedRouter(tmp_path/'routing.json',lambda *a,**k:None,slots=SLOTS,
        limiter=limiter,slot_limits=LOWER,retry_interval=600,clock=lambda:now[0],fallback_active=True)
    return router,limiter


def test_live_primary_increase_keeps_all_existing_requests(tmp_path):
    dump(tmp_path/'request_controls.json',dict(max_global_concurrency=5,api_slot_concurrency=LOWER,rate_limit_fallback_active=True))
    router,limiter=make_router(tmp_path,[100.]);held=[router.acquire() for _ in range(5)]
    selected=[];ready=threading.Event()
    def extra():selected.append(router.acquire());ready.set()
    thread=threading.Thread(target=extra);thread.start()
    try:
        assert not ready.wait(.1)
        dump(tmp_path/'request_controls.json',dict(max_global_concurrency=6,api_slot_concurrency=NORMAL,rate_limit_fallback_active=False))
        assert ready.wait(3)
        limiter.next_controls_check=0
        with limiter.cv:limiter._refresh_controls()
        assert selected[0].slot=='primary' and router.active==NORMAL and limiter.ceiling==6
        assert not router.fallback_active and all(id(route) in router.leases for route in held)
    finally:
        limiter.stop.set()
        with router.cv:router.cv.notify_all()
        for route in held+selected:router.abort(route)
        thread.join(2)


def test_upgraded_key_gets_one_early_probe_and_other_deadlines_stay_fixed(tmp_path):
    now=[100.];router,limiter=make_router(tmp_path,now)
    held=[router.acquire() for _ in range(5)]
    for route in held:router.failed(route,dict(status_code=402))
    assert all(deadline==700 for deadline in router.state['blocked_until'].values())
    dump(tmp_path/'request_controls.json',dict(max_global_concurrency=6,api_slot_concurrency=NORMAL,
        rate_limit_fallback_active=False,recovery_probe_request=dict(id='upgrade-1',slots=['primary'],user_authorization='Account upgraded; continue')))
    router.next_controls_check=0;probe=router.acquire()
    assert probe.slot=='primary' and probe.probe
    assert all(router.state['blocked_until'][slot]==700 for slot in SLOTS[1:])
    ready=threading.Event();selected=[]
    def extra():selected.append(router.acquire());ready.set()
    thread=threading.Thread(target=extra);thread.start()
    try:
        assert not ready.wait(.1)
        router.succeeded(probe)
        assert ready.wait(2) and selected[0].slot=='primary' and not selected[0].probe
    finally:
        limiter.stop.set()
        with router.cv:router.cv.notify_all()
        for route in selected:router.abort(route)
        thread.join(2)
    # A later failure is not erased by re-reading the same probe command.
    limiter.stop.clear();now[0]=200
    route=router.acquire();router.failed(route,dict(status_code=402))
    with router.cv:router._refresh_controls(force=True)
    assert router.state['blocked_until']['primary']==800
    again,_=make_router(tmp_path,now)
    assert again.state['blocked_until']['primary']==800


def test_early_recovery_request_never_cancels_a_probe_inflight(tmp_path):
    now=[100.];router,_=make_router(tmp_path,now)
    route=router.acquire();router.failed(route,dict(status_code=402));now[0]=700
    probe=router.acquire();assert probe.probe
    dump(tmp_path/'request_controls.json',dict(max_global_concurrency=6,api_slot_concurrency=NORMAL,
        rate_limit_fallback_active=False,recovery_probe_request=dict(id='upgrade-2',slots=['primary'],user_authorization='Upgrade')))
    with router.cv:router._refresh_controls(force=True)
    assert 'primary' in router.probing and id(probe) in router.leases and router.active['primary']==1
    router.succeeded(probe)
    assert router.state['blocked_until']['primary']==0 and router.active['primary']==0


def bare_client(path):
    client=LiveClient.__new__(LiveClient);client.audit=path;path.mkdir(parents=True,exist_ok=True)
    return client


def test_slow_history_of_one_case_does_not_block_another_http_callback(tmp_path):
    slow=bare_client(tmp_path/'slow');other=bare_client(tmp_path/'other')
    entered=threading.Event();release=threading.Event();written=threading.Event()
    def history():entered.set();assert release.wait(3);slow._history={}
    slow._ensure_history=history
    def callback():other.event('response_body_received');written.set()
    with ThreadPoolExecutor(2) as pool:
        first=pool.submit(slow.request_history,'signature');assert entered.wait(1)
        second=pool.submit(callback)
        try:assert written.wait(1)
        finally:release.set()
        first.result();second.result()
    assert slow.ledger_lock is not other.ledger_lock


def test_same_case_http_callback_does_not_wait_for_history_ledger(tmp_path):
    client=bare_client(tmp_path/'one');written=threading.Event()
    def callback():client.event('response_body_received');written.set()
    with ThreadPoolExecutor(1) as pool:
        with client.ledger_lock:
            future=pool.submit(callback);assert written.wait(1)
        assert written.wait(1);future.result()


def test_history_index_omits_only_duplicate_prompt_text_and_preserves_audit(tmp_path):
    client=bare_client(tmp_path/'audit');path=client.audit/'request-000001.json'
    record=dict(prompt_sha256='sig',prompt='full original prompt'*10000,base_prompt='full base'*10000,
        raw_response='{"score":61}',status='response_received',request_number=1,finish_reason='stop',
        diagnostic=dict(code='saved'),actual_input_tokens=123,actual_output_tokens=45)
    dump(path,record)
    indexed=client.request_history('sig')[0][1]
    assert indexed=={k:v for k,v in record.items() if k not in ('prompt','base_prompt')}
    assert read_json(path)==record
    record['raw_response']='{"score":42}';client.save_request(path,record)
    assert client.request_history('sig')[0][1]['raw_response']=='{"score":42}'
    assert read_json(path)==record


def test_event_locator_reads_only_the_requested_original_records(tmp_path,monkeypatch):
    import llm_client
    client=bare_client(tmp_path/'audit');events=[]
    for number,sig in [(1,'one'),(2,'two'),(3,'one')]:
        dump(client.audit/f'request-{number:06d}.json',dict(prompt_sha256=sig,request_number=number,
            status='response_received',raw_response='original answer',prompt='original prompt'))
        events.append(dict(stage='request_start',request_number=number,prompt_sha256=sig))
    (client.audit/'request-events.jsonl').write_text('\n'.join(map(json.dumps,events))+'\n',encoding='utf-8')
    original=llm_client.read_json;reads=[]
    def counted(path):reads.append(Path(path).name);return original(path)
    monkeypatch.setattr(llm_client,'read_json',counted)
    assert [record['request_number'] for _,record in client.request_history('two')]==[2]
    assert reads==['request-000002.json']
    assert len(client.request_history('one'))==2 and len(reads)==3
    client.request_history('two');assert len(reads)==3


def test_partial_or_old_event_logs_fall_back_to_original_request_files(tmp_path):
    client=bare_client(tmp_path/'audit')
    dump(client.audit/'request-000001.json',dict(prompt_sha256='one',status='pending_usage_unknown',request_number=1))
    (client.audit/'request-events.jsonl').write_text('[]\n{"stage":"request_start"',encoding='utf-8')
    assert client.request_history('one')[0][1]['status']=='pending_usage_unknown'


def test_conflicting_event_locator_never_uses_an_answer_for_another_prompt(tmp_path):
    client=bare_client(tmp_path/'audit')
    dump(client.audit/'request-000001.json',dict(prompt_sha256='actual',request_number=1))
    client.event('request_start',request_number=1,prompt_sha256='wrong')
    with pytest.raises(ValueError,match='signature mismatch'):client.request_history('wrong')
