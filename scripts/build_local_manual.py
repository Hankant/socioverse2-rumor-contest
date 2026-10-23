"""Build the offline local manual from reviewed Markdown and effective config."""
from pathlib import Path
import html
import json
import re
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'app_v6'))
from run import defaults

docs=ROOT/'docs'
quick=(ROOT/'README_LOCAL.md').read_text(encoding='utf-8')
detail=(docs/'V6_模型全部设定与待检查项.md').read_text(encoding='utf-8')
cfg={**defaults(),**json.loads((ROOT/'configs/local_defaults.json').read_text(encoding='utf-8'))}
config_text='```json\n'+json.dumps(cfg,ensure_ascii=False,indent=2)+'\n```'
detail=detail.replace('<!-- EFFECTIVE_CONFIG -->',config_text)
# Refresh an already-filled appendix if this builder is run again.
marker='## 附录A. 全部有效配置'
if marker in detail:
    head,tail=detail.split(marker,1)
    first=tail.find('```json')
    if first>=0:
        tail=tail[:first]+config_text+'\n'
        detail=head+marker+tail
(docs/'V6_模型全部设定与待检查项.md').write_text(detail,encoding='utf-8')
(docs/'effective_config.json').write_text(json.dumps(cfg,ensure_ascii=False,indent=2),encoding='utf-8')

def inline(text):
    text=html.escape(text)
    text=re.sub(r'`([^`]+)`',r'<code>\1</code>',text)
    text=re.sub(r'\*\*(.*?)\*\*',r'<strong>\1</strong>',text)
    return re.sub(r'\[([^\]]+)\]\((https?://[^)]+)\)',r'<a href="\2">\1</a>',text)

def render(markdown,prefix):
    lines=markdown.splitlines();blocks=[];toc=[];i=0;index=0
    while i<len(lines):
        line=lines[i]
        if not line.strip():i+=1;continue
        if line.startswith('```'):
            language=line[3:].strip();code=[];i+=1
            while i<len(lines) and not lines[i].startswith('```'):
                code.append(lines[i]);i+=1
            i+=1
            blocks.append('<div class="codebox"><div class="language">'+html.escape(language)+'</div><pre><code>'+html.escape('\n'.join(code))+'</code></pre></div>');continue
        if line.startswith('# '):blocks.append('<h1>'+inline(line[2:])+'</h1>');i+=1;continue
        if line.startswith('## '):
            index+=1;anchor=f'{prefix}-{index}';label=line[3:]
            blocks.append('<h2 id="'+anchor+'">'+inline(label)+'</h2>');toc.append((anchor,label));i+=1;continue
        if line.startswith('|'):
            rows=[]
            while i<len(lines) and lines[i].startswith('|'):
                cells=[s.strip() for s in lines[i].strip('|').split('|')]
                if not all(re.fullmatch(r'[-: ]+',s) for s in cells):rows.append(cells)
                i+=1
            blocks.append('<div class="tablewrap"><table><thead><tr>'+''.join('<th>'+inline(c)+'</th>' for c in rows[0])+'</tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+inline(c)+'</td>' for c in row)+'</tr>' for row in rows[1:])+'</tbody></table></div>');continue
        paras=[line];i+=1
        while i<len(lines) and lines[i].strip() and not lines[i].startswith(('#','|','```')):
            paras.append(lines[i]);i+=1
        blocks.append('<p>'+inline(' '.join(paras))+'</p>')
    return ''.join(blocks),toc

quick_html,quick_toc=render(quick,'start')
detail_html,detail_toc=render(detail,'model')
css='''*{box-sizing:border-box}body{margin:0;color:#223b4d;background:#edf2f5;font-family:"Microsoft YaHei","Segoe UI",sans-serif;font-size:15px;line-height:1.9}.layout{max-width:1530px;margin:auto;display:grid;grid-template-columns:285px minmax(0,1fr);gap:25px;padding:28px 24px}nav{position:sticky;top:20px;align-self:start;max-height:95vh;overflow:auto;background:#fff;border-radius:10px;padding:22px;font-size:12px;box-shadow:0 4px 24px #173c4a0a}nav a{display:block;margin:9px 0;color:#476477;text-decoration:none}nav a:hover{color:#127b76}nav strong{display:block;color:#127b76;margin-top:12px;font-size:14px}main{min-width:0;background:#fff;padding:45px 52px;border-top:7px solid #14847d;box-shadow:0 4px 24px #173c4a0a}h1{font-size:29px;line-height:1.5;color:#14354d;margin:0 0 22px}h2{font-size:21px;color:#153c53;border-bottom:1px solid #dbe6eb;margin:42px 0 18px;padding-bottom:10px;scroll-margin-top:20px}p{margin:17px 0;overflow-wrap:anywhere}strong{color:#166e6c}code{font-family:Consolas,"Microsoft YaHei",monospace;background:#eff4f6;padding:2px 5px;border-radius:3px;font-size:13px}pre{margin:0;white-space:pre-wrap;overflow-wrap:anywhere;line-height:1.7;padding:17px 20px}pre code{padding:0;background:none;color:#dcecf1}.codebox{background:#173b50;border-radius:7px;margin:18px 0;overflow:hidden}.language{font-size:11px;letter-spacing:1px;color:#adc9d6;background:#123246;padding:5px 20px}.tablewrap{overflow:auto}table{width:100%;border-collapse:collapse;font-size:13px;margin:18px 0}th{color:#fff;background:#24546c;text-align:left;padding:11px}td{padding:10px 11px;border-bottom:1px solid #e0e8ec;vertical-align:top}tbody tr:nth-child(even){background:#f4f8fa}a{color:#157b91;text-decoration:none}.badge{display:inline-block;border-radius:4px;color:#1a736e;background:#e9f5f2;font-size:12px;padding:4px 9px;margin:0 8px 16px 0}.section-sep{border:0;border-top:4px solid #14847d;margin:55px 0}.notice{background:#f1f8f6;border-left:4px solid #14847d;padding:15px 20px;margin:20px 0}footer{color:#758b99;font-size:12px;margin-top:40px}@media(max-width:950px){.layout{display:block;padding:0}nav{position:static;max-height:250px;border-radius:0}main{padding:27px 22px}h1{font-size:25px}}@media print{body{background:#fff}.layout{display:block;padding:0}nav{display:none}main{padding:0;box-shadow:none;border:0}h2{break-after:avoid}table,.codebox{break-inside:avoid}}'''
nav='<nav><strong>启动与运行</strong>'+''.join('<a href="#'+anchor+'">'+html.escape(label)+'</a>' for anchor,label in quick_toc)+'<strong>全部模型设定</strong>'+''.join('<a href="#'+anchor+'">'+html.escape(label)+'</a>' for anchor,label in detail_toc)+'</nav>'
badges='<span class="badge">305 LLM + 277规则</span><span class="badge">10轮 / 单次介入</span><span class="badge">54个配置</span><span class="badge">完整记忆保护</span>'
page='<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>V6本地部署与完整设定手册</title><style>'+css+'</style></head><body><div class="layout">'+nav+'<main>'+badges+quick_html+'<hr class="section-sep">'+detail_html+'<footer>本地文档 · 2026-10-21 · 实际运行配置与冻结输入为最终依据</footer></main></div></body></html>'
(docs/'V6_本地部署与设定手册.html').write_text(page,encoding='utf-8')
print('Built local manual:',docs/'V6_本地部署与设定手册.html')
