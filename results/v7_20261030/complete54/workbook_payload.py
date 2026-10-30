from pathlib import Path
import json,math
import pandas as pd

root=Path(__file__).resolve().parent
a=json.loads((root/'analysis.json').read_text(encoding='utf-8'));t=a['tables']
case=pd.read_csv(root/'data/cases.csv');initial=pd.read_csv(root/'data/initial_believers.csv');post=pd.read_csv(root/'data/post_cohort.csv')
names={'GT':'Government credibility GC','TG':'Response timing RT','TC':'Targeting capacity TC','D':'Group cocooning DGC'}
out={'RMST_initial9':'TBU9','RMST_post3':'PRUD3','initial_TBU_completed':'仅已转变者TBU','believer_rounds':'总相信负担'}
primary=set(a['primary_outcomes'])
main=[]
for kind in ('main','moderation'):
    for r in t[kind]:
        if r['outcome'] not in primary:continue
        main.append([out[r['outcome']],'平均水平差异' if kind=='main' else 'DGC调节',names[r['factor']],r['F'],r['df_num'],r['df_den'],r['p'],r['p_holm'],'显著' if r['p_holm']<.05 else '未获显著支持'])
pairs=[[out[r['outcome']],names[r['factor']],r['low'],r['high'],r['difference'],r['se'],r['t'],r['df'],r['ci_low'],r['ci_high'],r['p'],r['p_holm'],r['ci_family_low'],r['ci_family_high']] for r in t['pairwise'] if r['outcome'] in primary]
moderation=[]
for kind in ('conditional','did','matched_did'):
    for r in t[kind]:
        if r['outcome'] not in primary:continue
        moderation.append([out[r['outcome']],{'conditional':'DGC分层差异','did':'模型差异之差','matched_did':'匹配精确差异之差'}[kind],names[r['factor']],r.get('D'),r.get('backgrounds'),r['difference'],r.get('se'),r['t'],r['df'],r['ci_low'],r['ci_high'],r['p'],r['p_holm']])
robust=[]
for kind in ('specifications','wild','matched','matched_did'):
    for r in t[kind]:
        label=r.get('method',kind)
        if kind=='wild':label='wild_'+r['kind']
        robust.append([out[r['outcome']],label,names[r['factor']],r.get('name','F' if 'F' in r else 't'),r.get('F',r.get('statistic',r.get('t'))),r.get('df_num'),r.get('df_den',r.get('df')),r.get('backgrounds'),r.get('wild_B',r.get('permutations',r.get('exact_configurations'))),r['p'],r.get('p_holm',r.get('p_method_holm')),r.get('q_exploratory_BH'),r.get('p_exploratory_holm')])
case_rows=[]
for r in case.itertuples():
    case_rows.append([r.case_id,r.D,r.TG,r.TC,r.GT,None,None,None,None,None,r.believer_rounds,r.final_believe,r.final_reject,r.final_unjudged,r.RMST_initial9,r.RMST_post3])
user_rows=[]
for r in initial.itertuples():
    user_rows.append([r.case_id,r.agent_id,'圈内' if r.group=='inside' else '圈外',r.start_tick,r.end_tick if r.event else None,r.duration,r.event,None,None,r.D,r.TG,r.TC,r.GT])
post_rows=[]
for r in post.itertuples():
    post_rows.append([r.case_id,r.agent_id,r.TG,r.reject_tick if r.event else None,r.wait_or_censor,r.event,None,r.followup,r.D,r.TC,r.GT])
means=[[out[r['outcome']],names[r['factor']],r['level'],r['n'],r['mean'],r['ci_low'],r['ci_high']] for r in t['means'] if r['outcome'] in primary]
payload=dict(main=main,pairs=pairs,moderation=moderation,robust=robust,cases=case_rows,initial=user_rows,post=post_rows,means=means,
    source='完整活动批次 20261027-145124；raw目录54个原始轨迹CSV；分析单位为54情景，非独立用户轨迹。')
def clean(v):
    if isinstance(v,float) and not math.isfinite(v):return None
    if isinstance(v,list):return [clean(x) for x in v]
    if isinstance(v,dict):return {k:clean(x) for k,x in v.items()}
    return v
(root/'workbook_payload.json').write_text(json.dumps(clean(payload),ensure_ascii=False,allow_nan=False),encoding='utf-8')
print('Workbook payload ready.')
