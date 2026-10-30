"""V7: 300 real LLM agents, network exposure, atomic ticks and personal memory."""
from __future__ import annotations
import copy,csv,hashlib,json,math,os,sys,tempfile,time
from collections import Counter
from pathlib import Path
from statistics import mean
import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'vendor/SocioVerse2'))
from socioverse.abc import PopulationProvider,EnvironmentProvider,DecisionModel,MetricCollector
from socioverse.engine import register
from socioverse.schemas import Persona,Observation,Action
from comment_policy import LATEST_FEED_POLICY,PARTICIPATION_POLICY,MEMORY_POLICY,recent_comments,personal_memory_posts
from memory_policy import ROLLING,retained_memory,validate_memory_policy

POPULATION_N=300
INSIDE_N=48
OUTSIDE_N=252
BINARY_SCORE_POLICY='binary_score_gt50_v1'
COMPONENT_KEYS=('funds_redirected','safety_delayed','causal_link')
NETWORK_FEED_POLICIES=frozenset((LATEST_FEED_POLICY,))
FULL_THREAD_POLICIES=NETWORK_FEED_POLICIES


def feed_description(policy,comment_window_limit=30):
    if policy!=LATEST_FEED_POLICY:raise ValueError('V7 requires network-controlled exposure')
    return f'关注与转发决定首次接触；每个可见主帖展示上一轮以前最新{comment_window_limit}条评论；官方独立账号；300名用户均由LLM决策'


def retry_file(operation):
    for attempt in range(6):
        try:
            return operation()
        except PermissionError:
            if attempt == 5:
                raise
            time.sleep(0.2 * (attempt + 1))

def read_json(path):
    return retry_file(lambda: json.loads(Path(path).read_text(encoding="utf-8")))

def dump(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Replace only after the complete JSON is flushed: interruption cannot leave half a ledger.
    # A short random sibling name avoids repeating a 64-character cache hash
    # in temporary filenames near the Windows path-length limit.
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=".write-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        retry_file(lambda: os.replace(temporary, path))
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)

def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()

def exposure_summary(history, feed, tick):
    events = copy.deepcopy(history)
    for p in feed:
        entry = events.setdefault(p["content_id"], {"root_content_id": p["root_content_id"],
            "author_id": p["author_id"], "tick": tick, "ticks": []})
        entry.setdefault("ticks", [entry["tick"]])
        if tick not in entry["ticks"]:
            entry["ticks"].append(tick)
    result = {}
    for e in events.values():
        root = e["root_content_id"]
        row = result.setdefault(root, {"post_count": 0, "presentations": 0, "authors": set(), "ticks": set()})
        row["post_count"] += 1
        row["authors"].add(e["author_id"])
        ticks = e.get("ticks", [e["tick"]])
        row["ticks"].update(ticks)
        row["presentations"] += len(ticks)
    return {root: {"observed_post_count": r["post_count"], "distinct_author_count": len(r["authors"]),
        "presentation_count": r["presentations"], "exposure_tick_count": len(r["ticks"]), "first_seen_tick": min(r["ticks"]),
        "last_seen_tick": max(r["ticks"])} for root, r in sorted(result.items())}

def allowed_evidence_ids(feed, memories):
    ids = set()
    for p in feed + [p for m in memories for p in m["observed_posts"]]:
        ids.add(p["content_id"])
        ids.update(c["comment_id"] for c in p.get("comments", []))
        # Provider text holds original/root text, not the repost caption.
        if isinstance(p.get("text"), str) and p["text"].strip() and p.get("root_content_id"):
            ids.add(p["root_content_id"])
        # Complete-thread observations also display followed accounts' relay
        # captions. Those visible transport IDs are valid evidence, not new roots.
        ids.update(r["content_id"] for r in p.get("relay_context", []))
    return ids

def score_to_belief(score):
    """One authoritative boundary: >50 believe; <=50 reject. No rounding."""
    if type(score) not in (int, float) or not math.isfinite(score) or not 0 <= score <= 100:
        raise ValueError("invalid belief measurement")
    return "believe" if score > 50 else "reject"

def validate_belief_measurement(answer, required=False):
    """Validate the four self-report scores. Classification is a separate policy."""
    present = any(k in answer for k in ("subjective_credibility", "component_credibility"))
    if not present and not required:
        return
    def score(value):
        return type(value) in (int, float) and math.isfinite(value) and 0 <= value <= 100
    components = answer.get("component_credibility")
    if (not score(answer.get("subjective_credibility")) or not isinstance(components, dict)
            or set(components) != set(COMPONENT_KEYS) or not all(score(v) for v in components.values())):
        raise ValueError("invalid belief measurement")


def load_rows(path):
    with Path(path).open(encoding='utf-8-sig',newline='') as f:rows=sorted(csv.DictReader(f),key=lambda r:r['agent_id'])
    if len(rows)!=POPULATION_N or len({r['agent_id'] for r in rows})!=POPULATION_N:
        raise ValueError('V7 requires exactly 300 unique LLM agents')
    if any(r['decision_mode']!='llm' for r in rows):raise ValueError('V7 accepts LLM profiles only')
    if Counter(r['group'] for r in rows)!={'inside':INSIDE_N,'outside':OUTSIDE_N}:
        raise ValueError('V7 population must contain 48 inside and 252 outside users')
    if any((r['follows_source'].lower()=='true')!=(r['group']=='inside') for r in rows):
        raise ValueError('SOURCE followers must match the inside population')
    return rows


def make_network(rows):
    rng=np.random.Generator(np.random.PCG64(20261018));edges=[]
    for r in rows:
        for same,count in ((True,8),(False,2)):
            pool=[p['agent_id'] for p in rows if p['agent_id']!=r['agent_id'] and (p['group']==r['group'])==same]
            edges.extend((r['agent_id'],str(a)) for a in rng.choice(pool,count,replace=False))
        if r['group']=='inside':edges.append((r['agent_id'],'SOURCE'))
    return edges


def belief_states(policy=BINARY_SCORE_POLICY):
    if policy!=BINARY_SCORE_POLICY:raise ValueError('V7 uses score >50 / <=50 only')
    return ('unjudged','believe','reject')


def normalize_answer(raw,feed,memories,already_reposted,belief_policy=BINARY_SCORE_POLICY,comment_target_policy='explicit_visible_root'):
    if not feed:raise ValueError('no content must use idle')
    if belief_policy!=BINARY_SCORE_POLICY or comment_target_policy!='explicit_visible_root':raise ValueError('unsupported V7 decision policy')
    answer=copy.deepcopy(raw);validate_belief_measurement(answer,required=True)
    answer['belief']=score_to_belief(answer['subjective_credibility'])
    answer['belief_basis']='subjective_credibility > 50; score=50 is reject'
    if answer.get('repost') is False and answer.get('target_content_id') is None and answer.get('text','')=='':
        answer['repost']={'enabled':False,'target_content_id':None,'text':''}
        answer.pop('target_content_id',None);answer.pop('text',None)
        answer['format_repairs']=[*answer.get('format_repairs',[]),'explicit_false_repost_to_disabled_object']
    for key in ('comment','repost'):
        item=answer.get(key)
        if not isinstance(item,dict) or type(item.get('enabled')) is not bool or not isinstance(item.get('text'),str):raise ValueError('invalid action schema')
        if key=='comment' and item['enabled'] and not item['text'].strip():raise ValueError('empty enabled comment')
    if answer['comment']['enabled'] and answer['comment'].get('target_content_id') not in {p['content_id'] for p in feed}:raise ValueError('invalid/invisible comment target')
    evidence=answer.get('evidence_ids');allowed=allowed_evidence_ids(feed,memories)
    if not isinstance(evidence,list) or any(not isinstance(v,str) or v not in allowed for v in evidence):raise ValueError('invalid/invisible evidence')
    answer['decision_status']='applied'
    if answer['repost']['enabled']:
        target=next((p for p in feed if p['content_id']==answer['repost'].get('target_content_id')),None)
        if target is None:raise ValueError('invisible repost target')
        if target['root_content_id'] in already_reposted:
            answer['repost']={'enabled':False,'target_content_id':None,'text':''}
            answer.update(decision_status='partially_applied',repost_rejection_reason='duplicate_root_repost')
    for key in ('comment','repost'):
        if not answer[key]['enabled']:answer[key].update(target_content_id=None,text='')
    return answer


@register('population','rumor_v7.population')
class V7Population(PopulationProvider):
    def __init__(self,bundle):self.bundle=bundle;self.rows=load_rows(bundle.provider_args['roster_csv']);self.edges=bundle.interaction.edges
    def build(self,seed):
        return [Persona(agent_id=r['agent_id'],group_key=r['group'],attributes=r,init_state={'current_belief':'unjudged'}) for r in self.rows]
    def neighbors(self,aid):return [b for a,b in self.edges if a==aid]


@register('environment','rumor_v7.environment')
class V7Environment(EnvironmentProvider):
    def __init__(self,bundle):
        self.bundle=bundle;self.cfg=bundle.provider_args;validate_memory_policy(self.cfg)
        self.rows=load_rows(self.cfg['roster_csv']);self.by_id={r['agent_id']:r for r in self.rows}
        self.following={a:set() for a in self.by_id}
        for a,b in self.cfg['edges']:self.following[a].add(b)
        self.direct_targets=self.cfg['direct_targets'];self.government_tick=self.cfg['government_tick']

    def reset(self,seed):
        self.t=0;self.beliefs={a:'unjudged' for a in self.by_id}
        self.credibility={a:None for a in self.by_id};self.component_credibility={a:None for a in self.by_id}
        self.condition_application={a:None for a in self.by_id};self.condition_context_ref={a:None for a in self.by_id}
        self.seen={a:set() for a in self.by_id};self.reposted={a:set() for a in self.by_id};self.memory={a:[] for a in self.by_id}
        self.exposure_history={a:{} for a in self.by_id};self.read_comments={a:set() for a in self.by_id}
        self.last_updated={a:None for a in self.by_id};self.posts={};self.comments={};self.applied={};self.cohort=set();self.transitions={}
        from belief_dynamics import TRANSITION_POLICY,BeliefTransitionTracker
        self.belief_tracker=(BeliefTransitionTracker(self.government_tick,self.by_id,self.cfg['source_trust'],self.cfg['government_trust'])
                            if self.cfg.get('belief_transition_policy')==TRANSITION_POLICY else None)
        self._publish_root('P001','SOURCE',0,self.cfg['rumor_text'])

    def _publish_root(self,cid,author,tick,text):
        self.posts[cid]=dict(content_id=cid,root_content_id=cid,author_id=author,original_author_id=author,published_tick=tick,
                             available_tick=1 if tick==0 else tick,text=text,repost_text='')

    def advance_to(self,t):
        self.t=t
        for aid in self.memory:self.memory[aid]=retained_memory(self.memory[aid],t,self.cfg)
        if t==self.government_tick and 'G001' not in self.posts:self._publish_root('G001','GOVERNMENT',t,self.cfg['correction_text'])
        return [e for e in self.bundle.scheduled_events if e.at_step==t]

    def observe_batch(self,agent_ids,t,round_idx=0):
        out=[]
        for aid in agent_ids:
            feed=[]
            if t>=1:
                delivery=('followed_source' if 'SOURCE' in self.following[aid] else 'rumor_thread_revisit' if 'P001' in self.seen[aid] else 'followee_rumor_repost' if self._visible_relays('P001',aid,t) else None)
                if delivery:feed.append(self._shared_root_view('P001',aid,t,delivery))
                if 'G001' in self.posts and self.posts['G001']['available_tick']<=t:
                    direct=t==self.government_tick and aid in self.direct_targets
                    if direct or 'G001' in self.seen[aid] or self._visible_relays('G001',aid,t):
                        official=self._shared_root_view('G001',aid,t,'direct_government' if direct else 'official_thread_or_followee_repost')
                        feed.insert(0,official) if direct else feed.append(official)
            physical=dict(persona=self.by_id[aid],current_belief=self.beliefs[aid],exposure_history=copy.deepcopy(self.exposure_history[aid]),
                government_trust=self.cfg['government_trust'][aid],source_trust=self.cfg['source_trust'][aid],belief_target=self.cfg['belief_target'],
                subjective_credibility=self.credibility[aid],component_credibility=copy.deepcopy(self.component_credibility[aid]),
                memory=copy.deepcopy(retained_memory(self.memory[aid],t,self.cfg)),already_reposted=sorted(self.reposted[aid]),
                comment_target_policy='explicit_visible_root')
            for key in ('belief_measurement_policy','decision_condition_policy','feed_policy','comment_window_limit','comment_participation_policy','memory_comment_policy','memory_retention_policy','memory_window_ticks'):physical[key]=self.cfg[key]
            for key in ('belief_update_policy','belief_transition_policy','government_trust_prompt_policy'):
                if key in self.cfg:physical[key]=self.cfg[key]
            out.append(Observation(agent_id=aid,step=t,local_physical=physical,local_information={'posts':feed}))
        return out

    def _visible_relays(self, root, aid, t):
        return [p for p in self.posts.values() if p["root_content_id"] == root and p["content_id"] != root
                and p["author_id"] in self.following[aid] and p["available_tick"] <= t
                and 0 < t-p["published_tick"] < 40]

    def _shared_root_view(self, root, aid, t, delivery):
        post = copy.deepcopy(self.posts[root])
        # Include comments by non-followed accounts and comments under any
        # repost of THIS root; preserve IDs, text, author and publication time.
        post["comments"] = sorted([copy.deepcopy(c) for c in self.comments.values()
            if c["published_tick"] < t
            and self.posts.get(c["target_content_id"], {}).get("root_content_id") == root],
            key=lambda c: (c["published_tick"], c["comment_id"]))
        if self.cfg.get("feed_policy")==LATEST_FEED_POLICY:
            post["comments"]=recent_comments(post["comments"],self.cfg["comment_window_limit"],self.cfg["comment_tie_seed"])
        post["relay_context"] = sorted([{
            k: p[k] for k in ("content_id", "author_id", "published_tick", "repost_text")}
            for p in self._visible_relays(root, aid, t)], key=lambda p: (p["published_tick"], p["content_id"]))
        post.update(delivery=delivery, can_repost=root not in self.reposted[aid],
            block_reason="duplicate_root_repost" if root in self.reposted[aid] else None,
            is_reread=root in self.seen[aid], comment_scope="all_earlier_comments_on_root_and_reposts")
        if self.cfg.get("feed_policy")==LATEST_FEED_POLICY:
            post.update(comment_scope=f"latest_{self.cfg['comment_window_limit']}_earlier_comments_per_root",
                comment_window_limit=self.cfg["comment_window_limit"],
                comment_order="newest_tick_then_seeded_hash_v1")
        return post

    def apply(self,actions):
        from decision_conditions import validate_condition_application
        prepared=[];batch=set()
        for a in actions:
            key=(a.step,a.agent_id);signature=digest(a.payload)
            if key in batch:raise ValueError('duplicate action in batch')
            batch.add(key)
            if key in self.applied:
                if self.applied[key]!=signature:raise ValueError('conflicting action for an already committed agent/tick')
                continue
            if a.step!=self.t or a.agent_id not in self.by_id:raise ValueError('action step/agent mismatch')
            ob=self.observe(a.agent_id,a.step);feed=ob.local_information['posts']
            if a.kind=='idle':
                if feed:raise ValueError('an exposed LLM agent cannot silently become idle')
                prepared.append((a,signature,None));continue
            if a.kind!='decide' or a.payload['observed_posts']!=feed:raise ValueError('observation must match the complete visible window')
            retained=retained_memory(self.memory[a.agent_id],a.step,self.cfg)
            if a.payload['used_memory_ticks']!=[m['tick'] for m in retained]:raise ValueError('complete retained personal memory required')
            answer=normalize_answer(a.payload['answer'],feed,retained,self.reposted[a.agent_id])
            validate_condition_application(answer,ob);prepared.append((a,signature,answer))
        for a,signature,answer in prepared:
            aid=a.agent_id
            if answer is not None:
                feed=a.payload['observed_posts'];before=self.beliefs[aid];previous=self.credibility[aid]
                transition_before=dict(current_belief=before,subjective_credibility=previous,
                    exposure_summary=exposure_summary(self.exposure_history[aid],[],a.step)) if self.belief_tracker else None
                self.beliefs[aid]=answer['belief'];self.credibility[aid]=answer['subjective_credibility'];self.component_credibility[aid]=copy.deepcopy(answer['component_credibility'])
                self.condition_application[aid]=copy.deepcopy(answer['condition_application']);self.condition_context_ref[aid]=answer['condition_context_ref'];self.last_updated[aid]=a.step
                for p in feed:
                    entry=self.exposure_history[aid].setdefault(p['content_id'],dict(root_content_id=p['root_content_id'],author_id=p['author_id'],tick=a.step,ticks=[]))
                    if a.step not in entry['ticks']:entry['ticks'].append(a.step)
                    self.read_comments[aid].update(c['comment_id'] for c in p['comments'])
                self.seen[aid].update(p['content_id'] for p in feed)
                if answer['comment']['enabled']:
                    cid=f'C{a.step:02d}-{aid}';self.comments[cid]=dict(comment_id=cid,author_id=aid,published_tick=a.step,target_content_id=answer['comment']['target_content_id'],text=answer['comment']['text'])
                if answer['repost']['enabled']:
                    target=self.posts[answer['repost']['target_content_id']];cid=f'RP{a.step:02d}-{aid}'
                    self.posts[cid]=dict(content_id=cid,root_content_id=target['root_content_id'],author_id=aid,original_author_id=target['original_author_id'],published_tick=a.step,available_tick=a.step+1,text=target['text'],repost_text=answer['repost']['text'],parent_content_id=target['content_id'])
                    self.reposted[aid].add(target['root_content_id'])
                self.memory[aid].append(dict(agent_id=aid,tick=a.step,observed_posts=personal_memory_posts(feed),belief_before=before,belief_after=answer['belief'],subjective_credibility_before=previous,subjective_credibility_after=self.credibility[aid],component_credibility=copy.deepcopy(self.component_credibility[aid]),comment=answer['comment'],repost=answer['repost']))
                self.memory[aid]=retained_memory(self.memory[aid],a.step+1,self.cfg)
                if aid in self.cohort and a.step>=self.government_tick and answer['belief']=='reject':self.transitions.setdefault(aid,a.step)
                if self.belief_tracker:
                    self.belief_tracker.update(aid,a.step,transition_before,dict(current_belief=self.beliefs[aid],
                        subjective_credibility=self.credibility[aid],exposure_summary=exposure_summary(self.exposure_history[aid],[],a.step)))
            self.applied[(a.step,aid)]=signature
        if self.t==self.government_tick-1:self.cohort={a for a,b in self.beliefs.items() if b=='believe'}

    def agent_state(self, aid):
        state=dict(exposure_summary=exposure_summary(self.exposure_history[aid], [], self.t), current_belief=self.beliefs[aid], last_updated_tick=self.last_updated[aid],
                    decision_mode=self.by_id[aid]["decision_mode"], group=self.by_id[aid]["group"],
                    memory_count=len(self.memory[aid]), seen_count=len(self.seen[aid]),
                    subjective_credibility=self.credibility[aid],
                    component_credibility=copy.deepcopy(self.component_credibility[aid]),
                    condition_application=copy.deepcopy(self.condition_application[aid]),
                    condition_context_ref=self.condition_context_ref[aid],
                    synthetic_age=self.by_id[aid].get("synthetic_age"),
                    synthetic_region=self.by_id[aid].get("synthetic_region"),
                    synthetic_occupation=self.by_id[aid].get("synthetic_occupation"),
                    synthetic_mbti_type=self.by_id[aid].get("synthetic_mbti_type"),
                    reposted_roots=sorted(self.reposted[aid]))
        if self.belief_tracker:state.update(self.belief_tracker.agent_summary(aid))
        return state

    def snapshot(self):
        result=dict(tick=self.t,beliefs=self.beliefs,memory=self.memory,exposure_history=self.exposure_history,
            read_comments={a:sorted(v) for a,v in self.read_comments.items()},subjective_credibility=self.credibility,
            component_credibility=self.component_credibility,condition_application=self.condition_application,
            condition_context_ref=self.condition_context_ref,posts=self.posts,comments=self.comments,
            seen={a:sorted(v) for a,v in self.seen.items()},reposted={a:sorted(v) for a,v in self.reposted.items()},cohort=sorted(self.cohort),transitions=self.transitions)
        if self.belief_tracker:result['belief_to_reject_events']=copy.deepcopy(self.belief_tracker.events)
        return result


@register('decision','rumor_v7.decision')
class V7Decision(DecisionModel):
    client_factory=None  # Tests may inject a fake transport; production always uses LiveClient.
    def __init__(self,config,prompt_file,audit_dir):
        from llm_client import LiveClient
        self.cfg=config;self.audit_dir=Path(audit_dir);self.audit_dir.mkdir(parents=True,exist_ok=True)
        self.template=Path(prompt_file).read_text(encoding='utf-8').split('```text',1)[1].split('```',1)[0].strip()
        self.client=(self.client_factory or LiveClient)(config,audit_dir)

    def decide_batch(self,obs,memories):
        from concurrent.futures import ThreadPoolExecutor,wait,FIRST_COMPLETED
        observations=copy.deepcopy(list(obs))
        if len({o.agent_id for o in observations})!=len(observations):raise ValueError('duplicate agent in observation batch')
        self.client.preflight_batch(observations,self.template)
        workers=self.cfg['max_concurrency']
        if workers==1:return self._decide_serial(observations,memories)
        results={};errors=[];index=0
        with ThreadPoolExecutor(max_workers=workers) as pool:
            pending={}
            def submit(i):pending[pool.submit(self._decide_serial,[observations[i]],memories)]=i
            while index<min(workers,len(observations)):submit(index);index+=1
            try:
                while pending:
                    done,_=wait(pending,return_when=FIRST_COMPLETED)
                    for future in done:
                        i=pending.pop(future)
                        try:results[i]=future.result()
                        except Exception as exc:errors.append(exc)
                    if not errors:
                        while len(pending)<workers and index<len(observations):submit(index);index+=1
            except KeyboardInterrupt:
                self.client.gate.halt()
                for future in pending:future.cancel()
                print('正在暂停：停止新请求，等待已发送请求保存缓存。',flush=True);raise
            if errors:
                from llm_client import QuotaPause
                raise next((e for e in errors if isinstance(e,QuotaPause)),errors[0])
        return [action for i in range(len(observations)) for action in results[i]]

    def _decide_serial(self,observations,memories):
        from decision_conditions import validate_condition_application
        actions=[]
        for ob in observations:
            if not ob.local_information['posts']:
                actions.append(Action(agent_id=ob.agent_id,step=ob.step,kind='idle',source='llm',payload={'decision_status':'idle','reason':'no_exposed_posts'}));continue
            try:
                raw,used,meta=self.client.decide(ob,self.template)
                ticks=meta.get('used_memory_ticks',[m['tick'] for m in ob.local_physical['memory']])
                if ticks!=[m['tick'] for m in ob.local_physical['memory']]:raise ValueError('complete retained personal memory required')
                answer=normalize_answer(raw,used,ob.local_physical['memory'],ob.local_physical['already_reposted'])
                validate_condition_application(answer,ob)
            except Exception as exc:
                dump(self.audit_dir/f'failure-{ob.step:02d}-{ob.agent_id}.json',dict(agent_id=ob.agent_id,tick=ob.step,error_type=type(exc).__name__,decision_status='error',note='Tick not committed; successful LLM decisions remain cached.'))
                raise
            payload=dict(answer=answer,raw_answer=raw,observed_posts=used,api=meta,used_memory_ticks=ticks,decision_status=answer['decision_status'])
            actions.append(Action(agent_id=ob.agent_id,step=ob.step,kind='decide',source='llm',payload=payload))
        return actions


@register('collector','rumor_v7.metrics')
class V7Metrics(MetricCollector):
    def collect(self,env,actions,t):
        result={'population_n':len(env.by_id),'remaining_agents':len(env.by_id)}
        for group in ('all','inside','outside'):
            counts=Counter(b for aid,b in env.beliefs.items() if group=='all' or env.by_id[aid]['group']==group)
            if set(counts)-set(belief_states()):raise ValueError('invalid binary classification state')
            result[group+'_population_n']=sum(counts.values())
            for b in belief_states():result[f'{group}_{b}']=counts[b]
            judged=counts['believe']+counts['reject'];result[group+'_judged_n']=judged
            result[group+'_believe_rate_judged']=counts['believe']/judged if judged else None
        for root,prefix in [('P001','rumor'),('G001','official')]:
            first=[min(v for h in history.values() if h['root_content_id']==root for v in h['ticks']) for history in env.exposure_history.values() if any(h['root_content_id']==root for h in history.values())]
            result[prefix+'_new_reach']=sum(v==t for v in first);result[prefix+'_cumulative_reach']=len(first);result[prefix+'_coverage_rate']=len(first)/len(env.by_id)
            result[prefix+'_readers_this_tick']=sum(any(p['root_content_id']==root for p in a.payload.get('observed_posts',[])) for a in actions)
        scores=[v for v in env.credibility.values() if v is not None]
        result.update(llm_credibility_reported_n=len(scores),llm_credibility_mean=mean(scores) if scores else None,
            posts=len(env.posts),comments=len(env.comments),idle_actions=sum(a.kind=='idle' for a in actions),
            llm_decisions_this_tick=sum(a.kind=='decide' for a in actions),
            reread_presentations=sum(p.get('is_reread',False) for a in actions for p in a.payload.get('observed_posts',[])),
            visible_comment_presentations=sum(len(p['comments']) for a in actions for p in a.payload.get('observed_posts',[])),
            tbu_cohort=len(env.cohort),tbu_completed=len(env.transitions),tbu_engineering=mean(v-env.government_tick for v in env.transitions.values()) if env.transitions else None)
        if env.belief_tracker:
            events=env.belief_tracker.events
            result.update(believe_to_reject_events_this_tick=sum(e['reject_tick']==t for e in events),
                believe_to_reject_events_cumulative=len(events),believe_to_reject_users=len(env.belief_tracker.event_counts))
        return result
    def columns(self):return []
