"""Role wording reaches the actual wire; continuous trust stays authoritative."""
import copy
import pytest
import run
from government import government_trust_role,GOVERNMENT_PERSONA_DESCRIPTIONS,GOVERNMENT_PERSONA_POLICY
from llm_client import prepare_prompt
from response_contract import wire_prompt
from concise_wire import extract_data
from decision_conditions import condition_inputs,condition_reference


@pytest.mark.parametrize('value,level',[(0,'low'),(.25,'low'),(1/3-1e-12,'low'),(1/3,'medium'),(.5,'medium'),
    (2/3-1e-12,'medium'),(2/3,'high'),(.75,'high'),(1,'high')])
def test_exact_boundaries_and_original_numeric_value(value,level):
    role=government_trust_role(value)
    assert role['level']==level and role['policy']==GOVERNMENT_PERSONA_POLICY
    assert role['description']==GOVERNMENT_PERSONA_DESCRIPTIONS[level]
    assert f'{value:.6f}'in role['prompt']


@pytest.mark.parametrize('bad',[-.01,1.01,True,None,'0.75',float('nan'),float('inf')])
def test_invalid_individual_trust_is_not_silently_classified(bad):
    with pytest.raises(ValueError):government_trust_role(bad)


@pytest.mark.parametrize('style',['standard','concise_lossless_v1','concise_shared_prefix_v1'])
@pytest.mark.parametrize('value,level',[(.25,'low'),(.5,'medium'),(.75,'high')])
def test_each_individual_role_survives_every_actual_wire_style(setup,style,value,level):
    cfg,env=setup
    ob=next(o for o in env.observe_batch(list(env.by_id),1)if o.local_information['posts'])
    # Keep global mean=.75; the assigned individual value must determine wording.
    assert cfg['government_trust_mean']==.75
    ob.local_physical['government_trust']=value
    template=(run.SOURCE/'02_Prompt固定提示词.md').read_text(encoding='utf-8').split('```text',1)[1].split('```',1)[0].strip()
    base,*_=prepare_prompt(template,ob,2_000_000,memory_policy='preserve',encoding=cfg['prompt_encoding'])
    data=extract_data(base);profile=data['profile']['合成角色设定_不是真实账户事实']
    assert profile['government_prior']==value
    assert profile['government_trust_level']==government_trust_role(value)['label']
    assert profile['synthetic_government_evaluation']==government_trust_role(value)['prompt']
    wire=wire_prompt(base,ob,1536,style=style)
    assert GOVERNMENT_PERSONA_DESCRIPTIONS[level]in wire
    assert all(d not in wire for key,d in GOVERNMENT_PERSONA_DESCRIPTIONS.items()if key!=level)
    assert '未读时不能预知回应内容或结论'in wire
    assert '保留本人的具体信任数值'in wire
    assert env.cfg['correction_text']not in wire
    assert ob.local_physical['subjective_credibility']is None
    assert condition_inputs(ob)['government_trust']==value


def test_legacy_prompt_unchanged_without_new_policy_and_context_reference_changes(setup):
    cfg,env=setup;ob=next(o for o in env.observe_batch(list(env.by_id),1)if o.local_information['posts'])
    before=condition_reference(ob);legacy=copy.deepcopy(ob);legacy.local_physical.pop('government_trust_prompt_policy')
    assert condition_reference(legacy)!=before
    template=(run.SOURCE/'02_Prompt固定提示词.md').read_text(encoding='utf-8').split('```text',1)[1].split('```',1)[0].strip()
    base,*_=prepare_prompt(template,legacy,2_000_000,memory_policy='preserve',encoding=cfg['prompt_encoding'])
    profile=extract_data(base)['profile']['合成角色设定_不是真实账户事实']
    assert 'government_trust_level'not in profile
    assert profile['synthetic_government_evaluation'].startswith('本条件分配的政府来源接受倾向为')
