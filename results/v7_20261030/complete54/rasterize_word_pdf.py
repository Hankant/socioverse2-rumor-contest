from pathlib import Path
import sys,json
sys.path.append('D:/Program Files/Python312/Lib/site-packages')
import fitz
ROOT=Path(__file__).resolve().parent;out=ROOT/'docx_preview'
pdf=fitz.open(out/'report.pdf');metadata=[]
for index,page in enumerate(pdf):
    path=out/f'page-{index+1}.png'
    page.get_pixmap(matrix=fitz.Matrix(1.7,1.7),alpha=False).save(path)
    text=page.get_text()
    metadata.append(dict(page=index+1,chars=len(text),first=text[:120],last=text[-120:],width=page.rect.width,height=page.rect.height))
(out/'page_metadata.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2),encoding='utf-8')
print('Native Word PDF rendered:',len(pdf),'pages')
print(json.dumps([{'page':r['page'],'chars':r['chars'],'first':r['first'][:45]} for r in metadata],ensure_ascii=False))
