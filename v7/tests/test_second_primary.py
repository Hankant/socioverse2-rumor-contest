"""Credential/transport regression checks; no real API requests."""
import json
import pytest
from credentials import KEY_SLOTS,save_keys,load_keys,add_second_primary,update_key,validate_credentials,MINIMAX_CN
from model import dump,read_json
from batch_resources import SharedLimiter,SharedRouter
from round_robin_router import RoundRobinKeyRouter

SLOTS=KEY_SLOTS
BASE=dict(primary=0,backup=1,third=1,fourth=1,primary2=4)


def make_router(tmp_path):
    now=[100.]
    controls=dict(max_global_concurrency=8,api_slot_concurrency=BASE,
        api_capacity_policy='elastic_failover_v1',api_floating_lane_slots=['backup','third','fourth'],
        api_spillover_max_concurrency=dict.fromkeys(SLOTS,8),api_suspended_until={'primary':259300.},
        api_slot_labels=dict(primary='Main1',primary2='Main2',backup='Backup1',third='Backup2',fourth='Backup3'))
    dump(tmp_path/'request_controls.json',controls)
    limiter=SharedLimiter(tmp_path/'global.json')
    router=SharedRouter(tmp_path/'routing.json',lambda *a,**k:None,slots=SLOTS,limiter=limiter,
        slot_limits=BASE,clock=lambda:now[0])
    return router,limiter,now


def cleanup(router,routes):
    for route in routes:router.abort(route)


def test_main2_takes_over_four_baseline_lanes_and_total_stays_eight(tmp_path):
    router,_,_=make_router(tmp_path);routes=[router.acquire() for _ in range(8)]
    try:
        assert router.active==dict(primary=0,primary2=4,backup=2,third=1,fourth=1)
        saved=read_json(router.capacity_path)
        assert saved['active_requests']==8 and saved['slot_labels']['primary2']=='Main2'
        assert saved['suspended_until']['primary']==259300.
    finally:cleanup(router,routes)


@pytest.mark.parametrize('healthy',['primary2','backup','third','fourth'])
def test_any_single_healthy_key_can_take_all_eight(tmp_path,healthy):
    router,_,_=make_router(tmp_path)
    for slot in SLOTS:
        if slot!=healthy:router.state['blocked_until'][slot]=700.
    routes=[router.acquire() for _ in range(8)]
    try:
        assert [r.slot for r in routes]==[healthy]*8
        assert sum(router.active.values())==8 and not router.active['primary']
    finally:cleanup(router,routes)


def test_main2_rate_limit_immediately_redistributes_work(tmp_path):
    router,_,_=make_router(tmp_path);held=[]
    while True:
        route=router.acquire()
        if route.slot=='primary2':break
        held.append(route)
    assert router.failed(route,dict(status_code=429))
    cleanup(router,held)
    routes=[router.acquire() for _ in range(8)]
    try:
        assert not router.active['primary2'] and not router.active['primary']
        assert sum(router.active[s] for s in ('backup','third','fourth'))==8
    finally:cleanup(router,routes)


def test_main2_probe_restores_routing_without_changing_existing_leases(tmp_path):
    router,_,now=make_router(tmp_path)
    router.state['blocked_until']['primary2']=200.
    routes=[router.acquire() for _ in range(8)]
    now[0]=200.;router.succeeded(routes.pop())
    probe=router.acquire()
    try:
        assert probe.slot=='primary2' and probe.probe
        assert sum(router.active.values())==8
        assert all(id(r) in router.leases for r in routes)
        router.succeeded(probe)
        assert router.state['blocked_until']['primary2']==0
    finally:cleanup(router,routes+[probe])


def test_suspended_main1_stays_off_even_if_explicit_probe_is_requested(tmp_path):
    router,_,_=make_router(tmp_path);router.state['blocked_until']['primary']=150.
    controls=read_json(router.limiter.controls_path)
    controls['recovery_probe_request']=dict(id='do-not-override-suspension',slots=['primary'],user_authorization='Test only')
    dump(router.limiter.controls_path,controls)
    with router.cv:router._refresh_controls(force=True)
    assert router.state['blocked_until']['primary']==150.
    routes=[router.acquire() for _ in range(8)]
    try:assert all(r.slot!='primary' for r in routes)
    finally:cleanup(router,routes)


def test_main1_can_recover_after_three_day_hold(tmp_path):
    router,_,now=make_router(tmp_path)
    router.state['blocked_until']['primary']=259300.
    now[0]=259299.;assert 'primary' not in router._available()
    now[0]=259300.;probe=router.acquire()
    assert probe.slot=='primary' and probe.probe
    router.succeeded(probe)
    assert 'primary' in router._available()


def test_five_slot_round_robin_state_survives_restart(tmp_path):
    path=tmp_path/'routing.json'
    first=RoundRobinKeyRouter(path,lambda *a,**k:None,slots=SLOTS)
    route=first.acquire();first.failed(route,dict(status_code=429))
    again=RoundRobinKeyRouter(path,lambda *a,**k:None,slots=SLOTS)
    assert again.state==first.state and again.slots==SLOTS


def test_add_main2_retains_all_old_keys_and_routing_state(tmp_path,monkeypatch):
    import credentials
    monkeypatch.setattr(credentials,'_crypt',lambda data,decrypt=False:data)
    path=tmp_path/'keys.dpapi'
    save_keys('sk-cp-fake-main1','sk-fake-backup',path,third='sk-fake-third',fourth='sk-fake-fourth')
    old=load_keys(path);routing=b'unchanged routing'
    (tmp_path/'routing-round-robin.json').write_bytes(routing)
    add_second_primary('sk-cp-fake-main2',path)
    assert load_keys(path)=={**old,'primary2':'sk-cp-fake-main2'}
    assert (tmp_path/'routing-round-robin.json').read_bytes()==routing
    backups=list(tmp_path.glob('keys.before-add-primary2-*.dpapi'))
    assert len(backups)==1 and load_keys(backups[0])==old
    update_key('backup','sk-fake-replaced',path)
    assert load_keys(path)['primary2']=='sk-cp-fake-main2'
    assert all(load_keys(path)[s]==old[s] for s in ('primary','third','fourth'))
    monkeypatch.setattr(credentials,'vault_path',lambda:path)
    validate_credentials(dict(api_key_mode='windows_dpapi_failover',api_profile='minimax_m3',base_url=MINIMAX_CN,
        api_routing_policy='round_robin_v1'))


def test_adding_duplicate_main2_never_overwrites_vault(tmp_path,monkeypatch):
    import credentials
    monkeypatch.setattr(credentials,'_crypt',lambda data,decrypt=False:data)
    path=tmp_path/'keys.dpapi'
    save_keys('sk-cp-fake-main1','sk-fake-backup',path,third='sk-fake-third',fourth='sk-fake-fourth')
    before=path.read_bytes()
    with pytest.raises(ValueError):add_second_primary('sk-cp-fake-main1',path)
    assert path.read_bytes()==before
