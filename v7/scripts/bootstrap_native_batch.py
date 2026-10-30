"""Start the same V7 batch from an ordinary Windows console.

Packaged Codex redirects LocalAppData files. The ignored runtime pointer resolves
the original encrypted vault for an unpackaged console; DPAPI remains unchanged.
"""
from pathlib import Path
import sys,json,hashlib,os,ctypes
from ctypes import wintypes

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'app_v7'))
from model import read_json,dump
import credentials

def prepare():
    original=credentials.vault_path();source='default_current_user_vault'
    if not original.exists():
        pointer=read_json(ROOT/'runtime/v7/native_vault_location.json');physical=Path(pointer['vault_file'])
        if not physical.is_absolute() or not physical.is_file():raise ValueError('Original encrypted vault is unavailable')
        if hashlib.sha256(physical.read_bytes()).hexdigest()!=pointer['encrypted_file_sha256']:
            raise ValueError('Encrypted vault changed; refresh native location from the same Windows user before starting')
        credentials.vault_path=lambda:physical
        source='original_package_storage_resolved'
    import run
    cfg=run.read_config()
    credentials.validate_credentials(cfg)
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.GetCurrentProcess.restype=wintypes.HANDLE
    kernel.IsProcessInJob.argtypes=[wintypes.HANDLE,wintypes.HANDLE,ctypes.POINTER(wintypes.BOOL)]
    inside=wintypes.BOOL();ok=kernel.IsProcessInJob(kernel.GetCurrentProcess(),None,ctypes.byref(inside))
    report=dict(pid=os.getpid(),vault_source=source,encrypted_vault=str(credentials.vault_path()),
        configured_slots=list(credentials.load_keys()),job_query_ok=bool(ok),inside_job=bool(inside.value),
        plaintext_credentials_written=False,scientific_parameters_changed=False)
    dump(ROOT/'runtime/v7/native_bootstrap_status.json',report)
    return report

if __name__=='__main__':
    report=prepare()
    if '--check' in sys.argv:
        dump(ROOT/'runtime/v7/native_bootstrap_check.json',report)
        print(json.dumps(report,ensure_ascii=False))
    else:
        print('V7 native console: existing encrypted credentials verified; resuming saved batch.',flush=True)
        import batch54
        raise SystemExit(batch54.main())
