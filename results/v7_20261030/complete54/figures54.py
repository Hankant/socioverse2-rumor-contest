"""Publication-style static figures from the complete factorial analysis."""
from pathlib import Path
import sys,json
ROOT=Path(__file__).resolve().parent
sys.path.extend([str(ROOT/'scientific_deps'),'D:/Program Files/Python312/Lib/site-packages'])
import numpy as np,pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

out=ROOT/'figures';out.mkdir(exist_ok=True)
analysis=json.loads((ROOT/'analysis.json').read_text(encoding='utf-8'));T=analysis['tables']
cases=pd.read_csv(ROOT/'data/cases.csv');initial=pd.read_csv(ROOT/'data/initial_believers.csv')
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'axes.titlesize':11,'axes.labelsize':10,
    'axes.spines.top':False,'axes.spines.right':False,'axes.grid':False,'savefig.facecolor':'white',
    'svg.fonttype':'none','pdf.fonttype':42,'axes.unicode_minus':False})
FACTORS=['TG','TC','GT','D'];LABEL={'TG':'Response timing (RT)','TC':'Targeting capacity (TC)',
    'GT':'Government credibility (GC)','D':'Degree of group cocooning (DGC)'}
BLUE='#23628D';RED='#AE4D36';GREY='#687381';COLORS=[BLUE,RED,'#4B7D53'];manifest=[]
def fp(p):return '<.001' if p<.001 else f'{p:.3f}'
def save(fig,name,caption):
    fig.savefig(out/(name+'.png'),dpi=300,bbox_inches='tight')
    fig.savefig(out/(name+'.svg'),bbox_inches='tight');fig.savefig(out/(name+'.pdf'),bbox_inches='tight')
    plt.close(fig);manifest.append(dict(stem=name,caption=caption))
def theme(ax):
    ax.grid(axis='y',alpha=.17);ax.set_axisbelow(True)
def means(outcome):return pd.DataFrame([r for r in T['means'] if r['outcome']==outcome])

fig,ax=plt.subplots(figsize=(7.6,3.6));ax.set_xlim(0,10);ax.set_ylim(-.6,2);ax.set_yticks([1.2,.2],['Earlier response','Later response'])
for y,release,update in [(1.2,2,3),(.2,7,8)]:
    ax.plot([1,update],[y,y],color=BLUE,lw=5,alpha=.7)
    for tick,marker,color in [(1,'o',BLUE),(release,'s',RED),(update,'D','#4B7D53')]:ax.scatter(tick,y,marker=marker,color=color,s=60,zorder=3)
    ax.text((1+update)/2,y+.2,f'TBU = {update-1} steps',ha='center',fontsize=10)
    ax.text((release+update)/2,y-.22,'Post-response delay = 1',ha='center',fontsize=9)
ax.set_xticks(range(11));ax.set_xlabel('Simulation step');ax.set_title('Two clocks answer different questions',loc='left',fontweight='bold')
ax.spines['left'].set_visible(False);ax.spines['bottom'].set_position(('outward',5))
fig.text(.17,.035,'Circle: first belief; square: official release; diamond: first rejection.\nIllustrative example only; not observed trajectories.',fontsize=9)
fig.subplots_adjust(bottom=.32)
save(fig,'01_two_time_origins','两个时间起点的示意。首次相信至不信的TBU与回应发布后的等待并不相同；图中示例不是观测数据。')

for outcome,name,title,ylabel,color in [('RMST_initial9','02_TBU9_levels','Restricted mean belief updating time','Restricted mean TBU over 9 steps',BLUE),
    ('RMST_post3','03_post_response_levels','Restricted mean post-response updating delay','Restricted mean delay over 3 steps',RED)]:
    M=means(outcome);fig,axs=plt.subplots(2,2,figsize=(7.4,5.9),sharey=True)
    for ax,f in zip(axs.flat,FACTORS):
        z=M[M.factor.eq(f)].sort_values('level');x=np.arange(len(z));a=z['mean'].to_numpy()
        ax.errorbar(x,a,yerr=[a-z.ci_low.to_numpy(),z.ci_high.to_numpy()-a],fmt='o-',capsize=4,color=color,lw=1.6)
        labels=[f'Step {int(v)}' if f=='TG' else f'{v:.2f}' for v in z.level]
        ax.set_xticks(x,labels);ax.set_title(LABEL[f],loc='left')
        r=next(r for r in T['main'] if r['outcome']==outcome and r['factor']==f)
        ax.text(.02 if f=='TG' else .98,.96,f'Holm p {fp(r["p_holm"])}',transform=ax.transAxes,
                va='top',ha='left' if f=='TG' else 'right',fontsize=9)
        for xx,v,upper in zip(x,a,z.ci_high.to_numpy()):
            ax.annotate(f'{v:.2f}',(xx,upper),xytext=(0,5),textcoords='offset points',ha='center',fontsize=9)
        theme(ax);ax.set_xlim(-.4,len(z)-.6)
        ax.set_ylim(0,9 if outcome=='RMST_initial9' else 3)
    axs[0,0].set_ylabel(ylabel);axs[1,0].set_ylabel(ylabel)
    fig.suptitle(title,ha='left',x=.07,fontweight='bold',fontsize=13)
    fig.tight_layout(rect=[0,.02,1,.94]);fig.text(.08,.005,'Points: scenario-weighted marginal means. Bars: pointwise 95% HC3 intervals. Lower is faster.',fontsize=8)
    save(fig,name,'各因素不同水平的情景等权边际均值与95% HC3置信区间。主效应p对两结局共8项检验作Holm校正。')

fig,axs=plt.subplots(1,2,figsize=(8.2,4.3));comparisons={'TG':(2,7),'TC':(.2,.8),'GT':(.25,.75),'D':(0,.4)}
for ax,outcome,title,color in zip(axs,['RMST_initial9','RMST_post3'],['TBU9','Post-response delay3'],[BLUE,RED]):
    for i,f in enumerate(FACTORS):
        lo,hi=comparisons[f];r=next(r for r in T['pairwise'] if r['outcome']==outcome and r['factor']==f and r['low']==lo and r['high']==hi)
        ax.errorbar(r['difference'],3-i,xerr=[[r['difference']-r['ci_low']],[r['ci_high']-r['difference']]],fmt='o',color=color,capsize=3)
    ax.axvline(0,color=GREY,lw=1,ls='--');ax.set_yticks(range(4),['DGC .40 - .00','GC .75 - .25','TC .80 - .20','RT 7 - 2'])
    ax.set_xlabel('Difference in simulation steps');ax.set_title(title,loc='left',fontweight='bold');ax.grid(axis='x',alpha=.17)
fig.tight_layout();save(fig,'04_endpoint_effects','端点水平差异与逐项95% HC3区间。负差值表示更短；显著性判断另用20项两两比较的Holm校正p，完整表还提供同时区间。')

fig,axs=plt.subplots(3,1,figsize=(7.3,8.5),sharex=True)
for ax,f in zip(axs,['GT','TG','TC']):
    for oi,outcome,color,label in [(0,'RMST_initial9',BLUE,'TBU9'),(1,'RMST_post3',RED,'Post-response delay3')]:
        z=sorted([r for r in T['conditional'] if r['outcome']==outcome and r['factor']==f],key=lambda r:r['D'])
        x=np.array([r['D'] for r in z])+(oi-.5)*.008;y=np.array([r['difference'] for r in z])
        ax.errorbar(x,y,yerr=[y-np.array([r['ci_low'] for r in z]),np.array([r['ci_high'] for r in z])-y],fmt='o-',capsize=3,color=color,label=label)
    ax.axhline(0,color=GREY,ls='--',lw=.8);theme(ax)
    ax.set_title(LABEL[f]+f'  ({comparisons[f][1]} minus {comparisons[f][0]})',loc='left')
    p1=next(r['p_holm'] for r in T['moderation'] if r['outcome']=='RMST_initial9' and r['factor']==f)
    p2=next(r['p_holm'] for r in T['moderation'] if r['outcome']=='RMST_post3' and r['factor']==f)
    ax.set_title(LABEL[f]+f'  ({comparisons[f][1]} minus {comparisons[f][0]})\n'+
                 f'Joint interaction Holm p: TBU9 {fp(p1)}; delay3 {fp(p2)}',loc='left',fontsize=10)
    ax.set_ylabel('High-minus-low effect\n(simulation steps)')
axs[0].legend(frameon=False,ncol=2,loc='best');axs[-1].set_xticks([0,.2,.4]);axs[-1].set_xlabel('Degree of group cocooning (DGC)')
fig.tight_layout();save(fig,'05_cocooning_moderation','三项条件效应随DGC变化的曲线。点为高低水平差异，线为95%逐项区间；总体交互p对两结局共6项作Holm校正，均未达到.05。')

methods=['primary','wild','matched','additive','all_two_way','cohort_weighted','endpoints']
methodlabels=['HC3 factorial','Wild bootstrap','Matched test','Additive HC3','All two-way HC3','Cohort weighted','Endpoints only']
matrix=[];rownames=[]
for outcome in ['RMST_initial9','RMST_post3']:
    for f in FACTORS:
        ps=[]
        for method in methods:
            if method=='primary':r=next(r for r in T['main'] if r['outcome']==outcome and r['factor']==f);p=r['p_holm']
            elif method=='wild':r=next(r for r in T['wild'] if r['outcome']==outcome and r['factor']==f and r['kind']=='main');p=r['p_holm']
            elif method=='matched':r=next(r for r in T['matched'] if r['outcome']==outcome and r['factor']==f);p=r['p_holm']
            else:r=next(r for r in T['specifications'] if r['outcome']==outcome and r['factor']==f and r['method']==method);p=r['p_method_holm']
            ps.append(p)
        matrix.append(ps);rownames.append(('TBU9' if outcome=='RMST_initial9' else 'Delay3')+' / '+{'TG':'RT','TC':'TC','GT':'GC','D':'DGC'}[f])
A=np.array(matrix);fig,ax=plt.subplots(figsize=(9.0,5));im=ax.imshow(-np.log10(np.maximum(A,1e-6)),cmap='Blues',vmin=0,vmax=6,aspect='auto')
for i in range(len(A)):
    for j in range(A.shape[1]):ax.text(j,i,'<.001' if A[i,j]<.001 else f'{A[i,j]:.3f}',ha='center',va='center',fontsize=10,color='white' if A[i,j]<.001 else '#20242B')
ax.set_xticks(range(len(methods)),methodlabels,rotation=28,ha='right',fontsize=10);ax.set_yticks(range(len(rownames)),rownames)
ax.set_title('Adjusted p values across analysis methods',loc='left',fontweight='bold');fig.colorbar(im,ax=ax,shrink=.8,label='-log10(adjusted p)')
fig.tight_layout();save(fig,'06_method_robustness','七种方法或规格的比较。各列在同一方法内对8项平均主效应作Holm校正；全部探索检验另附全局BH和Holm。各列不是独立重复实验证据。')

fig,axs=plt.subplots(2,2,figsize=(7.4,6),sharex=True,sharey=True)
for ax,f in zip(axs.flat,FACTORS):
    for level,color in zip(sorted(cases[f].unique()),COLORS):
        z=initial[initial[f].eq(level)];curves=[]
        for _,g in z.groupby('case_id'):
            curves.append([np.mean((g.event.eq(0)|g.duration.gt(t)).to_numpy()) for t in range(10)])
        S=np.mean(curves,axis=0);ax.step(range(10),S,where='post',color=color,label=f'{level:g}')
    ax.set_title(LABEL[f],loc='left');ax.set_ylim(-.03,1.03);ax.set_xlim(0,9);theme(ax);ax.legend(frameon=False,title='Level',fontsize=8)
axs[1,0].set_xlabel('Steps since first belief');axs[1,1].set_xlabel('Steps since first belief')
axs[0,0].set_ylabel('Proportion not yet updated');axs[1,0].set_ylabel('Proportion not yet updated')
fig.tight_layout();save(fig,'07_belief_update_curves','第1轮相信者尚未完成首次更新的比例。先在各情景内计算，再对情景等权平均；末轮尚未更新者右删失。面积对应9轮限制平均TBU，不将用户轨迹视为独立实验。')

rowkeys=[(D,TC) for D in [0,.2,.4] for TC in [.2,.8]];colkeys=[(RT,GC) for RT in [2,4,7] for GC in [.25,.5,.75]]
Z=np.array([[cases.loc[cases.D.eq(D)&cases.TC.eq(TC)&cases.TG.eq(RT)&cases.GT.eq(GC),'RMST_initial9'].iloc[0] for RT,GC in colkeys] for D,TC in rowkeys])
fig,ax=plt.subplots(figsize=(8.4,4.6));im=ax.imshow(Z,cmap='YlOrRd',vmin=1,vmax=9,aspect='auto')
for i in range(6):
    for j in range(9):ax.text(j,i,f'{Z[i,j]:.2f}',ha='center',va='center',fontsize=9,color='white' if Z[i,j]>6.7 else '#20242B')
ax.set_yticks(range(6),[f'DGC {d:.2f} / TC {t:.2f}' for d,t in rowkeys]);ax.set_xticks(range(9),[f'RT {r}\nGC {g:.2f}' for r,g in colkeys])
ax.set_title('All 54 observed scenarios',loc='left',fontweight='bold');fig.colorbar(im,ax=ax,label='Restricted mean TBU9 (lower is faster)')
fig.tight_layout();save(fig,'08_full54_TBU_heatmap','54个实际完成情景的限制平均TBU，无插值或预测填格。行按DGC与TC排列，列按RT与GC排列；所有值来自真实保存的模拟输出。')

fig,axs=plt.subplots(1,3,figsize=(9,3.8))
for ax,f in zip(axs,['GT','TG','TC']):
    z=sorted([r for r in T['conditional'] if r['outcome']=='believer_rounds' and r['factor']==f],key=lambda r:r['D'])
    x=[r['D'] for r in z];y=np.array([r['difference'] for r in z]);ax.errorbar(x,y,yerr=[y-np.array([r['ci_low'] for r in z]),np.array([r['ci_high'] for r in z])-y],fmt='o-',color=BLUE,capsize=3)
    rr=next(r for r in T['moderation'] if r['outcome']=='believer_rounds' and r['factor']==f)
    ax.set_title({'GT':'GC .75 minus .25','TG':'RT 7 minus 2','TC':'TC .80 minus .20'}[f]+
        '\nInteraction Holm p '+fp(rr['p_supplement_holm']),loc='left',fontsize=9)
    ax.set_xticks([0,.2,.4]);ax.set_xlabel('DGC');ax.axhline(0,color=GREY,lw=.7,ls='--');theme(ax)
axs[0].set_ylabel('Difference in believer person-rounds');fig.tight_layout()
save(fig,'09_burden_moderation','补充结局总相信负担的调节效应。GC和RT与DGC的交互显著，TC交互不显著；总相信负担是10轮相信人数之和，不能改称为TBU。')
(ROOT/'figure_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
print('Saved',len(manifest),'figures in PNG, SVG and PDF.')
