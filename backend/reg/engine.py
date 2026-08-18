# -*- coding: utf-8 -*-
"""reg/engine.py — ChatGPT Register batch scheduling engine（event ring buffer + polling）

and mail-otp-server of reg_engine.py isomorphism，But suitable for this project：
  - none Flask/SSE：event buffer + since incremental polling（front end 3s polling）
  - none gevent：uvicorn pure asyncio；Register as a heavily blocking thread task（curl_cffi No event loop），
    by caller asyncio.to_thread implement stream_registration()
  - stdout Thread local forwarding：Only register threads print forward as log event，Does not pollute uvicorn log
  - Email channel：built-in mailtm；Customized channel register_email_channel register
    （setup_fn(proxies, cancel_check) -> (email, openai_password, fetch_code)）
  - Dropped into the library：reg_accounts surface + Successful account synchronization writing project tokens surface（source=register）

Singleton STATE Hold running state；POST /api/register/start After seizing the slot
asyncio.to_thread(stream_registration, ...) background execution。
"""
from __future__ import annotations

import io
import json
import os
import sys
import threading
import time
import uuid
from datetime import datetime, timezone

from reg import chatgpt_core as chatgpt
from reg import repo_accounts as ra

ALIVE_STATUSES = (
    "active", "pending", "expired", "suspended", "deactivated",
    "logout", "disabled", "revoked", "unknown",
)

# Email channel：built-in mailtm（Zero dependency online API）；The rest are registered by users to customize channels
# （See register_email_channel，Can access any mailbox：IMAP/outlook pool/Self-built mailbox, etc.）
# Notice：Cannot be evaluated at the top level of a module list_email_channels（chatgpt_core Initialization may not be complete yet），
# Lazy acquisition using functions，for api layer with register_one Check use。


def email_channels() -> tuple:
    return tuple(chatgpt.list_email_channels())


def register_email_channel(name: str, setup_fn) -> None:
    """Register for a custom email channel，Immediately after registration, it will appear in the panel channel drop-down and verification whitelist。

    setup_fn(proxies, cancel_check) -> (email, openai_password, fetch_code)
    fetch_code(timeout_sec=None, seen_ids=None, not_before=None) -> code|None
    """
    chatgpt.register_email_channel(name, setup_fn)


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")


# ==================== Running state（In-process singleton） ====================

class _RegistrationState:
    def __init__(self):
        self._lock = threading.Lock()
        self._events: list[dict] = []
        self._seq = 0
        self._running = False
        self._cancel = threading.Event()
        self._task_id = None

    def try_start(self) -> str | None:
        """Atomic preemption of task slots：Return successfully task_id；There is already a task running and returning None。"""
        with self._lock:
            if self._running:
                return None
            task_id = uuid.uuid4().hex
            self._running = True
            self._task_id = task_id
            self._cancel.clear()
            return task_id

    def set_running(self, task_id: str | None):
        with self._lock:
            self._running = task_id is not None
            self._task_id = task_id
            self._cancel.clear()

    def request_cancel(self) -> bool:
        with self._lock:
            if not self._running:
                return False
            self._cancel.set()
            return True

    def is_running(self) -> bool:
        with self._lock:
            return self._running

    @property
    def cancel_event(self):
        return self._cancel

    def push(self, ev: dict):
        with self._lock:
            self._seq += 1
            ev = {"seq": self._seq, "ts": _now_iso(), **ev}
            self._events.append(ev)
            if len(self._events) > 1000:
                del self._events[: len(self._events) - 1000]

    def replay_since(self, seq: int) -> list[dict]:
        with self._lock:
            return [e for e in self._events if e["seq"] > seq]

    def status(self) -> dict:
        with self._lock:
            return {
                "running": self._running,
                "task_id": self._task_id,
                "last_seq": self._seq,
            }


STATE = _RegistrationState()


# ==================== stdout → event forwarding（Thread local，Anti-pollution uvicorn） ====================

class _SSEForwarder(io.TextIOBase):
    """line buffering stdout，forward as log event。"""

    def __init__(self, on_event):
        super().__init__()
        self._on_event = on_event
        self._buf = ""

    def write(self, s: str) -> int:
        if not s:
            return 0
        self._buf += s
        while "\n" in self._buf:
            line, self._buf = self._buf.split("\n", 1)
            line = line.strip()
            if line:
                self._on_event({"type": "log", "stage": "register_one",
                                "message": line})
        return len(s)

    def flush(self):
        if self._buf.strip():
            line = self._buf.strip()
            self._buf = ""
            if line:
                self._on_event({"type": "log", "stage": "register_one",
                                "message": line})

    def isatty(self) -> bool:
        return False


class _MuxStdout(io.TextIOBase):
    """overall situation stdout multiplex forwarding：Only registered thread settings are forwarded as events，The remaining threads pass through to the real stdout。"""

    def __init__(self, real):
        super().__init__()
        self._real = real
        self._local = threading.local()

    def set_forwarder(self, fwd):
        self._local.fwd = fwd

    def clear_forwarder(self):
        self._local.fwd = None

    def write(self, s) -> int:
        fwd = getattr(self._local, "fwd", None)
        if fwd is not None:
            try:
                fwd.write(s)
                return len(s) if isinstance(s, str) else 0
            except Exception:
                pass
        try:
            self._real.write(s)
        except Exception:
            pass
        return len(s) if isinstance(s, str) else 0

    def flush(self):
        fwd = getattr(self._local, "fwd", None)
        if fwd is not None:
            try:
                fwd.flush()
            except Exception:
                pass
        try:
            self._real.flush()
        except Exception:
            pass

    def isatty(self) -> bool:
        try:
            return self._real.isatty()
        except Exception:
            return False

    def fileno(self) -> int:
        return self._real.fileno()

    @property
    def encoding(self):
        return getattr(self._real, "encoding", "utf-8")


def _install_mux_stdout():
    if not isinstance(sys.stdout, _MuxStdout):
        mux = _MuxStdout(sys.stdout)
        sys.stdout = mux  # type: ignore[assignment]
        return mux
    return sys.stdout


_STDOUT_MUX = _install_mux_stdout()


# ==================== Failure bucketing ====================

def _fail_code(detail: str, tail: list[str]) -> str:
    blob = "\n".join(tail).lower()
    if "Email is registered" in blob or "already_registered" in blob or "external_url" in blob:
        return "ALREADY_REGISTERED"
    if "Verification code waiting timeout" in blob or "otp timeout" in blob or "Failed to extract" in blob:
        return "OTP_TIMEOUT"
    if "area" in blob or "unsupported_country" in blob:
        return "UNSUPPORTED_COUNTRY"
    if "sentinel" in blob and ("none" in blob or "Lack" in blob):
        return "SENTINEL_FAILED"
    if "user_already_exists" in blob:
        return "ALREADY_REGISTERED"
    return "REGISTER_FAILED"


# ==================== Registration number ====================

def register_one(email_mode: str, proxy: str | None, cancel: threading.Event,
                 on_event) -> dict:
    """Register a single account。return dict（email/alive_status/error_code wait），Dropped by the caller。"""
    tail: list[str] = []
    tail_max = 60

    def _on_line(ev: dict):
        tail.append(str(ev.get("message") or ""))
        if len(tail) > tail_max:
            del tail[: len(tail) - tail_max]
        on_event(ev)

    mapped = email_mode
    if mapped not in email_channels():
        on_event({"type": "log", "stage": "engine",
                  "message": f"Unknown email channel: {email_mode}"})
        return {
            "email": None, "alive_status": "unknown", "plan_type": "unknown",
            "error_code": "UNKNOWN_EMAIL_MODE", "error_detail": email_mode,
        }

    on_event({"type": "log", "stage": "register_one",
              "message": f"Start registration（channel={email_mode}, acting={proxy or 'automatic'}）"})
    fwd = _SSEForwarder(_on_line)
    result = None
    _STDOUT_MUX.set_forwarder(fwd)
    try:
        result = chatgpt.run(proxy, email=mapped,
                             cancel_check=cancel.is_set)
    except Exception as e:
        on_event({"type": "log", "stage": "register_one",
                  "message": f"Registration exception: {repr(e)[:300]}"})
        code = _fail_code("", tail)
        return {
            "email": None, "alive_status": "unknown", "plan_type": "unknown",
            "error_code": code,
            "error_detail": f"{code}: {repr(e)[:200]}; tail={tail[-6:]}",
        }
    finally:
        _STDOUT_MUX.clear_forwarder()
        fwd.flush()

    if not result:
        code = _fail_code("", tail)
        detail = code
        if tail:
            detail = f"{code}; tail={tail[-8:]}"
        on_event({"type": "log", "stage": "register_one",
                  "message": f"Registration failed（{code}）"})
        return {
            "email": None, "alive_status": "unknown", "plan_type": "unknown",
            "error_code": code, "error_detail": detail,
        }

    token_json, email, password, access_token, session_token = result
    email = str(email or "").strip()
    if not email:
        on_event({"type": "log", "stage": "register_one",
                  "message": "Registration returns exception（none email）"})
        return {
            "email": None, "alive_status": "unknown", "plan_type": "unknown",
            "error_code": "REGISTER_FAILED", "error_detail": "run Return None email",
        }

    # Compatible with both token form：web flow next-auth accessToken / Codex OAuth flow token_json
    tj = token_json or {}
    if not access_token:
        access_token = str(tj.get("access_token") or tj.get("accessToken") or "").strip()
    if not session_token:
        session_token = str(tj.get("session_token") or tj.get("sessionToken") or "").strip()
    plan_type = str(tj.get("plan_type") or "").strip() or "unknown"

    on_event({"type": "log", "stage": "register_one",
              "message": f"Registration successful: {email}（plan={plan_type}）"})
    return {
        "email": email,
        "password": password,
        "access_token": access_token,
        "session_token": session_token,
        "refresh_token": str(tj.get("refresh_token") or "").strip() or None,
        "alive_status": "active",
        "plan_type": plan_type,
        "source_email": email if email_mode in email_channels() else None,
        "error_code": None,
        "error_detail": None,
    }


# ==================== Batch scheduling ====================

def _emit(ev: dict):
    STATE.push(ev)


def stream_registration(count: int, email_mode: str = "mailtm", concurrency: int = 1,
                        cooldown: float = 30.0, task_id: str | None = None,
                        proxy: str | None = None):
    """Batch registration（block，Must be run in a separate thread）。Number by number synchronization，event push STATE。

    proxy: None When chatgpt.run Automatically enabled 711 residential relay（need PROXY_711_USER/PASS）。
    """
    conn = ra.connect()
    task_id = task_id or uuid.uuid4().hex
    try:
        total = max(int(count or 1), 1)
        concurrency = min(max(int(concurrency or 1), 1), 10)
        STATE.set_running(task_id)
        _emit({"type": "start", "task_id": task_id, "total": total,
               "email_mode": email_mode, "concurrency": concurrency})

        results, success, failed = [], 0, 0
        cancel = STATE.cancel_event
        # Each number is independent 711 sticky session（Alignment codex server._make_sticky_proxy：
        # Parse incoming credentials + random region + random session id → Each number is different IP part）
        def _make_sticky_proxy(base_proxy: str | None) -> str | None:
            if not base_proxy:
                return None
            try:
                from core import proxy_711 as _p711
                if not _p711.is_711_proxy(base_proxy):
                    return base_proxy
                # Incoming from URL extract reality user:pass@host:port，replace user for
                # <user>-session-<random11Bit>-sessTime-30-region-<random>
                info = _p711.parse_proxy_url(base_proxy)
                region = _p711.pick_region()
                import random as _r
                import string as _st
                sid = "".join(_r.choice(_st.ascii_lowercase + _st.digits) for _ in range(11))
                user = f"{info['user']}-session-{sid}-sessTime-30-region-{region}"
                from urllib.parse import quote as _quote
                raw = (
                    f"http://{_quote(user, safe='')}:{_quote(info['password'], safe='')}"
                    f"@{info['host']}:{info['port']}"
                )
                return _p711.ensure_proxy(raw) or raw
            except Exception as e:
                _emit({"type": "log", "stage": "engine",
                       "message": f"sticky proxy Build failed（Use original proxy）: {repr(e)[:120]}"})
                return base_proxy

        idx = 0
        while idx < total and not cancel.is_set():
            idx += 1
            reg_proxy = _make_sticky_proxy(proxy)
            if reg_proxy and reg_proxy != proxy:
                _emit({"type": "log", "stage": "engine",
                       "message": f"[{idx}/{total}] 711 viscosity session: {reg_proxy.split('@')[-1]}"})
            r = register_one(email_mode, reg_proxy, cancel, _emit)
            ok = bool(r.get("email")) and not r.get("error_code")
            status = "active" if ok else "disabled"
            alive = r.get("alive_status") or ("active" if ok else "unknown")
            rid = None
            if r.get("email"):
                try:
                    rid = ra.upsert_account(conn, {
                        "email": r["email"], "password": r.get("password"),
                        "access_token": r.get("access_token"),
                        "session_token": r.get("session_token"),
                        "refresh_token": r.get("refresh_token"),
                        "alive_status": alive, "plan_type": r.get("plan_type") or "unknown",
                        "source_email": r.get("source_email"), "email_mode": email_mode,
                        "status": status, "error_code": r.get("error_code"),
                        "error_detail": (r.get("error_detail") or "")[:500],
                        "register_ts": _now_iso(),
                    })
                    if ok:
                        # Successful account synchronization is written into this project tokens surface（source=register），Can be lifted directly
                        ra.push_to_tokens(conn, r)
                except Exception as e:
                    _emit({"type": "log", "stage": "db", "message": f"Failed to drop into warehouse: {e}"})
            if ok:
                success += 1
            else:
                failed += 1
            results.append({"index": idx, "email": r.get("email"), "ok": ok,
                            "error": r.get("error_code"), "id": rid})
            _emit({"type": "progress", "index": idx, "total": total, "ok": ok,
                   "success": success, "failed": failed, "error": r.get("error_code")})
            if idx < total and not cancel.is_set() and cooldown > 0:
                _emit({"type": "log", "stage": "delay", "message": f"cool down {cooldown:.0f}s"})
                time.sleep(cooldown)

        stopped = cancel.is_set()
        _emit({"type": "complete", "task_id": task_id, "total": total, "success": success,
               "failed": failed, "stopped": stopped, "results": results})
    except Exception as e:
        _emit({"type": "error", "message": str(e)[:300]})
    finally:
        with STATE._lock:
            STATE._running = False
            STATE._task_id = None
        ra.close(conn)


def cancel_registration() -> bool:
    return STATE.request_cancel()