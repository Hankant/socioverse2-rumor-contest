"""Durable sequential execution and complete XLSX exports of the V6 factorial design.

This module never changes app_v6, research parameters or existing runs.
New saved-key jobs use the CurrentUser DPAPI vault; old environment-key jobs
retain their original hidden input mode. Existing terminated queues stay stopped.
"""
from __future__ import annotations
import argparse
import contextlib
import csv
from datetime import datetime, timezone, timedelta
import getpass
import hashlib
import itertools
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import zipfile
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
OUT = Path('D:/Codex/outputs/socioverse_v6_research54_20261022')
BATCH = ROOT/'runtime/v6/batch54-20261022'
NODE = Path('C:/Users/Administrator/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node.exe')
BUILDER = OUT/'build_workbooks.mjs'
FACTORS = ['source_trust_gap','government_tick','targeting_inside_ratio','government_trust_mean']
CN = timezone(timedelta(hours=8))
sys.path.insert(0,str(ROOT/'app_v6'))
from model import digest, dump, load_rows, belief_states, BINARY_SCORE_POLICY
from local_cli import condition_id
from experiment import validate_experiment
from government import validate
from verify_run import verify

def now(): return datetime.now(CN).isoformat()
def read(p): return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def public_env():
    env = dict(os.environ);env.pop('RUMOR_LLM_API_KEY',None)
    return env
def hashes():
    return {'code':{p.name:sha(p) for p in (ROOT/'app_v6').glob('*.py')},
            'inputs':{p.name:sha(p) for p in (ROOT/'materials_v6').iterdir() if p.is_file()}}
def xlsx_name(c):
    return (f"信任差{c['source_trust_gap']:.1f}_介入{c['government_tick']}_"
            f"圈内比例{c['targeting_inside_ratio']:.1f}_政府信任{c['government_trust_mean']:.2f}.xlsx")
def complete(run):
    p=Path(run)/'status.json'
    return p.is_file() and read(p).get('status')=='completed_live' and read(p).get('last_completed_tick')==10

def persist(m):
    m['updated_china']=now()
    m['completed_count']=sum(j['status']=='completed_exported' for j in m['jobs'])
    m['complete_run_count']=sum(bool(j.get('run_dir')) and complete(j['run_dir']) for j in m['jobs'])
    dump(BATCH/'batch_manifest.json',m)
    extra=[] if all(j['config'].get('belief_measurement_policy')==BINARY_SCORE_POLICY for j in m['jobs']) else ['final_uncertain']
    headers=['condition_id',*FACTORS,'status','last_completed_tick','final_believe',*extra,'final_reject',
             'tbu_engineering','requests','actual_input_tokens','actual_output_tokens','run_dir','xlsx_file','error_type']
    with (OUT/'54组运行进度.csv').open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=headers);writer.writeheader()
        for j in m['jobs']:
            values={**{k:j['config'][k] for k in FACTORS},**{k:j.get(k) for k in headers if k not in FACTORS}}
            writer.writerow(values)
    lines=[f"批量任务：{m['status']}",f"更新时间（北京时间）：{m['updated_china']}",
           f"真实完整运行：{m['complete_run_count']}/54；Excel已导出：{m['completed_count']}/54。",
           f"当前条件：{m.get('active_condition') or '无'}",f"当前完整时间步：{m.get('active_tick',0)}/10",
           '尚未完成条件的结果留空，不作为零值或完整结果。','',
           '文件名：信任差D_介入T_圈内比例C_政府信任GT.xlsx。',
           '每组10步。T为2/4/7之一，仅在该步直接投放一次100人；不筛选当前是否相信。',
           '源输入、网络和行为机制保持冻结；一组一次运行，不是54次独立重复。',
           f"每组Excel目录：{OUT/'Excel结果'}",f"原始运行目录：{ROOT/'runs/v6'}",'']
    (OUT/'运行状态.txt').write_text('\n'.join(lines),encoding='utf-8-sig')

def prepare():
    BATCH.mkdir(parents=True,exist_ok=True);OUT.mkdir(parents=True,exist_ok=True)
    (BATCH/'frozen_configs').mkdir(exist_ok=True);(BATCH/'export_payloads').mkdir(exist_ok=True)
    (BATCH/'console').mkdir(exist_ok=True);(OUT/'Excel结果').mkdir(exist_ok=True)
    existing=BATCH/'batch_manifest.json'
    if existing.exists(): return read(existing)
    signature=hashes();configs=[]
    for p in sorted((ROOT/'configs/research54').glob('*.json')):
        if re.fullmatch(r'D\d{3}_T\d{2}_C\d{3}_G\d{3}\.json',p.name):
            c=read(p);validate(c);validate_experiment(c);configs.append(c)
    assert len(configs)==54
    expected=set(itertools.product([0,.2,.4],[2,4,7],[.2,.8],[.25,.5,.75]))
    assert {tuple(c[k] for k in FACTORS) for c in configs}==expected
    runs=[]
    for p in (ROOT/'runs/v6').glob('government-rumor-v6-openai-*'):
        if not complete(p): continue
        prov=read(p/'provenance.json')
        if prov['code_sha256']==signature['code'] and prov['input_sha256']==signature['inputs'] and prov['total_steps']==10:
            runs.append((p,prov))
    jobs=[]
    for c in configs:
        cid=condition_id(c);path=BATCH/'frozen_configs'/f'{cid}.json';dump(path,c)
        matching=[p for p,prov in runs if prov['config']==c]
        job=dict(condition_id=cid,config=c,config_file=str(path),config_sha256=sha(path),
                 status='pending',last_completed_tick=0,xlsx_file=str(OUT/'Excel结果'/xlsx_name(c)),attempts=[])
        if matching:
            p=sorted(matching)[-1];job.update(run_dir=str(p),status='completed_pending_export',last_completed_tick=10,reused_existing=True)
        jobs.append(job)
    m=dict(batch_id='v6-research54-20261022',created_china=now(),updated_china=now(),status='prepared',
           total_conditions=54,steps_per_condition=10,repeat_count=1,signature=signature,jobs=jobs,
           execution='sequential; original V6 request, prompt and budget guards unchanged',
           output_dir=str(OUT/'Excel结果'),active_condition=None,active_tick=0)
    persist(m)
    return m

def as_cell(v):
    if v is None or isinstance(v,(str,int,float,bool)): return v
    return json.dumps(v,ensure_ascii=False,separators=(',',':'))

def prepare_payload(job):
    run=Path(job['run_dir']);assert complete(run),'Only completed live data may become a final workbook'
    with contextlib.redirect_stdout(open(os.devnull,'w')): verify(run)
    p=read(run/'provenance.json');cfg=p['config'];frozen=Path(p['config_dir']);audit=Path(p['audit_dir'])
    assert cfg==job['config'],'Research configuration mismatch'
    roster=load_rows(next(frozen.glob('01_*.csv')));people={r['agent_id']:r for r in roster}
    metrics=read(run/'trajectory/metrics_history.json')['rows'];last=metrics[-1]
    snap=read(run/'trajectory/final_snapshot.json');targets=set(read(frozen/'government_targets.json'))
    src=read(frozen/'source_trust.json');gov=read(frozen/'government_trust.json');budget=read(audit/'budget.json')
    checkrows=[]
    def ck(name,passed,detail=''):
        checkrows.append([name,bool(passed),detail]);assert passed,name+': '+str(detail)
    ck('completed_live_10_ticks',complete(run));ck('no_missing_roster',len(people)==582)
    with (run/'trajectory/panel.csv').open(encoding='utf-8-sig',newline='') as stream: panel=list(csv.DictReader(stream))
    states={(r['agent_id'],int(r['step'])):json.loads(r['state']) for r in panel}
    ck('unique_complete_agent_tick_panel',len(states)==len(panel)==6402)
    ck('snapshot_matches_final_beliefs',all(snap['beliefs'][a]==states[a,10]['current_belief'] for a in people))
    for tick in range(1,11):
        cp=read(run/f'checkpoints/tick-{tick:03d}.json')
        ck(f'checkpoint_{tick}_checksum',digest(cp['actions'])==cp['sha256'])
    for row in metrics:
        for mode in ['all','llm','rule']:
            for belief in belief_states(cfg.get('belief_measurement_policy','legacy')):
                got=sum(st['current_belief']==belief for (a,t),st in states.items() if t==row['step'] and (mode=='all' or people[a]['decision_mode']==mode))
                ck(f"panel_count_{row['step']}_{mode}_{belief}",got==row[f'{mode}_{belief}'])
    # Every object field is retained; lengthy text is split rather than truncated.
    longtexts=[]
    def text(v):
        val=as_cell(v)
        if isinstance(val,str) and len(val)>30000:
            tid=f'TEXT-{len(longtexts)+1:06d}'
            chunks=[val[i:i+30000] for i in range(0,len(val),30000)]
            longtexts.extend([[tid,i+1,len(chunks),chunk] for i,chunk in enumerate(chunks)])
            return f'[完整长文本见 长文本分段: {tid}]'
        return val
    def dataset(name,headers,rows,widths=None):
        return dict(name=name,headers=headers,rows=[[text(v) for v in r] for r in rows],widths=widths or [])
    metriccols=list(dict.fromkeys(['step']+[k for row in metrics for k in row if k!='step']))
    sheets=[dataset('逐步指标',metriccols,[[row.get(k) for k in metriccols] for row in metrics])]
    paramrows=[[k,v,'运行参数'] for k,v in cfg.items()]+[[k,v,'参数作用范围'] for k,v in read(run/'experiment_parameters.json')['scope_notes'].items()]
    paramrows += [['condition_id',job['condition_id'],''],['total_steps',10,''],['run_dir',str(run),'原始结果位置'],['audit_dir',str(audit),'完整提示词与响应位置'],
                  ['numpy_version',p['numpy_version'],''],['code_sha256',p['code_sha256'],''],['input_sha256',p['input_sha256'],''],
                  ['TBU_definition','介入前一轮已相信者首次拒绝的平均等待，按完成者统计',''],
                  ['belief_labels',('unjudged=未判断（统计分母外）; believe=评分>50; reject=评分<=50; 规则用户沿用原二分类' if cfg.get('belief_measurement_policy')==BINARY_SCORE_POLICY else 'unjudged=未判断; believe=相信; uncertain=不确定; reject=拒绝原始主张'),''],
                  ['raw_prompts','API请求表保留每个请求文件位置；完整提示词在原始JSON中，不受Excel单元格长度限制',''],
                  ['trust_assignment_summary',read(frozen/'trust_assignment_summary.json'),'实际冻结分配摘要']]
    sheets.append(dataset('参数设定',['参数','数值或定义','作用范围'],paramrows,[34,100,80]))
    extra=['source_trust_assigned','government_trust_assigned','direct_target','rule_pb_effective','rule_rc_effective']
    rocols=list(roster[0]);ro_rows=[]
    for row in roster:
        vals=[]
        for k in rocols:
            v=row[k]
            if k not in ['agent_id','group','decision_mode'] and re.fullmatch(r'-?\d+(\.\d+)?',v or ''):
                v=float(v) if '.' in v else int(v)
            vals.append(v)
        aid=row['agent_id'];rule=row['decision_mode']=='rule'
        ro_rows.append(vals+[src[aid],gov[aid],aid in targets,.579 if rule else None,.1 if rule else None])
    sheets.append(dataset('用户参数',rocols+extra,ro_rows))
    staterows=[];actionrows=[];readingrows=[];drawrows=[];validrequests={};history={a:[] for a in people}
    for row in sorted(panel,key=lambda r:(int(r['step']),r['agent_id'])):
        aid=row['agent_id'];tick=int(row['step']);st=states[aid,tick];payload=json.loads(row['action_payload'])
        staterows.append([aid,tick,people[aid]['decision_mode'],people[aid]['group'],st['current_belief'],st])
        if not tick:continue
        ans=payload.get('answer',{});raw=payload.get('raw_answer',{});api=payload.get('api',{})
        postlist=payload.get('observed_posts',[]);rp=ans.get('repost',{});cm=ans.get('comment',{})
        root=next((p['root_content_id'] for p in postlist if p['content_id']==rp.get('target_content_id')),None)
        actionrows.append([aid,tick,people[aid]['decision_mode'],people[aid]['group'],states[aid,tick-1]['current_belief'],st['current_belief'],
            row['action_kind'],payload.get('decision_status'),len(postlist),rp.get('enabled',False),rp.get('target_content_id'),root,rp.get('text'),
            cm.get('enabled',False),cm.get('text'),ans.get('evidence_ids'),raw,ans,payload.get('used_memory_ticks'),api.get('request_number'),
            {k:v for k,v in payload.items() if k not in ['observed_posts','answer','raw_answer']}])
        for pos,post in enumerate(postlist):
            readingrows.append([aid,tick,pos+1,post['content_id'],post['root_content_id'],post['author_id'],post['published_tick'],post['available_tick'],
                post.get('delivery'),post.get('is_reread'),post.get('can_repost'),post.get('text'),post.get('repost_text'),post.get('comments'),post])
        for draw in payload.get('draws',[]):drawrows.append([aid,tick,draw['name'],draw['probability'],draw['uniform'],draw['passed']])
        number=api.get('request_number')
        if number:
            validrequests[number]=(aid,tick,raw)
            ck(f'full_memory_{aid}_{tick}',payload.get('used_memory_ticks')==history[aid][-5:])
            history[aid].append(tick)
    sheets.append(dataset('用户状态',['agent_id','step','decision_mode','group','current_belief','完整状态JSON'],staterows,[14,10,14,14,16,90]))
    sheets.append(dataset('决策与行动',['agent_id','step','decision_mode','group','belief_before','belief_after','action_kind','decision_status','feed_count',
        'repost_enabled','repost_target','repost_root','repost_text','comment_enabled','comment_text','evidence_ids','raw_answer','applied_answer',
        'used_memory_ticks','request_number','其他完整载荷JSON'],actionrows))
    sheets.append(dataset('阅读记录',['agent_id','step','feed_position','content_id','root_content_id','author_id','published_tick','available_tick',
        'delivery','is_reread','can_repost','text','repost_text','visible_comments','完整观察JSON'],readingrows))
    sheets.append(dataset('规则抽样',['agent_id','step','draw_name','probability','uniform','passed'],drawrows,[14,10,16,16,16,14]))
    for name,items in [('帖子',list(snap['posts'].values())),('评论',list(snap['comments'].values()))]:
        keys=list(dict.fromkeys(k for item in items for k in item))
        sheets.append(dataset(name,keys,[[item.get(k) for k in keys] for item in items]))
    sheets.append(dataset('关注网络',['follower_id','publisher_id'],read(frozen/'network_edges.json'),[18,18]))
    requests=[];in_tokens=out_tokens=0;reqstatus={};maxproxy=0
    for file in sorted(audit.glob('request-*.json')):
        r=read(file);n=r['request_number'];in_tokens+=r.get('actual_input_tokens') or 0;out_tokens+=r.get('actual_output_tokens') or 0
        reqstatus[r.get('status','unknown')]=reqstatus.get(r.get('status','unknown'),0)+1;maxproxy=max(maxproxy,r.get('input_reserved_units',0))
        if n in validrequests:
            aid,tick,raw=validrequests[n];response=(r.get('raw_response') or '').strip()
            if response.startswith('```'):response=response.split('\n',1)[1].rsplit('```',1)[0].strip()
            ck(f'committed_response_{n}',json.loads(response)==raw)
        requests.append([n,r['agent_id'],r['tick'],r.get('status'),n in validrequests,r.get('requested_model'),r.get('returned_model'),r.get('attempt'),
            r.get('actual_input_tokens'),r.get('actual_output_tokens'),r.get('input_reserved_units'),r.get('elapsed_seconds'),r.get('finish_reason'),
            r.get('raw_response'),r.get('diagnostic'),r.get('used_memory_ticks'),r.get('trimmed_memory_count'),r.get('trimmed_post_count'),
            r.get('trimmed_comment_count'),r.get('prompt_sha256'),str(file)])
    ck('request_count_matches_budget',len(requests)==budget['requests'])
    ck('usage_matches_budget',in_tokens==budget['actual_input_tokens'] and out_tokens==budget['actual_output_tokens'])
    ck('no_unknown_pending_requests',reqstatus.get('pending_usage_unknown',0)==0)
    ck('prompt_guard',maxproxy<=cfg['prompt_input_token_limit'])
    sheets.append(dataset('API请求',['request_number','agent_id','step','status','committed','requested_model','returned_model','attempt',
        'actual_input_tokens','actual_output_tokens','input_reserved_units','elapsed_seconds','finish_reason','raw_response','diagnostic','used_memory_ticks',
        'trimmed_memory_count','trimmed_post_count','trimmed_comment_count','prompt_sha256','原始请求文件'],requests))
    sheets.append(dataset('核验',['检查','通过','详情'],checkrows,[50,12,80]))
    # dataset conversion may itself add overflow text; no long text is discarded.
    if longtexts:sheets.append(dict(name='长文本分段',headers=['text_id','part','total_parts','完整文本分段'],rows=longtexts,widths=[20,12,12,110]))
    events=[readline for readline in (audit/'request-events.jsonl').read_text(encoding='utf-8').splitlines() if readline.strip()]
    times=[datetime.fromisoformat(json.loads(line)['time']) for line in events]
    finish=datetime.fromtimestamp((run/'status.json').stat().st_mtime,CN)
    duration=(finish-min(times)).total_seconds()/60 if times else None
    headline=dict(condition_id=job['condition_id'],factors={k:cfg[k] for k in FACTORS},final=last,budget=budget,
        peak_believe=max(r['all_believe'] for r in metrics),llm_valid_decisions=len(validrequests),
        llm_believe_decisions=sum(r[2]=='llm' and r[5]=='believe' for r in actionrows),
        duration_minutes=duration,finished_china=finish.isoformat(),checks_count=len(checkrows),run_dir=str(run))
    payload=dict(kind='condition',output=job['xlsx_file'],condition_id=job['condition_id'],headline=headline,sheets=sheets,
                 preview_dir=str(BATCH/'previews'/job['condition_id']))
    path=BATCH/'export_payloads'/f"{job['condition_id']}.json";dump(path,payload)
    return path,headline

def verify_xlsx(path,payload_path):
    data=read(payload_path);ns={'s':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
    with zipfile.ZipFile(path) as z:
        assert z.testzip() is None
        sheets=ET.fromstring(z.read('xl/workbook.xml')).find('s:sheets',ns)
        expected=['实验结果']+[s['name'] for s in data['sheets']] if data['kind']=='condition' else ['54组进度']
        assert [s.attrib['name'] for s in sheets]==expected
        for i,s in enumerate(data.get('sheets',[]),2):
            xml=ET.fromstring(z.read(f'xl/worksheets/sheet{i}.xml'))
            rows=xml.findall('s:sheetData/s:row',ns)
            assert len(rows)==len(s['rows'])+1,(s['name'],len(rows),len(s['rows']))
        for name in z.namelist():
            if re.fullmatch(r'xl/worksheets/sheet\d+\.xml',name):
                root=ET.fromstring(z.read(name));assert not root.findall('.//s:c[@t="e"]',ns),name
        if data['kind']=='condition':
            charts=[n for n in z.namelist() if re.fullmatch(r'xl/(?:drawings/)?charts/chart\d+\.xml',n)]
            assert len(charts)==1
            chart=ET.fromstring(z.read(charts[0]))
            assert len(chart.findall('.//{http://schemas.openxmlformats.org/drawingml/2006/chart}ser'))==3
    return {'zip_integrity':True,'sheet_names_and_row_counts':True,'no_formula_errors':True,'sha256':sha(path),'bytes':Path(path).stat().st_size}

def node_export(payload_path,log):
    with Path(log).open('w',encoding='utf-8') as stream:
        result=subprocess.run([str(NODE),'--max-old-space-size=8192',str(BUILDER),str(payload_path)],
            cwd=OUT,env=public_env(),stdout=stream,stderr=subprocess.STDOUT)
    if result.returncode:raise RuntimeError('Excel export failed; inspect '+str(log))

def export_job(job):
    payload,head=prepare_payload(job)
    verification=None
    if Path(job['xlsx_file']).is_file():
        try:verification=verify_xlsx(job['xlsx_file'],payload)
        except (AssertionError,zipfile.BadZipFile,KeyError):pass
    if verification is None:
        node_export(payload,BATCH/'console'/f"export-{job['condition_id']}.log")
        verification=verify_xlsx(job['xlsx_file'],payload)
    job.update(status='completed_exported',last_completed_tick=10,export_verified=verification,
        final_believe=head['final']['all_believe'],final_reject=head['final']['all_reject'],
        tbu_engineering=head['final'].get('tbu_engineering'),requests=head['budget']['requests'],actual_input_tokens=head['budget']['actual_input_tokens'],
        actual_output_tokens=head['budget']['actual_output_tokens'],duration_minutes=head['duration_minutes'],completed_china=head['finished_china'],
        llm_believe_decisions=head['llm_believe_decisions'])
    if 'all_uncertain' in head['final']:job['final_uncertain']=head['final']['all_uncertain']
    else:job.pop('final_uncertain',None)

def export_overview(m):
    extra=[] if all(j['config'].get('belief_measurement_policy')==BINARY_SCORE_POLICY for j in m['jobs']) else ['final_uncertain']
    columns=['condition_id',*FACTORS,'status','last_completed_tick','final_believe',*extra,'final_reject','tbu_engineering',
             'llm_believe_decisions','requests','actual_input_tokens','actual_output_tokens','duration_minutes','xlsx_file','run_dir']
    rows=[]
    for j in m['jobs']:
        vals={**j['config'],**j};rows.append([vals.get(k) for k in columns])
    payload=dict(kind='overview',output=str(OUT/'54组结果总览.xlsx'),columns=columns,rows=rows,
        completed_count=m['completed_count'],status=m['status'],updated=m['updated_china'],preview_dir=str(BATCH/'previews/overview'))
    path=BATCH/'export_payloads/overview.json';dump(path,payload)
    node_export(path,BATCH/'console/export-overview.log');verify_xlsx(payload['output'],path)

@contextlib.contextmanager
def batch_lock():
    import msvcrt
    stream=(BATCH/'batch.lock').open('a+b');stream.seek(0);stream.write(b'0');stream.flush();stream.seek(0)
    try:msvcrt.locking(stream.fileno(),msvcrt.LK_NBLCK,1)
    except OSError:stream.close();raise RuntimeError('The batch controller is already running') from None
    try:yield
    finally:stream.seek(0);msvcrt.locking(stream.fileno(),msvcrt.LK_UNLCK,1);stream.close()

def authenticate(m):
    from openai import OpenAI
    from llm_client import request_options
    cfg=m['jobs'][0]['config']
    if cfg.get('api_key_mode')=='windows_dpapi_failover':
        from credentials import validate_credentials
        validate_credentials(cfg)
        print('Using encrypted local primary/backup keys; authentication and failover occur in the audited simulation client.',flush=True)
        return True
    print('V6 Batch54: 54 conditions, 10 steps each. One completed condition will be reused.',flush=True)
    print('The remaining 53 conditions make real MiniMax requests. Keep this window open.',flush=True)
    for attempt in range(3):
        key=os.environ.get('RUMOR_LLM_API_KEY') or getpass.getpass('MiniMax Token Plan key (hidden; not saved): ').strip()
        if not key.startswith('sk-cp-'):
            print('Enter a China MiniMax subscription key beginning sk-cp-.',flush=True);os.environ.pop('RUMOR_LLM_API_KEY',None);continue
        try:
            options=request_options(cfg);options['max_tokens']=32
            with OpenAI(api_key=key,base_url=cfg['base_url'],timeout=30,max_retries=0) as client:
                response=client.chat.completions.create(model=cfg['model'],messages=[{'role':'user','content':'Return exactly {"ok":true} and nothing else.'}],**options)
            assert json.loads(response.choices[0].message.content.strip())=={'ok':True}
            dump(BATCH/'authentication_check.json',dict(time_china=now(),status='success',model=response.model,
                input_tokens=getattr(response.usage,'prompt_tokens',None),output_tokens=getattr(response.usage,'completion_tokens',None),synthetic_not_research_data=True))
            os.environ['RUMOR_LLM_API_KEY']=key;key=None
            print('Authentication succeeded. Starting sequential queue.',flush=True);return True
        except Exception as exc:
            code=getattr(exc,'status_code',None)
            dump(BATCH/'authentication_check.json',dict(time_china=now(),status='failed',http_status=code,error_type=type(exc).__name__))
            print(f'Connection check failed: HTTP {code}, {type(exc).__name__}.',flush=True)
            os.environ.pop('RUMOR_LLM_API_KEY',None);key=None
    return False

def start_job(m,j):
    assert hashes()==m['signature'],'Frozen research code or inputs changed; refusing mixed versions'
    assert sha(j['config_file'])==j['config_sha256'],'Frozen condition configuration changed'
    command=[sys.executable,str(ROOT/'app_v6/run.py'),'--config',j['config_file'],'--steps','10','--max-requests',str(j['config']['max_requests']),'--live','--token-plan-run']
    previous=j.get('run_dir')
    if previous:
        state=read(Path(previous)/'status.json')
        if state['status'] in ['paused_quota','paused_prompt_budget']:
            j['status']=state['status'];m['status']=state['status'];persist(m);return False
        if state.get('error_type') not in [None,'KeyboardInterrupt']:
            j['status']='needs_attention';j['error_type']=state.get('error_type');persist(m);return True
        # Uncertain in-flight requests must be reviewed, never blindly reissued.
        audit=Path(read(Path(previous)/'provenance.json')['audit_dir'])
        if any(read(p).get('status')=='pending_usage_unknown' for p in audit.glob('request-*.json')):
            j['status']='needs_attention';j['error_type']='UncertainRequest';persist(m);return True
        command+=['--resume',previous]
    started=time.time();log=BATCH/'console'/f"run-{j['condition_id']}-{len(j['attempts'])+1}.log"
    j['status']='running';j['started_china']=now();m['active_condition']=j['condition_id'];m['active_tick']=j.get('last_completed_tick',0)
    with log.open('w',encoding='utf-8') as stream:
        child=subprocess.Popen(command,cwd=ROOT,env=dict(os.environ,PYTHONIOENCODING='utf-8'),stdout=stream,stderr=subprocess.STDOUT)
        j['attempts'].append(dict(started_china=now(),pid=child.pid,console_log=str(log)));m['child_pid']=child.pid;persist(m)
        print(f"Running {j['condition_id']}; PID={child.pid}; completed Excel {m['completed_count']}/54",flush=True)
        while child.poll() is None:
            latest=ROOT/'runs/v6/latest.json'
            if latest.exists():
                pointer=read(latest);candidate=Path(pointer['run_dir'])
                if candidate.exists() and candidate.stat().st_ctime>=started-2 and (candidate/'provenance.json').exists():
                    p=read(candidate/'provenance.json')
                    if p['config']==j['config']:
                        j['run_dir']=str(candidate);j['last_completed_tick']=pointer.get('last_completed_tick',0);m['active_tick']=j['last_completed_tick']
            persist(m);time.sleep(5)
        j['attempts'][-1]['exit_code']=child.returncode;j['attempts'][-1]['ended_china']=now()
    m.pop('child_pid',None)
    if not j.get('run_dir') or j['run_dir']==previous:
        # A very fast child may finish between polling intervals. Discover it by
        # exact config and creation time, never by an unrelated latest pointer.
        candidates=[]
        for d in (ROOT/'runs/v6').glob('government-rumor-v6-openai-*'):
            if d.stat().st_ctime>=started-2 and (d/'provenance.json').is_file() and read(d/'provenance.json')['config']==j['config']:
                candidates.append(d)
        if candidates:j['run_dir']=str(sorted(candidates)[-1])
    if j.get('run_dir') and complete(j['run_dir']):
        j['status']='completed_pending_export';persist(m)
        try:export_job(j)
        except Exception as exc:
            j['status']='export_failed';j['error_type']=type(exc).__name__;j['export_error']=str(exc)
        persist(m);export_overview(m);return True
    if j.get('run_dir') and (Path(j['run_dir'])/'status.json').exists():
        state=read(Path(j['run_dir'])/'status.json');j.update(status=state['status'],error_type=state.get('error_type'),last_completed_tick=state['last_completed_tick'])
        if state['status']=='paused_quota':m['status']='paused_quota';persist(m);export_overview(m);return False
    else:j.update(status='launch_failed',error_type='InitializationFailure')
    # A failed condition is recorded, never exported as a completed result.
    persist(m);export_overview(m);return True

def execute(m):
    with batch_lock():
        m['controller_pid']=os.getpid();m['status']='awaiting_key';persist(m)
        if not authenticate(m):m['status']='authentication_failed';persist(m);return 2
        import ctypes
        ctypes.windll.kernel32.SetThreadExecutionState(0x80000001)
        try:
            m['status']='running';persist(m)
            for j in m['jobs']:
                if j['status']=='completed_exported' and Path(j['xlsx_file']).is_file():continue
                if j.get('run_dir') and complete(j['run_dir']):
                    try:export_job(j)
                    except Exception as exc:j.update(status='export_failed',error_type=type(exc).__name__,export_error=str(exc))
                    persist(m);export_overview(m);continue
                if j['status']=='needs_attention':continue
                if not start_job(m,j):return 3
            m['status']='completed' if all(j['status']=='completed_exported' for j in m['jobs']) else 'needs_attention'
            m['active_condition']=None;m['active_tick']=0;persist(m);export_overview(m)
            print(f"Batch {m['status']}: {m['completed_count']}/54 Excel files.",flush=True)
            return 0 if m['status']=='completed' else 4
        finally:
            ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)
            os.environ.pop('RUMOR_LLM_API_KEY',None)

def main():
    parser=argparse.ArgumentParser();parser.add_argument('mode',choices=['prepare','export-existing','run','status'])
    args=parser.parse_args();m=prepare()
    if args.mode=='prepare':print(json.dumps({'batch':str(BATCH),'conditions':54,'reused_complete_runs':m['complete_run_count'],'remaining':54-m['complete_run_count']},ensure_ascii=False));return 0
    if args.mode=='status':
        print(json.dumps({k:v for k,v in m.items() if k not in ['jobs','signature']},ensure_ascii=False,indent=2));return 0
    if args.mode=='export-existing':
        with batch_lock():
            for j in m['jobs']:
                if j.get('run_dir') and complete(j['run_dir']) and j['status']!='completed_exported':export_job(j);persist(m)
            export_overview(m)
        print(f"Excel files exported: {m['completed_count']}/54");return 0
    return execute(m)

if __name__=='__main__':
    try:raise SystemExit(main())
    except KeyboardInterrupt:
        print('Batch interrupted; committed data preserved. Restart the launcher to inspect/resume.',flush=True)
        raise SystemExit(130)
