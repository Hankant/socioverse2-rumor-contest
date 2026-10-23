"""Export committed panel states, including nulls; no partial-tick cache results."""
import csv
import json
from pathlib import Path
from model import COMPONENT_KEYS, BINARY_SCORE_POLICY, score_to_belief
from csv_io import atomic_csv,iter_committed_states

def write_measurements(run_dir,roster,belief_policy="legacy"):
    folder=Path(run_dir)/'trajectory';people={r['agent_id']:r for r in roster}
    fields=['agent_id','step','decision_mode','group','synthetic_age','synthetic_region','synthetic_occupation','synthetic_mbti_type',
            'belief','subjective_credibility',*COMPONENT_KEYS,'measurement_status','classification_rule',
            'rumor_seen','rumor_first_seen_tick','official_seen','official_first_seen_tick']
    records=[]
    condition_records=[]
    for r in iter_committed_states(run_dir):
        p=people[r['agent_id']];s=json.loads(r['state']);score=s.get('subjective_credibility');components=s.get('component_credibility') or {}
        if belief_policy == BINARY_SCORE_POLICY and p['decision_mode']=='llm' and score is not None:
            if s['current_belief']!=score_to_belief(score):raise ValueError('score/classification mismatch in committed state')
        row={k:p.get(k,'') for k in fields if k not in ['step','belief','subjective_credibility','measurement_status','classification_rule',*COMPONENT_KEYS]}
        row.update(step=int(r['step']),belief=s['current_belief'],subjective_credibility='' if score is None else score,
                   measurement_status='not_applicable_rule' if p['decision_mode']=='rule' else ('not_yet_reported' if score is None else 'self_reported_uncalibrated'))
        row['classification_rule']='rule_probability_model' if p['decision_mode']=='rule' else ('score>50:believe;score<=50:reject' if belief_policy==BINARY_SCORE_POLICY else 'model_self_label')
        row.update({k:components.get(k,'') for k in COMPONENT_KEYS});records.append(row)
        exposure=s.get('exposure_summary',{})
        for root,prefix in [('P001','rumor'),('G001','official')]:
            row[prefix+'_seen']=root in exposure
            row[prefix+'_first_seen_tick']=exposure.get(root,{}).get('first_seen_tick','')
        if (p['decision_mode']=='llm' and s.get('condition_application') is not None
                and s.get('last_updated_tick')==int(r['step'])):
            from decision_conditions import CONDITION_LABELS
            for key,label in CONDITION_LABELS.items():
                item=s['condition_application'][key]
                condition_records.append(dict(agent_id=r['agent_id'],step=int(r['step']),condition=key,
                    condition_label=label,affects=';'.join(item['affects']),application_note=item['note'],
                    condition_context_ref=s['condition_context_ref'],subjective_credibility=score,
                    belief=s['current_belief'],audit_scope='self_reported_application_not_causal_proof'))
    path=folder/'belief_measurements.csv'
    with atomic_csv(path) as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(records)
    if belief_policy==BINARY_SCORE_POLICY:
        write_binary_results(run_dir,records)
    if condition_records:
        with atomic_csv(folder/'condition_applications.csv') as f:
            w=csv.DictWriter(f,fieldnames=list(condition_records[0]));w.writeheader();w.writerows(condition_records)
    return path


def write_binary_results(run_dir,records):
    folder=Path(run_dir)/'reports';folder.mkdir(exist_ok=True)
    last=max(r['step'] for r in records);final=[r for r in records if r['step']==last]
    summary=[]
    for mode in ['all','llm','rule']:
        rows=[r for r in final if mode=='all' or r['decision_mode']==mode]
        if any(r['belief'] not in ['believe','reject','unjudged'] for r in rows):raise ValueError('non-binary classified state in binary results')
        yes=sum(r['belief']=='believe' for r in rows);no=sum(r['belief']=='reject' for r in rows);n=yes+no
        summary.append(dict(mode=mode,step=last,population_n=len(rows),judged_n=n,believe=yes,reject=no,
                            believe_rate_judged=yes/n if n else None,unjudged_n=len(rows)-n))
    result={'policy':BINARY_SCORE_POLICY,'score_field':'subjective_credibility','believe_rule':'>50','reject_rule':'<=50',
            'denominator':'believe+reject; unjudged excluded','note':'Last complete tick only; consult status.json for completion/paused status.', 'results':summary}
    from model import dump
    dump(folder/'binary_results.json',result)
    with atomic_csv(folder/'binary_results.csv') as f:
        w=csv.DictWriter(f,fieldnames=list(summary[0]));w.writeheader();w.writerows(summary)
