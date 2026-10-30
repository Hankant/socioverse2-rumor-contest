import json
import pytest
from conftest import answer
from syntax_repair import repair_document,CONDITION_KEYS
from decision_conditions import CONDITION_LABELS
from llm_client import parse_and_validate


def fixture_answer(env):
    ob=next(o for o in env.observe_batch(list(env.by_id),1)if o.local_information['posts'])
    value=answer(ob,score=50.000001,comment=True,repost=True)
    value['comment']['text']='保留引号"、反斜杠\\，原话occupation":不能动。'
    return ob,value,json.dumps(value,ensure_ascii=False,separators=(',',':'))


@pytest.mark.parametrize('marker',['"',"'",'|','`'])
def test_single_eof_marker_removed_without_changing_any_decision(setup,marker):
    cfg,env=setup;ob,value,text=fixture_answer(env)
    fixed,meta=repair_document(text+marker)
    assert fixed==value and meta['behavioral_fields_changed']is False
    assert meta['changes'][-1]['kind']=='remove_single_orphan_eof_marker'
    accepted=parse_and_validate(text+marker,ob,ob.local_information['posts'],[])
    assert all(accepted[k]==v for k,v in value.items())


@pytest.mark.parametrize('key',['occupation','community_experience','source_trust','government_trust','history_and_memory'])
def test_only_missing_opening_quote_of_an_existing_schema_key_is_inserted(setup,key):
    cfg,env=setup;ob,value,text=fixture_answer(env)
    bad=text.replace(',"'+key+'":',','+key+'":',1)
    fixed,meta=repair_document(bad)
    assert fixed==value and meta['key_names_inferred']is False and meta['value_literals_inferred']is False
    accepted=parse_and_validate(bad,ob,ob.local_information['posts'],[])
    assert accepted['subjective_credibility']==50.000001
    assert accepted['comment']==value['comment']and accepted['repost']==value['repost']


def test_quote_and_tail_marker_share_the_three_edit_limit(setup):
    cfg,env=setup;ob,value,text=fixture_answer(env)
    bad=text.replace(',"occupation":',',occupation":',1).replace(',"community_experience":',',community_experience":',1)+'"'
    assert repair_document(bad)[0]==value
    with pytest.raises(ValueError):repair_document(bad,max_edits=2)


def test_missing_root_close_then_orphan_quote_is_bounded(setup):
    cfg,env=setup;ob,value,text=fixture_answer(env)
    assert repair_document(text[:-1]+'"')[0]==value


@pytest.mark.parametrize('tail',[' correction: score should be 20','\n'+ '{"subjective_credibility":20}', '"different answer"','null','[]','{}','""'])
def test_semantic_suffix_and_second_values_never_discarded(setup,tail):
    cfg,env=setup;ob,value,text=fixture_answer(env)
    with pytest.raises(ValueError):repair_document(text+tail)


def test_values_missing_quotes_and_unknown_keys_are_not_inferred(setup):
    cfg,env=setup;ob,value,text=fixture_answer(env)
    for bad in (text.replace('"P001"','P001"',1),text.replace('"occupation"','occupation',1),
                text.replace('"occupation"','unknown_role"',1),text.replace('50.000001','',1)):
        with pytest.raises(ValueError):repair_document(bad)
    assert CONDITION_KEYS==set(CONDITION_LABELS)
