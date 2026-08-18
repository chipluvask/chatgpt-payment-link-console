# -*- coding: utf-8 -*-
"""
provider_stats.py — by mailbox provider/domain Statistical registration success rate，
And support the deactivation of low success rate domain names（Some temporary email domain names will eventually create_account stage
quilt OpenAI Risk control rejection，The overall success rate increased significantly after deactivation）。

bucket（reason）：
    create_ok           Registration successful
    otp_timeout         OTP Wait timeout/Uncensored
    upstream_502        Failed to read letter from upstream（Mailbox pool 502 / UPSTREAM_READ_FAILED）
    already_registered  Email is already there OpenAI register（validate return external_url）
    other_fail          Other failures（default）

usage：
    import provider_stats as ps
    ps.record("someone@duck.com", success=True)                    # create_ok
    ps.record("x@outlook.com", success=False, reason="otp_timeout")
    if ps.is_blocked(email): ...
    print(ps.summary())
"""
import json
import threading
from pathlib import Path
from typing import Dict, Optional

STATS_FILE = Path(__file__).parent / "provider_stats.json"
BLOCK_THRESHOLD = 0.34     # Domains with a success rate lower than this value are marked for deactivation
MIN_SAMPLES = 5            # At least N Only sub-samples participate in the evaluation（Avoid accidental killing of small samples）

# Known bucketing；unknown reason subsumed other_fail
KNOWN_BUCKETS = (
    "create_ok",
    "otp_timeout",
    "upstream_502",
    "already_registered",
    "other_fail",
)

_lock = threading.Lock()
_data: Optional[Dict] = None


def _load() -> Dict:
    global _data
    if _data is not None:
        return _data
    if STATS_FILE.exists():
        try:
            _data = json.loads(STATS_FILE.read_text(encoding="utf-8"))
        except Exception:
            _data = {}
    else:
        _data = {}
    _data.setdefault("domains", {})
    return _data


def _save():
    try:
        STATS_FILE.write_text(
            json.dumps(_data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except Exception:
        pass


def _domain_of(email: str) -> str:
    if not email or "@" not in email:
        return "(unknown)"
    return email.split("@")[-1].lower()


def _normalize_reason(success: bool, reason: Optional[str]) -> str:
    if success:
        return "create_ok"
    r = (reason or "other_fail").strip().lower() or "other_fail"
    if r in ("ok", "success", "create_ok"):
        return "other_fail"  # Failure paths should not be marked with success buckets
    if r in KNOWN_BUCKETS:
        return r
    # Compatible with common aliases
    aliases = {
        "timeout": "otp_timeout",
        "otp_empty": "otp_timeout",
        "no_otp": "otp_timeout",
        "502": "upstream_502",
        "upstream_read_failed": "upstream_502",
        "already_reg": "already_registered",
        "external_url": "already_registered",
        "registered": "already_registered",
    }
    return aliases.get(r, "other_fail")


def record(email: str, success: bool, reason: Optional[str] = None) -> str:
    """Record a registration result，Return domain name。

    success=True remember create_ok；success=False time button reason bucket。
    Compatible with old calls：record(email, success) still valid。
    """
    d = _load()
    dom = _domain_of(email)
    rec = d["domains"].setdefault(dom, {"ok": 0, "fail": 0, "buckets": {}})
    buckets = rec.setdefault("buckets", {})
    bucket = _normalize_reason(success, reason)
    buckets[bucket] = int(buckets.get(bucket) or 0) + 1
    if success:
        rec["ok"] += 1
    else:
        rec["fail"] += 1
    _save()
    return dom


def is_blocked(email: str) -> bool:
    """Whether the domain name has been deactivated due to low success rate（No decision will be made when there are insufficient samples.）。

    Pay attention to bucketing：already_registered / otp_timeout still counted fail，
    avoid putting「Registered number pool」Misjudged as「The channel itself is available」。To evaluate channel health，
    Please use channel_fail_rate() exclude already_registered。
    """
    d = _load()
    dom = _domain_of(email)
    rec = d["domains"].get(dom)
    if not rec:
        return False
    total = rec["ok"] + rec["fail"]
    if total < MIN_SAMPLES:
        return False
    rate = rec["ok"] / total
    return rate < BLOCK_THRESHOLD


def rate_of(email: str) -> Optional[float]:
    d = _load()
    rec = d["domains"].get(_domain_of(email))
    if not rec:
        return None
    total = rec["ok"] + rec["fail"]
    return (rec["ok"] / total) if total else None


def channel_fail_rate(email: str) -> Optional[float]:
    """Channel true failure rate：exclude already_registered（Inventory issues，non-channel failure）。"""
    d = _load()
    rec = d["domains"].get(_domain_of(email))
    if not rec:
        return None
    buckets = rec.get("buckets") or {}
    already = int(buckets.get("already_registered") or 0)
    ok = int(rec.get("ok") or 0)
    fail = int(rec.get("fail") or 0)
    # valid sample = total sample - Registered（Registered neither ok Nor a channel fail）
    effective_total = ok + fail - already
    if effective_total <= 0:
        return None
    channel_fail = fail - already
    return channel_fail / effective_total


def summary() -> str:
    d = _load()
    lines = []
    for dom, rec in sorted(
        d["domains"].items(), key=lambda kv: -(kv[1]["ok"] + kv[1]["fail"])
    ):
        total = rec["ok"] + rec["fail"]
        rate = (rec["ok"] / total) if total else 0.0
        blocked = total >= MIN_SAMPLES and rate < BLOCK_THRESHOLD
        flag = " [Deactivated]" if blocked else ""
        buckets = rec.get("buckets") or {}
        bucket_parts = []
        for k in KNOWN_BUCKETS:
            n = int(buckets.get(k) or 0)
            if n:
                bucket_parts.append(f"{k}={n}")
        # Compatibility history：none buckets Show only when ok/fail
        extra = (" | " + " ".join(bucket_parts)) if bucket_parts else ""
        lines.append(
            f"  {dom:26} ok={rec['ok']:3} fail={rec['fail']:3} "
            f"rate={rate*100:5.1f}%{flag}{extra}"
        )
    return "\n".join(lines) if lines else "  (No statistics yet)"


if __name__ == "__main__":
    # Demo：Domain names with low success rates will be flagged；Bucketing can distinguish registered vs What a failure
    for _ in range(6):
        record("x@bad-temp.example", success=False, reason="other_fail")
    for _ in range(3):
        record("y@outlook.com", success=False, reason="already_registered")
    for _ in range(2):
        record("y@outlook.com", success=False, reason="otp_timeout")
    for _ in range(1):
        record("y@outlook.com", success=False, reason="upstream_502")
    for _ in range(6):
        record("z@good.example", success=True)
    print(summary())
    print("bad-temp blocked?", is_blocked("z@bad-temp.example"))
    print("good blocked?", is_blocked("z@good.example"))
    print("outlook channel_fail_rate", channel_fail_rate("a@outlook.com"))
