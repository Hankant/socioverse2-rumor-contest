"""Transport-only regression tests; no real API requests or fabricated results."""
from concurrent.futures import ThreadPoolExecutor
import threading,time
import pytest
from model import dump,read_json
from batch_resources import SharedLimiter,SharedRouter,BatchPauseRequested

SLOTS=('primary','backup','third','fourth')
BASE=dict(zip(SLOTS,(4,1,1,1)))

def make_router(tmp_path):
    now=[100.]
    controls=dict(max_global_concurrency=7,api_slot_concurrency=BASE,
        api_capacity_policy='elastic_failover_v1',
        api_spillover_max_concurrency=dict.fromkeys(SLOTS,7))
    dump(tmp_path/'request_controls.json',controls)
    limiter=SharedLimiter(tmp_path/'global.json')
    router=SharedRouter(tmp_path/'routing.json',lambda *a,**k:None,slots=SLOTS,
        limiter=limiter,slot_limits=BASE,clock=lambda:now[0],retry_interval=600)
    return router,limiter,now

def refuse(router,slot,diagnostic=None):
    held=[]
    for _ in range(7):
        route=router.acquire()
        if route.slot==slot:
            router.failed(route,diagnostic or dict(status_code=429))
            break
        held.append(route)
    else:pytest.fail('Could not obtain requested healthy key')
    for route in held:router.abort(route)

def cleanup(router,routes):
    for route in routes:router.abort(route)

def test_all_healthy_keep_four_one_one_one(tmp_path):
    router,_,_=make_router(tmp_path)
    routes=[router.acquire() for _ in range(7)]
    try:assert router.active==BASE
    finally:cleanup(router,routes)

@pytest.mark.parametrize('failed',['backup','third','fourth'])
def test_failed_secondary_lane_moves_to_primary_without_changing_global_cap(tmp_path,failed):
    router,_,_=make_router(tmp_path);refuse(router,failed)
    routes=[router.acquire() for _ in range(7)]
    try:
        assert router.active=={**BASE,'primary':5,failed:0}
        assert sum(router.active.values())==7
        telemetry=read_json(router.capacity_path)
        assert telemetry['effective_slot_limits']==router.active
        assert telemetry['slot_limits']==BASE
    finally:cleanup(router,routes)

def test_only_primary_available_can_carry_all_seven(tmp_path):
    router,_,_=make_router(tmp_path)
    for slot in SLOTS[1:]:refuse(router,slot)
    routes=[router.acquire() for _ in range(7)]
    try:assert [r.slot for r in routes]==['primary']*7
    finally:cleanup(router,routes)

def test_primary_failure_moves_work_to_healthy_secondaries_and_can_fail_over_again(tmp_path):
    router,_,_=make_router(tmp_path);refuse(router,'primary')
    routes=[router.acquire() for _ in range(7)]
    assert router.active==dict(primary=0,backup=5,third=1,fourth=1)
    cleanup(router,routes);refuse(router,'backup')
    routes=[router.acquire() for _ in range(7)]
    try:assert router.active==dict(primary=0,backup=0,third=6,fourth=1)
    finally:cleanup(router,routes)

@pytest.mark.parametrize('probe_succeeds',[True,False])
def test_recovery_probes_once_and_restores_base_or_returns_borrowed_lane(tmp_path,probe_succeeds):
    router,limiter,now=make_router(tmp_path);refuse(router,'backup')
    held=[router.acquire() for _ in range(7)]
    assert router.active['primary']==5
    now[0]=700.;selected=[];ready=threading.Event()
    def waiting():selected.append(router.acquire());ready.set()
    thread=threading.Thread(target=waiting);thread.start()
    try:
        assert not ready.wait(.1), 'Recovery must not add an eighth request'
        loan=next(r for r in held if r.slot=='primary')
        router.succeeded(loan)
        assert ready.wait(2)
        probe=selected[0]
        assert probe.slot=='backup' and probe.probe
        assert router.active==BASE
        assert all(id(r)in router.leases for r in held if r is not loan)
        if probe_succeeds:
            router.succeeded(probe)
            assert router.state['blocked_until']['backup']==0
            normal=router.acquire();held.append(normal)
            assert normal.slot=='backup' and not normal.probe and router.active==BASE
        else:
            router.failed(probe,dict(status_code=429))
            replacement=router.acquire();held.append(replacement)
            assert replacement.slot=='primary' and router.active['primary']==5
            assert router.state['blocked_until']['backup']==1300
    finally:
        limiter.stop.set()
        with router.cv:router.cv.notify_all()
        thread.join(2);cleanup(router,held+selected)

def test_a_probing_primary_does_not_get_extra_requests_before_success(tmp_path):
    router,_,now=make_router(tmp_path);refuse(router,'primary')
    held=[router.acquire() for _ in range(7)];now[0]=700
    release=next(r for r in held if r.slot=='backup');router.succeeded(release)
    probe=router.acquire();assert probe.slot=='primary' and probe.probe
    release2=next(r for r in held if r.slot=='backup' and r is not release);router.succeeded(release2)
    other=router.acquire();held.append(other)
    assert other.slot!='primary' and router.active['primary']==1
    router.succeeded(probe)
    release3=next(r for r in held if r.slot=='backup' and id(r)in router.leases)
    router.succeeded(release3);restored=router.acquire();held.append(restored)
    assert restored.slot=='primary' and not restored.probe
    cleanup(router,held)

def test_54_workers_keep_seven_actual_requests_during_secondary_cooldown(tmp_path):
    router,limiter,_=make_router(tmp_path);refuse(router,'backup')
    full=threading.Event();release=threading.Event();lock=threading.Lock();done=[]
    def call(index):
        with limiter.slot():
            route=router.acquire()
            if sum(router.active.values())==7:full.set()
            assert release.wait(4)
            time.sleep(.003)
            router.succeeded(route)
        with lock:done.append(index)
    with ThreadPoolExecutor(54) as pool:
        futures=[pool.submit(call,i) for i in range(54)]
        try:
            assert full.wait(3)
            assert router.active==dict(primary=5,backup=0,third=1,fourth=1)
            assert limiter.active==7
        finally:release.set()
        for f in futures:f.result()
    assert sorted(done)==list(range(54))
    assert router.peak_total==7 and limiter.max_observed==7
    assert not sum(router.active.values()) and limiter.active==0

def test_all_keys_down_wait_without_ignoring_provider_deadline(tmp_path):
    router,limiter,now=make_router(tmp_path)
    for slot in SLOTS:refuse(router,slot,dict(status_code=429,retry_after_seconds=1200))
    stopped=threading.Event()
    def waiter():
        with pytest.raises(BatchPauseRequested):router.acquire()
        stopped.set()
    thread=threading.Thread(target=waiter);thread.start()
    assert not stopped.wait(.1)
    assert router.state['blocked_until']==dict.fromkeys(SLOTS,1300)
    assert sum(router.active.values())==0
    limiter.stop.set()
    with router.cv:router.cv.notify_all()
    assert stopped.wait(2);thread.join(2)

def test_lower_explicit_spillover_cap_is_respected(tmp_path):
    router,_,_=make_router(tmp_path)
    controls=read_json(router.limiter.controls_path)
    controls['api_spillover_max_concurrency']['primary']=4
    dump(router.limiter.controls_path,controls)
    router.next_controls_check=0;refuse(router,'backup')
    held=[router.acquire() for _ in range(7)]
    try:assert router.active==dict(primary=4,backup=0,third=2,fourth=1)
    finally:cleanup(router,held)

@pytest.mark.parametrize('changes',[
    dict(api_capacity_policy='unbounded'),
    dict(api_spillover_max_concurrency={'primary':7}),
    dict(api_spillover_max_concurrency=dict.fromkeys(SLOTS,True)),
    dict(api_spillover_max_concurrency={**dict.fromkeys(SLOTS,7),'primary':3}),
])
def test_invalid_policy_or_ceiling_cannot_dispatch(tmp_path,changes):
    router,_,_=make_router(tmp_path);controls=read_json(router.limiter.controls_path)
    controls.update(changes);dump(router.limiter.controls_path,controls)
    router.next_controls_check=0
    with pytest.raises(ValueError):router.acquire()
    assert sum(router.active.values())==0
