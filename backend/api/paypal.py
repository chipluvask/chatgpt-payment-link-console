"""PayPal BA Payment authorization API routing。

supply BA Authorization record query、Single/Volume licensing starts、Authorization configuration management and other interfaces。
The authorization queue consists of core.ba_queue maintain: Automatically import after successful chain extraction, After restarting from
success_inventory (paypal channel) seed backfill。

National linkage (BA_COUNTRY_ALIGN_PLAN_20260812):
  - Authorization segment countries follow the queue by default record.country (lift chain segment billing_country)
  - config.identity_country / exit_country Coverable; follow_chain_country=False explicit country
  - Each authorized task is independent country_context, per-task config deep copy snapshot
  - Agents by country from proxy_pool select (711/sing-box/QG), Before starting geo Actual test verification
"""
from __future__ import annotations

import asyncio
import copy
import json
import os
import re
import threading
import time
from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel

from core.ba_queue import (
    add as ba_add,
    bulk_remove as ba_bulk_remove,
    clear as ba_clear,
    count as ba_count,
    extract_ba_token,
    get as ba_get,
    import_from_url,
    list_records,
    mark_stale as ba_mark_stale,
    remove as ba_remove,
    retry as ba_retry,
    try_start as ba_try_start,
    update as ba_update,
)
from core.token_store import token_store

router = APIRouter(prefix="/api/paypal", tags=["paypal"])

_BA_CONFIG_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "ba_config.json"
)

_ba_config: dict[str, Any] = {
    "sms_provider": "smsbower",
    "sms_price": "0.5",
    "sms_price_min": "0",
    "sms_max_attempts": 12,
    "sms_timeout": 15,
    "exit_country": "BR",
    "identity_country": "",
    "sms_country": "",
    "proxy_type": "711_sticky",
    "captcha_strategy": "frontend_disable",
    "buyer_mode": "elevation",
    "max_retries": 3,
    "max_flow_attempts": 2,
    "follow_chain_country": True,
    "fail_fast_geo": True,
    "max_concurrent": 3,
    "flow_timeout_s": 120,
}


def _load_ba_config() -> None:
    """start up/The module is loaded from ba_config.json Restore last configuration (If it does not exist, use the default)。"""
    global _ba_config
    try:
        if not os.path.exists(_BA_CONFIG_FILE):
            return
        with open(_BA_CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            _ba_config.update({k: v for k, v in data.items() if v is not None})
    except Exception:
        pass


def _save_ba_config() -> None:
    """Configuration changes are implemented immediately, Start next time/Refresh automatic recovery。"""
    try:
        tmp = _BA_CONFIG_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(_ba_config, f, ensure_ascii=False, indent=1)
        os.replace(tmp, _BA_CONFIG_FILE)
    except OSError:
        pass


_load_ba_config()

# ---- Authorization segment concurrency gate (independent of chain link max_concurrent_chains) ----
_ba_throttle_lock = threading.Lock()
_ba_running_count = 0


def _merged_ba_config(raw: dict[str, Any] | None) -> dict[str, Any]:
    """Authorize config merge: Explicit field override, Default fallback _ba_config default value。

    historical issues: `req.config or _ba_config` When the front end only transmits some fields, it will not be merged by default.,
    lead to buyer_mode Wait for fallback to hardcoded old value (original / 0.02 wait)。
    """
    merged = dict(_ba_config)
    if isinstance(raw, dict):
        merged.update(raw)
    return merged


def _ba_concurrency_cap(cfg: dict[str, Any] | None = None) -> int:
    """Concurrency limit: per-task config priority, Secondly, the overall situation _ba_config, default 3。"""
    try:
        if cfg is not None and cfg.get("max_concurrent"):
            return max(1, int(cfg.get("max_concurrent")))
    except Exception:
        pass
    try:
        return max(1, int(_ba_config.get("max_concurrent") or 3))
    except Exception:
        return 3


def _ba_acquire_slot(cap: int | None = None) -> bool:
    """Try to occupy a concurrency slot。cap Press when empty _ba_config calculate。"""
    global _ba_running_count
    limit = cap if cap is not None else _ba_concurrency_cap()
    with _ba_throttle_lock:
        if _ba_running_count >= limit:
            return False
        _ba_running_count += 1
        return True


def _ba_release_slot() -> None:
    global _ba_running_count
    with _ba_throttle_lock:
        _ba_running_count = max(0, _ba_running_count - 1)


class BAAuthorizeRequest(BaseModel):
    ba_token: str
    config: dict[str, Any] | None = None


class BABatchRequest(BaseModel):
    ba_tokens: list[str]
    config: dict[str, Any] | None = None


class BAConfigUpdate(BaseModel):
    sms_provider: str | None = None
    sms_api_key: str | None = None
    sms_price: str | None = None
    sms_price_min: str | None = None
    sms_max_attempts: int | None = None
    sms_timeout: int | None = None
    exit_country: str | None = None
    identity_country: str | None = None
    sms_country: str | None = None
    proxy_type: str | None = None
    captcha_strategy: str | None = None
    buyer_mode: str | None = None
    max_retries: int | None = None
    max_flow_attempts: int | None = None
    follow_chain_country: bool | None = None
    fail_fast_geo: bool | None = None
    max_concurrent: int | None = None
    flow_timeout_s: int | None = None


class BAImportRequest(BaseModel):
    text: str | None = None
    urls: list[str] | None = None
    email: str = ""
    country: str = ""
    source: str = "manual"


class BARetryRequest(BaseModel):
    ba_tokens: list[str]
    config: dict[str, Any] | None = None


class BADeleteRequest(BaseModel):
    ba_tokens: list[str]


class BAClearRequest(BaseModel):
    status: str | None = None


def _extract_ba_token(url: str) -> str:
    return extract_ba_token(url)


def _record_to_dict(r: dict[str, Any]) -> dict[str, Any]:
    return {
        "ba_token": r.get("ba_token", ""),
        "email": r.get("email", ""),
        "approve_url": r.get("approve_url", ""),
        "status": r.get("status", "pending"),
        "step": r.get("step", "submit_email"),
        "country": r.get("country", ""),
        "identity_country": r.get("identity_country", ""),
        "proxy_country": r.get("proxy_country", ""),
        "geo_country": r.get("geo_country", ""),
        "chain_id": r.get("chain_id", ""),
        "source": r.get("source", ""),
        "captcha_type": r.get("captcha_type", ""),
        "sms_phone": r.get("sms_phone", ""),
        "sms_price": r.get("sms_price", 0),
        "sms_provider_id": r.get("sms_provider_id", ""),
        "last_msg": r.get("last_msg", ""),
        "last_level": r.get("last_level", ""),
        "error": r.get("error", ""),
        "created_at": r.get("created_at", 0),
        "updated_at": r.get("updated_at", 0),
    }


def _resolve_auth_country(record: dict[str, Any], cfg: dict[str, Any]) -> str:
    """Authorization segment country analysis: follow_chain_country(default) Pick record.country, Otherwise explicit config。"""
    rec_country = str((record or {}).get("country") or "").strip().upper()
    explicit = str(
        cfg.get("identity_country") or cfg.get("exit_country") or ""
    ).strip().upper()
    follow = bool(cfg.get("follow_chain_country", True))
    if follow and rec_country:
        return rec_country
    return explicit or rec_country or "BR"


def _pick_ba_proxy(country: str, cfg: dict[str, Any]) -> tuple[str, str]:
    """Agent selection: explicit proxy > proxy_pool.pick_for_stage(country) > null(direct connection, will be geo check block)。

    proxy_type Configuration items mapped to proxy source preferences:
      - "711" / "711_sticky" (default): proxy_pool internal 711 priority
      - "qg": QG Tunnel priority (proxy_pool Fall back to default when there is no corresponding switch)
      - "singbox": sing-box Node priority (Fall back to default)
    explicit proxy URL Ignore when proxy_type。
    """
    explicit = str(cfg.get("proxy") or os.environ.get("MIN_BA_PROXY", "") or "").strip()
    if explicit:
        return explicit, "explicit"
    try:
        from core.proxy_pool import proxy_pool
        proxy_type = str(cfg.get("proxy_type") or "711_sticky").strip().lower()
        url = proxy_pool.pick_for_stage("resolve", country, source=proxy_type)
        if url:
            return url, "auto"
    except Exception:
        pass
    return "", "none"


def _geo_precheck(proxy: str, country: str) -> dict[str, Any]:
    """Actual testing of agent export countries before authorization is launched。return {ok, country, confidence, error}。"""
    if not proxy:
        return {"ok": False, "country": "", "confidence": 0.0, "error": "no_proxy"}
    try:
        from core.geo_probe import probe_country
        probe = probe_country(proxy=proxy)
    except Exception as exc:
        return {"ok": False, "country": "", "confidence": 0.0, "error": f"geo_probe_exc:{exc}"}
    actual = str(probe.get("country") or "").upper()
    confidence = probe.get("confidence") or 0.0
    if not probe.get("ok") or not actual:
        return {"ok": False, "country": actual, "confidence": confidence,
                "error": str(probe.get("error") or "geo_probe_failed")}
    return {
        "ok": actual == country,
        "country": actual,
        "confidence": confidence,
        "error": "" if actual == country else "geo_mismatch",
    }


def _resolve_sms_country_code(raw: str, ctx) -> tuple[str, str]:
    """Analysis of code receiving countries: alphabetical country code → SMSBower digital country code + Mobile phone country code。

    sms_country Probably from the frontend (letter ISO2, like "TH") or historical configuration (digital code, like "34"):
    - digital code: Transparent transmission as it is, phone_cc Follow the authorizing country context
    - alphabetical code: Walk country_profile Conversion to digital code, phone_cc Follow the code receiving country (The number prefix must be consistent with the country where the number is received)
    - null: Default follows authorizing country context
    """
    from ba_paypal.paypal.country_profile import country_context as _ctx
    from ba_paypal.paypal.country_profile import smsbower_country_id as _sms_id
    raw = str(raw or "").strip()
    if not raw:
        return ctx.sms_country_id, ctx.phone_country
    if raw.isdigit():
        return raw, ctx.phone_country
    cc = raw.upper()
    try:
        sub_ctx = _ctx(cc)
        return sub_ctx.sms_country_id, sub_ctx.phone_country
    except Exception:
        return _sms_id(cc), ctx.phone_country


def _build_sms_provider(country: str, cfg: dict[str, Any]):
    """Structured by country context SMSBower provider (Counter code receiving country + Mobile phone country code + price ceiling)。

    Currently only implemented smsbower (sms_activate/5sim The front-end options will be grayed out and disabled.)。
    """
    provider_name = str(cfg.get("sms_provider") or "smsbower").strip().lower()
    if provider_name not in ("smsbower", "sms_bower", ""):
        return None, f"unsupported_sms_provider:{provider_name} (Only supports smsbower)"
    from ba_paypal.paypal.country_profile import country_context as _ctx
    ctx = _ctx(country)
    try:
        from ba_paypal.paypal.smsbower import build_smsbower_provider as _build
        api_key = str(cfg.get("sms_api_key") or "").strip() or None
        provider = _build(enabled=True, api_key=api_key)
        if provider is None:
            return None, "smsbower_disabled"
        provider.country, provider.phone_cc = _resolve_sms_country_code(
            cfg.get("sms_country"), ctx
        )
        try:
            price = float(str(cfg.get("sms_price") or "0.5"))
            if price > 0:
                provider.max_price = price
        except Exception:
            pass
        try:
            price_min = float(str(cfg.get("sms_price_min") or "0"))
            if price_min > 0:
                provider.min_price = price_min
        except Exception:
            pass
        try:
            max_attempts = int(cfg.get("sms_max_attempts") or 12)
            if max_attempts > 0:
                provider.max_attempts = max(1, max_attempts)
        except Exception:
            pass
        try:
            sms_timeout = float(str(cfg.get("sms_timeout") or "15"))
            if sms_timeout >= 1:
                provider.wait_seconds = sms_timeout
        except Exception:
            pass
        return provider, ""
    except Exception as exc:
        return None, f"sms_provider_exc:{exc}"


async def _run_authorize_task(ba_token: str, cfg: dict[str, Any]) -> None:
    """Single authorization background task (country Follow record / ctx Assemble)。"""
    from ba_paypal import BAAuthorizer

    record = ba_get(ba_token)
    if record is None:
        return
    country = _resolve_auth_country(record, cfg)
    try:
        from ba_paypal.paypal.country_profile import country_context
        ctx = country_context(country)
    except Exception as exc:
        ba_update(ba_token, status="failed", error=f"unsupported_country:{exc}")
        return

    proxy, proxy_source = _pick_ba_proxy(country, cfg)
    # Explicit proxy priority hop geo check; Automatic proxy verification as required (fail_fast_geo default true)
    fail_fast = bool(cfg.get("fail_fast_geo", True))
    geo = None
    if proxy_source == "auto" or not proxy:
        geo = _geo_precheck(proxy, country)
        if not geo.get("ok"):
            ba_update(
                ba_token,
                status="failed",
                error=geo.get("error") or "geo_mismatch",
                proxy_country=geo.get("country") or "",
            )
            return
    ba_update(
        ba_token,
        country=record.get("country") or country,
        identity_country=country,
        proxy_country=proxy or "",
    )

    sms_provider, sms_err = _build_sms_provider(country, cfg)
    if sms_err:
        ba_update(ba_token, status="failed", error=sms_err)
        return

    # The background thread may still be running after timeout (to_thread Will not really cancel), Its subsequent writeback needs to be blocked
    timed_out = threading.Event()

    def _on_flow_progress(idx: int, name: str, status: str, kw: dict) -> None:
        """flow progress_cb -> Queue real-time writeback (3s Polling frontend is visible)。

        write only step + latest msg; sms_price/sms_phone Depend on SMS Segment callback brings out。
        Return after timeout, No longer overwrites writes on timeout branches status/step/error。
        """
        if timed_out.is_set():
            return
        try:
            detail = str(kw.get("detail") or "")
            level = str(kw.get("level") or "info")
            step = str(name or "")
            if step == "sms" and detail:
                # from detail Extract the number price (Format: Number taken provider=xxx price=$0.1234 phone=+66...)
                import re as _re
                m_price = _re.search(r"price=\$([0-9.]+)", detail)
                m_prov = _re.search(r"provider=([0-9]+)", detail)
                m_phone = _re.search(r"phone=(\+\d[\d\s]*)", detail)
                if m_price:
                    ba_update(ba_token, sms_price=float(m_price.group(1)))
                if m_prov:
                    ba_update(ba_token, sms_provider_id=m_prov.group(1))
                if m_phone:
                    ba_update(ba_token, sms_phone=m_phone.group(1).strip())
            ba_update(ba_token, step=step, last_msg=detail, last_level=level)
        except Exception:
            pass

    def _run() -> dict:
        auth = BAAuthorizer(proxy=proxy or None, fp_country=country)
        return auth.authorize(
            f"https://www.paypal.com/agreements/approve?ba_token={ba_token}",
            phone=str(cfg.get("phone") or "").strip() or None,
            buyer_mode=str(cfg.get("buyer_mode") or "elevation").strip().lower(),
            country=country,
            identity=cfg.get("identity"),
            sms_provider=sms_provider,
            max_card_attempts=int(cfg.get("max_retries") or 3) + 2,
            max_flow_attempts=int(cfg.get("max_flow_attempts") or 2),
            max_authorize_attempts=int(cfg.get("max_retries") or 3),
            on_step=_on_flow_progress,
        )

    try:
        # Timeout: flow stuck (like Playwright Cleanup pending) Force the end of the write queue when, Not infinite running
        timeout_s = float(cfg.get("flow_timeout_s") or 480)
        result = await asyncio.wait_for(asyncio.to_thread(_run), timeout=timeout_s)
        ok = result.get("status") == "success"
        ba_update(
            ba_token,
            status="success" if ok else "failed",
            step="done" if ok else str(result.get("reason") or "failed"),
            error="" if ok else str(result.get("error") or result.get("reason") or ""),
            email=(
                (result.get("user") or {}).get("email", "")
                if ok and isinstance(result.get("user"), dict)
                else record.get("email", "")
            ),
        )
    except asyncio.TimeoutError:
        timed_out.set()
        ba_update(
            ba_token,
            status="failed",
            step="failed",
            error=f"flow_timeout (The authorization process exceeds {timeout_s:.0f}s Not over)",
        )
        _logging.getLogger("api.paypal").warning(
            "BA authorize flow timed out after %ss: %s", timeout_s, ba_token,
        )
    except Exception as exc:
        import logging as _logging
        import traceback as _tb

        _logging.getLogger("api.paypal").error(
            "BA authorize task crashed: %s\n%s",
            exc,
            _tb.format_exc(),
        )
        ba_update(ba_token, status="failed", error=f"{type(exc).__name__}: {exc}")
    finally:
        _ba_release_slot()


_seeded_once = False


async def _seed_from_inventory() -> None:
    """When the queue is empty, From Success Inventory (paypal channel) backfill BA Record (only once per process)。

    Ensure that after the backend is restarted, The chain was successfully lifted before BA Still present in authorization queue。
    After manually clearing the queue, it will not be filled again. (within this process _seeded_once Set)。
    """
    global _seeded_once
    if _seeded_once:
        return
    _seeded_once = True
    if ba_count() > 0:
        return
    try:
        recs = await token_store.list_success(limit=500, channel="paypal")
    except Exception:
        return
    for r in recs:
        url = r.get("paypal_approve_url") or ""
        if "ba_token=" in url:
            import_from_url(
                url,
                email=r.get("email") or "",
                country=r.get("exit_country") or r.get("billing_country") or "",
                chain_id=r.get("ba") or "",
                source="inventory",
            )


@router.get("/ba/records")
async def get_ba_records() -> dict[str, Any]:
    """Get all BA Authorization record。"""
    await _seed_from_inventory()
    ba_mark_stale()
    records = list_records()
    return {
        "ok": True,
        "records": [_record_to_dict(r) for r in records],
        "total": len(records),
    }


@router.get("/ba/pending")
async def get_pending_ba() -> dict[str, Any]:
    """Get the pending authorization BA Record（Extract from success link）。"""
    await _seed_from_inventory()
    pending = [r for r in list_records() if r.get("status") == "pending"]
    return {
        "ok": True,
        "records": [_record_to_dict(r) for r in pending],
        "count": len(pending),
    }


@router.post("/ba/authorize")
async def authorize_ba(req: BAAuthorizeRequest) -> dict[str, Any]:
    """Start a single BA Authorization process (country follows queue record.country or config cover)。"""
    ba_token = req.ba_token.strip()
    if not ba_token:
        return {"ok": False, "error": "ba_token is required"}

    # Find or create records
    record = ba_get(ba_token)
    if record is None:
        cfg0 = req.config or {}
        country0 = str(
            cfg0.get("identity_country") or cfg0.get("exit_country") or ""
        ).upper()
        record = {
            "ba_token": ba_token,
            "email": "",
            "approve_url": f"https://www.paypal.com/agreements/approve?ba_token={ba_token}",
            "status": "pending",
            "step": "submit_email",
            "country": country0,
            "chain_id": "",
            "captcha_type": "",
            "sms_phone": "",
            "error": "",
            "source": "manual",
            "created_at": int(time.time() * 1000),
            "updated_at": int(time.time() * 1000),
        }
        ba_add(**record)

    cfg = _merged_ba_config(req.config)

    # pending -> running Atomic transfer (Repeated launch denied)
    ok, lock_err = ba_try_start(ba_token)
    if not ok:
        return {"ok": False, "error": lock_err}
    if not _ba_acquire_slot(cap=_ba_concurrency_cap(cfg)):
        ba_update(ba_token, status="pending", error="")
        return {"ok": False, "error": "concurrency_limit"}

    asyncio.create_task(_run_authorize_task(ba_token, cfg))

    return {
        "ok": True,
        "ba_token": ba_token,
        "status": "running",
        "step": "submit_email",
        "message": "BA Authorization process started (ba_paypal)",
    }


@router.post("/ba/batch")
async def batch_authorize(req: BABatchRequest) -> dict[str, Any]:
    """Batch start BA Authorize (Start tasks step by step, each record Distributed in respective countries)。"""
    tokens = [t.strip() for t in (req.ba_tokens or []) if t and t.strip()]
    if not tokens:
        return {"ok": False, "error": "ba_tokens list is empty"}

    started: list[str] = []
    skipped: dict[str, str] = {}
    for ba_token in tokens:
        record = ba_get(ba_token)
        if record is None:
            cfg0 = req.config or {}
            country0 = str(
                cfg0.get("identity_country") or cfg0.get("exit_country") or ""
            ).upper()
            ba_add(
                ba_token,
                approve_url=f"https://www.paypal.com/agreements/approve?ba_token={ba_token}",
                status="pending",
                step="submit_email",
                country=country0,
                source="manual",
            )
        ok, err = ba_try_start(ba_token)
        if not ok:
            skipped[ba_token] = err
            continue
        cfg = _merged_ba_config(req.config)
        if not _ba_acquire_slot(cap=_ba_concurrency_cap(cfg)):
            ba_update(ba_token, status="pending", error="")
            skipped[ba_token] = "concurrency_limit"
            break
        asyncio.create_task(_run_authorize_task(ba_token, cfg))
        started.append(ba_token)

    return {
        "ok": True,
        "started": len(started),
        "skipped": skipped,
        "total": len(tokens),
        "message": f"Started {len(started)}/{len(tokens)} strip BA Authorize",
    }


@router.post("/ba/import")
async def import_ba_manual(req: BAImportRequest) -> dict[str, Any]:
    """Manual import BA Link/bare token to the authorization queue (Support multi-line text / array / Single)。

    Compatible with old calls: body Contains paypal_approve_url Import by single item。
    """
    # Compatible with older formats: {paypal_approve_url, email, country, chain_id}
    body_items: list[str] = []
    if isinstance(req.urls, list):
        body_items.extend(u for u in req.urls if u and str(u).strip())
    if req.text and req.text.strip():
        for line in req.text.splitlines():
            for part in re.split(r"[,\s;]+", line.strip()):
                if part:
                    body_items.append(part)

    if not body_items:
        return {"ok": False, "error": "text/urls is empty"}

    email = (req.email or "").strip()
    country = (req.country or "").strip().upper()
    source = (req.source or "manual").strip() or "manual"

    seen: set[str] = set()
    imported: list[str] = []
    exists: list[str] = []
    invalid: list[str] = []
    for item in body_items:
        tok = extract_ba_token(item)
        if not tok:
            invalid.append(item)
            continue
        if tok in seen:
            continue
        seen.add(tok)
        if ba_get(tok) is not None:
            exists.append(tok)
            continue
        ba_add(
            tok,
            email=email,
            approve_url=f"https://www.paypal.com/agreements/approve?ba_token={tok}",
            status="pending",
            step="submit_email",
            country=country,
            chain_id="manual",
            source=source,
        )
        imported.append(tok)

    return {
        "ok": True,
        "imported": imported,
        "exists": exists,
        "invalid": invalid,
        "total": len(imported) + len(exists),
        "message": f"import {len(imported)} strip, repeat {len(exists)} strip, invalid {len(invalid)} strip",
    }


@router.post("/ba/import_url")
async def import_ba_from_chain(request: Request) -> dict[str, Any]:
    """Import from success link BA URL to the authorization queue (Keep legacy endpoints compatible)。

    Receive link success result in paypal_approve_url，extract ba_token。
    (orchestrator Already automatically imported when the link is successful, This endpoint is reserved for manual calls)
    """
    body = await request.json()
    url = body.get("paypal_approve_url", "")
    email = body.get("email", "")
    country = body.get("country", "")
    chain_id = body.get("chain_id", "")

    ba_token = _extract_ba_token(url)
    if not ba_token:
        return {"ok": False, "error": "No ba_token found in URL"}

    if ba_get(ba_token) is not None:
        return {"ok": True, "exists": True, "ba_token": ba_token}

    imported = import_from_url(url, email=email, country=country, chain_id=chain_id)
    return {"ok": True, "imported": imported, "ba_token": ba_token}


@router.post("/ba/retry")
async def retry_ba_batch(req: BARetryRequest) -> dict[str, Any]:
    """Batch retry BA: failed -> pending (allow_success=true You can rerun it even if it has been authorized.) -> start up。"""
    tokens = [t.strip() for t in (req.ba_tokens or []) if t and t.strip()]
    if not tokens:
        return {"ok": False, "error": "ba_tokens list is empty"}

    started: list[str] = []
    skipped: dict[str, str] = {}
    allow_success = bool((req.config or {}).get("allow_success_retry", False))
    for ba_token in tokens:
        if not ba_retry(ba_token, allow_success=allow_success):
            skipped[ba_token] = "not_retryable_or_not_found"
            continue
        # retry Just put failed->pending; Required before starting try_start change running,
        # Otherwise, the task is running but the queue status stay pending: The front end does not display"Authorization start"、
        # and batch/authorize will regard it as pending Repeated start
        ok, lock_err = ba_try_start(ba_token)
        if not ok:
            skipped[ba_token] = lock_err
            continue
        cfg = _merged_ba_config(req.config)
        if not _ba_acquire_slot(cap=_ba_concurrency_cap(cfg)):
            ba_update(ba_token, status="pending", error="")
            skipped[ba_token] = "concurrency_limit"
            break
        asyncio.create_task(_run_authorize_task(ba_token, cfg))
        started.append(ba_token)

    return {
        "ok": True,
        "started": len(started),
        "skipped": skipped,
        "total": len(tokens),
        "message": f"Retried {len(started)}/{len(tokens)} strip BA Authorize",
    }


@router.post("/ba/delete")
async def delete_ba_records(req: BADeleteRequest) -> dict[str, Any]:
    """Batch delete BA Authorization record。"""
    tokens = [t.strip() for t in (req.ba_tokens or []) if t and t.strip()]
    if not tokens:
        return {"ok": False, "error": "ba_tokens list is empty"}
    deleted = ba_bulk_remove(tokens)
    return {"ok": True, "deleted": deleted, "total": len(tokens)}


@router.post("/ba/clear")
async def clear_ba_records(req: BAClearRequest) -> dict[str, Any]:
    """Clear the queue: status Clear all by default; Only clear this status when specified (pending/running/success/failed)。"""
    status = (req.status or "").strip().lower()
    if status in ("pending", "running", "success", "failed"):
        removed = ba_clear(status=status)
    else:
        removed = ba_clear()
        status = "all"
    return {"ok": True, "removed": removed, "status": status}


@router.get("/ba/config")
async def get_ba_config() -> dict[str, Any]:
    """Get BA Authorization configuration。"""
    return {"ok": True, "config": _ba_config}


@router.post("/ba/config")
async def update_ba_config(req: BAConfigUpdate) -> dict[str, Any]:
    """renew BA Authorization configuration (Place order now, Automatically restore after restart)。

    captcha_strategy: frontend_disable / manual_required — Also write environment variables
    for flow of paypal_captcha_bypass_mode() read (The original configuration item is never flow Consumption)。
    """
    updates = req.model_dump(exclude_none=True)
    strategy = str(updates.get("captcha_strategy") or "").strip().lower()
    if strategy:
        if strategy in ("frontend_disable", "manual_required"):
            os.environ["PAYPAL_CAPTCHA_BYPASS_MODE"] = strategy
        else:
            updates["captcha_strategy"] = ""
    _ba_config.update(updates)
    _save_ba_config()
    return {"ok": True, "config": _ba_config}


@router.get("/ba/stats")
async def get_ba_stats() -> dict[str, Any]:
    """Get BA Authorization statistics。"""
    await _seed_from_inventory()
    records = list_records()
    total = len(records)
    pending = sum(1 for r in records if r.get("status") == "pending")
    running = sum(1 for r in records if r.get("status") == "running")
    success = sum(1 for r in records if r.get("status") == "success")
    failed = sum(1 for r in records if r.get("status") == "failed")

    iq_count = sum(1 for r in records if r.get("captcha_type") == "iq")
    pi_count = sum(1 for r in records if r.get("captcha_type") == "pi")

    # Country distribution (new)
    by_country: dict[str, int] = {}
    for r in records:
        cc = (r.get("identity_country") or r.get("country") or "UNKNOWN").upper()
        by_country[cc] = by_country.get(cc, 0) + 1

    return {
        "ok": True,
        "stats": {
            "total": total,
            "pending": pending,
            "running": running,
            "success": success,
            "failed": failed,
            "success_rate": round(success / (success + failed) * 100, 1) if (success + failed) > 0 else 0,
            "captcha_iq": iq_count,
            "captcha_pi": pi_count,
            "by_country": by_country,
        },
    }


@router.delete("/ba/{ba_token}")
async def delete_ba_record(ba_token: str) -> dict[str, Any]:
    """delete BA Authorization record。"""
    deleted = ba_remove(ba_token)
    return {"ok": True, "deleted": 1 if deleted else 0}


class IdentityRequest(BaseModel):
    country: str = "US"
    count: int = 1


@router.get("/identity/countries")
async def identity_countries() -> dict[str, Any]:
    """List all countries supported by Identity Vault (Contains sms/proxy Available tags, For front-end dust removal)。"""
    try:
        from ba_paypal.paypal.country_profile import available
        items = []
        for cc in available():
            try:
                from ba_paypal.paypal.country_profile import (
                    country_context,
                    sms_supported,
                    proxy_supported,
                )
                ctx = country_context(cc)
                items.append({
                    "code": cc,
                    "sms_supported": sms_supported(cc),
                    "proxy_supported": proxy_supported(cc),
                    "sms_country_id": ctx.sms_country_id,
                })
            except Exception:
                items.append({"code": cc, "sms_supported": False, "proxy_supported": False, "sms_country_id": ""})
        return {"ok": True, "countries": items}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


@router.get("/identity/fields/{country}")
async def identity_fields(country: str) -> dict[str, Any]:
    """Returns the form field configuration for the specified country (kycFields / id_types)。"""
    try:
        from ba_paypal.paypal.identity_lib import profile_summary
        return {"ok": True, "profile": profile_summary(country.upper())}
    except KeyError:
        return {"ok": False, "error": f"unsupported country: {country.upper()}"}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


@router.post("/identity/generate")
async def identity_generate(req: IdentityRequest) -> dict[str, Any]:
    """Generate registration identity data by country (Name/Birthday/ID number, etc., All check digits are valid)。"""
    try:
        from ba_paypal.paypal.identity_lib import generate_country_data
        items = generate_country_data(req.country.upper(), req.count)
        return {"ok": True, "country": req.country.upper(), "items": items}
    except KeyError:
        return {"ok": False, "error": f"unsupported country: {req.country.upper()}"}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


@router.get("/sms/quote")
async def sms_quote(country: str, service: str | None = None) -> dict[str, Any]:
    """Price quotation: List of lowest priced suppliers available in the country (bring TTL cache, Only check once for the same country in batches)。"""
    cc = (country or "").strip().upper()
    try:
        from ba_paypal.paypal.smsbower import build_provider_for_quote
        quotes = build_provider_for_quote(cc, service=service)
        return {"ok": True, "country": cc, "quotes": quotes,
                "service": quotes[0].get("service") if quotes else ""}
    except Exception as exc:
        return {"ok": False, "country": cc, "error": str(exc), "quotes": []}