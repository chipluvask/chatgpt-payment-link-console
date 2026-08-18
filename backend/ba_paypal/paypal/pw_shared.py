"""Thread affinity sharing Playwright sync Example。

background (2026-08-15 BA-7FC18 Actual measurement): Playwright sync API of dispatcher use greenlet
within thread `loop.run_until_complete(...)`, Should loop exist dispatcher Keep alive
running。`sync_playwright()` The inspection only recognizes"Does the current thread have running loop"——
Second call in the same thread `sync_playwright()` will hit
"It looks like you are using Playwright Sync API inside the asyncio loop"。

This module caches a single instance by thread: All in the same thread playwright call (local_headless /
recaptcha_solver / hcaptcha_semi_hybrid / roxy connect) Reuse the same instance,
Eliminate secondary boot checks from the root (Playwright official request sync API Single threaded singleton)。
Browser/The page handle is managed by the caller (launch/close), This module only deals with instance reuse。
"""
from __future__ import annotations

import threading
from contextlib import contextmanager
from typing import Any, Iterator

_thread = threading.local()


@contextmanager
def shared_playwright() -> Iterator[Any]:
    """Returns the share of the current thread playwright Example (Started when first called)。"""
    mgr = getattr(_thread, "mgr", None)
    if mgr is None:
        from playwright.sync_api import sync_playwright

        mgr = sync_playwright()
        pw = mgr.__enter__()
        _thread.mgr = mgr
        _thread.pw = pw
    yield _thread.pw


def close_shared_playwright() -> None:
    """Close the shared instance of the current thread (first by the caller close respective browser)。"""
    mgr = getattr(_thread, "mgr", None)
    if mgr is not None:
        try:
            mgr.__exit__(None, None, None)
        except Exception:
            pass
    _thread.mgr = None
    _thread.pw = None


def shared_playwright_active() -> bool:
    return getattr(_thread, "mgr", None) is not None