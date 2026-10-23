"""Interactive single-study launch with checkpoint recovery menus.

Saved-key mode uses the Windows DPAPI vault. Legacy environment/interactive
mode keeps credentials only in memory. Connection checks are not research data.
"""
from pathlib import Path
from datetime import datetime
import argparse
import getpass
import json
import os
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'app_v6'))
from local_cli import config_for, run_one
from llm_client import request_options


def main():
    parser=argparse.ArgumentParser(description='Check MiniMax authentication, then launch one live V6 study')
    parser.add_argument('--gap',type=float,default=.4,choices=[0,.2,.4])
    parser.add_argument('--tg',type=int,default=2,choices=[2,4,7])
    parser.add_argument('--target',type=float,default=.8,choices=[.2,.8])
    parser.add_argument('--gt',type=float,default=.75,choices=[.25,.5,.75])
    parser.add_argument('--steps',type=int,default=10)
    parser.add_argument('--concurrency',type=int,choices=range(1,11),default=None)
    parser.add_argument('--no-interactive-recovery',action='store_true')
    args=parser.parse_args()
    cfg=config_for(args)
    print(f'V6 live: ONE condition, {args.steps} rounds; version={cfg["runtime_version"]}; API concurrency cap={cfg["max_concurrency"]}.',flush=True)
    if cfg.get('api_key_mode')=='windows_dpapi_failover':
        # The simulation's first real call performs authentication through the
        # same audited failover path; do not let a separate primary-only check
        # prevent a valid backup from being used.
        from credentials import validate_credentials
        validate_credentials(cfg)
        return run_one(args,True)
    print('The first synthetic connection check is a real, small API call.',flush=True)
    print('Enter the Token Plan key only at the hidden prompt. It is never saved.',flush=True)
    folder=ROOT/'runtime/v6/connection_checks';folder.mkdir(parents=True,exist_ok=True)
    from openai import OpenAI
    for attempt in range(1,4):
        key=getpass.getpass('MiniMax Token Plan key (hidden): ').strip()
        if not key.startswith('sk-cp-'):
            print('This launcher needs a subscription key beginning with sk-cp-.',flush=True)
            continue
        started=time.monotonic()
        record=dict(time_local=datetime.now().astimezone().isoformat(),attempt=attempt,
                    model=cfg['model'],base_url=cfg['base_url'],synthetic_check=True)
        try:
            options=request_options(cfg);options['max_tokens']=32
            with OpenAI(api_key=key,base_url=cfg['base_url'],timeout=30,max_retries=0) as client:
                response=client.chat.completions.create(model=cfg['model'],
                    messages=[{'role':'user','content':'Return exactly this JSON object and nothing else: {"ok":true}'}],**options)
            record.update(status='success',elapsed_seconds=round(time.monotonic()-started,3),
                returned_model=response.model,input_tokens=getattr(response.usage,'prompt_tokens',None),
                output_tokens=getattr(response.usage,'completion_tokens',None))
            path=folder/(datetime.now().strftime('%Y%m%d-%H%M%S-%f')+'.json')
            path.write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
            print('Authentication succeeded. Starting the study with the same key.',flush=True)
            os.environ['RUMOR_LLM_API_KEY']=key
            key=None
            try:
                return run_one(args,True)
            finally:
                os.environ.pop('RUMOR_LLM_API_KEY',None)
        except Exception as exc:
            status=getattr(exc,'status_code',None)
            record.update(status='failed',http_status=status,error_type=type(exc).__name__,elapsed_seconds=round(time.monotonic()-started,3))
            path=folder/(datetime.now().strftime('%Y%m%d-%H%M%S-%f')+'.json')
            path.write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
            key=None
            print(f'Connection check failed: HTTP {status}, {type(exc).__name__}.',flush=True)
            if status==401:
                print('Check that this is an active China-region MiniMax Token Plan key. You may paste another key.',flush=True)
                continue
            return 1
    print('No valid authentication after three entries; no study was started.',flush=True)
    return 1


if __name__=='__main__':
    try:raise SystemExit(main())
    except KeyboardInterrupt:
        print('\nLaunch cancelled.',flush=True)
        raise SystemExit(130)
