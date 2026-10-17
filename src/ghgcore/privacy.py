"""Data-control layer — the difference between "legal" and "trusted".

The THETIS-MRV facts we serve are published by EMSA because Article 21 of
Regulation (EU) 2015/757 *requires* them to be public. Republishing them is
lawful and needs no consent. But two things are ours, not EMSA's:

1. **Derived estimates** (cost exposure, CII rating, penalty risk, lever
   savings). These are our computations about someone else's ship.
2. **Aggregation** (a whole fleet in one view, ranked). Aggregation creates
   competitive intelligence that the source data does not hand over as
   easily.

So the policy is asymmetric on purpose:
- Public verified facts stay visible to everyone — that is the regulation's
  intent, and hiding them would be pointless (they are one click away at
  mrv.emsa.europa.eu).
- **Our derived estimates about a third party can be suppressed on the
  operator's request.** Nobody can force us to publish our own arithmetic
  about their ship.
- Bulk/fleet-scale use is gated, because harvesting is the actual risk, not
  a single lookup.

This module holds the suppression list, the request log, and the rate
limiter. Everything is file-backed: no database needed at prototype stage,
and the founder can inspect/edit both files by hand.
"""
import json
import os
import threading
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Optional

_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data", "privacy")
SUPPRESSED_FILE = os.path.join(_DIR, "suppressed_imos.txt")
REQUESTS_FILE = os.path.join(_DIR, "requests.jsonl")

_lock = threading.Lock()
_suppressed_cache: Optional[set] = None
_suppressed_mtime: float = -1.0

# Anonymous limits. Generous enough that a genuine prospect never notices,
# tight enough that harvesting the register is impractical.
ANON_LOOKUPS_PER_HOUR = 120
ANON_FLEET_MAX_VESSELS = 8

# Operator requests are unauthenticated, so they are bounded: a single request cannot
# hide the register, and instant hiding stops after a daily budget (later requests are
# still recorded and applied by hand after a check).
MAX_IMOS_PER_REQUEST = 20
AUTO_SUPPRESS_PER_DAY = 60
FIELD_LIMITS = {"company": 200, "email": 254, "message": 2000}

_hits: dict[str, list[float]] = {}
_auto_suppressed: list[float] = []


def _ensure_dir() -> None:
    os.makedirs(_DIR, exist_ok=True)


def _file_suppressed() -> set:
    """Suppressed IMOs from the hand-editable file (re-read when it changes)."""
    global _suppressed_cache, _suppressed_mtime
    try:
        mtime = os.path.getmtime(SUPPRESSED_FILE)
    except OSError:
        _suppressed_cache, _suppressed_mtime = set(), -1.0
        return _suppressed_cache
    if _suppressed_cache is None or mtime != _suppressed_mtime:
        with open(SUPPRESSED_FILE, encoding="utf-8") as f:
            _suppressed_cache = {
                line.split("#")[0].strip() for line in f
                if line.split("#")[0].strip()
            }
        _suppressed_mtime = mtime
    return _suppressed_cache


def _env_suppressed() -> set:
    """IMOs listed in CARBONKEEL_SUPPRESSED_IMOS (comma/space separated).

    This is what survives a hosting restart. On a free host the disk is wiped
    whenever the instance sleeps or redeploys, so a request that only reached
    the file would silently un-suppress itself. The environment setting is
    the durable copy; the file is the convenient one for local use.
    """
    raw = os.environ.get("CARBONKEEL_SUPPRESSED_IMOS", "")
    return {t for t in raw.replace(",", " ").split() if t.isdigit()}


def suppressed_imos() -> set:
    """Every IMO whose derived figures must not be shown to third parties."""
    return _file_suppressed() | _env_suppressed()


def is_suppressed(imo: str) -> bool:
    return str(imo).strip() in suppressed_imos()


def suppress(imo: str, note: str = "") -> None:
    """Add an IMO to the suppression list (operator request)."""
    global _suppressed_mtime
    _ensure_dir()
    with _lock:
        with open(SUPPRESSED_FILE, "a", encoding="utf-8") as f:
            f.write(f"{str(imo).strip()}"
                    f"{('  # ' + note) if note else ''}\n")
        _suppressed_mtime = -1.0   # force reload


@dataclass
class DataRequest:
    """A claim / correction / suppression request from a ship's operator."""
    kind: str            # claim | correct | suppress
    imos: list[str]
    company: str
    contact_email: str
    message: str
    received_utc: str
    applied: bool = False      # a suppression that took effect straight away


VALID_KINDS = {"claim", "correct", "suppress"}


def _auto_budget_left(now: float) -> int:
    _auto_suppressed[:] = [t for t in _auto_suppressed if now - t < 86400]
    return AUTO_SUPPRESS_PER_DAY - len(_auto_suppressed)


def log_request(kind: str, imos: list[str], company: str, email: str,
                message: str = "") -> DataRequest:
    if kind not in VALID_KINDS:
        raise ValueError(f"kind must be one of {sorted(VALID_KINDS)}")
    clean = list(dict.fromkeys(str(i).strip() for i in imos if str(i).strip()))
    if not clean:
        raise ValueError("at least one IMO number is required")
    if any(not (len(i) == 7 and i.isdigit()) for i in clean):
        raise ValueError("IMO numbers have seven digits")
    if len(clean) > MAX_IMOS_PER_REQUEST:
        raise ValueError(f"send at most {MAX_IMOS_PER_REQUEST} IMO numbers per request; "
                         "for a larger fleet, email hello@carbonkeel.com")
    for name, val in (("company", company), ("email", email), ("message", message)):
        if len(val or "") > FIELD_LIMITS[name]:
            raise ValueError(f"the {name} is too long (at most {FIELD_LIMITS[name]} characters)")
    if "@" not in email or "." not in email.split("@")[-1]:
        raise ValueError("a contact email is required so we can verify the request")
    req = DataRequest(kind, clean, company.strip(), email.strip(),
                      message.strip(), datetime.now(timezone.utc).isoformat())
    new = [i for i in clean if not is_suppressed(i)] if kind == "suppress" else []
    if kind == "suppress":
        with _lock:
            now = time.time()
            if len(new) <= _auto_budget_left(now):
                _auto_suppressed.extend([now] * len(new))
                req.applied = True
    _ensure_dir()
    with _lock:
        with open(REQUESTS_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(req), ensure_ascii=False) + "\n")
    # Also emit it to the process log. A host with a wiped disk loses the
    # file above, but its log stream is retained — so the founder can still
    # see who asked for what. (Contains the requester's email; see the
    # privacy notice for how long that is kept.)
    print("CLAIM_REQUEST " + json.dumps(asdict(req), ensure_ascii=False), flush=True)
    # A suppression request takes effect immediately — we do not make an
    # operator wait for a human to action a "stop showing your data" ask —
    # within the daily budget above. (Claims and corrections are verified by
    # the founder before use.)
    if req.applied:
        for imo in new:
            suppress(imo, f"requested by {company or email}")
    return req


def rate_limit_ok(key: str, limit: int = ANON_LOOKUPS_PER_HOUR,
                  window_s: int = 3600) -> bool:
    """Sliding-window limiter. Returns False when `key` is over budget."""
    now = time.time()
    with _lock:
        if len(_hits) > 5000:                      # prune idle visitors
            for k in [k for k, v in _hits.items()
                      if not v or now - v[-1] >= window_s]:
                _hits.pop(k, None)
        hits = [t for t in _hits.get(key, []) if now - t < window_s]
        if len(hits) >= limit:
            _hits[key] = hits
            return False
        hits.append(now)
        _hits[key] = hits
    return True


SUPPRESSION_NOTE = (
    "This ship’s operator has asked us not to show CarbonKeel’s derived "
    "estimates (cost exposure, ratings, penalty risk) to third parties. The "
    "verified figures below stay public because Article 21 of the EU MRV "
    "Regulation requires their publication; they are also available from EMSA "
    "directly. If you operate this ship, claim it to see the full analysis."
)
