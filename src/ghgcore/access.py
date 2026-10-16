"""Access keys for the locked (owner-data) tools.

This is a shared-secret gate, not an authentication system. It exists so the
CII calculator and other owner-data tools are not open to the anonymous
internet during the pilot phase: you hand a key to a design partner, they
paste it once, it is remembered in their browser. Revoking = deleting a line.

When real accounts arrive (Phase 2 D2.1) this module is replaced wholesale;
until then it is honest about what it is. Do not use it to protect anything
whose disclosure would actually harm someone — it protects a feature, not a
secret.

Key file: data/access_keys.txt — `KEY  # label` per line, hand-editable,
re-read on change. A key is generated on first run if the file is absent.

The gate is OFF by default: the calculator is open to every visitor. Set the
environment variable CARBONKEEL_REQUIRE_KEY=1 to require a key again (on Fly.io:
`flyctl secrets set CARBONKEEL_REQUIRE_KEY=1`; remove it to reopen).
"""
import os
import secrets
import threading
from typing import Optional

_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data")
KEYS_FILE = os.path.join(_DIR, "access_keys.txt")

_lock = threading.Lock()
_cache: Optional[dict] = None
_mtime: float = -1.0

_HEADER = """# CarbonKeel access keys — one per line, `KEY  # who it was issued to`.
# These unlock the owner-data tools (CII calculator). Hand a key to a design
# partner; delete the line to revoke. Changes apply immediately.
"""


def _generate_default() -> str:
    os.makedirs(_DIR, exist_ok=True)
    key = "ck-" + secrets.token_hex(8)
    with open(KEYS_FILE, "w", encoding="utf-8") as f:
        f.write(_HEADER)
        f.write(f"{key}  # founder — generated on first run\n")
    return key


def _env_keys() -> dict:
    """Keys from CARBONKEEL_ACCESS_KEYS: 'key1:label one,key2:label two'.

    On a host that wipes its disk a key auto-generated into a file would be
    unreadable to the founder and gone after the next restart. Setting the
    keys in the host's environment makes them durable and visible to you.
    """
    out = {}
    for item in os.environ.get("CARBONKEEL_ACCESS_KEYS", "").split(","):
        item = item.strip()
        if not item:
            continue
        key, _, label = item.partition(":")
        if key.strip():
            out[key.strip()] = label.strip()
    return out


def keys() -> dict:
    """{key: label} from the environment plus the hand-editable file.

    A founder key is generated into the file only when NO keys are configured
    anywhere (local development) — never on a host that supplies them by env.
    """
    global _cache, _mtime
    env = _env_keys()
    if not os.path.exists(KEYS_FILE) and not env:
        _generate_default()
        _cache, _mtime = None, -1.0
    out = dict(env)
    if os.path.exists(KEYS_FILE):
        mtime = os.path.getmtime(KEYS_FILE)
        if _cache is None or mtime != _mtime:
            with _lock:
                fk = {}
                with open(KEYS_FILE, encoding="utf-8") as f:
                    for line in f:
                        body = line.split("#")[0].strip()
                        if not body:
                            continue
                        label = line.split("#", 1)[1].strip() if "#" in line else ""
                        fk[body] = label
                _cache, _mtime = fk, mtime
        out.update(_cache or {})
    return out


def required() -> bool:
    return os.environ.get("CARBONKEEL_REQUIRE_KEY", "").strip().lower() in ("1", "true", "yes", "on")


def is_valid(key: Optional[str]) -> bool:
    return bool(key) and key.strip() in keys()


def label_for(key: str) -> str:
    return keys().get(key.strip(), "")


def issue(label: str) -> str:
    """Mint a new key (for a design partner) and append it."""
    key = "ck-" + secrets.token_hex(8)
    keys()   # ensure file exists
    with _lock:
        with open(KEYS_FILE, "a", encoding="utf-8") as f:
            f.write(f"{key}  # {label}\n")
    global _mtime
    _mtime = -1.0
    return key
