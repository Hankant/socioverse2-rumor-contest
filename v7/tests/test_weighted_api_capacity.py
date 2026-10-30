from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from collections import Counter
import threading,time
import pytest
from batch_resources import SharedLimiter,SharedRouter,ConditionGate,BatchPauseRequested
from model import dump,read_json


SLOTS=('primary','backup','third','fourth')
LIMITS=dict(zip(SLOTS,(3,1,1,1)))


def make_router(tmp_path,clock=None):
    dump(tmp_path/'request_controls.json',dict(max_global_concurrency=6))
    limiter=SharedLimiter(tmp_path/'global.json')
    router=SharedRouter(tmp_path/'routing.json',lambda *a,**k:None,slots=SLOTS,
        limiter=limiter,slot_limits=LIMITS,clock=clock,retry_interval=600)
    return router,limiter


def test_54_jobs_use_six_slots_with_exact_three_one_one_one_peak(tmp_path):
    router,limiter=make_router(tmp_path);first_six=threading.Event();release=threading.Event();lock=threading.Lock();seen=[]
    def call(i):
        with limiter.slot():
            route=router.acquire()
            with lock:
                seen.append(i)
                if len(seen)==6:first_six.set()
            assert release.wait(4)
            time.sleep(.005)
            router.succeeded(route)
    with ThreadPoolExecutor(54) as pool:
        futures=[pool.submit(call,i) for i in range(54)]
        try:
            assert first_six.wait(3)
            assert router.active==LIMITS and limiter.active==6
        finally:release.set()
        for future in futures:future.result()
    assert set(seen)==set(range(54)) and router.peak==LIMITS and router.peak_total==6
    assert all(n==0 for n in router.active.values()) and limiter.active==0


def test_sequential_requests_have_three_one_one_one_weight(tmp_path):
    router,_=make_router(tmp_path);seen=Counter()
    for _ in range(60):
        route=router.acquire();seen[route.slot]+=1;router.succeeded(route)
    assert seen==dict(primary=30,backup=10,third=10,fourth=10)


def test_one_key_rate_limit_keeps_other_keys_and_global_capacity_available(tmp_path):
    now=[100.];router,limiter=make_router(tmp_path,lambda:now[0])
    route=router.acquire();assert route.slot=='primary'
    assert router.failed(route,dict(status_code=429)) is True
    assert router.state['blocked_until']['primary']==700
    assert limiter.effective==limiter.ceiling==6
    for _ in range(12):
        route=router.acquire(exclude={'primary'});assert route.slot!='primary';router.succeeded(route)
    now[0]=700
    probe=router.acquire(exclude={'primary'});assert probe.slot=='primary' and probe.probe
    other=router.acquire();assert other.slot!='primary'
    router.succeeded(other);router.succeeded(probe)
    assert router.state['blocked_until']['primary']==0 and not router.probing


@pytest.mark.parametrize('diagnostic',[
    dict(status_code=429),dict(status_code=402),dict(status_code=503),
    dict(status_code=200,service_status_code=1002),dict(status_code=429,provider_hints=['quota_or_balance'])])
def test_switchable_failures_cool_only_failed_key_for_ten_minutes(tmp_path,diagnostic):
    now=[0.];router,_=make_router(tmp_path,lambda:now[0]);route=router.acquire()
    assert router.failed(route,diagnostic)
    assert router.state['blocked_until']==dict(primary=600.,backup=0.,third=0.,fourth=0.)
    now[0]=600;probe=router.acquire();assert probe.slot=='primary' and probe.probe
    assert router.failed(probe,diagnostic)
    assert router.state['blocked_until']['primary']==1200


def test_longer_provider_retry_after_is_respected(tmp_path):
    router,_=make_router(tmp_path,lambda:0.)
    router.failed(router.acquire(),dict(status_code=429,retry_after_seconds=1200))
    assert router.state['blocked_until']['primary']==1200


def test_all_keys_down_wait_without_new_request_and_recover_one_probe_per_key(tmp_path):
    now=[0.];router,limiter=make_router(tmp_path,lambda:now[0])
    for _ in SLOTS:assert router.failed(router.acquire(),dict(status_code=429))
    assert all(d==600 for d in router.state['blocked_until'].values())
    done=threading.Event();routes=[]
    def wait_for_key():routes.append(router.acquire());done.set()
    thread=threading.Thread(target=wait_for_key);thread.start()
    try:
        assert not done.wait(.1)
        assert router.active==dict.fromkeys(SLOTS,0)
        now[0]=600
        with router.cv:router.cv.notify_all()
        assert done.wait(2)
        assert routes[0].probe
    finally:
        if not done.is_set():limiter.stop.set()
        thread.join(2)
    router.succeeded(routes[0]);assert router.peak_total==1


def test_stale_inflight_success_cannot_cancel_new_cooldown(tmp_path):
    router,_=make_router(tmp_path,lambda:0.)
    routes=[router.acquire() for _ in range(6)]
    primary=[r for r in routes if r.slot=='primary'];assert len(primary)==3
    router.failed(primary[0],dict(status_code=429))
    router.succeeded(primary[1]);router.failed(primary[2],dict(status_code=429))
    assert router.state['blocked_until']['primary']==600 and router.state['failure_count']['primary']==1
    for route in routes:
        if route.slot!='primary':router.succeeded(route)
    assert sum(router.active.values())==0


def test_unknown_timeout_releases_capacity_without_being_blindly_retried(tmp_path):
    router,_=make_router(tmp_path)
    route=router.acquire()
    assert not router.failed(route,dict(exception_type='APITimeoutError',timeout_phase='ReadTimeout',exception_chain=['ReadTimeout']))
    assert router.state['blocked_until']['primary']==0 and sum(router.active.values())==0


def test_invalid_model_or_request_never_switches_keys(tmp_path):
    router,_=make_router(tmp_path);route=router.acquire()
    assert not router.failed(route,dict(status_code=400,service_status_code=2013))
    assert all(v==0 for v in router.state['blocked_until'].values())


def test_abort_releases_probe_and_double_release_is_safe(tmp_path):
    now=[0.];router,_=make_router(tmp_path,lambda:now[0]);router.failed(router.acquire(),dict(status_code=429))
    now[0]=600;route=router.acquire();assert route.probe
    router.abort(route);router.abort(route)
    assert not router.probing and router.active['primary']==0


def test_condition_gate_releases_lease_when_bookkeeping_raises(tmp_path):
    router,limiter=make_router(tmp_path)
    class Local:
        halted=False
        @contextmanager
        def slot(self):yield
    gate=ConditionGate(Local(),limiter,router)
    with pytest.raises(RuntimeError,match='budget'):
        with gate.slot():router.acquire();raise RuntimeError('budget')
    assert limiter.active==0 and sum(router.active.values())==0


def test_pause_interrupts_waiting_router_without_sending_new_requests(tmp_path):
    router,limiter=make_router(tmp_path,lambda:0.)
    for _ in SLOTS:router.failed(router.acquire(),dict(status_code=429))
    stopped=threading.Event()
    def waiter():
        with pytest.raises(BatchPauseRequested):router.acquire()
        stopped.set()
    thread=threading.Thread(target=waiter);thread.start()
    dump(limiter.pause_file,dict(requested=True))
    assert stopped.wait(2);thread.join(2)
    assert sum(router.active.values())==0


@pytest.mark.parametrize('limits',[dict(primary=3),dict(zip(SLOTS,(True,1,1,1))),dict(zip(SLOTS,(3,1,-1,1)))])
def test_invalid_capacities_fail_before_any_request(tmp_path,limits):
    limiter=SharedLimiter(tmp_path/'global.json')
    with pytest.raises(ValueError):SharedRouter(tmp_path/'routing.json',lambda *a,**k:None,slots=SLOTS,limiter=limiter,slot_limits=limits)
