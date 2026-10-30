"""Complete, transparent scenario-level factorial analysis; no API calls."""
from pathlib import Path
from itertools import product, combinations, permutations
import os,sys,json,warnings,platform
for k in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS'):os.environ[k]='1'
ROOT=Path(__file__).resolve().parent

import numpy as np
import pandas as pd
from scipy import stats
import scipy,statsmodels.api as sm,patsy
from statsmodels.stats.multitest import multipletests

DATA=ROOT/'data';data=pd.read_csv(DATA/'cases.csv')
assert len(data)==54 and data.complete.all() and data.last_tick.eq(10).all()
FACTORS=['GT','TG','TC','D'];TARGETS=FACTORS[:3]
LEVELS={'GT':[.25,.5,.75],'TG':[2,4,7],'TC':[.2,.8],'D':[0,.2,.4]}
grid=pd.DataFrame(product(*(LEVELS[k] for k in FACTORS)),columns=FACTORS)
assert not data.duplicated(FACTORS).any()
assert set(map(tuple,data[FACTORS].to_numpy()))==set(map(tuple,grid.to_numpy()))
TERMS={f:f'C({f}, Sum)' for f in FACTORS}
FORM={'primary':' + '.join(TERMS.values())+' + '+' + '.join(TERMS[f]+':'+TERMS['D'] for f in TARGETS),
      'additive':' + '.join(TERMS.values()),'all_two_way':'('+' + '.join(TERMS.values())+')**2'}
PRIMARY=['RMST_initial9','RMST_post3'];OUTCOMES=PRIMARY+['initial_TBU_completed','believer_rounds']
HELPERS=(ROOT/'statistical_helpers.py').read_text(encoding='utf-8')
exec(compile(HELPERS,'statistical_helpers.py','exec'))

# The main implementation is independently checked against statsmodels OLS HC3.
# This wrapper adds the explicitly labelled cohort-size-weighted sensitivity.
unweighted_fit=fit
def fit(data,y,formula,weights=None):
    if weights is None:return unweighted_fit(data,y,formula)
    frame=patsy.dmatrix(formula,data,return_type='dataframe');raw=frame.to_numpy();w=np.asarray(weights,float);w=w/w.mean()
    X=raw*np.sqrt(w[:,None]);Y=np.asarray(y)*np.sqrt(w);n,p=X.shape
    assert np.linalg.matrix_rank(X)==p and n>p
    P=np.linalg.pinv(X);b=P@Y;res=Y-X@b;h=np.einsum('ij,ji->i',X,P);bread=P@P.T
    V=(P*(res/(1-h))**2)@P.T;Vc=bread*(res@res/(n-p))
    check=sm.WLS(y,raw,weights=w).fit().get_robustcov_results(cov_type='HC3',use_t=True)
    assert np.allclose(b,check.params) and np.allclose(V,check.cov_params())
    G=np.asarray(patsy.build_design_matrices([frame.design_info],grid)[0])
    return dict(X=X,b=b,res=res,h=h,pinv=P,bread=bread,V=V,Vc=Vc,df=n-p,n=n,p=p,G=G,
        info=frame.design_info,checked=check,r2=float(check.rsquared))

tables={k:[] for k in ['main','pairwise','moderation','means','conditional','did','wild','matched',
    'matched_did','specifications','joint','diagnostics','leave_one_out','descriptives','best_cases']}
models={}
def margins(m,factor):
    return [m['G'][grid[factor].eq(level)].mean(axis=0) for level in sorted(grid[factor].unique())]
def contrast(m,L):
    z=ct(m,L)
    for key in ('simultaneous_low','simultaneous_high'):z.pop(key,None)
    return z
def adj(rows,name='p_holm'):
    for r,p in zip(rows,holm([r['p'] for r in rows])):r[name]=float(p)
def inter_restriction(m,f):
    idx=[i for i,name in enumerate(m['info'].column_names) if ':' in name and TERMS[f] in name and TERMS['D'] in name]
    return np.eye(m['p'])[idx]
def fixed_margins(m,f,gap):
    return [m['G'][grid[f].eq(l)&grid.D.eq(gap)].mean(axis=0) for l in LEVELS[f]]

for outcome in OUTCOMES:
    z=data[data[outcome].notna()].copy();y=z[outcome].to_numpy()
    m=fit(z,y,FORM['primary']);models[outcome]=m
    tables['diagnostics'].append(dict(outcome=outcome,n=m['n'],parameters=m['p'],df=m['df'],r2=m['r2'],
        max_leverage=float(m['h'].max()),shapiro_p=float(stats.shapiro(m['res']).pvalue)))
    for f in FACTORS:
        tables['main'].append(dict(outcome=outcome,factor=f,method='primary_HC3',**ft(m,restriction(m,f))))
        M=margins(m,f)
        for level,L in zip(LEVELS[f],M):
            a=z[z[f].eq(level)][outcome];se=float(np.sqrt(L@m['V']@L));crit=stats.t.ppf(.975,m['df'])
            tables['means'].append(dict(outcome=outcome,factor=f,level=level,n=len(a),mean=float(L@m['b']),
                raw_mean=float(a.mean()),sd=float(a.std()),se=se,ci_low=float(L@m['b'])-crit*se,ci_high=float(L@m['b'])+crit*se))
        for lo,hi in combinations(range(len(M)),2):
            tables['pairwise'].append(dict(outcome=outcome,factor=f,low=LEVELS[f][lo],high=LEVELS[f][hi],**contrast(m,M[hi]-M[lo])))
        idx=[i for i,name in enumerate(m['info'].column_names) if TERMS[f] in name]
        tables['joint'].append(dict(outcome=outcome,factor=f,**ft(m,np.eye(m['p'])[idx])))
    for f in TARGETS:
        R=inter_restriction(m,f)
        tables['moderation'].append(dict(outcome=outcome,factor=f,**ft(m,R)))
        conditional_vectors=[]
        for gap in LEVELS['D']:
            M=fixed_margins(m,f,gap);L=M[-1]-M[0];conditional_vectors.append(L)
            tables['conditional'].append(dict(outcome=outcome,factor=f,D=gap,**contrast(m,L)))
        tables['did'].append(dict(outcome=outcome,factor=f,D_low=0,D_high=.4,**contrast(m,conditional_vectors[-1]-conditional_vectors[0])))
    # Same inputs and outcomes, alternative model structures and fit weights.
    specifications=[(name,formula,None) for name,formula in FORM.items()]
    if outcome in PRIMARY:
        specifications.append(('cohort_weighted',FORM['primary'],z['initial_believers' if outcome=='RMST_initial9' else 'post_cohort_n'].to_numpy()))
    for name,formula,weights in specifications:
        mm=fit(z,y,formula,weights=weights)
        for f in FACTORS:
            tables['specifications'].append(dict(outcome=outcome,method=name,factor=f,n=mm['n'],parameters=mm['p'],**ft(mm,restriction(mm,f))))
        if name=='all_two_way' and outcome in PRIMARY:
            for f in TARGETS:
                tables['specifications'].append(dict(outcome=outcome,method=name+'_interaction',factor=f,n=mm['n'],parameters=mm['p'],**ft(mm,inter_restriction(mm,f))))
    if outcome in PRIMARY:
        print('Wild bootstrap',outcome,flush=True)
        for n,f in enumerate(FACTORS):
            R=restriction(m,f);wr=wild(m,R,y,B=9999,seed=202610290+n+10*PRIMARY.index(outcome))
            tables['wild'].append(dict(outcome=outcome,factor=f,kind='main',**{**ft(m,R),**wr,'p':wr['p_wild']}))
        for n,f in enumerate(TARGETS):
            R=inter_restriction(m,f);wr=wild(m,R,y,B=9999,seed=202610390+n+10*PRIMARY.index(outcome))
            tables['wild'].append(dict(outcome=outcome,factor=f,kind='moderation',**{**ft(m,R),**wr,'p':wr['p_wild']}))
        # Pairwise complete-background tests; all levels retained.
        for fi,f in enumerate(FACTORS):
            others=[k for k in FACTORS if k!=f]
            wide=z.pivot(index=others,columns=f,values=outcome).dropna();A=wide[LEVELS[f]].to_numpy();n,k=A.shape
            B=99999;rng=np.random.default_rng(20261029+fi);cnt=0
            if k==2:
                diff=A[:,1]-A[:,0];obs=abs(diff.mean());tt=stats.ttest_rel(A[:,1],A[:,0]);ci=tt.confidence_interval()
                for start in range(0,B,1000):
                    draw=rng.choice([-1.,1.],size=(min(1000,B-start),n))@diff/n
                    cnt+=int((np.abs(draw)>=obs-1e-12).sum())
                r=dict(outcome=outcome,factor=f,backgrounds=n,statistic=float(tt.statistic),name='paired t',
                    df=n-1,p_paired_t=float(tt.pvalue),difference=float(diff.mean()),ci_low=float(ci.low),ci_high=float(ci.high))
            else:
                ranks=stats.rankdata(A,axis=1);obs=np.sum((ranks.sum(axis=0)-n*(k+1)/2)**2);pp=np.array(list(permutations(range(k))));ii=np.arange(n)[None,:,None]
                for start in range(0,B,1000):
                    idx=pp[rng.integers(len(pp),size=(min(1000,B-start),n))];rr=ranks[ii,idx]
                    cnt+=int((np.sum((rr.sum(axis=1)-n*(k+1)/2)**2,axis=1)>=obs-1e-12).sum())
                ff=stats.friedmanchisquare(*A.T)
                r=dict(outcome=outcome,factor=f,backgrounds=n,statistic=float(ff.statistic),name='Friedman Q',df=k-1,p_asymptotic=float(ff.pvalue))
            r.update(p=(cnt+1)/(B+1),permutations=B);tables['matched'].append(r)
        # Direct, matched difference-in-differences. Exact sign flips.
        for f in TARGETS:
            others=[k for k in FACTORS if k not in (f,'D')]
            keep=z[z[f].isin([LEVELS[f][0],LEVELS[f][-1]])&z.D.isin([0,.4])]
            ww=keep.pivot(index=others,columns=['D',f],values=outcome)
            diff=(ww[(.4,LEVELS[f][-1])]-ww[(.4,LEVELS[f][0])])-(ww[(0,LEVELS[f][-1])]-ww[(0,LEVELS[f][0])])
            a=diff.to_numpy();n=len(a);sign=np.array(list(product([-1.,1.],repeat=n)));null=sign@a/n
            exact=float((np.abs(null)>=abs(a.mean())-1e-12).mean());tt=stats.ttest_1samp(a,0);ci=tt.confidence_interval()
            tables['matched_did'].append(dict(outcome=outcome,factor=f,backgrounds=n,difference=float(a.mean()),
                t=float(tt.statistic),df=n-1,ci_low=float(ci.low),ci_high=float(ci.high),p=exact,p_t=float(tt.pvalue),exact_configurations=len(sign)))
        # Endpoint-only sensitivity is not used to replace the full design.
        previous_grid=grid
        grid=pd.DataFrame(product([.25,.75],[2,7],[.2,.8],[0,.2,.4]),columns=FACTORS)
        ep=z[z.GT.isin([.25,.75])&z.TG.isin([2,7])];em=fit(ep,ep[outcome].to_numpy(),FORM['primary'])
        for f in FACTORS:
            tables['specifications'].append(dict(outcome=outcome,method='endpoints',factor=f,n=em['n'],parameters=em['p'],**ft(em,restriction(em,f))))
        grid=previous_grid
        for ix,row in z.iterrows():
            zz=z.drop(ix);mm=fit(zz,zz[outcome].to_numpy(),FORM['primary'])
            for f in FACTORS:
                M=margins(mm,f)
                tables['leave_one_out'].append(dict(outcome=outcome,omitted=row.case_id,factor=f,kind='main',
                    difference=float((M[-1]-M[0])@mm['b']),**ft(mm,restriction(mm,f))))
            for f in TARGETS:
                M0=fixed_margins(mm,f,0);M1=fixed_margins(mm,f,.4)
                tables['leave_one_out'].append(dict(outcome=outcome,omitted=row.case_id,factor=f,kind='moderation',
                    difference=float((M1[-1]-M1[0]-M0[-1]+M0[0])@mm['b']),**ft(mm,inter_restriction(mm,f))))
    print('MAIN',outcome,[(r['factor'],round(r['F'],4),round(r['p'],7)) for r in tables['main'] if r['outcome']==outcome],flush=True)

for name in ('main','pairwise','moderation','conditional','did','joint'):
    primary_rows=[r for r in tables[name] if r['outcome'] in PRIMARY];supplement=[r for r in tables[name] if r['outcome'] not in PRIMARY]
    adj(primary_rows);adj(supplement,'p_supplement_holm')
    if name in ('pairwise','did','conditional'):
        for r in primary_rows:
            critical=stats.t.ppf(1-.05/(2*len(primary_rows)),r['df'])
            r['ci_family_low']=r['difference']-critical*r['se'];r['ci_family_high']=r['difference']+critical*r['se']
adj(tables['matched']);adj(tables['matched_did'])
for kind in ('main','moderation'):adj([r for r in tables['wild'] if r['kind']==kind])
for method in sorted({r['method'] for r in tables['specifications']}):
    adj([r for r in tables['specifications'] if r['method']==method and r['outcome'] in PRIMARY], 'p_method_holm')
exploratory=tables['specifications']+tables['matched']+tables['matched_did']+tables['wild']
for r,q,p in zip(exploratory,multipletests([r['p'] for r in exploratory],method='fdr_bh')[1],holm([r['p'] for r in exploratory])):
    r['q_exploratory_BH']=float(q);r['p_exploratory_holm']=float(p)
for kind in ('main','moderation'):
    for tag in data.case_id:
        adj([r for r in tables['leave_one_out'] if r['kind']==kind and r['omitted']==tag])
for outcome in PRIMARY:
    smallest=data.nsmallest(5,outcome)
    tables['best_cases'] += smallest[['case_id',*FACTORS,outcome,'initial_believers','post_cohort_n','final_believe']].assign(outcome=outcome).to_dict('records')

# Directly observable descriptive summaries, kept separate from model inference.
I=pd.read_csv(DATA/'initial_believers.csv');P=pd.read_csv(DATA/'post_cohort.csv');F=pd.read_csv(DATA/'first_belief.csv')
for f in FACTORS:
    for lev in LEVELS[f]:
        z=data[data[f].eq(lev)];ii=I[I[f].eq(lev)];pp=P[P[f].eq(lev)]
        tables['descriptives'].append(dict(factor=f,level=lev,scenarios=len(z),initial_trajectories=len(ii),
            initial_events=int(ii.event.sum()),initial_censored=int((1-ii.event).sum()),
            scenario_mean_TBU9=float(z.RMST_initial9.mean()),individual_mean_TBU9=float(np.minimum(ii.duration,9).mean()),
            scenario_mean_PRUD3=float(z.RMST_post3.mean()),post_cohort=len(pp),
            scenario_mean_initial_n=float(z.initial_believers.mean()),scenario_mean_burden=float(z.believer_rounds.mean())))

common_ids=set.intersection(*(set(g.agent_id) for _,g in I.groupby('case_id')))
summary=dict(scenarios=54,user_time_rows=54*300*11,initial_records=len(I),initial_events=int(I.event.sum()),
    initial_censored=int((1-I.event).sum()),initial_unique_users=I.agent_id.nunique(),all_first_records=len(F),
    first_events=int(F.event.sum()),first_censored=int((1-F.event).sum()),post_cohort=len(P),
    post_events=int(P.event.sum()),post_censored=int((1-P.event).sum()),common_initial_ids_across54=sorted(common_ids),
    first_events_before_official=int((F.event.eq(1)&(F.end_tick<F.official_first_tick)).sum()),
    first_events_without_official=int((F.event.eq(1)&F.official_first_tick.isna()).sum()))
for name,rows in tables.items():pd.DataFrame(rows).to_csv(DATA/(name+'.csv'),index=False,encoding='utf-8-sig')
versions=dict(python=platform.python_version(),numpy=np.__version__,pandas=pd.__version__,scipy=scipy.__version__,statsmodels=sm.__version__,patsy=patsy.__version__)
output=dict(primary_outcomes=PRIMARY,outcomes=OUTCOMES,formulas=FORM,levels=LEVELS,summary=summary,
    family_sizes={'main':8,'moderation':6,'pairwise':20,'conditional':18,'did':6,'exploratory':len(exploratory)},
    versions=versions,tables=tables)
def native(v):
    if isinstance(v,np.generic):return v.item()
    if isinstance(v,float) and not np.isfinite(v):return None
    if isinstance(v,dict):return {k:native(w) for k,w in v.items()}
    if isinstance(v,list):return [native(w) for w in v]
    return v
(ROOT/'analysis.json').write_text(json.dumps(native(output),ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
print('SUMMARY',json.dumps(native(summary),ensure_ascii=False),flush=True)
print('PRIMARY MAIN',pd.DataFrame(tables['main']).query('outcome in @PRIMARY').to_string(index=False),flush=True)
print('PRIMARY MODERATION',pd.DataFrame(tables['moderation']).query('outcome in @PRIMARY').to_string(index=False),flush=True)
