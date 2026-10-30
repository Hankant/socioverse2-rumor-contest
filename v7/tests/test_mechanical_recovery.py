import copy,json,threading,time
from types import SimpleNamespace
from pathlib import Path
import pytest
import run
from model import dump,read_json,V7Decision
from syntax_repair import repair_document,atoms
from maintenance_recovery import quota_recovery_info,verify_migration
from batch_resources import SharedLimiter,BatchPauseRequested
from conftest import answer
from llm_client import parse_and_validate


@pytest.mark.parametrize('field',['comment','repost'])
def test_missing_action_close_preserves_every_decision_literal(setup,field):
    cfg,env=setup;ob=next(o for o in env.observe_batch(list(env.by_id),1) if o.local_information['posts'])
    original=answer(ob,score=50.000001,comment=True,repost=True)
    text=json.dumps(original,ensure_ascii=False,separators=(',',':'))
    next_key='repost' if field=='comment' else 'evidence_ids'
    bad=text.replace('},"'+next_key+'":',',"'+next_key+'":',1)
    fixed,meta=repair_document(bad)
    assert fixed==original and meta['literal_sequence_unchanged'] and meta['behavioral_fields_changed'] is False
    accepted=parse_and_validate(bad,ob,ob.local_information['posts'],[])
    assert all(accepted[k]==v for k,v in original.items())


def test_missing_comma_and_quoted_punctuation_are_not_conflated(setup):
    cfg,env=setup;ob=next(o for o in env.observe_batch(list(env.by_id),1) if o.local_information['posts']);value=answer(ob)
    value['comment']['text']='原话有括号},"repost":与逗号，全部保留'
    text=json.dumps(value,ensure_ascii=False,separators=(',',':'));bad=text.replace(',"component_credibility"',' "component_credibility"',1)
    fixed,meta=repair_document(bad);assert fixed==value and meta['behavioral_fields_changed'] is False


@pytest.mark.parametrize('transform',[
    lambda t:t.replace('"subjective_credibility":61','"subjective_credibility":',1),
    lambda t:t.replace('"evidence_ids"','evidence_ids',1),
    lambda t:t+'\n其他字段保持不变。',
    lambda t:t+'\n'+t,
    lambda t:t.replace('"subjective_credibility":61','"subjective_credibility":61,"subjective_credibility":99',1),
])
def test_ambiguous_or_missing_values_never_repaired(setup,transform):
    cfg,env=setup;ob=next(o for o in env.observe_batch(list(env.by_id),1) if o.local_information['posts']);text=json.dumps(answer(ob),ensure_ascii=False,separators=(',',':'))
    with pytest.raises(ValueError):repair_document(transform(text))


def quota_info(tmp_path):
    return dict(run_dir=str(tmp_path),audit=str(tmp_path/'audit'),provenance=dict(config=run.read_config()),status=dict(error_type='QuotaPause',export_status='complete'),
        budget=dict(requests=12,input_reserved_units=10,actual_input_tokens=10,output_reserved_tokens=10),unknown=[],recent_request=dict(status='response_received',diagnostic=None))


def test_later_parallel_success_does_not_hide_actual_quota_refusal(tmp_path):
    from auto_retry import eligible
    info=quota_info(tmp_path)
    dump(tmp_path/'audit/request-000010.json',dict(status='request_error',request_number=10,diagnostic={'status_code':429}))
    dump(tmp_path/'audit/request-000011.json',dict(status='response_received',request_number=11))
    assert not eligible(info)
    recovered=quota_recovery_info(info);assert eligible(recovered) and recovered['recent_request']['request_number']==10
    assert info['recent_request']['status']=='response_received'


def test_newer_auth_failure_is_never_replaced_by_older_quota(tmp_path):
    from auto_retry import eligible
    info=quota_info(tmp_path)
    dump(tmp_path/'audit/request-000010.json',dict(status='request_error',request_number=10,diagnostic={'status_code':429}))
    dump(tmp_path/'audit/request-000011.json',dict(status='request_error',request_number=11,diagnostic={'status_code':401}))
    assert not eligible(quota_recovery_info(info,{'status_code':429}))


def test_unknown_and_hard_budget_still_block_quota_recovery(tmp_path):
    from auto_retry import eligible
    info=quota_info(tmp_path);info['unknown']=['unresolved'];assert not eligible(quota_recovery_info(info,{'status_code':429}))
    info['unknown']=[];info['budget']['requests']=12200;assert not eligible(quota_recovery_info(info,{'status_code':429}))


def test_cooperative_pause_drains_active_request_and_stops_new_ones(tmp_path):
    limiter=SharedLimiter(tmp_path/'gate.json');started=threading.Event();release=threading.Event();done=[]
    def active():
        with limiter.slot():started.set();release.wait(2);done.append('saved')
    thread=threading.Thread(target=active);thread.start();assert started.wait(2)
    dump(tmp_path/'PAUSE_REQUESTED.json',dict(requested=True))
    with pytest.raises(BatchPauseRequested):
        with limiter.slot():pytest.fail('no dispatch after pause request')
    release.set();thread.join(2);assert done==['saved'] and limiter.active==0


def test_migration_is_exact_and_cannot_change_scientific_parameters(tmp_path):
    cfg=run.read_config();previous=run.current_fingerprint(cfg,10);current=copy.deepcopy(previous)
    previous['code_sha256']['syntax_repair.py']='old-parser'
    manifest=dict(kind='v7-mechanical-recovery-v1',previous_code_sha256=previous['code_sha256'],current_code_sha256=current['code_sha256'],changed_files=['syntax_repair.py'])
    path=tmp_path/'migration.json';dump(path,manifest);assert verify_migration(path,previous,current)['changed_files']==['syntax_repair.py']
    current['config']['government_tick']=7
    with pytest.raises(ValueError,match='scientific'):verify_migration(path,previous,current)


def test_maintenance_resume_preserves_committed_tick_cache_and_budget(tmp_path,monkeypatch):
    from conftest import FakeClient
    from recovery import RunPaused
    from verify_run import verify
    for key,sub in [('RESULTS','results'),('CONFIGS','configs'),('LOGS','logs')]:monkeypatch.setattr(run,key,tmp_path/sub)
    monkeypatch.setattr(V7Decision,'client_factory',FakeClient);monkeypatch.setattr(FakeClient,'fail_tick',2)
    args=SimpleNamespace(config=None,steps=2,resume=None,concurrency=None,max_requests=None,execution_limit_migration=False)
    with pytest.raises(RunPaused):run.execute(args,test_mode=True)
    parent=Path(read_json(run.RESULTS/'latest.json')['run_dir']);previous=read_json(parent/'provenance.json');previous['code_sha256']['syntax_repair.py']='prior-parser-fixture';dump(parent/'provenance.json',previous)
    current=run.current_fingerprint(run.read_config(),2,'test_stub')
    manifest=tmp_path/'maintenance.json';dump(manifest,dict(kind='v7-mechanical-recovery-v1',previous_code_sha256=previous['code_sha256'],current_code_sha256=current['code_sha256'],changed_files=['syntax_repair.py']))
    args.resume=str(parent);args.maintenance_migration_manifest=str(manifest);monkeypatch.setattr(FakeClient,'fail_tick',None)
    child=run.execute(args,test_mode=True)
    assert verify(child)['panel_rows']==900
    assert read_json(child/'checkpoints/tick-001.json')['sha256']==read_json(parent/'checkpoints/tick-001.json')['sha256']
    prov=read_json(child/'provenance.json');assert prov['maintenance_upgrade']['changed_files']==['syntax_repair.py']
    logical=sum(a['action_kind']=='decide' for p in (child/'checkpoints').glob('*.json') for a in read_json(p)['actions'])
    assert read_json(Path(prov['audit_dir'])/'budget.json')['requests']==logical
