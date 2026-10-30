import threading,time
from concurrent.futures import ThreadPoolExecutor
import pytest
from batch_resources import SharedLimiter,SharedRouter
from model import dump,read_json


SLOTS=('primary','backup','third','fourth')
NORMAL=dict(zip(SLOTS,(3,1,1,1)))
LOWER=dict(zip(SLOTS,(2,1,1,1)))
FALLBACK=dict(max_global_concurrency=5,api_slot_concurrency=LOWER)


def make_router(tmp_path,now):
    path=tmp_path/'request_controls.json'
    if not path.exists():dump(path,dict(max_global_concurrency=6,api_slot_concurrency=NORMAL,rate_limit_fallback=FALLBACK,rate_limit_fallback_active=False))
    controls=read_json(path);limiter=SharedLimiter(tmp_path/'global.json')
    router=SharedRouter(tmp_path/'routing.json',lambda *a,**k:None,slots=SLOTS,
        limiter=limiter,slot_limits=controls['api_slot_concurrency'],retry_interval=600,clock=lambda:now[0],
        rate_limit_fallback=controls['rate_limit_fallback'],fallback_active=controls['rate_limit_fallback_active'])
    return router,limiter


@pytest.mark.parametrize('diagnostic',[dict(status_code=429),dict(status_code=529),
    dict(status_code=200,service_status_code=1002),dict(status_code=200,service_status_code=1045)])
def test_rate_limit_changes_both_global_and_primary_capacity_and_persists(tmp_path,diagnostic):
    now=[100.];router,limiter=make_router(tmp_path,now)
    assert router.failed(router.acquire(),diagnostic)
    assert limiter.ceiling==limiter.effective==5 and router.limits==LOWER and router.fallback_active
    controls=read_json(tmp_path/'request_controls.json')
    assert controls['max_global_concurrency']==5 and controls['api_slot_concurrency']==LOWER and controls['rate_limit_fallback_active']
    assert router.state['blocked_until']['primary']==700
    new_router,new_limiter=make_router(tmp_path,now)
    assert new_limiter.ceiling==5 and new_router.limits==LOWER and new_router.fallback_active
    assert new_router.state['blocked_until']['primary']==700


@pytest.mark.parametrize('diagnostic',[dict(status_code=500),dict(status_code=402),dict(status_code=403),
    dict(status_code=400,service_status_code=2013),dict(exception_type='APITimeoutError',timeout_phase='ReadTimeout')])
def test_non_rate_failures_do_not_activate_concurrency_fallback(tmp_path,diagnostic):
    router,limiter=make_router(tmp_path,[0.]);router.failed(router.acquire(),diagnostic)
    assert limiter.ceiling==6 and router.limits==NORMAL and not router.fallback_active


def test_fallback_keeps_existing_responses_and_never_adds_a_third_primary(tmp_path):
    now=[0.];router,limiter=make_router(tmp_path,now)
    routes=[router.acquire() for _ in range(6)]
    primary=[r for r in routes if r.slot=='primary'];assert len(primary)==3
    router.failed(primary[0],dict(status_code=429))
    assert router.active['primary']==2 and sum(router.active.values())==5
    # Existing successful outcomes remain usable even though their epoch is old.
    for route in routes:
        if route is not primary[0]:router.succeeded(route)
    assert sum(router.active.values())==0
    now[0]=600;probe=router.acquire();assert probe.probe;router.succeeded(probe)
    held=[router.acquire() for _ in range(5)]
    assert router.active==LOWER and limiter.ceiling==5
    done=threading.Event();chosen=[]
    def extra():chosen.append(router.acquire());done.set()
    thread=threading.Thread(target=extra);thread.start()
    try:
        assert not done.wait(.1)
        old=next(r for r in held if r.slot=='primary');router.succeeded(old)
        assert done.wait(2) and chosen[0].slot=='primary' and router.active==LOWER
    finally:
        for route in held:router.abort(route)
        for route in chosen:router.abort(route)
        thread.join(2)
    assert sum(router.active.values())==0


def test_recovered_key_and_success_streak_do_not_silently_restore_six(tmp_path):
    now=[0.];router,limiter=make_router(tmp_path,now)
    router.failed(router.acquire(),dict(status_code=429));now[0]=600
    router.succeeded(router.acquire());limiter.since=time.time()-70
    for _ in range(50):limiter.succeeded()
    assert limiter.ceiling==limiter.effective==5 and router.limits==LOWER
    assert read_json(tmp_path/'request_controls.json')['max_global_concurrency']==5


def test_multiple_simultaneous_rate_limits_activate_fallback_only_once(tmp_path):
    now=[0.];router,limiter=make_router(tmp_path,now);events=[];router.event=lambda stage,**kw:events.append(stage)
    routes=[router.acquire() for _ in range(6)]
    with ThreadPoolExecutor(6) as pool:list(pool.map(lambda r:router.failed(r,dict(status_code=429)),routes))
    assert events.count('api_rate_limit_fallback_activated')==1 and router.limits==LOWER and limiter.ceiling==5
    assert sum(router.active.values())==0


def test_fallback_does_not_raise_an_already_lower_global_limit(tmp_path):
    router,limiter=make_router(tmp_path,[0.]);limiter.restrict_ceiling(4)
    router.failed(router.acquire(),dict(status_code=429))
    assert limiter.ceiling==limiter.effective==4 and read_json(tmp_path/'request_controls.json')['max_global_concurrency']==4


def test_global_admission_drains_inflight_requests_before_new_five_limit(tmp_path):
    router,limiter=make_router(tmp_path,[0.]);held=threading.Event();release=threading.Event();lock=threading.Lock();inside=[]
    def occupy():
        with limiter.slot():
            with lock:
                inside.append(1)
                if len(inside)==6:held.set()
            release.wait(3)
    with ThreadPoolExecutor(6) as pool:
        futures=[pool.submit(occupy) for _ in range(6)]
        try:
            assert held.wait(2)
            router.failed(router.acquire(),dict(status_code=429))
            assert limiter.active==6 and limiter.ceiling==5
            # Draining does not cancel or discard any existing response.
        finally:release.set()
        for f in futures:f.result()
    assert limiter.active==0 and limiter.max_observed==6 and limiter.ceiling==5
