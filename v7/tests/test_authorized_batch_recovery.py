from copy import deepcopy
from pathlib import Path
import pytest
import run
from model import dump,read_json
from maintenance_recovery import automatic_recovery_decision
from recovery import install_authorization,authorization_state


POLICY=dict(version='user-authorized-batch-recovery-v1',user_authorization='哪个API能用就调用，恢复暂停组',
    max_unknown_reissues_per_decision=3,max_output_windows_per_decision=2,wait_seconds=30)


def info(tmp_path,kind='UncertainRequest'):
    audit=tmp_path/'audit';audit.mkdir(exist_ok=True)
    budget=dict(requests=8,input_reserved_units=1000,actual_input_tokens=500,output_reserved_tokens=2000)
    dump(audit/'budget.json',budget)
    data=dict(run_dir=str(tmp_path/'run'),audit=str(audit),status=dict(error_type=kind,export_status='complete',last_completed_tick=2),
        provenance=dict(config=run.read_config()),budget=budget,unknown=[])
    if kind=='UncertainRequest':
        item=dict(file='request-000008.json',prompt_sha256='network-sig',tick=3,agent_id='A0001',request_number=8)
        data['unknown']=[item]
        dump(audit/item['file'],dict(status='pending_usage_unknown',prompt_sha256='network-sig',tick=3,diagnostic=dict(exception_type='APITimeoutError',timeout_phase='ReadTimeout')))
    elif kind=='OutputContractPause':
        dump(audit/'request-000008.json',dict(status='response_received',prompt_sha256='output-sig',tick=3))
        dump(audit/'validation/request-000008.json',dict(prompt_sha256='output-sig',diagnostic=dict(code='invisible_evidence')))
    return data


def test_network_retry_acknowledges_exact_missing_answer_and_keeps_budget(tmp_path):
    data=info(tmp_path);before=deepcopy(data['budget']);decision=automatic_recovery_decision(data,POLICY)
    assert decision['kind']=='unknown_network_response' and decision['wait_seconds']==30
    assert decision['authorization']['unknown_reissue']==data['unknown'] and data['budget']==before
    install_authorization(data['audit'],decision['authorization'])
    cutoff,ack=authorization_state(data['audit'])
    assert cutoff==8 and ack=={('request-000008.json','network-sig')}
    assert read_json(Path(data['audit'])/'budget.json')==before
    assert read_json(Path(data['audit'])/'request-000008.json')['status']=='pending_usage_unknown'


def test_output_retry_keeps_evidence_validation_and_opens_only_bounded_window(tmp_path):
    data=info(tmp_path,'OutputContractPause');decision=automatic_recovery_decision(data,POLICY)
    assert decision['kind']=='output_contract' and decision['authorization']['unknown_reissue']==[]
    assert decision['authorization']['recovery_prompt_sha256s']==['output-sig']
    install_authorization(data['audit'],decision['authorization'])
    assert read_json(Path(data['audit'])/'validation/request-000008.json')['diagnostic']['code']=='invisible_evidence'
    entries=[dict(recovery_kind='output_contract',recovery_prompt_sha256s=['output-sig']) for _ in range(2)]
    dump(Path(data['audit'])/'recovery_authorizations.json',dict(entries=entries))
    assert automatic_recovery_decision(data,POLICY) is None


def test_three_prior_network_reissues_stop_more_automatic_spending(tmp_path):
    data=info(tmp_path)
    entries=[dict(unknown_reissue=data['unknown']) for _ in range(3)]
    dump(Path(data['audit'])/'recovery_authorizations.json',dict(entries=entries))
    assert automatic_recovery_decision(data,POLICY) is None


@pytest.mark.parametrize('kind',['RuntimeError','HardBudgetPause','PromptBudgetPause','BatchPauseRequested','KeyboardInterrupt','ExportPause'])
def test_arbitrary_runtime_or_operator_and_hard_limit_pauses_are_not_retried(tmp_path,kind):
    assert automatic_recovery_decision(info(tmp_path,kind),POLICY) is None


def test_http422_is_not_automatically_misclassified_as_network_timeout(tmp_path):
    data=info(tmp_path);path=Path(data['audit'])/'request-000008.json'
    record=read_json(path);record['diagnostic']=dict(exception_type='UnprocessableEntityError',status_code=422);dump(path,record)
    assert automatic_recovery_decision(data,POLICY) is None


def test_undocumented_power_loss_unknown_requires_separate_operator_decision(tmp_path):
    data=info(tmp_path);path=Path(data['audit'])/'request-000008.json'
    record=read_json(path);record.pop('diagnostic');dump(path,record)
    assert automatic_recovery_decision(data,POLICY) is None


@pytest.mark.parametrize('field',['requests','input_reserved_units','output_reserved_tokens'])
def test_automatic_retry_never_raises_or_resets_execution_budgets(tmp_path,field):
    data=info(tmp_path);cfg=data['provenance']['config']
    data['budget'][field]=cfg[{'requests':'max_requests','input_reserved_units':'max_input_reserved_units','output_reserved_tokens':'max_output_reserved_tokens'}[field]]
    assert automatic_recovery_decision(data,POLICY) is None


def test_provider_refusal_is_not_automatically_retried_on_other_keys(tmp_path):
    data=info(tmp_path,'OutputContractPause');data['status']['error_context']=dict(code='provider_refusal')
    assert automatic_recovery_decision(data,POLICY) is None


def test_cached_success_is_not_selected_for_regeneration(tmp_path):
    data=info(tmp_path,'OutputContractPause');dump(Path(data['audit'])/'response_cache/output-sig.json',dict(answer=dict(score=23)))
    assert automatic_recovery_decision(data,POLICY) is None


def test_missing_user_authorization_leaves_old_recovery_behavior(tmp_path):
    data=info(tmp_path);assert automatic_recovery_decision(data,None) is None
    policy=deepcopy(POLICY);policy.pop('user_authorization')
    assert automatic_recovery_decision(data,policy) is None


@pytest.mark.parametrize('field,value',[('max_unknown_reissues_per_decision',4),('max_output_windows_per_decision',True),('wait_seconds',0)])
def test_invalid_recovery_policy_cannot_create_unbounded_retries(tmp_path,field,value):
    policy=deepcopy(POLICY);policy[field]=value
    with pytest.raises(ValueError):automatic_recovery_decision(info(tmp_path),policy)


@pytest.mark.parametrize('authorized',[False,True])
def test_batch_resume_reuses_verified_authorization_without_scanning_all_old_prompts(tmp_path,monkeypatch,authorized):
    from types import SimpleNamespace
    import threading
    import batch54,batch_resources,credentials
    from model import V7Decision
    folder=tmp_path/'old';audit=tmp_path/'audit';batch=tmp_path/'batch';cfg=run.read_config()
    dump(folder/'provenance.json',dict(audit_dir=str(audit)))
    dump(folder/'status.json',dict(status='paused_by_user',error_type='BatchPauseRequested',last_completed_tick=2,export_status='complete'))
    dump(audit/'budget.json',dict(requests=12))
    dump(batch/'configs/one.json',cfg)
    state=dict(status='paused_by_user',output=str(tmp_path/'output'),cases=dict(one=dict(status='paused_by_user',last_completed_tick=2,run_dir=str(folder))))
    authorization=dict(source_run=str(folder),request_cutoff=12,unknown_reissue=[],action='explicit_operator_retry')
    if authorized:state['recovery_authorizations']=dict(one=authorization)
    dump(batch/'batch_status.json',state)
    dump(batch/'request_controls.json',dict(automatic_recovery=POLICY))
    limiter=SimpleNamespace(ceiling=5,stop=threading.Event())
    router=SimpleNamespace(limits=dict(primary=2,backup=1,third=1,fourth=1),retry_interval=600,fallback=None,fallback_active=True)
    factory=SimpleNamespace(shared_limiter=limiter,shared_router=router)
    monkeypatch.setattr(V7Decision,'client_factory',None)
    monkeypatch.setattr(batch_resources,'client_class',lambda *a:factory)
    monkeypatch.setattr(credentials,'validate_credentials',lambda *a:None)
    monkeypatch.setattr(batch54,'describe_pause',lambda *a:pytest.fail('ordinary saved pause should not reread every request'))
    monkeypatch.setattr(batch54,'load_job',lambda *a:SimpleNamespace(main={0:[]},write=lambda *a:None,folder=folder))
    class Exporter:
        def poll(self):return 0
        def terminate(self):pass
    monkeypatch.setattr(batch54.subprocess,'Popen',lambda *a,**k:Exporter())
    monkeypatch.setattr(batch54.subprocess,'run',lambda *a,**k:None)
    def execute(args,**kw):
        assert getattr(args,'recovery_authorization',None)==(authorization if authorized else None)
        dump(folder/'status.json',dict(status='completed_live',last_completed_tick=10,export_status='complete'))
        return folder
    monkeypatch.setattr(batch54.run,'execute',execute)
    result=batch54.start(batch,dict(node='offline-test-node'))
    assert result['cases']['one']['status']=='completed_live'


@pytest.mark.parametrize('relative',['request-000012.json','response_cache/valid.json'])
def test_immutable_request_and_cache_reuse_preserves_parent_on_atomic_write(tmp_path,relative):
    source=tmp_path/'old'/relative;destination=tmp_path/'new'/relative
    dump(source,dict(score=61,raw='saved original answer'));destination.parent.mkdir(parents=True,exist_ok=True)
    run.copy_recovery_file(source,destination)
    assert source.stat().st_ino==destination.stat().st_ino
    dump(destination,dict(score=23,raw='separate atomic replacement'))
    assert read_json(source)==dict(score=61,raw='saved original answer')
    assert read_json(destination)['score']==23


@pytest.mark.parametrize('relative',['budget.json','rate-limit-state.json','recovery_authorizations.json','request-events.jsonl'])
def test_mutable_ledgers_and_append_logs_are_independent_copies(tmp_path,relative):
    source=tmp_path/'old'/relative;destination=tmp_path/'new'/relative
    source.parent.mkdir(parents=True,exist_ok=True);destination.parent.mkdir(parents=True,exist_ok=True)
    source.write_text('original\n',encoding='utf-8');run.copy_recovery_file(source,destination)
    with destination.open('a',encoding='utf-8') as f:f.write('new child event\n')
    assert source.read_text(encoding='utf-8')=='original\n'


def test_filesystems_without_hard_links_fall_back_to_complete_copy(tmp_path,monkeypatch):
    source=tmp_path/'request-000001.json';destination=tmp_path/'new.json';dump(source,dict(original=True))
    def unsupported(*args):raise OSError('links unavailable')
    monkeypatch.setattr(run.os,'link',unsupported);run.copy_recovery_file(source,destination)
    assert read_json(destination)==read_json(source)
