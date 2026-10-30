"""Export only real believe-to-reject changes from committed states, no API."""
from pathlib import Path
import argparse,csv,json
from belief_dynamics import BeliefTransitionTracker,EVENT_FIELDS
from csv_io import atomic_csv,iter_committed_states
from model import read_json,dump


def tracker_for_run(folder,roster=None):
    folder=Path(folder);prov=read_json(folder/'provenance.json');frozen=Path(prov['config_dir'])
    if roster is None:
        roster=[json.loads(line)['attributes'] for line in (folder/'population/roster.jsonl').read_text(encoding='utf-8').splitlines()]
    source=read_json(frozen/'source_trust.json');government=read_json(frozen/'government_trust.json')
    return BeliefTransitionTracker(prov['config']['government_tick'],{r['agent_id']:r for r in roster},source,government)


def write_transition_events(output,events):
    with atomic_csv(output)as stream:
        writer=csv.DictWriter(stream,fieldnames=EVENT_FIELDS);writer.writeheader();writer.writerows(events)
    return Path(output)


def write_tracker_report(tracker,target,last_tick):
    target=Path(target);path=write_transition_events(target/'belief_to_reject_events.csv',tracker.events)
    summary=dict(last_completed_tick=last_tick,events=len(tracker.events),users_with_change=len(tracker.event_counts),
        policy='only_score_gt50_to_score_le50; all_episodes; no_nonchangers',time_unit='abstract_simulation_ticks',api_requests=0,
        before_government=sum(not r['after_government_intervention'] for r in tracker.events),
        without_official_exposure=sum(not r['official_seen_at_transition'] for r in tracker.events),file=str(path))
    dump(target/'belief_to_reject_summary.json',summary)
    return summary


def export_transitions(run_dir,output_dir=None):
    folder=Path(run_dir);target=Path(output_dir)if output_dir else folder/'reports'
    tracker=tracker_for_run(folder);previous={};counts={};last={}
    for row in iter_committed_states(folder):
        aid=row['agent_id'];tick=int(row['step']);state=json.loads(row['state'])
        if tick!=last.get(aid,-1)+1:raise ValueError('transition export requires contiguous committed ticks starting at zero')
        tracker.update(aid,tick,previous.get(aid,dict(current_belief='unjudged',subjective_credibility=None)),state)
        previous[aid]=state;last[aid]=tick;counts[tick]=counts.get(tick,0)+1
    if len(last)!=300 or len(set(last.values()))!=1 or any(n!=300 for n in counts.values()):raise ValueError('incomplete committed population for transition export')
    return write_tracker_report(tracker,target,max(counts))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description='Export observed believe-to-reject events; never calls an LLM')
    parser.add_argument('--run-dir',required=True);parser.add_argument('--output-dir');args=parser.parse_args()
    print(json.dumps(export_transitions(args.run_dir,args.output_dir),ensure_ascii=False,indent=2))
