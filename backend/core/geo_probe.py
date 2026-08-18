"""exit IP Real country multi-source detection module。

Use proxy link for each detection（curl_cffi chrome TLS fingerprint），from public IP Geographical library source pull export IP。
Three-source cross-validation:
    1. ip-api.com  (HTTP free, 45/min/IP, No need token, High precision)
    2. ipwho.is    (HTTPS free, No need token)
    3. ipinfo.io   (HTTPS free Lite Limited quantity, No need token; high precision city)

Strategy:
    - Any source can be returned successfully（record source），Speed ​​priority。
    - Taken when multiple sources are successful「majority consensus」country code；Fallback to the single source with the highest confidence in case of conflict。
    - result band confidence(0~1) and sources Details，For front-end display/Inventory review。

Because the detection request itself goes through the proxy exit，rate limit press export IP count：Each section of detection has a different exit，
naturally avoided ip-api 45/min/IP limit。same proxy_url(same sticky session) short window
Internal press TTL cache，Avoid repeated probing on retries。
"""
from __future__ import annotations

import datetime as _dt
import os
import threading
import time
from typing import Any, Callable

try:
    from curl_cffi import requests as _curl  # type: ignore
except Exception:  # pragma: no cover
    _curl = None

PROBE_TIMEOUT = 10.0
_CACHE_TTL = float(os.environ.get("PROBE_GEO_CACHE_TTL", "5") or "5")

_cfg: Any = None  # Delayed injection settings (avoid loops import)


def bind_settings(settings: Any) -> None:
    """Inject global settings to read geo Detection switch/time out/source list。"""
    global _cfg
    _cfg = settings


# ---- Analysis of various sources ---
def _parse_ip_api(d: dict[str, Any]) -> tuple[str, str, str, str]:
    if d.get("status") != "success":
        raise ValueError(f"ip-api status={d.get('status')}")
    return (str(d.get("query") or ""),
            str(d.get("countryCode") or "").upper(),
            str(d.get("city") or ""),
            str(d.get("regionName") or ""))


def _parse_ipwhois(d: dict[str, Any]) -> tuple[str, str, str, str]:
    if not d.get("success"):
        raise ValueError(f"ipwhois success={d.get('success')}")
    return (str(d.get("ip") or ""),
            str(d.get("country_code") or "").upper(),
            str(d.get("city") or ""),
            str(d.get("region") or ""))


def _parse_ipinfo(d: dict[str, Any]) -> tuple[str, str, str, str]:
    ip = str(d.get("ip") or "")
    cc = str(d.get("country") or "").upper()
    if not ip or not cc:
        raise ValueError("ipinfo lack ip/country")
    return (ip, cc, str(d.get("city") or ""), str(d.get("region") or ""))


PROVIDERS: dict[str, tuple[str, Callable[[dict[str, Any]], tuple[str, str, str, str]]]] = {
    "ip-api": ("http://ip-api.com/json/", _parse_ip_api),
    "ipwhois": ("https://ipwho.is/", _parse_ipwhois),
    "ipinfo": ("https://ipinfo.io/json", _parse_ipinfo),
}


def _default_sources() -> list[str]:
    if _cfg is not None:
        try:
            opts = (_cfg.raw or {}).get("geo") or {}
            src = opts.get("sources") or ["ip-api", "ipwhois", "ipinfo"]
            return [s for s in src if s in PROVIDERS]
        except Exception:
            pass
    return ["ip-api", "ipwhois", "ipinfo"]


def _default_timeout() -> float:
    if _cfg is not None:
        try:
            return float(((_cfg.raw or {}).get("geo") or {}).get("timeout", PROBE_TIMEOUT))
        except Exception:
            pass
    return PROBE_TIMEOUT


def _default_enabled() -> bool:
    if _cfg is not None:
        try:
            return bool(((_cfg.raw or {}).get("geo") or {}).get("enabled", True))
        except Exception:
            pass
    return True


# ---- cache (TTL) ---
_cache_lock = threading.Lock()
_cache: dict[str, tuple[float, dict[str, Any]]] = {}


def probe_country(proxy: str = "", timeout: float | None = None,
                  sources: list[str] | None = None) -> dict[str, Any]:
    """Detect the real country of export through an agent。

    proxy is empty/When directly connected, use the local exit.。return:
        {"ok", "ip", "country", "city", "confidence", "sources":
            [{"provider","ip","country","city","region"}...], "error", "ts"}
    """
    if _curl is None:
        return {"ok": False, "ip": "", "country": "", "city": "",
                "confidence": 0.0, "sources": [], "error": "curl_cffi Not available"}
    timeout = timeout or _default_timeout()
    srcs = sources or _default_sources()
    now = time.time()
    with _cache_lock:
        hit = _cache.get(proxy)
        if hit and hit[0] > now:
            return dict(hit[1])

    results: list[dict[str, Any]] = []
    errors: list[str] = []
    ip_primary = ""
    if not _default_enabled():
        return {"ok": False, "ip": "", "country": "", "city": "",
                "confidence": 0.0, "sources": [], "error": "geo Probe disabled"}
    for name in srcs:
        url, parse = PROVIDERS.get(name) or (None, None)
        if url is None:
            continue
        try:
            ip, cc, city, region = _probe(url, proxy, parse, timeout)
            results.append({"provider": name, "ip": ip, "country": cc,
                            "city": city, "region": region})
            if not ip_primary:
                ip_primary = ip
        except Exception as e:  # Skip failure source
            errors.append(f"{name}: {type(e).__name__}: {e}")
    codes = [r["country"] for r in results if r["country"]]
    out: dict[str, Any] = {"ok": False, "ip": ip_primary, "country": "",
                           "city": "", "confidence": 0.0,
                           "sources": results, "error": "；".join(errors),
                           "ts": _utc_now()}
    if codes:
        out["ok"] = True
        out["country"] = majority_code(codes) or codes[0]
        matched = sum(1 for c in codes if c == out["country"])
        out["confidence"] = round(matched / len(codes), 2)
        # Main category country city/region priority
        for r in results:
            if r["country"] == out["country"] and r["city"]:
                out["city"] = r["city"]
                break
    with _cache_lock:
        _cache[proxy] = (now + _CACHE_TTL, out)
    return out


def _probe(url: str, proxy: str, parse: Callable[[dict[str, Any]], tuple[str, str, str, str]],
           timeout: float) -> tuple[str, str, str, str]:
    s = _curl.Session(impersonate="chrome131")
    try:
        if proxy:
            s.proxies = {"http": proxy, "https": proxy}
        r = s.get(url, timeout=timeout, verify=False)
        if r.status_code == 200:
            try:
                d = r.json()
            except Exception:
                d = {}
            return parse(d)
        raise ValueError(f"HTTP {r.status_code}")
    finally:
        try:
            s.close()
        except Exception:
            pass


def clear_cache() -> None:
    with _cache_lock:
        _cache.clear()


def majority_code(codes: list[str]) -> str | None:
    counts: dict[str, int] = {}
    for c in codes:
        if c:
            counts[c] = counts.get(c, 0) + 1
    if not counts:
        return None
    return max(counts, key=lambda x: counts[x])


def _utc_now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat()