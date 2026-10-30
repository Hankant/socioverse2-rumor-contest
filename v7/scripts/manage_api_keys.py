"""Manage encrypted MiniMax slots or explicitly request tiny connection checks."""
from pathlib import Path
import argparse
from datetime import datetime
import getpass
import json
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app_v7"))
from credentials import save_keys, load_keys, update_key, add_primary_key, add_second_primary, vault_path, MINIMAX_CN, KEY_SLOTS


def check_keys():
    from openai import OpenAI
    from llm_client import request_options, parse_json_object
    from local_cli import load_local_defaults
    cfg = load_local_defaults()
    if cfg.get("base_url") != MINIMAX_CN or cfg.get("api_profile") != "minimax_m3":
        raise ValueError("Credential check is restricted to the configured MiniMax China endpoint")
    records = []
    for slot, key in load_keys().items():
        started = time.monotonic()
        record = {"api_key_slot": slot, "model": cfg["model"], "base_url": MINIMAX_CN,
                  "synthetic_not_research_data": True, "time_local": datetime.now().astimezone().isoformat()}
        try:
            options = request_options(cfg)
            options["max_tokens"] = 32
            with OpenAI(api_key=key, base_url=MINIMAX_CN, timeout=30, max_retries=0) as client:
                response = client.chat.completions.create(model=cfg["model"], messages=[{
                    "role": "user", "content": 'Return exactly {"ok":true} and nothing else.'}], **options)
            base = getattr(response, "base_resp", None)
            code = base.get("status_code") if isinstance(base, dict) else None
            record["service_status_code"] = code if isinstance(code, int) else None
            choice = response.choices[0] if response.choices else None
            record["status"] = "success" if (not code and choice and choice.finish_reason == "stop"
                and parse_json_object(choice.message.content) == {"ok": True}) else "failed"
            record.update(returned_model=response.model, input_tokens=getattr(response.usage,"prompt_tokens",None),
                          output_tokens=getattr(response.usage,"completion_tokens",None))
        except Exception as exc:
            body = getattr(exc,"body",None)
            base = body.get("base_resp",{}) if isinstance(body,dict) else {}
            code = base.get("status_code") if isinstance(base,dict) else None
            record.update(status="failed", http_status=getattr(exc,"status_code",None),
                          service_status_code=code if isinstance(code,int) else None, error_type=type(exc).__name__)
        record["elapsed_seconds"] = round(time.monotonic()-started,3)
        records.append(record)
        print(json.dumps(record,ensure_ascii=False),flush=True)
    folder = ROOT / "runtime/v6/connection_checks"
    folder.mkdir(parents=True,exist_ok=True)
    (folder / ("key-checks-"+datetime.now().strftime("%Y%m%d-%H%M%S-%f")+".json")).write_text(
        json.dumps(records,ensure_ascii=False,indent=2),encoding="utf-8")
    return 0 if all(r["status"]=="success" for r in records) else 1


def main():
    parser = argparse.ArgumentParser(description="MiniMax Windows encrypted credential vault; no key is printed")
    parser.add_argument("action",choices=["set","set-slot","add-primary","add-primary2","status","check"])
    parser.add_argument("--slot",choices=list(KEY_SLOTS))
    args = parser.parse_args()
    if args.action=="set":
        primary=getpass.getpass("Primary MiniMax subscription key (hidden): ")
        backup=getpass.getpass("Backup MiniMax API key (hidden): ")
        third=getpass.getpass("Third MiniMax API key (hidden; enter to omit): ").strip()
        fourth=getpass.getpass("Fourth MiniMax API key (hidden; enter to omit): ").strip() if third else ''
        save_keys(primary,backup,third=third or None,fourth=fourth or None)
        print("Keys saved with CurrentUser DPAPI encryption. Routing state reset.")
    elif args.action=="add-primary":
        key=getpass.getpass("New primary MiniMax subscription key (hidden): ")
        add_primary_key(key)
        key=None
        print("Encrypted primary added. Existing keys and their cooldowns retained; next request starts at primary.")
    elif args.action=="add-primary2":
        key=getpass.getpass("Second primary MiniMax subscription key (hidden): ")
        add_second_primary(key);key=None
        print("Second primary saved with CurrentUser DPAPI encryption. Existing slot identities and cooldowns retained.")
    elif args.action=="set-slot":
        if not args.slot:raise ValueError('set-slot requires --slot')
        key=getpass.getpass("Replacement MiniMax key (hidden): ")
        update_key(args.slot,key)
        key=None
        print("Encrypted slot updated: "+args.slot+". Other slots retained; routing reset.")
    elif args.action=="status":
        keys=load_keys()
        print("Encrypted slots available: "+", ".join(keys)+". Key values are hidden.")
        print("Vault:",vault_path())
        state=vault_path().parent/"routing-state.json"
        if state.exists():print(state.read_text(encoding="utf-8"))
        state=vault_path().parent/"routing-round-robin.json"
        if state.exists():print(state.read_text(encoding="utf-8"))
    else:
        return check_keys()
    return 0


if __name__=="__main__":
    try:raise SystemExit(main())
    except (ValueError,RuntimeError) as exc:
        print(str(exc),file=sys.stderr)
        raise SystemExit(2)
