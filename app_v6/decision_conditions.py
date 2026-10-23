"""Require all assigned conditions in the prompt and a short application audit.

Coverage is structurally verifiable. Self-reported notes do not prove that every
input caused a nonzero change in the model's output; no artificial score weights
or demographic belief probabilities are introduced here.
"""
import copy
import math
from model import digest

CONDITION_POLICY = "all_conditions_v1"
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


def scripted_condition_application(ob):
    """Artificial schema exercise only; never a substitute for a live response."""
    return {
        "condition_context_ref": condition_reference(ob),
        "condition_application": {key: {"affects": ["credibility", "comment", "repost"],
            "note": "离线固定测试：读取" + label + "；本说明不是真实LLM判断依据"}
            for key, label in CONDITION_LABELS.items()},
    }
