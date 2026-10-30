from pathlib import Path
from zipfile import ZipFile,ZIP_DEFLATED
from lxml import etree as E
import copy,json,hashlib,shutil
ROOT=Path(__file__).resolve().parent
SOURCE=Path('E:/papers/socioverse 2026/SocioVerse-研究报告_三栏框架图8页版.docx')
REF=ROOT/'reference/source_report.docx';REF.parent.mkdir(exist_ok=True)
assert hashlib.sha256(SOURCE.read_bytes()).hexdigest()=='facc6edf94c57f7340fb104f909029e389431d328c8fdbee0855cb736372f1b7'
shutil.copy2(SOURCE,REF)
A=json.loads((ROOT/'analysis.json').read_text(encoding='utf-8'));T=A['tables'];S=A['summary']
NS={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main','m':'http://schemas.openxmlformats.org/officeDocument/2006/math',
    'a':'http://schemas.openxmlformats.org/drawingml/2006/main','wp':'http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing',
    'r':'http://schemas.openxmlformats.org/officeDocument/2006/relationships'}
q=lambda name:'{'+NS[name.split(':')[0]]+'}'+name.split(':')[1]
get=lambda key,**kw:next(r for r in T[key] if all(r.get(k)==v for k,v in kw.items()))
pv=lambda p:'<.001' if p<.001 else f'{p:.3f}'
ci=lambda r:f"[{r['ci_low']:.3f}, {r['ci_high']:.3f}]"
with ZipFile(REF) as z:parts={name:z.read(name) for name in z.namelist()}
xml=E.fromstring(parts['word/document.xml']);body=xml.find('w:body',NS);original=list(body)
def replace(p,text):
    for e in list(p):
        if e.tag!=q('w:pPr'):p.remove(e)
    r=E.SubElement(p,q('w:r'));pr=E.SubElement(r,q('w:rPr'))
    # Reuse the preceding body role through its paragraph style and original run size.
    oldrpr=run_properties.get(id(p))
    if oldrpr is not None:r.replace(pr,copy.deepcopy(oldrpr))
    for i,line in enumerate(str(text).split('\n')):
        if i:E.SubElement(r,q('w:br'))
        t=E.SubElement(r,q('w:t'));t.set('{http://www.w3.org/XML/1998/namespace}space','preserve');t.text=line
run_properties={id(p):copy.deepcopy(p.find('w:r/w:rPr',NS)) for p in original if p.tag==q('w:p') and p.find('w:r/w:rPr',NS) is not None}
def put(i,text):replace(original[i],text)
put(1,'Completed factorial simulation comparing two definitions of belief updating time')
put(5,'Government corrections compete with rumor sources in uneven information networks. We compare response timing (RT), targeting capacity (TC) and government credibility (GC), and test moderation by degree of group cocooning (DGC), in 54 completed SocioVerse V7 scenarios with 300 LLM users and ten rounds each. Two TBU clocks are retained: government publication to first qualifying rejection (POST), and first belief to that same rejection (FB). Both use 757 observed transitions at or after publication and yield 54 scenario means. Mean POST and FB TBU are 1.51 and 4.56 steps. HC3-robust level tests with Holm correction across both endpoints support TC and GC differences. RT strongly differs under FB (p<.001); its POST result is borderline after joint correction (p=.051). DGC level effects and all three moderation terms are unsupported under either clock. FB includes time spent awaiting official publication, so a positive RT association concerns total belief duration, not slower processing after correction. Unresolved episodes are censored, and observed-converter means do not represent all believers. A common follow-up check and a fixed initial-believer cohort support interpretation. Single runs per cell, synthetic profiles, an uncalibrated case and no no-response control limit causal and population claims.')
put(23,'Figure 2  Integrated framework with two TBU clocks. Right: FB level means, FB interaction contrasts, and RT coefficients under POST, FB and initial-cohort RBD9. Interaction contrasts compare high-minus-low effects between DGC=.4 and 0 (RT 7−2, TC .8−.2, GC .75−.25). Whiskers are pointwise HC3 95% intervals. Level p values use Holm8 and interaction p values Holm6 across the two main endpoints. SOURCE and GOVERNMENT are scripted publishers.')
put(33,'Let b denote a user’s first observed belief round, RT the government publication round, and r the first observed belief-to-rejection transition at or after RT. Publication precedes decisions within its round, so same-round transitions qualify. We retain two clocks on the identical eligible users:')
put(35,'Each scenario averages the two intervals over the same eligible users. Never-believers have no TBU. Unresolved first episodes are right-censored at round 10; a user who resolved before publication is excluded from the matched endpoints.')
put(36,'Table 2  Two TBU clocks and supplementary endpoints')
put(38,'POST and FB use the same 757 transitions. The strict legacy analysis excludes 282 publication-round updates; its two undefined scenario means remain missing. No result is interpolated.')
put(39,'Scenario means are equally weighted. M1 includes numeric RT, TC and GC; M2 adds DGC; M3 adds DGC interactions with RT, TC and GC. Variables are centered at RT=13/3, TC=GC=.5 and DGC=.2. HC3 t/F inference is exploratory. Categorical level F tests and numeric linear-slope t tests have different null hypotheses. Joint Holm families cover eight level tests, twenty pairwise contrasts, eight numeric main slopes and six interactions across the two main clocks; within-clock corrections are also supplied. All 95% intervals are pointwise. Supplementary restricted durations address unresolved outcomes [6].')
put(42,'All 54 scenarios completed ten rounds (540/540). Among 16,200 user-scenario instances, 980 ever believed: 757 first updates occurred at or after publication, 222 first episodes remained unresolved, and one resolved earlier. Of the 757 qualifying updates, 282 occurred in the publication round and 475 later. Equal-scenario mean TBU is 1.512 steps for POST and 4.557 for FB; event-weighted means are 1.472 and 4.428. The former means are used for scenario-level inference.')
put(44,'Figure 3  Adjusted TBU under the two clocks. Top: POST; bottom: FB. Means are standardized equally over the complete factorial grid using separate categorical additive models (54 observations each). Error bars are pointwise HC3 95% intervals. Panel p values use Holm correction across eight omnibus tests for both endpoints.')
put(45,'Table 3  Factor-level tests and high-minus-low contrasts under both clocks')
put(47,'F tests use df=(2,46), except TC=(1,46); p in the F columns is joint Holm8. Contrasts are RT 7−2, TC .8−.2, GC .75−.25 and DGC .4−0; the last column gives joint Holm20 p. Confidence intervals are pointwise. Models adjust for all other categorical factors.')
rp=get('pairs',outcome='TBU_POST',factor='RT',low=2,high=7);rf=get('pairs',outcome='TBU_FB',factor='RT',low=2,high=7)
tc=get('pairs',outcome='TBU_FB',factor='TC',low=.2,high=.8);gc=get('pairs',outcome='TBU_FB',factor='GC',low=.25,high=.75)
put(48,f"RT=7 versus 2 changes adjusted POST TBU by {rp['estimate']:.3f} steps but FB TBU by +{rf['estimate']:.3f}. Under FB, higher TC corresponds to {tc['estimate']:.3f} steps and higher GC to {gc['estimate']:.3f} steps. TC and GC level differences survive correction across both clocks. DGC does not. The opposite RT directions follow from the clocks’ different starting points and cannot be described as contradictory estimates of one outcome.")
bp=get('blocks',outcome='TBU_POST',block='M3');bf=get('blocks',outcome='TBU_FB',block='M3')
put(51,f"Adding the three DGC interactions to M2 gives a joint HC3 F(3,46)={bp['F']:.3f}, p={pv(bp['p'])} for POST and F(3,46)={bf['F']:.3f}, p={pv(bf['p'])} for FB. None of the separate interaction tests survives the joint six-test Holm correction. Improved fit or different-looking within-DGC slopes does not itself establish moderation.")
put(53,'Figure 4  Conditional effects under POST (top) and FB (bottom). Columns show RT+1 step, TC .80−.20 and GC+.25 at DGC=0, .2 and .4. Error bars are pointwise HC3 95% intervals. Interaction p values are adjusted across the six terms under both clocks. Within-stratum significance is distinct from an interaction test.')
put(54,'Table 4  Numeric M3 coefficients under both clocks')
put(56,'N=54; residual df=46. Main slopes are conditional on DGC=.20 and other centered variables; TC, GC and DGC coefficients are per 1.0-unit change. Last-column p values use joint Holm8 for the four main slopes across clocks and Holm6 for interactions. All intervals are pointwise.')
dp=get('did',outcome='TBU_POST',factor='GC');df=get('did',outcome='TBU_FB',factor='GC')
put(57,f"For the GC .75−.25 contrast, the estimated change in its effect between DGC=.4 and 0 is {dp['estimate']:.3f} steps under POST ({ci(dp)}) and {df['estimate']:.3f} under FB ({ci(df)}). Both intervals include zero. The corresponding RT and TC differences also remain uncertain. Fully categorical interaction tests provide no corrected evidence of moderation under either clock.")
put(59,'7 Timing definitions follow-up and interpretation')
put(60,'The two clocks satisfy an exact identity for each included user: FB−POST=RT−b. Thus FB includes the interval spent believing before government publication, while POST starts at publication. Changing the starting point changes the policy quantity being measured. Among matched converters, the mean difference between clocks is 3.045 steps. Neither mean includes the 222 unresolved first episodes, so neither is an unrestricted all-believer mean.')
put(61,'Table 5  Clock and inclusion sensitivity using the same numeric M3 specification')
put(63,'Rows1–2 are the paired main endpoints; rows3–4 preserve the strict legacy inclusion rule. RBD9 uses 911 step-1 believer instances and a nine-step cap. PRUD3 uses believers immediately before release and a three-step post-release cap. Supplementary rows use within-endpoint Holm4, while the paired main rows use joint Holm8. Different cohorts are explicitly distinguished.')
put(64,'What a common three-step window means')
put(65,'RT=2, 4 and 7 leave eight, six and three post-release steps before round 10. The optional common-window check observes only the first three steps after each release: rounds3–5, 5–7 and 8–10. It does not redefine either TBU. A publication-round update has zero POST waiting; an update by the third later round contributes its waiting time, and no update within that interval contributes the three-step cap.')
put(66,'Why the RT result changes')
put(67,'Most observed believers first believe early. Delaying publication therefore adds time to FB before a qualifying post-release update can occur. This is a meaningful component of total belief duration, but it does not show that late corrections take longer to process after receipt. POST can instead shorten with later release because only fast, observed converters remain within the shorter follow-up horizon.')
put(68,'The fixed initial-believer check, RBD9, retains unfinished episodes through the nine-step restriction. It avoids dropping them from the mean but concerns 47 distinct inside-user IDs across scenarios. It cannot establish outside-user effects. PRUD3 concerns a different pre-release cohort; it is a sensitivity check rather than a competing primary definition.')
put(69,'Endpoint choice and policy interpretation')
put(70,'Use FB when the question is total duration from initial acceptance to the observed update; use POST when it is elapsed time after government publication among observed converters. Retain both with these labels. Government credibility and more inside-directed targeting are consistently associated with shorter intervals in this simulation. DGC moderation remains unsupported. The endpoint should follow the research question, with all analyses retained rather than selected by their smallest p value.')
put(77,'One stochastic trajectory per cell cannot identify within-cell Monte Carlo variation. The 757 matched transitions produce 54 scenario means, not 757 independent experimental replications. HC3 inference depends on the response surface and error assumptions; shared users and networks remain dependent. Low simulated belief, synthetic personas, one scripted case and no no-response control limit external and causal interpretation. MBTI is a role-diversity convention. DGC also changes population mean SOURCE trust, so it is not a pure structural-network contrast.')
put(80,'Both TBU clocks associate greater government credibility and more inside-directed targeting with shorter observed updating intervals. First-belief TBU also shows longer total duration under later publication, which includes the wait for the response itself. No corrected DGC moderation is established. Further validation should retain unresolved episodes, use independent replications and distinguish response publication, actual exposure and subsequent updating.')
# Replace the measurement equation in place; keep the two native repetition equations intact.
def mr(text):
    r=E.Element(q('m:r'));pr=E.SubElement(r,q('m:rPr'));E.SubElement(pr,q('m:sty')).set(q('m:val'),'p');E.SubElement(r,q('m:t')).text=text;return r
def sub(base,script,sup=None):
    z=E.Element(q('m:sSubSup') if sup else q('m:sSub'));E.SubElement(z,q('m:e')).append(mr(base));E.SubElement(z,q('m:sub')).append(mr(script))
    if sup:E.SubElement(z,q('m:sup')).append(mr(sup))
    return z
p=original[34]
for child in list(p):
    if child.tag!=q('w:pPr'):p.remove(child)
mp=E.SubElement(p,q('m:oMathPara'));om=E.SubElement(mp,q('m:oMath'))
for node in [sub('TBU','is','POST'),mr(' = '),sub('r','is'),mr(' − '),sub('RT','s'),mr(';   '),sub('TBU','is','FB'),mr(' = '),sub('r','is'),mr(' − '),sub('b','is'),mr('   ('),sub('r','is'),mr(' ≥ '),sub('RT','s'),mr(').')]:om.append(node)
# Reuse table elements and typography; change only authorized content and widths.
tables=body.findall('w:tbl',NS)
def set_table(index,headers,rows,widths=None):
    tb=tables[index];trs=tb.findall('w:tr',NS);template=copy.deepcopy(trs[1])
    for tr in trs[1:]:tb.remove(tr)
    for _ in rows:tb.append(copy.deepcopy(template))
    for tr,vals in zip(tb.findall('w:tr',NS),[headers]+rows):
        for tc,text in zip(tr.findall('w:tc',NS),vals):
            pars=tc.findall('w:p',NS)
            p=pars[0];rpr=p.find('w:r/w:rPr',NS)
            if rpr is not None:run_properties[id(p)]=copy.deepcopy(rpr)
            replace(p,text)
            for p2 in pars[1:]:tc.remove(p2)
    if widths:
        for c,w in zip(tb.find('w:tblGrid',NS),widths):c.set(q('w:w'),str(round(w*1440)))
        for tr in tb.findall('w:tr',NS):
            for tc,w in zip(tr.findall('w:tc',NS),widths):tc.find('w:tcPr/w:tcW',NS).set(q('w:w'),str(round(w*1440)))
set_table(1,['Endpoint','Population and scenario N','Clock and incomplete updates'],[
 ['POST TBU','757 matched updates; 54 means','Mean r−RT among users with first qualifying transition r≥RT.'],
 ['FB TBU','Same 757 updates; 54 means','Mean r−b using first belief as the origin and the identical endpoint.'],
 ['Strict legacy pair','475 updates; 52 means','Require r>RT under both clocks; two empty means stay undefined.'],
 ['Initial-cohort\nRBD9','911 step-1 believers; 54 means','Nine-step restricted first-episode duration; unresolved episodes contribute 9.']])
rows=[]
for f,lo,hi in [('RT',2,7),('TC',.2,.8),('GC',.25,.75),('DGC',0,.4)]:
    lp=get('levels',outcome='TBU_POST',factor=f);lf=get('levels',outcome='TBU_FB',factor=f)
    pp=get('pairs',outcome='TBU_POST',factor=f,low=lo,high=hi);pf=get('pairs',outcome='TBU_FB',factor=f,low=lo,high=hi)
    rows.append([f,f"{lp['F']:.3f}\n{pv(lp['p_holm_both'])}",f"{pp['estimate']:.3f}\n{ci(pp)}",f"{lf['F']:.3f}\n{pv(lf['p_holm_both'])}",f"{pf['estimate']:.3f}\n{ci(pf)}",pv(pp['p_holm_both'])+' /\n'+pv(pf['p_holm_both'])])
set_table(2,['Factor','POST F\nHolm p','POST contrast\n95% CI','FB F\nHolm p','FB contrast\n95% CI','Pair p\nPOST / FB'],rows,[.5,.85,1.7,.85,1.7,1.15])
rows=[]
for term in ['RT_c','TC_c','GC_c','DGC_c','DGC_c:RT_c','DGC_c:TC_c','DGC_c:GC_c']:
    pp=get('coefficients',outcome='TBU_POST',model='M3',term=term);pf=get('coefficients',outcome='TBU_FB',model='M3',term=term)
    if ':' in term:
        f=term.split(':')[1][:-2];qp=get('interactions',outcome='TBU_POST',factor=f)['p_holm_both'];qf=get('interactions',outcome='TBU_FB',factor=f)['p_holm_both'];label=f+' × DGC'
    else:qp=pp['p_holm_both'];qf=pf['p_holm_both'];label=term[:-2]
    rows.append([label,f"{pp['estimate']:.3f}",ci(pp),f"{pf['estimate']:.3f}",ci(pf),pv(qp)+' /\n'+pv(qf)])
set_table(3,['Term','POST b','POST 95% CI','FB b','FB 95% CI','Holm p\nPOST / FB'],rows,[1.05,.55,1.65,.55,1.65,1.3])
labels={'TBU_POST':'POST matched','TBU_FB':'FB matched','STRICT_POST':'POST strict legacy','STRICT_FB':'FB strict legacy','RBD9':'Initial-cohort RBD9','PRUD3':'Post-release PRUD3'}
rows=[]
for out,label in labels.items():
    rs=[get('coefficients',outcome=out,model='M3',term=f+'_c') for f in ['RT','TC','GC']]
    ps=[r['p_holm_both'] if out in ['TBU_POST','TBU_FB'] else r['p_holm'] for r in rs]
    rows.append([label,str(52 if out.startswith('STRICT') else 54),f"{rs[0]['estimate']:.3f}\n{ci(rs[0])}",*[pv(v) for v in ps]])
set_table(4,['Outcome','N','RT b and 95% CI','RT\nHolm p','TC\nHolm p','GC\nHolm p'],rows,[1.7,.3,2.2,.8,.8,.95])
# Replace the three active figure resources, retaining relationship IDs and placement.
rels=E.fromstring(parts['word/_rels/document.xml.rels'])
figfiles=[None,'Figure2_three_column_framework.png','Figure3_dual_clock_levels.png','Figure4_dual_clock_moderation.png']
modified=[]
for i,inline in enumerate(xml.xpath('.//wp:inline',namespaces=NS)):
    if not figfiles[i]:continue
    rid=inline.xpath('.//a:blip/@r:embed',namespaces=NS)[0];target=next(r.get('Target') for r in rels if r.get('Id')==rid);part='word/'+target
    file=ROOT/'figures'/figfiles[i];parts[part]=file.read_bytes();modified.append(part)
    if i in [2,3]:
        # Preserve original portrait width and use actual new figure aspect ratio.
        from PIL import Image
        with Image.open(file) as im:ww,hh=im.size
        extent=inline.find('wp:extent',NS);cx=int(extent.get('cx'));cy=round(cx*hh/ww);extent.set('cy',str(cy))
        for ext in inline.xpath('.//a:xfrm/a:ext',namespaces=NS):ext.set('cy',str(cy))
parts['word/document.xml']=E.tostring(xml,xml_declaration=True,encoding='UTF-8',standalone=True)
final=ROOT/'SocioVerse-研究报告_双TBU口径8页版.docx'
with ZipFile(final,'w',ZIP_DEFLATED) as z:
    for name,data in parts.items():z.writestr(name,data)
with ZipFile(REF) as old,ZipFile(final) as new:
    changed=[n for n in old.namelist() if old.read(n)!=new.read(n)]
    assert set(changed)==set(['word/document.xml']+modified)
    assert new.testzip() is None
(ROOT/'report_patch_audit.json').write_text(json.dumps(dict(output=str(final),changed_parts=changed,source_sha256=hashlib.sha256(REF.read_bytes()).hexdigest(),expected_pages=8),ensure_ascii=False,indent=2),encoding='utf-8')
print('Updated report:',final)
