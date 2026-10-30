"""Shared, durable rotation across three to five encrypted MiniMax key slots."""
import math
import threading
import time
from pathlib import Path
from api_router import Route,can_switch,NO_SWITCH_CODES
from model import dump,read_json


class NoUsableKey(RuntimeError):
    def __init__(self,retry_at):
        self.retry_at=retry_at
        super().__init__('All API key slots are cooling down or already failed for this decision')


class RoundRobinKeyRouter:
    is_round_robin=True

    def __init__(self,path,event,slots=('primary','backup','third'),clock=None,cooldown=60,quota_cooldown=3600):
        self.path,self.event=Path(path),event
        self.slots=tuple(slots)
        from credentials import KEY_SLOTS
        if self.slots not in (KEY_SLOTS[:3],KEY_SLOTS[:4],KEY_SLOTS):
            raise ValueError('Round robin requires three to five ordered configured slots')
        self.clock=clock or time.time
        self.cooldown,self.quota_cooldown=cooldown,quota_cooldown
        self.lock=threading.RLock();self.probing=set()
        self.state=read_json(self.path) if self.path.exists() else dict(version=1,policy='round_robin_v1',
            next_index=0,slots=list(self.slots),blocked_until={s:0. for s in self.slots},
            epochs={s:0 for s in self.slots},failure_count={s:0 for s in self.slots})
        if (self.state.get('version')!=1 or self.state.get('policy')!='round_robin_v1'
                or self.state.get('slots')!=list(self.slots) or type(self.state.get('next_index')) is not int
                or not 0<=self.state['next_index']<len(self.slots)):
            raise ValueError('Invalid round robin state')
        for key in ('blocked_until','epochs','failure_count'):
            if set(self.state.get(key,{}))!=set(self.slots):
                raise ValueError('Invalid round robin state')
        if any(type(v) not in (int,float) or not math.isfinite(v) or v<0 for v in self.state['blocked_until'].values()):
            raise ValueError('Invalid key cooldown')

    @staticmethod
    def switchable(diagnostic):
        return can_switch(diagnostic) or (diagnostic.get('status_code')==403
            and diagnostic.get('service_status_code') not in NO_SWITCH_CODES)

    def _available(self,exclude=()):
        now=self.clock()
        return [s for s in self.slots if s not in exclude and s not in self.probing
                and self.state['blocked_until'][s]<=now]

    def acquire(self,exclude=()):
        with self.lock:
            available=self._available(exclude)
            if not available:
                raise NoUsableKey(min(self.state['blocked_until'].values()))
            for offset in range(len(self.slots)):
                index=(self.state['next_index']+offset)%len(self.slots);slot=self.slots[index]
                if slot in available:break
            probe=self.state['blocked_until'][slot]>0
            if probe:self.probing.add(slot)
            self.state['next_index']=(index+1)%len(self.slots)
            dump(self.path,self.state)
            return Route(slot,probe,self.state['epochs'][slot])

    def abort(self,route):
        with self.lock:
            if route.epoch==self.state['epochs'][route.slot]:
                self.probing.discard(route.slot)

    def succeeded(self,route):
        with self.lock:
            if route.epoch!=self.state['epochs'][route.slot]:return
            self.probing.discard(route.slot)
            self.state['blocked_until'][route.slot]=0.
            dump(self.path,self.state)

    def failed(self,route,diagnostic):
        with self.lock:
            if route.epoch==self.state['epochs'][route.slot]:
                self.probing.discard(route.slot)
            if not self.switchable(diagnostic):return False
            if route.epoch==self.state['epochs'][route.slot]:
                hints=diagnostic.get('provider_hints',[])
                delay=self.quota_cooldown if (diagnostic.get('status_code') in (401,402,403)
                    or 'quota_or_balance' in hints) else self.cooldown
                retry=diagnostic.get('retry_after_seconds')
                if type(retry) in (int,float) and math.isfinite(retry):delay=max(delay,retry)
                self.state['blocked_until'][route.slot]=self.clock()+delay
                self.state['epochs'][route.slot]+=1
                self.state['failure_count'][route.slot]+=1
                dump(self.path,self.state)
                self.event('api_slot_cooling_down',api_key_slot=route.slot,
                    retry_at=self.state['blocked_until'][route.slot],http_status=diagnostic.get('status_code'),
                    service_status_code=diagnostic.get('service_status_code'))
                print(f"API router: {route.slot} unavailable; trying another key, cooldown={delay:g}s.",flush=True)
            return bool(self._available())
