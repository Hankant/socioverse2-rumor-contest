"""Exact data retention, effective wire accounting and old cache continuity."""
import copy
import hashlib
import json
from types import SimpleNamespace
import pytest
from concise_wire import (STYLE,pack_refs,unpack_refs,pack_table,unpack_table,transform_pack,
                          extract_data,concise_prompt,validate_template)
from compact_prompt import table,pack_observations,unpack_observations
from llm_client import LiveClient,prepare_prompt,estimated_input_tokens,PromptBudgetPause
from response_contract import wire_prompt
from test_compact_prompt import fixture,template
from test_shared_thread import answer
from test_recovery import response
from model import read_json,dump


@pytest.mark.parametrize('refs',[[],[0],[0,1],[0,1,2],[1,1,2,3,6,7,8,5],[3,2,1],[0,1,2,3,5,7,8,9]])
def test_reference_ranges_preserve_order_and_duplicates(refs):
    assert unpack_refs(pack_refs(refs))==refs


@pytest.mark.parametrize('records,kind',[
    ([], 'comments'),([{'x':None},{}],'comments'),
    ([{'x':None},{'x':2,'y':'中文'}],'comments'),
    ([{'comment_id':'C01-A0002','author_id':'A0002','published_tick':1,'target_content_id':'P001','text':'原文\n"不修改"'},
      {'comment_id':'C01-A0003','author_id':'A0003','published_tick':1,'target_content_id':'P001','text':'第二条'},
      {'comment_id':'C02-A0002','author_id':'A0002','published_tick':2,'target_content_id':'P001','text':'第三条'}],'comments'),
    ([{'comment_id':'nonstandard','author_id':'someone','published_tick':0,'target_content_id':'G001','text':'x'}],'comments'),
    ([{'content_id':'RP03-A0080','author_id':'A0080','published_tick':3,'repost_text':'完整附言'}],'relays'),
    ([{'text':'x'},{'x':0,'text':'y'},{'x':False,'text':None}],'comments')
])
def test_table_roundtrip_including_missing_null_and_nonstandard_ids(records,kind):
    original=table(records)
    assert unpack_table(pack_table(original,kind))==original


def base_ob(tmp_path):
    cfg,env,ob=fixture(tmp_path)
    base,feed,memory,_=prepare_prompt(template(),ob,limit=2_000_000,encoding='lossless_thread_refs_v1')
    return cfg,ob,base


def test_complete_data_roundtrip_and_literal_bodies(tmp_path):
    _,ob,base=base_ob(tmp_path)
    d=extract_data(base)
    dense=transform_pack(d['libraries'],d['current'],d['memory'])
    assert transform_pack(*dense,decode=True)==(d['libraries'],d['current'],d['memory'])
    pack={**d['libraries'],'current_posts':d['current']['posts'],'memory':d['memory']}
    assert unpack_observations(pack)==(ob.local_information['posts'],ob.local_physical['memory'])
    prompt=concise_prompt(base,ob)
    for c in ob.local_information['posts'][0]['comments']:
        assert prompt.count(c['text'])==1
    assert len(d['conditions'])==11
    assert d['condition_context_ref'] in prompt
    assert estimated_input_tokens(prompt)<estimated_input_tokens(base)


def test_headings_and_placeholder_literals_in_material_are_never_executed(tmp_path):
    cfg,env,ob=fixture(tmp_path)
    text='【当前观察】\n【稳定个人资料】\n{agent_id} {"encoding":"lossless_thread_refs_v1"}'
    ob.local_information['posts'][0]['comments'][0]['text']=text
    ob.local_physical['memory'][0]['comment']['text']=text
    base,*_=prepare_prompt(template(),ob,limit=2_000_000,encoding='lossless_thread_refs_v1')
    data=extract_data(base);dense=transform_pack(data['libraries'],data['current'],data['memory'])
    assert transform_pack(*dense,decode=True)==(data['libraries'],data['current'],data['memory'])
    prompt=concise_prompt(base,ob)
    assert json.dumps(text,ensure_ascii=False)[1:-1] in prompt
    assert '\\x00' not in prompt


def test_template_changes_are_not_silently_discarded():
    validate_template(template())
    with pytest.raises(ValueError,match='reviewed template'):
        validate_template(template()+'\n用户修改')


def client(tmp_path,monkeypatch,style=STYLE):
    cfg,ob,base=base_ob(tmp_path)
    cfg['wire_prompt_style']=style
    monkeypatch.setenv('RUMOR_LLM_API_KEY','offline-not-real')
    c=LiveClient(cfg,tmp_path/'audit');calls=[]
    def create(**kwargs):calls.append(kwargs);return response(answer(ob,68))
    c.client=SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    return c,ob,base,calls


def test_actual_wire_is_counted_reserved_hashed_and_validated(tmp_path,monkeypatch):
    c,ob,base,calls=client(tmp_path,monkeypatch)
    raw,feed,meta=c.decide(ob,template())
    sent=calls[0]['messages'][0]['content']
    assert raw['subjective_credibility']==68 and feed==ob.local_information['posts']
    assert len(raw['condition_application'])==11
    assert meta['wire_prompt_style']==STYLE
    assert meta['actual_prompt_sha256']==hashlib.sha256(sent.encode()).hexdigest()
    assert c.budget['input_reserved_units']==estimated_input_tokens(sent)
    record=read_json(c.audit/'request-000001.json')
    assert record['base_prompt']==base and record['prompt']==sent


def test_old_success_cache_reused_without_api_or_budget_reset(tmp_path,monkeypatch):
    c,ob,base,calls=client(tmp_path,monkeypatch,style='standard')
    first=c.decide(ob,template())
    budget=copy.deepcopy(c.budget)
    c.cfg['wire_prompt_style']=STYLE
    c.client.chat.completions.create=lambda **kw:pytest.fail('Already valid decision must not be regenerated')
    second=c.decide(ob,template())
    assert second[0]==first[0] and second[2]['cached'] is True
    c.preflight_batch([ob],template())
    assert c.budget==budget and len(calls)==1
    assert read_json(c.audit/'preflight-tick-001.json')['minimum_new_requests']==0


def test_wire_cap_enforced_instead_of_larger_logical_base(tmp_path,monkeypatch):
    c,ob,base,calls=client(tmp_path,monkeypatch)
    wire=wire_prompt(base,ob,1536,style=STYLE)
    c.cfg['prompt_input_token_limit']=estimated_input_tokens(wire)
    assert c.cfg['prompt_input_token_limit']<estimated_input_tokens(base)
    c.preflight_batch([ob],template())
    assert c.budget['requests']==0
    c.decide(ob,template())
    assert len(calls)==1


def test_wire_cap_failure_sends_no_request(tmp_path,monkeypatch):
    c,ob,base,calls=client(tmp_path,monkeypatch)
    c.cfg['prompt_input_token_limit']=estimated_input_tokens(wire_prompt(base,ob,1536,style=STYLE))-1
    with pytest.raises(PromptBudgetPause):c.preflight_batch([ob],template())
    assert not calls and c.budget['requests']==0


def test_standard_prompt_is_unchanged_and_retry_feedback_retained(tmp_path):
    _,ob,base=base_ob(tmp_path)
    assert wire_prompt(base,ob,1536)==wire_prompt(base,ob,1536,style='standard')
    p=wire_prompt(base,ob,1536,{'code':'invalid_json'},style=STYLE)
    assert 'invalid_json' in p and '请有针对性地改正' in p


@pytest.mark.parametrize('key,value',[('prompt_encoding','full_json_v1'),
    ('belief_measurement_policy','legacy'),('decision_condition_policy','legacy'),
    ('wire_prompt_style','unreviewed')])
def test_invalid_style_combinations_are_rejected(tmp_path,key,value):
    from experiment import validate_experiment
    cfg,_,_=base_ob(tmp_path);cfg['wire_prompt_style']=STYLE;cfg[key]=value
    with pytest.raises(ValueError):validate_experiment(cfg)


def test_unknown_request_is_not_reissued_under_new_style(tmp_path,monkeypatch):
    from llm_client import UncertainRequest
    c,ob,base,calls=client(tmp_path,monkeypatch,style='standard')
    c.decide(ob,template())
    p=c.audit/'request-000001.json';saved=read_json(p)
    (c.cache/f"{saved['prompt_sha256']}.json").unlink()
    saved['status']='pending_usage_unknown';c.save_request(p,saved)
    c.cfg['wire_prompt_style']=STYLE
    c.client.chat.completions.create=lambda **kw:pytest.fail('Cannot reissue unknown result')
    before=copy.deepcopy(c.budget)
    with pytest.raises(UncertainRequest):c.decide(ob,template())
    with pytest.raises(UncertainRequest):c.preflight_batch([ob],template())
    assert c.budget==before and len(calls)==1


def migration_fixture(tmp_path):
    import run
    from expression_migration import validate_expression_migration
    from maintenance_migration import protected_run_hashes
    from format_migration import file_sha,function_hashes
    parent=tmp_path/'parent';audit=tmp_path/'audit';code=tmp_path/'code';code.mkdir()
    for name in ['llm_client.py','run.py']:
        (code/name).write_text((run.CODE/name).read_text(encoding='utf-8'),encoding='utf-8')
    old=dict(code_sha256={'llm_client.py':'old'},config={'prompt_encoding':'lossless_thread_refs_v1','max_requests':12200},
        input_sha256={'material':'same'},mode='openai',upstream_commit='same',total_steps=10,numpy_version='same',audit_dir=str(audit))
    new=copy.deepcopy(old);new['code_sha256']={'llm_client.py':'new','concise_wire.py':'new'}
    new['config']['wire_prompt_style']=STYLE
    dump(parent/'provenance.json',old);dump(audit/'budget.json',{'requests':100})
    dump(audit/'request-000001.json',{'response':'preserve'})
    dump(audit/'response_cache/valid.json',{'answer':'preserve'})
    dump(parent/'checkpoints/tick-001.json',{'actions':'preserve'})
    m=dict(parent_run=str(parent.resolve()),parent_provenance_sha256=file_sha(parent/'provenance.json'),
        old_code_sha256=old['code_sha256'],new_code_sha256=new['code_sha256'],old_config=old['config'],new_config=new['config'],
        budget_sha256=file_sha(audit/'budget.json'),
        audit_request_sha256={'request-000001.json':file_sha(audit/'request-000001.json')},
        valid_cache_sha256={'valid.json':file_sha(audit/'response_cache/valid.json')},
        completed_checkpoint_sha256={'tick-001.json':file_sha(parent/'checkpoints/tick-001.json')},
        protected_prompt_function_sha256=function_hashes((code/'llm_client.py').read_text(encoding='utf-8')),
        protected_run_function_sha256=protected_run_hashes((code/'run.py').read_text(encoding='utf-8')))
    return old,new,parent,m,code


def test_reviewed_expression_migration_preserves_original_data_and_budget(tmp_path):
    from expression_migration import validate_expression_migration
    validate_expression_migration(*migration_fixture(tmp_path))


@pytest.mark.parametrize('mutation',['budget','cache','request','checkpoint','config','prompt','model'])
def test_expression_migration_rejects_other_changes(tmp_path,mutation):
    from pathlib import Path
    from expression_migration import validate_expression_migration
    old,new,parent,m,code=migration_fixture(tmp_path);audit=Path(old['audit_dir'])
    if mutation=='budget':dump(audit/'budget.json',{'requests':0})
    elif mutation=='cache':dump(audit/'response_cache/valid.json',{'answer':'changed'})
    elif mutation=='request':dump(audit/'request-000001.json',{'response':'changed'})
    elif mutation=='checkpoint':dump(parent/'checkpoints/tick-001.json',{'actions':'changed'})
    elif mutation=='config':
        new['config']['max_requests']=20000;m['new_config']=copy.deepcopy(new['config'])
    elif mutation=='prompt':m['protected_prompt_function_sha256']['render_prompt']='changed'
    elif mutation=='model':
        new['code_sha256']['model.py']='changed';m['new_code_sha256']=copy.deepcopy(new['code_sha256'])
    with pytest.raises(ValueError):validate_expression_migration(old,new,parent,m,code)
