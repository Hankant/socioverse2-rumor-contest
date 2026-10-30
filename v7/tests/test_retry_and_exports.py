import csv
from concurrent.futures import ThreadPoolExecutor
import pytest
import run
from model import read_json,dump
from auto_retry import eligible,decision_after_wait
from round_robin_router import RoundRobinKeyRouter,NoUsableKey
from csv_io import ensure_large_fields,atomic_csv


def info(tmp_path):
    return dict(run_dir=str(tmp_path),status=dict(error_type='QuotaPause',export_status='complete'),
        provenance=dict(config=run.read_config()),budget=dict(requests=10,input_reserved_units=100,actual_input_tokens=100,output_reserved_tokens=100),
        unknown=[],recent_request=dict(diagnostic=dict(status_code=429)))


def test_two_minute_recovery_preserves_science_and_budget(tmp_path):
    data=info(tmp_path);waits=[]
    result=decision_after_wait(data,lambda *a:None,lambda n,**k:waits.append(n) or True,ready=lambda i:True,clock=lambda:0)
    assert waits==[2] and result['config']==data['provenance']['config'] and result['authorization']['unknown_reissue']==[]
    assert read_json(tmp_path/'reports/auto_retry.json')['interval_seconds']==120


@pytest.mark.parametrize('reason',['UncertainRequest','HardBudgetPause','PromptBudgetPause','OutputContractPause','ExportPause','KeyboardInterrupt','ValueError'])
def test_no_automatic_retry_for_non_provider_pause(tmp_path,reason):
    data=info(tmp_path);data['status']['error_type']=reason;assert not eligible(data)


@pytest.mark.parametrize('code',[400,401,402,403,404])
def test_no_auto_reissue_for_invalid_or_auth_error(tmp_path,code):
    data=info(tmp_path);data['recent_request']['diagnostic']['status_code']=code;assert not eligible(data)


def test_unknown_or_exhausted_budget_stops_auto_retry(tmp_path):
    data=info(tmp_path);data['unknown']=['unknown-request'];assert not eligible(data)
    data['unknown']=[];data['budget']['requests']=12200;assert not eligible(data)


def test_four_slot_round_robin_and_shared_cooldown(tmp_path):
    now=[0.];slots=('primary','backup','third','fourth');path=tmp_path/'router.json'
    router=RoundRobinKeyRouter(path,lambda *a,**k:None,slots=slots,clock=lambda:now[0])
    assert [router.acquire().slot for _ in range(4)]==list(slots)
    with ThreadPoolExecutor(4) as pool:chosen=list(pool.map(lambda _:router.acquire().slot,range(40)))
    assert all(chosen.count(slot)==10 for slot in slots)
    for _ in slots:router.failed(router.acquire(),{'status_code':429})
    with pytest.raises(NoUsableKey):router.acquire()
    now[0]=120;restarted=RoundRobinKeyRouter(path,lambda *a,**k:None,slots=slots,clock=lambda:now[0])
    route=restarted.acquire();assert route.probe;restarted.succeeded(route)


def test_large_csv_cells_preserved_exactly(tmp_path):
    text='测试大字段'+('甲乙丙'*100000);path=tmp_path/'large.csv'
    with atomic_csv(path) as f:csv.writer(f).writerows([['text'],[text]])
    ensure_large_fields()
    with path.open(encoding='utf-8-sig',newline='') as f:assert list(csv.DictReader(f))[0]['text']==text
