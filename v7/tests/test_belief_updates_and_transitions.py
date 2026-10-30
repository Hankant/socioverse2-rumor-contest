import csv,copy,json
from types import SimpleNamespace
import pytest
import run
from conftest import FakeClient
from test_environment import action,insider
from model import V7Decision,V7Environment,read_json
from belief_dynamics import BeliefTransitionTracker,UPDATE_INSTRUCTIONS,update_context


def state(score=None,exposure=None):
    return dict(current_belief='unjudged'if score is None else'believe'if score>50 else'reject',
                subjective_credibility=score,exposure_summary=exposure or {})


def test_only_actual_believe_to_reject_changes_and_multiple_episodes():
    tracker=BeliefTransitionTracker(4,{'A':{'group':'inside'}},{'A':.7},{'A':.8})
    previous=state()
    for tick,score in enumerate([40,70,65,50,30,80,10],1):
        after=state(score,{'G001':dict(first_seen_tick=4,last_seen_tick=tick,exposure_tick_count=tick-3)}if tick>=4 else{})
        tracker.update('A',tick,previous,after);previous=after
    assert len(tracker.events)==2
    one,two=tracker.events
    assert (one['believe_started_tick'],one['reject_tick'],one['believe_duration_ticks'])==(2,4,2)
    assert one['score_before']==65 and one['score_after']==50 and one['score_change']==-15
    assert one['ticks_from_government']==0 and one['official_seen_at_transition']
    assert not one['official_seen_before'] and one['official_shown_in_transition_tick']
    assert (two['episode_number'],two['believe_started_tick'],two['reject_tick'],two['believe_duration_ticks'])==(2,6,7,1)
    assert tracker.agent_summary('A')['believe_to_reject_events']==2


def test_pre_government_change_is_recorded_without_false_government_causation():
    tracker=BeliefTransitionTracker(7);tracker.update('A',1,state(),state(50.00001))
    event=tracker.update('A',2,state(50.00001),state(50))
    assert event['ticks_from_government']=='' and not event['after_government_intervention']
    assert not event['official_seen_at_transition'] and event['believe_duration_ticks']==1
    assert 'not_proof_of_causation'in event['causal_attribution']


def test_no_events_for_unjudged_reject_or_continuing_belief():
    tracker=BeliefTransitionTracker(2)
    assert tracker.update('A',1,state(),state(50))is None
    assert tracker.update('A',2,state(50),state(20))is None
    assert tracker.update('A',3,state(20),state(90))is None
    assert tracker.update('A',4,state(90),state(60))is None
    assert tracker.events==[] and tracker.starts['A']==3


@pytest.mark.parametrize('bad',[dict(current_belief='believe',subjective_credibility=50),dict(current_belief='reject',subjective_credibility=80),dict(current_belief='unjudged',subjective_credibility=0)])
def test_transition_tracker_refuses_inconsistent_scores(bad):
    with pytest.raises(ValueError):BeliefTransitionTracker(2).update('A',1,state(),bad)


def test_episode_history_and_score_survive_three_tick_memory_expiry(setup):
    cfg,env=setup;aid=insider(env)
    env.apply([action(env,aid,score=70)])
    for tick in [2,3,4,5]:env.advance_to(tick)
    ob=env.observe(aid,5)
    assert ob.local_physical['memory']==[] and ob.local_physical['subjective_credibility']==70
    assert env.agent_state(aid)['believe_episode_start_tick']==1
    a=action(env,aid,score=50);env.apply([a]);env.apply([a])
    assert env.credibility[aid]==50 and len(env.belief_tracker.events)==1
    assert env.belief_tracker.events[0]['believe_duration_ticks']==4


def test_two_followee_reposts_count_as_one_root_read_and_reread_keeps_old_score(setup):
    cfg,env=setup
    outside=next(a for a,r in env.by_id.items()if r['group']=='outside'and a not in env.direct_targets)
    sources=[a for a in env.following[outside]if a in env.by_id and env.by_id[a]['group']=='inside']
    assert len(sources)==2
    env.apply([action(env,a,repost=True,score=65)for a in sources]);env.advance_to(2)
    ob=env.observe(outside,2);context=update_context(ob);root=context['actual_exposure']['P001']
    assert root['read_rounds_including_this_tick']==1 and root['repeated_rounds_including_this_tick']==0
    assert root['visible_followee_reposts']==2 and root['delivery']==['followee_rumor_repost']
    assert not context['government_response_has_been_read']
    env.apply([action(env,outside,score=42)]);env.advance_to(3)
    context=update_context(env.observe(outside,3));root=context['actual_exposure']['P001']
    assert root['read_rounds_including_this_tick']==2 and root['repeated_rounds_including_this_tick']==1
    assert context['rumor_belief_score_before']==42 and not context['automatic_numeric_adjustments']
    env.apply([action(env,outside,score=42)])
    assert env.credibility[outside]==42  # No program-forced increase on repetition.


def test_government_context_only_after_real_exposure_and_score_is_llm_returned(setup):
    cfg,env=setup;aid=next(a for a in env.direct_targets if env.by_id[a]['group']=='inside')
    assert not update_context(env.observe(aid,1))['government_response_has_been_read']
    env.apply([action(env,aid,score=72)]);env.advance_to(2)
    context=update_context(env.observe(aid,2))
    assert context['government_response_has_been_read'] and context['rumor_belief_score_before']==72
    assert context['government_trust']==env.cfg['government_trust'][aid]
    env.apply([action(env,aid,score=73)])
    assert env.credibility[aid]==73  # No forced decrease even with an official post.


@pytest.mark.parametrize('style',['standard','concise_lossless_v1','concise_shared_prefix_v1'])
def test_every_wire_has_update_rules_and_actual_score_and_counts(setup,style):
    from llm_client import prepare_prompt
    from response_contract import wire_prompt
    cfg,env=setup;aid=insider(env);env.apply([action(env,aid,score=68)]);env.advance_to(2);ob=env.observe(aid,2)
    template=(run.SOURCE/'02_Prompt固定提示词.md').read_text(encoding='utf-8').split('```text',1)[1].split('```',1)[0].strip()
    base,*_=prepare_prompt(template,ob,2_000_000,memory_policy='preserve',encoding=cfg['prompt_encoding'])
    wire=wire_prompt(base,ob,1536,style=style)
    assert UPDATE_INSTRUCTIONS in wire and 'rumor_belief_score_before'in wire
    assert 'repeated_rounds_including_this_tick'in wire and '68'in wire
    assert '不机械加减固定分'in wire and '本人越信任政府'in wire


def test_old_environment_bundle_still_replays_without_new_state_fields(setup):
    cfg,env=setup;bundle=copy.deepcopy(env.bundle)
    bundle.provider_args.pop('belief_update_policy');bundle.provider_args.pop('belief_transition_policy')
    legacy=V7Environment(bundle);legacy.reset(cfg['behavior_seed']);legacy.advance_to(1)
    aid=insider(legacy);legacy.apply([action(legacy,aid,score=70)])
    assert legacy.belief_tracker is None and 'believe_episode_start_tick'not in legacy.agent_state(aid)


def test_committed_exports_have_only_changes_and_reexport_is_identical(tmp_path,monkeypatch):
    from transition_report import export_transitions
    for key,sub in [('RESULTS','runs'),('CONFIGS','configs'),('LOGS','audit')]:monkeypatch.setattr(run,key,tmp_path/sub)
    monkeypatch.setattr(V7Decision,'client_factory',FakeClient)
    args=SimpleNamespace(config=None,steps=4,resume=None,concurrency=None,max_requests=None,execution_limit_migration=False)
    folder=run.execute(args,test_mode=True);path=folder/'reports/belief_to_reject_events.csv'
    with path.open(encoding='utf-8-sig',newline='')as f:events=list(csv.DictReader(f))
    assert events and all(float(e['score_before'])>50 and float(e['score_after'])<=50 for e in events)
    assert len({e['event_id']for e in events})==len(events)
    with(folder/'trajectory/belief_measurements.csv').open(encoding='utf-8-sig',newline='')as f:measurements=list(csv.DictReader(f))
    assert sum(r['believe_to_reject_event']=='True'for r in measurements)==len(events)
    monkeypatch.setattr(V7Decision,'client_factory',lambda*a,**k:pytest.fail('export must never construct an API client'))
    summary=export_transitions(folder,tmp_path/'reexport')
    assert summary['events']==len(events) and summary['api_requests']==0
    assert (tmp_path/'reexport/belief_to_reject_events.csv').read_bytes()==path.read_bytes()
    from verify_run import verify
    assert verify(folder)['replay']=='exact'
