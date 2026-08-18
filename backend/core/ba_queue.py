"""PayPal BA authorization queue (JSON File persistence)。

After successfully lifting the chain orchestrator Automatically paypal Produced by channels BA Import this queue,
PayPal Authorization page (api/paypal.py) Read from this queue/Update record。
Support manual import (api/paypal.py /ba/import), All records placed backend/ba_queue.json,
Not lost after restarting; success_inventory backfill only as"The file is empty and has not been backfilled by this process."The bottom line。

Concurrency safety: All read and write use module-level locks; try_start supply pending->running Atomic transfer
(Repeated start returns already_running); mark_stale Clean up zombies running。
persistence: Atomic write after each change (tmp + os.replace)。
"""
from __future__ import annotations

import json
import os
import re
import threading
import time
from typing import Any

_BA_TOKEN_RE = re.compile(r"ba_token=(BA-[A-Za-z0-9]+)")
_BARE_TOKEN_RE = re.compile(r"^(BA-[A-Za-z0-9]+)$")

_QUEUE_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "ba_queue.json"
)

_records: list[dict[str, Any]] = []
_lock = threading.Lock()
_loaded = False

_STALE_RUNNING_MS = 30 * 60 * 1000  # running overtake 30min Tag zombie


def extract_ba_token(url: str) -> str:
    """from URL or naked token extracted from BA-xxx。"""
    m = _BA_TOKEN_RE.search(url or "")
    if m:
        return m.group(1)
    m = _BARE_TOKEN_RE.match((url or "").strip())
    return m.group(1) if m else ""


def _load_locked() -> None:
    global _records, _loaded
    if _loaded:
        return
    _loaded = True
    try:
        with open(_QUEUE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            _records = [r for r in data if isinstance(r, dict) and r.get("ba_token")]
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        _records = []


def _save_locked() -> None:
    tmp = _QUEUE_FILE + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(_records, f, ensure_ascii=False, indent=1)
        os.replace(tmp, _QUEUE_FILE)
    except OSError:
        pass


def add(ba_token: str, email: str = "", approve_url: str = "",
        country: str = "", chain_id: str = "", status: str = "pending",
        step: str = "submit_email", captcha_type: str = "",
        sms_phone: str = "", error: str = "", source: str = "chain") -> bool:
    """join queue (according to ba_token Remove duplicates)。Return whether to add。"""
    ba_token = (ba_token or "").strip()
    if not ba_token:
        return False
    with _lock:
        _load_locked()
        for r in _records:
            if r.get("ba_token") == ba_token:
                return False
        now = int(time.time() * 1000)
        _records.append({
            "ba_token": ba_token,
            "email": email,
            "approve_url": approve_url,
            "status": status,
            "step": step,
            "country": (country or "").upper(),
            "chain_id": chain_id,
            "captcha_type": captcha_type,
            "sms_phone": sms_phone,
            "error": error,
            "source": source,
            "created_at": now,
            "updated_at": now,
        })
        _save_locked()
        return True


def import_from_url(url: str, email: str = "", country: str = "",
                    chain_id: str = "", source: str = "chain") -> bool:
    """Produced from the chain paypal_approve_url Import queue。"""
    tok = extract_ba_token(url or "")
    if not tok:
        return False
    return add(tok, email=email, approve_url=url,
               country=country, chain_id=chain_id, source=source)


def get(ba_token: str) -> dict[str, Any] | None:
    with _lock:
        _load_locked()
        for r in _records:
            if r.get("ba_token") == ba_token:
                return dict(r)
    return None


def update(ba_token: str, **fields: Any) -> None:
    with _lock:
        _load_locked()
        for r in _records:
            if r.get("ba_token") == ba_token:
                for k, v in fields.items():
                    r[k] = v
                if "country" in fields:
                    r["country"] = str(fields["country"] or "").upper()
                r["updated_at"] = int(time.time() * 1000)
                _save_locked()
                return


def list_records() -> list[dict[str, Any]]:
    with _lock:
        _load_locked()
        return [dict(r) for r in _records]


def remove(ba_token: str) -> bool:
    global _records
    with _lock:
        _load_locked()
        before = len(_records)
        _records = [r for r in _records if r.get("ba_token") != ba_token]
        changed = len(_records) != before
        if changed:
            _save_locked()
        return changed


def bulk_remove(ba_tokens: list[str]) -> int:
    """Batch delete, Return the number of deleted items。"""
    global _records
    with _lock:
        _load_locked()
        tokens = set(t for t in (ba_tokens or []) if t)
        before = len(_records)
        _records = [r for r in _records if r.get("ba_token") not in tokens]
        removed = before - len(_records)
        if removed:
            _save_locked()
        return removed


def clear(status: str | None = None) -> int:
    """Clear the queue (status Only clear this status when specified), Return the number of deleted items。"""
    global _records
    with _lock:
        _load_locked()
        before = len(_records)
        if status:
            _records = [r for r in _records if r.get("status") != status]
        else:
            _records = []
        removed = before - len(_records)
        if removed:
            _save_locked()
        return removed


def count() -> int:
    with _lock:
        _load_locked()
        return len(_records)


def try_start(ba_token: str) -> tuple[bool, str]:
    """pending -> running Atomic transfer。return (Is it successful?, error message)。"""
    with _lock:
        _load_locked()
        r = next((x for x in _records if x.get("ba_token") == ba_token), None)
        if r is None:
            return False, "not_found"
        if r.get("status") == "running":
            return False, "already_running"
        r["status"] = "running"
        r["step"] = "submit_email"
        r["error"] = ""
        r["updated_at"] = int(time.time() * 1000)
        _save_locked()
        return True, ""


def retry(ba_token: str, allow_success: bool = False) -> bool:
    """failed/success -> pending (Clear error/step), for batch retry。Return whether successful。

    allow_success=True You can rerun even if the record has been authorized. (Consume new number and new card, used for EUAT Got it but
    Scenarios such as subscription not taking effect); Default only failed。
    """
    with _lock:
        _load_locked()
        r = next((x for x in _records if x.get("ba_token") == ba_token), None)
        if r is None:
            return False
        if r.get("status") == "running":
            return False
        if r.get("status") not in ("failed",) and not (allow_success and r.get("status") == "success"):
            return False
        r["status"] = "pending"
        r["step"] = "submit_email"
        r["error"] = ""
        r["updated_at"] = int(time.time() * 1000)
        _save_locked()
        return True


def mark_stale(older_than_ms: int = _STALE_RUNNING_MS) -> int:
    """zombie running clean up: running and updated_at time out -> failed + error=stale_running。"""
    now = int(time.time() * 1000)
    marked = 0
    with _lock:
        _load_locked()
        for r in _records:
            if r.get("status") == "running" and now - int(r.get("updated_at") or 0) > older_than_ms:
                r["status"] = "failed"
                r["error"] = "stale_running"
                r["updated_at"] = now
                marked += 1
        if marked:
            _save_locked()
    return marked