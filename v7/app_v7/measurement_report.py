"""Export full committed V7 states; never count partial request caches as results."""
import csv,json
from collections import Counter,defaultdict
from pathlib import Path
from model import COMPONENT_KEYS,BINARY_SCORE_POLICY,score_to_belief,dump
from csv_io import atomic_csv,iter_committed_states


def write_measurements(run_dir,roster,belief_policy=BINARY_SCORE_POLICY):
    if belief_policy!=BINARY_SCORE_POLICY:raise ValueError('V7 requires binary scoring')
    from transition_report import tracker_for_run,write_tracker_report
    tracker=tracker_for_run(run_dir,roster);previous={}
    folder=Path(run_dir)/'trajectory';people={r['agent_id']:r for r in roster};records=[];conditions=[]
    for row in iter_committed_states(run_dir):
        person=people[row['agent_id']];state=json.loads(row['state']);score=state.get('subjective_credibility');step=int(row['step'])
        if score is not None and state['current_belief']!=score_to_belief(score):raise ValueError('committed score/classification mismatch')
        if state['current_belief'] not in ('unjudged','believe','reject'):raise ValueError('invalid classification')
        before=previous.get(row['agent_id'],dict(current_belief='unjudged',subjective_credibility=None))
        event=tracker.update(row['agent_id'],step,before,state)
        record={k:person[k] for k in ('agent_id','group','synthetic_age','synthetic_region','synthetic_occupation','synthetic_mbti_type')}
        record.update(step=step,belief=state['current_belief'],subjective_credibility='' if score is None else score,
            measurement_status='not_yet_reported' if score is None else 'self_reported_uncalibrated',classification_rule='score>50:believe;score<=50:reject')
        old_score=before.get('subjective_credibility')
        record.update(previous_subjective_credibility='' if old_score is None else old_score,
            score_change=score-old_score if score is not None and old_score is not None else '',
            believe_to_reject_event=event is not None,**tracker.agent_summary(row['agent_id']))
        record.update({k:(state.get('component_credibility') or {}).get(k,'') for k in COMPONENT_KEYS})
        for root,prefix in [('P001','rumor'),('G001','official')]:
            exposure=state.get('exposure_summary',{}).get(root)
            record[prefix+'_seen']=bool(exposure);record[prefix+'_first_seen_tick']=exposure.get('first_seen_tick','') if exposure else ''
        records.append(record)
        previous[row['agent_id']]=state
        if state.get('condition_application') and state.get('last_updated_tick')==step:
            from decision_conditions import CONDITION_LABELS
            for key,label in CONDITION_LABELS.items():
                item=state['condition_application'][key]
                conditions.append(dict(agent_id=record['agent_id'],step=step,condition=key,condition_label=label,
                    affects=';'.join(item['affects']),application_note=item['note'],condition_context_ref=state['condition_context_ref'],
                    subjective_credibility=score,belief=state['current_belief'],audit_scope='self_report_not_causal_proof'))
    for path,rows in [(folder/'belief_measurements.csv',records),(folder/'condition_applications.csv',conditions)]:
        if rows:
            with atomic_csv(path) as stream:
                writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    report=Path(run_dir)/'reports';report.mkdir(exist_ok=True);summary=[]
    by_tick=defaultdict(list)
    for row in records:by_tick[row['step']].append(row)
    for tick,rows in sorted(by_tick.items()):
        if len(rows)!=300:raise ValueError('incomplete committed V7 tick')
        for group in ('all','inside','outside'):
            subset=[r for r in rows if group=='all' or r['group']==group];counts=Counter(r['belief'] for r in subset);n=counts['believe']+counts['reject']
            summary.append(dict(step=tick,group=group,population_n=len(subset),judged_n=n,believe=counts['believe'],reject=counts['reject'],
                unjudged_n=counts['unjudged'],believe_rate_judged=counts['believe']/n if n else '',
                rumor_seen_n=sum(r['rumor_seen'] for r in subset),official_seen_n=sum(r['official_seen'] for r in subset)))
    if summary:
        for name,rows in [('per_tick_results.csv',summary),('binary_results.csv',[r for r in summary if r['step']==max(by_tick)])]:
            with atomic_csv(report/name) as stream:
                writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
        dump(report/'binary_results.json',dict(policy=BINARY_SCORE_POLICY,denominator='believe+reject; unjudged excluded',results=[r for r in summary if r['step']==max(by_tick)]))
        write_tracker_report(tracker,report,max(by_tick))
    return folder/'belief_measurements.csv'
