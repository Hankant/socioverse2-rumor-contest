"""Validate a completed V6 run without making requests or changing results."""
import argparse
import json
from pathlib import Path
from model import digest, belief_states, BINARY_SCORE_POLICY, score_to_belief, FULL_THREAD_POLICIES, NETWORK_FEED_POLICIES
from comment_policy import LATEST_FEED_POLICY,PARTICIPATION_POLICY,recent_comments


def verify(path):
    path = Path(path)
    state = json.loads((path / "status.json").read_text(encoding="utf-8"))
    steps = json.loads((path / "simulation/simulation.json").read_text(encoding="utf-8"))["n_steps"]
    assert state["last_completed_tick"] == steps
    assert state["status"] in ("completed_offline", "completed_live")
    provenance=json.loads((path/'provenance.json').read_text(encoding='utf-8'))
    config=provenance['config']
    shared=config.get('feed_policy') in FULL_THREAD_POLICIES
    network=config.get('feed_policy') in NETWORK_FEED_POLICIES
    latest=config.get('feed_policy')==LATEST_FEED_POLICY
    replay=None
    if network:
        from socioverse.schemas import EnvironmentBundle, Action
        from model import V4Environment
        replay=V4Environment(EnvironmentBundle.model_validate_json((path/'environment/environment.json').read_text(encoding='utf-8')))
        replay.reset(config['behavior_seed'])
    thread_checks=[]
    known_comments={'P001':[],'G001':[]}
    if shared:
        from model import load_rows
        llm_ids={r['agent_id'] for r in load_rows(Path(provenance['config_dir'])/'01_Agent基础信息表.csv') if r['decision_mode']=='llm'}
    for tick in range(1, steps+1):
        data = json.loads((path / "checkpoints" / f"tick-{tick:03d}.json").read_text(encoding="utf-8"))
        actions = data["actions"]
        assert digest(actions) == data["sha256"]
        assert len(actions) == 582
        assert {a["agent_id"] for a in actions} == {f"A{i:04d}" for i in range(1, 583)}
        assert all(a["step"] == tick for a in actions)
        if network:
            replay.advance_to(tick)
            for a in actions:
                if a['action_payload'].get('decision_status')=='technical_dropout':
                    continue
                expected=replay.observe(a['agent_id'],tick).local_information['posts']
                assert a['action_payload'].get('observed_posts',[])==expected, 'network exposure or full discussion mismatch'
        if shared:
            rumor_readers=official_readers=covered=0
            for a in actions:
                payload=a['action_payload']
                posts=payload.get('observed_posts',[])
                if not posts:continue
                rumor_readers+=any(p['root_content_id']=='P001' for p in posts)
                official_readers+=any(p['root_content_id']=='G001' for p in posts)
                rumor_count=sum(p['root_content_id']=='P001' for p in posts)
                assert rumor_count<=1
                if not network:assert rumor_count==1
                assert len({p['root_content_id'] for p in posts})==len(posts)
                assert {p['content_id'] for p in posts}<={'P001','G001'}
                assert all(c['published_tick']<tick for p in posts for c in p['comments'])
                for p in posts:
                    expected_comments=known_comments[p['root_content_id']]
                    if latest:expected_comments=recent_comments(expected_comments,config['comment_window_limit'],config['behavior_seed'])
                    assert p['comments']==expected_comments
                if a['agent_id'] in llm_ids:
                    from decision_conditions import CONDITION_LABELS
                    usage=payload['answer']['condition_application']
                    assert set(usage)==set(CONDITION_LABELS)
                    if config.get('comment_participation_policy')==PARTICIPATION_POLICY:
                        assert 'comment' in usage['mbti_preferences']['affects']
                    covered+=1
            thread_checks.append(dict(tick=tick,rumor_readers=rumor_readers,official_readers=official_readers,
                all_visible_rumor_comments=min(config['comment_window_limit'],len(known_comments['P001'])) if latest else len(known_comments['P001']),
                all_visible_official_comments=min(config['comment_window_limit'],len(known_comments['G001'])) if latest else len(known_comments['G001']),
                archived_rumor_comments=len(known_comments['P001']),archived_official_comments=len(known_comments['G001']),
                llm_decisions_with_all_11_conditions=covered))
            # Reconstruct the complete public discussion from committed actions,
            # so the next tick is checked against all comments, not just a cap.
            for a in actions:
                comment=a['action_payload'].get('answer',{}).get('comment',{})
                if comment.get('enabled'):
                    target=comment['target_content_id']
                    assert target in known_comments
                    known_comments[target].append(dict(comment_id=f"C{tick:02d}-{a['agent_id']}",author_id=a['agent_id'],
                        published_tick=tick,target_content_id=target,text=comment['text']))
            for comments in known_comments.values():comments.sort(key=lambda c:(c['published_tick'],c['comment_id']))
        if network:
            replay.apply([Action(agent_id=a['agent_id'],step=tick,kind=a['action_kind'],payload=a['action_payload'],source='replay') for a in actions])
            thread_checks[-1]['rumor_cumulative_reach']=sum('P001' in s for s in replay.seen.values())
    rows = json.loads((path / "trajectory/metrics_history.json").read_text(encoding="utf-8"))["rows"]
    policy=config.get('belief_measurement_policy','legacy')
    labels=belief_states(policy)
    assert [r["step"] for r in rows] == list(range(steps+1))
    for r in rows:
        assert sum(r[f"all_{s}"] for s in labels) == 582
        if policy==BINARY_SCORE_POLICY:assert 'all_uncertain' not in r
    if policy==BINARY_SCORE_POLICY:
        import csv
        with (path/'trajectory/belief_measurements.csv').open(encoding='utf-8-sig') as f:
            for row in csv.DictReader(f):
                assert row['belief'] in labels
                if row['decision_mode']=='llm' and row['subjective_credibility']!='':
                    assert row['belief']==score_to_belief(float(row['subjective_credibility']))
    result = dict(status=state["status"], ticks=steps, agents=582,
                  reread_presentations=sum(r.get("reread_presentations", 0) for r in rows),
                  comment_presentations=sum(r.get("visible_comment_presentations", 0) for r in rows))
    if shared:result['shared_thread_checks']=thread_checks
    if network:result['network_exposure_replay_verified']=True
    print(json.dumps(result))
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("run_dir")
    verify(parser.parse_args().run_dir)
