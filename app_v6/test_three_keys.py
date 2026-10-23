"""Three-slot scheduling, bounded failover, cache/budget and DPAPI tests."""
import copy
import json
import os
from concurrent.futures import ThreadPoolExecutor
import pytest
import credentials
from round_robin_router import RoundRobinKeyRouter,NoUsableKey
from llm_client import LiveClient,QuotaPause,UncertainRequest,HardBudgetPause
from run import defaults
from test_api_failover import Refusal
from test_recovery import observation,response,valid


def router(tmp_path,now=None):
    clock=now if now is not None else [0.]
    return RoundRobinKeyRouter(tmp_path/'rr.json',lambda *a,**k:None,clock=lambda:clock[0])


def client(tmp_path,monkeypatch):
    monkeypatch.setattr(credentials,'load_keys',lambda:{
        'primary':'sk-cp-test-primary','backup':'sk-cp-test-backup','third':'sk-cp-test-third'})
    monkeypatch.setattr(credentials,'vault_path',lambda:tmp_path/'vault/keys.dpapi')
    cfg={**defaults(),'api_key_mode':'windows_dpapi_failover','api_routing_policy':'round_robin_v1',
         'api_profile':'minimax_m3','model':'MiniMax-M3','base_url':credentials.MINIMAX_CN}
    return LiveClient(cfg,tmp_path/'audit')


def test_rotation_and_persisted_cursor(tmp_path):
    r=router(tmp_path)
    assert [r.acquire().slot for _ in range(7)]==['primary','backup','third']*2+['primary']
    assert router(tmp_path).acquire().slot=='backup'


def test_concurrent_selection_is_balanced_and_durable(tmp_path):
    r=router(tmp_path)
    with ThreadPoolExecutor(6) as pool:slots=list(pool.map(lambda _:r.acquire().slot,range(90)))
    assert all(slots.count(s)==30 for s in r.slots)
    assert router(tmp_path).state['next_index']==0


@pytest.mark.parametrize('diagnostic,delay',[
    ({'status_code':429},60),({'status_code':500},60),({'timeout_phase':'ConnectTimeout'},60),
    ({'status_code':401},3600),({'status_code':402},3600),({'status_code':403},3600),
    ({'status_code':429,'provider_hints':['quota_or_balance']},3600),
    ({'status_code':429,'retry_after_seconds':123},123)])
def test_failure_cooldown_and_other_slot(diagnostic,delay,tmp_path):
    now=[0.];r=router(tmp_path,now);a=r.acquire()
    assert r.failed(a,diagnostic)
    assert r.state['blocked_until']['primary']==delay
    assert [r.acquire().slot for _ in range(4)]==['backup','third','backup','third']
    now[0]=delay
    assert r.acquire().slot=='primary'


def test_all_blocked_pause_then_expiry_and_stale_success(tmp_path):
    now=[0.];r=router(tmp_path,now)
    a=r.acquire();r.acquire();r.acquire();stale=r.acquire()
    r.failed(a,{'status_code':429});r.succeeded(stale)
    assert r.state['blocked_until']['primary']==60
    r.failed(r.acquire(),{'status_code':429})
    assert not r.failed(r.acquire(),{'status_code':429})
    with pytest.raises(NoUsableKey):r.acquire()
    with pytest.raises(NoUsableKey):router(tmp_path,now).acquire()
    now[0]=60;probe=r.acquire();assert probe.probe
    r.succeeded(probe);assert r.state['blocked_until'][probe.slot]==0


def test_healthy_requests_rotate_and_cache_does_not_advance_cursor(tmp_path,monkeypatch):
    c=client(tmp_path,monkeypatch);seen=[]
    for slot,api in c.clients.items():
        def ok(_slot=slot,**kwargs):seen.append(_slot);return response(valid())
        api.chat.completions.create=ok
    ob=observation(tmp_path)
    c.decide(ob,'{当前观察}')
    c.decide(ob,'{当前观察}')
    for i in range(1,6):
        other=copy.deepcopy(ob);other.agent_id=f'A{i+2:04d}'
        c.decide(other,'{当前观察}')
    assert seen==['primary','backup','third']*2
    assert c.budget['requests']==6


def test_two_refusals_third_success_same_prompt_and_shared_budget(tmp_path,monkeypatch):
    c=client(tmp_path,monkeypatch);calls=[]
    for slot,api in c.clients.items():
        def call(_slot=slot,**kw):
            calls.append((_slot,kw))
            if _slot!='third':raise Refusal()
            return response(valid())
        api.chat.completions.create=call
    raw,_,meta=c.decide(observation(tmp_path),'{当前观察}')
    assert raw==valid() and meta['api_key_slot']=='third'
    assert [s for s,_ in calls]==['primary','backup','third']
    assert calls[0][1]==calls[1][1]==calls[2][1]
    assert c.budget['requests']==3 and c.budget['actual_input_tokens']==100
    logs='\n'.join(p.read_text(encoding='utf-8') for p in tmp_path.rglob('*.json*'))
    assert all(key not in logs for key in credentials.load_keys().values())


def test_three_refusals_stop_without_infinite_retry_or_restart_reset(tmp_path,monkeypatch):
    c=client(tmp_path,monkeypatch)
    def fail(**kw):raise Refusal()
    for api in c.clients.values():api.chat.completions.create=fail
    ob=observation(tmp_path)
    with pytest.raises(QuotaPause):c.decide(ob,'{当前观察}')
    assert c.budget['requests']==3 and not list(c.cache.glob('*.json'))
    restored=client(tmp_path,monkeypatch)
    for api in restored.clients.values():api.chat.completions.create=lambda **kw:pytest.fail('all cooling')
    with pytest.raises(QuotaPause):restored.decide(ob,'{当前观察}')
    assert restored.budget['requests']==3


def test_unknown_timeout_not_blindly_reissued_on_other_keys(tmp_path,monkeypatch):
    c=client(tmp_path,monkeypatch)
    class APITimeoutError(Exception):pass
    def fail(**kw):raise APITimeoutError()
    c.clients['primary'].chat.completions.create=fail
    for slot in ('backup','third'):
        c.clients[slot].chat.completions.create=lambda **kw:pytest.fail('unknown outcome')
    with pytest.raises(UncertainRequest):c.decide(observation(tmp_path),'{当前观察}')
    assert c.budget['requests']==1


def test_hard_budget_applies_across_three_slots(tmp_path,monkeypatch):
    c=client(tmp_path,monkeypatch);c.cfg['max_requests']=2
    def fail(**kw):raise Refusal()
    c.clients['primary'].chat.completions.create=fail
    c.clients['backup'].chat.completions.create=fail
    c.clients['third'].chat.completions.create=lambda **kw:pytest.fail('shared budget')
    with pytest.raises(HardBudgetPause):c.decide(observation(tmp_path),'{当前观察}')
    assert c.budget['requests']==2


@pytest.mark.skipif(os.name!='nt',reason='Windows CurrentUser DPAPI')
def test_three_key_vault_update_preserves_other_slots_and_blocks_duplicates(tmp_path):
    p=tmp_path/'keys.dpapi'
    credentials.save_keys('sk-cp-test-primary','sk-api-test-old-backup',path=p)
    credentials.update_key('backup','sk-cp-test-new-backup',path=p)
    credentials.update_key('third','sk-cp-test-third',path=p)
    keys=credentials.load_keys(p)
    assert keys=={'primary':'sk-cp-test-primary','backup':'sk-cp-test-new-backup','third':'sk-cp-test-third'}
    assert all(key.encode() not in p.read_bytes() for key in keys.values())
    before=p.read_bytes()
    with pytest.raises(ValueError):credentials.update_key('third',keys['backup'],path=p)
    assert p.read_bytes()==before


def test_no_content_or_model_error_masked_by_rotation(tmp_path):
    r=router(tmp_path)
    assert not r.failed(r.acquire(),{'status_code':403,'service_status_code':1026})
    assert r.state['failure_count']==dict(primary=0,backup=0,third=0)


@pytest.mark.parametrize('outcome',['abort','failed'])
def test_stale_outcome_cannot_release_new_recovery_probe(tmp_path,outcome):
    now=[0.];r=router(tmp_path,now);stale=r.acquire()
    r.failed(stale,{'status_code':429});now[0]=60
    r.acquire();r.acquire();probe=r.acquire()
    assert probe.slot=='primary' and probe.probe and 'primary' in r.probing
    if outcome=='abort':r.abort(stale)
    else:r.failed(stale,{'status_code':429})
    assert 'primary' in r.probing
    assert r.state['blocked_until']['primary']==60
