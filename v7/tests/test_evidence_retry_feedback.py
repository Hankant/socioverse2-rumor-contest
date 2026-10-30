import copy
import json

import pytest

from conftest import answer
from llm_client import parse_and_validate
from model import allowed_evidence_ids
from response_contract import wire_prompt


def test_retry_does_not_repeat_fabricated_id_or_supply_a_decision(setup):
    _, env = setup
    ob = next(o for o in env.observe_batch(list(env.by_id), 1) if o.local_information['posts'])
    before = copy.deepcopy(ob.model_dump(mode='json'))
    invalid = 'C07-A0069'
    assert invalid not in allowed_evidence_ids(ob.local_information['posts'], ob.local_physical['memory'])
    text = wire_prompt('unchanged observed materials', ob, 1536,
                       {'code': 'invisible_evidence', 'invalid_evidence_ids': [invalid]})
    assert invalid not in text
    assert '未发表评论的轮次没有该轮评论ID' in text
    assert json.dumps(list(enumerate(sorted(allowed_evidence_ids(ob.local_information['posts'], ob.local_physical['memory'])))),
                      ensure_ascii=False, separators=(',', ':')) in text
    assert '"evidence_choice_indices":[]' in text
    assert '不要求改变评分、评论或转发立场' in text
    assert ob.model_dump(mode='json') == before


def test_retry_still_rejects_invented_evidence_and_accepts_visible_evidence(setup):
    _, env = setup
    ob = next(o for o in env.observe_batch(list(env.by_id), 1) if o.local_information['posts'])
    original = answer(ob, score=50.000001, comment=True)
    assert parse_and_validate(json.dumps(original), ob, ob.local_information['posts'], []) == original
    invalid = copy.deepcopy(original)
    invalid['evidence_ids'].append('C07-A0069')
    with pytest.raises(ValueError, match='invalid/invisible evidence'):
        parse_and_validate(json.dumps(invalid), ob, ob.local_information['posts'], [])


def test_other_failure_diagnostics_and_initial_prompt_do_not_get_evidence_feedback(setup):
    _, env = setup
    ob = next(o for o in env.observe_batch(list(env.by_id), 1) if o.local_information['posts'])
    for diagnostic in (None, {'code': 'invalid_json', 'line': 1, 'column': 20}):
        text = wire_prompt('observed materials', ob, 1536, diagnostic)
        assert '这次可使用的精确证据ID' not in text
        assert '未发表评论的轮次没有该轮评论ID' not in text
    assert '"column": 20' in text


def test_model_selected_indices_decode_exactly_without_changing_decisions(setup):
    from output_adapter import adapt_condition_output
    _, env = setup
    ob = next(o for o in env.observe_batch(list(env.by_id), 1) if o.local_information['posts'])
    original = answer(ob, score=50.000001, comment=True, repost=True)
    choices = sorted(allowed_evidence_ids(ob.local_information['posts'], ob.local_physical['memory']))
    indexed = copy.deepcopy(original)
    indexed['evidence_choice_indices'] = [choices.index(i) for i in indexed.pop('evidence_ids')]
    before = copy.deepcopy(indexed)
    decoded = parse_and_validate(json.dumps(indexed), ob, ob.local_information['posts'], [])
    assert all(decoded[k] == v for k, v in original.items())
    assert indexed == before
    assert decoded['output_format_repairs']['changes'] == [{'kind':'visible_evidence_index_mapping',
        'indices':indexed['evidence_choice_indices'], 'decoded_ids':original['evidence_ids']}]
    again = adapt_condition_output(decoded, ob)
    assert again == decoded


@pytest.mark.parametrize('indices', [[-1], [1000], [True], [1.0], ['0'], [0, 0], [None], None, [0]*7])
def test_invalid_index_choices_are_never_silently_changed(setup, indices):
    _, env = setup
    ob = next(o for o in env.observe_batch(list(env.by_id), 1) if o.local_information['posts'])
    indexed = answer(ob)
    indexed.pop('evidence_ids')
    indexed['evidence_choice_indices'] = indices
    with pytest.raises(ValueError, match='invalid evidence selection indices'):
        parse_and_validate(json.dumps(indexed), ob, ob.local_information['posts'], [])


def test_conflicting_string_and_index_choices_are_rejected(setup):
    _, env = setup
    ob = next(o for o in env.observe_batch(list(env.by_id), 1) if o.local_information['posts'])
    indexed = answer(ob)
    indexed['evidence_choice_indices'] = [0]
    with pytest.raises(ValueError, match='invalid evidence selection indices'):
        parse_and_validate(json.dumps(indexed), ob, ob.local_information['posts'], [])
