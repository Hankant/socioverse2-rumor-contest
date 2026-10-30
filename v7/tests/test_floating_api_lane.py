"""One additional real request rotates across available secondary keys."""
from concurrent.futures import ThreadPoolExecutor
import threading,time
import pytest
from model import dump,read_json
from batch_resources import SharedLimiter,SharedRouter

SLOTS=('primary','backup','third','fourth')
SECONDARIES=list(SLOTS[1:])
BASE=dict(zip(SLOTS,(4,1,1,1)))

def make_router(tmp_path):
    now=[100.];events=[]
    controls=dict(max_global_concurrency=8,api_slot_concurrency=BASE,
        api_capacity_policy='elastic_failover_v1',
        api_spillover_max_concurrency=dict.fromkeys(SLOTS,8),api_floating_lane_slots=SECONDARIES)
    dump(tmp_path/'request_controls.json',controls)
    limiter=SharedLimiter(tmp_path/'global.json')
    router=SharedRouter(tmp_path/'routing.json',lambda stage,**kw:events.append((stage,kw)),
        slots=SLOTS,limiter=limiter,slot_limits=BASE,clock=lambda:now[0],retry_interval=600)
    return router,limiter,now,events

def release_all(router):
    for route in list(router.leases.values()):router.abort(route)

def refuse(router,slot):
    held=[]
    while True:
        route=router.acquire()
        if route.slot==slot:router.failed(route,dict(status_code=429));break
        held.append(route)
    for route in held:router.abort(route)

def test_extra_lane_rotates_in_order_after_each_completed_request(tmp_path):
    router,_,_,events=make_router(tmp_path)
    for _ in range(8):router.acquire()
    seen=[]
    try:
        for _ in range(9):
            route=router.leases[router.floating_lease];seen.append(route.slot)
            assert router.active['primary']==4 and sum(router.active.values())==8
            assert sum(max(0,router.active[s]-BASE[s]) for s in SLOTS)==1
            router.succeeded(route);router.acquire()
        assert seen==SECONDARIES*3
        assert all(not info['fallback'] for stage,info in events if stage=='api_floating_lane_acquired')
    finally:release_all(router)

def test_base_request_finishing_does_not_create_a_second_floating_worker(tmp_path):
    router,_,_,_=make_router(tmp_path)
    for _ in range(8):router.acquire()
    floating=router.leases[router.floating_lease]
    normal=next(r for r in router.leases.values() if r.slot==floating.slot and r is not floating)
    router.succeeded(normal);replacement=router.acquire()
    try:
        assert replacement.slot==floating.slot
        assert router.floating_lease==id(floating)
        assert router.active==dict(primary=4,backup=2,third=1,fourth=1)
        router.succeeded(floating);new_float=router.acquire()
        assert router.floating_lease==id(new_float) and new_float.slot=='third'
    finally:release_all(router)

@pytest.mark.parametrize('failed',SECONDARIES)
def test_rotating_lane_skips_each_cooling_secondary_and_retains_eight_requests(tmp_path,failed):
    router,_,_,_=make_router(tmp_path);refuse(router,failed)
    for _ in range(8):router.acquire()
    seen=[]
    try:
        for _ in range(6):
            route=router.leases[router.floating_lease];seen.append(route.slot)
            assert failed not in [r.slot for r in router.leases.values()]
            assert router.active['primary']==5 and sum(router.active.values())==8
            router.succeeded(route);router.acquire()
        expected=[s for s in SECONDARIES if s!=failed]
        assert all(s in expected for s in seen) and set(seen)==set(expected)
        assert all(a!=b for a,b in zip(seen,seen[1:]))
    finally:release_all(router)

def test_all_secondary_keys_down_move_the_extra_lane_to_primary(tmp_path):
    router,_,_,events=make_router(tmp_path)
    for slot in SECONDARIES:refuse(router,slot)
    for _ in range(8):router.acquire()
    try:
        assert router.active==dict(primary=8,backup=0,third=0,fourth=0)
        assert router.leases[router.floating_lease].slot=='primary'
        assert [i for s,i in events if s=='api_floating_lane_acquired'][-1]['fallback'] is True
    finally:release_all(router)

def test_failed_floating_request_releases_its_lane_and_moves_to_next_healthy_key(tmp_path):
    router,_,_,_=make_router(tmp_path)
    for _ in range(8):router.acquire()
    route=router.leases[router.floating_lease];assert route.slot=='backup'
    router.failed(route,dict(status_code=429))
    for old in list(router.leases.values()):
        if old.slot=='backup':router.abort(old)
    router.acquire();router.acquire()
    try:
        assert router.leases[router.floating_lease].slot=='third'
        assert router.active==dict(primary=5,backup=0,third=2,fourth=1)
    finally:release_all(router)

def test_recovery_probe_keeps_one_lane_until_provider_success(tmp_path):
    router,_,now,_=make_router(tmp_path);refuse(router,'backup')
    for _ in range(8):router.acquire()
    now[0]=700
    normal=next(r for r in router.leases.values() if r.slot=='primary')
    router.succeeded(normal);probe=router.acquire()
    try:
        assert probe.slot=='backup' and probe.probe and router.active['backup']==1
        assert router.leases[router.floating_lease].slot=='third'
        router.succeeded(probe);restored=router.acquire()
        assert restored.slot=='backup' and not restored.probe
        assert router.active==dict(primary=4,backup=1,third=2,fourth=1)
    finally:release_all(router)

def test_hot_enable_preserves_all_seven_existing_leases(tmp_path):
    router,limiter,_,_=make_router(tmp_path)
    controls=read_json(limiter.controls_path)
    controls.update(max_global_concurrency=7,api_floating_lane_slots=[])
    dump(limiter.controls_path,controls);router.next_controls_check=0
    limiter.next_controls_check=0
    with limiter.cv:limiter._refresh_controls()
    held=[router.acquire() for _ in range(7)]
    controls.update(max_global_concurrency=8,api_floating_lane_slots=SECONDARIES)
    dump(limiter.controls_path,controls);router.next_controls_check=0;limiter.next_controls_check=0
    with limiter.cv:limiter._refresh_controls()
    extra=router.acquire()
    try:
        assert all(id(r)in router.leases for r in held)
        assert router.floating_lease==id(extra) and extra.slot in SECONDARIES
        assert sum(router.active.values())==8
    finally:release_all(router)

def test_54_workers_share_eight_lanes_without_ninth_dispatch(tmp_path):
    router,limiter,_,_=make_router(tmp_path);full=threading.Event();release=threading.Event();done=[]
    lock=threading.Lock()
    def work(index):
        with limiter.slot():
            route=router.acquire()
            if sum(router.active.values())==8:full.set()
            assert release.wait(4)
            time.sleep(.003);router.succeeded(route)
        with lock:done.append(index)
    with ThreadPoolExecutor(54) as pool:
        futures=[pool.submit(work,i) for i in range(54)]
        try:
            assert full.wait(3)
            assert limiter.active==8 and sum(router.active.values())==8
        finally:release.set()
        for f in futures:f.result()
    assert len(done)==54 and router.peak_total==limiter.max_observed==8
    assert not router.leases and router.floating_lease is None

@pytest.mark.parametrize('bad',[True,'backup',['backup','backup'],['missing'],[{}]])
def test_invalid_rotation_is_rejected_before_dispatch(tmp_path,bad):
    router,limiter,_,_=make_router(tmp_path);controls=read_json(limiter.controls_path)
    controls['api_floating_lane_slots']=bad;dump(limiter.controls_path,controls);router.next_controls_check=0
    with pytest.raises(ValueError):router.acquire()
    assert sum(router.active.values())==0
