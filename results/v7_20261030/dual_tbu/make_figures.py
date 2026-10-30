from pathlib import Path
import sys,json
ROOT=Path(__file__).resolve().parent;OUT=ROOT/'figures';OUT.mkdir(exist_ok=True)
sys.path.append('D:/Program Files/Python312/Lib/site-packages')
import numpy as np,matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
for fn in ['arial.ttf','arialbd.ttf','times.ttf','msyh.ttc']:font_manager.fontManager.addfont('C:/Windows/Fonts/'+fn)
plt.rcParams.update({'font.family':'Arial','font.size':9,'axes.spines.top':False,'axes.spines.right':False,'pdf.fonttype':42,'svg.fonttype':'none','axes.unicode_minus':False})
A=json.loads((ROOT/'analysis.json').read_text(encoding='utf-8'));T=A['tables']
BLUE='#416F91';TEAL='#3D837A';ORANGE='#B47A4C';GREY='#768692'
NAMES={'RT':'Response timing','TC':'Targeting capacity','GC':'Government credibility','DGC':'Group cocooning'}
LABEL={'TBU_POST':'Publication to rejection','TBU_FB':'First belief to rejection'}
def get(name,**kw):return next(r for r in T[name] if all(r.get(k)==v for k,v in kw.items()))
def pv(p):return '< .001' if p<.001 else '= '+f'{p:.3f}'
def save(f,name):
    for ext in ['png','svg','pdf']:f.savefig(OUT/(name+'.'+ext),dpi=600,facecolor='white')
    f.savefig(OUT/(name+'_preview.png'),dpi=180,facecolor='white');plt.close(f)
fig,axs=plt.subplots(2,4,figsize=(6.9,3.65),layout='constrained')
for row,outcome in enumerate(['TBU_POST','TBU_FB']):
    for col,f in enumerate(NAMES):
        a=axs[row,col];rs=sorted([r for r in T['means'] if r['outcome']==outcome and r['factor']==f],key=lambda r:r['level'])
        x=np.arange(len(rs));y=np.array([r['estimate'] for r in rs]);lo=np.array([r['ci_low'] for r in rs]);hi=np.array([r['ci_high'] for r in rs])
        a.errorbar(x,y,yerr=[y-lo,hi-y],fmt='o-',color=BLUE if row==0 else TEAL,ms=3,capsize=2,lw=1)
        a.set_xticks(x,[f"{r['level']:g}" for r in rs],fontsize=7);a.tick_params(axis='y',labelsize=7)
        a.set_xlim(-.25,len(rs)-.75);a.grid(axis='y',alpha=.18);a.set_ylim(min(0,min(lo)-.15),max(hi)+.4)
        for xx,yy in zip(x,hi):a.annotate(f'{y[xx]:.2f}',(xx,yy),xytext=(0,3),textcoords='offset points',ha='center',fontsize=6.6)
        a.set_title(f"{chr(97+row*4+col)}  {NAMES[f]}\np {pv(get('levels',outcome=outcome,factor=f)['p_holm_both'])}",fontsize=8.2,loc='left',pad=5)
        if col==0:a.set_ylabel(('POST' if row==0 else 'FB')+' TBU (steps)',fontsize=8)
save(fig,'Figure3_dual_clock_levels')
fig,axs=plt.subplots(2,3,figsize=(6.9,3.8),layout='constrained')
for row,outcome in enumerate(['TBU_POST','TBU_FB']):
    for col,f in enumerate(['RT','TC','GC']):
        a=axs[row,col];rs=sorted([r for r in T['conditional'] if r['outcome']==outcome and r['factor']==f],key=lambda r:r['DGC'])
        x=[r['DGC'] for r in rs];y=np.array([r['estimate'] for r in rs]);lo=np.array([r['ci_low'] for r in rs]);hi=np.array([r['ci_high'] for r in rs])
        a.errorbar(x,y,yerr=[y-lo,hi-y],fmt='o-',color=BLUE if row==0 else TEAL,ms=3,capsize=2,lw=1)
        a.axhline(0,ls='--',color=GREY,lw=.7);a.set_xticks([0,.2,.4]);a.set_xlim(-.025,.425);a.tick_params(labelsize=7);a.grid(axis='y',alpha=.18)
        a.set_title(f"{chr(97+row*3+col)}  "+{'RT':'RT +1 step','TC':'TC .80 minus .20','GC':'GC +.25'}[f],fontsize=9,loc='left')
        a.text(.02,.03,'Interaction p '+pv(get('interactions',outcome=outcome,factor=f)['p_holm_both']),transform=a.transAxes,fontsize=6.9,bbox=dict(fc='white',ec='none',pad=.6))
        if col==0:a.set_ylabel(('POST' if row==0 else 'FB')+' TBU difference',fontsize=8)
        if row==1:a.set_xlabel('DGC',fontsize=8)
save(fig,'Figure4_dual_clock_moderation')
# Explain clocks and the common-window check using an explicitly illustrative timeline.
fig,axs=plt.subplots(2,1,figsize=(9,5.4),gridspec_kw={'height_ratios':[1,1.2]},layout='constrained')
a=axs[0];a.set_xlim(0,10.5);a.set_ylim(-.45,1.6);a.set_yticks([]);a.set_xticks(range(11));a.set_xlabel('Simulation round')
for x,t in [(1,'First belief\nb = 1'),(2,'Official release\nRT = 2'),(5,'First rejection\nr = 5')]:
    a.vlines(x,-.15,1.1,colors=GREY,lw=.7,ls=':');a.text(x,1.22,t,ha='center',fontsize=8)
a.annotate('',(5,.75),(2,.75),arrowprops={'arrowstyle':'<->','lw':2,'color':BLUE});a.text(3.5,.92,'POST TBU = 5 - 2 = 3',ha='center',color=BLUE)
a.annotate('',(5,.1),(1,.1),arrowprops={'arrowstyle':'<->','lw':2,'color':TEAL});a.text(3,.27,'FB TBU = 5 - 1 = 4',ha='center',color=TEAL)
a.set_title('a  Same user and endpoint, two starting times',loc='left',weight='bold')
a=axs[1];a.set_xlim(0,10.5);a.set_ylim(-.7,2.8);a.set_yticks([2,1,0],['Release at 2','Release at 4','Release at 7']);a.set_xticks(range(11));a.set_xlabel('Simulation round')
for yy,rt in [(2,2),(1,4),(0,7)]:
    a.plot([rt,10],[yy,yy],color='#CAD2D8',lw=9,solid_capstyle='butt')
    a.plot([rt,rt+3],[yy,yy],color=BLUE,lw=9,solid_capstyle='butt')
    a.scatter([rt],[yy],marker='D',color=ORANGE,s=28,zorder=3)
    a.text(rt+1.5,yy+.19,'Same 3-step interval',ha='center',fontsize=8,color=BLUE)
    for xx in range(rt+1,rt+4):a.scatter(xx,yy,color='white',s=12,zorder=4)
a.axvline(10,color=GREY,ls='--',lw=.8);a.set_title('b  Supplementary check: equal follow-up after release',loc='left',weight='bold')
save(fig,'TBU_clocks_and_common_window')
# Retain the user's three-column composition and vector actor portraits; update all results.
src=Path('D:/Codex/outputs/v7_triptych_20261030/draw_triptych.py').read_text(encoding='utf-8')
adapter="""A=json.loads((ROOT/'analysis.json').read_text(encoding='utf-8'));S=A['tables']
T={'level_means':[dict(r,mean=r['estimate']) for r in S['means'] if r['outcome']=='TBU_FB'],
   'did':[dict(r,cov='HC3',difference=r['estimate'],p_holm=r['p_holm_both']) for r in S['did'] if r['outcome']=='TBU_FB'],
   'outcome_comparison':[dict(r,kind='main',difference=r['estimate']) for r in S['sensitivity']]}
"""
src=src.replace("T=json.loads(Path('D:/Codex/outputs/v7_manuscript_methods_20261030/analysis.json').read_text(encoding='utf-8'))['tables']",adapter)
src=src.replace("'TBU',size=", "'TBU',size=")
src=src.replace("54 complete runs; 52 defined strict-TBU means","54 runs; two matched TBU clocks")
src=src.replace("'GC: p < .001' if fa=='GC' else 'TC: p = .007'","('GC: p '+pv(get('levels',outcome='TBU_FB',factor='GC')['p_holm_both'])) if fa=='GC' else ('TC: p '+pv(get('levels',outcome='TBU_FB',factor='TC')['p_holm_both']))")
src=src.replace("a.set_ylim(1,3.8);a.set_yticks([1,2,3])","a.set_ylim(2,6.2);a.set_yticks([2,4,6])")
src=src.replace("'Adjusted TBU'","'First-belief TBU'")
src=src.replace("ha='center',fontsize=6.8,color=INK)","ha='left' if xx==0 else 'center',fontsize=6.8,color=INK)")
src=src.replace("DGC level difference: Holm p = .115","DGC level difference: Holm p = .272")
src=src.replace("(2,'TBU_article',ORANGE),(1,'PRUD3',BLUE),(0,'TBU9',TEAL)","(2,'TBU_POST',ORANGE),(1,'TBU_FB',BLUE),(0,'RBD9',TEAL)")
src=src.replace("['Strict TBU','Common 3-step','First-belief 9-step']","['Post-release TBU','First-belief TBU','First-belief RBD9']")
src=src.replace("primary_n=52","primary_n=54")
src=src.replace("D:/Codex/outputs/v7_manuscript_methods_20261030/analysis.json",str(ROOT/'analysis.json').replace('\\','/'))
src=src.replace("a.set_title('RT depends on the TBU clock'","a.set_title('RT depends on the TBU clock'")
# Primary FB means can have taller intervals, so labels need modest breathing room.
scope=dict(__file__=str(ROOT/'draw_framework_generated.py'),__name__='__main__',pv=pv,get=get)
exec(compile(src,'draw_framework_generated.py','exec'),scope)
print('Saved dual-clock results, explanation and updated three-column framework.')
