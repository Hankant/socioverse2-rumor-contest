"""Windows CurrentUser DPAPI vault. Plaintext keys never enter run artifacts."""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import json
import os
from datetime import datetime
from pathlib import Path

MINIMAX_CN = "https://api.minimax.cn/v1"
KEY_SLOTS = ('primary', 'backup', 'third', 'fourth', 'primary2')


def vault_path():
    return Path(os.environ["LOCALAPPDATA"]) / "SocioVerseV6" / "minimax-keys.dpapi"


def _crypt(data, decrypt=False):
    if os.name != "nt":
        raise RuntimeError("The credential vault requires Windows DPAPI for the current user")

    class Blob(ctypes.Structure):
        _fields_ = [("size", wintypes.DWORD), ("data", ctypes.POINTER(ctypes.c_ubyte))]

    buffer = ctypes.create_string_buffer(data)
    source = Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    output = Blob()
    crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p
    if decrypt:
        fn = crypt32.CryptUnprotectData
        fn.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p,
                       ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
        ok = fn(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(output))
    else:
        fn = crypt32.CryptProtectData
        fn.argtypes = [ctypes.POINTER(Blob), wintypes.LPCWSTR, ctypes.c_void_p,
                       ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
        # UI forbidden; LOCAL_MACHINE deliberately absent (CurrentUser scope).
        ok = fn(ctypes.byref(source), "SocioVerse V6 MiniMax", None, None, None, 1, ctypes.byref(output))
    if not ok:
        raise RuntimeError("Windows DPAPI credential operation failed")
    try:
        return ctypes.string_at(output.data, output.size)
    finally:
        kernel32.LocalFree(output.data)
        ctypes.memset(buffer, 0, len(data))


def save_keys(primary, backup, path=None, third=None, fourth=None, primary2=None):
    primary, backup = primary.strip(), backup.strip()
    if not primary.startswith("sk-cp-") or not backup.startswith("sk-") or primary == backup:
        raise ValueError("Expected different MiniMax primary subscription and backup API keys")
    record = dict(version=1, provider="minimax_cn", primary=primary, backup=backup)
    if third is not None:
        third=third.strip()
        if not third.startswith('sk-') or third in (primary,backup):
            raise ValueError('Expected three different MiniMax keys')
        record.update(version=2,third=third)
    if fourth is not None:
        fourth=fourth.strip()
        if third is None or not fourth.startswith('sk-') or fourth in (primary,backup,third):
            raise ValueError('Expected four different MiniMax keys with no missing slots')
        record.update(version=3,fourth=fourth)
    if primary2 is not None:
        primary2=primary2.strip()
        if fourth is None or not primary2.startswith('sk-cp-') or primary2 in (primary,backup,third,fourth):
            raise ValueError('Expected a different second primary subscription key and four existing slots')
        record.update(version=4,primary2=primary2)
    encrypted = _crypt(json.dumps(record).encode("utf-8"))
    target = Path(path) if path is not None else vault_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(".tmp")
    temporary.write_bytes(encrypted)
    os.replace(temporary, target)
    # Ordinary replacement resets routing; adding a primary remaps cooldowns below.
    if path is None:
        (target.parent / "routing-state.json").unlink(missing_ok=True)
        (target.parent / "routing-round-robin.json").unlink(missing_ok=True)
    return target


def load_keys(path=None):
    target = Path(path) if path is not None else vault_path()
    try:
        record = json.loads(_crypt(target.read_bytes(), decrypt=True))
        primary, backup = record["primary"], record["backup"]
        if (record["version"] not in (1,2,3,4) or record["provider"] != "minimax_cn"
                or not isinstance(primary, str) or not primary.startswith("sk-cp-")
                or not isinstance(backup, str) or not backup.startswith("sk-") or primary == backup):
            raise ValueError
        keys={"primary": primary, "backup": backup}
        if record['version']>=2:
            third=record.get('third')
            if not isinstance(third,str) or not third.startswith('sk-') or third in keys.values():
                raise ValueError
            keys['third']=third
        if record['version']>=3:
            fourth=record.get('fourth')
            if not isinstance(fourth,str) or not fourth.startswith('sk-') or fourth in keys.values():
                raise ValueError
            keys['fourth']=fourth
        if record['version']>=4:
            primary2=record.get('primary2')
            if not isinstance(primary2,str) or not primary2.startswith('sk-cp-') or primary2 in keys.values():
                raise ValueError
            keys['primary2']=primary2
        return keys
    except Exception:
        raise ValueError("Cannot open MiniMax vault for this Windows user; run scripts/manage_api_keys.py set") from None


def update_key(slot,key,path=None):
    if slot not in KEY_SLOTS:
        raise ValueError('Unknown credential slot')
    keys=load_keys(path);keys[slot]=key.strip()
    target=save_keys(keys['primary'],keys['backup'],path=path,third=keys.get('third'),fourth=keys.get('fourth'),primary2=keys.get('primary2'))
    if load_keys(path)!=keys:
        raise RuntimeError('Encrypted credential verification failed')
    return target


def add_primary_key(key, path=None):
    """Prepend a new key, preserve existing keys and their identity-based cooldowns."""
    key=key.strip();old=load_keys(path)
    target=Path(path) if path is not None else vault_path()
    if key==old['primary']:
        return target
    if len(old)>=len(KEY_SLOTS):
        raise ValueError('All credential slots already exist; replace a slot instead')
    if not key.startswith('sk-cp-') or key in old.values():
        raise ValueError('New primary must be a different MiniMax subscription key')
    new=dict(zip(KEY_SLOTS,[key,*old.values()]))
    state_path=target.parent/'routing-round-robin.json'
    state=None
    if state_path.exists():
        state=json.loads(state_path.read_text(encoding='utf-8'))
        if state.get('slots')!=list(old) or state.get('version')!=1 or state.get('policy')!='round_robin_v1':
            raise ValueError('Existing routing state does not match the encrypted slots')
        remapped=dict(version=1,policy='round_robin_v1',next_index=0,slots=list(new))
        for field in ('blocked_until','epochs','failure_count'):
            if set(state.get(field,{}))!=set(old):
                raise ValueError('Invalid existing credential routing state')
            remapped[field]={slot:(0 if i==0 else state[field][list(old)[i-1]]) for i,slot in enumerate(new)}
    backup=target.with_name(target.stem+'.before-add-primary-'+datetime.now().strftime('%Y%m%d-%H%M%S-%f')+target.suffix)
    backup.write_bytes(target.read_bytes())  # DPAPI ciphertext only.
    if state is not None:
        backup.with_suffix('.routing.json').write_text(json.dumps(state),encoding='utf-8')
    save_keys(new['primary'],new['backup'],path=path,third=new.get('third'),fourth=new.get('fourth'),primary2=new.get('primary2'))
    if state is not None:
        from model import dump
        dump(state_path,remapped)
    if load_keys(path)!=new:
        raise RuntimeError('Encrypted credential verification failed')
    return target


def add_second_primary(key,path=None):
    """Add main2 without relabeling any existing key or resetting its cooldown."""
    keys=load_keys(path);key=key.strip()
    if 'primary2' in keys:
        if keys['primary2']==key:return Path(path) if path is not None else vault_path()
        raise ValueError('Second primary already exists; replace primary2 explicitly')
    if tuple(keys)!=KEY_SLOTS[:4] or not key.startswith('sk-cp-') or key in keys.values():
        raise ValueError('Second primary needs a distinct subscription key and four existing slots')
    target=Path(path) if path is not None else vault_path()
    backup=target.with_name(target.stem+'.before-add-primary2-'+datetime.now().strftime('%Y%m%d-%H%M%S-%f')+target.suffix)
    backup.write_bytes(target.read_bytes())  # CurrentUser DPAPI ciphertext only.
    # Explicit path preserves existing routing. The stopped controller's
    # operator migrates the new slot into its pinned routing state separately.
    save_keys(keys['primary'],keys['backup'],path=target,third=keys['third'],fourth=keys['fourth'],primary2=key)
    if load_keys(target)!={**keys,'primary2':key}:raise RuntimeError('Encrypted credential verification failed')
    return target


def validate_credentials(config):
    """Validate launch mode without printing, exporting or sending credentials."""
    mode = config.get("api_key_mode", "environment")
    if mode not in ("environment", "windows_dpapi_failover"):
        raise ValueError("Unsupported api_key_mode")
    if mode == "windows_dpapi_failover":
        if config.get("api_profile") != "minimax_m3" or config.get("base_url") != MINIMAX_CN:
            raise ValueError("Saved keys are restricted to the MiniMax China endpoint and profile")
        if config.get("api_primary_retry_seconds", 3600) != 3600:
            raise ValueError("This failover policy checks the primary every 3600 seconds")
        keys=load_keys()
        if config.get('api_routing_policy','primary_first_v1')=='round_robin_v1' and tuple(keys) not in (KEY_SLOTS[:3],KEY_SLOTS[:4],KEY_SLOTS):
            raise ValueError('Round robin needs three to five ordered encrypted credential slots')
    elif not (os.environ.get("RUMOR_LLM_API_KEY") or "").strip():
        raise ValueError("Set RUMOR_LLM_API_KEY; no API request was made")
    return mode
