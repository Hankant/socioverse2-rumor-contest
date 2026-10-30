from pathlib import Path
from zipfile import ZipFile
from lxml import etree as E
from docx import Document
import hashlib,json,shutil
ROOT=Path(__file__).resolve().parent;REF=ROOT/'reference';REF.mkdir(parents=True,exist_ok=True)
SOURCE=Path('E:/papers/socioverse 2026/SocioVerse-研究报告.docx');COPY=REF/'source_report.docx';shutil.copy2(SOURCE,COPY)
sha=lambda b:hashlib.sha256(b).hexdigest()
ns={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main','a':'http://schemas.openxmlformats.org/drawingml/2006/main','wp':'http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing','r':'http://schemas.openxmlformats.org/officeDocument/2006/relationships','m':'http://schemas.openxmlformats.org/officeDocument/2006/math'}
with ZipFile(COPY) as z:
    x=E.fromstring(z.read('word/document.xml'));body=x.find('w:body',ns);rels=E.fromstring(z.read('word/_rels/document.xml.rels'))
    blocks=[];images=[]
    for i,e in enumerate(body):
        text=''.join(e.xpath('.//w:t/text()',namespaces=ns));blocks.append(dict(index=i,type=E.QName(e).localname,text=text))
    for i,e in enumerate(x.xpath('.//wp:inline',namespaces=ns),1):
        rid=e.xpath('.//a:blip/@r:embed',namespaces=ns)[0];target='word/'+next(r.get('Target')for r in rels if r.get('Id')==rid)
        file=REF/(f'figure{i}'+Path(target).suffix);file.write_bytes(z.read(target))
        images.append(dict(number=i,part=target,path=str(file),cx=e.find('wp:extent',ns).get('cx'),cy=e.find('wp:extent',ns).get('cy')))
    inventory=[dict(part=n,bytes=len(z.read(n)),sha256=sha(z.read(n)))for n in z.namelist()]
doc=Document(COPY)
sections=[]
for s in doc.sections:
    sections.append({k:int(getattr(s,k)) if getattr(s,k) is not None else None for k in ['page_width','page_height','left_margin','right_margin','top_margin','bottom_margin','header_distance','footer_distance']})
styles={name:dict(font=doc.styles[name].font.name,size=doc.styles[name].font.size.pt if doc.styles[name].font.size else None)for name in ['Normal','Title','Subtitle','Heading 1','Heading 2','Caption']}
out=dict(source=str(SOURCE),sha256=sha(SOURCE.read_bytes()),sections=sections,styles=styles,images=images,tables=len(doc.tables),native_equations=len(x.xpath('.//m:oMath',namespaces=ns)),blocks=blocks,parts=inventory)
(ROOT/'reference_inventory.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in out.items() if k not in ['parts','blocks']},ensure_ascii=False,indent=2))
for b in blocks:
    if b['text']:print(b['index'],b['type'],b['text'])
