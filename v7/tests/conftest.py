from pathlib import Path
import sys,copy,threading
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app_v7'))
import pytest
import run
from model import V7Environment,load_rows,dump,read_json,digest,COMPONENT_KEYS
from decision_conditions import CONDITION_LABELS,condition_reference


@pytest.fixture(autouse=True)
def forbid_network(monkeypatch):
    import httpx,socket
    def blocked(*a,**k):raise AssertionError('V7 engineering tests must never access a network')
    monkeypatch.setattr(httpx.Client,'send',blocked);monkeypatch.setattr(socket.socket,'connect',blocked)


@pytest.fixture
def setup(tmp_path):
    cfg=run.read_config();_,bundle,_,_=run.make_bundles(run.SOURCE/'01_Agent基础信息表.csv',run.SOURCE/'02_Prompt固定提示词.md',cfg,tmp_path/'audit')
    env=V7Environment(bundle);env.reset(cfg['behavior_seed']);env.advance_to(1)
    return cfg,env


def answer(ob,score=61,comment=False,repost=False):
    root=ob.local_information['posts'][0]['content_id']
    return dict(subjective_credibility=score,component_credibility={k:score for k in COMPONENT_KEYS},
        comment=dict(enabled=comment,target_content_id=root if comment else None,text='测试专用评论' if comment else ''),
        repost=dict(enabled=repost,target_content_id=root if repost else None,text='测试专用转发' if repost else ''),
        evidence_ids=[root],condition_context_ref=condition_reference(ob),
        condition_application={k:dict(affects=['credibility','comment','repost'],note='仅供离线验证条件覆盖') for k in CONDITION_LABELS})


class FakeClient:
    """Offline transport double only. Never imported by production code."""
    fail_tick=None
    lock=threading.RLock()
    def __init__(self,cfg,audit):
        self.cfg=cfg;self.audit=Path(audit);self.cache=self.audit/'response_cache';self.cache.mkdir(parents=True,exist_ok=True)
        self.calls=[];self.gate=SimpleNamespace(halt=lambda:None)
        self.budget=read_json(self.audit/'budget.json') if (self.audit/'budget.json').exists() else dict(requests=0,input_reserved_units=0,output_reserved_tokens=0,actual_input_tokens=0,actual_output_tokens=0,usage_unknown_requests=0)
    def preflight_batch(self,obs,template):pass
    def close(self):pass
    def decide(self,ob,template):
        with self.lock:
            signature=digest(ob.model_dump(mode='json'));path=self.cache/f'{signature}.json'
            if path.exists():
                value=read_json(path);return value['answer'],ob.local_information['posts'],dict(used_memory_ticks=[m['tick'] for m in ob.local_physical['memory']],cached=True)
            if self.fail_tick==ob.step and sum(t==ob.step for t,a in self.calls)>=3:raise RuntimeError('Deliberate test interruption')
            value=answer(ob,score=(int(ob.agent_id[1:])+ob.step*7)%101,comment=int(ob.agent_id[1:])%3==0,repost=bool(any(p['can_repost'] for p in ob.local_information['posts'])))
            available=next((p for p in ob.local_information['posts'] if p['can_repost']),None)
            if available:value['repost']['target_content_id']=available['content_id']
            self.calls.append((ob.step,ob.agent_id));self.budget['requests']+=1;self.budget['input_reserved_units']+=100;self.budget['output_reserved_tokens']+=100
            dump(path,dict(answer=value));dump(self.audit/'budget.json',self.budget)
            return value,ob.local_information['posts'],dict(used_memory_ticks=[m['tick'] for m in ob.local_physical['memory']],cached=False)
