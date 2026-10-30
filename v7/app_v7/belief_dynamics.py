"""Autonomous LLM updates and observed believe-to-reject episodes only.

No numeric score increment/decrement or expected belief proportion is imposed.
Episode durations are abstract simulation ticks, not real-world clock time.
"""
import copy
import math

UPDATE_POLICY='autonomous_belief_reinforcement_v1'
TRANSITION_POLICY='believe_to_reject_episodes_v1'
UPDATE_INSTRUCTIONS='''【持续信念与重复接触更新】
subjective_credibility就是本人对当前核心说法的持续信念值（0—100），不同于0—1来源信任。每轮以上一次已报告分数为起点，结合本轮接触更新，不每轮重置为50，也不把初始来源信任直接乘100。尚未接触时为null/未判断，不虚设初始相信分。
实际再看到同一说法（直接读博主或关注者转发）可能增加熟悉感、强化已有相信；来源信任较高、重复敏感度较高且较少核验时，这种倾向通常更强，但逐次增量可减弱。先看本人的真实重复次数，再判断本轮是否强化、维持或被相反内容抵消；不能只在摘要写“已考虑重复”。
同一轮同一主帖只算一次接触，多个转发不冒充多份独立证据。区分赞同原说法的附言、求证、质疑和反驳；别人转发或出现更多评论，不自动等于更多人支持，更不等于主张被证实。
只在实际读过官方回应后，政府信任才影响对回应的接受。其余已见条件相同时，本人越信任政府，通常越重视其核查与否认，使原核心说法的信念分更向下调整；低政府信任减弱这种作用。官方帖重复出现也可巩固纠正，但不凭空增加证据强度。
同时读到原帖和官方帖时，综合旧分数、双方来源信任、实际接触次数、正文/附言/评论和个人条件。允许互相抵消、维持或反向更新，不机械加减固定分，不强迫每轮升降，不迎合研究者预期。最后如实返回新的subjective_credibility，并在信任/重复/历史三项的短摘要中交代实际起点或次数的作用。>50相信，≤50不相信，50归不相信。'''


def update_context(ob):
    """Only material actually exposed, including this tick; compact wire safe."""
    from model import exposure_summary
    p=ob.local_physical
    if p.get('belief_update_policy')!=UPDATE_POLICY:return None
    feed=ob.local_information['posts']
    previous=exposure_summary(p.get('exposure_history',{}),[],ob.step)
    current=exposure_summary(p.get('exposure_history',{}),feed,ob.step)
    roots={}
    for root in ('P001','G001'):
        views=[post for post in feed if post['root_content_id']==root]
        prior=previous.get(root,{}).get('exposure_tick_count',0)
        total=current.get(root,{}).get('exposure_tick_count',0)
        roots[root]=dict(prior_read_rounds=prior,read_this_tick=bool(views),read_rounds_including_this_tick=total,
            repeated_rounds_including_this_tick=max(0,total-1),
            delivery=[post.get('delivery','unknown') for post in views],
            visible_followee_reposts=len({r['content_id'] for post in views for r in post.get('relay_context',[])}))
    return dict(policy=UPDATE_POLICY,rumor_belief_score_before=p.get('subjective_credibility'),
        score_to_return='subjective_credibility',classification='>50=believe; <=50=reject',
        source_trust=p['source_trust'],government_trust=p['government_trust'],
        government_response_has_been_read=roots['G001']['read_rounds_including_this_tick']>0,
        actual_exposure=roots,root_views_counting='once_per_root_per_tick; relays_are_not_independent_confirmation',
        automatic_numeric_adjustments=False)


EVENT_FIELDS=('event_id','agent_id','group','episode_number','believe_started_tick','reject_tick','believe_duration_ticks',
    'score_before','score_after','score_change','government_tick','ticks_from_government','after_government_intervention',
    'official_seen_before','official_seen_at_transition','official_first_seen_tick','official_shown_in_transition_tick',
    'rumor_read_rounds','official_read_rounds','source_trust','government_trust','causal_attribution')


class BeliefTransitionTracker:
    """Idempotence is provided by the committed-action or committed-state caller."""
    def __init__(self,government_tick,people=None,source_trust=None,government_trust=None):
        self.government_tick=government_tick;self.people=people or {};self.source=source_trust or {};self.government=government_trust or {}
        self.starts={};self.episodes={};self.events=[];self.event_counts={}

    def update(self,aid,tick,before,after):
        old=before['current_belief'];new=after['current_belief']
        for state in (before,after):
            score=state.get('subjective_credibility')
            if state['current_belief']=='unjudged':
                if score is not None:raise ValueError('unjudged transition state has a score')
            elif (type(score)not in(int,float)or not math.isfinite(score)or not 0<=score<=100
                  or ('believe'if score>50 else'reject')!=state['current_belief']):
                raise ValueError('transition state score/classification mismatch')
        if old!='believe' and new=='believe':
            self.starts[aid]=tick;self.episodes[aid]=self.episodes.get(aid,0)+1
        elif old=='believe' and new=='reject':
            if aid not in self.starts:raise ValueError('missing committed start of belief episode')
            start=self.starts.pop(aid);number=self.episodes[aid]
            old_g=before.get('exposure_summary',{}).get('G001',{});new_g=after.get('exposure_summary',{}).get('G001',{})
            rumor=after.get('exposure_summary',{}).get('P001',{})
            event=dict(event_id=f'{aid}-B2R-{number:03d}',agent_id=aid,group=self.people.get(aid,{}).get('group',after.get('group','')),
                episode_number=number,believe_started_tick=start,reject_tick=tick,believe_duration_ticks=tick-start,
                score_before=before['subjective_credibility'],score_after=after['subjective_credibility'],
                score_change=after['subjective_credibility']-before['subjective_credibility'],government_tick=self.government_tick,
                ticks_from_government=tick-self.government_tick if tick>=self.government_tick else '',
                after_government_intervention=tick>=self.government_tick,official_seen_before=bool(old_g),official_seen_at_transition=bool(new_g),
                official_first_seen_tick=new_g.get('first_seen_tick',''),official_shown_in_transition_tick=new_g.get('last_seen_tick')==tick,
                rumor_read_rounds=rumor.get('exposure_tick_count',0),official_read_rounds=new_g.get('exposure_tick_count',0),
                source_trust=self.source.get(aid,''),government_trust=self.government.get(aid,''),
                causal_attribution='observed_change_only; official_exposure_is_not_proof_of_causation')
            self.events.append(event)
            self.event_counts[aid]=self.event_counts.get(aid,0)+1
            return copy.deepcopy(event)
        return None

    def agent_summary(self,aid):
        return dict(believe_episode_start_tick=self.starts.get(aid),belief_episodes_started=self.episodes.get(aid,0),
                    believe_to_reject_events=self.event_counts.get(aid,0))
