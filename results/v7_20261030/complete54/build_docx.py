from pathlib import Path
import json
from docx import Document
from docx.shared import Inches,Pt,RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT,WD_CELL_VERTICAL_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

ROOT=Path(__file__).resolve().parent
R=json.loads((ROOT/'report_content.json').read_text(encoding='utf-8'))
doc=Document();sec=doc.sections[0]
sec.page_width=Inches(8.5);sec.page_height=Inches(11)
sec.left_margin=sec.right_margin=Inches(.75);sec.top_margin=sec.bottom_margin=Inches(.7)
sec.header_distance=sec.footer_distance=Inches(.28)
for name in ('Normal','Title','Subtitle','Heading 1','Heading 2','Caption'):
    st=doc.styles[name];st.font.name='Times New Roman';st.font.color.rgb=RGBColor(0,0,0)
    st.element.get_or_add_rPr().get_or_add_rFonts().set(qn('w:eastAsia'),'SimSun')
normal=doc.styles['Normal'];normal.font.size=Pt(11);normal.paragraph_format.line_spacing=1.22
normal.paragraph_format.space_after=Pt(7)
doc.styles['Title'].font.size=Pt(19);doc.styles['Title'].font.bold=True
doc.styles['Title'].paragraph_format.space_after=Pt(10)
doc.styles['Subtitle'].font.size=Pt(11);doc.styles['Subtitle'].paragraph_format.space_after=Pt(10)
doc.styles['Heading 1'].font.size=Pt(14);doc.styles['Heading 1'].font.bold=True
doc.styles['Heading 1'].paragraph_format.space_before=Pt(15);doc.styles['Heading 1'].paragraph_format.space_after=Pt(7)
doc.styles['Heading 2'].font.size=Pt(12);doc.styles['Heading 2'].font.bold=True
doc.styles['Caption'].font.size=Pt(10);doc.styles['Caption'].paragraph_format.space_after=Pt(7)
doc.styles['Caption'].paragraph_format.line_spacing=1.1
for stname in ('Title','Subtitle','Heading 1','Heading 2'):
    st=doc.styles[stname]
    if st.element.pPr is not None:
        for el in list(st.element.pPr):
            if el.tag in (qn('w:pBdr'),qn('w:shd')):st.element.pPr.remove(el)
header=sec.header.paragraphs[0];header.text='Government correction strategies and belief updating'
header.runs[0].font.size=Pt(9)
footer=sec.footer.paragraphs[0];footer.alignment=WD_ALIGN_PARAGRAPH.CENTER
footer.add_run('Page ').font.size=Pt(9)
field=OxmlElement('w:fldSimple');field.set(qn('w:instr'),'PAGE');footer._p.append(field)
props=doc.core_properties;props.title=R['title'];props.subject='Complete 54-scenario factorial analysis of belief-updating time'
props.author='Research report';props.keywords='TBU, LLM agents, response timing, government credibility, cocooning'

def runfont(r,size=11,bold=False):
    r.font.name='Times New Roman';r.font.size=Pt(size);r.font.bold=bold;r.font.color.rgb=RGBColor(0,0,0)
    r._element.get_or_add_rPr().get_or_add_rFonts().set(qn('w:eastAsia'),'SimSun')
def paragraph(text,style=None):
    p=doc.add_paragraph(style=style);runfont(p.add_run(text),10 if style=='Caption' else 11)
    return p
def table(b):
    cap=paragraph(b['title'],'Caption');cap.paragraph_format.keep_with_next=True
    n=len(b['headers'])
    widths={3:[1.65,1.15,4.2],7:[.8,1.1,.65,.65,1.02,1.02,1.76],6:[1.05,1.25,.95,.8,1.75,1.2]}.get(n,[7/n]*n)
    if b['key']=='robustness':widths=[1.15]+[.975]*6
    if b['key']=='moderation':widths=[1.1,1.4,.8,.8,1.45,1.45]
    if b['key']=='contrasts':widths=[.8,1.2,1.0,.75,2.0,1.25]
    tb=doc.add_table(rows=1,cols=n);tb.alignment=WD_TABLE_ALIGNMENT.CENTER;tb.autofit=False
    for c,w in zip(tb.columns,widths):c.width=Inches(w)
    tblpr=tb._tbl.tblPr
    borders=OxmlElement('w:tblBorders')
    for edge in ('top','left','bottom','right','insideH','insideV'):
        el=OxmlElement('w:'+edge);el.set(qn('w:val'),'single');el.set(qn('w:sz'),'4');el.set(qn('w:color'),'D9D9D9');borders.append(el)
    tblpr.append(borders)
    margins=OxmlElement('w:tblCellMar')
    for side,val in [('top',75),('bottom',75),('left',75),('right',75)]:
        el=OxmlElement('w:'+side);el.set(qn('w:w'),str(val));el.set(qn('w:type'),'dxa');margins.append(el)
    tblpr.append(margins)
    headerrow=tb.rows[0]
    rep=OxmlElement('w:tblHeader');headerrow._tr.get_or_add_trPr().append(rep)
    for cell,text,w in zip(headerrow.cells,b['headers'],widths):
        cell.width=Inches(w);cell.vertical_alignment=WD_CELL_VERTICAL_ALIGNMENT.CENTER
        sh=OxmlElement('w:shd');sh.set(qn('w:fill'),'EAF0F6');cell._tc.get_or_add_tcPr().append(sh)
        p=cell.paragraphs[0];p.alignment=WD_ALIGN_PARAGRAPH.CENTER;p.paragraph_format.space_after=Pt(0);p.paragraph_format.line_spacing=1.05
        runfont(p.add_run(text),10,True)
    for row in b['rows']:
        cells=tb.add_row().cells
        for j,(cell,text,w) in enumerate(zip(cells,row,widths)):
            cell.width=Inches(w);cell.vertical_alignment=WD_CELL_VERTICAL_ALIGNMENT.CENTER
            text=str(text).replace('回应后限制平均等待 PRUD3','PRUD3').replace('限制平均TBU9','TBU9')
            p=cell.paragraphs[0];p.paragraph_format.space_after=Pt(0);p.paragraph_format.line_spacing=1.08
            p.alignment=WD_ALIGN_PARAGRAPH.LEFT if (n==3 or j<2) else WD_ALIGN_PARAGRAPH.CENTER
            runfont(p.add_run(text),10)
        nosplit=OxmlElement('w:cantSplit');tb.rows[-1]._tr.get_or_add_trPr().append(nosplit)
    note=paragraph(b['note'],'Caption');note.paragraph_format.space_before=Pt(5)

doc.add_paragraph(R['title'],'Title');doc.add_paragraph(R['subtitle'],'Subtitle')
paragraph('2026年10月29日　完整54情景　全水平比较与探索性调节检验')
for section in R['sections']:
    doc.add_heading(section['title'],level=1)
    for b in section['blocks']:
        if b['kind']=='paragraph':paragraph(b['text'])
        elif b['kind']=='table':table(b)
        else:
            p=paragraph('图'+str(int(b['stem'][:2]))+'见文末图表部分。','Caption')

doc.add_page_break()
for section in R['english']:
    doc.add_heading(section['title'],level=1)
    for b in section['blocks']:paragraph(b['text'])
doc.add_heading('References',level=1)
for r in R['references']:
    paragraph(r['text']+' '+r['url'])

english_captions={
 '01_two_time_origins':'Two time origins. Earlier publication can shorten TBU even when post-response delay is identical. The trajectories shown are illustrative rather than observed.',
 '02_TBU9_levels':'Factor-level marginal means for nine-step restricted mean TBU. Error bars are pointwise 95% HC3 intervals. Main-effect p values are Holm-adjusted across eight tests.',
 '03_post_response_levels':'Factor-level marginal means for three-step restricted mean post-response updating delay. The observation window is common to all response-timing conditions.',
 '04_endpoint_effects':'Extreme-level contrasts in simulation steps. Negative values indicate shorter durations at the higher factor level. Error bars are pointwise intervals; adjusted inference is reported separately.',
 '05_cocooning_moderation':'Conditional extreme-level contrasts across cocooning levels. Both time outcomes are shown. Joint interaction tests were Holm-adjusted across six tests.',
 '06_method_robustness':'Adjusted main-effect p values across analytical methods. Each method applies Holm correction to eight tests. The full exploratory family is also reported in the data workbook.',
 '07_belief_update_curves':'Scenario-weighted proportions of step-1 believers who have not yet updated. All trajectories share nine follow-up steps; non-updaters are right-censored at the end.',
 '08_full54_TBU_heatmap':'Observed restricted mean TBU in all 54 completed scenarios. No missing outcomes were interpolated or replaced by model predictions.',
 '09_burden_moderation':'Supplementary cocooning interactions for cumulative belief burden, measured in believer person-rounds. These effects must not be relabeled as TBU interactions.'}
figs=R['figures']
for index,fig in enumerate(figs):
    # Two short figures share a page; taller scientific panels get a full page.
    doc.add_page_break()
    doc.add_heading('图'+str(index+1)+'  '+{'01_two_time_origins':'两个时间起点','02_TBU9_levels':'TBU的因素水平差异','03_post_response_levels':'回应后等待的因素水平差异','04_endpoint_effects':'高低水平的效应差','05_cocooning_moderation':'群体茧房程度的调节','06_method_robustness':'多方法稳健性','07_belief_update_curves':'首次信念更新的时间曲线','08_full54_TBU_heatmap':'全部54情景的TBU','09_burden_moderation':'总相信负担的补充调节'}[fig['stem']],level=1)
    width=6.15 if fig['stem']=='05_cocooning_moderation' else 6.9
    p=doc.add_paragraph();p.paragraph_format.space_after=Pt(5);p.alignment=WD_ALIGN_PARAGRAPH.CENTER
    p.add_run().add_picture(str(ROOT/'figures'/(fig['stem']+'.png')),width=Inches(width))
    paragraph(fig['caption'],'Caption')
    paragraph('Figure '+str(index+1)+'. '+english_captions[fig['stem']],'Caption')

doc.save(ROOT/'V7_54组_TBU研究报告.docx')
print('DOCX research report saved.')
