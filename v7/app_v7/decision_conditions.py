"""Require all assigned conditions in the prompt and a short application audit.

Coverage is structurally verifiable. Self-reported notes do not prove that every
input caused a nonzero change in the model's output; no artificial score weights
or demographic belief probabilities are introduced here.
"""
import copy
import math
from model import digest

CONDITION_POLICY = "all_conditions_v1"
TRUST_DECISION_INSTRUCTIONS = """【来源信任：必须落实到评分与行动】
两种信任是本轮决策的关键差异变量，不是可略过的资料。使用本人0—1具体取值（0低、0.5中、1高）决定来源说服力。
SOURCE来源信任（source_prior/source_trust）：其他条件和已见材料相同时，较高值应使你更愿意接受博主对具体事实的叙述，给其陈述更大可信权重；较低值应降低该来源的说服力。材料未独立核实不等于所有人的来源信任差异都失效，不用统一怀疑立场覆盖个人高低信任。
政府来源信任（government_prior/government_trust）：实际读到官方回应后，较高值应使你更愿意接受其核查、解释和否认；官方否认调资且没有更强的已见反证时，对原调资说法的评分通常应向不成立方向调整。较低值减弱官方自述的说服力，可以保留原判断。未读到官方回应时，此项尚未触发对回应的接受，不能预知其结论。
两来源冲突时，比较本人对双方的信任和实际已见内容，形成不同的证据权重，再决定评分、评论与转发。充分反证或两种影响抵消可以使本轮分数不变；不得仅因账号标签统一采信，也不把信任值乘100当作主张评分，不机械加减固定分。
subjective_credibility始终衡量“安全整改资金调去商业街并导致安全整改延后”成立的程度，不是官方回应可信度或居民安全诉求的合理性。更接受官方否认通常对应原主张评分降低，不能把对官方的高信任填成原主张的高分。
在source_trust与government_trust的note中分别简述本人具体信任值（可简写到2—3位小数）及其提高、降低、抵消或尚未触发的作用；提交前核对摘要与评分对象、方向一致。只需简短应用摘要，不输出长篇推理。"""
CONDITION_LABELS = {
    "age": "年龄",
    "region": "居住地区与居住环境",
    "occupation": "职业",
    "community_experience": "社区工程经历与事前经历",
    "mbti_preferences": "MBTI风格与个体偏好强度",
    "source_trust": "SOURCE来源信任",
    "government_trust": "政府来源信任",
    "verification_preference": "核验偏好",
    "sharing_propensity": "分享倾向与分享习惯",
    "repetition_sensitivity": "重复接触敏感度与实际接触记录",
    "history_and_memory": "既往状态、评分和个人记忆",
}


def condition_inputs(ob):
    p = ob.local_physical
    row = p["persona"]

    def text(field):
        value = row.get(field)
        if not isinstance(value, str) or not value.strip():
            raise ValueError("missing assigned decision condition: " + field)
        return value

    def number(field, override=None):
        value = row.get(field) if override is None else override
        try:
            value = float(value)
        except (ValueError, TypeError):
            raise ValueError("missing assigned decision condition: " + field) from None
        if not math.isfinite(value) or not 0 <= value <= 1:
            raise ValueError("invalid assigned decision condition: " + field)
        return value

    from model import exposure_summary
    feed = ob.local_information["posts"]
    summary = exposure_summary(p.get("exposure_history", {}), feed, ob.step)
    result = {
        "age": int(text("synthetic_age")),
        "region": {"region": text("synthetic_region"), "settlement": text("synthetic_settlement")},
        "occupation": text("synthetic_occupation"),
        "community_experience": {"community": text("synthetic_role_experience"),
                                 "prior_experience": text("synthetic_pre_event_experience")},
        "mbti_preferences": {"type": text("synthetic_mbti_type"),
                             "strengths": text("synthetic_mbti_preference_strengths"),
                             "description": text("synthetic_personality_description")},
        "source_trust": number("source_prior", p.get("source_trust")),
        "government_trust": number("government_prior", p.get("government_trust")),
        "verification_preference": number("verification_preference"),
        "sharing_propensity": {"value": number("sharing_propensity"), "habit": text("synthetic_sharing_habit")},
        "repetition_sensitivity": {"value": number("repetition_sensitivity"), "actual_exposure": summary},
        "history_and_memory": {"current_belief": p["current_belief"],
                               "previous_score": p.get("subjective_credibility"),
                               "memory_ticks": [m["tick"] for m in p["memory"]],
                               "memory_sha256": digest(p["memory"]),
                               "complete_memory_section": "个人记忆"},
    }
    from memory_policy import ROLLING
    if p.get('memory_retention_policy') == ROLLING:
        result['history_and_memory'].update(retention_policy=ROLLING, window_ticks=p['memory_window_ticks'])
    from belief_dynamics import UPDATE_POLICY
    if p.get('belief_update_policy')==UPDATE_POLICY:
        result['history_and_memory'].update(belief_update_policy=UPDATE_POLICY,
            score_field='subjective_credibility',update_context_section='本轮合成重复接触倾向.belief_update_context')
    if p.get('government_trust_prompt_policy')=='individual_three_level_v1':
        result['history_and_memory']['government_trust_prompt_policy']=p['government_trust_prompt_policy']
    return result


def condition_reference(ob):
    return digest(condition_inputs(ob))[:16]


def validate_condition_application(answer, ob):
    """Require each current input to have an explicit, bounded application note."""
    if ob.local_physical.get("decision_condition_policy") != CONDITION_POLICY:
        return
    usage = answer.get("condition_application")
    if (answer.get("condition_context_ref") != condition_reference(ob)
            or not isinstance(usage, dict) or set(usage) != set(CONDITION_LABELS)):
        raise ValueError("invalid decision condition coverage")
    for item in usage.values():
        if (not isinstance(item, dict) or set(item) != {"affects", "note"}
                or not isinstance(item["affects"], list) or not item["affects"]
                or any(not isinstance(x, str) for x in item["affects"])
                or len(item["affects"]) != len(set(item["affects"]))
                or any(x not in ("credibility", "comment", "repost") for x in item["affects"])
                or not isinstance(item["note"], str) or not 4 <= len(item["note"].strip()) <= 60
                or item["note"].strip() in ("已经考虑所有条件", "同上已考虑", "已考虑该条件")):
            raise ValueError("invalid decision condition coverage")
    from comment_policy import PARTICIPATION_POLICY
    if (ob.local_physical.get('comment_participation_policy')==PARTICIPATION_POLICY
            and 'comment' not in usage['mbti_preferences']['affects']):
        raise ValueError("invalid decision condition coverage")


