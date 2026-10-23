"""Run a unique local V6 study using the unmodified upstream engine."""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
from socioverse.engine import build_simulator
from socioverse.schemas import (StudySpec, EnvironmentBundle, EnvironmentLayer, ScheduledEvent,
    InformationProgram, Broadcast, PopulationBundle, InteractionStructure, SimulationConfig, WarmStartSpec)
from model import load_rows, make_network, targets, dump, digest, BINARY_SCORE_POLICY, feed_description, read_json

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "materials_v6"
UPSTREAM = ROOT / "vendor/SocioVerse2"
CODE = Path(__file__).resolve().parent
RESULTS = ROOT / "runs/v6"
CONFIGS = ROOT / "runtime/v6/configs"
LOGS = ROOT / "runtime/v6/logs"


from government import validate, select_targets, trust_values
from experiment import validate_experiment, source_trust_values, assignment_summary
from recovery import RunPaused, install_authorization
from memory_policy import memory_description


def defaults():
    return dict(prompt_encoding='full_json_v1',wire_prompt_style='standard',
        memory_retention_policy='last_five_experiences_v1',memory_window_ticks=None,
        comment_window_limit=None,comment_participation_policy='legacy',memory_comment_policy='complete_observed_v1',
        contract_status="engineering_only_pending_confirmation", pbd=0.0, gt=.6, rf=.6,
        behavior_seed=20261020, strategy="inside", base_url="https://api.zetatechs.com/v1",
        model="deepseek-v4-flash", max_requests=12200,
        government_tick=8, government_reach=40, targeting_inside_ratio=None,
        government_trust_mean=None, government_trust_sd=.10,
        government_target_seed=20261019, government_trust_seed=20261022,
        tbu_definition="pre_government_tick_believers_first_reject_mean_wait_completers",
        probability_precision="table_values", contact_rule="once_per_tick_correction_priority",
        rule_rebelief=False, direct_relay_same_gt=True,
        comment_target="first_displayed_post", token_guard="cl100k_base_estimate_15percent_plus64",
        source_trust_gap=None, source_trust_center=.5, source_trust_sd=.10, source_trust_seed=20261023,
        rule_source_trust_mode="legacy_pb", prompt_input_token_limit=32768, prompt_memory_policy="preserve",
        belief_measurement_policy="legacy", llm_max_output_tokens=512,
        max_input_reserved_units=49_971_200, max_output_reserved_tokens=6_246_400,
        runtime_version="v6-network-mbti-latest100-20261023-1",
        feed_policy="legacy", decision_condition_policy="legacy",
        api_key_mode="environment", api_primary_retry_seconds=3600,
        api_routing_policy="primary_first_v1",api_key_cooldown_seconds=60,
        rate_recovery_successes=20, rate_recovery_seconds=60., rate_limit_max_retries=6,
        rate_limit_wait_seconds=2., rate_limit_max_wait_seconds=60., rate_limit_spacing_seconds=1., max_concurrency=5, format_max_attempts=4, rule_reconsider_rumor=True)


def extract_post_blocks(text):
    """Read two Markdown blockquotes, preserving paragraphs inside each post."""
    blocks, current = [], []
    for line in text.splitlines() + [""]:
        if line.startswith(">"):
            content = line[1:]
            current.append(content[1:] if content.startswith(" ") else content)
        elif current:
            blocks.append("\n".join(current).strip())
            current = []
    if len(blocks) != 2:
        raise ValueError("Expected exactly two post blockquotes; review P001 and G001 extraction")
    return blocks


def make_bundles(roster, prompt, cfg, audit, study_id="government-rumor-v6", steps=10, mode="scripted"):
    rows = load_rows(roster)
    env_text = (Path(roster).parent / "03_新环境设定.md").read_text(encoding="utf-8")
    quotes = extract_post_blocks(env_text)
    scenario_file = Path(roster).parent / "05_案例与判断对象.json"
    scenario = json.loads(scenario_file.read_text(encoding="utf-8")) if scenario_file.exists() else {}
    correction_mode = scenario.get("correction_mode", "scripted_no_evidence")
    edges = make_network(rows)
    direct = select_targets(rows, cfg)
    trust = trust_values(rows, cfg)
    source_trust = source_trust_values(rows, cfg)
    tg = cfg["government_tick"]
    binary = cfg.get("belief_measurement_policy") == BINARY_SCORE_POLICY
    display_beliefs = ["all_believe", "all_reject"] if binary else ["all_believe", "all_uncertain", "all_reject"]
    belief_descriptions = {"all_believe": "当前相信人数", "all_reject": "当前不相信人数"}
    if not binary:belief_descriptions["all_uncertain"] = "当前不确定人数"
    study = StudySpec(study_id=study_id, title="V6 政府谣言辟谣：本地混合模型" + ("（离线工程测试）" if mode == "scripted" else "（真实调用）"),
        research_question="在固定混合人群与网络下，初始SOURCE信任均值差、政府介入时间、投放圈内比例和政府信任设定伴随怎样的信念与传播轨迹？",
        n_steps=steps, seed=cfg["behavior_seed"], time_unit="abstract", step_meaning="一轮同步观察与决策，无现实分钟映射",
        key_attributes=["current_belief", "decision_mode", "group"],
        metrics=["remaining_agents", "remaining_llm", "technical_dropout_count", *display_beliefs, "comments", "posts"],
        display_metrics=["remaining_agents", "remaining_llm", "technical_dropout_count"],
        metric_descriptions={**belief_descriptions,
                             "comments": "累计公开评论数", "posts": "累计帖子数（含原帖与转发）"},
        domain="rumor", tags=["V6", "hybrid", "local"], legacy_simulator="from_scratch",
        provider_refs=["rumor_v6.population", "rumor_v6.environment", "rumor_v6.decision", "rumor_v6.metrics"],
        status="engineering-only", resources_ref=None,
        adjustable_params=["pbd", "source_trust_gap", "source_trust_center", "source_trust_sd", "rule_source_trust_mode", "gt", "rf", "strategy", "government_tick", "government_reach", "targeting_inside_ratio", "government_trust_mean", "government_trust_sd", "model", "base_url"])
    env = EnvironmentBundle(study_id=study_id, provider_ref="rumor_v6.environment", provider_args={
        "roster_csv": str(roster), "edges": edges, "direct_targets": direct,
        "government_tick": tg, "government_trust": trust, "source_trust": source_trust,
        "rumor_text": quotes[0], "correction_text": quotes[1], "correction_mode": correction_mode, "reread_interval": 3, "max_post_reads": 4,
        "scenario_id": scenario.get("scenario_id"), "belief_target": scenario.get("belief_target"),
        "feed_policy": cfg.get("feed_policy", "legacy"),
        "comment_window_limit": cfg.get("comment_window_limit"),
        "comment_tie_seed": cfg["behavior_seed"],
        "comment_participation_policy": cfg.get("comment_participation_policy","legacy"),
        "memory_comment_policy": cfg.get("memory_comment_policy","complete_observed_v1"),
        "memory_retention_policy": cfg.get('memory_retention_policy', 'last_five_experiences_v1'),
        "memory_window_ticks": cfg.get('memory_window_ticks'),
        "decision_condition_policy": cfg.get("decision_condition_policy", "legacy"),
        "comment_target": cfg.get("comment_target", "first_displayed_post"),
        "belief_measurement_policy": cfg.get("belief_measurement_policy", "legacy"),
        "prompt_revision": scenario.get("prompt_revision")},
        layers=[EnvironmentLayer(name=name, modality=mod, scope=scope, dynamics=dyn, description=desc)
                for name, mod, scope, dyn, desc in [
                    ("follow_network", "physical", "local", "static", "5902有向边；关注者到发布者"),
                    ("reading_policy", "physical", "macro", "static",
                     feed_description(cfg.get("feed_policy","legacy"), cfg.get('comment_window_limit'))),
                    ("government_policy", "physical", "macro", "scheduled", f"tick{tg}定向{len(direct)}人，保证首位展示"),
                    ("content_feed", "information", "local", "endogenous", "关注流；新行动下一轮可见"),
                    ("correction_content", "information", "local", "scheduled", "固定实验回应；非真实通告"),
                    ("personal_memory", "information", "local", "endogenous", memory_description(cfg)+'；不读取他人私态')]],
        scheduled_events=[ScheduledEvent(at_step=tg, target_layer="government_policy", op="set",
                          property_name="enabled", value=True, note="G001一次性定向展示，非全员广播")],
        information_program=InformationProgram(broadcasts=[Broadcast(message_id="G001", content=quotes[1],
            at_step=tg, ttl=1, audience={"agent_ids": direct}, note=f"{correction_mode}；实际触达者另显独立官方帖")]))
    pop = PopulationBundle(study_id=study_id, provider_ref="rumor_v6.population",
        provider_args={"roster_csv": str(roster)}, materialized_count=582,
        interaction=InteractionStructure(kind="explicit_network", edges=edges), propagation="broadcast_then_local")
    sim = SimulationConfig(study_id=study_id, n_steps=steps, seed=cfg["behavior_seed"],
        decision_ref="rumor_v6.decision", decision_args={"config": cfg, "prompt_file": str(prompt),
            "audit_dir": str(audit), "llm_kind": mode}, collector_ref="rumor_v6.metrics",
        interaction_rounds=1, engine_args={"memory_window": cfg.get('memory_window_ticks') or 5})
    return study, env, pop, sim


def execute(args):
    if any(getattr(args, k, False) for k in ("retry_policy_migration", "evidence_policy_migration", "dropout_migration", "io_repair_migration")):
        raise ValueError("V6 requires a new experiment; no V4/V5 checkpoint migration")
    if getattr(args, "rate_migration_manifest", None) and not args.resume:
        raise ValueError("Rate migration requires an explicit parent")
    if getattr(args, "execution_limit_migration", False) and not args.resume:
        raise ValueError("Execution limit migration requires an explicit parent")
    if getattr(args, "format_migration_manifest", None) and not args.resume:
        raise ValueError("Format migration requires an explicit parent")
    if getattr(args,'input_migration_manifest',None) and not args.resume:
        raise ValueError('Input migration requires an explicit parent')
    if getattr(args,'maintenance_migration_manifest',None) and not args.resume:
        raise ValueError('Maintenance repair requires an explicit parent')
    if getattr(args,'expression_migration_manifest',None) and not args.resume:
        raise ValueError('Expression migration requires an explicit parent')
    cfg = defaults()
    if args.config:
        cfg.update(json.loads(Path(args.config).read_text(encoding="utf-8")))
    if getattr(args, "concurrency", None) is not None:
        cfg["max_concurrency"] = args.concurrency
    adjustable = {"contract_status", "pbd", "gt", "rf", "behavior_seed", "strategy", "base_url", "model", "max_requests", "api_profile", "rule_reconsider_rumor"}
    adjustable.update({"government_tick", "government_reach", "targeting_inside_ratio", "government_trust_mean", "government_trust_sd", "government_target_seed", "government_trust_seed"})
    adjustable.add("max_concurrency")
    adjustable.update({"source_trust_gap", "source_trust_center", "source_trust_sd", "source_trust_seed",
        "rule_source_trust_mode", "prompt_input_token_limit", "prompt_memory_policy",
        "max_input_reserved_units", "max_output_reserved_tokens", "belief_measurement_policy", "llm_max_output_tokens",
        "api_key_mode", "api_primary_retry_seconds", "feed_policy", "decision_condition_policy", "comment_target"})
    adjustable.add('prompt_encoding')
    adjustable.add('wire_prompt_style')
    adjustable.update({'comment_window_limit','comment_participation_policy','memory_comment_policy'})
    adjustable.update({'memory_retention_policy','memory_window_ticks'})
    adjustable.update({'api_routing_policy','api_key_cooldown_seconds'})
    if type(cfg["max_concurrency"]) is not int or not 1 <= cfg["max_concurrency"] <= 10:
        raise ValueError("max_concurrency must be an integer in 1..10")
    validate(cfg)
    validate_experiment(cfg)
    for key, val in cfg.items():
        if key not in adjustable and defaults().get(key) != val:
            raise ValueError(f"Unsupported rule change: {key}; implement and test a new version")
    if cfg["pbd"] not in (0, .2, .4) or cfg["rf"] != .6:
        raise ValueError("Use V4 probability table and RF=.6")
    if cfg["strategy"] not in ("inside", "outside", "random") or not 1 <= cfg["max_requests"] <= 12200:
        raise ValueError("invalid strategy or request limit")
    mode = "openai" if args.live else "scripted"
    if cfg.get("api_profile") not in (None, "minimax_m3"):
        raise ValueError("unsupported api_profile")
    if args.live:
        from credentials import validate_credentials
        key_mode = validate_credentials(cfg)
        subscription_run = getattr(args, "token_plan_run", False)
        if subscription_run:
            if cfg.get("api_profile") != "minimax_m3" or cfg["base_url"] != "https://api.minimax.cn/v1":
                raise ValueError("Token Plan launch is restricted to the configured MiniMax endpoint")
            if cfg["contract_status"] not in ("confirmed", "authorized_engineering_run"):
                raise ValueError("Token Plan launch needs an explicitly authorized run configuration")
            if key_mode == "environment" and not (os.environ.get("RUMOR_LLM_API_KEY") or "").strip().startswith("sk-cp-"):
                raise ValueError("Environment mode expects a subscription key (sk-cp-)")
        elif not args.cost_limit_configured or cfg["contract_status"] != "confirmed":
            raise ValueError("Live requires a confirmed contract and --cost-limit-configured; offline remains available")
        if not 1 <= args.max_requests <= 12200:
            raise ValueError("max_requests must be 1..12200")
        cfg["max_requests"] = args.max_requests  # default20: real-interface smoke, not 40-round claim
    if not 1 <= args.steps <= 40:
        raise ValueError("steps must be 1..40")
    if args.resume:
        check_resume_compatible(args)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    sid = f"government-rumor-v6-{mode}-{stamp}"
    run_dir, audit, config_dir = RESULTS / sid, LOGS / sid, CONFIGS / sid
    run_dir.mkdir(parents=True, exist_ok=False)
    audit.mkdir(parents=True, exist_ok=False)
    config_dir.mkdir(parents=True, exist_ok=False)
    # Local-only frozen inputs. Original materials remain untouched.
    hashes = {}
    for p in SOURCE.iterdir():
        if p.is_file():
            hashes[p.name] = hashlib.sha256(p.read_bytes()).hexdigest()
            shutil.copy2(p, config_dir / p.name)
    code_hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in CODE.glob("*.py")}
    provenance = dict(input_sha256=hashes, code_sha256=code_hashes, numpy_version=np.__version__, total_steps=args.steps,
        upstream_url="https://github.com/sii-research/SocioVerse2",
        upstream_commit=json.loads((ROOT / "vendor/UPSTREAM.json").read_text(encoding="utf-8"))["commit"],
        mode=mode, dry_run=not args.live, config=cfg, audit_dir=str(audit), config_dir=str(config_dir))
    dump(run_dir / "provenance.json", provenance)
    from parameter_report import write_parameters
    write_parameters(run_dir, cfg, args.steps)
    study, env, pop, simcfg = make_bundles(config_dir / "01_Agent基础信息表.csv",
        config_dir / "02_Prompt固定提示词.md", cfg, audit, sid, args.steps, mode)
    if args.resume:
        parent = Path(args.resume).resolve()
        previous = json.loads((parent / "provenance.json").read_text(encoding="utf-8"))
        migration = getattr(args, "retry_policy_migration", False)
        evidence_migration = getattr(args, "evidence_policy_migration", False)
        manifest_path = getattr(args, "rate_migration_manifest", None)
        if getattr(args,'expression_migration_manifest',None):
            from expression_migration import validate_expression_migration
            manifest=json.loads(Path(args.expression_migration_manifest).read_text(encoding='utf-8'))
            validate_expression_migration(previous,provenance,parent,manifest)
            provenance['expression_migration']=manifest
        elif getattr(args,'maintenance_migration_manifest',None):
            from maintenance_migration import validate_maintenance_migration
            manifest=json.loads(Path(args.maintenance_migration_manifest).read_text(encoding='utf-8'))
            validate_maintenance_migration(previous,provenance,parent,manifest)
            provenance['export_recovery_migration']=manifest
        elif getattr(args,'input_migration_manifest',None):
            from compact_migration import validate_compact_migration
            manifest=json.loads(Path(args.input_migration_manifest).read_text(encoding='utf-8'))
            validate_compact_migration(previous,provenance,parent,manifest)
            provenance['input_encoding_migration']=manifest
        elif getattr(args,"format_migration_manifest",None):
            from format_migration import validate_format_migration
            manifest=json.loads(Path(args.format_migration_manifest).read_text(encoding="utf-8"))
            validate_format_migration(previous,provenance,parent,manifest)
            provenance["output_schema_migration"]=manifest
        elif manifest_path:
            manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
            validate_rate_migration(previous, provenance, parent, manifest)
            provenance["engineering_migration"] = manifest
        elif getattr(args, "execution_limit_migration", False):
            validate_execution_limit_migration(previous, provenance)
            provenance["execution_limit_migration"] = dict(old_config=previous["config"], new_config=cfg,
                reason="Explicit increase of execution limits only; research rules, prompts, code and previous API outcomes preserved")
        elif any(previous[k] != provenance[k] for k in ("input_sha256", "code_sha256", "config", "mode", "upstream_commit", "total_steps")):
            raise ValueError("V6 resume requires identical inputs, code, config, mode and upstream")
        completed, replay_file = prepare_replay(parent, run_dir, upto=args.steps)
        if migration and completed != 19:
            raise ValueError("migration requires complete checkpoints through tick19")
        if evidence_migration and completed != 21:
            raise ValueError("evidence migration requires completed tick21")
        if getattr(args, "dropout_migration", False) and completed != 21:
            raise ValueError("dropout migration expects completed tick21")
        simcfg.warm_start = WarmStartSpec(source_version=parent.name,
            source_trajectory=str(replay_file), resume_from=completed)
        shutil.copytree(previous["audit_dir"], audit, dirs_exist_ok=True)
        if (getattr(args,'maintenance_migration_manifest',None) or getattr(args,'expression_migration_manifest',None)) and read_json(parent/'status.json').get('error_type')=='QuotaPause':
            from recovery import initialize_quota_recovery_gate
            provenance['quota_recovery_gate']=initialize_quota_recovery_gate(audit,cfg)
        if getattr(args, "recovery_authorization", None):
            install_authorization(audit, args.recovery_authorization)
            provenance["recovery_authorization"] = args.recovery_authorization
        provenance["resumed_from"] = str(parent)
        provenance["inherited_completed_tick"] = completed
        dump(run_dir / "provenance.json", provenance)
    for name, obj in (("study.yaml", study), ("environment/environment.json", env),
                      ("population/population.json", pop), ("simulation/simulation.json", simcfg)):
        dump(run_dir / name, obj.model_dump(mode="json"))
    dump(config_dir / "behavior_contract.json", cfg)
    dump(config_dir / "network_edges.json", env.provider_args["edges"])
    dump(config_dir / "government_targets.json", env.provider_args["direct_targets"])
    dump(config_dir / "government_trust.json", env.provider_args["government_trust"])
    dump(config_dir / "source_trust.json", env.provider_args["source_trust"])
    dump(config_dir / "trust_assignment_summary.json", assignment_summary(
        load_rows(config_dir / "01_Agent基础信息表.csv"), env.provider_args["source_trust"], env.provider_args["government_trust"]))
    dump(config_dir / "frozen_input_hashes.json", {"network": digest(env.provider_args["edges"]),
         "government_targets": digest(env.provider_args["direct_targets"]), "behavior_contract": digest(cfg),
         "source_trust": digest(env.provider_args["source_trust"]), "government_trust": digest(env.provider_args["government_trust"])})
    dump(run_dir / "grounding/grounding.json", {"method_notes": "V4用户指定工程模型，合成网络；实验性纠正文本。",
        "assumptions": [{"id": "pending-rule-contract", "claim": cfg["contract_status"]}]})
    shutil.copy2(CODE / "model.py", run_dir / "model.py")
    state = {"status": "running", "last_completed_tick": 0, "dry_run": not args.live}
    metrics = []
    def on_step(t, m):
        metrics.append(m)
        dump(run_dir / "reports" / "technical_dropout.json", {"tick":t,
             "remaining_agents":m.get("remaining_agents"), "remaining_llm":m.get("remaining_llm"),
             "technical_dropout_count":m.get("technical_dropout_count"),
             "offline_agents":simulator.env.offline})
        # Durable whole-tick action checkpoint. Independent of open DuckDB/WAL files.
        records = simulator.store._con.execute(
            "SELECT agent_id, action_kind, action_payload FROM panel WHERE step=? ORDER BY agent_id", [t]).fetchall()
        if t > 0 and len(records) != 582:
            raise ValueError("refusing incomplete tick checkpoint")
        if t > 0:
            actions = [{"agent_id": aid, "step": t, "action_kind": kind,
                        "action_payload": json.loads(payload)} for aid, kind, payload in records]
            dump(run_dir / "checkpoints" / f"tick-{t:03d}.json", {"actions": actions, "sha256": digest(actions)})
        state["last_completed_tick"] = t
        dump(run_dir / "status.json", state)
        dump(RESULTS / "latest.json", {"run_dir": str(run_dir), **state})
        dump(run_dir / "trajectory/metrics_history.json", {"study_id": sid, "rows": metrics})
        print(f"tick {t}/{args.steps}: believe={m['all_believe']} reject={m['all_reject']} remaining={m['remaining_agents']} dropout={m['technical_dropout_count']}", flush=True)
    simulator = build_simulator(env_bundle=env, pop_bundle=pop, sim_config=simcfg,
        store_path=run_dir / "trajectory/study.duckdb", on_step=on_step)
    personas, initial = simulator.materialize_initial()
    (run_dir / "population/roster.jsonl").write_text(
        "\n".join(p.model_dump_json() for p in personas) + "\n", encoding="utf-8")
    dump(config_dir / "initial_state.json", [r.model_dump() for r in initial])
    dump(run_dir / "status.json", state)
    dump(RESULTS / "latest.json", {"run_dir": str(run_dir), **state})
    failed = None
    try:
        history = simulator.run()
        state["status"] = "completed_offline" if not args.live else "completed_live"
        dump(run_dir / "trajectory/metrics_history.json", history.model_dump())
    except (Exception, KeyboardInterrupt) as exc:
        failed = exc
        import traceback
        dump(run_dir / "failure_diagnostic.json", {
            "type":type(exc).__name__, "filename":getattr(exc,"filename",None),
            "filename2":getattr(exc,"filename2",None), "errno":getattr(exc,"errno",None), "winerror":getattr(exc,"winerror",None),
            "output_error":getattr(exc,"safe_details",None),
            "frames":[{"file":f.filename,"line":f.lineno,"function":f.name} for f in traceback.extract_tb(exc.__traceback__)]})
        state["status"] = {"QuotaPause":"paused_quota", "PromptBudgetPause":"paused_prompt_budget",
                           "HardBudgetPause":"paused_hard_budget", "UncertainRequest":"paused_unknown_request",
                           "KeyboardInterrupt":"paused_by_user",
                           "OutputContractPause":"paused_output_contract",
                           "DecisionConditionsPause":"paused_decision_contract"}.get(type(exc).__name__,"interrupted")
        if type(exc).__name__ in ("PromptBudgetPause","OutputContractPause","HardBudgetPause"):
            state["error_details"] = str(exc)
            if getattr(exc,"safe_details",None):state['error_context']=exc.safe_details
            print(str(exc),flush=True)
        state["error_type"] = type(exc).__name__
        # Finalize only committed panel rows; never label failed tick completed.
        if simulator.store._con is not None:
            simulator.store.finalize()
    finally:
        dump(run_dir / "status.json", state)
        snapshot = simulator.env.snapshot()
        snapshot["last_completed_tick"] = state["last_completed_tick"]
        snapshot["note"] = "May include scheduled exogenous update for attempted tick; resume replays committed DB actions."
        dump(run_dir / "trajectory/final_snapshot.json", snapshot)
        dump(RESULTS / "latest.json", {"run_dir": str(run_dir), **state})
        client = getattr(simulator.decision, "client", None)
        if client is not None:
            client.close()
    from export_recovery import finalize_exports
    return finalize_exports(run_dir,load_rows(config_dir/'01_Agent基础信息表.csv'),cfg,state,mode,RESULTS/'latest.json',simulation_error=failed)


def check_resume_compatible(args):
    """Fail before creating any files if an old experiment cannot be replayed."""
    parent = Path(args.resume).resolve()
    previous = json.loads((parent / "provenance.json").read_text(encoding="utf-8"))
    cfg = defaults()
    if args.config:
        cfg.update(json.loads(Path(args.config).read_text(encoding="utf-8")))
    if getattr(args, "concurrency", None) is not None:
        cfg["max_concurrency"] = args.concurrency
    if args.live:
        cfg["max_requests"] = args.max_requests
    current = dict(config=cfg, total_steps=args.steps, numpy_version=np.__version__,
        mode="openai" if args.live else "scripted",
        upstream_commit=json.loads((ROOT / "vendor/UPSTREAM.json").read_text(encoding="utf-8"))["commit"],
        input_sha256={p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in SOURCE.iterdir() if p.is_file()},
        code_sha256={p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in CODE.glob("*.py")})
    if getattr(args,'expression_migration_manifest',None):
        from expression_migration import validate_expression_migration
        validate_expression_migration(previous,current,parent,json.loads(Path(args.expression_migration_manifest).read_text(encoding='utf-8')))
    elif getattr(args,'maintenance_migration_manifest',None):
        from maintenance_migration import validate_maintenance_migration
        validate_maintenance_migration(previous,current,parent,json.loads(Path(args.maintenance_migration_manifest).read_text(encoding='utf-8')))
    elif getattr(args,'input_migration_manifest',None):
        from compact_migration import validate_compact_migration
        validate_compact_migration(previous,current,parent,json.loads(Path(args.input_migration_manifest).read_text(encoding='utf-8')))
    elif getattr(args,"format_migration_manifest",None):
        from format_migration import validate_format_migration
        validate_format_migration(previous,current,parent,
            json.loads(Path(args.format_migration_manifest).read_text(encoding="utf-8")))
    elif getattr(args, "rate_migration_manifest", None):
        validate_rate_migration(previous, current, parent,
            json.loads(Path(args.rate_migration_manifest).read_text(encoding="utf-8")))
    elif getattr(args, "execution_limit_migration", False):
        validate_execution_limit_migration(previous, current)
    else:
        changed = [k for k in current if previous.get(k) != current[k]]
        if changed:
            raise ValueError("无法直接续跑：代码、素材或配置与原实验不一致（" + ", ".join(changed) +
                             "）。原结果已保留；请使用原版本环境续跑，或按新设定重新开始实验。")


def validate_execution_limit_migration(previous, current):
    for key in ("input_sha256", "code_sha256", "mode", "upstream_commit", "total_steps", "numpy_version"):
        if previous[key] != current[key]:
            raise ValueError("Execution limit migration cannot change " + key)
    allowed = {"prompt_input_token_limit", "max_input_reserved_units", "max_output_reserved_tokens"}
    for key in previous["config"].keys() | current["config"].keys():
        old,new=previous["config"].get(key),current["config"].get(key)
        if old == new:
            continue
        if key not in allowed or not isinstance(old,int) or not isinstance(new,int) or new<old:
            raise ValueError("Execution limit migration only permits increasing explicit execution ceilings: " + key)
    if previous["config"].get("prompt_memory_policy") != "preserve":
        raise ValueError("Increasing the input ceiling during resume requires preserve policy; do not alter old trimming behavior")


def validate_rate_migration(previous, current, parent, manifest):
    if str(parent.resolve()) != manifest["parent_run"]:
        raise ValueError("Rate migration parent mismatch")
    if previous["code_sha256"] != manifest["old_code_sha256"] or current["code_sha256"] != manifest["new_code_sha256"]:
        raise ValueError("Rate migration code hash mismatch")
    if previous["config"] != manifest["old_config"] or current["config"] != manifest["new_config"]:
        raise ValueError("Rate migration configuration mismatch")
    for key in ("input_sha256", "mode", "dry_run", "upstream_commit", "upstream_url", "numpy_version", "total_steps"):
        if previous[key] != current[key]:
            raise ValueError("Rate migration cannot change " + key)
    allowed = {"runtime_version", "rate_limit_max_retries", "rate_limit_wait_seconds",
               "rate_limit_max_wait_seconds", "rate_limit_spacing_seconds"}
    for key in previous["config"].keys() | current["config"].keys():
        if key not in allowed and previous["config"].get(key) != current["config"].get(key):
            raise ValueError("Rate migration cannot change research/budget configuration: " + key)


def validate_retry_migration(previous, current, parent_name, manifest):
    if parent_name != manifest["parent_run"]:
        raise ValueError("retry migration only applies to the explicitly authorized parent")
    for key in ("input_sha256", "mode", "upstream_commit", "numpy_version"):
        if previous[key] != current[key]:
            raise ValueError("migration cannot change source/model environment")
    expected = {**previous["config"], "format_max_attempts": 4}
    if expected != current["config"]:
        raise ValueError("migration may only add the four-generation retry policy")
    if previous["code_sha256"] != manifest["parent_code_sha256"] or current["code_sha256"] != manifest["target_code_sha256"]:
        raise ValueError("migration code hashes differ from the reviewed version")
    if previous["code_sha256"]["model.py"] != current["code_sha256"]["model.py"]:
        raise ValueError("environment and behavioral rules must remain unchanged")


def prepare_replay(parent, destination, upto=40):
    """Only contiguous, checksummed, complete ticks can enter a recovery replay."""
    completed = 0
    lines = []
    for tick in range(1, upto + 1):
        path = parent / "checkpoints" / f"tick-{tick:03d}.json"
        if not path.exists():
            break
        data = json.loads(path.read_text(encoding="utf-8"))
        actions = data["actions"]
        if digest(actions) != data["sha256"] or len(actions) != 582:
            raise ValueError("checkpoint checksum/count mismatch")
        if {a["agent_id"] for a in actions} != {f"A{i:04d}" for i in range(1, 583)} or any(a["step"] != tick for a in actions):
            raise ValueError("checkpoint population/tick mismatch")
        lines.extend(json.dumps(a, ensure_ascii=True) for a in actions)
        completed = tick
    replay_file = destination / "recovery_actions.jsonl"
    replay_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return completed, replay_file


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--concurrency", type=int, choices=range(1, 11), help="Execution concurrency only; no research rule changes")
    parser.add_argument("--steps", type=int, default=10)
    parser.add_argument("--config", default=str(ROOT / "configs/local_defaults.json"))
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--cost-limit-configured", action="store_true")
    parser.add_argument("--token-plan-run", action="store_true", help="Authorize subscription quota use; does not assert a currency cap")
    parser.add_argument("--max-requests", type=int, default=20)
    parser.add_argument("--io-repair-migration", action="store_true")
    parser.add_argument("--dropout-migration", action="store_true")
    parser.add_argument("--rate-migration-manifest", help="Reviewed exact-parent/code-hash rate policy migration")
    parser.add_argument("--format-migration-manifest", help="Reviewed exact-parent output-format adapter migration; no input/config/rule changes")
    parser.add_argument('--input-migration-manifest',help='Reviewed exact-parent lossless input-format migration')
    parser.add_argument('--maintenance-migration-manifest',help='Reviewed exact-parent export and recovery repair')
    parser.add_argument('--expression-migration-manifest',help='Reviewed concise expression with lossless original data and cached decisions')
    parser.add_argument("--resume", help="parent run directory; exact same input/code/config required")
    parser.add_argument("--execution-limit-migration", action="store_true", help="Explicitly increase prompt/input/output ceilings only, with identical code and research parameters")
    parser.add_argument("--evidence-policy-migration", action="store_true")
    parser.add_argument("--retry-policy-migration", action="store_true", help="Reviewed one-time migration; replay through19, continue20")
    parser.add_argument("--no-interactive-recovery", action="store_true", help="Save and return code 2 on pause; never wait for terminal input")
    args = parser.parse_args()
    # Windows process lock prevents two launchers spending the same run budget concurrently.
    import msvcrt
    lock_path = CODE / ".simulation.lock"
    with open(lock_path, "a+b") as lock:
        if lock.tell() == 0:
            lock.write(b"0")
            lock.flush()
        lock.seek(0)
        try:
            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            raise SystemExit("Another simulation is running; do not launch a second copy")
        try:
            from recovery import supervise
            interactive = sys.stdin.isatty() and not args.no_interactive_recovery
            return supervise(args, execute, check_resume_compatible, interactive=interactive)
        finally:
            lock.seek(0)
            msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\n启动或操作已取消；已有检查点和缓存保留。", flush=True)
        raise SystemExit(130)
    except (ValueError, FileNotFoundError) as exc:
        print("配置/续跑错误：" + str(exc), file=sys.stderr, flush=True)
        raise SystemExit(2)
