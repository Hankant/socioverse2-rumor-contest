"""All interfaces are fake. No test in this file sends an API request."""
import copy
import json
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from model import dump, read_json, digest
from recovery import (RunPaused, authorization_state, describe_pause, install_authorization,
                      pause_menu, supervise, wait_minutes)
from llm_client import LiveClient, QuotaPause, UncertainRequest, FormatAttemptsExhausted
from test_recovery import client, observation, response, valid


def fake_sdk(c, callback):
    c.client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=callback)))


def authorize(audit, unknown=()):
    install_authorization(audit, {"request_cutoff": read_json(Path(audit)/"budget.json")["requests"],
                                 "unknown_reissue": list(unknown), "action": "test_explicit_retry"})


def reader_for(*values):
    it = iter(values)
    return lambda prompt: next(it)


def paused_run(tmp_path, reason="QuotaPause", requests=7):
    from run import defaults
    folder = tmp_path/"saved"
    audit = tmp_path/"audit"
    cfg = defaults()
    dump(folder/"provenance.json", {"config": cfg, "audit_dir": str(audit),
         "config_dir": str(tmp_path/"runtime/v6/configs/old"), "total_steps": 10, "mode": "openai"})
    dump(folder/"status.json", {"status": "interrupted", "error_type": reason, "last_completed_tick": 5})
    dump(audit/"budget.json", {"requests": requests, "input_reserved_units": 12345, "output_reserved_tokens": 1234})
    return folder, audit


def test_explicit_retry_opens_bounded_window_and_preserves_all_spending(tmp_path, monkeypatch):
    c = client(tmp_path, monkeypatch)
    ob = observation(tmp_path)
    fake_sdk(c, lambda **k: response({"belief": "bad"}))
    with pytest.raises(FormatAttemptsExhausted):
        c.decide(ob, "{当前观察}")
    before = {p.name: p.read_bytes() for p in tmp_path.glob("request-*.json")}
    authorize(tmp_path)
    resumed = client(tmp_path, monkeypatch)
    fake_sdk(resumed, lambda **k: response(valid()))
    _, _, meta = resumed.decide(ob, "{当前观察}")
    assert meta["attempt"] == 1 and resumed.budget["requests"] == 5
    assert resumed.budget["output_reserved_tokens"] == 5*512
    assert all((tmp_path/name).read_bytes() == raw for name, raw in before.items())
    assert resumed.decide(ob, "{当前观察}")[2]["cached"]
    assert resumed.budget["requests"] == 5


def test_new_retry_window_remains_bounded(tmp_path, monkeypatch):
    c = client(tmp_path, monkeypatch)
    ob = observation(tmp_path)
    fake_sdk(c, lambda **k: response({"belief": "bad"}))
    with pytest.raises(FormatAttemptsExhausted):
        c.decide(ob, "{当前观察}")
    authorize(tmp_path)
    c = client(tmp_path, monkeypatch)
    fake_sdk(c, lambda **k: response({"belief": "bad"}))
    with pytest.raises(FormatAttemptsExhausted):
        c.decide(ob, "{当前观察}")
    assert c.budget["requests"] == 8
    with pytest.raises(FormatAttemptsExhausted):
        c.decide(ob, "{当前观察}")
    assert c.budget["requests"] == 8


def test_retry_clears_rate_attempt_window_without_discarding_reservations(tmp_path, monkeypatch):
    c = client(tmp_path, monkeypatch)
    c.cfg.update(rate_limit_max_retries=0, rate_limit_wait_seconds=0, rate_limit_spacing_seconds=0)
    class Limit(Exception):
        status_code = 429
    def refuse(**k):
        raise Limit()
    fake_sdk(c, refuse)
    ob = observation(tmp_path)
    with pytest.raises(QuotaPause):
        c.decide(ob, "{当前观察}")
    restored = client(tmp_path, monkeypatch)
    restored.cfg.update(c.cfg)
    fake_sdk(restored, lambda **k: pytest.fail("retry requires a human action"))
    with pytest.raises(QuotaPause):
        restored.decide(ob, "{当前观察}")
    authorize(tmp_path)
    restored = client(tmp_path, monkeypatch)
    restored.cfg.update(c.cfg)
    fake_sdk(restored, lambda **k: response(valid()))
    restored.decide(ob, "{当前观察}")
    assert restored.budget["requests"] == 2


@pytest.mark.parametrize("kind", ["truncated", "semantic"])
def test_acknowledged_bad_output_can_retry_without_altering_original(tmp_path, monkeypatch, kind):
    c = client(tmp_path, monkeypatch)
    ob = observation(tmp_path)
    bad = valid()
    if kind == "semantic":
        bad["repost"] = {"enabled": True, "target_content_id": "future", "text": ""}
    r = response(bad)
    if kind == "truncated":
        r.choices[0].finish_reason = "length"
    fake_sdk(c, lambda **k: r)
    with pytest.raises(ValueError):
        c.decide(ob, "{当前观察}")
    first = (tmp_path/"request-000001.json").read_bytes()
    authorize(tmp_path)
    c = client(tmp_path, monkeypatch)
    fake_sdk(c, lambda **k: response(valid()))
    c.decide(ob, "{当前观察}")
    assert c.budget["requests"] == 2
    assert (tmp_path/"request-000001.json").read_bytes() == first


def test_unknown_outcome_requires_specific_authorization_even_after_retry(tmp_path, monkeypatch):
    c = client(tmp_path, monkeypatch)
    ob = observation(tmp_path)
    def killed(**k):
        raise KeyboardInterrupt()
    fake_sdk(c, killed)
    with pytest.raises(KeyboardInterrupt):
        c.decide(ob, "{当前观察}")
    authorize(tmp_path)  # R authorizes bounded retry, but NEVER unknown reissue.
    c = client(tmp_path, monkeypatch)
    fake_sdk(c, lambda **k: pytest.fail("must not reissue silently"))
    with pytest.raises(UncertainRequest):
        c.decide(ob, "{当前观察}")
    record = read_json(tmp_path/"request-000001.json")
    item = {"file": "request-000001.json", "prompt_sha256": record["prompt_sha256"]}
    authorize(tmp_path, [item])
    c = client(tmp_path, monkeypatch)
    fake_sdk(c, lambda **k: response(valid()))
    c.decide(ob, "{当前观察}")
    assert c.budget["requests"] == 2
    assert read_json(tmp_path/"request-000001.json")["status"] == "pending_usage_unknown"
    assert authorization_state(tmp_path)[1] == {(item["file"], item["prompt_sha256"])}


def test_grant_rejects_changed_request_or_budget(tmp_path):
    dump(tmp_path/"budget.json", {"requests": 2})
    with pytest.raises(ValueError, match="budget changed"):
        install_authorization(tmp_path, {"request_cutoff": 1, "unknown_reissue": []})
    dump(tmp_path/"request-000002.json", {"status": "response_received", "prompt_sha256": "a"})
    with pytest.raises(ValueError, match="changed"):
        install_authorization(tmp_path, {"request_cutoff": 2,
            "unknown_reissue": [{"file": "request-000002.json", "prompt_sha256": "a"}]})


@pytest.mark.parametrize("choice", ["s", "q"])
def test_menu_save_exit(tmp_path, choice):
    folder, _ = paused_run(tmp_path)
    assert pause_menu(folder, reader=reader_for(choice), output=lambda *a: None) is None


def test_menu_eof_or_ctrl_c_saves_without_loop(tmp_path):
    folder, _ = paused_run(tmp_path)
    for exc in (EOFError, KeyboardInterrupt):
        def interrupted(prompt):
            raise exc()
        assert pause_menu(folder, reader=interrupted, output=lambda *a: None) is None


def test_menu_enter_and_wait_continue(tmp_path):
    folder, _ = paused_run(tmp_path)
    assert pause_menu(folder, reader=reader_for(""), output=lambda *a: None)["authorization"]["request_cutoff"] == 7
    waited = []
    result = pause_menu(folder, reader=reader_for("w", "300"), output=lambda *a: None,
                        waiter=lambda m, **k: waited.append(m) or True)
    assert waited == [300] and result["authorization"]["action"] == "w"


def test_menu_unknown_cannot_use_normal_retry_and_needs_full_confirmation(tmp_path):
    folder, audit = paused_run(tmp_path, "UncertainRequest")
    dump(audit/"request-000007.json", {"status": "pending_usage_unknown", "prompt_sha256": "abc",
                                       "tick": 6, "agent_id": "A0034", "request_number": 7})
    logs = []
    result = pause_menu(folder, reader=reader_for("r", "u", "yes", "u", "REISSUE"), output=logs.append)
    assert len(result["authorization"]["unknown_reissue"]) == 1
    assert any("普通继续已拦截" in x for x in logs) and any("未确认" in x for x in logs)
    assert read_json(audit/"request-000007.json")["status"] == "pending_usage_unknown"


def test_prompt_pause_requires_explicit_upward_limit(tmp_path):
    folder, _ = paused_run(tmp_path, "PromptBudgetPause")
    logs = []
    result = pause_menu(folder, reader=reader_for("r", "l", "65536", "", ""), output=logs.append)
    assert result["config"]["prompt_input_token_limit"] == 65536
    assert any("同一个执行上限" in x for x in logs)
    assert read_json(folder/"provenance.json")["config"]["prompt_input_token_limit"] == 32768


@pytest.mark.parametrize("choice", ["u", "l"])
def test_parallel_unknown_and_prompt_limit_can_be_resolved_together(tmp_path, choice):
    folder, audit = paused_run(tmp_path, "PromptBudgetPause")
    dump(audit/"request-000007.json", {"status": "pending_usage_unknown", "prompt_sha256": "abc",
                                       "tick": 6, "agent_id": "A0034", "request_number": 7})
    steps = ["u", "REISSUE", "65536", "", ""] if choice == "u" else ["l", "65536", "", "", "REISSUE"]
    result = pause_menu(folder, reader=reader_for(*steps), output=lambda *a: None)
    assert result["config"]["prompt_input_token_limit"] == 65536
    assert len(result["authorization"]["unknown_reissue"]) == 1


@pytest.mark.parametrize("bad", ["10", "invalid", "262144"])
def test_invalid_limit_does_not_start_retry(tmp_path, bad):
    folder, _ = paused_run(tmp_path, "PromptBudgetPause")
    choices = ["l", bad] + (["", ""] if bad == "262144" else []) + ["s"]
    assert pause_menu(folder, reader=reader_for(*choices), output=lambda *a: None) is None


def test_request_cap_cannot_be_reset_from_menu(tmp_path):
    from run import defaults
    folder, _ = paused_run(tmp_path, "HardBudgetPause", requests=defaults()["max_requests"])
    logs = []
    assert pause_menu(folder, reader=reader_for("r", "l", "s"), output=logs.append) is None
    assert any("不会增加请求次数" in x for x in logs)


def test_wait_countdown_is_cancellable_and_exact(tmp_path):
    now = [0.]
    def sleep(seconds):
        now[0] += seconds
    assert wait_minutes(1, output=lambda *a: None, clock=lambda: now[0], sleep=sleep)
    assert now[0] == 60
    def cancel(seconds):
        raise KeyboardInterrupt()
    assert not wait_minutes(1, output=lambda *a: None, clock=lambda: 0, sleep=cancel)


def test_noninteractive_pause_returns_code_without_reading_stdin(tmp_path):
    folder, _ = paused_run(tmp_path)
    def stop(args):
        raise RunPaused(folder, "QuotaPause")
    assert supervise(SimpleNamespace(resume=None), stop, lambda a: None, interactive=False,
                     reader=lambda p: pytest.fail("must never wait on a pipe"), output=lambda *a: None) == 2


def test_launcher_leaves_ctrl_c_to_child_and_restores_handler(monkeypatch):
    import local_cli
    import signal
    before = signal.getsignal(signal.SIGINT)
    def child(command, **kw):
        handler = signal.getsignal(signal.SIGINT)
        assert callable(handler) and handler is not before
        handler(signal.SIGINT, None)
        return 0
    monkeypatch.setattr(local_cli.subprocess, "call", child)
    assert local_cli.run_child(["fake-child"]) == 0
    assert signal.getsignal(signal.SIGINT) is before


def test_existing_pause_menu_does_not_execute_when_saved(tmp_path):
    folder, _ = paused_run(tmp_path)
    checks = []
    assert supervise(SimpleNamespace(resume=str(folder)), lambda a: pytest.fail("user chose save"),
                     lambda a: checks.append(1), interactive=True, reader=reader_for("s"), output=lambda *a: None) == 0
    assert checks == [1]


def test_incompatible_resume_fails_before_menu(tmp_path):
    def incompatible(args):
        raise ValueError("incompatible")
    with pytest.raises(ValueError, match="incompatible"):
        supervise(SimpleNamespace(resume="old"), lambda a: None, incompatible, interactive=True,
                  reader=lambda p: pytest.fail("old experiment cannot be resumed"))


def test_parallel_ctrl_c_stops_refill_and_drains_workers(tmp_path, monkeypatch):
    import threading
    from model import V4Decision
    from run import defaults, SOURCE
    released = threading.Event()
    called = []
    dec = V4Decision({**defaults(), "max_concurrency": 2}, SOURCE/"02_Prompt固定提示词.md", tmp_path, "scripted")
    dec.mode = "openai"
    dec.client = SimpleNamespace(gate=SimpleNamespace(halt=released.set))
    def serial(observations, memories):
        called.append(observations[0].agent_id)
        assert released.wait(5)
        return []
    def interrupted(*a, **kw):
        raise KeyboardInterrupt()
    dec._decide_serial = serial
    monkeypatch.setattr("concurrent.futures.wait", interrupted)
    with pytest.raises(KeyboardInterrupt):
        dec.decide_batch([SimpleNamespace(agent_id=i) for i in range(6)], {})
    assert released.is_set() and set(called) <= {0,1}


@pytest.mark.parametrize("restarted", [False, True])
def test_real_engine_two_ticks_partial_response_recovery_no_real_api(tmp_path, monkeypatch, restarted):
    """582 users, network-gated thread contract, real engine/storage, fake SDK."""
    import run
    from decision_conditions import CONDITION_LABELS
    from test_network_thread import setup
    cfg, _, _ = setup(tmp_path/"environment")
    cfg.update(contract_status="authorized_engineering_run", max_concurrency=1, max_requests=1000,
               rate_limit_max_retries=0, rate_limit_wait_seconds=0, rate_limit_spacing_seconds=0)
    # Nonadjustable defaults must match the runner; zero retry is injected into
    # the test client instead of changing the research configuration.
    for k in ("rate_limit_max_retries", "rate_limit_wait_seconds", "rate_limit_spacing_seconds"):
        cfg.pop(k)
    path = tmp_path/"input.json"
    dump(path, cfg)
    calls = []
    class Refusal(Exception):
        status_code = 401  # Known refusal pauses immediately; no network/timeout.
    def create(**kwargs):
        calls.append(kwargs)
        if len(calls) == 45:
            raise Refusal()
        prompt = kwargs["messages"][0]["content"]
        ref = re.search(r"本轮输入标识 ([0-9a-f]{16})", prompt).group(1)
        raw = dict(subjective_credibility=60, component_credibility={k:60 for k in ("funds_redirected","safety_delayed","causal_link")},
            comment={"enabled":False,"target_content_id":None,"text":""},
            repost={"enabled":False,"target_content_id":None,"text":""},
            evidence_ids=[json.loads(re.search(r'allowed_evidence_ids=(\[[^\n]*\])',prompt).group(1))[0]],
            condition_context_ref=ref,
            condition_application={k:{"affects":["credibility"],"note":"离线恢复测试固定回答，仅检查结构，不是行为结果"} for k in CONDITION_LABELS})
        return response(raw)
    monkeypatch.setattr("openai.OpenAI", lambda **kw: SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create))))
    monkeypatch.setenv("RUMOR_LLM_API_KEY", "sk-cp-mock-not-real")
    for name, suffix in (("RESULTS","runs"),("CONFIGS","runtime/v6/configs"),("LOGS","logs")):
        monkeypatch.setattr(run, name, tmp_path/suffix)
    args = SimpleNamespace(config=str(path), live=True, token_plan_run=True, max_requests=1000, steps=2,
                           resume=None, concurrency=None, cost_limit_configured=False)
    if restarted:
        with pytest.raises(RunPaused):
            run.execute(args)
        args.resume = read_json(tmp_path/"runs/latest.json")["run_dir"]
    prompts, parents = [], []
    def answer_retry(prompt):
        prompts.append(prompt)
        parents.append(Path(read_json(tmp_path/"runs/latest.json")["run_dir"]))
        return "r"
    assert supervise(args, run.execute, run.check_resume_compatible, reader=answer_retry, interactive=True) == 0
    assert len(prompts) == 1
    parent = parents[0]
    resumed = Path(read_json(tmp_path/"runs/latest.json")["run_dir"])
    assert read_json(parent/"status.json")["last_completed_tick"] == 1
    assert read_json(resumed/"status.json")["last_completed_tick"] == 2
    assert read_json(resumed/"status.json")["status"] == "completed_live"
    assert read_json(parent/"checkpoints/tick-001.json")["sha256"] == read_json(resumed/"checkpoints/tick-001.json")["sha256"]
    before, after = describe_pause(parent), describe_pause(resumed)
    metrics = read_json(resumed/"trajectory/metrics_history.json")["rows"]
    decisions=sum(r['llm_judged_n'] for r in metrics[1:])
    assert len(calls)==decisions+1
    assert before["budget"]["requests"] == 45 and after["budget"]["requests"] == decisions+1
    assert after["cached_decisions"] == decisions
    assert after["budget"]["output_reserved_tokens"] == (decisions+1)*1536
    assert after["provenance"]["resumed_from"] == str(parent)
    # Original successful/failed responses, including the partial second tick,
    # are copied byte-for-byte. Only the child receives retry authorization.
    for original in Path(before["audit"]).glob("request-*.json"):
        assert original.read_bytes() == (Path(after["audit"])/original.name).read_bytes()
    assert not (Path(before["audit"])/"recovery_authorizations.json").exists()
    assert (Path(after["audit"])/"recovery_authorizations.json").exists()
    first = read_json(resumed/"checkpoints/tick-002.json")["actions"]
    cached = [a for a in first if a["action_payload"].get("api", {}).get("cached")]
    assert len(cached) == 1
    assert metrics[-1]["llm_believe"] == metrics[-1]['llm_judged_n'] and metrics[-1]["technical_dropout_count"] == 0
    assert metrics[1]['rumor_cumulative_reach']==82 and metrics[1]['llm_judged_n']==43
    from verify_run import verify
    assert verify(resumed)['network_exposure_replay_verified']
    first_checkpoint=resumed/'checkpoints/tick-001.json'
    original=first_checkpoint.read_bytes()
    tampered=read_json(first_checkpoint)
    hidden=next(a for a in tampered['actions'] if a['action_kind']=='idle')
    visible=next(a for a in tampered['actions'] if a['action_payload'].get('observed_posts'))
    hidden['action_payload']['observed_posts']=copy.deepcopy(visible['action_payload']['observed_posts'])
    tampered['sha256']=digest(tampered['actions'])
    dump(first_checkpoint,tampered)
    try:
        with pytest.raises(AssertionError,match='network exposure'):
            verify(resumed)
    finally:
        first_checkpoint.write_bytes(original)
    incompatible = tmp_path/"incompatible"
    old = copy.deepcopy(after["provenance"])
    old["code_sha256"]["model.py"] = "an_old_research_version"
    dump(incompatible/"provenance.json", old)
    check_args = copy.copy(args)
    check_args.resume = str(incompatible)
    with pytest.raises(ValueError, match="无法直接续跑"):
        run.check_resume_compatible(check_args)
    dump(tmp_path/"offline_recovery_acceptance.json", {
        "real_api_requests":0,"mock_sdk_dispatches":len(calls),"completed_ticks":2,"agents":582,
        "replayed_tick_checksum_matches":True,"partial_tick_cache_reused":1,
        "budget_and_parent_audit_preserved":True,"condition_application_users_per_tick":[r['llm_judged_n'] for r in metrics[1:]],
        "feed_policy":cfg['feed_policy'],"first_tick_rumor_readers":82,"network_replay_verified":True,
        "process_restart_tested":restarted,"incompatible_old_code_rejected":True})
