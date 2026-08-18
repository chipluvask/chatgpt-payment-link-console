# -*- coding: utf-8 -*-
"""reg/channel_api798.py — api798.com Email extraction tool custom registration channel

Card secret format（per line）：email----https://api798.com/latest?email=...&auth_code=XXX
Get the code and go JSON endpoint GET /get_code?email=&auth_code= （return {success, code, subject, body, date}）。

Registration channel contract（reg/engine.register_email_channel）：
    setup_fn(proxies, cancel_check) -> (email, openai_password, fetch_code)
    fetch_code(timeout_sec=None, seen_ids=None, not_before=None) -> code|None

usage（app.py On startup）：
    from reg import engine as reg_engine
    from reg.channel_api798 import load_mailboxes, build_channel
    reg_engine.register_email_channel("api798", build_channel(load_mailboxes("Cardamom.txt")))
"""
from __future__ import annotations

import re
import threading
import time
import urllib.parse

from . import chatgpt_core as cc

_API_BASE = "https://api798.com/get_code"

# Received mailbox queue（Thread safety，Spend one less one）
_QUEUE: list[dict] = []
_QLOCK = threading.Lock()


def load_mailboxes(path: str, auth_code: str = "") -> list[dict]:
    """Export text from card secret to load mailbox list。

    Support line format：
      email----https://api798.com/latest?email=xxx&auth_code=XXX
      email|auth_code
    """
    out: list[dict] = []
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or line.startswith("Cardamom"):
                    continue
                # row format: email----https://api798.com/latest?email=...&auth_code=XXX
                m = re.match(r"^([^@\s]+@[^@\s]+)(?:----|,|\s+)(\S*)$", line)
                if not m:
                    continue
                email = m.group(1).strip()
                rest = m.group(2).strip()
                ac = auth_code
                if "auth_code=" in rest:
                    ac = re.search(r"auth_code=([^&\s]+)", rest).group(1)
                elif rest:
                    ac = rest
                if email and ac:
                    out.append({"email": email, "auth_code": ac})
    except Exception as e:
        print(f"[api798] Failed to load mailbox: {e}")
    return out


def build_channel(mailboxes: list[dict], poll_interval: float = 6.0):
    """Structure registration channel setup_fn。

    each setup Call to receive an email（Queue consumption），Registration failed/Use once successful；
    Return when the queue is exhausted during batch registration None（Outer layer number change and retry）。
    """
    with _QLOCK:
        _QUEUE.extend(mailboxes)

    def setup_fn(proxies, cancel_check):
        with _QLOCK:
            if not _QUEUE:
                print("[api798] Mailbox queue exhausted")
                return None, None, None
            mb = _QUEUE.pop(0)
        email = mb["email"]
        auth = mb["auth_code"]
        openai_password = cc._gen_password()

        def fetch_code(timeout_sec=None, seen_ids=None, not_before=None):
            timeout_s = int(timeout_sec or 240)
            deadline = time.time() + timeout_s
            seen = set(seen_ids or [])
            last_code = {"v": ""}
            last_log = 0.0
            print(f"[api798] wait OTP: {email} (timeout≈{timeout_s}s)")
            while time.time() < deadline:
                if cancel_check and cancel_check():
                    print("[api798] Canceled（wait OTP middle）")
                    return None
                try:
                    code = _fetch_code_once(email, auth, not_before=not_before)
                    if code and code not in seen and code != last_code["v"]:
                        print(f"[api798] OTP ok: {code}")
                        last_code["v"] = code
                        return code
                except Exception as e:
                    print(f"[api798] Code acquisition exception（continue）: {repr(e)[:120]}")
                now = time.time()
                if now - last_log >= 20:
                    print(f"[api798] still waiting OTP... remain≈{int(deadline - now)}s")
                    last_log = now
                time.sleep(poll_interval)
            print("[api798] OTP timeout")
            return None

        fetch_code.mark_already_registered = lambda detail: print(
            f"[api798] Email is registered mark: {email} ({detail})")
        return email, openai_password, fetch_code

    return setup_fn


def _fetch_code_once(email: str, auth_code: str, not_before=None) -> str | None:
    """GET /get_code，Return verification code。

    response JSON：
      {"success": true, "message": "Query successful",
       "data": {"code": "238909", "subject": "...", "body": "...html...", "date": "..."}}
    Take priority data.code；Fallback if missing subject/body latest in 6 Verification code
    （body May contain historical code，code The field is the current code）。

    not_before: Timestamp（Second），Only accept messages arriving after this time（date Field），
    Avoid retrieving old verification codes from old emails when the registered email is re-run.。
    """
    from curl_cffi import requests

    qs = urllib.parse.urlencode({"email": email, "auth_code": auth_code})
    r = requests.get(f"{_API_BASE}?{qs}", timeout=25, impersonate="chrome131")
    try:
        data = r.json()
    except Exception:
        return None
    if not isinstance(data, dict) or not data.get("success"):
        return None
    inner = data.get("data")
    if isinstance(inner, dict):
        if not_before is not None:
            d = str(inner.get("date") or "")
            if d:
                try:
                    dt = float(d)
                    if dt < float(not_before):
                        return None
                except Exception:
                    pass
        code = str(inner.get("code") or "").strip()
        if code:
            return code
        blob = " ".join(str(inner.get(k) or "") for k in ("subject", "body"))
        m = re.search(r"\b(\d{6,8})\b", blob)
        return m.group(1) if m else None
    code = str(data.get("code") or "").strip()
    if code:
        return code
    return None