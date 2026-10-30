"""Independent checks from unchanged raw CSV, followed by a reproducible package."""
from pathlib import Path
from collections import defaultdict,Counter
import csv,json,hashlib,math,zipfile,sys
import xml.etree.ElementTree as ET
import pandas as pd

ROOT=Path(__file__).resolve().parent
extract=json.loads((ROOT/'extraction.json').read_text(encoding='utf-8'))
A=json.loads((ROOT/'analysis.json').read_text(encoding='utf-8'))
cases=pd.read_csv(ROOT/'data/cases.csv').set_index('case_id')
assert extract['complete_cases']==54 and extract['incomplete']==[]
checked=0;transition_count=0
source_hashes=[]
for entry in extract['source_files']:
    tag=entry['case_id'];src=Path(entry['source']);snap=ROOT/'raw'/(tag+'.csv')
    assert hashlib.sha256(src.read_bytes()).hexdigest()==entry['sha256']
    assert hashlib.sha256(snap.read_bytes()).hexdigest()==entry['sha256']
    source_hashes.append(dict(case_id=tag,source=str(src),sha256=entry['sha256']))
    rows=list(csv.DictReader(snap.open(encoding='utf-8-sig',newline='')))
    assert len(rows)==3300 and len({(r['agent_id'],r['step']) for r in rows})==3300
    assert Counter(int(r['step']) for r in rows)==dict.fromkeys(range(11),300)
    by=defaultdict(dict)
    for r in rows:
        t=int(r['step']);by[r['agent_id']][t]=r
        if r['subjective_credibility']:
            assert (float(r['subjective_credibility'])>50)==(r['belief']=='believe')
        checked+=1
    initial=[];post=[];ninitial=0;ninit_events=0;tg=int(cases.loc[tag,'TG'])
    for aid,series in by.items():
        for t in range(1,11):
            event=series[t-1]['belief']=='believe' and series[t]['belief']=='reject'
            recorded=series[t]['believe_to_reject_event'].lower() in ('true','1','1.0')
            assert event==recorded,(tag,aid,t)
            transition_count+=int(event)
        if series[1]['belief']=='believe':
            assert series[1]['group']=='inside'
            event_ticks=[t for t in range(2,11) if series[t]['belief']=='reject']
            initial.append(event_ticks[0]-1 if event_ticks else 9)
            ninitial+=1;ninit_events+=bool(event_ticks)
        if series[tg-1]['belief']=='believe':
            event_ticks=[t for t in range(tg,11) if series[t]['belief']=='reject']
            post.append(min(event_ticks[0]-tg if event_ticks else 10-tg,3))
    assert abs(sum(initial)/len(initial)-cases.loc[tag,'RMST_initial9'])<1e-12
    assert abs(sum(post)/len(post)-cases.loc[tag,'RMST_post3'])<1e-12
    assert ninitial==cases.loc[tag,'initial_believers'] and ninit_events==cases.loc[tag,'initial_events']

# Full balanced factorial marginal estimates equal direct raw-case means.
for r in A['tables']['means']:
    raw=cases.loc[cases[r['factor']].eq(r['level']),r['outcome']].mean()
    assert abs(raw-r['mean'])<1e-10
for out in A['primary_outcomes']:
    m=next(r for r in A['tables']['main'] if r['outcome']==out and r['factor']=='TC')
    pair=next(r for r in A['tables']['pairwise'] if r['outcome']==out and r['factor']=='TC')
    assert abs(m['F']-pair['t']**2)<1e-9 and abs(m['p']-pair['p'])<1e-12
assert len([r for r in A['tables']['main'] if r['outcome'] in A['primary_outcomes']])==8
assert len([r for r in A['tables']['moderation'] if r['outcome'] in A['primary_outcomes']])==6
assert len([r for r in A['tables']['pairwise'] if r['outcome'] in A['primary_outcomes']])==20

NS={'m':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
book=ROOT/'V7_54组_TBU统计结果与数据.xlsx'
with zipfile.ZipFile(book) as z:
    assert z.testzip() is None
    for name in z.namelist():
        if name.startswith('xl/worksheets/sheet') and name.endswith('.xml'):
            xml=ET.fromstring(z.read(name))
            assert not [c for c in xml.findall('.//m:c',NS) if c.attrib.get('t')=='e']
with zipfile.ZipFile(ROOT/'V7_54组_TBU研究报告.docx') as z:assert z.testzip() is None
assert len(list((ROOT/'figures').glob('*.png')))==9
assert len(list((ROOT/'docx_preview').glob('page-*.png')))==19
assert json.loads((ROOT/'workbook_verification.json').read_text(encoding='utf-8'))['formula_error'] is False

cases.reset_index().rename(columns={'GT':'GC','TG':'RT','D':'DGC','RMST_initial9':'restricted_mean_TBU_9steps',
    'RMST_post3':'restricted_mean_postresponse_delay_3steps'}).to_csv(ROOT/'data/scenario_summary_SCI.csv',index=False,encoding='utf-8-sig')
verification=dict(scenarios=54,raw_agent_step_rows=checked,raw_event_flags_checked=True,
    all_believe_to_reject_events=transition_count,restricted_means_independently_recalculated=108,
    source_files_unchanged=54,no_imputation=True,analysis_api_calls=0,TC_F_equals_t_squared=True,
    workbook_formula_checks=54,workbook_marginal_mean_checks=22,docx_render_engine='Microsoft Word native PDF export',
    canonical_renderer_unavailable_reason='LibreOffice soffice.exe was not on PATH; native Word rendering was used instead',
    rendered_docx_pages=19,figures=9,source_hashes=source_hashes)
(ROOT/'verification.json').write_text(json.dumps(verification,ensure_ascii=False,indent=2),encoding='utf-8')

readme='''完整54情景 TBU研究结果

先打开 V7_完整54组_TBU研究报告.html，或使用19页Word报告。
Excel共7张表：主要检验、水平对比、调节效应、稳健性分析、情景指标、初始相信者、回应前队列。
9幅图同时提供PNG、SVG、PDF，保存在figures文件夹；英文方法、结果和讨论另有TXT写作稿。

TBU9为第1轮相信者的9轮限制平均持续时间；PRUD3为发布前一轮相信者的3轮限制平均发布后等待。
删失者未被删掉或伪造为已更新者。主分析单位54情景，不是911条用户轨迹。
GC是主观政府来源信任；TC是固定50人中的圈内比例；DGC是圈内外初始来源信任差，未操纵网络拓扑。

主要结果：GC和TC缩短TBU9与PRUD3；较早RT缩短TBU9，但PRUD3的RT差异不显著。
DGC在两个时间结局上的直接差异和总体调节未获显著支持。
总相信负担出现DGC×GC、DGC×RT调节，是补充结局，不能改称TBU调节。
GC .75相对.50的额外收益没有通过两两校正。不能写成高中低全部两两显著。

raw是54份完整结果快照；data是情景指标、用户事件/删失、逐步人数和所有统计检验。
scenario_summary_SCI.csv将旧字段GT/TG/D改名为GC/RT/DGC，保留其数值和含义；其他原始中间文件沿用代码字段。
extraction.json记录54份原始来源位置和SHA256；verification.json记录独立复算与原始文件保留检查。
protocol.txt在本次54格拟合前固定分析口径，但此前看过53格结果，故不属于预注册。

复现顺序：extract.py → analysis54.py → figures54.py → build_content.py。
分析环境版本见analysis.json的versions。工作区附带numpy/pandas；本任务补充scipy 1.16.3，使用既有statsmodels 0.15.0、patsy 1.0.3和matplotlib 3.9.2。
统计核心代码在statistical_helpers.py；其HC3系数/协方差和F统计量逐模型与statsmodels核对。
独立核验脚本verify_and_package.py从原始CSV再次计算108个限制均值，并验证阈值、跨状态事件和F=t²。
构建Excel需@oai/artifact-tool，Word需python-docx；Word排版已通过本机Microsoft Word导出PDF并逐页查看。
推断统计是分析代码的结果快照；Excel中的情景指标和水平均值可重算，但修改输入后F/t/p值需要重新拟合。

完整模拟原始目录
D:/Codex/runs/V7_Optimized_20261027_145124

本次只读分析，不改变模拟代码、参数和运行结果，也不新增MiniMax调用。
'''
(ROOT/'阅读与复现说明.txt').write_text(readme,encoding='utf-8')
requirements='\n'.join(f'{k}=={v}' for k,v in A['versions'].items() if k!='python')+'\nmatplotlib==3.9.2\npython-docx==1.2.0\n'
(ROOT/'requirements-analysis.txt').write_text(requirements,encoding='utf-8')

whitelist=['V7_完整54组_TBU研究报告.html','V7_54组_TBU研究报告.docx','V7_54组_TBU统计结果与数据.xlsx',
    'SCI_英文方法结果与讨论.txt','阅读与复现说明.txt','protocol.txt','extraction.json','analysis.json','verification.json',
    'report_content.json','figure_manifest.json','workbook_verification.json','requirements-analysis.txt',
    'extract.py','analysis54.py','statistical_helpers.py','figures54.py','build_content.py','workbook_payload.py',
    'build_workbook.mjs','build_docx.py','verify_and_package.py','render_with_word.ps1','rasterize_word_pdf.py']
files=[ROOT/n for n in whitelist]
for name in ('raw','data','figures'):files += sorted((ROOT/name).glob('*'))
manifest=[dict(path=str(p.relative_to(ROOT)).replace('\\','/'),bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in files]
(ROOT/'package_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
package=ROOT/'V7_54组_TBU研究报告与数据图表.zip'
with zipfile.ZipFile(package,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
    for p in files:z.write(p,p.relative_to(ROOT))
    z.write(ROOT/'package_manifest.json','package_manifest.json')
print(json.dumps({'scenarios':54,'raw_rows':checked,'mean_checks':108,'raw_events':transition_count,
    'package_files':len(files)+1,'package_megabytes':round(package.stat().st_size/1048576,2)},ensure_ascii=False))
