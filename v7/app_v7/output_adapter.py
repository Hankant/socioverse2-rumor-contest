"""Mechanical schema adaptation only: never supply a missing decision or note."""
import copy
from decision_conditions import CONDITION_LABELS, CONDITION_POLICY, condition_reference

ADAPTER_VERSION = "condition-output-adapter-v2"
ALIASES = {"source_prior": "source_trust", "government_prior": "government_trust", "mbti": "mbti_preferences"}


def adapt_condition_output(answer, ob):
    """The caller binds this answer to the exact request prompt/signature.

    The short context hash is bookkeeping, not behavioral evidence. Bind it
    locally; retain the model's original value and every repair in the audit.
    All eleven real application notes still have to pass the original validator.
    """
    if ob.local_physical.get("decision_condition_policy") != CONDITION_POLICY:
        return answer
    result = copy.deepcopy(answer)
    usage = result.get("condition_application")
    if not isinstance(usage, dict):
        return result
    repairs = []
    for alias, canonical in ALIASES.items():
        if alias not in usage:
            continue
        if canonical in usage and usage[canonical] != usage[alias]:
            raise ValueError("ambiguous decision condition alias")
        usage[canonical] = usage.pop(alias)
        repairs.append({"kind": "condition_key_alias", "from": alias, "to": canonical})
    required = set(CONDITION_LABELS)
    if not required <= set(usage):
        return result  # Missing real conditions are NEVER manufactured.
    extra = {key: value for key, value in usage.items() if key not in required}
    if extra:
        result["supplementary_condition_application"] = extra
        result["condition_application"] = {key: usage[key] for key in CONDITION_LABELS}
        repairs.append({"kind": "supplementary_condition_fields", "fields": sorted(extra)})
    if 'evidence_choice_indices' in result:
        from model import allowed_evidence_ids
        choices=sorted(allowed_evidence_ids(ob.local_information['posts'],ob.local_physical['memory']))
        indices=result['evidence_choice_indices']
        if ('evidence_ids' in result or not isinstance(indices,list) or len(indices)>6
                or any(type(i) is not int or not 0<=i<len(choices) for i in indices)
                or len(indices)!=len(set(indices))):
            raise ValueError('invalid evidence selection indices')
        # Decode an explicit model choice; never drop, replace or invent a
        # model-provided ID. Original integer choices remain in the raw audit.
        result['evidence_ids']=[choices[i] for i in indices]
        result.pop('evidence_choice_indices')
        repairs.append({'kind':'visible_evidence_index_mapping','indices':indices,
                        'decoded_ids':list(result['evidence_ids'])})
    expected = condition_reference(ob)
    if result.get("condition_context_ref") != expected:
        result["model_returned_condition_context_ref"] = result.get("condition_context_ref")
        result["condition_context_ref"] = expected
        repairs.append({"kind": "request_bound_context_reference", "expected": expected})
    if repairs:
        result["output_format_repairs"] = {"version": ADAPTER_VERSION, "changes": repairs,
                                           "behavioral_fields_changed": False}
    return result


def validation_diagnostic(text, ob, feed, memory):
    """Machine-readable failure details; no exception bodies, keys or reasoning."""
    import json
    from llm_client import parse_response_object, validate_response
    try:
        raw,_ = parse_response_object(text,ob)
    except json.JSONDecodeError as exc:
        return {"code": "invalid_json", "line": exc.lineno, "column": exc.colno,"parse_error":exc.msg}
    except ValueError:
        return {"code": "json_root_not_object"}
    diagnostic = {}
    usage = raw.get("condition_application")
    try:
        answer = adapt_condition_output(raw, ob)
        usage=answer.get('condition_application')
        if ob.local_physical.get("decision_condition_policy") == CONDITION_POLICY:
            diagnostic["missing_conditions"] = sorted(set(CONDITION_LABELS)-set(usage)) if isinstance(usage,dict) else list(CONDITION_LABELS)
            diagnostic["context_reference_matches_raw"] = raw.get("condition_context_ref") == condition_reference(ob)
        validate_response(answer, ob, feed, memory)
        return {**diagnostic, "code": "valid_after_mechanical_adaptation"}
    except ValueError as exc:
        codes = {"invalid decision condition coverage": "condition_coverage_or_note_invalid",
                 "ambiguous decision condition alias": "conflicting_condition_aliases",
                 "invalid/invisible evidence": "invisible_evidence", "invalid/invisible comment target": "invisible_comment_target",
                 "invisible repost target": "invisible_repost_target", "invalid belief measurement": "invalid_score",
                 "invalid evidence selection indices": "invisible_evidence",
                 "invalid action schema": "invalid_action_schema", "empty enabled comment":"empty_comment"}
        diagnostic["code"] = codes.get(str(exc), "response_validation_failed")
        if diagnostic['code']=='invisible_evidence':
            from model import allowed_evidence_ids
            ids=raw.get('evidence_ids',[])
            if isinstance(ids,list):
                allowed=allowed_evidence_ids(feed,memory)
                diagnostic['invalid_evidence_ids']=[v for v in ids if isinstance(v,str) and v not in allowed][:6]
        if isinstance(usage,dict):
            diagnostic["invalid_note_conditions"] = [key for key in CONDITION_LABELS if key in usage and
                (not isinstance(usage[key],dict) or not isinstance(usage[key].get("note"),str)
                 or not 4 <= len(usage[key]["note"].strip()) <= 60
                 or usage[key]['note'].strip() in ("已经考虑所有条件", "同上已考虑", "已考虑该条件"))]
            invalid_fields={}
            for key in CONDITION_LABELS:
                if key not in usage:continue
                item=usage[key]
                if not isinstance(item,dict):invalid_fields[key]=['item_must_be_object'];continue
                fields=[]
                if set(item)!={'affects','note'}:fields.append('keys_must_be_affects_and_note')
                affects=item.get('affects')
                affects_errors=[]
                if not isinstance(affects,list):affects_errors.append('affects_must_be_array')
                elif not affects:affects_errors.append('affects_empty')
                elif any(not isinstance(x,str) for x in affects):affects_errors.append('affects_entries_must_be_strings')
                else:
                    if any(x not in ('credibility','comment','repost') for x in affects):affects_errors.append('affects_unknown_choice')
                    if len(affects)!=len(set(affects)):affects_errors.append('affects_duplicate')
                if affects_errors:fields.extend(['affects_invalid',*affects_errors])
                from comment_policy import PARTICIPATION_POLICY
                if (key=='mbti_preferences' and ob.local_physical.get('comment_participation_policy')==PARTICIPATION_POLICY
                        and isinstance(affects,list) and 'comment' not in affects):fields.append('mbti_comment_application_missing')
                if key in diagnostic['invalid_note_conditions']:fields.append('note_invalid_or_generic')
                if fields:invalid_fields[key]=fields
            if invalid_fields:diagnostic['invalid_condition_fields']=invalid_fields
        return diagnostic
