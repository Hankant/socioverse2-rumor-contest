"""One FIFO request queue and one key router shared by 54 independent studies."""
from collections import deque
from contextlib import contextmanager
from pathlib import Path
import json,threading,time,os,tempfile,math
from model import dump,read_json,retry_file
from throttle import RateGate
from llm_client import LiveClient
from round_robin_router import RoundRobinKeyRouter
from api_router import Route,RATE_CODES


class BatchPauseRequested(RuntimeError):pass


def telemetry(path,value):
    """Atomic visibility for live counters, without a disk barrier per counter.

    Budgets, request bodies, validated answers and key cooldowns still use
    model.dump(). Live active/queued counters are reconstructed on startup.
    """
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    fd,temporary=tempfile.mkstemp(dir=path.parent,prefix='.telemetry-',suffix='.tmp')
    try:
        with os.fdopen(fd,'w',encoding='utf-8') as stream:
            json.dump(value,stream,ensure_ascii=False)
        retry_file(lambda:os.replace(temporary,path))
    finally:
        if os.path.exists(temporary):os.unlink(temporary)


class SharedLimiter:
    def __init__(self,path,ceiling=2):
        self.path=Path(path);self.controls_path=self.path.parent/'request_controls.json';self.controls_stamp=None;self.next_controls_check=0.
        if self.controls_path.exists():
            ceiling=self._requested_limit(read_json(self.controls_path));self.controls_stamp=self.controls_path.stat().st_mtime_ns
        self.ceiling=ceiling;self.cv=threading.Condition();self.queue=deque();self.active=0;self.max_observed=0
        old=read_json(self.path) if self.path.exists() else {}
        self.effective=ceiling if old.get('ceiling',ceiling)!=ceiling else min(ceiling,old.get('effective_concurrency',ceiling));self.cooldown_until=old.get('cooldown_until',0.)
        self.successes=0;self.since=time.time();self.stop=threading.Event()
        self.pause_file=self.path.parent/'PAUSE_REQUESTED.json'
    @staticmethod
    def _requested_limit(controls):
        value=controls.get('max_global_concurrency')
        if type(value) is not int or not 1<=value<=10:raise ValueError('Global API concurrency must be an integer from 1 to 10')
        return value
    def _refresh_controls(self):
        if time.monotonic()<self.next_controls_check:return
        self.next_controls_check=time.monotonic()+1.
        if not self.controls_path.exists():return
        stamp=self.controls_path.stat().st_mtime_ns
        if stamp==self.controls_stamp:return
        requested=self._requested_limit(read_json(self.controls_path));self.controls_stamp=stamp
        if requested!=self.ceiling:
            self.ceiling=requested;self.effective=requested;self.successes=0;self.since=time.time()
            self.save();self.cv.notify_all()
    def save(self):
        telemetry(self.path,dict(ceiling=self.ceiling,effective_concurrency=self.effective,active_requests=self.active,queued_requests=len(self.queue),max_observed=self.max_observed,cooldown_until=self.cooldown_until,updated_at=time.time()))
    def restrict_ceiling(self,requested):
        """Lower admission immediately, allowing existing requests to drain."""
        with self.cv:
            self.ceiling=min(self.ceiling,requested);self.effective=min(self.effective,self.ceiling)
            self.successes=0;self.since=time.time();self.save();self.cv.notify_all()
    @contextmanager
    def slot(self,halted=lambda:False):
        ticket=object()
        with self.cv:
            self.queue.append(ticket)
            try:
                while True:
                    if self.pause_file.exists() or self.stop.is_set():raise BatchPauseRequested('Batch paused before dispatch; keep all outcomes')
                    if halted():raise RuntimeError('Condition request gate halted; keep cached outcomes')
                    self._refresh_controls()
                    if self.queue[0] is ticket and self.active<self.effective and time.time()>=self.cooldown_until:
                        self.queue.popleft();self.active+=1;self.max_observed=max(self.max_observed,self.active);self.save();self.cv.notify_all();break
                    self.cv.wait(.5)
            except BaseException:
                if ticket in self.queue:self.queue.remove(ticket)
                self.cv.notify_all();raise
        try:yield
        finally:
            with self.cv:self.active-=1;self.save();self.cv.notify_all()
    def limited(self,diagnostic=None):
        with self.cv:
            delay=2.;retry=(diagnostic or {}).get('retry_after_seconds')
            if type(retry) in (int,float):delay=max(delay,retry)
            self.effective=max(1,self.effective//2);self.cooldown_until=max(self.cooldown_until,time.time()+delay);self.successes=0;self.since=time.time();self.save();self.cv.notify_all()
    def succeeded(self):
        with self.cv:
            self.successes+=1
            if self.effective<self.ceiling and self.successes>=20 and time.time()-self.since>=60:
                self.effective+=1;self.successes=0;self.since=time.time()
            self.save();self.cv.notify_all()


class ConditionGate:
    def __init__(self,local,shared,router=None):self.local,self.shared,self.router=local,shared,router
    @contextmanager
    def slot(self):
        with self.local.slot():
            with self.shared.slot(lambda:self.local.halted):
                try:yield
                finally:
                    if self.router:self.router.release_current()
    def halt(self):self.local.halt()
    def failed(self):self.local.failed()
    def succeeded(self):self.local.succeeded();self.shared.succeeded()
    def limited(self,failures,retry_after=None):
        self.local.limited(failures,retry_after);self.shared.limited(dict(retry_after_seconds=retry_after))


class SharedRouter(RoundRobinKeyRouter):
    """Bound each key independently; one refused key never blocks healthy keys.

    Recovery uses one real queued decision after the deadline, rather than
    extra health-check requests. A lease covers dispatch through HTTP outcome;
    ConditionGate also releases it if pre-dispatch bookkeeping raises.
    """
    def __init__(self,*a,limiter,slot_limits=None,retry_interval=600,rate_limit_fallback=None,fallback_active=False,**kw):
        self.limiter=limiter;self.refusal_path=limiter.path.parent/'last-provider-refusal.json'
        self.last_refusal=read_json(self.refusal_path) if self.refusal_path.exists() else None
        if type(retry_interval) is not int or not 1<=retry_interval<=86400:raise ValueError('Invalid API recovery interval')
        kw.update(cooldown=retry_interval,quota_cooldown=retry_interval)
        super().__init__(*a,**kw)
        self.limits=dict(slot_limits or {s:1 for s in self.slots})
        if (set(self.limits)!=set(self.slots) or any(type(n) is not int or not 0<=n<=10 for n in self.limits.values())
                or not any(self.limits.values())):
            raise ValueError('Provide integer capacities per configured API slot and at least one active slot')
        self.fallback=rate_limit_fallback;self.fallback_active=bool(fallback_active)
        if self.fallback is not None:
            fallback_ceiling=SharedLimiter._requested_limit(self.fallback)
            limits=self.fallback.get('api_slot_concurrency',{})
            if (set(limits)!=set(self.slots) or any(type(n) is not int or not 1<=n<=self.limits[s] for s,n in limits.items())
                    or sum(limits.values())!=fallback_ceiling):raise ValueError('Invalid rate-limit fallback capacities')
        self.retry_interval=retry_interval;self.cv=threading.Condition(self.lock)
        self.active={s:0 for s in self.slots};self.peak=dict(self.active);self.leases={};self.owners={}
        self.capacity_policy='fixed_per_key_v1';self.spillover_limits=dict(self.limits);self.last_allocation=None
        self.floating_slots=();self.floating_cursor=0;self.floating_lease=None
        self.suspended_until={s:0. for s in self.slots};self.slot_labels={s:s for s in self.slots}
        self.schedule=tuple(s for i in range(max(self.limits.values())) for s in self.slots if self.limits[s]>i)
        self.cursor=0;self.peak_total=0
        self.capacity_path=limiter.path.parent/'api-capacity-state.json'
        self.controls_stamp=None;self.next_controls_check=0.
        with self.cv:self._refresh_controls(force=True)
        self._save_capacity()

    def _refresh_controls(self,force=False):
        """Apply explicit capacity/probe requests without restarting 54 cases."""
        if not force and time.monotonic()<self.next_controls_check:return
        self.next_controls_check=time.monotonic()+1.
        path=self.limiter.controls_path
        if not path.exists():return
        stamp=path.stat().st_mtime_ns
        if stamp==self.controls_stamp:return
        controls=read_json(path);limits=controls.get('api_slot_concurrency',self.limits)
        ceiling=SharedLimiter._requested_limit(controls)
        floating=controls.get('api_floating_lane_slots',list(self.floating_slots))
        if (not isinstance(floating,list) or not all(isinstance(s,str) for s in floating)
                or len(set(floating))!=len(floating)
                or not set(floating)<=set(self.slots)):
            raise ValueError('Invalid floating API lane slots')
        if (set(limits)!=set(self.slots) or any(type(n) is not int or not 0<=n<=10 for n in limits.values())
                or sum(limits.values())+bool(floating)<ceiling):raise ValueError('Invalid runtime API slot capacities')
        suspended=controls.get('api_suspended_until',{})
        if (not isinstance(suspended,dict) or not set(suspended)<=set(self.slots)
                or any(type(n) not in (int,float) or not math.isfinite(n) or n<0 for n in suspended.values())):
            raise ValueError('Invalid explicit API suspension deadlines')
        labels=controls.get('api_slot_labels',self.slot_labels)
        if (not isinstance(labels,dict) or set(labels)!=set(self.slots)
                or any(not isinstance(label,str) or not label or len(label)>40 for label in labels.values())):
            raise ValueError('Invalid API slot labels')
        capacity_policy=controls.get('api_capacity_policy',self.capacity_policy)
        if capacity_policy not in ('fixed_per_key_v1','elastic_failover_v1'):
            raise ValueError('Invalid API capacity policy')
        if floating and (capacity_policy!='elastic_failover_v1' or ceiling<2):
            raise ValueError('Floating lane requires elastic routing and at least two total lanes')
        spillover=controls.get('api_spillover_max_concurrency',limits)
        if (not isinstance(spillover,dict) or set(spillover)!=set(self.slots)
                or any(type(n) is not int or not limits[s]<=n<=10 for s,n in spillover.items())):
            raise ValueError('Invalid API spillover capacities')
        fallback=controls.get('rate_limit_fallback',self.fallback)
        if fallback is not None:
            lower=fallback.get('api_slot_concurrency',{})
            if (set(lower)!=set(self.slots) or any(type(n) is not int or not 1<=n<=limits[s] for s,n in lower.items())
                    or sum(lower.values())!=SharedLimiter._requested_limit(fallback)):
                raise ValueError('Invalid runtime rate-limit fallback')
        fallback_active=controls.get('rate_limit_fallback_active',self.fallback_active)
        if type(fallback_active) is not bool:raise ValueError('Invalid runtime fallback flag')
        probe=controls.get('recovery_probe_request')
        if probe is not None and (not isinstance(probe,dict) or not isinstance(probe.get('id'),str) or not probe['id']
                or not probe.get('user_authorization') or not isinstance(probe.get('slots'),list)
                or not probe['slots'] or len(set(probe['slots']))!=len(probe['slots']) or not set(probe['slots'])<=set(self.slots)):
            raise ValueError('Invalid explicit API recovery probe request')
        changed=(self.limits!=limits or self.fallback_active!=fallback_active
            or self.capacity_policy!=capacity_policy or self.spillover_limits!=spillover
            or self.floating_slots!=tuple(floating)
            or self.suspended_until!={s:suspended.get(s,0.) for s in self.slots} or self.slot_labels!=labels)
        self.limits.update(limits);self.fallback=fallback;self.fallback_active=fallback_active
        self.capacity_policy=capacity_policy;self.spillover_limits=dict(spillover)
        self.floating_slots=tuple(floating)
        self.suspended_until={s:suspended.get(s,0.) for s in self.slots};self.slot_labels=dict(labels)
        self.floating_cursor=self.floating_cursor%len(floating) if floating else 0
        self.schedule=tuple(s for i in range(max(self.limits.values())) for s in self.slots if self.limits[s]>i)
        self.cursor%=len(self.schedule)
        if probe and probe['id']!=self.state.get('last_recovery_probe_request'):
            requested=[]
            for slot in probe['slots']:
                if self.state['blocked_until'][slot]>0 and self.suspended_until[slot]<=self.clock():
                    self.state['blocked_until'][slot]=max(self.clock(),1e-9);requested.append(slot)
            # Never discard an in-flight probe. It still owns its lease and
            # must finish before another recovery request can use that key.
            self.state['last_recovery_probe_request']=probe['id'];dump(self.path,self.state)
            self.event('explicit_api_recovery_probe_requested',request_id=probe['id'],api_key_slots=requested)
        self.controls_stamp=stamp
        if changed:self.event('api_capacity_controls_applied',slot_limits=dict(self.limits),
            capacity_policy=self.capacity_policy,spillover_max_concurrency=self.spillover_limits,
            floating_lane_slots=list(self.floating_slots),
            rate_limit_fallback_active=self.fallback_active)
        self._save_capacity();self.cv.notify_all()

    def _available(self,exclude=()):
        return [s for s in super()._available(exclude) if self.suspended_until.get(s,0.)<=self.clock()]

    def _key_priority(self,slot):
        # Main2 takes over main1's overflow; the original ordering is retained
        # for installations without a second primary.
        return (slot!='primary2',slot!='primary',self.slots.index(slot))

    def _base_capacity_limits(self,ceiling):
        """Borrow unavailable keys' capacity inside the unchanged global cap.

        Healthy primary receives overflow first, then other healthy keys in
        configured order. A key due for a probe (or probing) receives only one
        lane until that probe succeeds. Existing leases always drain normally.
        """
        if self.capacity_policy!='elastic_failover_v1':return dict(self.limits)
        now=self.clock();healthy=[];capacities={}
        for slot in self.slots:
            deadline=self.state['blocked_until'][slot]
            if self.suspended_until[slot]>now:
                capacities[slot]=0
            elif deadline==0 and slot not in self.probing:
                healthy.append(slot);capacities[slot]=min(self.limits[slot],ceiling)
            else:
                capacities[slot]=1 if deadline<=now or slot in self.probing else 0
        unused=max(0,ceiling-sum(capacities.values()))
        priority=sorted(healthy,key=self._key_priority)
        for slot in priority:
            extra=min(unused,max(0,min(ceiling,self.spillover_limits[slot])-capacities[slot]))
            capacities[slot]+=extra;unused-=extra
        return capacities

    def _capacity_plan(self):
        reserved=bool(self.floating_slots)
        base=self._base_capacity_limits(max(0,self.limiter.ceiling-reserved))
        capacities=dict(base);target=None
        if reserved:
            if self.floating_lease in self.leases:
                target=self.leases[self.floating_lease].slot
            else:
                order=[self.floating_slots[(self.floating_cursor+i)%len(self.floating_slots)]
                    for i in range(len(self.floating_slots))]
                # Prefer the configured secondary rotation, then the other
                # healthy keys if all secondaries are cooling down or capped.
                order.extend(s for s in sorted(self.slots,key=self._key_priority) if s not in order)
                target=next((s for s in order if self.state['blocked_until'][s]==0
                    and self.suspended_until[s]<=self.clock()
                    and s not in self.probing and base[s]<self.spillover_limits[s]),None)
            if target is not None:capacities[target]+=1
        return capacities,base,target

    def _capacity_limits(self):return self._capacity_plan()[0]

    def _save_capacity(self):
        capacities=self._capacity_limits()
        if self.capacity_policy=='elastic_failover_v1' and capacities!=self.last_allocation:
            self.last_allocation=dict(capacities)
            self.event('api_elastic_capacity_reallocated',base_slot_limits=dict(self.limits),
                effective_slot_limits=capacities,global_concurrency=self.limiter.ceiling)
            print(f'API elastic capacity: {capacities}; global maximum={self.limiter.ceiling}.',flush=True)
        telemetry(self.capacity_path,dict(policy='capacity_weighted_v1',slot_limits=self.limits,
            capacity_policy=self.capacity_policy,effective_slot_limits=capacities,
            spillover_max_concurrency=self.spillover_limits,
            floating_lane_slots=list(self.floating_slots),
            floating_lane_active_slot=(self.leases[self.floating_lease].slot
                if self.floating_lease in self.leases else None),
            active_by_slot=self.active,peak_by_slot=self.peak,active_requests=sum(self.active.values()),
            max_observed=self.peak_total,retry_interval_seconds=self.retry_interval,
            rate_limit_fallback_active=self.fallback_active,
            slot_labels=self.slot_labels,suspended_until=self.suspended_until,
            blocked_until=self.state['blocked_until'],probing=sorted(self.probing),updated_at=self.clock()))

    def _activate_rate_fallback(self,diagnostic):
        if self.fallback is None or self.fallback_active:return
        if diagnostic.get('status_code') not in (429,529) and diagnostic.get('service_status_code') not in RATE_CODES:return
        with self.limiter.cv:
            controls=read_json(self.limiter.controls_path) if self.limiter.controls_path.exists() else {}
            ceiling=min(self.limiter.ceiling,SharedLimiter._requested_limit(self.fallback))
            controls.update(max_global_concurrency=ceiling,api_slot_concurrency=dict(self.fallback['api_slot_concurrency']),
                rate_limit_fallback=self.fallback,rate_limit_fallback_active=True,rate_limit_fallback_at=self.clock(),
                rate_limit_fallback_reason=dict(http_status=diagnostic.get('status_code'),service_status_code=diagnostic.get('service_status_code')))
            # Persist before admitting a replacement. Ordinary restarts cannot
            # silently restore the six-slot setting after a rate-limit fallback.
            dump(self.limiter.controls_path,controls)
            self.limiter.restrict_ceiling(ceiling)
            self.limiter.controls_stamp=self.limiter.controls_path.stat().st_mtime_ns
        self.limits.update(self.fallback['api_slot_concurrency'])
        self.schedule=tuple(s for i in range(max(self.limits.values())) for s in self.slots if self.limits[s]>i)
        self.cursor=0;self.fallback_active=True
        self.event('api_rate_limit_fallback_activated',global_concurrency=ceiling,slot_limits=dict(self.limits),automatic_restore=False)
        print(f'API rate limit: reducing global capacity to {ceiling}; per-key limits={self.limits}. Existing responses will be saved.',flush=True)

    def acquire(self,exclude=()):
        with self.cv:
            announced=False
            while True:
                if self.limiter.stop.is_set() or self.limiter.pause_file.exists():
                    raise BatchPauseRequested('Batch paused before API lease; no request sent')
                self._refresh_controls()
                # Durable deadlines replace decision-local exclusions. A refused
                # slot stays unavailable until its one recovery probe succeeds.
                capacities,base_capacities,floating_target=self._capacity_plan()
                room=(self.capacity_policy!='elastic_failover_v1'
                    or sum(self.active.values())<self.limiter.ceiling)
                available=[s for s in self._available() if room and self.active[s]<capacities[s]]
                probes=[s for s in available if self.state['blocked_until'][s]>0]
                if probes:
                    slot=min(probes,key=lambda s:self.state['blocked_until'][s])
                elif available:
                    for offset in range(len(self.schedule)):
                        index=(self.cursor+offset)%len(self.schedule);slot=self.schedule[index]
                        if slot in available:break
                    self.cursor=(index+1)%len(self.schedule)
                else:
                    if not announced:
                        self.event('api_capacity_wait',active_by_slot=dict(self.active),blocked_until=dict(self.state['blocked_until']))
                        announced=True
                    self.cv.wait(.5)
                    continue
                probe=self.state['blocked_until'][slot]>0
                if probe:self.probing.add(slot)
                route=Route(slot,probe,self.state['epochs'][slot]);key=id(route)
                floating=(bool(self.floating_slots) and self.floating_lease not in self.leases
                    and slot==floating_target and self.active[slot]>=base_capacities[slot])
                self.leases[key]=route;self.owners[key]=threading.get_ident()
                if floating:
                    self.floating_lease=key
                    if slot in self.floating_slots:
                        self.floating_cursor=(self.floating_slots.index(slot)+1)%len(self.floating_slots)
                    self.event('api_floating_lane_acquired',api_key_slot=slot,
                        preferred_slots=list(self.floating_slots),fallback=slot not in self.floating_slots)
                self.active[slot]+=1;self.peak[slot]=max(self.peak[slot],self.active[slot])
                self.peak_total=max(self.peak_total,sum(self.active.values()))
                self._save_capacity()
                self.event('api_route_lease_acquired',api_key_slot=slot,probe=probe,
                    active_by_slot=dict(self.active),routing_policy='capacity_weighted_v1',
                    capacity_policy=self.capacity_policy,effective_slot_limits=capacities,
                    borrowed_capacity=self.active[slot]>self.limits[slot],floating_lane=bool(floating))
                if probe:print(f'API router: probing {slot} after recovery interval.',flush=True)
                return route

    def _release(self,route):
        if self.leases.pop(id(route),None) is not None:
            self.owners.pop(id(route),None);self.active[route.slot]-=1
            if self.floating_lease==id(route):self.floating_lease=None
        self._save_capacity();self.cv.notify_all()

    def release_current(self):
        with self.cv:
            for key in [k for k,owner in self.owners.items() if owner==threading.get_ident()]:
                self.abort(self.leases[key])

    def abort(self,route):
        with self.cv:
            super().abort(route);self._release(route)

    def succeeded(self,route):
        with self.cv:
            # A healthy success changes no durable cooldown state. Persist
            # actual recovery transitions, rather than fsyncing unchanged JSON
            # while holding the router lock after every successful HTTP call.
            if route.epoch==self.state['epochs'][route.slot]:
                changed=self.state['blocked_until'][route.slot]!=0
                self.probing.discard(route.slot)
                self.state['blocked_until'][route.slot]=0.
                if changed:dump(self.path,self.state)
            self._release(route)
            if route.probe:
                self.event('api_slot_probe_completed',api_key_slot=route.slot,restored=self.state['blocked_until'][route.slot]==0)

    def failed(self,route,diagnostic):
        with self.cv:
            switchable=self.switchable(diagnostic)
            if switchable:
                self.last_refusal=diagnostic;dump(self.refusal_path,diagnostic)
                self._activate_rate_fallback(diagnostic)
            try:super().failed(route,diagnostic)
            finally:self._release(route)
            # Capacity exhaustion is a wait, not a provider refusal. Even if all
            # keys cool down, stay in the same run and probe at the deadline.
            # Unknown outcomes and invalid requests still use LiveClient guards.
            return switchable


def client_class(batch_dir,cfg):
    from credentials import load_keys,vault_path
    batch_dir=Path(batch_dir);shared=SharedLimiter(batch_dir/'global-request-state.json',2)
    lock=threading.Lock()
    def event(stage,**fields):
        with lock:
            with (batch_dir/'routing-events.jsonl').open('a',encoding='utf-8') as f:f.write(json.dumps(dict(time=time.time(),stage=stage,**fields))+'\n')
    controls=read_json(batch_dir/'request_controls.json') if (batch_dir/'request_controls.json').exists() else {}
    router=SharedRouter(vault_path().parent/'routing-round-robin.json',event,slots=tuple(load_keys()),limiter=shared,
        slot_limits=controls.get('api_slot_concurrency'),retry_interval=controls.get('api_retry_interval_seconds',600),
        rate_limit_fallback=controls.get('rate_limit_fallback'),fallback_active=controls.get('rate_limit_fallback_active',False))
    class BatchClient(LiveClient):
        def __init__(self,config,audit):
            super().__init__(config,audit)
            self.router=router;self._gate=ConditionGate(RateGate(config,audit,self.event),shared,router)
            self.event('batch_runtime_routing_enabled',routing_policy='capacity_weighted_v1',
                global_concurrency=shared.ceiling,slot_limits=router.limits,retry_interval_seconds=router.retry_interval)
    BatchClient.shared_limiter=shared
    BatchClient.shared_router=router
    return BatchClient
