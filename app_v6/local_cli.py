"""Local V6 launcher and preflight. Preview/offline/doctor never call the API."""
from __future__ import annotations
import argparse
import csv
from datetime import datetime
import getpass
import importlib.metadata
import itertools
import json
import os
from pathlib import Path
import subprocess
import sys
import signal

from model import dump, digest, load_rows
from run import ROOT, SOURCE, defaults, make_bundles
from experiment import assignment_summary, validate_experiment
from government import validate

LOCAL = ROOT/'configs/local_defaults.json'


def run_child(command):
    # The child owns Ctrl+C and its recovery menu. A callable no-op, rather
    # than SIG_IGN, avoids passing an ignore-Ctrl+C flag to Windows children.
    previous = signal.getsignal(signal.SIGINT)
    try:
        signal.signal(signal.SIGINT, lambda signum, frame: None)
        return subprocess.call(command, cwd=ROOT)
    finally:
        signal.signal(signal.SIGINT, previous)


def load_local_defaults():
    return json.loads(LOCAL.read_text(encoding='utf-8'))


def condition_id(cfg):
    return (f"D{round(cfg['source_trust_gap']*100):03d}_T{cfg['government_tick']:02d}_"
            f"C{round(cfg['targeting_inside_ratio']*100):03d}_G{round(cfg['government_trust_mean']*100):03d}")


def config_for(args):
    cfg={**defaults(),**load_local_defaults()}
    if getattr(args,'config',None):
        path=Path(args.config).resolve()
        overrides=json.loads(path.read_text(encoding='utf-8-sig'))
        if any(k in overrides for k in ('api_key','RUMOR_LLM_API_KEY','authorization')):
            raise ValueError('Never store credentials in a config file')
        unknown=set(overrides)-set(defaults())-{'api_profile'}
        if unknown:raise ValueError('Unknown configuration fields: '+', '.join(sorted(unknown)))
        cfg.update(overrides)
    mapping=dict(gap='source_trust_gap',tg='government_tick',target='targeting_inside_ratio',
        gt='government_trust_mean',concurrency='max_concurrency',prompt_limit='prompt_input_token_limit',
        memory_policy='prompt_memory_policy',max_requests='max_requests',behavior_seed='behavior_seed',
        source_trust_seed='source_trust_seed',target_seed='government_target_seed',trust_seed='government_trust_seed',
        input_budget='max_input_reserved_units',output_budget='max_output_reserved_tokens')
    for key,field in mapping.items():
        value=getattr(args,key,None)
        if value is not None:
            cfg[field]=value
    validate(cfg); validate_experiment(cfg)
    if cfg['source_trust_gap'] is None or cfg['government_trust_mean'] is None or cfg['targeting_inside_ratio'] is None:
        raise ValueError('The local research launcher needs explicit values for all four factors')
    if cfg['government_tick'] not in (2,4,7):
        raise ValueError('Local study intervention conditions are 2, 4 or 7, once per independent run')
    if cfg['targeting_inside_ratio'] not in (.2,.8) or cfg['government_trust_mean'] not in (.25,.5,.75):
        raise ValueError('Local study targeting levels are .2/.8; government trust levels are .25/.5/.75')
    return cfg


def preview(cfg, steps=10, output=None):
    stamp=datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    folder=Path(output) if output else ROOT/'runtime/v6/preflight'/f'{condition_id(cfg)}-{stamp}'
    folder.mkdir(parents=True,exist_ok=False)
    rows=load_rows(SOURCE/'01_Agent基础信息表.csv')
    bundles=make_bundles(SOURCE/'01_Agent基础信息表.csv',SOURCE/'02_Prompt固定提示词.md',cfg,folder/'audit',steps=steps)
    args=bundles[1].provider_args
    selected=set(args['direct_targets'])
    summary=assignment_summary(rows,args['source_trust'],args['government_trust'])
    summary['condition_id']=condition_id(cfg)
    summary['steps']=steps
    summary['targets']={group:sum(r['group']==group and r['agent_id'] in selected for r in rows) for group in ('inside','outside')}
    summary['government_reach']=len(selected)
    summary['targeting_definition']='proportion_of_recipients_inside_not_current_believer_detection'
    summary['rule_source_trust_mode']=cfg['rule_source_trust_mode']
    summary['prompt_policy']={k:cfg[k] for k in ('prompt_input_token_limit','prompt_memory_policy','belief_measurement_policy','llm_max_output_tokens')}
    summary['feed_policy']=cfg.get('feed_policy','legacy')
    summary['decision_condition_policy']=cfg.get('decision_condition_policy','legacy')
    summary['comment_target']=cfg.get('comment_target','first_displayed_post')
    summary['memory_retention_policy']=cfg.get('memory_retention_policy','last_five_experiences_v1')
    summary['memory_window_ticks']=cfg.get('memory_window_ticks')
    summary['wire_prompt_style']=cfg.get('wire_prompt_style','standard')
    summary['comment_window_limit']=cfg.get('comment_window_limit')
    from collections import Counter
    summary['synthetic_population']={k:dict(Counter(r.get(k,'') for r in rows)) for k in
        ('synthetic_mbti_type','synthetic_age_band','synthetic_region','synthetic_occupation')}
    summary['budget']={k:cfg[k] for k in ('max_requests','max_input_reserved_units','max_output_reserved_tokens')}
    summary['warnings']=[
        'No API call was made; preview is not a behavioral experiment.',
        'LLM trust is a role input, not a calibrated output probability.',
        'Rule correction remains absorbing after a passed GT draw.',
        '32768 proxy tokens are an application guard, not a supplier tokenizer or a guarantee of quota.',
        'Fixed seeds do not make provider LLM responses deterministic.',
    ]
    dump(folder/'config.json',cfg)
    dump(folder/'assignment_summary.json',summary)
    dump(folder/'source_trust.json',args['source_trust'])
    dump(folder/'government_trust.json',args['government_trust'])
    dump(folder/'government_targets.json',args['direct_targets'])
    with (folder/'agent_parameters.csv').open('w',encoding='utf-8-sig',newline='') as stream:
        new_fields=['synthetic_age','synthetic_age_band','synthetic_region','synthetic_settlement','synthetic_occupation','synthetic_mbti_type','synthetic_personality_description','synthetic_role_experience']
        writer=csv.DictWriter(stream,fieldnames=['agent_id','decision_mode','group',*new_fields,'initial_source_trust','government_trust','direct_target','rule_pb'])
        writer.writeheader()
        for r in rows:
            aid=r['agent_id']
            writer.writerow(dict(agent_id=aid,decision_mode=r['decision_mode'],group=r['group'],
                **{k:r.get(k,'') for k in new_fields},initial_source_trust=args['source_trust'][aid],government_trust=args['government_trust'][aid],direct_target=aid in selected,
                rule_pb=(args['source_trust'][aid] if cfg['rule_source_trust_mode']=='individual_pb' else .579) if r['decision_mode']=='rule' else ''))
    from model import V4Environment
    from llm_client import render_prompt, prepare_prompt
    env=V4Environment(bundles[1]);env.reset(cfg['behavior_seed']);env.advance_to(1)
    aid=next(r['agent_id'] for r in rows if r['decision_mode']=='llm' and r['group']=='inside')
    ob=env.observe(aid,1)
    template=(SOURCE/'02_Prompt固定提示词.md').read_text(encoding='utf-8').split('```text',1)[1].split('```',1)[0].strip()
    concise=cfg.get('wire_prompt_style','standard') in ('concise_lossless_v1','concise_shared_prefix_v1')
    if concise:
        from concise_wire import validate_template
        validate_template(template)
    prompt,feed,memory,estimate=prepare_prompt(template,ob,limit=2_000_000 if concise else cfg['prompt_input_token_limit'],
        memory_policy=cfg['prompt_memory_policy'],encoding=cfg.get('prompt_encoding','full_json_v1'))
    from response_contract import wire_prompt
    from llm_client import estimated_input_tokens,PromptBudgetPause
    prompt=wire_prompt(prompt,ob,cfg['llm_max_output_tokens'],style=cfg.get('wire_prompt_style','standard'))
    estimate=estimated_input_tokens(prompt)
    if estimate>cfg['prompt_input_token_limit']:
        raise PromptBudgetPause('preview actual wire input exceeds configured limit')
    (folder/'sample_prompt_tick1.txt').write_text(prompt,encoding='utf-8')
    summary['first_sample_prompt_proxy_tokens']=estimate
    dump(folder/'assignment_summary.json',summary)
    print(f"条件 {condition_id(cfg)}：10轮、{cfg['government_reach']}名直接接收者；圈内{summary['targets']['inside']} / 圈外{summary['targets']['outside']}")
    print(f"SOURCE均值 inside={summary['source_trust']['all/inside']['mean']:.6f}, outside={summary['source_trust']['all/outside']['mean']:.6f}; GT全体均值={summary['government_trust']['all/all']['mean']:.6f}")
    print(f"预检文件：{folder}")
    return folder,summary


def run_one(args,live=False):
    cfg=config_for(args)
    folder,_=preview(cfg,args.steps)
    command=[sys.executable,str(ROOT/'app_v6/run.py'),'--config',str(folder/'config.json'),
             '--steps',str(args.steps),'--max-requests',str(cfg['max_requests'])]
    if getattr(args,'no_interactive_recovery',False):
        command+=['--no-interactive-recovery']
    else:
        print('运行期间 Ctrl+C 可暂停；发生故障后将显示恢复菜单，R/回车继续、W等待、L调整上限、S保存退出。',flush=True)
    added_key=False
    if live:
        if cfg.get('api_key_mode')=='windows_dpapi_failover':
            from credentials import validate_credentials
            validate_credentials(cfg)
            if cfg.get('api_routing_policy')=='round_robin_v1':
                from credentials import load_keys
                print('Using encrypted MiniMax keys: '+' -> '.join(load_keys())+'; skip unavailable slots and retain shared budgets.',flush=True)
            else:
                print('Using encrypted local MiniMax keys: primary first, backup on service refusal; primary retry every hour.',flush=True)
        else:
            if not sys.stdin.isatty() and not os.environ.get('RUMOR_LLM_API_KEY'):
                raise ValueError('Live mode needs an interactive terminal for hidden key entry, or RUMOR_LLM_API_KEY in this process environment')
            if not os.environ.get('RUMOR_LLM_API_KEY'):
                os.environ['RUMOR_LLM_API_KEY']=getpass.getpass('MiniMax Token Plan key (hidden; not saved): ').strip()
                added_key=True
        command+=['--live','--token-plan-run']
    try:
        return run_child(command)
    finally:
        if added_key:
            os.environ.pop('RUMOR_LLM_API_KEY',None)


def design(args):
    base=config_for(args)
    dest=ROOT/'configs/research54'
    dest.mkdir(parents=True,exist_ok=True)
    records=[]
    rows=load_rows(SOURCE/'01_Agent基础信息表.csv')
    from government import select_targets,trust_values
    from experiment import source_trust_values
    for gap,tick,ratio,mu in itertools.product((0,.2,.4),(2,4,7),(.2,.8),(.25,.5,.75)):
        cfg={**base,'source_trust_gap':gap,'government_tick':tick,'targeting_inside_ratio':ratio,'government_trust_mean':mu}
        targets=select_targets(rows,cfg);source=source_trust_values(rows,cfg);gov=trust_values(rows,cfg)
        name=condition_id(cfg)
        dump(dest/(name+'.json'),cfg)
        records.append(dict(condition_id=name,source_trust_gap=gap,source_inside_mean=cfg['source_trust_center']+gap/2,source_outside_mean=cfg['source_trust_center']-gap/2,
            government_tick=tick,targeting_inside_ratio=ratio,government_reach=cfg['government_reach'],government_trust_mean=mu,
            source_assignment_hash=digest(source),government_assignment_hash=digest(gov),targets_hash=digest(targets),
            config_file=str(dest/(name+'.json'))))
    with (dest/'design_matrix.csv').open('w',encoding='utf-8-sig',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(records[0]));writer.writeheader();writer.writerows(records)
    dump(dest/'design_manifest.json',{'factors':{'source_trust_gap':[0,.2,.4],'government_tick':[2,4,7],
        'targeting_inside_ratio':[.2,.8],'government_trust_mean':[.25,.5,.75]},'conditions':54,'runs_executed':0,
        'repeat_count':1,'note':'Configurations only; no live runs are automatically started'})
    print(f'已生成54个条件（未启动实验）：{dest}')


def doctor():
    packages=['numpy','pandas','pyarrow','pydantic','duckdb','openai','httpx','tiktoken','pytest','SocioVerse2']
    result={'python':sys.version,'executable':sys.executable,'deployment_root':str(ROOT),
        'packages':{name:importlib.metadata.version(name) for name in packages},
        'roster_count':len(load_rows(SOURCE/'01_Agent基础信息表.csv')),
        'local_default_config_exists':LOCAL.is_file(),
        'credential_present_in_environment':bool(os.environ.get('RUMOR_LLM_API_KEY')),
        'credential_mode':load_local_defaults().get('api_key_mode','environment'),
        'paid_requests_made':0}
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return result


def status():
    latest=ROOT/'runs/v6/latest.json'
    if not latest.exists():
        print('当前部署尚无运行记录。');return
    state=json.loads(latest.read_text(encoding='utf-8'))
    print(json.dumps(state,ensure_ascii=False,indent=2))
    p=Path(state['run_dir'])/'trajectory/metrics_history.json'
    if p.is_file():
        rows=json.loads(p.read_text(encoding='utf-8'))['rows']
        if rows:print(json.dumps(rows[-1],ensure_ascii=False,indent=2))


def resume(args):
    if getattr(args,'parent',None):
        parent=Path(args.parent).resolve()
    else:
        latest=ROOT/'runs/v6/latest.json'
        if not latest.exists():raise ValueError('尚无运行记录，请先启动一个实验')
        parent=Path(json.loads(latest.read_text(encoding='utf-8'))['run_dir']).resolve()
    print('准备续跑：'+str(parent),flush=True)
    prov=json.loads((parent/'provenance.json').read_text(encoding='utf-8'))
    steps=prov['total_steps'];cfg=dict(prov['config']);live=prov['mode']=='openai'
    changed=False
    if getattr(args,'prompt_encoding',None):cfg['prompt_encoding']=args.prompt_encoding
    if getattr(args,'wire_prompt_style',None):cfg['wire_prompt_style']=args.wire_prompt_style
    for arg,field in [('prompt_limit','prompt_input_token_limit'),('input_budget','max_input_reserved_units'),('output_budget','max_output_reserved_tokens')]:
        value=getattr(args,arg,None)
        if value is not None:
            if value < cfg[field]:raise ValueError('Resume limits may only increase: '+field)
            changed = changed or value != cfg[field]
            cfg[field]=value
    validate_experiment(cfg)
    folder=ROOT/'runtime/v6/resume_configs';folder.mkdir(parents=True,exist_ok=True)
    path=folder/(datetime.now().strftime('%Y%m%d-%H%M%S-%f')+'.json');dump(path,cfg)
    command=[sys.executable,str(ROOT/'app_v6/run.py'),'--resume',str(parent),'--config',str(path),
        '--steps',str(steps),'--max-requests',str(cfg['max_requests'])]
    if changed:command+=['--execution-limit-migration']
    if getattr(args,'format_migration_manifest',None):command+=['--format-migration-manifest',str(Path(args.format_migration_manifest).resolve())]
    if getattr(args,'input_migration_manifest',None):command+=['--input-migration-manifest',str(Path(args.input_migration_manifest).resolve())]
    if getattr(args,'maintenance_migration_manifest',None):command+=['--maintenance-migration-manifest',str(Path(args.maintenance_migration_manifest).resolve())]
    if getattr(args,'expression_migration_manifest',None):command+=['--expression-migration-manifest',str(Path(args.expression_migration_manifest).resolve())]
    if getattr(args,'no_interactive_recovery',False):command+=['--no-interactive-recovery']
    added=False
    if live:
        if cfg.get('api_key_mode')=='windows_dpapi_failover':
            from credentials import validate_credentials
            validate_credentials(cfg)
        elif not os.environ.get('RUMOR_LLM_API_KEY'):
            if not sys.stdin.isatty():raise ValueError('Live resume needs hidden key entry in an interactive terminal')
            os.environ['RUMOR_LLM_API_KEY']=getpass.getpass('MiniMax Token Plan key (hidden; not saved): ').strip();added=True
        command+=['--live','--token-plan-run']
    try:return run_child(command)
    finally:
        if added:os.environ.pop('RUMOR_LLM_API_KEY',None)


def main():
    parser=argparse.ArgumentParser(description='本地V6：预检、离线、真实运行、配置矩阵、检查与续跑')
    sub=parser.add_subparsers(dest='mode',required=True)
    for mode in ['preview','offline','live','design']:
        p=sub.add_parser(mode)
        p.add_argument('--gap',type=float,choices=[0,.2,.4]);p.add_argument('--tg',type=int,choices=[2,4,7])
        p.add_argument('--target',type=float,choices=[.2,.8]);p.add_argument('--gt',type=float,choices=[.25,.5,.75])
        p.add_argument('--steps',type=int,default=10,choices=range(1,41));p.add_argument('--concurrency',type=int,choices=range(1,11))
        p.add_argument('--prompt-limit',type=int);p.add_argument('--memory-policy',choices=['trim_oldest','preserve'])
        p.add_argument('--max-requests',type=int);p.add_argument('--input-budget',type=int);p.add_argument('--output-budget',type=int)
        p.add_argument('--behavior-seed',type=int);p.add_argument('--source-trust-seed',type=int);p.add_argument('--target-seed',type=int);p.add_argument('--trust-seed',type=int)
        p.add_argument('--config',help='Explicit JSON overrides; do not put credentials here')
        p.add_argument('--no-interactive-recovery',action='store_true',help='暂停后返回退出码2，不等待按键（供批处理使用）')
    sub.add_parser('doctor');sub.add_parser('status')
    p=sub.add_parser('resume');p.add_argument('--parent',help='原结果目录；省略时使用 latest.json 指向的运行')
    p.add_argument('--prompt-limit',type=int);p.add_argument('--input-budget',type=int);p.add_argument('--output-budget',type=int)
    p.add_argument('--no-interactive-recovery',action='store_true')
    p.add_argument('--format-migration-manifest',help='仅用于已核对的精确父实验格式修复清单')
    p.add_argument('--input-migration-manifest',help='仅用于已核对的精确父实验输入去重清单')
    p.add_argument('--maintenance-migration-manifest',help='仅用于已核对的精确父实验导出与恢复修复')
    p.add_argument('--expression-migration-manifest',help='仅用于已核对的保留完整内容的表达精简')
    p.add_argument('--wire-prompt-style',choices=['standard','concise_lossless_v1','concise_shared_prefix_v1'])
    p.add_argument('--prompt-encoding',choices=['full_json_v1','lossless_thread_refs_v1'],help='改变编码需经过精确父实验迁移校验')
    p=sub.add_parser('verify');p.add_argument('--run-dir',required=True)
    args=parser.parse_args()
    if args.mode=='doctor':doctor()
    elif args.mode=='status':status()
    elif args.mode=='preview':preview(config_for(args),args.steps)
    elif args.mode=='design':design(args)
    elif args.mode=='offline':return run_one(args,False)
    elif args.mode=='live':return run_one(args,True)
    elif args.mode=='resume':return resume(args)
    elif args.mode=='verify':
        from verify_run import verify
        verify(args.run_dir)
    return 0


if __name__=='__main__':
    try:
        raise SystemExit(main())
    except (ValueError,FileNotFoundError) as exc:
        print('配置/启动错误：'+str(exc),file=sys.stderr)
        raise SystemExit(2)
