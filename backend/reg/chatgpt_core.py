import json
import os
import re
import sys
import time
import uuid
import random
import string
import secrets
import hashlib
import base64
import argparse
import threading
from pathlib import Path
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime
from dataclasses import dataclass
from typing import Any, Dict, Optional
import urllib.parse
import urllib.request
import urllib.error

# Windows Default console/Pipes are often GBK：print emoji meeting UnicodeEncodeError collapse directly。
# ops.bat redirect to logs\*.log This is especially true when。Start early stdout/stderr Cut to UTF-8。
def _force_utf8_stdio() -> None:
    for _stream in (sys.stdout, sys.stderr):
        try:
            if hasattr(_stream, "reconfigure"):
                _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


_force_utf8_stdio()

# --- end temporary hook ---

# Retry with tape curl_cffi Session Gasket（Study scriptures mihomo agency intermittent TLS 'invalid library'）
from .cf_shim import requests, Session
# OpenAI official Sentinel SDK（Camoufox load，generate Sentinel-Token / SO-Token）
from . import sentinel_sdk
# Statistics on registration success rate by email domain name，Deactivate domain names with low success rate
from . import provider_stats
# 711 residential agency：curl_cffi direct connection meeting CONNECT aborted，Need to go through this machine relay→Clash→711
from core import proxy_711  # noqa: E402
# Email channel: built-in mailtm; The rest is left to the caller (reg/engine) Custom channel registry injection
import atexit
atexit.register(lambda: sentinel_sdk.close_browser())

# Configure output directories and requestsUA（default value = Fingerprint pool first item chrome131 Win；run() Each number can be selected independently）
OUT_DIR = Path(__file__).parent.resolve()

# Register for full coverage：single stage（like authorize）Maximum retries；Outer layer while True Maximum total attempts（Anti-agent/The time and space consumption of the whole pool）
MAX_STAGE_RETRY = 5
MAX_TOTAL_ATTEMPTS = 30

# Log in to get cookie：authorize fall email-verification Time to go to the mailbox OTP（Two stage waiting）
LOGIN_OTP_PHASE1_SEC = 45   # Wait first openai Automatically issued verification code，time out resend
LOGIN_OTP_PHASE2_SEC = 90   # resend Only new codes will be received later


def _build_chrome_fp(
    ua: str,
    major: str,
    *,
    platform: str = "Windows",
    platform_version: str = "10.0.0",
    accept_language: str = "en-US,en;q=0.9",
) -> Dict[str, str]:
    """Structure and UA / impersonate Version self-consistent Client Hints head bag。"""
    sec_ch_ua = (
        f'"Not:A-Brand";v="99", "Google Chrome";v="{major}", "Chromium";v="{major}"'
    )
    full_ver = (
        f'"Not:A-Brand";v="99.0.0.0", "Google Chrome";v="{major}.0.0.0", '
        f'"Chromium";v="{major}.0.0.0"'
    )
    return {
        "accept": "application/json, text/plain, */*",
        "accept-encoding": "gzip, deflate, br, zstd",
        "accept-language": accept_language,
        "priority": "u=1, i",
        "sec-ch-ua": sec_ch_ua,
        "sec-ch-ua-full-version-list": full_ver,
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": f'"{platform}"',
        "sec-ch-ua-platform-version": f'"{platform_version}"',
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin",
        "user-agent": ua,
        "upgrade-insecure-requests": "1",
    }


def _fp_profile(
    *,
    pid: str,
    major: str,
    impersonate: str,
    ua: str,
    platform: str,
    nav_platform: str,
    platform_version: str,
    languages: tuple,
    screen_w: int,
    screen_h: int,
    px_ratio: float,
    canvas_seed: str,
    webgl_vendor: str,
    webgl_renderer: str,
    hardware_concurrency: int = 8,
    device_memory: float = 8.0,
    accept_language: str = "en-US,en;q=0.9",
) -> Dict[str, Any]:
    """Single matching fingerprint profile：HTTP head + TLS impersonate + sentinel VM Same set of fields。"""
    ch_platform = "Windows" if platform.lower().startswith("win") else (
        "macOS" if platform.lower().startswith("mac") else platform
    )
    chrome_fp = _build_chrome_fp(
        ua, major,
        platform=ch_platform,
        platform_version=platform_version,
        accept_language=accept_language,
    )
    return {
        "id": pid,
        "ua": ua,
        "impersonate": impersonate,
        "chrome_fp": chrome_fp,
        "platform": nav_platform,          # navigator.platform e.g. Win32 / MacIntel
        "os_platform": ch_platform,        # sec-ch-ua-platform e.g. Windows / macOS
        "languages": list(languages),
        "screen": {
            "width": screen_w,
            "height": screen_h,
            "px_ratio": px_ratio,
        },
        "canvas_seed": canvas_seed,
        "webgl_vendor": webgl_vendor,
        "webgl_renderer": webgl_renderer,
        "hardware_concurrency": hardware_concurrency,
        "device_memory": device_memory,
        "chrome_major": major,
    }


# ≥12 a reality Chrome fingerprint profile（impersonate Must curl_cffi support；UA/sec-ch-ua/major strict binding）
# curl_cffi 0.15 desktop Chrome：100/101/104/107/110/116/119/120/123/124/131/133a/136/142/145/146
FP_POOL: list = [
    # --- Chrome 131 Windows multiple resolutions ---
    _fp_profile(
        pid="chrome131_win_fhd",
        major="131", impersonate="chrome131",
        ua=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"),
        platform="Windows", nav_platform="Win32", platform_version="10.0.0",
        languages=("en-US", "en"),
        screen_w=1920, screen_h=1080, px_ratio=1.0,
        canvas_seed="win-fhd-gtx1060-a1",
        webgl_vendor="Google Inc. (NVIDIA)",
        webgl_renderer="ANGLE (NVIDIA, NVIDIA GeForce GTX 1060 Direct3D11 vs_5_0 ps_5_0)",
        hardware_concurrency=8, device_memory=8.0,
    ),
    _fp_profile(
        pid="chrome131_win_qhd",
        major="131", impersonate="chrome131",
        ua=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"),
        platform="Windows", nav_platform="Win32", platform_version="15.0.0",
        languages=("en-US", "en"),
        screen_w=2560, screen_h=1440, px_ratio=1.0,
        canvas_seed="win-qhd-rtx3060-b2",
        webgl_vendor="Google Inc. (NVIDIA)",
        webgl_renderer="ANGLE (NVIDIA, NVIDIA GeForce RTX 3060 Direct3D11 vs_5_0 ps_5_0)",
        hardware_concurrency=12, device_memory=16.0,
    ),
    _fp_profile(
        pid="chrome131_win_hd",
        major="131", impersonate="chrome131",
        ua=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"),
        platform="Windows", nav_platform="Win32", platform_version="10.0.0",
        languages=("en-US", "en", "zh-CN"),
        screen_w=1366, screen_h=768, px_ratio=1.0,
        canvas_seed="win-hd-uhd620-c3",
        webgl_vendor="Google Inc. (Intel)",
        webgl_renderer="ANGLE (Intel, Intel(R) UHD Graphics 620 Direct3D11 vs_5_0 ps_5_0)",
        hardware_concurrency=4, device_memory=8.0,
        accept_language="en-US,en;q=0.9,zh-CN;q=0.8",
    ),
    _fp_profile(
        pid="chrome131_win_uhd",
        major="131", impersonate="chrome131",
        ua=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"),
        platform="Windows", nav_platform="Win32", platform_version="15.0.0",
        languages=("en-US", "en"),
        screen_w=3840, screen_h=2160, px_ratio=1.5,
        canvas_seed="win-uhd-rtx4070-c4",
        webgl_vendor="Google Inc. (NVIDIA)",
        webgl_renderer="ANGLE (NVIDIA, NVIDIA GeForce RTX 4070 Direct3D11 vs_5_0 ps_5_0)",
        hardware_concurrency=16, device_memory=32.0,
    ),
    _fp_profile(
        pid="chrome131_mac_retina",
        major="131", impersonate="chrome131",
        ua=("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"),
        platform="macOS", nav_platform="MacIntel", platform_version="14.2.1",
        languages=("en-US", "en"),
        screen_w=1440, screen_h=900, px_ratio=2.0,
        canvas_seed="mac-retina-applem1-d4",
        webgl_vendor="Google Inc. (Apple)",
        webgl_renderer="ANGLE (Apple, Apple M1, OpenGL 4.1)",
        hardware_concurrency=8, device_memory=8.0,
    ),
    # --- Chrome 133 / 136 ---
    _fp_profile(
        pid="chrome133_win_fhd",
        major="133", impersonate="chrome133a",
        ua=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36"),
        platform="Windows", nav_platform="Win32", platform_version="10.0.0",
        languages=("en-US", "en"),
        screen_w=1920, screen_h=1080, px_ratio=1.0,
        canvas_seed="win-fhd-rtx4060-e5",
        webgl_vendor="Google Inc. (NVIDIA)",
        webgl_renderer="ANGLE (NVIDIA, NVIDIA GeForce RTX 4060 Direct3D11 vs_5_0 ps_5_0)",
        hardware_concurrency=16, device_memory=16.0,
    ),
    _fp_profile(
        pid="chrome133_win_laptop",
        major="133", impersonate="chrome133a",
        ua=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36"),
        platform="Windows", nav_platform="Win32", platform_version="10.0.0",
        languages=("en-US", "en"),
        screen_w=1600, screen_h=900, px_ratio=1.25,
        canvas_seed="win-1600-irisxe-e6",
        webgl_vendor="Google Inc. (Intel)",
        webgl_renderer="ANGLE (Intel, Intel(R) Iris(R) Xe Graphics Direct3D11 vs_5_0 ps_5_0)",
        hardware_concurrency=8, device_memory=16.0,
    ),
    _fp_profile(
        pid="chrome136_win_qhd",
        major="136", impersonate="chrome136",
        ua=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36"),
        platform="Windows", nav_platform="Win32", platform_version="15.0.0",
        languages=("en-US", "en"),
        screen_w=2560, screen_h=1440, px_ratio=1.25,
        canvas_seed="win-qhd-rx7600-f6",
        webgl_vendor="Google Inc. (AMD)",
        webgl_renderer="ANGLE (AMD, AMD Radeon RX 7600 Direct3D11 vs_5_0 ps_5_0)",
        hardware_concurrency=12, device_memory=32.0,
    ),
    _fp_profile(
        pid="chrome136_win_fhd",
        major="136", impersonate="chrome136",
        ua=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36"),
        platform="Windows", nav_platform="Win32", platform_version="10.0.0",
        languages=("en-US", "en", "es"),
        screen_w=1920, screen_h=1080, px_ratio=1.0,
        canvas_seed="win-fhd-gtx1660-f7",
        webgl_vendor="Google Inc. (NVIDIA)",
        webgl_renderer="ANGLE (NVIDIA, NVIDIA GeForce GTX 1660 SUPER Direct3D11 vs_5_0 ps_5_0)",
        hardware_concurrency=6, device_memory=16.0,
        accept_language="en-US,en;q=0.9,es;q=0.8",
    ),
    _fp_profile(
        pid="chrome136_mac_studio",
        major="136", impersonate="chrome136",
        ua=("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36"),
        platform="macOS", nav_platform="MacIntel", platform_version="15.1.0",
        languages=("en-US", "en"),
        screen_w=1680, screen_h=1050, px_ratio=2.0,
        canvas_seed="mac-studio-m2pro-h8",
        webgl_vendor="Google Inc. (Apple)",
        webgl_renderer="ANGLE (Apple, Apple M2 Pro, OpenGL 4.1)",
        hardware_concurrency=10, device_memory=16.0,
    ),
    _fp_profile(
        pid="chrome136_mac_mba",
        major="136", impersonate="chrome136",
        ua=("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36"),
        platform="macOS", nav_platform="MacIntel", platform_version="14.5.0",
        languages=("en-US", "en"),
        screen_w=2560, screen_h=1600, px_ratio=2.0,
        canvas_seed="mac-mba-m3-h9",
        webgl_vendor="Google Inc. (Apple)",
        webgl_renderer="ANGLE (Apple, Apple M3, OpenGL 4.1)",
        hardware_concurrency=8, device_memory=16.0,
    ),
    # --- older / newer major（dispersion JA3 pool） ---
    _fp_profile(
        pid="chrome124_win_fhd",
        major="124", impersonate="chrome124",
        ua=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"),
        platform="Windows", nav_platform="Win32", platform_version="10.0.0",
        languages=("en-GB", "en-US", "en"),
        screen_w=1536, screen_h=864, px_ratio=1.25,
        canvas_seed="win-1536-irisxe-g7",
        webgl_vendor="Google Inc. (Intel)",
        webgl_renderer="ANGLE (Intel, Intel(R) Iris(R) Xe Graphics Direct3D11 vs_5_0 ps_5_0)",
        hardware_concurrency=8, device_memory=16.0,
        accept_language="en-GB,en-US;q=0.9,en;q=0.8",
    ),
    _fp_profile(
        pid="chrome120_win_hdplus",
        major="120", impersonate="chrome120",
        ua=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"),
        platform="Windows", nav_platform="Win32", platform_version="10.0.0",
        languages=("en-US", "en"),
        screen_w=1680, screen_h=1050, px_ratio=1.0,
        canvas_seed="win-1680-rx580-i1",
        webgl_vendor="Google Inc. (AMD)",
        webgl_renderer="ANGLE (AMD, AMD Radeon RX 580 Series Direct3D11 vs_5_0 ps_5_0)",
        hardware_concurrency=8, device_memory=16.0,
    ),
    _fp_profile(
        pid="chrome123_win_fhd",
        major="123", impersonate="chrome123",
        ua=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"),
        platform="Windows", nav_platform="Win32", platform_version="10.0.0",
        languages=("en-US", "en"),
        screen_w=1920, screen_h=1200, px_ratio=1.0,
        canvas_seed="win-1920x1200-uhd770-i2",
        webgl_vendor="Google Inc. (Intel)",
        webgl_renderer="ANGLE (Intel, Intel(R) UHD Graphics 770 Direct3D11 vs_5_0 ps_5_0)",
        hardware_concurrency=12, device_memory=32.0,
    ),
    _fp_profile(
        pid="chrome142_win_qhd",
        major="142", impersonate="chrome142",
        ua=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36"),
        platform="Windows", nav_platform="Win32", platform_version="15.0.0",
        languages=("en-US", "en"),
        screen_w=2560, screen_h=1440, px_ratio=1.0,
        canvas_seed="win-qhd-rtx4070ti-j1",
        webgl_vendor="Google Inc. (NVIDIA)",
        webgl_renderer="ANGLE (NVIDIA, NVIDIA GeForce RTX 4070 Ti Direct3D11 vs_5_0 ps_5_0)",
        hardware_concurrency=16, device_memory=32.0,
    ),
    _fp_profile(
        pid="chrome142_mac_retina",
        major="142", impersonate="chrome142",
        ua=("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36"),
        platform="macOS", nav_platform="MacIntel", platform_version="15.2.0",
        languages=("en-US", "en"),
        screen_w=1512, screen_h=982, px_ratio=2.0,
        canvas_seed="mac-14m3pro-j2",
        webgl_vendor="Google Inc. (Apple)",
        webgl_renderer="ANGLE (Apple, Apple M3 Pro, OpenGL 4.1)",
        hardware_concurrency=12, device_memory=18.0,
    ),
    _fp_profile(
        pid="chrome145_win_fhd",
        major="145", impersonate="chrome145",
        ua=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36"),
        platform="Windows", nav_platform="Win32", platform_version="15.0.0",
        languages=("en-US", "en"),
        screen_w=1920, screen_h=1080, px_ratio=1.0,
        canvas_seed="win-fhd-arc-a770-k1",
        webgl_vendor="Google Inc. (Intel)",
        webgl_renderer="ANGLE (Intel, Intel(R) Arc(TM) A770 Graphics Direct3D11 vs_5_0 ps_5_0)",
        hardware_concurrency=16, device_memory=32.0,
    ),
    _fp_profile(
        pid="chrome146_win_uwqhd",
        major="146", impersonate="chrome146",
        ua=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36"),
        platform="Windows", nav_platform="Win32", platform_version="15.0.0",
        languages=("en-US", "en"),
        screen_w=3440, screen_h=1440, px_ratio=1.0,
        canvas_seed="win-uwqhd-rtx4080-k2",
        webgl_vendor="Google Inc. (NVIDIA)",
        webgl_renderer="ANGLE (NVIDIA, NVIDIA GeForce RTX 4080 Direct3D11 vs_5_0 ps_5_0)",
        hardware_concurrency=24, device_memory=64.0,
    ),
    _fp_profile(
        pid="chrome146_mac_studio",
        major="146", impersonate="chrome146",
        ua=("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36"),
        platform="macOS", nav_platform="MacIntel", platform_version="15.3.0",
        languages=("en-US", "en"),
        screen_w=3008, screen_h=1692, px_ratio=2.0,
        canvas_seed="mac-studio-m2max-k3",
        webgl_vendor="Google Inc. (Apple)",
        webgl_renderer="ANGLE (Apple, Apple M2 Max, OpenGL 4.1)",
        hardware_concurrency=12, device_memory=32.0,
    ),
]

# backwards compatible：The default global constant points to the first item in the pool（mail.tm Wait for non OpenAI The path can continue to be used）
_DEFAULT_FP = FP_POOL[0]
UA = _DEFAULT_FP["ua"]
IMPERSONATE = _DEFAULT_FP["impersonate"]
SEC_CH_UA = _DEFAULT_FP["chrome_fp"]["sec-ch-ua"]
CHROME_FP = dict(_DEFAULT_FP["chrome_fp"])


def choose_fp(seed: Optional[str] = None) -> Dict[str, Any]:
    """Choose a set of matching fingerprints for each number。

    - environment variables ANTI_FUZZ_FP_ID：fix something profile（id or 0-based subscript，for debugging）
    - incoming seed/email：SHA256 Stable mapping to an item in the pool
    - otherwise random.choice
    Return deep copy，Avoid contamination between sessions chrome_fp dict。
    """
    force = (os.environ.get("ANTI_FUZZ_FP_ID") or "").strip()
    picked = None
    if force:
        if force.isdigit():
            idx = int(force) % len(FP_POOL)
            picked = FP_POOL[idx]
        else:
            for p in FP_POOL:
                if p.get("id") == force:
                    picked = p
                    break
            if picked is None:
                # allow chrome131 / chrome136 Wait major or impersonate Match first item
                for p in FP_POOL:
                    if force in (p.get("impersonate"), p.get("chrome_major"), f"chrome{p.get('chrome_major')}"):
                        picked = p
                        break
        if picked is None:
            print(f"[anti-fuzz] ANTI_FUZZ_FP_ID={force!r} Not matched，Fallback random")
    if picked is None and seed:
        h = hashlib.sha256(str(seed).encode("utf-8", errors="replace")).hexdigest()
        idx = int(h[:8], 16) % len(FP_POOL)
        picked = FP_POOL[idx]
    if picked is None:
        picked = random.choice(FP_POOL)
    # Deep copy variable substructure
    out = dict(picked)
    out["chrome_fp"] = dict(picked["chrome_fp"])
    out["screen"] = dict(picked["screen"])
    out["languages"] = list(picked["languages"])
    return out


def _fp_summary(fp: Dict[str, Any]) -> str:
    scr = fp.get("screen") or {}
    return (
        f"id={fp.get('id')} chrome={fp.get('chrome_major')} "
        f"impersonate={fp.get('impersonate')} platform={fp.get('platform')} "
        f"screen={scr.get('width')}x{scr.get('height')}@{scr.get('px_ratio')}"
    )


def _bind_session_fp(session, fp: Dict[str, Any]) -> None:
    """Attach the matching fingerprint of this number to Session，for next-auth Wait for the auxiliary function to read。"""
    try:
        session._anti_fuzz_fp = fp  # type: ignore[attr-defined]
        session._anti_fuzz_ua = fp.get("ua") or UA  # type: ignore[attr-defined]
        session._anti_fuzz_impersonate = fp.get("impersonate") or IMPERSONATE  # type: ignore[attr-defined]
    except Exception:
        pass


def _session_ua(session=None, default: str = "") -> str:
    if session is not None:
        ua = getattr(session, "_anti_fuzz_ua", None)
        if ua:
            return ua
        try:
            h = session.headers.get("user-agent") or session.headers.get("User-Agent")
            if h:
                return h
        except Exception:
            pass
    return default or UA


def _session_impersonate(session=None, default: str = "") -> str:
    if session is not None:
        imp = getattr(session, "_anti_fuzz_impersonate", None)
        if imp:
            return imp
        imp = getattr(session, "impersonate", None)
        if imp:
            return str(imp)
    return default or IMPERSONATE


def _make_trace_headers():
    """generate Datadog APM trace headers（and real browser RUM SDK consistent）"""
    trace_id = random.randint(10**17, 10**18 - 1)
    parent_id = random.randint(10**17, 10**18 - 1)
    tp = f"00-{uuid.uuid4().hex}-{format(parent_id, '016x')}-01"
    return {
        "traceparent": tp, "tracestate": "dd=s:1;o:rum",
        "x-datadog-origin": "rum", "x-datadog-sampling-priority": "1",
        "x-datadog-trace-id": str(trace_id), "x-datadog-parent-id": str(parent_id),
    }


# ---------- Risk prevention and control：random time difference + New device per number（See ANTI_FUZZING.md）----------
# ANTI_FUZZ=0 Step jitter can be turned off（debug）；Room cooling is still recommended to be retained。
def _anti_fuzz_enabled() -> bool:
    return os.environ.get("ANTI_FUZZ", "1").strip() not in ("0", "false", "False", "no", "off")


def _new_oai_did() -> str:
    """Force new device every time you register ID（UUID）。same time run() Reuse throughout the entire process，Prohibit cross-number reuse。"""
    return str(uuid.uuid4())


# Thread local cancellation callback：Each thread is independent during concurrent registration，Avoid stepping on each other in global lists。
# remain list Shape compatible with old references，But read and write TLS。
_CANCEL_TLS = threading.local()
_CANCEL_HOLDER = [None]  # compatible：single thread/The old path is still writable [0]；_interruptible_sleep priority TLS


def _set_cancel_check(fn):
    _CANCEL_TLS.fn = fn
    _CANCEL_HOLDER[0] = fn


def _get_cancel_check():
    fn = getattr(_CANCEL_TLS, "fn", None)
    if fn is not None:
        return fn
    return _CANCEL_HOLDER[0]


def _interruptible_sleep(t: float) -> None:
    """Interruptible by cancel signal sleep（0.2s granularity）。If the cancel callback returns true, it will return immediately.。"""
    end = time.time() + t
    while True:
        ck = _get_cancel_check()
        if ck and ck():
            return
        remaining = end - time.time()
        if remaining <= 0:
            return
        time.sleep(min(0.2, remaining))

def _human_delay(lo: float = 0.4, hi: float = 1.8, label: str = "") -> float:
    """Real-life rhythm jitter between steps：uniformly distributed + Occasionally long pauses。return actual sleep seconds。"""
    if not _anti_fuzz_enabled():
        return 0.0
    try:
        lo_e = float(os.environ.get("ANTI_FUZZ_STEP_LO", lo))
        hi_e = float(os.environ.get("ANTI_FUZZ_STEP_HI", hi))
        lo, hi = lo_e, hi_e
    except Exception:
        pass
    if hi < lo:
        lo, hi = hi, lo
    t = random.uniform(lo, hi)
    # about 15% Probability「daze」one time，Break up the mechanical rhythm
    if random.random() < 0.15:
        t += random.uniform(0.5, 2.5)
    if label:
        print(f"[anti-fuzz] delay {t:.2f}s ({label})")
    _interruptible_sleep(t)
    return t


def _batch_cooldown_seconds() -> int:
    """Cooling down between accounts（Second）。Environment variables can cover upper and lower limits。"""
    try:
        lo = int(os.environ.get("ANTI_FUZZ_BATCH_LO", "8"))
        hi = int(os.environ.get("ANTI_FUZZ_BATCH_HI", "25"))
    except Exception:
        lo, hi = 8, 25
    if hi < lo:
        lo, hi = hi, lo
    return random.randint(lo, hi)


def _retry_backoff(attempt: int, base: float = 0.8) -> float:
    """Retry on failure：exponential backoff + Jitter base * 2^(n-1) + U(0,1)。attempt from 1 rise。"""
    if not _anti_fuzz_enabled():
        t = float(attempt)
        _interruptible_sleep(t)
        return t
    n = max(1, int(attempt))
    t = float(base) * (2 ** (n - 1)) + random.uniform(0.0, 1.0)
    print(f"[anti-fuzz] retry backoff {t:.2f}s (attempt={n})")
    _interruptible_sleep(t)
    return t


def _bind_oai_did(session, did: str) -> None:
    """Bundle oai-did write chatgpt.com + .openai.com，ensure authorize / sentinel Homology。"""
    if not did:
        return
    try:
        session.cookies.set("oai-did", did, domain=".openai.com", path="/")
        session.cookies.set("oai-did", did, domain="chatgpt.com", path="/")
    except Exception:
        pass

# ========== 1. Mail.tm Temporary mailbox processing module ==========

def rstr(n=10): 
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=n))


def _local_or_env_proxies():
    """DDG / mail.tm wait「Can't go 711 residential pool」of API Use proxy。

    root cause repair：Clear old logic HTTP_PROXY Force true·direct connection，but quack.duckduckgo.com /
    api.mail.tm Real direct connection in domestic network curl: (28) time out；And naked curl_cffi The test can pass，
    precisely because libcurl Default read HTTP_PROXY=local machine Clash(7897)。

    Strategy：
      1) Use native from environment variables/Universal proxy（jump over 711 with native 711 relay）
      2) detection Clash mixed-port（7897/17897/7890）
      3) Return only if there is none None（Really direct connection）
    Never run() incoming 711 sticky session Use these API superior。
    """
    import socket

    def _is_711_like(url: str) -> bool:
        if not url:
            return False
        if proxy_711.is_711_proxy(url):
            return True
        low = url.lower()
        # proxy_711 Chain relay default port
        if "127.0.0.1:18792" in low or "localhost:18792" in low:
            return True
        return False

    for k in (
        "HTTPS_PROXY", "HTTP_PROXY", "https_proxy", "http_proxy",
        "ALL_PROXY", "all_proxy",
    ):
        v = (os.environ.get(k) or "").strip()
        if not v or _is_711_like(v):
            continue
        return {"http": v, "https": v}

    for item in ("127.0.0.1:7897", "127.0.0.1:17897", "127.0.0.1:7890"):
        host, port_s = item.rsplit(":", 1)
        try:
            sock = socket.create_connection((host, int(port_s)), timeout=0.6)
            sock.close()
            u = f"http://{item}"
            return {"http": u, "https": u}
        except OSError:
            continue
    return None


def mreq(mt, pt, js=None, tk=None, proxies=None):
    hdrs = {
        "content-type": "application/json",
        "accept": "application/json",
        "user-agent": UA,
        "pragma": "no-cache"
    }
    if tk: 
        hdrs["authorization"] = f"Bearer {tk}"
    # mail.tm Not leaving 711；If the caller does not specify a proxy，Use this machine Clash / HTTP_PROXY（Do not clear env）
    if proxies is None:
        proxies = _local_or_env_proxies()
    try:
        with Session(proxies=proxies) as s:
            return s.request(mt, f"https://api.mail.tm{pt}", json=js, headers=hdrs, timeout=20)
    except: 
        return None

def getotp(tk, proxies=None, cancel_check=None):
    for _ in range(60):
        if cancel_check and cancel_check():
            return None
        r = mreq("GET", "/messages", tk=tk, proxies=proxies)
        if r and r.status_code == 200:
            try: 
                dat = r.json()
            except: 
                time.sleep(8); continue
                
            msgs = dat.get("hydra:member", []) if isinstance(dat, dict) else dat
            if not isinstance(msgs, list): msgs = []
                
            for m in msgs:
                if not isinstance(m, dict): continue
                sb = m.get("subject", "")
                intro = m.get("intro", "")
                if "OpenAI" in sb or "ChatGPT" in sb or "code" in intro:
                    rb = mreq("GET", f"/messages/{m.get('id')}", tk=tk, proxies=proxies)
                    if rb and rb.status_code == 200:
                        txt = rb.json().get("text", "")
                        mt = re.search(r"(\d{6})", txt) or re.search(r"(\d{6})", sb)
                        if mt: 
                            return mt.group(1)
        # Split 8 seconds sleep for 1 second granularity，Facilitates timely response to cancellation signals
        for _ in range(8):
            if cancel_check and cancel_check():
                return None
            time.sleep(1)
    return None

def setup_mail_tm(proxies=None, cancel_check=None):
    """Dynamic acquisition mail.tm mailbox and return the required data"""
    mail_pw = "at41rvxgptye"
    
    # Dynamically obtain currently available email domain names
    domain_res = mreq("GET", "/domains", proxies=proxies)
    if not domain_res or domain_res.status_code != 200:
        print("  [!] Unable to obtain available email domain name")
        return None, None, None
    
    try:
        js_data = domain_res.json()
        if isinstance(js_data, list):
            domains_data = js_data
        elif isinstance(js_data, dict):
            domains_data = js_data.get("hydra:member", js_data.get("hydra:collection", []))
        else:
            domains_data = []

        if not domains_data:
            print("  [!] Domain name list is empty")
            return None, None, None
            
        active_domain = domains_data[0].get("domain")
    except Exception as e:
        print(f"  [!] Failed to resolve domain name: {e}")
        return None, None, None

    email = f"{rstr(10)}@{active_domain}"
    openai_password = _gen_password()  # for OpenAI Generate strong passwords for accounts
    
    # register mail.tm Mail
    r = mreq("POST", "/accounts", {"address": email, "password": mail_pw}, proxies=proxies)
    if not r or r.status_code not in [200, 201]: 
        print(f"  [!] Email registration rejected: {r.text if r else 'No response'}")
        return None, None, None
        
    # Get mail.tm of Token
    r = mreq("POST", "/token", {"address": email, "password": mail_pw}, proxies=proxies)
    if not r or r.status_code != 200: 
        print("  [!] Get email Token fail")
        return None, None, None
        
    mail_token = r.json().get("token")
    if not mail_token:
        return None, None, None

    # Define the closure function to extract the verification code
    def fetch_code():
        print("  [*] Waiting for verification code (The maximum waiting time is approx.8minute)...")
        return getotp(mail_token, proxies=proxies, cancel_check=cancel_check)
        
    return email, openai_password, fetch_code


def _msg_date_ts(msg):
    """Parse emails Date The head is unix timestamp；Return on failure None。"""
    try:
        raw = msg.get("Date") if msg is not None else None
        if not raw:
            return None
        dt = parsedate_to_datetime(str(raw))
        if dt is None:
            return None
        return float(dt.timestamp())
    except Exception:
        return None


def _imap_fetch_message_bytes(conn, mid):
    """Pull the complete email raw bytes。

    iCloud (imap.mail.me.com) right (RFC822) Often returns empty body ``N ()``，BODY.PEEK[] normal。
    163/126 Both are available；priority BODY.PEEK[]（Don't change \\Seen），Fall back after failure RFC822。
    """
    for spec in ("(BODY.PEEK[])", "(RFC822)"):
        try:
            _typ, data = conn.fetch(mid, spec)
        except Exception:
            continue
        if not data:
            continue
        for item in data:
            if isinstance(item, tuple) and len(item) >= 2 and isinstance(item[1], (bytes, bytearray)):
                if item[1]:
                    return bytes(item[1])
    return None


def imap_get_otp(email_alias=None, cancel_check=None, timeout_min=None, timeout_sec=None,
                 seen_ids=None, not_before=None, imap_label=None):
    """Connect to forwarding mailbox（IMAP），Traverse IMAP_ACCOUNTS Find it in every inbox OpenAI Verification code。
    email_alias: For registration @duck.com Alias，for filtering DDG Forwarded email。
    timeout_sec: priority；Ends in seconds when given（two stages OTP use）。
    timeout_min: Compatible with old calls；timeout_sec Minutes not given（default IMAP_TIMEOUT_MIN）。
    seen_ids: Optional set，Reuse seen messages across stages id（With account prefix），avoid resend Scan old messages again。
    not_before: Optional unix ts；only accept Date >= not_before - SKEW of OTP，Block historical code / resend forward OTP1。
    """
    accounts = list(IMAP_ACCOUNTS) if IMAP_ACCOUNTS else []
    if imap_label:
        _filtered = [a for a in accounts if (a.get("label") or "") == imap_label]
        if _filtered:
            accounts = _filtered
        # Specify label Filter only if it exists；Otherwise keep all（compatible duck/163 Not passed on label）
    if not accounts:
        # backwards compatible：Fallback to single account when there is no list IMAP_* constant
        if IMAP_USER:
            accounts = [{
                "host": IMAP_HOST, "port": IMAP_PORT,
                "user": IMAP_USER, "auth": IMAP_AUTH, "label": "default",
            }]
    if not accounts or not any(a.get("user") for a in accounts):
        print("  [!] Not configured IMAP_ACCOUNTS / IMAP_USER（Forwarding email address）")
        return None
    if timeout_sec is not None:
        total_sec = max(1, int(timeout_sec))
    else:
        total_sec = int((timeout_min or IMAP_TIMEOUT_MIN) * 60)
    import imaplib
    import email as _email

    deadline = time.time() + total_sec
    # short timeout（two stages 10s）use 1s polling、Wait after shortening baseline；Long timeout remains the same 5s Rhythm
    short_mode = total_sec <= 45
    baseline_sleep = 1 if short_mode else 5
    poll_sleep = 1 if short_mode else 5
    if seen_ids is None:
        seen_ids = set()
    # Independent baseline per account；Reuse across stages seen Baseline reconstruction is skipped entirely when
    skip_baseline = bool(seen_ids)
    baseline_done = {
        (a.get("label") or a.get("user") or str(i)): skip_baseline
        for i, a in enumerate(accounts)
    }
    alias = (email_alias or "").lower()
    skew = IMAP_OTP_DATE_SKEW_SEC
    nb = float(not_before) if not_before is not None else None

    def _seen_key(label, mid):
        """Across mailboxes mid possible conflict，use label prefix isolation。"""
        mid_s = mid.decode("utf-8", errors="replace") if isinstance(mid, (bytes, bytearray)) else str(mid)
        return f"{label}:{mid_s}"

    while time.time() < deadline:
        if cancel_check and cancel_check():
            return None

        any_baseline_this_round = False

        for acc_i, acc in enumerate(accounts):
            if cancel_check and cancel_check():
                return None
            if time.time() >= deadline:
                return None

            label = acc.get("label") or acc.get("user") or str(acc_i)
            host = acc.get("host") or IMAP_HOST
            port = int(acc.get("port") or IMAP_PORT or 993)
            user = acc.get("user") or ""
            auth = acc.get("auth") or ""
            if not user or not auth:
                continue

            # 163/126/yeah.net Must go first IMAP ID Order，Otherwise the login will be refused
            need_id = any(h in host for h in ("163.com", "126.com", "yeah.net"))

            conn = None
            try:
                conn = imaplib.IMAP4_SSL(host, port, timeout=15)
                if need_id:
                    imaplib.Commands['ID'] = ('NONAUTH', 'AUTH', 'SELECTED')
                    conn._simple_command('ID', '("name" "IMAPClient" "version" "1.0")')
                conn.login(user, auth)
                conn.select("INBOX", readonly=True)

                _, msg_nums = conn.search(None, "ALL")
                ids = msg_nums[0].split() if msg_nums and msg_nums[0] else []

                # First poll establishes baseline：Just put「No OTP」of historical messages marked as seen。
                # critical fix：If the verification code arrives before the first poll（OpenAI generally 5s Delivered within），
                # It cannot be included in the baseline，Otherwise it will be permanently skipped → stuck waiting OTP。
                # So the baseline only skips really old emails，OTP Messages are retained for retrieval even if they are older than polled。
                # not_before：OTP like Date earlier than window（or none Date）Also marked seen，Block historical code。
                if not baseline_done.get(label):
                    skipped = 0
                    for mid in ids:
                        sk = _seen_key(label, mid)
                        try:
                            raw0 = _imap_fetch_message_bytes(conn, mid)
                            if not raw0:
                                seen_ids.add(sk)
                                skipped += 1
                                continue
                            m0 = _email.message_from_bytes(raw0)
                            fr0 = str(m0.get("From", "") or "").lower()
                            sj0 = str(m0.get("Subject", "") or "").lower()
                            is_otp = (("openai" in fr0 or "noreply" in fr0)
                                        and "verification code" in sj0)
                        except Exception:
                            is_otp = False
                            m0 = None
                        if not is_otp:
                            seen_ids.add(sk)
                            skipped += 1
                        elif nb is not None:
                            dts = _msg_date_ts(m0) if m0 is not None else None
                            if dts is None or dts < (nb - skew):
                                # none Date of OTP Conservative standard seen；Date If it is too old, the historical code will be blocked.
                                seen_ids.add(sk)
                                skipped += 1
                    baseline_done[label] = True
                    any_baseline_this_round = True
                    print(f"  [*] IMAP[{label}] baseline：jump over {skipped} Feng Fei OTP/old OTP mail，Waiting for new verification email..."
                          + (f" not_before={nb:.0f}" if nb is not None else ""))
                    conn.logout()
                    conn = None
                    continue  # Next account；If there is a baseline in this round, it will be unified at the end sleep

                for mid in reversed(ids[-40:]):
                    sk = _seen_key(label, mid)
                    if sk in seen_ids:
                        continue
                    seen_ids.add(sk)
                    raw = _imap_fetch_message_bytes(conn, mid)
                    if not raw:
                        continue
                    msg = _email.message_from_bytes(raw)
                    to_addr = str(msg.get("To", "") or "").lower()
                    from_addr = str(msg.get("From", "") or "").lower()
                    subject = str(msg.get("Subject", "") or "")
                    # provisional diagnosis：Confirm every new email label/from/to and alias Match situation
                    print(f"  [debug] scan [{label}] From={from_addr[:50]} To={to_addr[:50]} alias={alias}")
                    # Filter by current alias：DDG When forwarding, always write the alias in From rewrite
                    # （noreply_at_tm.openai.com_<local>@duck.com）and/or To。
                    # old logic"or from openai/noreply"will extract old OTP → wrong_email_otp_code。
                    # +tag emergency alias：OpenAI May be sent to base+tag，DDG Or maybe just recognize base；
                    # Therefore, both complete matches alias and base local（go +tag）。
                    if alias:
                        base_local = alias.split("@", 1)[0].split("+", 1)[0]
                        hay = f"{to_addr} {from_addr}"
                        if alias not in hay and base_local not in hay:
                            continue
                    if not alias and "openai" not in from_addr and "noreply" not in from_addr \
                            and "openai" not in subject.lower() and "chatgpt" not in subject.lower():
                        continue

                    # not_before time window：extract 6 filter old before bitcode OTP / none Date mail
                    msg_date_ts = _msg_date_ts(msg)
                    if nb is not None:
                        if msg_date_ts is None:
                            print(f"  [~] skip none Date mail [{label}] mid={mid!r} "
                                  f"From={from_addr[:80]} To={to_addr[:80]}")
                            continue
                        if msg_date_ts < (nb - skew):
                            print(f"  [~] skip old OTP [{label}] mid={mid!r} Date={msg_date_ts:.0f} "
                                  f"not_before={nb:.0f} skew={skew} From={from_addr[:60]}")
                            continue

                    body_parts = []
                    if msg.is_multipart():
                        for part in msg.walk():
                            ct = part.get_content_type()
                            if ct in ("text/plain", "text/html"):
                                try:
                                    payload = part.get_payload(decode=True)
                                except Exception:
                                    continue
                                if payload:
                                    charset = part.get_content_charset() or "utf-8"
                                    body_parts.append(payload.decode(charset, errors="replace"))
                    else:
                        try:
                            payload = msg.get_payload(decode=True)
                        except Exception:
                            payload = None
                        if payload:
                            charset = msg.get_content_charset() or "utf-8"
                            body_parts.append(payload.decode(charset, errors="replace"))

                    combined = subject + " " + " ".join(body_parts)
                    # go style/script with all tags，avoid matching CSS color(like #000000)or HTML number
                    combined = re.sub(r'<style[^>]*>.*?</style>', '', combined, flags=re.DOTALL | re.IGNORECASE)
                    combined = re.sub(r'<script[^>]*>.*?</script>', '', combined, flags=re.DOTALL | re.IGNORECASE)
                    combined = re.sub(r'<[^>]+>', ' ', combined)
                    m = re.search(r'(?<!\d)(\d{6})(?!\d)', combined)
                    if m:
                        code = m.group(1)
                        msgid = str(msg.get("Message-ID", "") or "")
                        date_s = f"{msg_date_ts:.0f}" if msg_date_ts is not None else "None"
                        nb_s = f"{nb:.0f}" if nb is not None else "None"
                        print(f"  [*] IMAP[{label}] OTP hit code={code} Date={date_s} Message-ID={msgid} "
                              f"From={from_addr[:80]} To={to_addr[:80]} not_before={nb_s}")
                        return code
                conn.logout()
                conn = None
            except (imaplib.IMAP4.error, OSError) as e:
                print(f"  [!] IMAP[{label}] Connection abnormality: {e}")
            finally:
                if conn:
                    try:
                        conn.logout()
                    except Exception:
                        pass

        # There are accounts in this round that have just created a baseline → use baseline_sleep；otherwise poll_sleep
        sleep_n = baseline_sleep if any_baseline_this_round else poll_sleep
        for _ in range(sleep_n):
            if cancel_check and cancel_check():
                return None
            if time.time() >= deadline:
                return None
            time.sleep(1)
    return None


# ========== 2. OpenAI OAuth2 Authorization and environment generation module ==========

# key：web The outflow number used to capture packets is /api/accounts/authorize（No Hydra /oauth/authorize）。
# /oauth/authorize It is still possible OTP，But the session state machine is different from create_account When not aligned
# meeting 400 invalid_auth_step（See camoufox_captured.json[3]/[4]、NOBROWSER_INVALID_AUTH_STEP.md）。
AUTH_URL = "https://auth.openai.com/api/accounts/authorize"
TOKEN_URL = "https://auth.openai.com/oauth/token"
CLIENT_ID = "app_X8zY6vW2pQ9tR3dE7nK1jL5gH"   # web flow ChatGPT Web client（No Codex app_EMoamEEZ…）
DEFAULT_REDIRECT_URI = "https://chatgpt.com/api/auth/callback/openai"
DEFAULT_SCOPE = "openid email profile offline_access model.request model.read organization.read organization.write"

def _gen_password() -> str:
    alphabet = string.ascii_letters + string.digits
    special = "!@#$%^&*.-"
    base = [
        random.choice(string.ascii_lowercase),
        random.choice(string.ascii_uppercase),
        random.choice(string.digits),
        random.choice(special),
    ]
    base += [random.choice(alphabet + special) for _ in range(12)]
    random.shuffle(base)
    return "".join(base)

def _random_name() -> str:
    return ''.join(random.choice(string.ascii_lowercase) for _ in range(random.randint(5, 9))).capitalize()

def _random_birthdate() -> str:
    start = datetime(1970,1,1)
    end = datetime(1999,12,31)
    d = start + timedelta(days=random.randrange((end - start).days + 1))
    return d.strftime('%Y-%m-%d')

def _b64url_no_pad(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")

def _sha256_b64url_no_pad(s: str) -> str:
    return _b64url_no_pad(hashlib.sha256(s.encode("ascii")).digest())

def _random_state(nbytes: int = 16) -> str:
    return secrets.token_urlsafe(nbytes)

def _pkce_verifier() -> str:
    return secrets.token_urlsafe(64)

def _parse_callback_url(callback_url: str) -> Dict[str, Any]:
    candidate = callback_url.strip()
    if not candidate:
        return {"code": "","state": "","error": "","error_description": ""}
    if "://" not in candidate:
        if candidate.startswith("?"): candidate = f"http://localhost{candidate}"
        elif any(ch in candidate for ch in "/?#") or ":" in candidate: candidate = f"http://{candidate}"
        elif "=" in candidate: candidate = f"http://localhost/?{candidate}"
    parsed = urllib.parse.urlparse(candidate)
    query = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
    fragment = urllib.parse.parse_qs(parsed.fragment, keep_blank_values=True)
    for key, values in fragment.items():
        if key not in query or not query[key] or not (query[key][0] or "").strip():
            query[key] = values
    def get1(k: str) -> str:
        v = query.get(k, [""])
        return (v[0] or "").strip()
    code = get1("code"); state = get1("state")
    error = get1("error"); error_description = get1("error_description")
    if code and not state and "#" in code:
        code, state = code.split("#",1)
    if not error and error_description:
        error, error_description = error_description, ""
    return {"code": code,"state": state,"error": error,"error_description": error_description}

def _jwt_claims_no_verify(id_token: str) -> Dict[str, Any]:
    if not id_token or id_token.count(".") < 2: return {}
    payload_b64 = id_token.split(".")[1]
    pad = "=" * ((4 - (len(payload_b64) % 4)) % 4)
    try:
        return json.loads(base64.urlsafe_b64decode((payload_b64 + pad).encode("ascii")).decode("utf-8"))
    except: return {}

def _decode_jwt_segment(seg: str) -> Dict[str, Any]:
    raw = (seg or "").strip()
    if not raw: return {}
    pad = "=" * ((4 - (len(raw) % 4)) % 4)
    try: return json.loads(base64.urlsafe_b64decode((raw + pad).encode("ascii")).decode("utf-8"))
    except: return {}

def _to_int(v: Any) -> int:
    try: return int(v)
    except: return 0

def _post_form(url: str, data: Dict[str, str], timeout: int = 30) -> Dict[str, Any]:
    body = urllib.parse.urlencode(data).encode("utf-8")
    req = urllib.request.Request(
        url, data=body, method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded","Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            if resp.status != 200: raise RuntimeError(f"token exchange failed: {resp.status}")
            return json.loads(raw.decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"token exchange failed: {exc.code}") from exc

@dataclass(frozen=True)
class OAuthStart:
    auth_url: str
    state: str
    code_verifier: str
    redirect_uri: str

def generate_oauth_url(
    *,
    redirect_uri: str = DEFAULT_REDIRECT_URI,
    scope: str = DEFAULT_SCOPE,
    login_hint: str = "",
    device_id: str = "",
    state: str = "",
) -> OAuthStart:
    """structure web flow authorize URL（Alignment camoufox Successful packet capture parameters）。

    A must-have for grabbing bags：device_id / ext-oai-did / auth_session_logging_id /
    ext-passkey-client-capabilities / screen_hint / login_hint。

    Notice：If you want to take chatgpt.com next-auth accessToken，state must come from
    next-auth POST /api/auth/signin/openai issued state（and
    __Secure-next-auth.state JWE cookie binding）。Self-made state will lead to
    callback hour OAuthCallback（state no match）。
    """
    state = (state or "").strip() or _random_state()
    code_verifier = _pkce_verifier()
    code_challenge = _sha256_b64url_no_pad(code_verifier)
    did = (device_id or "").strip() or str(uuid.uuid4())
    logging_id = str(uuid.uuid4())
    params = {
        "client_id": CLIENT_ID,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "scope": scope,
        "state": state,
        # Browser next-auth Path None PKCE；reserve PKCE Compatible only Codex /oauth/token Exchange tickets to save money
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "prompt": "login",
        "audience": "https://api.openai.com/v1",
        "screen_hint": "login_or_signup",
        "device_id": did,
        "ext-oai-did": did,
        "ext-passkey-client-capabilities": "01001",
        "auth_session_logging_id": logging_id,
    }
    if login_hint:
        params["login_hint"] = login_hint
    auth_url = f"{AUTH_URL}?{urllib.parse.urlencode(params)}"
    return OAuthStart(auth_url=auth_url, state=state, code_verifier=code_verifier, redirect_uri=redirect_uri)


def start_nextauth_openai_oauth(
    session,
    *,
    callback_url: str = "https://chatgpt.com/",
    login_hint: str = "",
    device_id: str = "",
) -> OAuthStart:
    """through next-auth initiate openai OAuth（curl_cffi No browser）。

    correct order（Consistent with browser）：
      1) GET chatgpt.com/auth/login  → kind __Host-next-auth.csrf-token
      2) GET /api/auth/csrf          → csrfToken
      3) POST /api/auth/signin/openai (csrfToken + callbackUrl + json=true)
         → 200 {"url": "https://auth.openai.com/api/accounts/authorize?...&state=..."}
         → Set-Cookie __Secure-next-auth.state=<JWE>（and state binding，Unforgeable）
      4) exist authorize URL Top up login_hint/screen_hint Wait for registration parameters（reserve next-auth state）

    Wrong approach：
      - Self-made state direct GET authorize → create_account of continue_url Unable to pass next-auth callback
      - After registration is complete, POST signin/openai → new state，old code void，And the session will be cleared and the /auth/login
      - GET continue_url no matching __Secure-next-auth.state → error=OAuthCallback
    """
    ua = _session_ua(session)
    impersonate = _session_impersonate(session)
    nav_headers = {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Upgrade-Insecure-Requests": "1",
        "user-agent": ua,
        "sec-fetch-dest": "document",
        "sec-fetch-mode": "navigate",
        "sec-fetch-site": "same-origin",
        **_make_trace_headers(),
    }
    try:
        session.get(
            "https://chatgpt.com/auth/login",
            timeout=20,
            headers={**nav_headers, "referer": "https://chatgpt.com/"},
            impersonate=impersonate,
        )
    except Exception as e:
        print(f"[~] /auth/login Abnormal preheating: {repr(e)[:100]}")

    csrf = ""
    try:
        csrf_resp = session.get(
            "https://chatgpt.com/api/auth/csrf",
            timeout=15,
            headers={
                "Accept": "application/json",
                "user-agent": ua,
                "referer": "https://chatgpt.com/auth/login",
                **_make_trace_headers(),
            },
            impersonate=impersonate,
        )
        if csrf_resp.status_code == 200:
            csrf = str((csrf_resp.json() or {}).get("csrfToken") or "").strip()
        print(f"[debug] next-auth csrf status={csrf_resp.status_code} token={'set' if csrf else 'null'}")
    except Exception as e:
        print(f"[!] next-auth csrf abnormal: {repr(e)[:120]}")
        raise RuntimeError("next-auth csrf failed") from e
    if not csrf:
        raise RuntimeError("next-auth csrfToken empty")

    # json=true → 200 + {"url": authorize...}，and write __Secure-next-auth.state JWE
    body = urllib.parse.urlencode(
        {
            "csrfToken": csrf,
            "callbackUrl": callback_url,
            "json": "true",
        }
    )
    try:
        signin_resp = session.post(
            "https://chatgpt.com/api/auth/signin/openai",
            timeout=30,
            allow_redirects=False,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/x-www-form-urlencoded",
                "Origin": "https://chatgpt.com",
                "Referer": "https://chatgpt.com/auth/login",
                "user-agent": ua,
                "sec-fetch-dest": "empty",
                "sec-fetch-mode": "cors",
                "sec-fetch-site": "same-origin",
                **_make_trace_headers(),
            },
            data=body,
            impersonate=impersonate,
        )
    except Exception as e:
        print(f"[!] POST signin/openai abnormal: {repr(e)[:120]}")
        raise RuntimeError("next-auth signin failed") from e

    auth_url = ""
    if signin_resp.status_code in (301, 302, 303, 307, 308):
        auth_url = (signin_resp.headers.get("Location") or signin_resp.headers.get("location") or "").strip()
    else:
        try:
            auth_url = str((signin_resp.json() or {}).get("url") or "").strip()
        except Exception:
            auth_url = ""
        if not auth_url:
            auth_url = (signin_resp.headers.get("Location") or signin_resp.headers.get("location") or "").strip()

    cookie_names = _session_cookie_names(session)
    has_state_cookie = any(n == "__Secure-next-auth.state" for n in cookie_names)
    print(
        f"[debug] POST signin/openai status={signin_resp.status_code} "
        f"url={'set' if auth_url else 'null'} state_cookie={has_state_cookie}"
    )
    if not auth_url or "authorize" not in auth_url:
        raise RuntimeError(
            f"next-auth signin did not return authorize url: "
            f"status={signin_resp.status_code} body={str(signin_resp.text)[:200]}"
        )
    if not has_state_cookie:
        print("[Warn] not seen __Secure-next-auth.state cookie — callback Very likely OAuthCallback")

    # reserve next-auth issued state/client_id/redirect_uri，For supplementary registration query
    parsed = urllib.parse.urlparse(auth_url)
    qs = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
    params = {k: (v[0] if v else "") for k, v in qs.items()}
    state = str(params.get("state") or "").strip()
    if not state:
        raise RuntimeError("next-auth authorize url missing state")

    did = (device_id or "").strip() or str(params.get("device_id") or "").strip() or str(uuid.uuid4())
    params["device_id"] = did
    params["ext-oai-did"] = did
    params.setdefault("prompt", "login")
    params.setdefault("screen_hint", "login_or_signup")
    params.setdefault("ext-passkey-client-capabilities", "01001")
    if "auth_session_logging_id" not in params:
        params["auth_session_logging_id"] = str(uuid.uuid4())
    if login_hint:
        params["login_hint"] = login_hint
    # next-auth Default None PKCE；Don't add it yourself code_challenge，Otherwise with server Inconsistent ticket exchange between terminals

    auth_url = f"{AUTH_URL}?{urllib.parse.urlencode(params)}"
    print(f"[debug] next-auth authorize state={state[:16]}... did={did[:8]}... hint={bool(login_hint)}")
    return OAuthStart(
        auth_url=auth_url,
        state=state,
        code_verifier="",  # next-auth server-side token exchange，none PKCE
        redirect_uri=str(params.get("redirect_uri") or DEFAULT_REDIRECT_URI),
    )


def _extract_cookie_value(session, name: str) -> str:
    """from Session CookieJar Get specified cookie value（compatible curl_cffi / requests）。"""
    try:
        for c in session.cookies:
            if getattr(c, "name", None) == name:
                return str(getattr(c, "value", "") or "")
    except Exception:
        pass
    try:
        return str(session.cookies.get(name) or "")
    except Exception:
        return ""


def finish_nextauth_access_token(session, continue_url: str) -> tuple[str, str]:
    """use create_account returned continue_url Finish next-auth callback，read accessToken。

    return (access_token, session_token)：
      - access_token: chatgpt.com/api/auth/session returned accessToken
      - session_token: __Secure-next-auth.session-token cookie（AT Replace it with a new one after it expires AT）
    continue_url shaped like:
      https://chatgpt.com/api/auth/callback/openai?code=...&state=...
    Require Session There are already matching __Secure-next-auth.state（signin issued nowadays JWE）。
    """
    cu = (continue_url or "").strip()
    if not cu or "code=" not in cu:
        print("[!] finish_nextauth: continue_url none code")
        return "", ""

    names = _session_cookie_names(session)
    has_state = any(n == "__Secure-next-auth.state" for n in names)
    print(f"[debug] callback forward next-auth cookies: state={has_state} "
          f"csrf={any('csrf' in n for n in names)} "
          f"names={[n for n in names if 'next-auth' in n]}")

    ua = _session_ua(session)
    impersonate = _session_impersonate(session)
    nav_headers = {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Upgrade-Insecure-Requests": "1",
        "user-agent": ua,
        "referer": "https://auth.openai.com/",
        "sec-fetch-dest": "document",
        "sec-fetch-mode": "navigate",
        "sec-fetch-site": "cross-site",
        **_make_trace_headers(),
    }

    # Follow redirects step by step，Easy to diagnose OAuthCallback / fall login
    current = cu
    final_url = cu
    try:
        for hop in range(8):
            resp = session.get(
                current,
                timeout=30,
                allow_redirects=False,
                headers=nav_headers if hop == 0 else {
                    **nav_headers,
                    "referer": current if hop else "https://auth.openai.com/",
                    "sec-fetch-site": "same-origin" if "chatgpt.com" in current else "cross-site",
                },
                impersonate=impersonate,
            )
            loc = (resp.headers.get("Location") or resp.headers.get("location") or "").strip()
            print(f"[debug] callback hop[{hop}] status={resp.status_code} "
                  f"url={current[:90]} loc={loc[:100]}")
            final_url = str(getattr(resp, "url", None) or current)
            if resp.status_code not in (301, 302, 303, 307, 308) or not loc:
                final_url = str(getattr(resp, "url", None) or current)
                # Non-redirect endpoint
                if resp.status_code >= 400:
                    print(f"[!] callback end HTTP {resp.status_code} body={resp.text[:200]}")
                break
            next_url = urllib.parse.urljoin(current, loc)
            if "error=" in next_url or "/auth/error" in next_url:
                print(f"[!] next-auth callback fail: {next_url[:160]}")
                return "", ""
            current = next_url
            final_url = next_url
        else:
            print("[Warn] callback Redirects over 8 Jump")
    except Exception as e:
        print(f"[!] GET continue_url/callback abnormal: {repr(e)[:140]}")
        return "", ""

    print(f"[debug] callback Finish final={final_url[:100]}")

    try:
        sess_resp = session.get(
            "https://chatgpt.com/api/auth/session",
            timeout=20,
            headers={
                "Accept": "application/json",
                "user-agent": ua,
                "referer": "https://chatgpt.com/",
                **_make_trace_headers(),
            },
            impersonate=impersonate,
        )
        if sess_resp.status_code != 200:
            print(f"[!] /api/auth/session status={sess_resp.status_code} body={sess_resp.text[:300]}")
            return "", ""
        sess_json = sess_resp.json() or {}
        access_token = str(sess_json.get("accessToken") or "").strip()
        uemail = str(((sess_json.get("user") or {}).get("email")) or "")
        session_token = _extract_cookie_value(session, "__Secure-next-auth.session-token")
        print(
            f"[debug] /api/auth/session accessToken={'set' if access_token else 'EMPTY'} "
            f"session_token={'set' if session_token else 'EMPTY'} "
            f"user={uemail[:60]} keys={list(sess_json.keys())[:8]}"
        )
        return access_token, session_token
    except Exception as e:
        print(f"[!] /api/auth/session abnormal: {repr(e)[:120]}")
        return "", ""


def _session_cookie_names(session) -> list:
    """List current Session cookie name（compatible curl_cffi CookieJar）。"""
    names = []
    try:
        for c in session.cookies:
            n = getattr(c, "name", None)
            if n:
                names.append(n)
    except Exception:
        pass
    if not names:
        try:
            # RequestsCookieJar / dict-like
            names = list(session.cookies.keys())  # type: ignore[arg-type]
        except Exception:
            pass
    return names


def _auth_session_flags(session) -> Dict[str, bool]:
    """Compare and capture packets：create_account Key things to have before cookie。"""
    names = _session_cookie_names(session)
    return {
        "oai_did": any(n == "oai-did" for n in names),
        "oai_login_csrf": any(n.startswith("oai-login-csrf") for n in names),
        "login_session": "login_session" in names,
        "oai_client_auth_session": "oai-client-auth-session" in names,
        "auth_provider": "auth_provider" in names,
        "hydra_redirect": "hydra_redirect" in names,
        "cf_clearance": "cf_clearance" in names,
    }

def fetch_sentinel_token(*, flow: str, did: str, proxies: Any = None) -> Optional[str]:
    """Get OpenAI Sentinel envelope（OpenAI-Sentinel-Token use）。

    Correction：must return JSON envelope {"p":..,"t":..,"c":<token>,"id":<did>,"flow":..}，
    Can't be naked token string。Direct reuse sentinel_sdk of pure Python Constructor。
    """
    try:
        return sentinel_sdk.build_sentinel_token(did, flow, proxies)
    except Exception:
        return None

def submit_callback_url(*, callback_url: str, expected_state: str, code_verifier: str, redirect_uri: str = DEFAULT_REDIRECT_URI) -> str:
    """Extract the redirect Code and in exchange for the final Access / Refresh Token"""
    cb = _parse_callback_url(callback_url)
    if cb["error"]: raise RuntimeError(f"oauth error: {cb['error']}")
    if not cb["code"] or not cb["state"]: raise ValueError("callback missing code/state")
    if cb["state"] != expected_state: raise ValueError("state mismatch")

    token_resp = _post_form(TOKEN_URL, {
        "grant_type": "authorization_code", "client_id": CLIENT_ID,
        "code": cb["code"], "redirect_uri": redirect_uri, "code_verifier": code_verifier,
    })
    
    access_token = (token_resp.get("access_token") or "").strip()
    refresh_token = (token_resp.get("refresh_token") or "").strip()
    id_token = (token_resp.get("id_token") or "").strip()
    expires_in = _to_int(token_resp.get("expires_in"))

    claims = _jwt_claims_no_verify(id_token)
    email = str(claims.get("email") or "").strip()
    auth_claims = claims.get("https://api.openai.com/auth") or {}
    account_id = str(auth_claims.get("chatgpt_account_id") or "").strip()

    now = int(time.time())
    expired_rfc3339 = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now + max(expires_in, 0)))
    now_rfc3339 = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now))

    config = {
        "id_token": id_token, "access_token": access_token, "refresh_token": refresh_token,
        "account_id": account_id, "last_refresh": now_rfc3339, "email": email,
        "type": "codex", "expired": expired_rfc3339,
    }
    return json.dumps(config, ensure_ascii=False, separators=(",", ":"))


# ========== 3. Core registration and extraction process ==========

def _log_sdk(flow: str, meta) -> None:
    """Record according to specifications Sentinel SDK result：Just remember the length/Version/so Whether to generate，Never print token plain text。"""
    if not isinstance(meta, dict):
        print(f"[Sentinel:{flow}] No valid results returned")
        return
    print(f"[Sentinel:{flow}] mode={meta.get('mode')} "
          f"sentinel_len={meta.get('sentinel_len')} "
          f"so_len={meta.get('so_len')} "
          f"sdk_version={meta.get('sdk_version')} "
          f"so_present={meta.get('so_present')} "
          f"t_ok={meta.get('t_ok')} so_ok={meta.get('so_ok')} "
          f"observer_wait_ms={meta.get('observer_wait_ms')} "
          f"ok={meta.get('ok')}")
    if meta.get("error"):
        print(f"[Sentinel:{flow}] Remark: {meta.get('error')}")


# Module level caching：Available proxies automatically detected are only detected once.，Avoid re-exploring the main loop every round。
_probed_proxy: Optional[str] = None


def _resend_email_otp(s, did, ua, impersonate) -> bool:
    """call OpenAI resend OTP：GET /api/accounts/email-otp/send（with password flow/Resend Button origin）。

    page email-verification of「Resend email」Now open this interface；302/200 are deemed to be triggered successfully。
    """
    headers = {
        "referer": "https://auth.openai.com/email-verification",
        "origin": "https://auth.openai.com",
        "accept": "application/json",
        "oai-device-id": did,
        "user-agent": ua,
        **_make_trace_headers(),
    }
    try:
        r = s.get(
            "https://auth.openai.com/api/accounts/email-otp/send",
            headers=headers,
            timeout=15,
            impersonate=impersonate,
            allow_redirects=False,
        )
        ok = r.status_code in (200, 302, 303, 307, 308)
        print(f"[*] resend OTP email-otp/send status={r.status_code} ok={ok}")
        return ok
    except Exception as e:
        print(f"[!] resend OTP abnormal: {repr(e)[:160]}")
        return False


def _wait_otp_imap_two_phase(code_fetcher, s, did, ua, impersonate, cancel_check=None, *,
                             phase1_sec=None, phase2_sec=None, allow_resend=True,
                             otp_issued_at=None):
    """IMAP OTP two stages：phase1 wait → (Optional resend) → phase2 Wait some more → Still no rules None。

    phase1_sec/phase2_sec default IMAP_OTP_PHASE_SEC（password path 10s Maintain status quo in two stages）。
    web Path consists of run() incoming IMAP_OTP_WEB_PHASE_SEC / IMAP_OTP_WEB_PHASE2_SEC。
    not_before：phase1 use otp_issued_at（or now）；resend after success phase2 use resend_at，
    avoid phase2 mentioned OTP1 → validate invalid_state。
    seen_ids Reuse across stages。mail.tm The path does not follow this function。
    """
    phase1 = IMAP_OTP_PHASE_SEC if phase1_sec is None else int(phase1_sec)
    phase2 = IMAP_OTP_PHASE_SEC if phase2_sec is None else int(phase2_sec)
    seen_ids = set()
    not_before = float(otp_issued_at) if otp_issued_at is not None else time.time()
    print(f"[*] OTP Two stage waiting：{phase1}s → resend={allow_resend} → {phase2}s "
          f"（not_before={not_before:.0f}）")

    code = code_fetcher(timeout_sec=phase1, seen_ids=seen_ids, not_before=not_before)
    if code:
        return code
    if cancel_check and cancel_check():
        return None

    if not allow_resend:
        print(f"[!] No.1stage {phase1}s Not received OTP，allow_resend=False，Abandon this email")
        return None

    print(f"[*] No.1stage {phase1}s Not received OTP，trigger resend...")
    resend_ok = _resend_email_otp(s, did, ua, impersonate)
    # resend moment of success：phase2 Only accept OTP2，Block the old one that comes first OTP1
    resend_at = time.time() if resend_ok else not_before
    if cancel_check and cancel_check():
        return None

    code = code_fetcher(timeout_sec=phase2, seen_ids=seen_ids, not_before=resend_at)
    if code:
        return code
    print(f"[!] No.2stage {phase2}s Still not received OTP，Abandon this email")
    return None


def login_with_password(proxy, email, password, cancel_check=None, code_fetcher=None) -> Optional[tuple]:
    """Use email+password go next-auth Log in，Recapture existing accounts session_token。

    Completely reusable run() conversation/Fingerprint infrastructure（fp + oai-did + 711 + CF warm-up +
    next-auth state JWE），Register the「create-account + OTP」Change password to log in：
      authorize(login_hint=email) → login_password Page → sentinel(password_verify)
      → POST /api/accounts/password/verify → callback → GET /api/auth/session

    return (email, access_token, session_token) or None。
    Log in if you require email OTP（email-verification），return None And in stdout Give reasons。
    """
    _set_cancel_check(cancel_check)
    email = (email or "").strip()
    password = (password or "").strip()
    if not email or not password:
        print("[!] login_with_password: Lack email/password")
        return None

    if proxy and proxy_711.is_711_proxy(proxy):
        proxy = proxy_711.ensure_proxy(proxy)
    proxies = {"http": proxy, "https": proxy} if proxy else None

    fp = choose_fp(seed=email)
    ua = fp["ua"]
    impersonate = fp["impersonate"]
    chrome_fp = fp["chrome_fp"]
    did = _new_oai_did()
    print(f"[login] fingerprint {_fp_summary(fp)} new equipment oai-did={did[:8]}...")

    s = requests.Session(proxies=proxies, impersonate=impersonate)
    s.headers.clear()
    s.headers.update(chrome_fp)
    _bind_session_fp(s, fp)
    _bind_oai_did(s, did)

    try:
        # Step zero：chatgpt.com take Cloudflare cookies（same run()）
        try:
            s.get("https://chatgpt.com/", timeout=20, headers={
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": chrome_fp.get("accept-language", "en-US,en;q=0.9"),
                "Upgrade-Insecure-Requests": "1",
                "user-agent": ua, **_make_trace_headers(),
            }, impersonate=impersonate)
            print("[login] Visited chatgpt.com Get CF cookies")
        except Exception as e:
            print(f"[login] chatgpt.com Access exception（continue）: {repr(e)[:100]}")
        _bind_oai_did(s, did)
        _human_delay(0.8, 2.2, "after chatgpt.com warm-up")

        # first step：next-auth initiate OAuth（state binding __Secure-next-auth.state JWE）
        oauth_headers = {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": chrome_fp.get("accept-language", "en-US,en;q=0.9"),
            "Upgrade-Insecure-Requests": "1",
            "user-agent": ua,
            "referer": "https://chatgpt.com/",
            "sec-fetch-dest": "document",
            "sec-fetch-mode": "navigate",
            "sec-fetch-site": "cross-site",
            **_make_trace_headers(),
        }
        oauth = None
        for attempt in range(1, MAX_STAGE_RETRY + 1):
            if cancel_check and cancel_check():
                print("[login] Canceled（authorize forward）")
                return None
            try:
                oauth = start_nextauth_openai_oauth(
                    s, callback_url="https://chatgpt.com/", login_hint=email, device_id=did
                )
            except Exception as e:
                print(f"[login] next-auth signin fail ({repr(e)[:100]})，No. {attempt}/{MAX_STAGE_RETRY} Second-rate")
                if attempt < MAX_STAGE_RETRY:
                    _retry_backoff(attempt)
                    continue
                return None

            _human_delay(0.3, 1.2, f"before authorize attempt={attempt}")
            resp = s.get(oauth.auth_url, timeout=25, headers=oauth_headers, allow_redirects=True)
            _bind_oai_did(s, did)
            final_url = str(getattr(resp, "url", "") or "")
            print(f"[login] authorize status={resp.status_code} url={final_url[:110]} "
                  f"cookies={_auth_session_flags(s)}")

            # like authorize Jump directly to chatgpt.com callback（Very rare），End directly
            cb = _parse_callback_url(final_url)
            if cb["code"] and cb["state"]:
                return email, *finish_nextauth_access_token(s, final_url)

            # Session established（login_password Page/Email verification page/Or certified jump）You can enter the password step
            if final_url and ("log-in" in final_url or "login" in final_url
                              or "password" in final_url or "email-verification" in final_url):
                break
            if attempt < MAX_STAGE_RETRY:
                print(f"[login] authorize Not reached the login page（No. {attempt}/{MAX_STAGE_RETRY} Second-rate），Retry the same session")
                _retry_backoff(attempt)
        else:
            return None

        if cancel_check and cancel_check():
            print("[login] Canceled（login page back）")
            return None
        _human_delay(0.4, 1.5, "after authorize / before password verify")

        # OTP Priority path：authorize fall directly email-verification（OpenAI The default email code is sent when logging in to a new device.）
        if "email-verification" in final_url:
            otp_issued_at = time.time()
            _human_delay(0.3, 1.0, "before OTP wait")
            if not code_fetcher:
                print("[login] authorize fall email-verification（Email required OTP），"
                      "But no code_fetcher；only outlook Pool account support，give up")
                return None
            code = _wait_otp_imap_two_phase(
                code_fetcher, s, did, ua, impersonate, cancel_check=cancel_check,
                phase1_sec=LOGIN_OTP_PHASE1_SEC, phase2_sec=LOGIN_OTP_PHASE2_SEC,
                allow_resend=True, otp_issued_at=otp_issued_at,
            )
            if not code:
                print("[login] Mail OTP Timeout not received，Give up this account")
                return None
            print(f"[login] Mail OTP Received: {code}")
            validate_headers = {
                "referer": final_url or "https://auth.openai.com/email-verification",
                "origin": "https://auth.openai.com",
                "content-type": "application/json",
                "oai-device-id": did,
                "user-agent": ua,
                **_make_trace_headers(),
            }
            code_resp = s.post(
                "https://auth.openai.com/api/accounts/email-otp/validate",
                headers=validate_headers,
                data=json.dumps({"code": code}),
                impersonate=impersonate,
                allow_redirects=False,
                timeout=30,
            )
            print(f"[login] /api/accounts/email-otp/validate → {code_resp.status_code}")
            if code_resp.status_code not in (200, 302):
                print(f"[login] OTP Verification failed: {code_resp.status_code} body={code_resp.text[:300]}")
                return None
            if code_resp.status_code == 200:
                try:
                    vj = code_resp.json()
                except Exception:
                    vj = {}
                cont = str((vj or {}).get("continue_url") or "").strip()
                print(f"[login] OTP validate 200 continue_url={cont[:110]}")
            else:
                cont = (code_resp.headers.get("Location") or "").strip()
                print(f"[login] OTP validate 302 location={cont[:110]}")
            at, st = finish_nextauth_access_token(s, cont or final_url)
            if not at:
                print("[login] /api/auth/session Not returned accessToken，Login is not really implemented")
                return None
            print(f"[login] success accessToken={'have' if at else 'none'} "
                  f"session_token={'have' if st else 'none'} email={email}")
            return email, at, st

        # Password path：fall login/password The page just left password/verify

        # Step 2：sentinel(password_verify) Anti-bot，Again POST /api/accounts/password/verify
        pwd_headers = {
            "referer": final_url or "https://auth.openai.com/log-in/password",
            "origin": "https://auth.openai.com",
            "accept": "application/json",
            "content-type": "application/json",
            "oai-device-id": did,
            "user-agent": ua,
            **_make_trace_headers(),
        }
        try:
            from . import sentinel_sdk as _sdk_login
            _sl = _sdk_login.sentinel_for("password_verify", proxy=proxy, did=did, fp=fp)
            _sentinel_pwd = _sl.get("sentinel_token") if _sl.get("ok") else None
        except Exception as e:
            print(f"[login] sentinel(password_verify) abnormal: {repr(e)[:100]}")
            _sentinel_pwd = None
        if _sentinel_pwd:
            pwd_headers["openai-sentinel-token"] = _sentinel_pwd
            print("[login] sentinel(password_verify) has been issued")
        else:
            print("[Warn] [login] Didn't get it sentinel(password_verify)，Try to log in directly")

        pv = s.post(
            "https://auth.openai.com/api/accounts/password/verify",
            headers=pwd_headers,
            data=json.dumps({"password": password}),
            impersonate=impersonate,
            allow_redirects=False,
            timeout=30,
        )
        print(f"[login] /api/accounts/password/verify → {pv.status_code}")
        if pv.status_code != 200:
            print(f"[login] Password login failed: {pv.status_code} body={pv.text[:300]}")
            return None
        try:
            vj = pv.json()
        except Exception:
            vj = {}
        cont = str((vj or {}).get("continue_url") or "").strip()
        print(f"[login] password/verify 200 continue_url={cont[:110]}")

        if "email-verification" in (cont or final_url):
            print("[login] Email is required to log in to this account OTP（email-verification），There is currently no receiving channel，give up")
            return None

        # Step 3：GET /api/auth/session take accessToken + session_token（Internal follow-up callback redirection）
        at, st = finish_nextauth_access_token(s, cont or final_url)
        if not at:
            print("[login] /api/auth/session Not returned accessToken，Login is not really implemented")
            return None
        print(f"[login] success accessToken={'have' if at else 'none'} session_token={'have' if st else 'none'} email={email}")
        return email, at, st

    except Exception as e:
        print(f"[login] Unexpected exception，Give up this account: {repr(e)[:200]}")
        return None


# Customized email channel registration form: Caller registration setup_email(proxies, cancel_check) -> (email, openai_password, fetch_code)
# fetch_code(timeout_sec=None, seen_ids=None, not_before=None) -> code|None
CUSTOM_EMAIL_CHANNELS: Dict[str, Any] = {}


def register_email_channel(name: str, setup_fn) -> None:
    """Register for a custom email channel。name Right now run(email=name) And the value of the panel channel drop-down。"""
    name = str(name or "").strip().lower()
    if not name or not callable(setup_fn):
        raise ValueError("register_email_channel: need name + setup_fn")
    CUSTOM_EMAIL_CHANNELS[name] = setup_fn


def list_email_channels() -> list:
    """built-in + Custom channel name list（For panel pull-down）。"""
    return ["mailtm"] + sorted(CUSTOM_EMAIL_CHANNELS.keys())


def run(proxy: Optional[str], email: str = "mailtm", cancel_check=None, imap_label=None) -> Optional[tuple]:
    # return 5-tuple: (token_json, email, password, access_token, session_token)
    #   - web flow: token_json=None, access_token+session_token from chatgpt.com/api/auth/session
    #   - Codex flow: token_json=JSONstring(Contains refresh_token), access_token/session_token All are ""
    # Cancel signal access：register_loop incoming STATE.cancel.is_set；OTP Wait between loops and steps
    # sleep Respond in seconds based on this，The stop button can immediately interrupt the current registration。
    # TLS：When registering multiple accounts concurrently, they do not cover each other. cancel callback。
    _set_cancel_check(cancel_check)
    # If not explicitly given to the agent，Automatically select one from the proxy pool that can penetrate OpenAI Cloudflare of。
    # （current 1000 Tiaoduo is a data center IP，most 403；Use it if you find something alive，Can't detect
    #  but fallback arrive 711 residential chain relay——with test activity side _resolve_relay_proxy Alignment。）
    global _probed_proxy
    # When not explicitly given to the agent：Automatically build 711 residential relay（from OpenAI Support random selection of country whitelist region，
    # Every number sticky lock area，avoid unsupported_country 403）
    if not proxy:
            try:
                region = proxy_711.pick_region()
                proxy = proxy_711.build_711_proxy(region=region, sess_time=30)
                print(f"[*] 711 Relay locked country: {region}")
                print(f"[*] No proxy available in free pool，Automatically enabled 711 relay: {proxy.split('@')[-1] if proxy and '@' in proxy else proxy}")
            except Exception as e:
                print(f"[!] 711 Relay automatic activation failed: {e}")
    # 711 Directly connected to curl_cffi Will be blocked by the gateway next time CONNECT；Rewrite to native Clash chain relay。
    # Camoufox The browser path can continue to use the original 711 URL（System side Clash/TUN Covered）。
    # New for every number 711 sticky session（proxy_711.build_711_proxy Automatically new every time session id）。
    if proxy and proxy_711.is_711_proxy(proxy):
        proxy = proxy_711.ensure_proxy(proxy)
    proxies = {"http": proxy, "https": proxy} if proxy else None
    _email = None
    _ok = False
    code_fetcher = None  # Custom channel coder

    # Save mailbox mode：later mail_data will cover email The variable is the specific address
    email_mode = email
    print(f"[*] Initialization request，ready to use {email} Email registration...")
    if email == "mailtm":
        mail_data = setup_mail_tm(proxies=None, cancel_check=cancel_check)  # mail.tm direct connection，Not leaving 711 acting
    elif email in CUSTOM_EMAIL_CHANNELS:
        # caller (reg/engine) Registered custom email channel
        mail_data = CUSTOM_EMAIL_CHANNELS[email](proxies, cancel_check=cancel_check)
    else:
        print(f"[Error] Unknown email channel: {email!r}（built-in mailtm；See custom channels reg/engine.register_email_channel）")
        return None
    if not mail_data or not mail_data[0]:
        print(f"[Error] Get {email} Email failed")
        return None

    email, password, code_fetcher = mail_data
    _email = email
    if cancel_check and cancel_check():
        print("[*] Canceled（After getting the email），Suspend this registration")
        return None
    print(f"[*] Successfully obtained email address: {email}")
    if password:
        # right duck/163/dms path：password yes OpenAI Account password；
        # mail.tm The second return value of the path is also OpenAI password（mail.tm Save the receiving password）。
        print(f"[*] OpenAI Account password has been generated（len={len(password)}）")
    else:
        print("[!] Not generated OpenAI password，password process will fail")

    # §3.5 Operation list for each number：①new oai-did ②new fp profile ③new 711 session ④TLS impersonate Follow fp
    fp = choose_fp(seed=email)
    ua = fp["ua"]
    impersonate = fp["impersonate"]
    chrome_fp = fp["chrome_fp"]
    did = _new_oai_did()
    print(f"[anti-fuzz] Fingerprint of this number {_fp_summary(fp)}")
    print(f"[anti-fuzz] new equipment oai-did={did[:8]}...（This number is fixed throughout the journey，and fp Supporting）")

    s = requests.Session(proxies=proxies, impersonate=impersonate)
    s.headers.clear()
    s.headers.update(chrome_fp)
    _bind_session_fp(s, fp)
    _bind_oai_did(s, did)

    try:
        # Step zero：Visit first chatgpt.com take Cloudflare cookies（cf_clearance/__cf_bm wait）。
        # oai-did Forced to write；After responding, still use this number did Subject to（Anti-server Set-Cookie Associated devices）。
        try:
            s.get("https://chatgpt.com/", timeout=20, headers={
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": chrome_fp.get("accept-language", "en-US,en;q=0.9"),
                "Upgrade-Insecure-Requests": "1",
                "user-agent": ua, **_make_trace_headers(),
            }, impersonate=impersonate)
            print("[*] Visited chatgpt.com Get CF cookies")
        except Exception as e:
            print(f"[~] chatgpt.com Access exception（continue）: {repr(e)[:100]}")
        _bind_oai_did(s, did)
        _human_delay(0.8, 2.2, "after chatgpt.com warm-up")

        # first step：through next-auth initiate OAuth，Go ahead /api/accounts/authorize + login_hint
        # key：state must come from POST /api/auth/signin/openai（binding __Secure-next-auth.state JWE），
        # Self-made state will lead to create_account of continue_url exist callback hour OAuthCallback。
        # Browser path：csrf → POST signin/openai → authorize?...&state=<next-auth> → register → callback。
        oauth_headers = {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": chrome_fp.get("accept-language", "en-US,en;q=0.9"),
            "Upgrade-Insecure-Requests": "1",
            "user-agent": ua,
            "referer": "https://chatgpt.com/",
            "sec-fetch-dest": "document",
            "sec-fetch-mode": "navigate",
            "sec-fetch-site": "cross-site",
            **_make_trace_headers(),
        }
        auth_ok = False
        oauth = None
        final_url = ""
        for attempt in range(1, MAX_STAGE_RETRY + 1):
            if cancel_check and cancel_check():
                print("[*] Canceled（authorize forward），Suspend this registration")
                return None
            try:
                oauth = start_nextauth_openai_oauth(
                    s, callback_url="https://chatgpt.com/", login_hint=email, device_id=did
                )
            except Exception as e:
                print(f"[Warn] next-auth signin fail ({repr(e)[:100]})，No. {attempt}/{MAX_STAGE_RETRY} Second-rate；"
                      f"fallback self-made state（Only number can be issued，accessToken Most likely you won’t get it）")
                oauth = generate_oauth_url(login_hint=email, device_id=did)

            _human_delay(0.3, 1.2, f"before authorize attempt={attempt}")
            resp = s.get(oauth.auth_url, timeout=25, headers=oauth_headers, allow_redirects=True)
            # Keep this number did fixed，Do not use other methods that may be issued by the server. oai-did
            _bind_oai_did(s, did)
            flags = _auth_session_flags(s)
            final_url = str(getattr(resp, "url", "") or "")
            print(f"[*] authorize attempt={attempt} status={resp.status_code} "
                  f"url={final_url[:90]} cookies={flags}")
            # have oai-did +（csrf or login_session）Consider the session established
            if did and (flags.get("oai_login_csrf") or flags.get("login_session")
                        or flags.get("oai_client_auth_session")
                        or "email-verification" in final_url):
                auth_ok = True
                break
            reason = f"HTTP {resp.status_code}"
            err_code = ""
            try:
                err_json = resp.json()
                err_code = err_json.get("error", {}).get("code", "")
                err_msg = err_json.get("error", {}).get("message", "")
                if err_code == "unsupported_country_region_territory":
                    # exit IP Region not supported：Retry current number/Agents must fail，Give up immediately and change to the next email address
                    reason = "HTTP 403 - exit IP The area is not subject to OpenAI support，Please use supported regional agents such as the United States."
                    print(f"[Warn] authorize deterministic failure ({reason})，Give up this account")
                    return None
                elif err_code:
                    reason = f"HTTP {resp.status_code} - {err_code}: {err_msg}"
            except Exception:
                pass
            print(f"[Warn] authorize Session is not ready ({reason}, No. {attempt}/{MAX_STAGE_RETRY} Second-rate)")
            if attempt < MAX_STAGE_RETRY:
                # §3.2 exponential backoff + Jitter：base * 2^(n-1) + U(0,1)
                _retry_backoff(attempt, base=0.8)
                # Try again with the same account number fp / did（Do not change fingerprints mid-session）
                s = requests.Session(proxies=proxies, impersonate=impersonate)
                s.headers.clear()
                s.headers.update(chrome_fp)
                _bind_session_fp(s, fp)
                _bind_oai_did(s, did)
        if not did:
            print("[Error] failed to obtain OpenAI Device ID (oai-did) - See specific reasons above")
            return None
        if not auth_ok:
            # authorize Unsuccessful：Don't go in again OTP Waiting to death，Just give up your current account and let the outer layer change your email address.
            print("[Warn] authorize post key cookie Still incomplete，Give up this account "
                  f"(cookie_names={_session_cookie_names(s)[:20]})")
            return None

        # web flow：authorize when successful OTP1 Sent；Remember immediately issued available at all times IMAP not_before
        otp_issued_at = time.time()

        if cancel_check and cancel_check():
            print("[*] Canceled（authorize back），Suspend this registration")
            return None
        _human_delay(0.5, 1.8, "after authorize / before OTP path")

        # Password process detection（Subscribe node/data center IP Walk password Page，need user/register + email-otp/send）
        is_password_flow = "create-account/password" in final_url
        if is_password_flow:
            print("[*] authorize fall create-account/password，Follow the password process（user/register + email-otp/send）")
            try:
                from . import sentinel_sdk as _sdk2
                _su = _sdk2.sentinel_for("username_password_create", proxy, did=did, fp=fp)
                _sentinel_user = _su.get("sentinel_token") if _su.get("ok") else None
            except Exception:
                _sentinel_user = None
            _pwd_headers = {
                "referer": "https://auth.openai.com/create-account/password",
                "origin": "https://auth.openai.com",
                "accept": "application/json",
                "content-type": "application/json",
                "oai-device-id": did,
                "user-agent": ua,
                **_make_trace_headers(),
            }
            if _sentinel_user:
                _pwd_headers["openai-sentinel-token"] = _sentinel_user
            _pwd_resp = s.post("https://auth.openai.com/api/accounts/user/register",
                               headers=_pwd_headers,
                               data=json.dumps({"password": password, "username": email}),
                               impersonate=impersonate)
            print(f"[debug] user/register status={_pwd_resp.status_code} body={_pwd_resp.text[:300]}")
            if _pwd_resp.status_code != 200:
                print("[Error] user/register fail")
                return None
            s.get("https://auth.openai.com/api/accounts/email-otp/send", headers=_pwd_headers, timeout=15, impersonate=impersonate)
            print("[*] Password process user/register success，Triggered email-otp/send")
            # password flow：OTP exist email-otp/send issued later
            otp_issued_at = time.time()
        else:
            # web flow：authorize bring login_hint Sent automatically OTP，No password step、none authorize/continue
            print(f"[*] web flow：authorize Finish did={did[:8]}... OTP should have been sent（No password step）")

        # wait OTP（mail.tm API Direct reading / 163 IMAP / duck Forward / icloud HME）
        # duck/163：two stages IMAP；password Keep 10s×2，web use longer phase cover DDG Delay。
        # icloud：Reuse web The duration of the two stages，allow_resend=False（HME forward pair resend Support unknown，Avoid getting the wrong code）。
        # mail.tm / dms：Keep the original code_fetcher() Logic remains unchanged。
        if email_mode in ("duck", "163"):
            if is_password_flow:
                code = _wait_otp_imap_two_phase(
                    code_fetcher, s, did, ua, impersonate, cancel_check=cancel_check,
                    phase1_sec=IMAP_OTP_PHASE_SEC, phase2_sec=IMAP_OTP_PHASE_SEC,
                    allow_resend=True, otp_issued_at=otp_issued_at,
                )
            else:
                code = _wait_otp_imap_two_phase(
                    code_fetcher, s, did, ua, impersonate, cancel_check=cancel_check,
                    phase1_sec=IMAP_OTP_WEB_PHASE_SEC, phase2_sec=IMAP_OTP_WEB_PHASE2_SEC,
                    allow_resend=True, otp_issued_at=otp_issued_at,
                )
        elif email_mode == "icloud":
            code = _wait_otp_imap_two_phase(
                code_fetcher, s, did, ua, impersonate, cancel_check=cancel_check,
                phase1_sec=IMAP_OTP_ICLOUD_PHASE_SEC, phase2_sec=IMAP_OTP_WEB_PHASE2_SEC,
                allow_resend=False, otp_issued_at=otp_issued_at,
            )
        else:
            code = code_fetcher()
        if cancel_check and cancel_check():
            print("[*] Canceled（wait OTP period），Suspend this registration")
            return None
        if not code:
            print("[Error] Verification code waiting timed out or extraction failed")
            return None
        print(f"[*] Successfully extracted verification code: {code}")
        _human_delay(0.4, 1.5, "before email-otp/validate")

        # Step 7：Verify verification code → The server advances to about_you
        validate_headers = {
            "referer": "https://auth.openai.com/email-verification",
            "origin": "https://auth.openai.com",
            "content-type": "application/json",
            "oai-device-id": did,
            **_make_trace_headers(),
        }
        code_resp = s.post(
            "https://auth.openai.com/api/accounts/email-otp/validate",
            headers=validate_headers,
            data=json.dumps({"code": code}),
            impersonate=impersonate,
        )
        if code_resp.status_code != 200:
            print(f"[Error] Verification code verification failed: {code_resp.status_code} | used_code={code} | body={code_resp.text[:600]}")
            return None

        # Capture packets：validate 200 return continue_url=about-you + page.type=about_you，
        # The browser will GET about-you Again POST create_account。Follow me even if you don’t have a browser，
        # Avoid the server still being stuck email_verification → create_account invalid_auth_step。
        about_url = "https://auth.openai.com/about-you"
        try:
            vj = code_resp.json() if code_resp.text else {}
            page_type = str(((vj or {}).get("page") or {}).get("type") or "")
            cont = str((vj or {}).get("continue_url") or "").strip()
            # Registered email before proceeding OTP check，OpenAI No reply about_you，
            # Rather page=external_url + continue_url=chatgpt.com Login callback。
            # If you blindly believe at this time cont go GET，Will directly log in to the old account and cause pollution cookie，
            # subsequently create_account must 400 invalid_auth_step。
            # recognize this status → Give up this time，Let the outer batch loop change the alias and try again（Custom channels have been deduplicated）。
            if page_type == "external_url" or "chatgpt.com/api/auth/callback" in cont:
                # Registered email OTP Verification returns login callback = Account already exists。
                # do not give up，Go directly next-auth callback catch up accessToken/sessionToken
                # (Existing account login link, Supply, supplement and import token Library)。
                _login_at, _login_st = None, None
                try:
                    if cont and "code=" in cont:
                        _login_at, _login_st = finish_nextauth_access_token(s, cont)
                except Exception as _le:
                    print(f"[~] Stock login callback abnormal: {repr(_le)[:150]}")
                if _login_at:
                    print(f"[+] Login to existing account successfully: at_len={len(_login_at)} "
                          f"st={'set' if _login_st else 'NONE'}")
                    _ok = True
                    return None, email, password, _login_at, _login_st or ""
                print(f"[!] Email is registered（OTP validate return external_url Login callback）→ "
                      f"Give up this time，Change alias/Change number and try again")
                print(f"[!] page={page_type or '?'} continue={cont[:100]}")
                # Custom channels：Tag is registered（If so mark_already_registered hook）
                if code_fetcher is not None:
                    try:
                        _mark = getattr(code_fetcher, "mark_already_registered", None)
                        if callable(_mark):
                            _mark("already_registered_openai")
                        _lfr = getattr(code_fetcher, "last_fail_reason", None)
                        if isinstance(_lfr, dict):
                            _lfr["reason"] = "already_registered"
                    except Exception:
                        pass
                return None
            if cont:
                about_url = cont
            print(f"[*] OTP OK page={page_type or '?'} continue={about_url[:100]}")
        except Exception as e:
            print(f"[~] parse validate body fail（continue GET about-you）: {e}")
        try:
            s.get(about_url, timeout=20, headers={
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": chrome_fp.get("accept-language", "en-US,en;q=0.9"),
                "Upgrade-Insecure-Requests": "1",
                "user-agent": ua,
                "referer": "https://auth.openai.com/email-verification",
                "sec-fetch-dest": "document",
                "sec-fetch-mode": "navigate",
                "sec-fetch-site": "same-origin",
                **_make_trace_headers(),
            }, impersonate=impersonate)
            print(f"[*] already GET about-you Advance conversation cookies={_auth_session_flags(s)}")
        except Exception as e:
            print(f"[~] GET about-you abnormal（continue create_account）: {repr(e)[:120]}")

        # Before step eight：reality Chrome generate create_account of Sentinel/SO（hybrid architecture）
        # default OPENAI_SENTINEL_MODE=browser → sentinel_browser.generate_tokens
        # Node fake DOM although t_ok=so_ok=True，but t/so Untrue solution，The server does not recognize it。
        sentinel_acct, so_token = None, None
        sdk_acct = None
        try:
            # default pure（sentinel_pure_vm pure Python t/so，none Chrome）；Can be overridden by environment variables
            os.environ.setdefault("OPENAI_SENTINEL_MODE", "pure")
            # Matching alignment：sentinel VM of screen/webgl/platform/languages and HTTP Same set of heads fp
            sdk_acct = sentinel_sdk.sentinel_for(
                "oauth_create_account", proxy, did=did, fp=fp
            )
            _log_sdk("oauth_create_account", sdk_acct)
            if sdk_acct and sdk_acct.get("ok"):
                sentinel_acct = sdk_acct.get("sentinel_token")
                so_token = sdk_acct.get("so_token")
            else:
                print(f"[!] oauth_create_account SDK Not ready: "
                      f"{(sdk_acct or {}).get('error') or 'unknown'}")
        except Exception as e:
            print(f"[!] create_account of Sentinel Construction failed：{e}")
        print(f"[*] sentinel(acct)={'set' if sentinel_acct else 'NONE'} "
              f"len={len(sentinel_acct) if sentinel_acct else 0} "
              f"so_token={'set' if so_token else 'NONE'} "
              f"so_len={len(so_token) if so_token else 0} "
              f"mode={(sdk_acct or {}).get('mode')}")
        if not sentinel_acct or not so_token:
            print("[Error] create_account lack of truth t/so（pure-vm/browser/node All failed），"
                  "Please confirm Playwright+system Chrome Available（OPENAI_SENTINEL_MODE=browser）")
            return None

        # Step 8：Complete account registration（Align captured packets header + cookie session）
        flags = _auth_session_flags(s)
        print(f"[debug] pre-create_account cookies={flags} "
              f"names={[n for n in _session_cookie_names(s) if 'oai' in n or 'session' in n or 'csrf' in n or 'auth' in n]}")
        if not flags.get("oai_login_csrf") and not flags.get("login_session"):
            print("[Warn] Lack oai-login-csrf_* / login_session — high probability invalid_auth_step")

        create_headers = {
            "accept": "application/json",
            "referer": "https://auth.openai.com/about-you",
            "origin": "https://auth.openai.com",
            "content-type": "application/json",
            "oai-device-id": did,
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-origin",
            **_make_trace_headers(),
        }
        create_headers["openai-sentinel-token"] = sentinel_acct
        create_headers["openai-sentinel-so-token"] = so_token
        create_data = {"name": _random_name(), "birthdate": _random_birthdate()}
        # Capture packets web flow create_account body only name+birthdate，Without cf_turnstile_response
        if cancel_check and cancel_check():
            print("[*] Canceled（create_account forward），Suspend this registration")
            return None
        _human_delay(0.6, 2.0, "before create_account (fill profile)")
        create_resp = s.post(
            "https://auth.openai.com/api/accounts/create_account",
            headers=create_headers,
            data=json.dumps(create_data),
            impersonate=impersonate,
        )
        print(f"[debug] create_account status={create_resp.status_code} body={create_resp.text[:500]}")
        if create_resp.status_code != 200:
            try:
                _e = create_resp.json().get("error", {})
                _code = _e.get("code")
                print(f"[Error] Failed to fill in account information: {create_resp.status_code} | "
                      f"code={_code} msg={_e.get('message')}")
                if _code == "invalid_auth_step":
                    print("[Hint] invalid_auth_step = Session is not in about_you step（examine authorize endpoint/cookie），"
                          "no registration_disallowed（The latter is t/so/Risk control）")
                elif _code == "registration_disallowed":
                    print("[Hint] registration_disallowed = sentinel t/so or equipment/IP/Email risk control；"
                          "confirm mode=browser and t/so from reality Chrome")
                elif _code == "user_already_exists":
                    print("[Hint] user_already_exists = This email address has already been registered（DDG Duplicate alias），"
                          "burn After aliasing, the outer layer changes the number and tries again.")
            except Exception:
                print(f"[Error] Failed to fill in account information: {create_resp.status_code} | "
                      f"body={create_resp.text[:600]}")
            return None

        # web flow：create_account 200 of continue_url Directly contain next-auth callback code+state。
        # this code The ____ does not work /oauth/token Change Codex token（meeting 401）。
        # Correct ending（Never again POST signin/openai — It will be replaced with a new one state fall side by side /auth/login）：
        #   1) GET continue_url（callback/openai?code=&state=）— Need to match __Secure-next-auth.state
        #   2) GET /api/auth/session → {accessToken, user, expires}
        try:
            _cj = create_resp.json()
            _cu = str(_cj.get("continue_url") or "").strip()
        except Exception:
            _cu = ""
        if _cu and "code=" in _cu:
            print("[debug] web flow create_account 200，GET continue_url Finish next-auth callback Pick accessToken")
            # check continue_url of state and signin saved at the time state consistent
            try:
                _cb = _parse_callback_url(_cu)
                if oauth and oauth.state and _cb.get("state") and _cb["state"] != oauth.state:
                    print(f"[Warn] continue_url state and next-auth state inconsistent "
                          f"cu={_cb['state'][:16]} oauth={oauth.state[:16]}")
                else:
                    print(f"[debug] continue_url state Alignment next-auth "
                          f"state={(_cb.get('state') or '')[:16]}...")
            except Exception:
                pass
            _access_token, _session_token = finish_nextauth_access_token(s, _cu)
            _ok = True
            # web flow nothing Codex token（next-auth code Depend on chatgpt.com Server-side ticket exchange），
            # accessToken from chatgpt.com/api/auth/session
            return None, email, password, _access_token, _session_token

        # Step 9：Select workspace Workspace（Codex OAuth Streaming is needed）
        auth_cookie = s.cookies.get("oai-client-auth-session")
        print(f"[debug] auth_cookie={bool(auth_cookie)} cookie_names={list(s.cookies.keys())}")
        if not auth_cookie:
            print("[debug] none auth_cookie，create_account Maybe the account was not actually created or the process has changed.")
            return None
        auth_json = _decode_jwt_segment(auth_cookie.split(".")[0])
        workspace_id = str((auth_json.get("workspaces") or [{}])[0].get("id") or "").strip()
        
        select_resp = s.post("https://auth.openai.com/api/accounts/workspace/select", headers={"referer": "https://auth.openai.com/sign-in-with-chatgpt/codex/consent", "origin": "https://auth.openai.com", "content-type": "application/json", "oai-device-id": did, "user-agent": ua, **_make_trace_headers()}, data=json.dumps({"workspace_id": workspace_id}), impersonate=impersonate)
        print(f"[debug] workspace/select status={select_resp.status_code} body={select_resp.text[:300]}")
        if select_resp.status_code != 200: return None
        
        continue_url = str((select_resp.json() or {}).get("continue_url") or "").strip()

        # Step 10：intercept redirect，extract ultimate Token
        current_url = continue_url
        for _ in range(6):
            final_resp = s.get(current_url, allow_redirects=False, timeout=15)
            location = final_resp.headers.get("Location") or ""
            print(f"[debug] redirect[{_}] status={final_resp.status_code} url={current_url[:80]} loc={location[:120]}")
            if final_resp.status_code not in [301, 302, 303, 307, 308] or not location:
                break
            next_url = urllib.parse.urljoin(current_url, location)
            if "code=" in next_url and "state=" in next_url:
                token_json = submit_callback_url(callback_url=next_url, code_verifier=oauth.code_verifier, redirect_uri=oauth.redirect_uri, expected_state=oauth.state)
                _ok = True
                # Codex OAuth flow（/oauth/token Ticket exchange successful），none next-auth accessToken
                return token_json, email, password, "", ""
            current_url = next_url

        print("[Error] Failed to catch final in redirect chain Token")
        return None

    except Exception as _e:
        print(f"[reveal all the details] Unexpected exception，Give up this account: {repr(_e)[:200]}")
        return None
    finally:
        _set_cancel_check(None)
        if _email:
            try:
                _reason = None
                if not _ok and code_fetcher is not None:
                    _lfr = getattr(code_fetcher, "last_fail_reason", None)
                    if isinstance(_lfr, dict):
                        _reason = (_lfr.get("reason") or "").strip() or None
                if not _ok and not _reason:
                    _reason = "other_fail"
                provider_stats.record(_email, _ok, reason=_reason)
            except Exception:
                pass
            try:
                print("[statistics] Email domain name success rate:\n" + provider_stats.summary())
            except Exception:
                pass


# ========== 4. Main program polling and saving ==========

def main():
    _force_utf8_stdio()
    parser = argparse.ArgumentParser(description="OpenAI Perfect integration of automated registration scripts (By Gemini)")
    parser.add_argument(
        "--proxy",
        default=None,
        help="proxy address，like http://127.0.0.1:7890 or 711: "
             "http://USER:PASS@global.rotgb.711proxy.com:10000 "
             "（711 will be automatically rewritten as Clash chain relay）",
    )
    parser.add_argument("--email", choices=["mailtm", *list_email_channels()], default="mailtm", help="Registered email source（default mailtm，dms=Self-builtdocker-mailserver，icloud=Hide My Email，outlookpool=Native mailbox pool）")
    parser.add_argument("--once", action="store_true", help="Run only once")
    parser.add_argument("--count", type=int, default=0, help="Total number of registrations（0=unlimited，Cooperate --once Equivalent to1）")
    args = parser.parse_args()

    count = 0
    print("========================================")
    print("[*] OpenAI Ultimate Keygen (bring Token Extract and DDG@duck.com / 163 Mail)")
    print("========================================")
    
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    while True:
        count += 1
        # Maximum total attempts：final insurance，avoid proxies/When the entire pool is unavailable, unlimited number changes will be used.
        if count > MAX_TOTAL_ATTEMPTS:
            print(f"[*] Total attempts limit reached {MAX_TOTAL_ATTEMPTS}，stop（possible agent/The entire pool is unavailable）")
            break
        if args.count and count > args.count:
            count -= 1
            break
        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] >>> Start the first {count} registration process <<<")
        run_result = run(args.proxy, email=args.email)
        
        if run_result:
            token_json, email, password, access_token, session_token = run_result
            fname_email = email.replace("@", "_")

            # Save mechanism 1：Save separately Token JSON document
            tokens_dir = OUT_DIR / "tokens"
            tokens_dir.mkdir(parents=True, exist_ok=True)
            file_path = tokens_dir / f"token_{fname_email}_{int(time.time())}.json"
            if token_json:
                file_path.write_text(token_json, encoding="utf-8")
                print(f"[OK] successfully obtained Token！Saved to: {file_path}")
            elif access_token:
                save = {"accessToken": access_token, "email": email}
                if session_token:
                    save["session_token"] = session_token
                file_path.write_text(json.dumps(save, ensure_ascii=False), encoding="utf-8")
                print(f"[OK] Account created successfully，accessToken Saved to: {file_path}")
            else:
                print(f"[OK] Account created successfully（create_account 200），web flow nothing Codex token（next-auth code）")

            # Save mechanism 2：Summarize account and password information
            acc_file = tokens_dir / "accounts.txt"
            with open(acc_file, "a", encoding="utf-8") as f:
                f.write(f"{email}----{password}\n")
            print(f"[OK] Account has been added to: {acc_file}")
            
        else:
            print("[-] This registration process is disconnected。")

        if args.once:
            break
            
        wait_time = _batch_cooldown_seconds()
        print(f"[*] cool down {wait_time} Second（anti-fuzz Random interval between numbers）...")
        time.sleep(wait_time)

if __name__ == "__main__":
    main()
