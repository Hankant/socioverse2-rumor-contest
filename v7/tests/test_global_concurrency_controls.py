from concurrent.futures import ThreadPoolExecutor
import threading,time
import pytest
from model import dump,read_json
from batch_resources import SharedLimiter


def test_five_global_slots_are_used_and_never_exceeded(tmp_path):
    dump(tmp_path/'request_controls.json',dict(max_global_concurrency=5))
    dump(tmp_path/'state.json',dict(ceiling=2,effective_concurrency=1,cooldown_until=0))
    limiter=SharedLimiter(tmp_path/'state.json',2);assert limiter.ceiling==limiter.effective==5
    active=peak=0;lock=threading.Lock();seen=[]
    def call(i):
        nonlocal active,peak
        with limiter.slot():
            with lock:active+=1;peak=max(peak,active);seen.append(i)
            time.sleep(.025)
            with lock:active-=1
    with ThreadPoolExecutor(54) as pool:list(pool.map(call,range(54)))
    assert peak==5 and len(set(seen))==54 and limiter.max_observed==5
    assert read_json(tmp_path/'state.json')['ceiling']==5


def test_running_queue_picks_up_new_limit_without_restart(tmp_path):
    limiter=SharedLimiter(tmp_path/'state.json',2);release=threading.Event();two=threading.Event();five=threading.Event();lock=threading.Lock();active=0
    def call():
        nonlocal active
        with limiter.slot():
            with lock:
                active+=1
                if active==2:two.set()
                if active==5:five.set()
            release.wait(4)
            with lock:active-=1
    with ThreadPoolExecutor(5) as pool:
        futures=[pool.submit(call) for _ in range(5)]
        assert two.wait(2)
        dump(tmp_path/'request_controls.json',dict(max_global_concurrency=5))
        assert five.wait(3)
        release.set()
        for f in futures:f.result()
    assert limiter.ceiling==limiter.max_observed==5


@pytest.mark.parametrize('value',[0,11,True,5.0,'5',None])
def test_invalid_concurrency_is_rejected(tmp_path,value):
    dump(tmp_path/'request_controls.json',dict(max_global_concurrency=value))
    with pytest.raises(ValueError):SharedLimiter(tmp_path/'state.json')


def test_new_limit_keeps_provider_cooldown_and_adaptive_protection(tmp_path):
    deadline=time.time()+20
    dump(tmp_path/'request_controls.json',dict(max_global_concurrency=5,revision=1))
    dump(tmp_path/'state.json',dict(ceiling=2,effective_concurrency=1,cooldown_until=deadline))
    limiter=SharedLimiter(tmp_path/'state.json');assert limiter.cooldown_until==deadline
    limiter.limited({'retry_after_seconds':30});assert limiter.ceiling==5 and limiter.effective==2
    dump(tmp_path/'request_controls.json',dict(max_global_concurrency=5,revision=2))
    limiter.next_controls_check=0
    with limiter.cv:limiter._refresh_controls()
    assert limiter.effective==2 and limiter.cooldown_until>=deadline
