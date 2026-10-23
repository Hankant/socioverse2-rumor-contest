"""Audited gateway calls, bounded attempts, optional same-model key failover."""
from __future__ import annotations
import copy
import hashlib
import json
import os
import re
import time
from pathlib import Path
from model import dump, digest, read_json
from functools import lru_cache
from output_adapter import adapt_condition_output, validation_diagnostic
from response_contract import RETRY_POLICY, ERROR_LABELS, response_envelope_diagnostic, wire_prompt


class AgentRequestFailure(RuntimeError):
    """Persisted or current repeated transport failure."""


class QuotaPause(RuntimeError):
    """Rate retry allowance exhausted; stop without dropping the agent."""


class PromptBudgetPause(ValueError):
    """Preserve the full observation and memory; pause before an oversized call."""


class HardBudgetPause(RuntimeError):
    """Execution ceiling reached; human must explicitly increase a token budget."""


class UncertainRequest(RuntimeError):
    """A dispatched request has no durable response; billing/outcome unknown."""


class FormatAttemptsExhausted(ValueError):
    """All permitted generations produced invalid JSON/schema."""


class DecisionConditionsPause(ValueError):
    """New all-conditions contract remains incomplete; pause without dropping a user."""


class OutputContractPause(DecisionConditionsPause):
    """A precise bounded output failure, never a fabricated decision."""
    def __init__(self, agent_id, tick, attempts, diagnostic):
        self.safe_details={"agent_id":agent_id,"tick":tick,"generation_attempts":attempts,**diagnostic}
        code=diagnostic.get("code","response_validation_failed")
        super().__init__(f"{agent_id} tick={tick}: {ERROR_LABELS.get(code,code)}; attempts={attempts}")


def parse_and_validate(text, ob, feed, memory):
    """Strictly validate; the caller selects the policy for bounded regeneration."""
    answer,syntax = parse_response_object(text,ob)
    answer = adapt_condition_output(answer, ob)
    validate_response(answer, ob, feed, memory)
    if syntax:answer['output_syntax_repairs']=syntax
    return answer


def parse_response_object(text,ob):
    try:return parse_json_object(text),None
    except json.JSONDecodeError as original:
        if ob.local_physical.get('decision_condition_policy')!='all_conditions_v1':
            raise
        from syntax_repair import repair_document
        try:return repair_document(text)
        except (ValueError,TypeError,RecursionError):
            raise original from None


def is_format_error(exc):
    return isinstance(exc, json.JSONDecodeError) or str(exc) in {
        "LLM JSON root must be object", "LLM must return a judged belief",
        "invalid belief", "invalid action schema", "empty enabled comment", "invalid/invisible evidence", "invalid belief measurement",
        "invalid decision condition coverage", "invalid/invisible comment target", "ambiguous decision condition alias"}


@lru_cache(maxsize=1)
def token_estimator():
    import tiktoken
    return tiktoken.get_encoding("cl100k_base")


def estimated_input_tokens(prompt):
    # Proxy tokenizer, NOT MiniMax's official tokenizer. Reserve 15% + chat overhead.
    import math
    return math.ceil(len(token_estimator().encode(prompt, disallowed_special=())) * 1.15) + 64


def validate_response(answer, ob, feed, memory):
    if ob.agent_id == "TEST":
        if answer != {"ok": True}:
            raise ValueError("synthetic connection check schema mismatch")
        return
    from model import normalize_answer, validate_belief_measurement, BINARY_SCORE_POLICY
    policy = ob.local_physical.get("belief_measurement_policy", "legacy")
    if policy != BINARY_SCORE_POLICY and answer.get("belief") not in ("believe", "uncertain", "reject"):
        raise ValueError("LLM must return a judged belief")
    normalize_answer(answer, feed, memory, ob.local_physical["already_reposted"], belief_policy=policy,
                     comment_target_policy=ob.local_physical.get("comment_target_policy", "first_displayed_post"))
    validate_belief_measurement(answer, required=policy in ("subjective_credibility_v1", BINARY_SCORE_POLICY))
    from decision_conditions import validate_condition_application
    validate_condition_application(answer, ob)


def parse_json_object(text):
    """Accept one JSON object, optionally wrapped in a single Markdown fence.

    Never extract an arbitrary object from prose or repair malformed JSON.
    The caller preserves the original response in the request audit.
    """
    if not isinstance(text,str) or not text.strip():
        raise ValueError("LLM empty response")
    text = text.strip()
    fenced = re.fullmatch(r"```(?:json)?\s*\n(.*?)\n\s*```", text, re.DOTALL | re.IGNORECASE)
    if fenced:
        text = fenced.group(1).strip()
    answer = json.loads(text)
    if not isinstance(answer, dict):
        raise ValueError("LLM JSON root must be object")
    return answer


def request_options(config):
    options = dict(temperature=.7, top_p=.8, max_tokens=config.get("llm_max_output_tokens", 512))
    if config.get("api_profile") == "minimax_m3":
        if config["model"] != "MiniMax-M3":
            raise ValueError("minimax_m3 profile requires MiniMax-M3; review thinking/budget for another model")
        # Official MiniMax docs: M3 supports disabled thinking; M2.x/M3.1 do not.
        # JSON is requested by the V4 prompt and strictly parsed locally. Do not
        # assume an undocumented response_format parameter enforces JSON.
        options["extra_body"] = {"thinking": {"type": "disabled"}, "reasoning_split": True}
        # Current provider documentation says M3 ignores supplied sampling
        # values and uses temperature=1 / top_p=.95. Record those values honestly.
        options.update(temperature=1.0, top_p=.95)
    else:
        options["response_format"] = {"type": "json_object"}
    return options


def repetition_context(persona, summary):
    """Bounded hypothesis inputs to the LLM, NOT calibrated output probabilities."""
    import math
    def value(key):
        raw=persona.get(key)
        return .5 if raw is None or raw=="" else float(raw)
    sensitivity = value("repetition_sensitivity")
    verification = value("verification_preference")
    sharing = value("sharing_propensity")
    result = {}
    for root, counts in summary.items():
        repeats = max(0, counts["exposure_tick_count"]-1)
        saturation = 1 - math.exp(-repeats/3)
        result[root] = {
            "repeated_rounds": repeats,
            "familiarity_increment": round(.35*sensitivity*(1-.5*verification)*saturation, 6),
            "sharing_increment": round(.25*sensitivity*saturation, 6),
            "sharing_disposition": round(min(.95, sharing+.25*sensitivity*saturation), 6),
            "interpretation": "合成倾向强度，不是已校准的相信或转发概率；影响日常反应，不直接决定本轮选择",
        }
    return result


def browsing_context(ob, feed):
    """Describe only the agent's actual source relationship and current exposure."""
    from model import exposure_summary
    if not feed:
        return "你正在日常浏览信息流，本轮没有展示新帖子。"
    has_source_post = any(p.get("root_content_id") == "P001" for p in feed)
    previous = exposure_summary(ob.local_physical.get("exposure_history", {}), [], ob.step)
    if has_source_post and "P001" not in previous:
        from model import NETWORK_FEED_POLICIES
        if ob.local_physical.get("feed_policy") in NETWORK_FEED_POLICIES:
            from comment_policy import LATEST_FEED_POLICY
            from comment_policy import comment_limit
            comments=(f"最新{comment_limit(ob.local_physical)}条已发布评论（截至上一轮）" if ob.local_physical.get('feed_policy')==LATEST_FEED_POLICY else "截至上一轮的完整评论")
            source = next(p for p in feed if p.get("root_content_id")=="P001")
            if source["delivery"] == "followed_source":
                return ("你正在日常刷信息流，无意间刷到自己平时喜欢阅读、已经关注的博主SOURCE发布的内容。"
                        "这是你第一次接触这条原始说法，可以打开同一原帖阅读"+comments+"。")
            return ("你正在日常刷信息流，无意间刷到自己关注的账号转发了SOURCE的一条帖子。"
                    "你没有关注SOURCE；这是你第一次接触这条原始说法。实际转发账号、时间和附言在relay_context中，"
                    "你打开原帖查看了正文及"+comments+"，不代表你此前已接触过。")
        if ob.local_physical["persona"]["group"] == "inside":
            return ("你正在日常刷信息流，无意间刷到自己平时喜欢阅读、已经关注的博主SOURCE发布的内容。"
                    "这是你在本次事件中第一次看到这条原始说法；本轮实际帖子和附言见当前观察。")
        if ob.local_physical.get("feed_policy")=="shared_rumor_all_comments_v1":
            return ("你正在日常刷公开信息流，无意间刷到SOURCE的同一条公开帖子。你没有关注SOURCE；"
                    "本实验全体用户每轮均能看到该主帖和截至上一轮的全部评论，不假设你通过某个关注账号的转发才看到。")
        return ("你正在日常刷信息流，无意间刷到自己关注的账号转发的一条帖子，原始发布者是SOURCE。"
                "你没有关注SOURCE；本轮实际接触来自当前观察中的这些帖子和附言。")
    if has_source_post:
        return ("你继续日常浏览信息流，本轮再次看到了围绕SOURCE那条原帖的内容。"
                "此前实际读到的内容见个人记忆，本轮展示见当前观察。")
    return "你继续日常浏览信息流，本轮刷到的后续帖子、附言和讨论见当前观察。"


def render_prompt(template, ob, feed, memory, include_evidence=True):
    row = ob.local_physical["persona"]
    fields = ("sex", "location", "following_count", "followers_count", "statuses_count",
              "pre_event_experience", "sharing_habit", "initial_source_evaluation", "initial_government_evaluation")
    persona = {k: row.get(k) or "未提供" for k in fields}
    persona["合成角色设定_不是真实账户事实"] = {
        k: row.get(k) or "未提供" for k in (
            "synthetic_pre_event_experience", "synthetic_sharing_habit",
            "synthetic_source_evaluation", "synthetic_government_evaluation",
            "sharing_propensity", "verification_preference", "source_prior", "government_prior",
            "repetition_sensitivity", "synthetic_persona_basis")}
    if row.get("synthetic_mbti_type"):
        persona["原账户所在地_历史快照"] = persona.pop("location", "未提供")
        persona["合成角色设定_不是真实账户事实"]["人口与人格背景"] = {
            k:row.get(k) or "未提供" for k in ("synthetic_age", "synthetic_age_band", "synthetic_region",
                "synthetic_settlement", "synthetic_occupation", "synthetic_mbti_type",
                "synthetic_mbti_preference_strengths", "synthetic_personality_description",
                "synthetic_role_experience", "synthetic_demographic_basis", "synthetic_mbti_basis")}
    assigned_trust = ob.local_physical.get("government_trust")
    assigned_source = ob.local_physical.get("source_trust")
    if assigned_source is not None:
        persona["合成角色设定_不是真实账户事实"]["source_prior"] = assigned_source
        persona["合成角色设定_不是真实账户事实"]["synthetic_source_evaluation"] = (
            f"本实验给你分配的初始SOURCE来源信任为{assigned_source:.6f}（0低1高），覆盖资料表默认来源倾向；"
            "它描述你对发布者的日常信任背景，不是对当前原始主张的相信概率；"
            "你可以倾向相信、暂时拿不准或倾向不相信。")
        if ob.local_physical.get("belief_measurement_policy") == "binary_score_gt50_v1":
            persona["合成角色设定_不是真实账户事实"]["synthetic_source_evaluation"] = (
                f"初始SOURCE来源信任为{assigned_source:.6f}（0低1高）；这是来源背景。请对当前核心说法另行给出0—100主观可信度评分。")
    if assigned_trust is not None:
        persona["合成角色设定_不是真实账户事实"]["government_prior"] = assigned_trust
        persona["合成角色设定_不是真实账户事实"]["synthetic_government_evaluation"] = f"本条件分配的政府来源接受倾向为{assigned_trust:.6f}，覆盖资料表的默认设定；它描述日常来源背景，不预设你会接受或拒绝其回应。"
    persona["关注原帖发布者"] = row["group"] == "inside"
    values = {"agent_id": ob.agent_id, "稳定个人资料": persona,
              "浏览情境": browsing_context(ob, feed),
              "判断对象": ob.local_physical.get("belief_target") or "原始帖子中的核心事实说法。",
              "当前信念": ob.local_physical["current_belief"], "个人记忆": memory or "暂无",
              "当前主观可信度": {"subjective_credibility":ob.local_physical.get("subjective_credibility"),
                               "component_credibility":ob.local_physical.get("component_credibility")},
              "当前观察": {"posts": feed, "eligible_repost_content_ids": [p["content_id"] for p in feed if p["can_repost"]]}}
    values["逐项条件应用要求"] = ""
    values["条件应用输出要求"] = ""
    if ob.local_physical.get("decision_condition_policy")=="all_conditions_v1":
        from decision_conditions import condition_inputs, condition_reference, CONDITION_LABELS
        values["逐项条件应用要求"] = (
            "【必须逐项采用的本轮条件】\n"+json.dumps(condition_inputs(ob),ensure_ascii=False)+
            "\n以上每一项都必须结合其具体取值，作用于可信度评分、是否及如何评论、是否及如何转发中的至少一项。"
            "不可用通用助手立场替代角色，不能只说‘已考虑全部条件’。年龄、地区、职业和MBTI须体现为角色的关切、处理或表达方式，"
            "不凭这些属性虚构对当前项目的事实知识或机械分配轻信分数。"
            "政府信任在未实际读到官方信息时不能让你预知官方结论；首次接触时重复效应为零；"
            "没有历史时须从真实的初始状态出发。对这些边界也要说明其如何影响本轮反应。"
            "先综合全部条件和完整已见评论区作决定，再以简短摘要记录各项应用；不要求输出详细思维过程。")
        values["条件应用输出要求"] = (
            "condition_context_ref：必须原样返回本轮输入标识 "+condition_reference(ob)+"。\n"
            "condition_application：必须恰好包含以下全部11个键："+json.dumps(CONDITION_LABELS,ensure_ascii=False)+
            "。每个键的值是{\"affects\":[\"credibility\",\"comment\",\"repost\"],\"note\":\"具体应用摘要\"}；"
            "affects只选择实际影响的项目，至少一项；note用4—60个字符说明该条件的具体取值或背景怎样作用于本轮决策，"
            "结合本人的资料，不能省略、空白、同上或只写‘已考虑’。这属于简短决策依据，不输出长篇推理。")
    prompt = template
    for k, v in values.items():
        prompt = prompt.replace("{" + k + "}", v if isinstance(v, str) else json.dumps(v, ensure_ascii=False))
    from model import exposure_summary
    summary = exposure_summary(ob.local_physical.get("exposure_history", {}), feed, ob.step)
    prompt += "\n【累计实际接触（包含本轮实际展示内容）】\n" + json.dumps(summary, ensure_ascii=False)
    prompt += "\n【本轮合成重复接触倾向】\n" + json.dumps(repetition_context(row, summary), ensure_ascii=False)
    prompt += (
        "\n重复接触倾向描述同一内容多轮出现后你的熟悉感和分享习惯变化，程度由上述个人参数决定，增量会饱和。"
        "结合本轮帖子、附言、讨论和自己的经历形成当前看法；之前的判断可以保持，也可以向任一方向改变。"
        "这些数值不要求达到某个总体相信比例，也不要求每轮转发。"
        "是否评论或分享，由你本轮的想法和日常习惯分别决定。"
        "enabled=false表示本轮没有公开转发，不会替你自动传播。")
    if include_evidence:
        from model import allowed_evidence_ids
        prompt += "\nallowed_evidence_ids=" + json.dumps(sorted(allowed_evidence_ids(feed, memory)), ensure_ascii=False) + "\nChoose evidence_ids only from this list."
    from model import FULL_THREAD_POLICIES, NETWORK_FEED_POLICIES
    from comment_policy import LATEST_FEED_POLICY,policy_instructions
    from comment_policy import comment_limit
    comment_scope=(f"每个主帖截至上一轮最新{comment_limit(ob.local_physical)}条评论" if ob.local_physical.get('feed_policy')==LATEST_FEED_POLICY else "截至上一轮的全部评论")
    if ob.local_physical.get("feed_policy") in FULL_THREAD_POLICIES:
        reading = ("只有关注SOURCE的用户初始接触原帖；其他用户通过已关注账号的转发首次接触。"
                   "接触原帖后，每轮可回看同一主帖及"+comment_scope+"；未接触者不会获得该原帖或评论。"
                   "本轮只判断当前观察中实际展示的内容，不推测未见帖子或其他用户的私下信念。"
                   if ob.local_physical.get("feed_policy") in NETWORK_FEED_POLICIES else
                   "全体用户每轮阅读同一条SOURCE主帖及其截至上一轮的全部评论。")
        prompt += ("\n【本轮阅读与评论规则】" + reading +
                   "GOVERNMENT使用自己的独立账号发帖，不是SOURCE评论区的官方回复；只有实际展示的官方正文才算你已读。"
                   "若本轮还展示了官方独立帖，其评论区与SOURCE评论区分开；转发记录不会增加同一根主帖的阅读份数。"
                   "每轮最多评论一处；comment.target_content_id明确选择当前实际展示的P001或官方主帖ID；"
                   "不评论时该字段为null。评论内容必须和所选对象相符。")
        return prompt + "\n同一root_content_id全程最多转发一次；can_repost=false时不得再次转发，但仍可判断和评论。"+policy_instructions(ob.local_physical)
    return prompt + "\n同一root_content_id全程最多转发一次；can_repost=false时不得再次转发，但仍可判断和评论。评论默认针对本轮第一条帖子。"


def prepare_prompt(template, ob, limit=32768, include_evidence=True, memory_policy="preserve", encoding="full_json_v1"):
    feed = copy.deepcopy(ob.local_information["posts"])
    memory = copy.deepcopy(ob.local_physical["memory"])
    from model import FULL_THREAD_POLICIES
    if ob.local_physical.get("feed_policy") in FULL_THREAD_POLICIES and memory_policy!="preserve":
        raise ValueError("shared thread observations and memories cannot be silently trimmed")
    if encoding!='full_json_v1':
        from compact_prompt import ENCODING,render_compact_prompt
        if encoding!=ENCODING:raise ValueError('unknown prompt encoding')
        if memory_policy!='preserve' or ob.local_physical.get('feed_policy') not in FULL_THREAD_POLICIES:
            raise ValueError('compact input requires a full-thread preserve policy')
        prompt=render_compact_prompt(template,ob,feed,memory)
        reserved=estimated_input_tokens(prompt)
        if reserved>limit:
            raise PromptBudgetPause(f'lossless_prompt_limit_exceeded: estimate={reserved}, limit={limit}; agent={ob.agent_id}, tick={ob.step}; full text and memory preserved')
        return prompt,feed,memory,reserved
    while True:
        prompt = render_prompt(template, ob, feed, memory, include_evidence)
        reserved = estimated_input_tokens(prompt)
        if reserved <= limit:
            return prompt, feed, memory, reserved
        if memory_policy == "preserve":
            raise PromptBudgetPause(f"prompt_preservation_limit_exceeded: estimate={reserved}, limit={limit}; no history or content was silently removed")
        if memory_policy != "trim_oldest":
            raise ValueError("unknown prompt memory policy")
        if memory:
            memory.pop(0)
        elif any(p["comments"] for p in feed):
            next(p for p in reversed(feed) if p["comments"])["comments"].pop()
        elif len(feed) > 1:
            feed.pop()
        else:
            raise ValueError("prompt_input_guard_exceeded_with_first_post")


import threading
_LEDGER_LOCK = threading.RLock()
_CONTEXT = threading.local()


class LiveClient:
    router = None  # Legacy single-client integrations may construct via __new__.

    @property
    def context(self):
        return getattr(_CONTEXT, "value", {})

    @context.setter
    def context(self, value):
        _CONTEXT.value = value

    def __init__(self, config, audit_dir):
        from openai import OpenAI
        from credentials import validate_credentials, load_keys, vault_path
        mode = validate_credentials(config)
        keys = load_keys() if mode == "windows_dpapi_failover" else {
            "primary": os.environ["RUMOR_LLM_API_KEY"].strip()}
        self.cfg = config
        self.audit = Path(audit_dir)
        self.cache = self.audit / "response_cache"
        self.cache.mkdir(parents=True, exist_ok=True)
        self.budget_path = self.audit / "budget.json"
        self.budget = read_json(self.budget_path) if self.budget_path.exists() else {
            "requests": 0, "input_reserved_units": 0, "output_reserved_tokens": 0,
            "actual_input_tokens": 0, "actual_output_tokens": 0, "usage_unknown_requests": 0}
        from recovery import authorization_state
        self.retry_cutoff, self.acknowledged_unknown = authorization_state(self.audit)
        import httpx
        self.context = {}
        self.clients = {slot: OpenAI(api_key=key, base_url=config["base_url"], timeout=90, max_retries=0,
            http_client=httpx.Client(event_hooks={"request": [self.on_request], "response": [self.on_response]}))
            for slot, key in keys.items()}
        self.client = self.clients["primary"]  # Preserve single-key integrations.
        self.router = None
        if mode == "windows_dpapi_failover":
            if config.get('api_routing_policy','primary_first_v1')=='round_robin_v1':
                from round_robin_router import RoundRobinKeyRouter
                self.router=RoundRobinKeyRouter(vault_path().parent/'routing-round-robin.json',self.event,
                    slots=tuple(keys),cooldown=config.get('api_key_cooldown_seconds',60),
                    quota_cooldown=config.get('api_primary_retry_seconds',3600))
                self.event('api_round_robin_enabled',api_key_slots=list(keys),
                    next_index=self.router.state['next_index'])
            else:
                from api_router import KeyRouter
                self.router = KeyRouter(vault_path().parent / "routing-state.json", self.event,
                                        interval=config.get("api_primary_retry_seconds", 3600))
                self.event("api_failover_enabled", active_slot=self.router.state["active_slot"],
                           primary_retry_seconds=config.get("api_primary_retry_seconds", 3600))

    def close(self):
        for client in self.clients.values():
            close = getattr(client, "close", None)
            if close:
                close()

    def request_history(self, signature):
        with _LEDGER_LOCK:
            self._ensure_history()
            return [(path, record) for path, record in sorted(self._history.get(signature, {}).items())]

    def _ensure_history(self):
        if not hasattr(self, "_history"):
            history = {}
            for path in self.audit.glob("request-*.json"):
                record = read_json(path)
                history.setdefault(record.get("prompt_sha256"), {})[path] = record
            self._history = history

    def save_request(self, path, record):
        with _LEDGER_LOCK:
            self._ensure_history()
            dump(path, record)  # Durable source of truth before updating the in-memory index.
            self._history.setdefault(record.get("prompt_sha256"), {})[path] = record

    def event(self, stage, **fields):
        from datetime import datetime, timezone
        with _LEDGER_LOCK:
            with (self.audit / "request-events.jsonl").open("a", encoding="utf-8") as f:
                f.write(json.dumps({"time":datetime.now(timezone.utc).isoformat(), **getattr(self,"context",{}),
                                   "stage":stage, **fields}, ensure_ascii=True)+"\n")
                f.flush()
                os.fsync(f.fileno())

    @property
    def gate(self):
        from throttle import RateGate
        with _LEDGER_LOCK:
            if not hasattr(self, "_gate"):
                self._gate = RateGate(self.cfg, self.audit, self.event)
            return self._gate

    def rate_refusal(self, failures, diagnostic):
        if failures > self.cfg.get("rate_limit_max_retries", 6):
            self.event("rate_limit_exhausted", failures=failures)
            self.gate.halt()
            raise QuotaPause("Rate-limit retries exhausted; outcomes cached, no agent dropout")
        self.gate.limited(failures, diagnostic.get("retry_after_seconds"))

    def on_request(self, request):
        self.event("http_dispatch")

    def on_response(self, response):
        from throttle import safe_response_metadata
        self.event("response_headers_received", http_status=response.status_code, **safe_response_metadata(response))

    def record_output_failure(self, path, ob, signature, generation, diagnostic):
        dump(self.audit/"validation"/path.name,{"status":"format_error","error_type":"ValueError",
            "generation_attempt":generation,"prompt_sha256":signature,"diagnostic":diagnostic,"retry_policy":RETRY_POLICY})
        self.event("validation_failed",generation_attempt=generation,diagnostic=diagnostic)

    def output_exhausted(self, ob, generations, diagnostic):
        if self.cfg.get("decision_condition_policy")=="all_conditions_v1":
            raise OutputContractPause(ob.agent_id,ob.step,generations,diagnostic or {"code":"response_validation_failed"})
        raise FormatAttemptsExhausted(f"Format generation limit reached ({generations}); preserved for review")

    def base_prompt_limit(self, template):
        # Logical/cache identity retains the original v1 prompt. Only the actual
        # wire prompt is sent, counted, reserved and checked against the user cap.
        if self.cfg.get('wire_prompt_style','standard') in ('concise_lossless_v1','concise_shared_prefix_v1'):
            from concise_wire import validate_template
            validate_template(template)
            return 2_000_000
        return self.cfg.get('prompt_input_token_limit',4096)

    def preflight_batch(self, observations, template):
        """Check the entire frozen tick BEFORE any API call; never reserve twice."""
        if self.cfg.get('prompt_encoding','full_json_v1')!='lossless_thread_refs_v1':return
        options=request_options(self.cfg)
        planned=[];cached=0;unknown=[]
        for ob in observations:
            if ob.local_physical['persona']['decision_mode']!='llm' or not ob.local_information['posts']:continue
            self.base_prompt_limit(template)
            prompt,feed,memory,_=prepare_prompt(template,ob,limit=2_000_000,memory_policy='preserve',encoding='lossless_thread_refs_v1')
            sig=digest({'prompt':prompt,'model':self.cfg['model'],'base_url':self.cfg['base_url'],
                        'request_options':options,'agent_id':ob.agent_id,'step':ob.step})
            cache=self.cache/f'{sig}.json'
            if cache.exists():
                validate_response(read_json(cache)['answer'],ob,feed,memory);cached+=1;continue
            feedback=None;recovered=False
            for path,record in self.request_history(sig):
                if record.get('status')=='pending_usage_unknown':
                    if (path.name,sig) not in getattr(self,'acknowledged_unknown',set()):unknown.append(path.name)
                elif record.get('status')=='response_received':
                    feedback=response_envelope_diagnostic(record)
                    if feedback is None:
                        try:parse_and_validate(record['raw_response'],ob,feed,memory);recovered=True;break
                        except ValueError:feedback=validation_diagnostic(record['raw_response'],ob,feed,memory)
            if recovered:cached+=1;continue
            planned.append({'agent_id':ob.agent_id,'input_reserved_units':estimated_input_tokens(
                wire_prompt(prompt,ob,options['max_tokens'],feedback,style=self.cfg.get('wire_prompt_style','standard')))})
        tick=observations[0].step if observations else 0
        b=self.budget
        report={'tick':tick,'prompt_encoding':'lossless_thread_refs_v1','cached_or_recoverable':cached,
            'minimum_new_requests':len(planned),'minimum_new_input_reservation':sum(x['input_reserved_units'] for x in planned),
            'minimum_new_output_reservation':len(planned)*options['max_tokens'],
            'maximum_single_input':max((x['input_reserved_units'] for x in planned),default=0),
            'wire_prompt_style':self.cfg.get('wire_prompt_style','standard'),
            'remaining_input_reservation':self.cfg['max_input_reserved_units']-max(b['input_reserved_units'],b['actual_input_tokens']),
            'requests':planned,'unknown_outcomes':unknown,
            'note':'Minimum one generation per unresolved decision; retries still consume the same shared hard budget. No reservation or API request made by preflight.'}
        dump(self.audit/f'preflight-tick-{tick:03d}.json',report)
        print(f"Preflight tick={tick}: cached={cached}, new={len(planned)}, max_input={report['maximum_single_input']}, minimum_input={report['minimum_new_input_reservation']}, remaining_input={report['remaining_input_reservation']}",flush=True)
        if unknown:raise UncertainRequest('Whole-tick preflight found unresolved request outcomes; review before reissue')
        if report['maximum_single_input']>self.cfg['prompt_input_token_limit']:
            raise PromptBudgetPause(f"whole_tick_input_limit: tick={tick}, maximum_estimate={report['maximum_single_input']}, limit={self.cfg['prompt_input_token_limit']}; no API dispatched for this tick; full text preserved")
        if (b['requests']+len(planned)>self.cfg['max_requests'] or
            report['minimum_new_input_reservation']>report['remaining_input_reservation'] or
            b['output_reserved_tokens']+report['minimum_new_output_reservation']>self.cfg['max_output_reserved_tokens']):
            raise HardBudgetPause(f"whole_tick_minimum_budget: tick={tick}, required_input={report['minimum_new_input_reservation']}, remaining_input={report['remaining_input_reservation']}; no new request dispatched for this tick")


    def decide(self, ob, template):
        prompt_limit=self.cfg.get("prompt_input_token_limit",4096)
        memory_policy=self.cfg.get("prompt_memory_policy","trim_oldest")
        base_limit=self.base_prompt_limit(template)
        prompt, feed, memory, reserved = prepare_prompt(template, ob, limit=base_limit, memory_policy=memory_policy,encoding=self.cfg.get('prompt_encoding','full_json_v1'))
        options = request_options(self.cfg)
        signature = digest({"prompt": prompt, "model": self.cfg["model"], "base_url": self.cfg["base_url"],
                            "request_options": options,
                            "agent_id": ob.agent_id, "step": ob.step})
        # Preserve exact prior prompts, cached responses and generation counts.
        legacy = prepare_prompt(template, ob, limit=base_limit, include_evidence=False, memory_policy=memory_policy,encoding=self.cfg.get('prompt_encoding','full_json_v1'))
        legacy_signature = digest({"prompt": legacy[0], "model": self.cfg["model"], "base_url": self.cfg["base_url"],
                                   "request_options": options, "agent_id": ob.agent_id, "step": ob.step})
        if self.request_history(legacy_signature):
            prompt, feed, memory, reserved = legacy
            signature = legacy_signature
        history = self.request_history(signature)
        cutoff = getattr(self, "retry_cutoff", 0)
        def fresh(record):
            return not (0 < record.get("request_number", 0) <= cutoff)
        prior = [record for _, record in history if fresh(record)]
        self.context = {"agent_id":ob.agent_id, "tick":ob.step, "prompt_sha256":signature}
        self.event("decision_start", memory_ticks=[m["tick"] for m in memory],
                   observed_ids=[p["content_id"] for p in feed], prompt_chars=len(prompt))
        cache_path = self.cache / f"{signature}.json"
        if cache_path.exists():
            saved = read_json(cache_path)
            validate_response(saved["answer"], ob, feed, memory)
            self.event("cache_reused")
            return saved["answer"], feed, {**saved["metadata"], "cached": True}
        # A restart alone never resets limits. An explicit recovery authorization
        # opens a fresh bounded window, while retaining every reservation/record.
        generations = 0
        max_generations = int(self.cfg.get("format_max_attempts", 4))
        contract = self.cfg.get("decision_condition_policy")=="all_conditions_v1"
        last_diagnostic = None
        for previous, saved in history:
            if saved.get("prompt_sha256") != signature:
                continue
            if saved.get("status") == "response_received" and contract:
                envelope=response_envelope_diagnostic(saved)
                if envelope:
                    if not fresh(saved):continue
                    generations+=1
                    last_diagnostic=envelope
                    self.record_output_failure(previous,ob,signature,generations,envelope)
                    if not envelope.get('retryable',True):
                        raise OutputContractPause(ob.agent_id,ob.step,generations,envelope)
                    continue
            if saved.get("status") == "response_received" and saved.get("finish_reason") == "stop":
                if fresh(saved):
                    generations += 1
                try:
                    answer = parse_and_validate(saved["raw_response"], ob, feed, memory)
                except ValueError as exc:
                    if not fresh(saved):
                        continue  # Human authorized another generation; raw response retained.
                    if not contract and not is_format_error(exc):
                        raise
                    last_diagnostic=validation_diagnostic(saved["raw_response"],ob,feed,memory)
                    self.record_output_failure(previous,ob,signature,generations,last_diagnostic)
                    continue
                recovered = {k: v for k, v in saved.items() if k not in ("prompt", "raw_response", "base_prompt")}
                if answer.get('output_syntax_repairs'):
                    recovered['syntax_repaired']=True
                    self.event('saved_response_syntax_recovered',source_request=previous.name,
                        syntax_version=answer['output_syntax_repairs']['version'])
                    print(f"Saved response reused: {ob.agent_id} tick={ob.step}, punctuation repaired; no new API request.",flush=True)
                dump(cache_path, {"answer": answer, "metadata": recovered, "validation_status": "valid"})
                return answer, feed, {**recovered, "cached": True}
            if saved.get("status") == "pending_usage_unknown":
                if (previous.name, signature) in getattr(self, "acknowledged_unknown", set()):
                    continue
                raise UncertainRequest("Request outcome unknown; inspect audit before explicitly authorizing reissue")
            if saved.get("status") == "response_received":
                if not fresh(saved):
                    continue
                raise ValueError("LLM empty/refused/truncated response; no state committed")
        failed_transport = [r for r in prior if r.get("prompt_sha256") == signature
            and r.get("status") == "request_error"
            and r.get("diagnostic", {}).get("exception_type") in ("APITimeoutError", "APIConnectionError")]
        if not self.router and len(failed_transport) >= 2:
            self.event("persisted_transport_exhausted", failures=len(failed_transport))
            raise AgentRequestFailure("Persisted repeated transport failure")
        if generations >= max_generations:
            self.output_exhausted(ob,generations,last_diagnostic)
        rate_failures = sum(r.get("prompt_sha256") == signature and (
            r.get("status") == "quota_paused" or
            (r.get("status") == "request_error" and (
                r.get("diagnostic", {}).get("status_code") in (429, 529) or
                r.get("diagnostic", {}).get("service_status_code") in (1002, 2056))))
            and not (self.router and r.get("api_key_slot") == "primary") for r in prior)
        if rate_failures > self.cfg.get("rate_limit_max_retries", 6):
            self.gate.halt()
            raise QuotaPause("Persisted rate-limit retry allowance exhausted")
        transport_retries = 0
        refused_slots=set()
        while generations < max_generations:
            sent_prompt=wire_prompt(prompt,ob,options['max_tokens'],last_diagnostic,style=self.cfg.get('wire_prompt_style','standard'))
            reserved=estimated_input_tokens(sent_prompt)
            if reserved>prompt_limit:
                raise PromptBudgetPause(f"prompt_preservation_limit_exceeded: estimate={reserved}, limit={prompt_limit}; agent={ob.agent_id}, tick={ob.step}; complete input and output protocol preserved")
            prompt_record={'prompt':sent_prompt}
            if contract:prompt_record['base_prompt']=prompt
            with self.gate.slot():
                if self.router and getattr(self.router,'is_round_robin',False):
                    from round_robin_router import NoUsableKey
                    try:route=self.router.acquire(exclude=refused_slots)
                    except NoUsableKey as exc:
                        self.gate.halt()
                        self.event('all_api_slots_unavailable',earliest_retry_at=exc.retry_at)
                        raise QuotaPause('All configured API slots unavailable; checkpoints, cache and budgets preserved') from None
                else:
                    route = self.router.acquire() if self.router else None
                api_slot = route.slot if route else "primary"
                with _LEDGER_LOCK:
                    b = self.budget
                    if (b["requests"] >= self.cfg["max_requests"] or
                        max(b["input_reserved_units"], b["actual_input_tokens"]) + reserved > self.cfg.get("max_input_reserved_units",49_971_200) or
                        b["output_reserved_tokens"] + options["max_tokens"] > self.cfg.get("max_output_reserved_tokens",6_246_400)):
                        if self.router:
                            self.router.abort(route)
                        raise HardBudgetPause("LLM hard budget reached; preserve completed steps")
                    b["requests"] += 1
                    b["input_reserved_units"] += reserved
                    b["output_reserved_tokens"] += options["max_tokens"]
                    dump(self.budget_path, b)  # persist BEFORE dispatch, including process interruption
                    metadata = dict(agent_id=ob.agent_id, tick=ob.step, attempt=generations + 1,
                        format_max_attempts=max_generations,
                        request_number=b["requests"], requested_model=self.cfg["model"],
                        api_key_slot=api_slot, primary_probe=bool(route and route.probe and api_slot=='primary'),
                        api_key_recovery_probe=bool(route and route.probe),
                        api_routing_policy=self.cfg.get('api_routing_policy','primary_first_v1'),
                        prompt_sha256=signature, input_reserved_units=reserved,
                        actual_prompt_sha256=hashlib.sha256(sent_prompt.encode('utf-8')).hexdigest(),
                        response_retry_policy=RETRY_POLICY if contract else "legacy",
                        prompt_encoding=self.cfg.get('prompt_encoding','full_json_v1'),
                        wire_prompt_style=self.cfg.get('wire_prompt_style','standard'),
                        output_retry_diagnostic=last_diagnostic,
                        request_options=options,
                        input_count_method="cl100k_base_estimate_15percent_plus64_not_minimax_tokenizer",
                        trimmed_memory_count=len(ob.local_physical["memory"]) - len(memory),
                        trimmed_post_count=len(ob.local_information["posts"]) - len(feed),
                        trimmed_comment_count=sum(len(p["comments"]) for p in ob.local_information["posts"]) - sum(len(p["comments"]) for p in feed),
                        used_memory_ticks=[m["tick"] for m in memory], cached=False)
                    print(f"LLM request {b['requests']}: tick={ob.step}, agent={ob.agent_id}, memory={len(memory)}, key={api_slot}", flush=True)
                    audit_path = self.audit / f"request-{b['requests']:06d}.json"
                    self.context["request_number"] = b["requests"]
                    self.context["api_key_slot"] = api_slot
                    self.event("request_start", generation_attempt=generations+1, transport_retry=transport_retries)
                    started = time.monotonic()
                    self.save_request(audit_path, {**metadata, "status": "pending_usage_unknown", **prompt_record})
                try:
                    active_client = self.clients[api_slot] if self.router else self.client
                    response = active_client.chat.completions.create(
                        model=self.cfg["model"], messages=[{"role": "user", "content": sent_prompt}],
                        **options)
                except Exception as exc:
                    with _LEDGER_LOCK:
                        b["usage_unknown_requests"] += 1
                        dump(self.budget_path, b)
                    status = getattr(exc, "status_code", None)
                    code = getattr(exc, "code", None)
                    body = getattr(exc, "body", None)
                    service_code = body.get("base_resp", {}).get("status_code") if isinstance(body, dict) and isinstance(body.get("base_resp"), dict) else None
                    if not isinstance(service_code, int):
                        service_code = None
                    # Whitelist machine-safe codes only: no raw headers, exception text or body.
                    code = code if isinstance(code, str) and not code.startswith("sk-") and re.fullmatch(r"[a-zA-Z0-9_.-]{1,80}", code) else None
                    diagnostic = dict(exception_type=type(exc).__name__, status_code=status,
                                      error_code=code, service_status_code=service_code, elapsed_seconds=round(time.monotonic() - started, 3))
                    from throttle import safe_response_metadata
                    diagnostic.update(safe_response_metadata(getattr(exc, "response", None)))
                    # Categories only, never arbitrary provider message/body text.
                    body_text = json.dumps(body, ensure_ascii=False, default=str).lower() if body is not None else ""
                    diagnostic["provider_hints"] = [label for label, terms in {
                        "request_rate": ("rpm", "requests per minute", "请求频率"),
                        "token_rate": ("tpm", "tokens per minute"),
                        "concurrency": ("concurrency", "concurrent", "并发"),
                        "quota_or_balance": ("quota", "balance", "余额", "额度")
                    }.items() if any(term in body_text for term in terms)]
                    diagnostic["response_body_available"] = body is not None
                    chain = []
                    node = exc
                    while node is not None and len(chain) < 8 and id(node) not in [x[0] for x in chain]:
                        chain.append((id(node), type(node).__name__))
                        node = node.__cause__ or node.__context__
                    diagnostic["exception_chain"] = [x[1] for x in chain]
                    diagnostic["timeout_phase"] = next((x[1] for x in chain if x[1] in ("ConnectTimeout", "ReadTimeout", "WriteTimeout", "PoolTimeout")), "unknown")
                    self.gate.failed()
                    self.event("request_error", **diagnostic)
                    self.save_request(audit_path, {**metadata, "status": "request_error", "diagnostic": diagnostic,
                                      **prompt_record})
                    if self.router:
                        from api_router import can_switch
                        rotated=getattr(self.router,'is_round_robin',False)
                        if rotated and self.router.switchable(diagnostic):refused_slots.add(api_slot)
                        can_retry=self.router.failed(route, diagnostic)
                        if can_retry:
                            # A known refusal consumes a request reservation but
                            # does not consume a JSON generation attempt. The
                            # next route is backup, or a recovered primary.
                            continue
                        if rotated and self.router.switchable(diagnostic):
                            self.gate.halt()
                            raise QuotaPause('All configured API slots unavailable; preserve completed steps') from None
                        if api_slot == "backup" and can_switch(diagnostic):
                            self.gate.halt()
                            raise QuotaPause("Backup API unavailable while primary circuit is open; preserve completed steps") from None
                        if type(exc).__name__ in ("APITimeoutError", "APIConnectionError"):
                            # The provider may already be generating/charging.
                            # Retain an explicit unresolved record instead of
                            # silently repeating this decision on another key.
                            self.save_request(audit_path, {**metadata, "status": "pending_usage_unknown",
                                              "diagnostic": diagnostic, **prompt_record})
                            raise UncertainRequest("Dispatched API outcome unknown; inspect audit before explicitly authorizing reissue") from None
                    if status in (429, 529) or service_code in (1002, 2056):
                        rate_failures += 1
                        self.rate_refusal(rate_failures, diagnostic)
                        continue
                    retryable = status in (429, 500, 502, 503, 504) or type(exc).__name__ in ("APITimeoutError", "APIConnectionError")
                    # Unknown 570 is NOT automatically treated as transient.
                    if transport_retries == 0 and retryable:
                        transport_retries += 1
                        time.sleep(1)
                        continue
                    if type(exc).__name__ in ("APITimeoutError", "APIConnectionError"):
                        raise AgentRequestFailure("Repeated transport failure") from None
                    hint = " Authentication failed: re-enter the API key and check its issuing platform/endpoint." if status == 401 else ""
                    raise RuntimeError(
                        f"LLM request failed: HTTP {status}, {type(exc).__name__}."
                        f"{hint} Diagnostic: {audit_path}"
                    ) from None
                self.event("response_body_received", elapsed_seconds=round(time.monotonic()-started,3))
                usage = response.usage
                base = getattr(response, "base_resp", None)
                service_error = base.get("status_code") if isinstance(base, dict) else None
                if isinstance(service_error, int) and service_error != 0:
                    with _LEDGER_LOCK:
                        b["usage_unknown_requests"] += 1
                        dump(self.budget_path, b)
                    diagnostic = {"status_code": 200, "service_status_code": service_error}
                    if not self.router and service_error in (1002, 2056):
                        # Keep the original single-key audit/replay contract.
                        self.save_request(audit_path, {**metadata, "status": "quota_paused", "service_status_code": service_error})
                    else:
                        self.save_request(audit_path, {**metadata, "status": "request_error", "diagnostic": diagnostic, **prompt_record})
                    self.gate.failed()
                    self.event("provider_error", **diagnostic)
                    if self.router:
                        from api_router import can_switch
                        rotated=getattr(self.router,'is_round_robin',False)
                        if rotated and self.router.switchable(diagnostic):refused_slots.add(api_slot)
                        can_retry=self.router.failed(route, diagnostic)
                        if can_retry:
                            continue
                        if rotated and self.router.switchable(diagnostic):
                            self.gate.halt()
                            raise QuotaPause('All configured API slots unavailable; preserve completed steps')
                        if api_slot == "backup" and can_switch(diagnostic):
                            self.gate.halt()
                            raise QuotaPause("Backup API unavailable while primary circuit is open; preserve completed steps")
                    if service_error in (1002, 2056):
                        rate_failures += 1
                        self.rate_refusal(rate_failures, diagnostic)
                        continue
                    raise RuntimeError(f"MiniMax service error {service_error}; inspect local request audit")
                if self.router:
                    self.router.succeeded(route)
                refused_slots.clear()
                it = getattr(usage, "prompt_tokens", None)
                ot = getattr(usage, "completion_tokens", None)
                with _LEDGER_LOCK:
                    if it is not None and ot is not None:
                        b["actual_input_tokens"] += it
                        b["actual_output_tokens"] += ot
                        # Reservations remain a conservative spending guard, not reported usage.
                    else:
                        b["usage_unknown_requests"] += 1
                    dump(self.budget_path, b)
                metadata.update(returned_model=response.model, actual_input_tokens=it, actual_output_tokens=ot,
                                elapsed_seconds=round(time.monotonic() - started, 3))
                # Record provider cache accounting without changing spending guards.
                details = getattr(usage, 'prompt_tokens_details', None)
                output_details = getattr(usage, 'completion_tokens_details', None)
                def detail_value(source, key):
                    value = source.get(key) if isinstance(source, dict) else getattr(source, key, None)
                    return value if type(value) is int and value >= 0 else None
                metadata['cached_input_tokens'] = detail_value(details, 'cached_tokens')
                metadata['reasoning_output_tokens'] = detail_value(output_details, 'reasoning_tokens')
                choice = response.choices[0] if response.choices else None
                message=getattr(choice,'message',None)
                text = getattr(message,'content',None)
                response_record={**metadata, "status": "response_received", **prompt_record,
                    "raw_response":text,"finish_reason":getattr(choice,"finish_reason",None),
                    "refusal_present":bool(getattr(message,'refusal',None))}
                self.save_request(audit_path,response_record)
                if contract:
                    generations+=1
                    last_diagnostic=response_envelope_diagnostic(response_record)
                    if last_diagnostic:
                        self.gate.failed()
                        self.record_output_failure(audit_path,ob,signature,generations,last_diagnostic)
                        if not last_diagnostic.get('retryable',True):
                            raise OutputContractPause(ob.agent_id,ob.step,generations,last_diagnostic)
                        if generations>=max_generations:self.output_exhausted(ob,generations,last_diagnostic)
                        print(f"Output retry: {ob.agent_id} tick={ob.step}, reason={ERROR_LABELS.get(last_diagnostic['code'],last_diagnostic['code'])}, next attempt={generations+1}/{max_generations}",flush=True)
                        continue
                if choice is None or choice.finish_reason != "stop" or not text:
                    self.gate.failed()
                    raise ValueError("LLM empty/refused/truncated response; no state committed")
                if not contract:generations += 1
                try:
                    answer = parse_and_validate(text, ob, feed, memory)
                except ValueError as exc:
                    self.gate.failed()
                    self.event("validation_failed", error_type=type(exc).__name__, retryable=is_format_error(exc))
                    if not contract and not is_format_error(exc):
                        raise
                    last_diagnostic=validation_diagnostic(text,ob,feed,memory)
                    self.record_output_failure(audit_path,ob,signature,generations,last_diagnostic)
                    if generations >= max_generations:
                        self.output_exhausted(ob,generations,last_diagnostic)
                    print(f"Format retry: {ob.agent_id} tick={ob.step}, reason={ERROR_LABELS.get(last_diagnostic['code'],last_diagnostic['code'])}, next attempt={generations + 1}/{max_generations}", flush=True)
                    continue
                self.event("validation_passed")
                if answer.get('output_syntax_repairs'):
                    metadata['syntax_repaired']=True
                    self.event('response_syntax_repaired',syntax_version=answer['output_syntax_repairs']['version'])
                dump(cache_path, {"answer": answer, "metadata": metadata, "validation_status": "valid"})
                self.gate.succeeded()
                return answer, feed, metadata
        raise RuntimeError("unreachable")
