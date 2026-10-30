"""Public V7 entry points. Preview/status/verify make no network requests."""
import argparse,importlib,json,sys
from pathlib import Path
import run
from model import V7Environment,load_rows,dump,read_json


def load_local_defaults():return run.read_config(run.ROOT/'configs/v7/local_defaults.json')


def latest_run():
    path=run.RESULTS/'latest.json'
    if not path.exists():raise ValueError('V7尚无正式运行记录；请先运行Preview-V7.cmd，再运行Run-V7.cmd。')
    return Path(read_json(path)['run_dir'])


def preview(cfg_path=None):
    cfg=run.read_config(cfg_path);rows=load_rows(run.SOURCE/'01_Agent基础信息表.csv')
    _,bundle,_,_=run.make_bundles(run.SOURCE/'01_Agent基础信息表.csv',run.SOURCE/'02_Prompt固定提示词.md',cfg,'unused-preview')
    env=V7Environment(bundle);env.reset(cfg['behavior_seed']);env.advance_to(1)
    obs=env.observe_batch(list(env.by_id),1);inside=sum(bool(o.local_information['posts']) for o in obs)
    env.advance_to(cfg['government_tick']);g=env.observe_batch(list(env.by_id),cfg['government_tick'])
    official=sum(any(p['content_id']=='G001' for p in o.local_information['posts']) for o in g)
    from llm_client import prepare_prompt,estimated_input_tokens,request_options
    from response_contract import wire_prompt
    from concise_wire import validate_template
    template=(run.SOURCE/'02_Prompt固定提示词.md').read_text(encoding='utf-8').split('```text',1)[1].split('```',1)[0].strip()
    validate_template(template);ob=next(o for o in obs if o.local_information['posts'])
    base,_,_,_=prepare_prompt(template,ob,limit=2_000_000,memory_policy='preserve',encoding=cfg['prompt_encoding'])
    wire=wire_prompt(base,ob,request_options(cfg)['max_tokens'],style=cfg['wire_prompt_style'])
    folder=run.ROOT/'runtime/v7/preview';folder.mkdir(parents=True,exist_ok=True)
    (folder/'first_agent_wire_prompt.txt').write_text(wire,encoding='utf-8')
    targets=bundle.provider_args['direct_targets'];by_id={r['agent_id']:r for r in rows}
    report=dict(population=300,inside=48,outside=252,all_decision_mode='llm',network_edges=len(bundle.provider_args['edges']),
        tick1_rumor_readers=inside,government_direct_readers=official,
        government_inside=sum(by_id[a]['group']=='inside' for a in targets),government_outside=sum(by_id[a]['group']=='outside' for a in targets),
        comment_limit_per_visible_root=30,memory_prior_simulation_ticks=3,first_agent_estimated_input_units=estimated_input_tokens(wire),
        api_requests=0,preview_prompt=str(folder/'first_agent_wire_prompt.txt'),config=str(cfg_path))
    from government import GOVERNMENT_PERSONA_POLICY,government_trust_role
    if cfg.get('government_trust_prompt_policy')==GOVERNMENT_PERSONA_POLICY:
        from collections import Counter
        report['government_trust_role_policy']=GOVERNMENT_PERSONA_POLICY
        report['government_trust_role_counts']=dict(Counter(government_trust_role(v)['label']for v in bundle.provider_args['government_trust'].values()))
        report['first_agent_government_trust']=ob.local_physical['government_trust']
        report['first_agent_government_trust_description']=government_trust_role(ob.local_physical['government_trust'])['prompt']
    dump(folder/'summary.json',report);return report


def main():
    p=argparse.ArgumentParser(description='V7: 300 LLM agents (48 inside /252 outside)')
    p.add_argument('mode',choices=('preview','live','resume','status','doctor','verify'))
    p.add_argument('--config',default=str(run.ROOT/'configs/v7/one_condition.json'));p.add_argument('--steps',type=int,default=10)
    p.add_argument('--run-dir');args=p.parse_args()
    if args.mode=='preview':result=preview(args.config)
    elif args.mode=='doctor':
        modules={name:getattr(importlib.import_module(name),'__version__','installed') for name in ('numpy','openai','duckdb','pydantic')}
        from credentials import vault_path
        result=dict(python=sys.executable,project=str(run.ROOT),dependencies=modules,encrypted_vault_present=vault_path().exists(),api_requests=0)
        preview(args.config)
    elif args.mode in ('status','verify'):
        folder=Path(args.run_dir) if args.run_dir else latest_run()
        if args.mode=='status':result=dict(run_dir=str(folder),**read_json(folder/'status.json'))
        else:
            from verify_run import verify
            result=verify(folder)
    else:
        import subprocess
        command=[sys.executable,str(run.CODE/'run.py'),'--config',args.config,'--steps',str(args.steps)]
        if args.mode=='resume':
            folder=Path(args.run_dir) if args.run_dir else latest_run();state=read_json(folder/'status.json')
            if state['status'].startswith('completed'):
                print('本组已经完成，无需续跑。结果目录：'+str(folder));return 0
            prov=read_json(folder/'provenance.json')
            command=[sys.executable,str(run.CODE/'run.py'),'--config',str(Path(prov['config_dir'])/'behavior_contract.json'),'--steps',str(prov['total_steps']),'--resume',str(folder)]
        return subprocess.call(command,cwd=run.ROOT)
    print(json.dumps(result,ensure_ascii=False,indent=2));return 0


if __name__=='__main__':
    try:raise SystemExit(main())
    except (ValueError,FileNotFoundError) as exc:print('V7：'+str(exc),file=sys.stderr);raise SystemExit(2)
