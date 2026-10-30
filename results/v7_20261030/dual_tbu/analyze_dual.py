from pathlib import Path
from itertools import product, combinations
import sys,json,hashlib
ROOT=Path(__file__).resolve().parent
PREV=ROOT.parent/'complete54'
import numpy as np,pandas as pd,patsy,statsmodels.api as sm
from scipy import stats
from statsmodels.stats.multitest import multipletests
DATA=ROOT/'data';DATA.mkdir(parents=True,exist_ok=True)
old_extract=json.loads((PREV/'extraction.json').read_text(encoding='utf-8'))
for source in old_extract['source_files']:
    assert hashlib.sha256((PREV/'raw'/(source['case_id']+'.csv')).read_bytes()).hexdigest()==source['sha256']
panel=pd.read_csv(PREV/'data/all_committed_user_states.csv')
assert len(panel)==54*300*11 and not panel.duplicated(['case_id','agent_id','step']).any()
cases=pd.read_csv(PREV/'data/cases.csv').rename(columns={'D':'DGC','TG':'RT','GT':'GC'})
episodes=pd.read_csv(PREV/'data/episodes.csv').rename(columns={'D':'DGC','TG':'RT','GT':'GC'})
assert cases.complete.all() and cases.last_tick.eq(10).all()
# Independently reconstruct first belief and every observed believe-to-reject transition.
panel=panel.sort_values(['case_id','agent_id','step'])
panel['prior_belief']=panel.groupby(['case_id','agent_id']).belief.shift()
reconstructed=panel[panel.prior_belief.eq('believe')&panel.belief.eq('reject')][['case_id','agent_id','step']]
actual=episodes[episodes.event.eq(1)]
assert len(reconstructed)==len(actual)==758
assert set(map(tuple,reconstructed.to_numpy()))==set(map(tuple,actual[['case_id','agent_id','end_tick']].to_numpy()))
firsts=panel[panel.belief.eq('believe')].groupby(['case_id','agent_id']).step.min()
records=[]
for e in episodes[episodes.episode_no.eq(1)].itertuples():
    b=int(firsts[e.case_id,e.agent_id]);assert b==e.start_tick
    all_e=actual[actual.case_id.eq(e.case_id)&actual.agent_id.eq(e.agent_id)]
    elig=all_e[all_e.end_tick.ge(e.RT)]
    end=int(elig.end_tick.min()) if len(elig) else None
    before=bool(len(all_e[all_e.end_tick.lt(e.RT)]))
    state='observed_post_release' if end is not None else ('resolved_before_release' if before else 'right_censored')
    p=panel[(panel.case_id==e.case_id)&(panel.agent_id==e.agent_id)].iloc[0]
    records.append(dict(case_id=e.case_id,agent_id=e.agent_id,group=e.group,DGC=e.DGC,RT=e.RT,TC=e.TC,GC=e.GC,
      first_belief_tick=b,reject_tick=end,state=state,post_event=int(end is not None),strict_event=int(end is not None and end>e.RT),
      TBU_POST=(end-e.RT) if end is not None else None,TBU_FB=(end-b) if end is not None else None,
      first_belief_followup=10-b,censor_tick=10 if state=='right_censored' else None,
      official_first_seen_tick=None if pd.isna(e.official_first_tick) else int(e.official_first_tick),
      mbti=p.synthetic_mbti_type,age=int(p.synthetic_age),region=p.synthetic_region,occupation=p.synthetic_occupation))
people=pd.DataFrame(records);ev=people[people.post_event.eq(1)].copy();strict=people[people.strict_event.eq(1)].copy()
assert len(people)==980 and len(ev)==757 and len(strict)==475
assert np.allclose(ev.TBU_FB-ev.TBU_POST,ev.RT-ev.first_belief_tick)
for name,df in [('users',people),('matched_events',ev),('strict_events',strict)]:df.to_csv(DATA/(name+'.csv'),index=False,encoding='utf-8-sig')
for col,values in {'TBU_POST':ev.groupby('case_id').TBU_POST.mean(),'TBU_FB':ev.groupby('case_id').TBU_FB.mean(),
                   'STRICT_POST':strict.groupby('case_id').TBU_POST.mean(),'STRICT_FB':strict.groupby('case_id').TBU_FB.mean(),
                   'matched_n':ev.groupby('case_id').size(),'strict_n':strict.groupby('case_id').size(),
                   'censored_n':people[people.state.eq('right_censored')].groupby('case_id').size(),
                   'pre_release_resolved_n':people[people.state.eq('resolved_before_release')].groupby('case_id').size(),
                   'mean_first_belief_tick':ev.groupby('case_id').first_belief_tick.mean()}.items():cases[col]=cases.case_id.map(values)
for col in ['matched_n','strict_n','censored_n','pre_release_resolved_n']:cases[col]=cases[col].fillna(0).astype(int)
cases['clock_gap']=cases.TBU_FB-cases.TBU_POST
cases['RBD9']=cases.RMST_initial9
cases['PRUD3']=cases.RMST_post3
assert np.allclose(cases.clock_gap,cases.RT-cases.mean_first_belief_tick)
assert cases[['TBU_POST','TBU_FB']].notna().all().all()
cases.to_csv(DATA/'scenarios.csv',index=False,encoding='utf-8-sig')
LEV={'RT':[2,4,7],'TC':[.2,.8],'GC':[.25,.5,.75],'DGC':[0,.2,.4]}
grid=pd.DataFrame(product(*(LEV[k] for k in LEV)),columns=list(LEV));centers={'RT':13/3,'TC':.5,'GC':.5,'DGC':.2}
for f,v in centers.items():cases[f+'_c']=cases[f]-v;grid[f+'_c']=grid[f]-v
FORMS={'M1':'RT_c+TC_c+GC_c','M2':'RT_c+TC_c+GC_c+DGC_c','M3':'RT_c+TC_c+GC_c+DGC_c+DGC_c:(RT_c+TC_c+GC_c)'}
T={k:[] for k in ['levels','means','pairs','coefficients','fits','blocks','interactions','conditional','did','categorical_interactions','clock_difference','sensitivity','descriptives']}
models={}
def adjust(rows,key='p_holm'):
    if rows:
        for r,q in zip(rows,multipletests([r['p'] for r in rows],method='holm')[1]):r[key]=float(q)
def fit(df,y,formula):
    X=patsy.dmatrix(formula,df,return_type='dataframe');o=sm.OLS(df[y],X).fit();r=o.get_robustcov_results(cov_type='HC3',use_t=True)
    assert np.linalg.matrix_rank(X)==X.shape[1]
    G=np.asarray(patsy.build_design_matrices([X.design_info],grid)[0])
    return dict(o=o,r=r,X=X,G=G,names=list(X.columns),n=len(df),df=int(o.df_resid))
def ct(m,L):
    z=m['r'].t_test(L);ci=z.conf_int()[0]
    return dict(estimate=float(np.asarray(z.effect).item()),se=float(np.asarray(z.sd).item()),t=float(np.asarray(z.tvalue).item()),df=m['df'],
                ci_low=float(ci[0]),ci_high=float(ci[1]),p=float(np.asarray(z.pvalue).item()))
def ft(m,R):
    z=m['r'].f_test(R);return dict(F=float(z.fvalue),df_num=float(z.df_num),df_den=float(z.df_denom),p=float(z.pvalue))
cat='C(RT,Sum)+C(TC,Sum)+C(GC,Sum)+C(DGC,Sum)'
OUT=['TBU_POST','TBU_FB','STRICT_POST','STRICT_FB','RBD9','PRUD3']
for outcome in OUT:
    df=cases[cases[outcome].notna()].copy()
    for name,formula in FORMS.items():
        m=fit(df,outcome,formula);models[outcome,name]=m;o=m['o']
        T['fits'].append(dict(outcome=outcome,model=name,n=len(df),parameters=len(m['names']),df=m['df'],R2=float(o.rsquared),adj_R2=float(o.rsquared_adj),RMSE=float(np.sqrt(o.mse_resid)),**ft(m,np.eye(len(m['names']))[1:])))
        rr=[]
        for j,term in enumerate(m['names']):
            v=dict(outcome=outcome,model=name,term=term,n=len(df),**ct(m,np.eye(len(m['names']))[j]));T['coefficients'].append(v)
            if name=='M3' and ':' in term:
                f=next(f for f in ['RT','TC','GC'] if f+'_c' in term)
                T['interactions'].append(dict(outcome=outcome,factor=f,**ct(m,np.eye(len(m['names']))[j])))
            if name=='M3' and term in ['RT_c','TC_c','GC_c','DGC_c']:rr.append(v)
        adjust(rr)
        if name in ['M2','M3']:
            idx=[m['names'].index('DGC_c')] if name=='M2' else [j for j,n in enumerate(m['names']) if ':' in n]
            prev=models[outcome,'M1' if name=='M2' else 'M2']
            T['blocks'].append(dict(outcome=outcome,block=name,delta_R2=float(o.rsquared-prev['o'].rsquared),**ft(m,np.eye(len(m['names']))[idx])))
        if name=='M3':
            for f,increment in [('RT',1),('TC',.6),('GC',.25)]:
                vi=np.eye(len(m['names']))[m['names'].index(f+'_c')]
                inter=next(j for j,nm in enumerate(m['names']) if ':' in nm and f+'_c' in nm.split(':'))
                wi=np.eye(len(m['names']))[inter]
                for d in [0,.2,.4]:T['conditional'].append(dict(outcome=outcome,factor=f,DGC=d,increment=increment,**ct(m,increment*(vi+(d-.2)*wi))))
                span={'RT':5,'TC':.6,'GC':.5}[f]
                T['did'].append(dict(outcome=outcome,factor=f,span=span,**ct(m,.4*span*wi)))
    adjust([r for r in T['interactions'] if r['outcome']==outcome]);adjust([r for r in T['did'] if r['outcome']==outcome]);adjust([r for r in T['conditional'] if r['outcome']==outcome])
    cm=fit(df,outcome,cat);models[outcome,'categorical']=cm
    for f,levels in LEV.items():
        LM=[cm['G'][grid[f].eq(level)].mean(axis=0) for level in levels]
        T['levels'].append(dict(outcome=outcome,factor=f,n=len(df),**ft(cm,np.array([v-LM[0] for v in LM[1:]]))))
        for level,L in zip(levels,LM):T['means'].append(dict(outcome=outcome,factor=f,level=level,**ct(cm,L)))
        for i,j in combinations(range(len(levels)),2):T['pairs'].append(dict(outcome=outcome,factor=f,low=levels[i],high=levels[j],**ct(cm,LM[j]-LM[i])))
    adjust([r for r in T['levels'] if r['outcome']==outcome]);adjust([r for r in T['pairs'] if r['outcome']==outcome])
    full=fit(df,outcome,cat+'+C(DGC,Sum):(C(RT,Sum)+C(TC,Sum)+C(GC,Sum))')
    for f in ['RT','TC','GC']:
        ids=[j for j,n in enumerate(full['names']) if ':' in n and f'C({f}, Sum)' in n]
        T['categorical_interactions'].append(dict(outcome=outcome,factor=f,**ft(full,np.eye(len(full['names']))[ids])))
    adjust([r for r in T['categorical_interactions'] if r['outcome']==outcome])
    for f in LEV:
        r=next(r for r in T['coefficients'] if r['outcome']==outcome and r['model']=='M3' and r['term']==f+'_c')
        T['sensitivity'].append(dict(outcome=outcome,factor=f,n=len(df),**{k:r[k] for k in ['estimate','se','ci_low','ci_high','t','df','p','p_holm']}))
    print('Fitted',outcome,'N',len(df),flush=True)
# Explicitly preserve both outcomes without selecting by significance.
for name in ['levels','pairs','interactions','did']:
    rows=[r for r in T[name] if r['outcome'] in ['TBU_POST','TBU_FB']]
    adjust(rows,'p_holm_both')
adjust([r for r in T['coefficients'] if r['outcome'] in ['TBU_POST','TBU_FB'] and r['model']=='M3' and r['term'] in ['RT_c','TC_c','GC_c','DGC_c']], 'p_holm_both')
# Coefficients differ exactly by fitting the within-scenario clock difference.
gap=fit(cases,'clock_gap',FORMS['M3'])
for j,term in enumerate(gap['names']):T['clock_difference'].append(dict(term=term,**ct(gap,np.eye(len(gap['names']))[j])))
assert np.allclose(models['TBU_FB','M3']['o'].params-models['TBU_POST','M3']['o'].params,gap['o'].params)
for f in LEV:
    for level,z in cases.groupby(f):
        T['descriptives'].append(dict(factor=f,level=float(level),n=len(z),events=int(z.matched_n.sum()),
            POST_mean=float(z.TBU_POST.mean()),POST_sd=float(z.TBU_POST.std()),FB_mean=float(z.TBU_FB.mean()),FB_sd=float(z.TBU_FB.std()),
            censored=int(z.censored_n.sum())))
for name,rows in T.items():pd.DataFrame(rows).to_csv(DATA/(name+'.csv'),index=False,encoding='utf-8-sig')
summary=dict(completed_scenarios=54,rounds=10,users_per_scenario=300,user_scenario_instances=16200,ever_believer_instances=980,
    all_actual_transitions=758,matched_post_release_events=757,strictly_after_events=475,same_release_round_events=282,
    resolved_before_release=1,right_censored_first_episodes=222,second_episode_censored=1,
    main_scenario_n=54,strict_scenario_n=52,main_POST_mean=float(cases.TBU_POST.mean()),main_FB_mean=float(cases.TBU_FB.mean()),
    clock_gap_mean=float(cases.clock_gap.mean()),event_weighted_POST=float(ev.TBU_POST.mean()),event_weighted_FB=float(ev.TBU_FB.mean()),
    never_believers=16200-980,initial_cohort_n=911,
    initial_cohort_distinct_ids=int(people[people.first_belief_tick.eq(1)].agent_id.nunique()),
    strict_undefined_cases=cases.loc[cases.STRICT_POST.isna(),'case_id'].tolist(),
    paired_clock_identity='TBU_FB - TBU_POST = RT - first_belief_tick',
    initial_same_user_correction='First observed qualifying transition; later relapse does not erase first update.',
    official_not_seen_before_update=int((ev.official_first_seen_tick.isna()|ev.official_first_seen_tick.gt(ev.reject_tick)).sum()),
    api_calls=0)
output=dict(summary=summary,formulas=FORMS,centers=centers,levels=LEV,tables=T,source_files=old_extract['source_files'])
(ROOT/'analysis.json').write_text(json.dumps(output,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
print(json.dumps(summary,ensure_ascii=False,indent=2))
print(pd.DataFrame(T['levels']).query('outcome in ["TBU_POST","TBU_FB"]').to_string(index=False))
print(pd.DataFrame(T['interactions']).query('outcome in ["TBU_POST","TBU_FB"]').to_string(index=False))
print('ENDPOINT CONTRASTS')
print(pd.DataFrame([r for r in T['pairs'] if r['outcome'] in ['TBU_POST','TBU_FB'] and (r['factor'],r['low'],r['high']) in [('RT',2,7),('TC',.2,.8),('GC',.25,.75),('DGC',0,.4)]]).to_string(index=False))
print('NUMERIC MAIN SLOPES')
print(pd.DataFrame([r for r in T['sensitivity'] if r['outcome'] in ['TBU_POST','TBU_FB']]).to_string(index=False))
