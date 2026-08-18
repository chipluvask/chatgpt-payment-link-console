# -*- coding: utf-8 -*-
"""OpenAI Sentinel token mint (Node/V8 sdk bridge → (main, so) Head value).

Alignment link-pp handoff/protocol/sentinel.py: pass stdin Pass parameters to
sentinel_assets/sentinel_bridge.js, parse stdout JSON {main, so}。
main as OpenAI-Sentinel-Token, so as OpenAI-Sentinel-SO-Token。
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

BRIDGE_VERSION = "20260219f9f6"
_BRIDGE_JS = Path(__file__).with_name("sentinel_assets") / "sentinel_bridge.js"


def mint_sentinel_sync(
    *,
    flow: str,
    device_id: str,
    user_agent: str,
    proxy: str = "",
    cores: int = 16,
    page_url: str = "https://chatgpt.com/",
    language: str = "en-US",
    timezone: str = "America/Chicago",
    cookie_header: str = "",
    timeout_s: float = 120.0,
) -> tuple[str, str]:
    """generate OpenAI Sentinel Head value (main, so)。Throw on failure RuntimeError。"""
    payload = json.dumps(
        {
            "ua": user_agent,
            "cores": cores,
            "deviceId": device_id,
            "flow": flow,
            "proxy": proxy,
            "version": BRIDGE_VERSION,
            "pageUrl": page_url,
            "language": language,
            "timezone": timezone,
            "cookieHeader": cookie_header,
            "sentinelOrigin": "https://chatgpt.com",
        },
        separators=(",", ":"),
    ).encode()
    node = os.environ.get("SENTINEL_NODE") or "node"
    try:
        process = subprocess.run(
            [node, str(_BRIDGE_JS)],
            input=payload,
            capture_output=True,
            timeout=timeout_s,
            check=False,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("Sentinel need Node.js") from exc
    except subprocess.TimeoutExpired as exc:
        raise TimeoutError(f"Sentinel Generate timeout（>{timeout_s:.0f}s）") from exc

    output = (process.stdout or b"").decode("utf-8", "replace").strip()
    if not output:
        error = (process.stderr or b"").decode("utf-8", "replace")[:300]
        raise RuntimeError(f"Sentinel bridge No output: {error}")
    try:
        result = json.loads(output)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Sentinel bridge Invalid output: {output[:200]}") from exc
    if result.get("error"):
        raise RuntimeError(f"Sentinel bridge fail: {str(result['error'])[:300]}")
    main = str(result.get("main") or "")
    if not main:
        raise RuntimeError("Sentinel bridge Not returned main token")
    try:
        token_payload = json.loads(main)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Sentinel bridge main token Not valid JSON") from exc
    if (
        token_payload.get("id") != device_id
        or token_payload.get("flow") != flow
        or not token_payload.get("c")
    ):
        raise RuntimeError("Sentinel bridge token with current device/flow no match")
    return main, str(result.get("so") or "")


def try_mint_sentinel(
    *,
    flow: str,
    device_id: str,
    user_agent: str,
    proxy: str = "",
    page_url: str = "https://chatgpt.com/",
    language: str = "en-US",
    timezone: str = "America/Chicago",
    cookie_header: str = "",
) -> tuple[str, str]:
    """mint Return on failure ("", "") Don't throw exception (Alignment link-pp Downgrade strategy)。"""
    try:
        return mint_sentinel_sync(
            flow=flow,
            device_id=device_id,
            user_agent=user_agent,
            proxy=proxy,
            page_url=page_url,
            language=language,
            timezone=timezone,
            cookie_header=cookie_header,
        )
    except Exception:
        return "", ""