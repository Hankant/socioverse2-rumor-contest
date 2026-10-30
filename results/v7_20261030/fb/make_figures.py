from pathlib import Path
import sys,json,shutil
ROOT=Path(__file__).resolve().parent;OUT=ROOT/'figures';OUT.mkdir(exist_ok=True)
sys.path.append('D:/Program Files/Python312/Lib/site-packages')
import numpy as np,matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
for fn in ['arial.ttf','arialbd.ttf','times.ttf','timesbd.ttf']:font_manager.fontManager.addfont('C:/Windows/Fonts/'+fn)
plt.rcParams.update({'font.family':'Arial','font.size':9,'axes.spines.top':False,'axes.spines.right':False,'pdf.fonttype':42,'svg.fonttype':'none','axes.unicode_minus':False})
A=json.loads((ROOT/'analysis_FB.json').read_text(encoding='utf-8'));T=A['tables']
BLUE='#426D8A';TEAL='#44847D';ORANGE='#B27B4D';PURPLE='#84759A';GREY='#74818B';INK='#263744'
get=lambda name,**kw:next(r for r in T[name] if all(r.get(k)==v for k,v in kw.items()))
pv=lambda p:'< .001' if p<.001 else '= '+f'{p:.3f}'
N={'RT':'Response timing','TC':'Targeting capacity','GC':'Government credibility','DGC':'Degree of group cocooning'}
def save(fig,stem):
    for ext in ['png','svg','pdf']:fig.savefig(OUT/(stem+'.'+ext),dpi=600,facecolor='white')
    fig.savefig(OUT/(stem+'_preview.png'),dpi=200,facecolor='white');plt.close(fig)
shutil.copy2(Path('D:/Codex/outputs/v7_report_update_20261030/figures/Figure1_network_access.png'),OUT/'Figure1_network_access.png')
fig,axs=plt.subplots(2,2,figsize=(6.8,3.8),layout='constrained')
for a,f in zip(axs.flat,N):
    rs=sorted([r for r in T['means'] if r['factor']==f],key=lambda r:r['level']);x=np.arange(len(rs));y=np.array([r['estimate'] for r in rs]);lo=np.array([r['ci_low']for r in rs]);hi=np.array([r['ci_high']for r in rs])
    a.errorbar(x,y,yerr=[y-lo,hi-y],fmt='o-',color=TEAL,ms=4,capsize=3,lw=1.2)
    a.set_xticks(x,[f"{r['level']:g}" for r in rs]);a.set_xlim(-.2,len(rs)-.8);a.set_ylim(min(0,min(lo)-.2),max(hi)+.6);a.grid(axis='y',alpha=.18)
    a.set_title(N[f]+'\nAdjusted p '+pv(get('levels',factor=f)['p_holm_both']),loc='left',fontsize=10,weight='bold')
    a.set_ylabel('Adjusted TBU (steps)',fontsize=8)
    for xx,yy,upper in zip(x,y,hi):a.annotate(f'{yy:.2f}',(xx,upper),xytext=(0,4),textcoords='offset points',ha='center',fontsize=8)
save(fig,'Figure3_FB_level_differences')
fig,axs=plt.subplots(2,2,figsize=(6.8,3.7),layout='constrained')
for a,f in zip(axs.flat,['RT','TC','GC']):
    rs=sorted([r for r in T['conditional']if r['factor']==f],key=lambda r:r['DGC']);x=[r['DGC']for r in rs];y=np.array([r['estimate']for r in rs]);lo=np.array([r['ci_low']for r in rs]);hi=np.array([r['ci_high']for r in rs])
    a.errorbar(x,y,yerr=[y-lo,hi-y],fmt='o-',color=TEAL,ms=4,capsize=3,lw=1.1);a.axhline(0,color=GREY,ls='--',lw=.7)
    a.set_xticks([0,.2,.4]);a.set_xlim(-.03,.43);a.set_xlabel('DGC',fontsize=8);a.set_ylabel('TBU difference (steps)',fontsize=8);a.grid(axis='y',alpha=.17)
    a.set_title({'RT':'RT +1 step','TC':'TC .80 minus .20','GC':'GC +.25'}[f],loc='left',weight='bold',fontsize=10)
    a.text(.02,.04,'Interaction p '+pv(get('interactions',factor=f)['p_holm_both']),transform=a.transAxes,fontsize=8,bbox=dict(fc='white',ec='none',pad=1))
a=axs.flat[3]
for y,f,c in [(2,'RT',BLUE),(1,'TC',TEAL),(0,'GC',ORANGE)]:
    r=get('did',factor=f);a.errorbar(r['estimate'],y,xerr=[[r['estimate']-r['ci_low']],[r['ci_high']-r['estimate']]],fmt='o',color=c,ms=4,capsize=3,lw=1.1)
    a.text(3.0,y,'p '+pv(r['p_holm_both']),ha='right',va='center',fontsize=8,color=GREY)
a.set_yticks([2,1,0],['RT','TC','GC']);a.axvline(0,color=GREY,ls='--',lw=.7);a.set_xlim(-2.3,3.1);a.set_xticks([-2,0,2]);a.set_ylim(-.6,2.6);a.set_xlabel('Difference in effects (steps)',fontsize=8)
a.set_title('High minus low effects: DGC .4 vs 0',loc='left',fontsize=9,weight='bold')
save(fig,'Figure4_FB_moderation')
# FB-only illustration: it contains no alternative timing endpoint or follow-up window.
fig,a=plt.subplots(figsize=(6.8,1.2),layout='constrained');a.set_xlim(0,10);a.set_ylim(-.3,1.45);a.set_yticks([]);a.set_xticks(range(11));a.tick_params(axis='x',labelsize=8);a.set_xlabel('Simulation round',fontsize=8)
for x,label in [(1,'First belief\nb = 1'),(2,'Official release\nRT = 2'),(5,'First rejection\nr = 5')]:
    a.vlines(x,-.05,.9,color=GREY,ls=':',lw=.7);a.text(x,.98,label,ha='center',va='bottom',fontsize=7.2)
a.annotate('',(5,.32),(1,.32),arrowprops={'arrowstyle':'<->','lw':1.8,'color':TEAL});a.text(3,.55,'TBU = r − b = 5 − 1 = 4 steps',ha='center',fontsize=8.5,color=TEAL)
save(fig,'Figure5_FB_time_origin')
# Reuse the original editable vector portrait functions, rather than raster edits.
helper=Path('D:/Codex/outputs/v7_triptych_20261030/draw_triptych.py').read_text(encoding='utf-8').split('fig,ax=canvas()')[0]
helper=helper.replace("T=json.loads(Path('D:/Codex/outputs/v7_manuscript_methods_20261030/analysis.json').read_text(encoding='utf-8'))['tables']",'')
ns={'__file__':str(ROOT/'draw_helpers.py')};exec(compile(helper,'draw_helpers.py','exec'),ns)
canvas,tx,box,arrow,banner,actor=[ns[k]for k in ['canvas','tx','box','arrow','banner','actor']]
from matplotlib.patches import Rectangle,Ellipse
W,H=240,150;fig,ax=canvas()
for x,w,col in [(1,77,'#FDF5F5'),(81,77,'#F5F6F7'),(161,78,'#F2F8F7')]:box(ax,x,11,w,138,fill=col,edge='#DAE0E4',radius=.6,lw=.5)
banner(ax,1,77,'I  Model design framework','#E7BCBC');banner(ax,81,77,'II  Agent design and simulation','#C4C7CA');banner(ax,161,78,'III  Results and inference','#B7D1CE')
box(ax,6,19,66,20)
for j in [2,1,0]:ax.add_patch(Rectangle((10+j*.9,23-j*.7),9.2,11,fc='white',ec='#B7C5CF',lw=.6,zorder=4))
for j in range(4):ax.plot([12,17.5],[25+j*2,25+j*2],color=[BLUE,ORANGE,TEAL,GREY][j],lw=.8,zorder=6)
tx(ax,45.5,24,'Freeze case and population',size=8.3,bold=True);tx(ax,45.5,32,'One allegation + official response\nSynthetic profiles; fixed network',size=7.7);arrow(ax,[(39,39),(39,43)])
tx(ax,39,46,'Tested associations and moderation',size=8.1,bold=True)
for y,text,c in [(58,'Response timing\n(RT)',BLUE),(71,'Targeting capacity\n(TC)',TEAL),(84,'Government credibility\n(GC)',ORANGE)]:
    box(ax,6,y-5,31,10,edge=c,radius=.7);tx(ax,21.5,y,text,size=7.2 if y==84 else 7.8,bold=True,color=c);arrow(ax,[(37,y),(47,79)],color=c)
box(ax,43,53,31,11,fill='#F1EDF5',edge=PURPLE,radius=.7);tx(ax,58.5,58.5,'Degree of group\ncocooning (DGC)',size=7.5,bold=True,color=PURPLE)
ax.add_patch(Ellipse((61,79),28,18,fc='#ECF3F8',ec=BLUE,lw=.8,zorder=5));tx(ax,61,79,'Time of belief\nupdating (TBU)',size=8.3,bold=True,color=BLUE)
arrow(ax,[(43,58.5),(40,58.5),(40,82.5),(43,82.5)],color=PURPLE,dash=True,head=4);arrow(ax,[(40,64.3),(43,64.3)],color=PURPLE,dash=True,head=4);arrow(ax,[(40,73.4),(43,73.4)],color=PURPLE,dash=True,head=4)
tx(ax,39,94,'Moderation: DGC × RT, TC and GC',size=7.2,color=PURPLE);tx(ax,39,99,'54-cell controlled factorial design',size=8.5,bold=True)
cards=[(6,104,'Response timing\n(RT)',['Low','Medium','High'],['2','4','7'],BLUE),(40.5,104,'Targeting capacity\n(TC)',['Low','High'],['.20','.80'],TEAL),
       (6,122,'Government credibility\n(GC)',['Low','Medium','High'],['.25','.50','.75'],ORANGE),(40.5,122,'Degree of group\ncocooning (DGC)',['Low','Medium','High'],['0','.20','.40'],PURPLE)]
for x,y,title,labs,vals,c in cards:
    box(ax,x,y,31.5,15,edge='#D5DDE2',radius=.6);tx(ax,x+15.75,y+3.3,title,size=7.2,bold=True,color=c)
    xs=np.linspace(x+5.4,x+26.1,len(labs))
    for xx,lab,val in zip(xs,labs,vals):tx(ax,xx,y+9,lab,size=6.3,color=GREY);tx(ax,xx,y+12.6,val,size=7.4)
box(ax,6,141,66,5.2,fill='#EAEFF3',edge='#C4D1DA',radius=.7);tx(ax,39,143.6,'300 LLM users · 54 scenarios × 10 rounds',size=7.6,bold=True);tx(ax,39,148,'One stochastic trajectory per parameter cell',size=6.8,color=GREY)
for cx,kind,name,count in [(90,'source','Rumor\nblogger','SOURCE'),(108.5,'inside','Inside\nrumor cocoon\nusers','n = 48'),(127,'outside','Outside\nrumor cocoon\nusers','n = 252'),(146,'government','Government\naccount','50 recipients')]:
    actor(ax,cx,26,kind,.9);tx(ax,cx,39,name,size=7.1,bold=True);tx(ax,cx,46,count,size=7,color=GREY)
box(ax,86,50,67,12,edge='#D6DEE3',radius=.6);tx(ax,119.5,56,'Demographics · MBTI · trust · habits\nPrior score · 3-step memory · actual exposure',size=7.8)
flow=[(68,13,'Begin round t','Retain the previous 3 rounds\nPublish the official response if t = RT'),(86,14,'Construct the visible feed','Following, reposts and revisits\n≤30 earlier comments per visible root'),
      (106,14,'LLM-Agent decision','Integrate all 11 assigned conditions\nScore, comment and repost choices'),(126,14,'Record decisions and update states','Store b and r; TBU = r − b (r ≥ RT)\nSocial actions become visible at t + 1')]
for y,h,title,body in flow:box(ax,88,y,64,h,edge='#A9B8C2',radius=.7);tx(ax,120,y+3.1,title,size=8.1,bold=True);tx(ax,120,y+9.1,body,size=7.5)
for start,end in [(62,68),(81,86),(100,106),(120,126)]:arrow(ax,[(120,start),(120,end)],color=BLUE)
arrow(ax,[(88,133),(83.5,133),(83.5,74),(88,74)],dash=True,head=5);tx(ax,83.5,105,'t ← t + 1',size=7,color=GREY,rotation=90,bbox=dict(fc='#F5F6F7',ec='none',pad=.7));tx(ax,120,147,'Publishers are scripted; audience users call the LLM.',size=7,color=GREY)
box(ax,166,19,68,12,edge='#BDD4D0',radius=.6);tx(ax,200,23.2,'First-belief TBU = r − b',size=9,bold=True);tx(ax,200,28,'HC3 OLS + F / t tests + Holm',size=8.3,bold=True)
tx(ax,200,36,'54 scenario means · 757 observed updates',size=7.7,color=GREY);tx(ax,200,42,'DGC level difference: adjusted p = .272',size=7.4,color=GREY)
def axesmm(x,y,w,h):
    a=fig.add_axes([x/W,1-(y+h)/H,w/W,h/H]);a.tick_params(labelsize=6.7,length=2.5,width=.5,pad=2);a.grid(axis='y',color='#E4EBEE',lw=.5)
    for side in ['left','bottom']:a.spines[side].set_color('#6B7C86')
    return a
def meansplot(a,f,col):
    rs=sorted([r for r in T['means']if r['factor']==f],key=lambda r:r['level']);x=np.arange(len(rs));y=np.array([r['estimate']for r in rs]);lo=np.array([r['ci_low']for r in rs]);hi=np.array([r['ci_high']for r in rs])
    a.errorbar(x,y,yerr=[y-lo,hi-y],fmt='o-',color=col,ms=3,capsize=2,lw=1)
    a.set_xticks(x,[f"{r['level']:g}"for r in rs]);a.set_xlim(-.15,len(rs)-.85)
    for xx,yy,upper in zip(x,y,hi):a.annotate(f'{yy:.2f}',(xx,upper),xytext=(0,3),textcoords='offset points',ha='left' if xx==0 else 'center',fontsize=6.7,color=INK)
for x,f,col in [(165,'GC',TEAL),(202,'TC',BLUE)]:
    box(ax,x,49,35,45,edge='#CDDCDD',radius=.7);tx(ax,x+17.5,54,N[f],size=7.5,bold=True);tx(ax,x+17.5,59,f'({f}): p < .001',size=7.8,bold=True)
    a=axesmm(x+7,67,26,21);meansplot(a,f,col);a.set_ylim(2,6.4);a.set_yticks([2,4,6]);a.set_ylabel('Adjusted TBU',fontsize=6.7,labelpad=1)
box(ax,165,99,35,46,edge='#CDDCDD',radius=.7);tx(ax,182.5,104,'Cocooning interactions',size=7.6,bold=True);tx(ax,182.5,110,'All adjusted p > .81',size=7,color=GREY)
a=axesmm(174,116,24,23)
for y,f,c in [(2,'RT',BLUE),(1,'TC',TEAL),(0,'GC',ORANGE)]:
    r=get('did',factor=f);a.errorbar(r['estimate'],y,xerr=[[r['estimate']-r['ci_low']],[r['ci_high']-r['estimate']]],fmt='o',color=c,ms=3,capsize=2,lw=1)
a.set_yticks([2,1,0],['RT','TC','GC']);a.set_ylim(-.6,2.6);a.set_xlim(-2.3,2.4);a.set_xticks([-2,0,2]);a.axvline(0,color=GREY,ls='--',lw=.6);a.set_xlabel('Effect difference (steps)',fontsize=6.4,labelpad=1)
box(ax,202,99,35,46,edge='#CDDCDD',radius=.7);tx(ax,219.5,104,'Response timing (RT)',size=7.6,bold=True);tx(ax,219.5,110,'Adjusted p < .001',size=7.1,color=GREY)
a=axesmm(209,117,26,22);meansplot(a,'RT',BLUE);a.set_ylim(0,8);a.set_yticks([2,4,6,8]);a.set_ylabel('Adjusted TBU',fontsize=6.6,labelpad=1);a.set_xlabel('Release round',fontsize=6.6,labelpad=1)
save(fig,'Figure2_FB_framework')
(ROOT/'figure_manifest.json').write_text(json.dumps(dict(data_source=str(ROOT/'analysis_FB.json'),endpoint='FB only',png_dpi=600,framework_size_mm=[240,150],original_vector_role_illustrations=True,api_calls=0),indent=2),encoding='utf-8')
print('Created five figures, including FB-only framework and time-origin illustration.')
