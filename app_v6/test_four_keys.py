"""Four encrypted slots, primary insertion, cooldown migration and shared guards."""
import json
import os
from concurrent.futures import ThreadPoolExecutor
import pytest
import credentials
from round_robin_router import RoundRobinKeyRouter, NoUsableKey
from test_three_keys import client as three_client
from test_recovery import observation, response, valid
from test_api_failover import Refusal
from llm_client import LiveClient, QuotaPause, HardBudgetPause

SLOTS=('primary','backup','third','fourth')


def test_four_rotation_concurrent_balance_and_restart(tmp_path):
    path=tmp_path/'state.json'
    r=RoundRobinKeyRouter(path,lambda *a,**k:None,slots=SLOTS)
    assert [r.acquire().slot for _ in range(5)]==list(SLOTS)+['primary']
    r=RoundRobinKeyRouter(path,lambda *a,**k:None,slots=SLOTS)
    assert r.acquire().slot=='backup'
    with ThreadPoolExecutor(8) as pool:
        selected=list(pool.map(lambda _:r.acquire().slot,range(80)))
    assert all(selected.count(slot)==20 for slot in SLOTS)


def four_client(tmp_path,monkeypatch):
    c=three_client(tmp_path,monkeypatch);cfg=c.cfg;c.close()
    monkeypatch.setattr(credentials,'load_keys',lambda:{s:'sk-cp-test-'+s for s in SLOTS})
    # The first fixture initialized no routing state until a request was acquired.
    return LiveClient(cfg,tmp_path/'audit')


def test_three_refusals_fourth_success_identical_prompt_and_one_budget(tmp_path,monkeypatch):
    c=four_client(tmp_path,monkeypatch);seen=[]
    for slot,api in c.clients.items():
        def call(_slot=slot,**kw):
            seen.append((_slot,kw))
            if _slot!='fourth':raise Refusal()
            return response(valid())
        api.chat.completions.create=call
    raw,_,meta=c.decide(observation(tmp_path),'{当前观察}')
    assert raw==valid() and meta['api_key_slot']=='fourth'
    assert [x[0] for x in seen]==list(SLOTS)
    assert all(x[1]==seen[0][1] for x in seen)
    assert c.budget['requests']==4 and c.budget['actual_input_tokens']==100
    before=c.budget.copy()
    assert c.decide(observation(tmp_path),'{当前观察}')[2]['cached']
    assert c.budget==before


def test_all_four_refused_pause_without_unbounded_retry(tmp_path,monkeypatch):
    c=four_client(tmp_path,monkeypatch)
    def fail(**kw):raise Refusal()
    for api in c.clients.values():api.chat.completions.create=fail
    with pytest.raises(QuotaPause):c.decide(observation(tmp_path),'{当前观察}')
    assert c.budget['requests']==4
    with pytest.raises(NoUsableKey):c.router.acquire()


def test_fourth_does_not_bypass_total_request_budget(tmp_path,monkeypatch):
    c=four_client(tmp_path,monkeypatch);c.cfg['max_requests']=3
    def fail(**kw):raise Refusal()
    for slot in SLOTS[:3]:c.clients[slot].chat.completions.create=fail
    c.clients['fourth'].chat.completions.create=lambda **kw:pytest.fail('No new budget for fourth key')
    with pytest.raises(HardBudgetPause):c.decide(observation(tmp_path),'{当前观察}')
    assert c.budget['requests']==3


@pytest.mark.skipif(os.name!='nt',reason='CurrentUser DPAPI')
def test_prepend_primary_preserves_all_old_keys_and_remaps_cooldowns(tmp_path):
    path=tmp_path/'keys.dpapi'
    credentials.save_keys('sk-cp-test-old-primary','sk-cp-test-old-backup',third='sk-cp-test-old-third',path=path)
    old=credentials.load_keys(path);ciphertext=path.read_bytes()
    r=RoundRobinKeyRouter(tmp_path/'routing-round-robin.json',lambda *a,**k:None,clock=lambda:0.)
    r.failed(r.acquire(),{'status_code':429,'provider_hints':['quota_or_balance']})
    r.failed(r.acquire(),{'status_code':429})
    credentials.add_primary_key('sk-cp-test-new-primary',path=path)
    keys=credentials.load_keys(path)
    assert keys==dict(zip(SLOTS,['sk-cp-test-new-primary',*old.values()]))
    assert next(tmp_path.glob('keys.before-add-primary-*.dpapi')).read_bytes()==ciphertext
    assert all(key.encode() not in path.read_bytes() for key in keys.values())
    new=RoundRobinKeyRouter(tmp_path/'routing-round-robin.json',lambda *a,**k:None,slots=SLOTS,clock=lambda:0.)
    assert new.state['blocked_until']==dict(primary=0,backup=3600,third=60,fourth=0)
    assert new.acquire().slot=='primary' and new.acquire().slot=='fourth'
    state=(tmp_path/'routing-round-robin.json').read_bytes();vault=path.read_bytes()
    credentials.add_primary_key(keys['primary'],path=path)
    assert path.read_bytes()==vault and (tmp_path/'routing-round-robin.json').read_bytes()==state
    credentials.update_key('fourth','sk-cp-test-updated-fourth',path=path)
    assert credentials.load_keys(path)=={**keys,'fourth':'sk-cp-test-updated-fourth'}


@pytest.mark.skipif(os.name!='nt',reason='CurrentUser DPAPI')
def test_duplicates_and_fifth_slot_do_not_overwrite_vault(tmp_path):
    path=tmp_path/'keys.dpapi'
    credentials.save_keys('sk-cp-test-primary','sk-cp-test-backup',third='sk-cp-test-third',path=path)
    before=path.read_bytes()
    with pytest.raises(ValueError):credentials.add_primary_key('sk-cp-test-backup',path=path)
    assert path.read_bytes()==before
    credentials.add_primary_key('sk-cp-test-new-primary',path=path);before=path.read_bytes()
    with pytest.raises(ValueError):credentials.add_primary_key('sk-cp-test-fifth',path=path)
    assert path.read_bytes()==before
