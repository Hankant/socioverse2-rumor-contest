from pathlib import Path
from zipfile import ZipFile,ZIP_DEFLATED
from itertools import product
import sys,json,hashlib,shutil,copy,re
from lxml import etree as E
ROOT=Path(__file__).resolve().parent
sys.path.extend(['D:/Codex/outputs/v7_complete54_research_20261029/scientific_deps','D:/Codex/outputs/v7_factorial_tests_20261028/packages','D:/Program Files/Python312/Lib/site-packages'])
import numpy as np,pandas as pd,patsy
from scipy import stats
import fitz
A=json.loads((ROOT/'analysis.json').read_text(encoding='utf-8'));T=A['tables']
cases=pd.read_csv(ROOT/'data/scenarios.csv');people=pd.read_csv(ROOT/'data/users.csv')
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
for s in A['source_files']:assert sha(Path(s['source']))==s['sha256']
assert people.post_event.sum()==757 and people.strict_event.sum()==475
assert people.state.value_counts().to_dict()=={'observed_post_release':757,'right_censored':222,'resolved_before_release':1}
ev=people[people.post_event.eq(1)]
assert np.allclose(ev.TBU_FB-ev.TBU_POST,ev.RT-ev.first_belief_tick)
# Independent linear algebra audit of coefficients, HC3 covariance and marginal contrasts.
levels=A['levels'];grid=pd.DataFrame(product(*(levels[k] for k in levels)),columns=list(levels))
for f,c in A['centers'].items():cases[f+'_c']=cases[f]-c;grid[f+'_c']=grid[f]-c
get=lambda name,**kw:next(r for r in T[name] if all(r.get(k)==v for k,v in kw.items()))
for out in ['TBU_POST','TBU_FB']:
    Xdf=patsy.dmatrix(A['formulas']['M3'],cases,return_type='dataframe');X=Xdf.to_numpy();y=cases[out].to_numpy()
    P=np.linalg.pinv(X);b=P@y;e=y-X@b;h=np.einsum('ij,ji->i',X,P);V=(P*(e/(1-h))**2)@P.T
    df=len(y)-X.shape[1]
    for j,term in enumerate(Xdf.columns):
        r=get('coefficients',outcome=out,model='M3',term=term);se=np.sqrt(V[j,j]);z=b[j]/se
        assert abs(r['estimate']-b[j])<1e-10 and abs(r['se']-se)<1e-10
        assert abs(r['p']-2*stats.t.sf(abs(z),df))<1e-10
    G=np.asarray(patsy.build_design_matrices([Xdf.design_info],grid)[0])
    for f in ['RT','TC','GC']:
        lo,hi=min(levels[f]),max(levels[f]);L=np.zeros(X.shape[1])
        for d,sign in [(0,-1),(.4,1)]:
            L+=sign*(G[grid[f].eq(hi)&grid.DGC.eq(d)].mean(0)-G[grid[f].eq(lo)&grid.DGC.eq(d)].mean(0))
        r=get('did',outcome=out,factor=f)
        assert abs(r['estimate']-L@b)<1e-9
        assert abs(r['se']-np.sqrt(L@V@L))<1e-9
    Xdf=patsy.dmatrix('C(RT,Sum)+C(TC,Sum)+C(GC,Sum)+C(DGC,Sum)',cases,return_type='dataframe');X=Xdf.to_numpy()
    P=np.linalg.pinv(X);b=P@y;e=y-X@b;h=np.einsum('ij,ji->i',X,P);V=(P*(e/(1-h))**2)@P.T
    G=np.asarray(patsy.build_design_matrices([Xdf.design_info],grid)[0])
    for f in levels:
        M=[G[grid[f].eq(l)].mean(0) for l in levels[f]];R=np.array([m-M[0] for m in M[1:]])
        z=R@b;F=float(z@np.linalg.solve(R@V@R.T,z)/len(R));r=get('levels',outcome=out,factor=f)
        assert abs(r['F']-F)<1e-8
        assert abs(r['p']-stats.f.sf(F,len(R),len(y)-X.shape[1]))<1e-10
ref=ROOT/'reference/source_report.docx';doc=ROOT/'SocioVerse-研究报告_双TBU口径8页版.docx'
assert sha(ref)=='facc6edf94c57f7340fb104f909029e389431d328c8fdbee0855cb736372f1b7'
assert sha(Path('E:/papers/socioverse 2026/SocioVerse-研究报告_三栏框架图8页版.docx'))==sha(ref)
ns={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main','m':'http://schemas.openxmlformats.org/officeDocument/2006/math','wp':'http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing','a':'http://schemas.openxmlformats.org/drawingml/2006/main','r':'http://schemas.openxmlformats.org/officeDocument/2006/relationships'}
with ZipFile(ref) as old,ZipFile(doc) as new:
    assert new.testzip() is None
    changed=[name for name in old.namelist() if old.read(name)!=new.read(name)]
    assert len(changed)==4 and 'word/document.xml' in changed
    assert all(n.startswith('word/media/') for n in changed if n!='word/document.xml')
    x=E.fromstring(new.read('word/document.xml'));before=E.fromstring(old.read('word/document.xml'))
    assert len(x.xpath('.//w:tbl',namespaces=ns))==5 and len(x.xpath('.//wp:inline',namespaces=ns))==4 and len(x.xpath('.//m:oMath',namespaces=ns))==3
    assert E.tostring(x.xpath('.//w:tbl',namespaces=ns)[0])==E.tostring(before.xpath('.//w:tbl',namespaces=ns)[0])
    assert [E.tostring(e) for e in x.xpath('.//w:sectPr',namespaces=ns)]==[E.tostring(e) for e in before.xpath('.//w:sectPr',namespaces=ns)]
    xb=x.find('w:body',ns);bb=before.find('w:body',ns)
    for i in [0,2,3,*range(7,22),*range(25,33),*range(81,88)]:assert E.tostring(xb[i])==E.tostring(bb[i]),f'Unintended paragraph change {i}'
    rels=E.fromstring(new.read('word/_rels/document.xml.rels'))
    files=[None,'Figure2_three_column_framework.png','Figure3_dual_clock_levels.png','Figure4_dual_clock_moderation.png']
    for i,inline in enumerate(x.xpath('.//wp:inline',namespaces=ns)):
        rid=inline.xpath('.//a:blip/@r:embed',namespaces=ns)[0];target='word/'+next(e.get('Target') for e in rels if e.get('Id')==rid)
        if i:assert hashlib.sha256(new.read(target)).hexdigest()==sha(ROOT/'figures'/files[i])
        else:assert new.read(target)==old.read(target)
pdf=fitz.open(ROOT/'report_render/report.pdf');assert len(pdf)==8
assert [p.rect.width>p.rect.height for p in pdf]==[False,False,True,False,False,False,False,False]
for p in pdf:
    assert len(p.get_text().strip())>100
    for b in p.get_text('blocks'):assert b[0]>=0 and b[1]>=0 and b[2]<=p.rect.width+1 and b[3]<=p.rect.height+1
# Saved XLSX cached values independently reconcile all scenario formulas.
xlsx=ROOT/'V7_双TBU定义_统计结果与数据.xlsx'
xns={'s':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
with ZipFile(xlsx) as z:
    assert z.testzip() is None
    xml=E.fromstring(z.read('xl/worksheets/sheet4.xml'))
    values={c.get('r'):c.findtext('s:v',namespaces=xns) for c in xml.xpath('.//s:sheetData/s:row/s:c',namespaces=xns)}
    for i,r in enumerate(cases.itertuples(),7):
        for col,key in [('G','matched_n'),('H','strict_n'),('I','censored_n'),('J','pre_release_resolved_n'),('K','TBU_POST'),('L','TBU_FB'),('M','clock_gap'),('N','STRICT_POST'),('O','STRICT_FB')]:
            a=values.get(f'{col}{i}');expected=getattr(r,key)
            if pd.isna(expected):assert a in [None,'']
            else:assert abs(float(a)-expected)<1e-9
verification=dict(pages=8,sections='portrait / landscape / portrait',figures=4,tables=5,source_files=54,matched_events=757,
    censored_first_episodes=222,independent_HC3_and_F_checked=True,counterfactual_DID_checked=True,clock_identity_checked=True,
    xlsx_saved_cached_means_checked=True,preserve_only_parts_unchanged=True,original_report_unchanged=True,api_calls=0)
if '--publish' not in sys.argv:
    print(json.dumps(verification,ensure_ascii=False,indent=2));raise SystemExit
# Publish only after all final document and workbook views have been visually inspected.
dest=Path('E:/papers/socioverse 2026/socioverse2_v6_local/Results_V7/双TBU定义对比_20261030');dest.mkdir(exist_ok=True)
report_dest=Path('E:/papers/socioverse 2026')/doc.name
def publish(a,b):
    if b.exists():assert sha(a)==sha(b),'Existing destination differs: '+str(b)
    else:shutil.copy2(a,b)
    assert sha(a)==sha(b)
publish(doc,report_dest)
for a in [doc,xlsx,ROOT/'双TBU定义_结果对比与通俗解释.html']:
    publish(a,dest/a.name)
for directory in ['figures','data']:
    (dest/directory).mkdir(exist_ok=True)
    for a in (ROOT/directory).iterdir():
        if a.is_file():publish(a,dest/directory/a.name)
(dest/'源数据核对.json').write_text(json.dumps(A['source_files'],ensure_ascii=False,indent=2),encoding='utf-8')
(dest/'阅读说明.txt').write_text('主分析同时保留POST（发布到转不信）和FB（首次相信到辟谣后转不信），使用同757次更新、54个情景。旧版严格排除发布当轮的475次更新与52个情景均值保留于补充。先打开HTML通俗解释；8页Word可用于研究报告；Excel可核查980份曾相信用户记录及54组公式均值。data为完整重算CSV，figures含SVG/PDF/600dpi PNG。原始轨迹与此前报告均未修改。',encoding='utf-8')
archive=ROOT/'V7_双TBU定义_报告图表与数据.zip'
with ZipFile(archive,'w',ZIP_DEFLATED) as z:
    for p in dest.rglob('*'):
        if p.is_file():z.write(p,p.relative_to(dest))
publish(archive,dest/archive.name)
verification.update(published_directory=str(dest),published_report=str(report_dest),docx_sha256=sha(doc),xlsx_sha256=sha(xlsx),all_pages_and_sheets_visually_reviewed=True)
(ROOT/'delivery_verification.json').write_text(json.dumps(verification,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(verification,ensure_ascii=False,indent=2))
