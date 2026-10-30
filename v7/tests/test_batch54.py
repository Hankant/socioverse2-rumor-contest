from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import threading,time
import pytest
import run
from batch_resources import SharedLimiter,ConditionGate
from batch_tables import count_rows,WorkbookJob
from model import read_json


def test_54_conditions_share_only_two_http_slots(tmp_path):
    limiter=SharedLimiter(tmp_path/'global.json',2);lock=threading.Lock();active=0;peak=0;seen=set()
    def request(i):
        nonlocal active,peak
        with limiter.slot():
            with lock:active+=1;peak=max(peak,active);seen.add(i)
            time.sleep(.01)
            with lock:active-=1
    with ThreadPoolExecutor(54) as pool:list(pool.map(request,range(54)))
    assert peak==2 and len(seen)==54 and limiter.max_observed==2


def test_count_types_and_pending_jobs_are_not_fake_results(setup,tmp_path):
    cfg,env=setup;env.reset(cfg['behavior_seed']);main,detail=count_rows(env,0)
    assert sum(r['population'] for r in main if r['type']!='全体')==300
    assert all(r['believe']==r['reject']==0 and r['unjudged']==r['population'] for r in main+detail)
    assert sum(r['population'] for r in detail if r['dimension']=='MBTI')==300
    job=WorkbookJob(tmp_path/'job.json','test',cfg,'test.xlsx');job.progress(tmp_path,dict(status='running',last_completed_tick=0),cfg,env,0,{})
    saved=read_json(tmp_path/'job.json');assert {r['tick'] for r in saved['rows']}=={0}


def test_prepare_creates_54_distinct_configs_and_jobs(tmp_path):
    from batch54 import prepare
    batch=prepare(tmp_path/'results');state=read_json(batch/'batch_status.json')
    assert len(state['cases'])==54 and len(list((batch/'jobs').glob('*.json')))==54
    assert all(c['status']=='queued' and c['last_completed_tick']==0 for c in state['cases'].values())
    assert len({c['filename'] for c in state['cases'].values()})==54


@pytest.mark.parametrize('events',[None,[],[dict(event_id='synthetic-test-B2R-001')]])
def test_loading_workbook_job_retains_transition_records_before_next_tick(tmp_path,events):
    from batch54 import load_job
    job=WorkbookJob(tmp_path/'jobs/test.json','test',run.read_config(),'test.xlsx')
    job.transitions=events;job.write('paused_quota',0)
    restored=load_job(tmp_path,'test');restored.write('paused_quota',0)
    assert read_json(tmp_path/'jobs/test.json').get('belief_to_reject_events')==events


def test_run_roots_and_progress_callbacks_are_independent(tmp_path,monkeypatch):
    from conftest import FakeClient
    from model import V7Decision
    from types import SimpleNamespace
    monkeypatch.setattr(V7Decision,'client_factory',FakeClient)
    monkeypatch.setattr(run,'RESULTS',tmp_path/'forbidden-default-results')
    args=SimpleNamespace(config=None,steps=1,resume=None,concurrency=None,max_requests=None,execution_limit_migration=False)
    progress=[]
    roots=dict(results=tmp_path/'case/runs',configs=tmp_path/'case/configs',logs=tmp_path/'case/logs')
    folder=run.execute(args,test_mode=True,run_roots=roots,progress_callback=lambda f,s,c,e,t,m:progress.append((t,m['population_n'])))
    assert folder.parent==roots['results'] and progress==[(0,300),(1,300)]
    assert not run.RESULTS.exists()
