from pathlib import Path
import json,hashlib
import pandas as pd
ROOT=Path(__file__).resolve().parent;DATA=ROOT/'data';DATA.mkdir(exist_ok=True)
BASE=ROOT.parent/'dual_tbu';A=json.loads((BASE/'analysis.json').read_text(encoding='utf-8'))
for s in A['source_files']:assert hashlib.sha256((ROOT.parent/'complete54/raw'/(s['case_id']+'.csv')).read_bytes()).hexdigest()==s['sha256']
T={name:[r for r in rows if r.get('outcome')=='TBU_FB'] for name,rows in A['tables'].items()}
T={k:v for k,v in T.items() if v}
cases=pd.read_csv(BASE/'data/scenarios.csv')
cases=cases[['case_id','RT','TC','GC','DGC','ever_believers','matched_n','censored_n','pre_release_resolved_n','TBU_FB','mean_first_belief_tick','final_believe','final_reject','final_unjudged']]
people=pd.read_csv(BASE/'data/users.csv');people=people[['case_id','agent_id','group','RT','TC','GC','DGC','first_belief_tick','reject_tick','state','TBU_FB','first_belief_followup','official_first_seen_tick']]
assert len(cases)==54 and len(people)==980 and people.TBU_FB.notna().sum()==757
assert abs(cases.TBU_FB.mean()-4.55684896011148)<1e-12
cases.to_csv(DATA/'FB_scenarios.csv',index=False,encoding='utf-8-sig');people.to_csv(DATA/'FB_users.csv',index=False,encoding='utf-8-sig')
for name,rows in T.items():pd.DataFrame(rows).to_csv(DATA/(name+'.csv'),index=False,encoding='utf-8-sig')
out=dict(endpoint='First belief to first qualifying belief-to-rejection transition at or after government publication',
    rule='TBU_i = r_i - b_i, r_i >= RT; scenario means equally weighted',
    completed_scenarios=54,scenario_mean=float(cases.TBU_FB.mean()),event_weighted_mean=float(people.TBU_FB.mean()),
    observed_updates=757,same_release_round=282,strictly_after_release=475,right_censored_first_episodes=222,resolved_before_release=1,
    multiplicity='Preserve previously tested families: 8 omnibus, 20 pairs, 8 numeric main slopes, 6 interactions. Only FB is displayed.',
    formulas=A['formulas'],centers=A['centers'],levels=A['levels'],tables=T,source_files=A['source_files'],api_calls=0)
(ROOT/'analysis_FB.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
print('FB-only results prepared; 54 scenarios, 757 observed updates; mean=',out['scenario_mean'])
