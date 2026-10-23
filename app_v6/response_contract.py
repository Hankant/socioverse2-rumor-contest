"""Bounded output protocol and precise retry feedback. No evidence is removed."""
import json
from decision_conditions import CONDITION_LABELS, CONDITION_POLICY

RETRY_POLICY = "bounded-output-feedback-v3"
ERROR_LABELS = {
    "truncated_output": "输出达到长度上限，被截断",
    "empty_response": "接口返回空正文或没有选择项",
    "invalid_json": "JSON语法错误",
    "json_root_not_object": "JSON根节点必须为对象",
    "condition_coverage_or_note_invalid": "11项条件或其摘要格式不完整",
    "conflicting_condition_aliases": "同义字段内容冲突",
    "invisible_evidence": "引用了不可见或无效的证据ID",
    "invisible_comment_target": "评论对象不可见",
    "invisible_repost_target": "转发对象不可见",
    "invalid_score": "评分字段格式或范围无效",
    "invalid_action_schema": "评论或转发字段结构无效",
    "empty_comment": "启用评论时正文为空",
    "provider_refusal": "供应商明确拒绝生成，需检查而非盲目重试",
    "unexpected_finish_reason": "接口未正常结束生成",
    "response_validation_failed": "回答未通过结构校验",
}


def response_envelope_diagnostic(record):
    finish=record.get("finish_reason")
    if record.get("refusal_present") or finish=="content_filter":
        return {"code":"provider_refusal","retryable":False}
    if finish=="length":
        return {"code":"truncated_output","finish_reason":"length","retryable":True}
    text=record.get("raw_response")
    if not isinstance(text,str) or not text.strip():
        return {"code":"empty_response","retryable":True}
    if finish!="stop":
        return {"code":"unexpected_finish_reason","retryable":True}
    return None


def output_structure(ob):
    from decision_conditions import condition_reference
    return {'condition_context_ref':condition_reference(ob),'subjective_credibility':None,
        'component_credibility':{'funds_redirected':None,'safety_delayed':None,'causal_link':None},
        'comment':{'enabled':None,'target_content_id':None,'text':''},
        'repost':{'enabled':None,'target_content_id':None,'text':''},'evidence_ids':[],
        'condition_application':{key:{'affects':[],'note':''} for key in CONDITION_LABELS}}


def wire_prompt(base_prompt, ob, max_tokens, diagnostic=None, style='standard'):
    from concise_wire import STYLES, SHARED_PREFIX_STYLE
    if style in STYLES:
        from concise_wire import concise_prompt
        base_prompt=concise_prompt(base_prompt,ob,shared_prefix=style==SHARED_PREFIX_STYLE)
    elif style!='standard':
        raise ValueError('unknown wire prompt style')
    if ob.local_physical.get("decision_condition_policy")!=CONDITION_POLICY:
        return base_prompt
    suffix=("\n【机器输出协议：仅限制回答结构，不改变角色判断】"
        "只输出一个完整JSON对象，不输出Markdown或解释文字。"
        "先完整阅读上面的全部帖子、评论和个人条件，再自行决定分数、评论和转发；本协议不减少任何阅读内容。"
        "evidence_ids只选择0至6个最相关且实际可见的ID，不要复制完整白名单，也不要列举所有评论ID。"
        "11项condition_application全部保留，每项note为4至60字符，建议8至24字符；简洁表达，确保JSON完整结束。"
        "comment/repost启用时使用本轮实际可见的对象；不启用时正文为空、对象为null。"
        "评分用0至100的JSON数字；不凭程序提示预设分数或行动。"
        f"本次输出上限仍为{max_tokens} tokens，不会自动扩大预算。")
    suffix+=("\n【完整JSON结构模板，仅示意结构，不是本轮答案】"
        "下面的分数null、enabled:null和条件空占位必须用你本人的决定替换；不预设任何分数、评论或转发比例。"
        "字段名一律双引号。condition_context_ref放在根对象前部，condition_application为最后一个根字段；"
        "11项说明完成后再关闭根对象，不要在根对象外追加字段或逗号。\n"
        +json.dumps(output_structure(ob),ensure_ascii=False,separators=(',',':')))
    root_ids=[p['content_id'] for p in ob.local_information['posts']]
    suffix+=("\n可直接引用的本轮可见主帖ID："+json.dumps(root_ids,ensure_ascii=False)+
        "。评论证据请复制当前表中实际comment_id，不猜编号；原帖发布时间不是评论发布时间。")
    if diagnostic:
        safe={k:diagnostic[k] for k in ("code","missing_conditions","invalid_note_conditions","invalid_condition_fields","line","column","parse_error","invalid_evidence_ids") if k in diagnostic}
        suffix+=("\n【上次输出结构失败，请有针对性地改正】"+json.dumps(safe,ensure_ascii=False)+
                 "\n这不是新的事件材料，不要编造缺失证据；在相同角色和完整观察下重新返回完整JSON。"
                 "condition_application的规定键为："+json.dumps(list(CONDITION_LABELS),ensure_ascii=False)+
                 "。不得省略真实条件摘要；不得用抄写所有证据ID代替11项说明。")
        if diagnostic.get('code')=='invisible_evidence':
            from model import allowed_evidence_ids
            suffix+=("\n这次可使用的精确证据ID（来自相同已见材料）："+
                json.dumps(sorted(allowed_evidence_ids(ob.local_information['posts'],ob.local_physical['memory'])),ensure_ascii=False,separators=(',',':'))+
                "。只选0—6个相关项；未列出的ID不得使用，不得把行号当ID。")
    return base_prompt+suffix
