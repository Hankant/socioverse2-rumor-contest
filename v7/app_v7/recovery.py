"""Human-controlled recovery. Never reset spending or invent a missing decision."""
from __future__ import annotations

import copy
import json
import math
from datetime import datetime, timezone
from pathlib import Path
import sys
import time

from model import dump, read_json

RECOVERY_VERSION = "interactive-recovery-v1"
LIMITS = ("prompt_input_token_limit", "max_input_reserved_units", "max_output_reserved_tokens")


class RunPaused(RuntimeError):
    def __init__(self, run_dir, error_type):
        self.run_dir, self.error_type = Path(run_dir), error_type
        super().__init__(f"Run interrupted ({error_type}); checkpoint and request audit preserved")


def authorization_state(audit):
    path = Path(audit) / "recovery_authorizations.json"
    entries = read_json(path)["entries"] if path.exists() else []
    # Automatic reconnect resets transport refusals, never output-format attempts.
    cutoff = max((e["request_cutoff"] for e in entries if e.get('action') != 'auto_retry_120s'), default=0)
    unknown = {(r["file"], r["prompt_sha256"]) for e in entries for r in e["unknown_reissue"]}
    return cutoff, unknown


def transport_authorization_cutoff(audit):
    path = Path(audit)/'recovery_authorizations.json'
    entries = read_json(path)['entries'] if path.exists() else []
    return max((e['request_cutoff'] for e in entries), default=0)


def initialize_quota_recovery_gate(audit,cfg):
    """Serial first live probe; retain configured ceiling and all spending."""
    path=Path(audit)/'rate-limit-state.json'
    state=read_json(path) if path.exists() else {'effective_concurrency':cfg.get('max_concurrency',1),
        'cooldown_until':0.,'next_dispatch_at':0.,'limit_events':0}
    old=state['effective_concurrency'];state.update(effective_concurrency=1,success_streak=0,recovery_since=time.time())
    dump(path,state)
    return {'previous_effective_concurrency':old,'initial_effective_concurrency':1,
        'configured_ceiling':cfg.get('max_concurrency',1),'reason':'Do not send a parallel request to the known-refused backup while the first primary probe is in flight; normal adaptive recovery may restore concurrency.'}


def install_authorization(audit, decision):
    """Called only in a NEW recovery directory, after copying the original audit."""
    audit = Path(audit)
    budget = read_json(audit / "budget.json") if (audit / "budget.json").exists() else {"requests": 0}
    if decision.get('action') == 'auto_retry_120s' and decision['unknown_reissue']:
        raise ValueError('Automatic reconnect cannot authorize unknown requests')
    if decision["request_cutoff"] != budget["requests"]:
        raise ValueError("Recovery budget changed after the menu; inspect before retrying")
    for item in decision["unknown_reissue"]:
        if Path(item["file"]).name != item["file"]:
            raise ValueError("Invalid recovery request path")
        record = read_json(audit / item["file"])
        if record.get("status") != "pending_usage_unknown" or record.get("prompt_sha256") != item["prompt_sha256"]:
            raise ValueError("Unknown request changed after explicit reissue approval")
    path = audit / "recovery_authorizations.json"
    data = read_json(path) if path.exists() else {"version": RECOVERY_VERSION, "entries": []}
    data["entries"].append({**decision, "time_utc": datetime.now(timezone.utc).isoformat(),
                            "note": "Fresh bounded retry window; all original records and reservations retained"})
    dump(path, data)


def describe_pause(run_dir):
    folder = Path(run_dir)
    prov = read_json(folder / "provenance.json")
    status = read_json(folder / "status.json")
    audit = Path(prov["audit_dir"])
    budget = read_json(audit / "budget.json") if (audit / "budget.json").exists() else {"requests": 0}
    _, acknowledged = authorization_state(audit)
    unknown, recent = [], None
    for path in sorted(audit.glob("request-*.json")):
        r = read_json(path)
        recent = {k: r.get(k) for k in ("request_number", "agent_id", "tick", "status", "finish_reason", "diagnostic","api_key_slot")}
        sig = r.get("prompt_sha256")
        if (r.get("status") == "pending_usage_unknown" and (path.name, sig) not in acknowledged
                and not (audit / "response_cache" / f"{sig}.json").exists()):
            unknown.append({"file": path.name, "prompt_sha256": sig, "tick": r.get("tick"),
                            "agent_id": r.get("agent_id"), "request_number": r.get("request_number")})
    return {"run_dir": str(folder), "provenance": prov, "status": status, "audit": str(audit),
            "budget": budget, "unknown": unknown, "recent_request": recent,
            "cached_decisions": sum(1 for _ in (audit / "response_cache").glob("*.json"))}


def print_pause(info, output=print):
    state, cfg, b = info["status"], info["provenance"]["config"], info["budget"]
    output("\n========== 已暂停并保存，等待你的操作 ==========")
    output(f"完整轮次：{state.get('last_completed_tick', 0)}/{info['provenance']['total_steps']}；"
           f"原因：{state.get('error_type', state['status'])}")
    hints = {
        "QuotaPause": "接口暂时不可用：可能是429限流、529服务异常或额度问题，不能仅凭此状态判断额度耗尽；自动重连开启时每2分钟检查重试，预算保持不变。",
        "ExportPause": "模拟结果已保存，结果文件导出未完成。修复本地导出或文件占用问题后R重试，完整检查点会重放，不会重付已完成决策。",
        "PromptBudgetPause": "完整评论与记忆超过输入上限。直接重试不会解决；可选择 L 明确提高执行上限，或保存退出。",
        "HardBudgetPause": "累计请求或 token 预留预算到达上限。直接重试不会解决；L 可提高 token 预算，请求次数上限保持不变。",
        "DecisionConditionsPause": "输出未满足逐项条件要求。R 可额外开启一组有上限的生成重试；不会把失败回答当作实验结果。",
        "OutputContractPause": "输出仍未通过校验：可重试的情况已进行有限自动重试，供应商明确拒绝则直接暂停。查看下面的具体用户和原因；R仅开启额外一组有限重试，不自动增加预算。",
        "UncertainRequest": "请求可能已发送并计费，但没有完整响应。只有 U 加明确确认才能重发这些请求。",
        "KeyboardInterrupt": "已接收到 Ctrl+C。正在运行的请求已收尾；已成功响应可以复用。",
        "ValueError": "输出可能为空、截断或未通过校验。可检查日志后 R 重试；若反复出现，应先检查输出上限或代码。",
    }
    output(hints.get(state.get("error_type"), "请检查本地诊断或修复环境后选择 R；若修改了代码或实验设定，应新开实验。"))
    output(f"累计请求：{b.get('requests', 0)}/{cfg['max_requests']}；已缓存成功决策：{info['cached_decisions']}")
    output(f"输入预留：{b.get('input_reserved_units', 0)}/{cfg['max_input_reserved_units']}；"
           f"输出预留：{b.get('output_reserved_tokens', 0)}/{cfg['max_output_reserved_tokens']}")
    if state.get("error_details"):
        output(str(state["error_details"]))
    if state.get('export_status')=='failed':
        output('另有结果导出错误：'+state.get('export_error_type','unknown')+'；原始暂停原因保留，检查点与API缓存仍可恢复。')
    recent = info.get("recent_request") or {}
    diag = recent.get("diagnostic") or {}
    if diag.get("status_code") in (401, 403):
        slot=recent.get('api_key_slot')
        command=('scripts/manage_api_keys.py set-slot --slot '+slot) if slot in ('primary','backup','third','fourth') else 'scripts/manage_api_keys.py set'
        output("最近接口返回认证/权限拒绝。可在另一终端运行 "+command+" 更新本地密钥，然后返回这里 R；密钥不填在菜单里。")
    if recent.get("finish_reason") == "length":
        output("最近响应被输出上限截断。R 只重新生成；若持续出现，需要另外检查输出上限与提示词，L 不修改单次输出上限。")
    output(f"结果目录：{info['run_dir']}")
    output(f"请求日志：{info['audit']}")
    if info["unknown"]:
        output(f"尚有 {len(info['unknown'])} 个结果未知的请求；普通 R/回车不会重发它们：")
        for r in info["unknown"]:
            output(f"  {r['file']}：tick={r['tick']}，agent={r['agent_id']}")


def _ask(reader, prompt):
    try:
        return reader(prompt).strip()
    except (EOFError, KeyboardInterrupt):
        return None


def _limits(cfg, reader, output):
    from experiment import validate_experiment
    updated = dict(cfg)
    ceiling=524288 if cfg.get('prompt_encoding')=='lossless_thread_refs_v1' else 131072
    labels = (f"单次输入代理 token 上限（最大{ceiling}）", "累计输入预留上限", "累计输出预留上限")
    output("输入新的整数；回车保留当前值。只允许提高执行上限，可能增加实际用量。")
    for key, label in zip(LIMITS, labels):
        value = _ask(reader, f"{label} [{cfg[key]}]：")
        if value is None:
            return None
        try:
            new = int(value) if value else cfg[key]
            if new < cfg[key]:
                raise ValueError()
            updated[key] = new
        except ValueError:
            output("输入无效：必须是大于等于原值的整数；本次修改已取消。")
            return None
    try:
        validate_experiment(updated)
    except ValueError:
        output("数值超出当前程序允许范围；本次修改已取消。")
        return None
    if updated == cfg:
        output("上限没有变化，仍停留在菜单。")
        return None
    return updated


def wait_minutes(minutes, output=print, clock=time.monotonic, sleep=time.sleep):
    """Short sleep intervals keep Ctrl+C responsive; no background/API activity."""
    deadline = clock() + minutes * 60
    try:
        while clock() < deadline:
            remaining = deadline - clock()
            output(f"等待恢复：还剩约 {math.ceil(remaining / 60)} 分钟；Ctrl+C 返回暂停菜单。")
            end = min(deadline, clock() + 30)
            while clock() < end:
                sleep(min(1., end - clock()))
        return True
    except KeyboardInterrupt:
        output("已取消等待，返回暂停菜单。")
        return False


def pause_menu(run_dir, reader=input, output=print, waiter=wait_minutes):
    info = describe_pause(run_dir)
    print_pause(info, output)
    cfg = info["provenance"]["config"]
    while True:
        choice = _ask(reader, "\nR/回车=处理后重试 | W=等待后重试 | L=提高执行上限 | U=确认重发未知请求 | D=详情 | S=保存退出\n请选择：")
        if choice is None or choice.lower() in ("s", "q"):
            return None
        choice = choice.lower()
        if choice == "d":
            output(json.dumps({k: info[k] for k in ("budget", "recent_request", "unknown")}, ensure_ascii=False, indent=2))
            continue
        updated = dict(cfg)
        reissue = []
        if (info["status"].get("error_type") == "HardBudgetPause"
                and info["budget"].get("requests", 0) >= cfg["max_requests"]):
            output("累计请求次数已用尽；本菜单不会增加请求次数或清零用量。请选择 S 保存退出，或 D 检查详情。")
            continue
        if choice in ("", "r", "w") and info["unknown"]:
            output("有结果未知的请求，普通继续已拦截；请选择 U 确认重发，或 S 保存退出。")
            continue
        if choice == "l":
            updated = _limits(cfg, reader, output)
            if updated is None:
                continue
        elif choice == "w":
            value = _ask(reader, "等待多少分钟后尝试一次（1..720，回车=60）：")
            if value is None:
                continue
            try:
                minutes = int(value or "60")
                if not 1 <= minutes <= 720:
                    raise ValueError()
            except ValueError:
                output("请输入1到720之间的整数。")
                continue
            if not waiter(minutes, output=output):
                continue
        elif choice == "u":
            if not info["unknown"]:
                output("没有需要确认重发的未知请求；可用 R 重试。")
                continue
            output("这些请求可能已经计费。重发会保留原始未知记录，并再次占用预算；新回答可能与未收到的回答不同。")
            if _ask(reader, "确认重发以上列出的未知请求，请完整输入 REISSUE：") != "REISSUE":
                output("未确认，仍暂停。")
                continue
            reissue = info["unknown"]
        elif choice not in ("", "r"):
            output("请输入菜单中的字母。")
            continue
        if info["unknown"] and not reissue:
            # A parallel batch can have BOTH an execution ceiling and a lost
            # response. Permit one explicit combined operation, not a dead end.
            output("上限修改还需处理上面列出的未知请求；它们可能已计费，重发会再次占用预算。")
            if _ask(reader, "若同时同意重发这些未知请求，请输入 REISSUE，否则返回菜单：") != "REISSUE":
                continue
            reissue = info["unknown"]
        reason = info["status"].get("error_type")
        if reason in ("PromptBudgetPause", "HardBudgetPause") and updated == cfg:
            if choice == "u":
                updated = _limits(cfg, reader, output)
                if updated is None:
                    continue
            else:
                output("当前仍会触发同一个执行上限；请选择 L 调整，或 S 保存退出。")
                continue
        return {"config": updated, "authorization": {"request_cutoff": info["budget"].get("requests", 0),
                "unknown_reissue": reissue, "action": choice or "r", "source_run": str(Path(run_dir).resolve())}}


def supervise(args, execute, check_resume, reader=input, output=print, interactive=None, auto_waiter=None):
    """One locked foreground controller. Each retry is an auditable child run."""
    args = copy.copy(args)
    interactive = sys.stdin.isatty() if interactive is None else interactive
    # An old incompatible run must be rejected before creating a child directory.
    if getattr(args, "resume", None):
        check_resume(args)
        parent = Path(args.resume)
        state = read_json(parent / "status.json")
        if state["status"].startswith("completed"):
            output("这次运行已完成，无需续跑。")
            return 0
        if interactive and not (getattr(args,"format_migration_manifest",None) or getattr(args,'input_migration_manifest',None) or getattr(args,'maintenance_migration_manifest',None) or getattr(args,'expression_migration_manifest',None)):
            pending = parent
        else:
            pending = None
    else:
        pending = None
    while True:
        if pending is not None:
            decision = None
            if getattr(args, 'auto_retry_seconds', 0) == 120 and not getattr(args, 'no_interactive_recovery', False):
                from auto_retry import decision_after_wait
                decision = decision_after_wait(describe_pause(pending), output, auto_waiter or wait_minutes)
            if decision is None:
                if not interactive:
                    output(f"运行已暂停：{pending}。非交互输入不会等待按键；请在本地终端使用 Resume-V7.cmd。")
                    return 2
                decision = pause_menu(pending, reader=reader, output=output)
            if decision is None:
                output(f"已保存退出；本次实验尚未完成。续跑目录：{pending}")
                return 0
            if getattr(args,"format_migration_manifest",None) and decision['config']!=read_json(pending/'provenance.json')['config']:
                output("本次格式修复必须保持输入和预算配置不变。请先 R 接续格式修复；后续若超输入上限，再单独使用 L。")
                continue
            old = read_json(pending / "provenance.json")
            cfg = decision["config"]
            config_dir = Path(old["config_dir"]).parents[1] / "resume_configs"
            path = config_dir / (datetime.now().strftime("%Y%m%d-%H%M%S-%f") + ".json")
            dump(path, cfg)
            args.config, args.resume, args.concurrency = str(path), str(pending), None
            args.steps, args.max_requests = old["total_steps"], cfg["max_requests"]
            args.execution_limit_migration = cfg != old["config"]
            args.recovery_authorization = decision["authorization"]
            check_resume(args)
            output("从完整轮次恢复；未完成轮次中的有效缓存会复用，累计用量保持不变。")
            pending = None
        try:
            execute(args)
            return 0
        except RunPaused as exc:
            pending = exc.run_dir
            args.format_migration_manifest = None  # Exact-parent adapter migration is one-time only.
            args.input_migration_manifest = None
            args.maintenance_migration_manifest = None
            args.expression_migration_manifest = None
