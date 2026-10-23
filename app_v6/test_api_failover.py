import copy
import json
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest
import credentials
from api_router import KeyRouter, can_switch
from llm_client import LiveClient, QuotaPause, UncertainRequest
from run import defaults
from test_recovery import observation, response, valid


class Refusal(Exception):
    def __init__(self, status=429, service=None):
        self.status_code = status
        self.body = {"base_resp": {"status_code": service}} if service is not None else None


def mock_client(tmp_path, monkeypatch):
    monkeypatch.setattr(credentials,"load_keys",lambda: {"primary":"sk-cp-unit-primary","backup":"sk-api-unit-backup"})
    monkeypatch.setattr(credentials,"vault_path",lambda: tmp_path/"vault/keys.dpapi")
    cfg={**defaults(),"api_key_mode":"windows_dpapi_failover","api_profile":"minimax_m3",
         "model":"MiniMax-M3","base_url":credentials.MINIMAX_CN}
    return LiveClient(cfg,tmp_path/"audit")


def test_primary_failure_backup_same_prompt_budget_and_cache(tmp_path,monkeypatch):
    c=mock_client(tmp_path,monkeypatch)
    calls=[]
    def fail(**kwargs):calls.append(("primary",kwargs));raise Refusal()
    def ok(**kwargs):calls.append(("backup",kwargs));return response(valid())
    c.clients["primary"].chat.completions.create=fail
    c.clients["backup"].chat.completions.create=ok
    ob=observation(tmp_path)
    answer,_,metadata=c.decide(ob,"{当前观察}")
    assert answer==valid() and [slot for slot,_ in calls]==["primary","backup"]
    assert calls[0][1]==calls[1][1]
    assert metadata["api_key_slot"]=="backup" and metadata["attempt"]==1
    assert c.budget["requests"]==2 and c.budget["output_reserved_tokens"]==1024
    assert c.budget["actual_input_tokens"]==100
    assert c.decide(ob,"{当前观察}")[2]["cached"] and len(calls)==2
    # A new process retains the one-hour deadline and valid caches.
    restored=mock_client(tmp_path,monkeypatch)
    assert restored.router.state["active_slot"]=="backup"
    assert restored.decide(ob,"{当前观察}")[2]["cached"]


@pytest.mark.parametrize("code",[1002,1004,1008,2049,2056,2062,2067,2064])
def test_http200_provider_refusal_is_not_success(tmp_path,monkeypatch,code):
    c=mock_client(tmp_path,monkeypatch)
    refused=response(valid());refused.base_resp={"status_code":code}
    c.clients["primary"].chat.completions.create=lambda **k:refused
    c.clients["backup"].chat.completions.create=lambda **k:response(valid())
    assert c.decide(observation(tmp_path),"{当前观察}")[2]["api_key_slot"]=="backup"
    assert c.budget["requests"]==2 and c.budget["actual_input_tokens"]==100


@pytest.mark.parametrize("code",[1026,1027,1039,2013,2022,2061,2068,2069])
def test_content_parameter_and_model_errors_do_not_switch(tmp_path,monkeypatch,code):
    c=mock_client(tmp_path,monkeypatch)
    def fail(**kwargs):raise Refusal(400,code)
    c.clients["primary"].chat.completions.create=fail
    c.clients["backup"].chat.completions.create=lambda **k:pytest.fail("must not mask configuration/content error")
    with pytest.raises(RuntimeError):c.decide(observation(tmp_path),"{当前观察}")
    assert c.budget["requests"]==1 and c.router.state["active_slot"]=="primary"


def test_hourly_probe_failure_then_recovery_and_stale_results(tmp_path):
    now=[100.]
    router=KeyRouter(tmp_path/"routing.json",lambda *a,**k:None,clock=lambda:now[0])
    first=router.acquire();stale=router.acquire()
    assert router.failed(first,{"status_code":429})
    assert router.state["next_primary_probe_at"]==3700.
    now[0]=150
    assert router.failed(stale,{"status_code":429})
    assert router.state["next_primary_probe_at"]==3700.
    router.succeeded(stale)
    assert router.state["active_slot"]=="backup"
    now[0]=3699.99
    assert router.acquire().slot=="backup"
    now[0]=3700
    probe=router.acquire();assert probe.probe
    assert router.acquire().slot=="backup"
    router.failed(probe,{"service_status_code":2056})
    assert router.state["next_primary_probe_at"]==7300.
    now[0]=7300
    probe=router.acquire();assert probe.probe
    router.succeeded(probe)
    assert router.acquire().slot=="primary" and router.state["next_primary_probe_at"] is None
    router.failed(stale,{"status_code":429})
    assert router.state["active_slot"]=="primary"


def test_many_threads_only_one_primary_probe(tmp_path):
    now=[0.]
    router=KeyRouter(tmp_path/"routing.json",lambda *a,**k:None,clock=lambda:now[0])
    router.failed(router.acquire(),{"status_code":401})
    now[0]=3600.
    barrier=threading.Barrier(10)
    def choose(_):barrier.wait(timeout=10);return router.acquire()
    with ThreadPoolExecutor(10) as pool:routes=list(pool.map(choose,range(10)))
    assert sum(r.probe for r in routes)==1
    assert sum(r.slot=="backup" for r in routes)==9


def test_probe_runs_real_decision_once_no_extra_probe_cost(tmp_path,monkeypatch):
    c=mock_client(tmp_path,monkeypatch)
    now=[0.];c.router.clock=lambda:now[0]
    def fail(**kwargs):raise Refusal()
    c.clients["primary"].chat.completions.create=fail
    c.clients["backup"].chat.completions.create=lambda **k:response(valid())
    ob=observation(tmp_path);c.decide(ob,"{当前观察}")
    now[0]=3600
    c.clients["primary"].chat.completions.create=lambda **k:response(valid())
    second=copy.deepcopy(ob);second.agent_id="A0003"
    meta=c.decide(second,"{当前观察}")[2]
    assert meta["primary_probe"] and meta["api_key_slot"]=="primary"
    assert c.budget["requests"]==3 and c.router.state["active_slot"]=="primary"


def test_backup_failure_pauses_no_success_cache(tmp_path,monkeypatch):
    c=mock_client(tmp_path,monkeypatch)
    def fail(**kwargs):raise Refusal()
    for client in c.clients.values():client.chat.completions.create=fail
    with pytest.raises(QuotaPause):c.decide(observation(tmp_path),"{当前观察}")
    assert c.budget["requests"]==2 and not list(c.cache.glob("*.json"))


def test_unknown_read_timeout_pauses_without_blind_backup_retry(tmp_path,monkeypatch):
    c=mock_client(tmp_path,monkeypatch)
    class APITimeoutError(Exception):pass
    def fail(**kwargs):raise APITimeoutError("secret exception text must not be recorded")
    c.clients["primary"].chat.completions.create=fail
    c.clients["backup"].chat.completions.create=lambda **k:pytest.fail("outcome unknown")
    ob=observation(tmp_path)
    with pytest.raises(UncertainRequest):c.decide(ob,"{当前观察}")
    assert c.budget["requests"]==1
    assert json.loads(next(c.audit.glob("request-*.json")).read_text(encoding="utf-8"))["status"]=="pending_usage_unknown"
    with pytest.raises(UncertainRequest):c.decide(ob,"{当前观察}")


def test_definite_connect_failure_can_switch():
    assert can_switch({"timeout_phase":"ConnectTimeout"})
    assert can_switch({"exception_chain":["APIConnectionError","ConnectError"]})
    assert not can_switch({"timeout_phase":"ReadTimeout"})
    assert not can_switch({"status_code":403,"service_status_code":1026})


def test_unknown_probe_failure_does_not_create_a_probe_storm(tmp_path):
    now=[0.]
    router=KeyRouter(tmp_path/"routing.json",lambda *a,**k:None,clock=lambda:now[0])
    router.failed(router.acquire(),{"status_code":429})
    now[0]=3600.
    assert not router.failed(router.acquire(),{"timeout_phase":"ReadTimeout"})
    assert router.state["next_primary_probe_at"]==7200.
    assert router.acquire().slot=="backup"


def test_inflight_backup_failure_can_use_already_recovered_primary(tmp_path):
    now=[0.]
    router=KeyRouter(tmp_path/"routing.json",lambda *a,**k:None,clock=lambda:now[0])
    router.failed(router.acquire(),{"status_code":429})
    backup=router.acquire()
    now[0]=3600.
    router.succeeded(router.acquire())
    assert router.failed(backup,{"status_code":429})
    assert router.acquire().slot=="primary"


def test_both_known_connect_failures_can_retry_after_restart(tmp_path,monkeypatch):
    c=mock_client(tmp_path,monkeypatch)
    class APIConnectionError(Exception):pass
    class ConnectError(Exception):pass
    def fail(**kwargs):
        try:raise ConnectError()
        except ConnectError as exc:raise APIConnectionError() from exc
    for client in c.clients.values():client.chat.completions.create=fail
    ob=observation(tmp_path)
    with pytest.raises(QuotaPause):c.decide(ob,"{当前观察}")
    resumed=mock_client(tmp_path,monkeypatch)
    resumed.clients["backup"].chat.completions.create=lambda **k:response(valid())
    assert resumed.decide(ob,"{当前观察}")[2]["api_key_slot"]=="backup"
    assert resumed.budget["requests"]==3


def test_failed_primary_does_not_reset_shared_hard_budget(tmp_path,monkeypatch):
    c=mock_client(tmp_path,monkeypatch);c.cfg["max_requests"]=1
    def fail(**kwargs):raise Refusal()
    c.clients["primary"].chat.completions.create=fail
    c.clients["backup"].chat.completions.create=lambda **k:pytest.fail("budget must still apply")
    with pytest.raises(RuntimeError,match="hard budget"):c.decide(observation(tmp_path),"{当前观察}")
    assert c.budget["requests"]==1


def test_secrets_and_raw_provider_errors_absent_from_audit(tmp_path,monkeypatch):
    c=mock_client(tmp_path,monkeypatch)
    class LeakyRefusal(Refusal):
        code="sk-cp-unit-primary"
    def fail(**kwargs):raise LeakyRefusal()
    c.clients["primary"].chat.completions.create=fail
    c.clients["backup"].chat.completions.create=lambda **k:response(valid())
    c.decide(observation(tmp_path),"{当前观察}")
    logs="\n".join(p.read_text(encoding="utf-8") for p in tmp_path.rglob("*.json*"))
    assert "sk-cp-unit-primary" not in logs and "sk-api-unit-backup" not in logs


@pytest.mark.skipif(os.name!="nt",reason="Windows CurrentUser DPAPI")
def test_dpapi_vault_roundtrip_and_tamper(tmp_path):
    path=tmp_path/"keys.dpapi"
    credentials.save_keys("sk-cp-unit-primary","sk-api-unit-backup",path=path)
    assert b"sk-cp" not in path.read_bytes() and b"sk-api" not in path.read_bytes()
    assert credentials.load_keys(path)["backup"]=="sk-api-unit-backup"
    path.write_bytes(b"invalid encrypted vault")
    with pytest.raises(ValueError,match="Cannot open MiniMax vault"):credentials.load_keys(path)


def test_saved_keys_never_sent_to_other_endpoints(monkeypatch):
    monkeypatch.setattr(credentials,"load_keys",lambda:pytest.fail("must reject endpoint before reading keys"))
    with pytest.raises(ValueError,match="restricted"):
        credentials.validate_credentials({"api_key_mode":"windows_dpapi_failover","api_profile":"minimax_m3",
                                          "base_url":"https://example.com/v1"})
