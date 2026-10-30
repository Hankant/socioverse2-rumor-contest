import csv,json
from pathlib import Path
from types import SimpleNamespace
import pytest
import run
from model import V7Decision,read_json,dump
from recovery import RunPaused
from verify_run import verify
from conftest import FakeClient


def install(tmp_path,monkeypatch):
    for key,sub in [('RESULTS','results'),('CONFIGS','configs'),('LOGS','logs')]:monkeypatch.setattr(run,key,tmp_path/sub)
    monkeypatch.setattr(V7Decision,'client_factory',FakeClient)
    return SimpleNamespace(config=str(run.ROOT/'configs/v7/one_condition.json'),steps=10,resume=None,concurrency=None,max_requests=None,execution_limit_migration=False)


def test_complete_ten_ticks_and_exact_replay(tmp_path,monkeypatch):
    args=install(tmp_path,monkeypatch);folder=run.execute(args,test_mode=True)
    state=read_json(folder/'status.json');assert state['status']=='completed_test' and state['last_completed_tick']==10 and state['export_status']=='complete'
    result=verify(folder);assert result['panel_rows']==3300 and result['replay']=='exact'
    with (folder/'reports/per_tick_results.csv').open(encoding='utf-8-sig',newline='') as f:rows=list(csv.DictReader(f))
    assert len(rows)==33
    for row in rows:
        assert sum(int(row[k]) for k in ('believe','reject','unjudged_n'))==int(row['population_n'])
        assert int(row['population_n'])==dict(all=300,inside=48,outside=252)[row['group']]
    assert not any('rule' in k for row in rows for k in row)
    prov=read_json(folder/'provenance.json');assert read_json(Path(prov['audit_dir'])/'budget.json')['requests']<=3000
    for path in (folder/'checkpoints').glob('*.json'):
        actions=read_json(path)['actions'];assert len(actions)==300
        for action in actions:
            if action['action_kind']=='decide':
                payload=action['action_payload'];assert len(payload['used_memory_ticks'])<=3
                assert all(action['step']-3<=t<action['step'] for t in payload['used_memory_ticks'])
                assert all(len(p['comments'])<=30 for p in payload['observed_posts'])


def test_pause_resume_reuses_partial_tick_and_keeps_budget(tmp_path,monkeypatch):
    args=install(tmp_path,monkeypatch);monkeypatch.setattr(FakeClient,'fail_tick',3)
    with pytest.raises(RunPaused):run.execute(args,test_mode=True)
    parent=Path(read_json(run.RESULTS/'latest.json')['run_dir']);prov=read_json(parent/'provenance.json');audit=Path(prov['audit_dir'])
    assert read_json(parent/'status.json')['last_completed_tick']==2
    assert verify(parent)['panel_rows']==900
    before=read_json(audit/'budget.json')['requests'];assert len(list((audit/'response_cache').glob('*.json')))==before
    monkeypatch.setattr(FakeClient,'fail_tick',None);args.resume=str(parent)
    child=run.execute(args,test_mode=True);assert verify(child)['panel_rows']==3300
    childprov=read_json(child/'provenance.json');assert childprov['inherited_completed_tick']==2
    requests=read_json(Path(childprov['audit_dir'])/'budget.json')['requests']
    checkpoints=[read_json(p) for p in sorted((child/'checkpoints').glob('*.json'))]
    logical=sum(a['action_kind']=='decide' for cp in checkpoints for a in cp['actions'])
    assert requests==logical and requests>=before
    for t in (1,2):assert read_json(child/'checkpoints'/f'tick-{t:03d}.json')['sha256']==read_json(parent/'checkpoints'/f'tick-{t:03d}.json')['sha256']


def test_v6_checkpoint_rejected_before_new_artifacts(tmp_path,monkeypatch):
    args=install(tmp_path,monkeypatch);parent=tmp_path/'old';dump(parent/'provenance.json',dict(version='V6'));args.resume=str(parent)
    with pytest.raises(ValueError,match='population/version'):run.execute(args,test_mode=True)
    assert not run.RESULTS.exists()


def test_completed_cli_resume_never_calls_simulator(tmp_path,monkeypatch,capsys):
    import local_cli,subprocess,sys
    parent=tmp_path/'done';dump(parent/'status.json',dict(status='completed_live',last_completed_tick=10))
    monkeypatch.setattr(sys,'argv',['local_cli.py','resume','--run-dir',str(parent)])
    monkeypatch.setattr(subprocess,'call',lambda *a,**k:pytest.fail('must not start a completed run'))
    assert local_cli.main()==0 and '已经完成' in capsys.readouterr().out
