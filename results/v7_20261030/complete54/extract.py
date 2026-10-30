"""Snapshot committed new-batch outputs. Runtime and source files remain untouched."""
from pathlib import Path
from itertools import product
import json,hashlib,shutil
from datetime import datetime,timezone,timedelta
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parent;ROOT.mkdir(exist_ok=True)
DATA=ROOT/'data';DATA.mkdir(exist_ok=True);RAW=ROOT/'raw';RAW.mkdir(exist_ok=True)
BATCH=Path('D:/Codex/runs/V7_Optimized_20261027_145124/_batch54/20261027-145124')
snapshot=(BATCH/'batch_status.json').read_bytes();state=json.loads(snapshot)
(ROOT/'batch_status_snapshot.json').write_bytes(snapshot)
cases=[];cohorts=[];first=[];initial=[];episodes=[];ticks=[];provenance=[];panels=[]
for tag,item in sorted(state['cases'].items()):
    run=Path(item['run_dir']);prov=json.loads((run/'provenance.json').read_text(encoding='utf-8'));cfg=prov['config']
    complete=item['status']=='completed_live' and item['last_completed_tick']==10
    end=int(item['last_completed_tick'])
    f=run/'trajectory/belief_measurements.csv';raw=f.read_bytes();(RAW/(tag+'.csv')).write_bytes(raw)
    x=pd.read_csv(f,encoding='utf-8-sig');x=x[x.step.le(end)].copy()
    assert len(x)==300*(end+1) and not x.duplicated(['agent_id','step']).any()
    assert x.loc[x.subjective_credibility.notna(),'belief'].eq(np.where(x.loc[x.subjective_credibility.notna(),'subjective_credibility'].gt(50),'believe','reject')).all()
    params=dict(D=cfg['source_trust_gap'],GT=cfg['government_trust_mean'],TG=cfg['government_tick'],TC=cfg['targeting_inside_ratio'])
    meta=dict(case_id=tag,complete=complete,last_tick=end,**params)
    official=x.groupby('agent_id').official_first_seen_tick.min()
    # Post-publication cohort, reproducing the old workbook's clock.
    ids=x.loc[x.step.eq(params['TG']-1)&x.belief.eq('believe'),'agent_id']
    rejs=x.loc[x.agent_id.isin(ids)&x.step.ge(params['TG'])&x.belief.eq('reject')].groupby('agent_id').step.min()
    own=[]
    for aid in ids:
        event=aid in rejs;when=int(rejs[aid]) if event else None;wait=when-params['TG'] if event else end-params['TG']
        rec=dict(**meta,agent_id=aid,event=int(event),reject_tick=when,wait_or_censor=wait,
            restricted_wait3=min(wait,3),followup=end-params['TG'],official_first_tick=official[aid] if pd.notna(official[aid]) else None)
        own.append(rec);cohorts.append(rec)
    # All actual belief episodes, including right-censored episodes.
    ff=[];ii=[];ee=[]
    for aid,z in x.groupby('agent_id',sort=False):
        z=z.sort_values('step');start=None;episode_no=0
        for row in z.itertuples():
            if row.belief=='believe' and start is None:start=int(row.step);episode_no+=1
            elif row.belief=='reject' and start is not None:
                ee.append(dict(**meta,agent_id=aid,group=row.group,episode_no=episode_no,start_tick=start,
                    end_tick=int(row.step),duration=int(row.step)-start,event=1,official_first_tick=official[aid] if pd.notna(official[aid]) else None))
                start=None
        if start is not None:
            ee.append(dict(**meta,agent_id=aid,group=z.iloc[-1]['group'],episode_no=episode_no,start_tick=start,
                end_tick=end,duration=end-start,event=0,official_first_tick=official[aid] if pd.notna(official[aid]) else None))
    for r in ee:
        if r['episode_no']==1:
            ff.append(r)
            if r['start_tick']==1:ii.append(r)
    episodes+=ee;first+=ff;initial+=ii
    # Complete time-step counts from exactly 300 committed states.
    ts=[]
    for step,z in x.groupby('step',sort=True):
        for group in ['all','inside','outside']:
            a=z if group=='all' else z[z.group.eq(group)]
            counts=a.belief.value_counts();score=a.subjective_credibility.dropna()
            ts.append(dict(**meta,tick=int(step),group=group,n=len(a),believe=int(counts.get('believe',0)),
                reject=int(counts.get('reject',0)),unjudged=int(counts.get('unjudged',0)),
                score_mean=float(score.mean()) if len(score) else None,
                rumor_seen=int(a.rumor_seen.sum()),official_seen=int(a.official_seen.sum())))
    ticks+=ts
    allts=pd.DataFrame([t for t in ts if t['group']=='all']);final=x[x.step.eq(end)]
    base=dict(**meta,status=item['status'],run_dir=str(run),xlsx=str(BATCH.parent.parent/item['filename']),
        post_cohort_n=len(own),post_events=sum(r['event'] for r in own),post_censored=sum(1-r['event'] for r in own),
        TBU_post=float(np.mean([r['wait_or_censor'] for r in own if r['event']])) if rejs.size else None,
        RMST_post3=float(np.mean([r['restricted_wait3'] for r in own])) if own and end-params['TG']>=3 else None,
        conversion_post3=float(np.mean([r['event'] and r['wait_or_censor']<=3 for r in own])) if own and end-params['TG']>=3 else None,
        initial_believers=len(ii),initial_events=sum(r['event'] for r in ii),
        RMST_initial6=float(np.mean([min(r['duration'],6) for r in ii])) if ii and end>=7 else None,
        RMST_initial9=float(np.mean([min(r['duration'],9) for r in ii])) if ii and end==10 else None,
        initial_TBU_completed=float(np.mean([r['duration'] for r in ii if r['event']])) if any(r['event'] for r in ii) else None,
        ever_believers=len(ff),first_events=sum(r['event'] for r in ff),first_censored=sum(1-r['event'] for r in ff),
        all_episode_events=sum(r['event'] for r in ee),recurrent_episode_n=sum(r['episode_no']>1 for r in ee),
        believer_rounds=int(allts.loc[allts.tick.ge(1),'believe'].sum()),
        final_believe=int(final.belief.eq('believe').sum()),final_reject=int(final.belief.eq('reject').sum()),
        final_unjudged=int(final.belief.eq('unjudged').sum()),final_score=float(final.subjective_credibility.mean()),
        final_rumor_seen=int(final.rumor_seen.sum()),final_official_seen=int(final.official_seen.sum()))
    cases.append(base)
    provenance.append(dict(case_id=tag,source=str(f),sha256=hashlib.sha256(raw).hexdigest(),bytes=len(raw),complete=complete,last_tick=end))
    x.insert(0,'case_id',tag);x['complete']=complete;panels.append(x)
    print(f'Extracted {len(cases)}/54 {tag}: complete={complete}, initial={len(ii)}, post_cohort={len(own)}',flush=True)

for name,rows in [('cases',cases),('post_cohort',cohorts),('first_belief',first),('initial_believers',initial),('episodes',episodes),('per_tick_counts',ticks)]:
    pd.DataFrame(rows).to_csv(DATA/(name+'.csv'),index=False,encoding='utf-8-sig')
pd.concat(panels,ignore_index=True).to_csv(DATA/'all_committed_user_states.csv',index=False,encoding='utf-8-sig')
C=pd.DataFrame(cases);F=pd.DataFrame(first);I=pd.DataFrame(initial);P=pd.DataFrame(cohorts)
summary=dict(checked_at_beijing=datetime.now(timezone(timedelta(hours=8))).isoformat(),batch_dir=str(BATCH),
    dataset_root=str(BATCH.parent.parent),batch_status=state['status'],complete_cases=int(C.complete.sum()),
    incomplete=C.loc[~C.complete,['case_id','last_tick','status']].to_dict('records'),
    complete_case_metrics=C[C.complete].drop(columns=['run_dir','xlsx']).to_dict('records'),
    complete_cohort_records=int(P.complete.sum()),complete_first_belief_records=int(F.complete.sum()),
    complete_initial_records=int(I.complete.sum()),initial_start_distribution=F[F.complete].start_tick.value_counts().sort_index().to_dict(),
    completed_initial_censored=int(((I.complete)&I.event.eq(0)).sum()),complete_empty_post=C.loc[C.complete&C.post_cohort_n.eq(0),'case_id'].tolist(),
    complete_empty_initial=C.loc[C.complete&C.initial_believers.eq(0),'case_id'].tolist(),
    complete_ever_believer_unique_ids=int(F[F.complete].agent_id.nunique()),source_files=provenance,api_calls=0)
(ROOT/'extraction.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
print('SUMMARY',json.dumps({k:v for k,v in summary.items() if k not in ['source_files','complete_case_metrics']},ensure_ascii=False,indent=2))
