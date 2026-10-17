"""Country of an IP address, from the DB-IP Lite country database (CC BY 4.0, db-ip.com).

The tables in data/geo are built by scripts/make_geo.py from the monthly DB-IP Lite CSV. The
IP address itself is never stored; only the two-letter country it maps to.
"""
import bisect
import ipaddress
import json
import os
import threading
from array import array

_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data", "geo")
_lock = threading.Lock()
_T = None


def _load():
    global _T
    with _lock:
        if _T is None:
            meta = json.load(open(os.path.join(_DIR, "meta.json"), encoding="utf-8"))
            t = {"codes": meta["codes"]}
            for name, code in (("v4s", "I"), ("v4c", "H"), ("v6s", "Q"), ("v6c", "H")):
                a = array(code)
                with open(os.path.join(_DIR, name + ".bin"), "rb") as f:
                    a.frombytes(f.read())
                t[name] = a
            _T = t
    return _T


def country(ip: str) -> str:
    """Two-letter country code, or '' when unknown, private or unparsable."""
    try:
        addr = ipaddress.ip_address((ip or "").strip())
    except ValueError:
        return ""
    if addr.version == 6 and addr.ipv4_mapped:
        addr = addr.ipv4_mapped
    if addr.is_private or addr.is_loopback or addr.is_reserved or addr.is_link_local:
        return ""
    try:
        t = _load()
    except OSError:
        return ""
    if addr.version == 4:
        i = bisect.bisect_right(t["v4s"], int(addr)) - 1
        cc = t["codes"][t["v4c"][i]] if i >= 0 else ""
    else:
        i = bisect.bisect_right(t["v6s"], int(addr) >> 64) - 1
        cc = t["codes"][t["v6c"][i]] if i >= 0 else ""
    return "" if cc == "ZZ" else cc
