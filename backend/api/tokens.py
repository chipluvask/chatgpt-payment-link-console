"""Token CRUD + Import routes in batches。

REST:
- POST /api/tokens/import  - Batch import
- GET  /api/tokens         - Token list
- DELETE /api/tokens/{id}  - delete
- POST /api/tokens/{id}/run - one Token start up (forward to chain batch)
- POST /api/tokens/{id}/probe - session type/discount/token status detection
- POST /api/tokens/{id}/tags - Set label
"""
from __future__ import annotations

import json
import time

from fastapi import APIRouter

from core.config import settings
from core.token_store import token_store
from .deps import runtime

router = APIRouter(prefix="/api/tokens", tags=["tokens"])

# Zero decimal currency: amount_due It is the smallest unit, No points->yuan conversion
_ZERO_DECIMAL_CURRENCIES = {
    "JPY", "KRW", "VND", "IDR", "CLP", "ISK", "XOF", "XAF", "UGX", "RWF",
    "BIF", "GNF", "KMF", "DJF", "VUV", "PYG", "MGA", "IQD", "TWD",
}


def _fmt_amount(due: Any, currency: str = "") -> str:
    """amount_due in smallest unit(point)storage, Convert to main unit for easy display。"""
    try:
        v = float(due)
    except (TypeError, ValueError):
        return ""
    if (currency or "USD").upper() in _ZERO_DECIMAL_CURRENCIES:
        return str(int(v))
    return f"{v / 100:.2f}"


def _parse_probe(raw: str) -> dict:
    try:
        d = json.loads(raw or "{}")
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def _split_tags(raw: str) -> list[str]:
    return [t for t in (str(raw or "").split(",")) if t.strip()]


@router.get("")
async def list_tokens(source: str | None = None):
    tokens = await token_store.list_tokens(source=source)
    # Compatible with front-end fields
    out = []
    for t in tokens:
        out.append({
            "id": t["id"], "email": t.get("email", ""), "sub": t.get("sub", ""),
            "account_id": t.get("account_id", ""), "plan_type": t.get("plan_type", ""),
            "register_method": t.get("register_method", "email"),
            "expires_at": t.get("expires_at", ""), "status": t.get("status", "idle"),
            "created_at": t.get("created_at", ""), "last_run_at": t.get("last_run_at", ""),
            "source": t.get("source", "stripe"),
            "session_type": t.get("session_type", ""),
            "probe": _parse_probe(t.get("probe", "")),
            "tags": _split_tags(t.get("tags", "")),
        })
    return {"ok": True, "tokens": out, "total": len(out), "source": source or "all"}


def _probe_token_session(token: dict[str, Any]) -> tuple[str, dict]:
    """Complete detection of a single token: session type + token state + Discount qualifications, Write library。

    return (session type, Complete detection results dict), For callers to broadcast in real time probe_done。
    """
    from core.detect import probe_token
    from core.proxy_pool import proxy_pool
    at = token.get("access_token") or token.get("raw") or ""
    st = token.get("session_token") or ""
    if not at:
        return "error:no_token", {}
    try:
        proxy = proxy_pool.pick_for_stage("checkout", "US")
    except Exception:
        proxy = ""
    try:
        r = probe_token(at, st, proxy=proxy, country="US", currency="USD")
        stype = r.get("session_type") or ""
        if not stype:
            stype = f"error:{r.get('token_error') or r.get('error') or 'unknown'}"[:60]
        probe = {
            "session_type": r.get("session_type") or "",
            "token": r.get("token") or "",
            "token_error": r.get("token_error") or "",
            "promo": r.get("promo") or "",
            "paypal": bool(r.get("paypal")),
            "amount": r.get("amount"),
            "status": r.get("status") or 0,
            "ts": int(time.time()),
        }
        token_store.set_session_type_sync(token["id"], stype)
        token_store.set_probe_sync(token["id"], json.dumps(probe, ensure_ascii=False))
        return stype, probe
    except Exception as e:
        stype = f"error:{type(e).__name__}:{str(e)[:40]}"[:60]
        try:
            token_store.set_session_type_sync(token["id"], stype)
        except Exception:
            pass
        return stype, {}


async def _probe_new_tokens(new_tokens: list[dict]) -> None:
    """background detection token list (concurrent 3), Every time a broadcast is completed probe_done + probe_progress。"""
    if not new_tokens:
        return
    import asyncio
    total = len(new_tokens)
    sem = asyncio.Semaphore(3)
    done = 0

    async def _one(tok: dict) -> None:
        nonlocal done
        async with sem:
            try:
                stype, probe = await asyncio.to_thread(_probe_token_session, tok)
            except Exception:
                stype, probe = "error:probe_failed", {}
        done += 1
        if runtime.conn_mgr:
            await runtime.conn_mgr.broadcast({
                "type": "probe_done",
                "token_id": tok.get("id", ""),
                "session_type": stype,
                "probe": probe,
            })
            await runtime.conn_mgr.broadcast({
                "type": "probe_progress", "done": done, "total": total,
            })

    try:
        await asyncio.gather(*[_one(t) for t in new_tokens], return_exceptions=True)
        all_tokens = await token_store.list_tokens()
        if runtime.conn_mgr:
            token_list = [
                {"id": t["id"], "email": t.get("email", ""), "sub": t.get("sub", ""),
                 "plan_type": t.get("plan_type", ""), "status": t.get("status", "idle"),
                 "register_method": t.get("register_method", "email"),
                 "session_type": t.get("session_type", ""),
                 "probe": _parse_probe(t.get("probe", "")),
                 "tags": _split_tags(t.get("tags", "")),
                 "expires_at": t.get("expires_at", ""), "source": t.get("source", "stripe")}
                for t in all_tokens
            ]
            await runtime.conn_mgr.broadcast({
                "type": "token_imported", "tokens": token_list,
                "imported": 0, "failed": 0,
            })
            await runtime.conn_mgr.broadcast({
                "type": "probe_progress", "done": total, "total": total,
            })
    except Exception:
        pass


@router.post("/import")
async def import_tokens(body: dict):
    raw = body.get("raw", "")
    source = str(body.get("source") or "stripe").strip().lower() or "stripe"
    if not raw.strip():
        return {"ok": False, "imported": 0, "failed": 0, "tokens": [], "error": "raw is empty"}
    imported, failed, new_tokens = await token_store.import_raw(raw, source=source)
    # broadcast token_imported event
    if runtime.conn_mgr:
        all_tokens = await token_store.list_tokens()
        token_list = [
            {"id": t["id"], "email": t.get("email", ""), "sub": t.get("sub", ""),
             "plan_type": t.get("plan_type", ""), "status": t.get("status", "idle"),
             "register_method": t.get("register_method", "email"),
             "session_type": t.get("session_type", ""),
             "probe": _parse_probe(t.get("probe", "")),
             "tags": _split_tags(t.get("tags", "")),
             "expires_at": t.get("expires_at", ""), "source": t.get("source", "stripe")}
            for t in all_tokens
        ]
        await runtime.conn_mgr.broadcast({
            "type": "token_imported", "tokens": token_list,
            "imported": imported, "failed": failed,
        })
    # Automatically detect session type in the background (cs_live / oaics) and mark
    if new_tokens:
        import asyncio
        asyncio.create_task(_probe_new_tokens(new_tokens))
    return {"ok": True, "imported": imported, "failed": failed, "tokens": new_tokens}


@router.post("/import-from-pool")
async def import_from_pool(body: dict):
    """Register pool from email (codex_register) Pull unused mailboxes/token Import this library。

    body: {status?:"unused", source?:"stripe"} — base_url Walk config.register_pool
    pull GET {base_url}/api/emails?status=unused，through import_from_pool according to
    access_token + email Write after deduplication tokens surface。
    return {ok, total, imported, skipped, tokens}
    """
    import httpx
    import urllib.parse

    status = str(body.get("status") or "unused").strip() or "unused"
    source = str(body.get("source") or "stripe").strip().lower() or "stripe"
    pool = settings.register_pool or {}
    base_url = str(pool.get("base_url") or "http://127.0.0.1:8780").rstrip("/")
    timeout = float(pool.get("timeout") or 15)
    url = f"{base_url}/api/emails?status={urllib.parse.quote(status)}"
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()
    except Exception as e:
        return {"ok": False, "error": f"Failed to pull registration pool: {e}"}
    emails = (data or {}).get("emails") or []
    imported, skipped, new_tokens = await token_store.import_from_pool(emails, source=source)
    # broadcast token_imported event
    if runtime.conn_mgr:
        all_tokens = await token_store.list_tokens()
        token_list = [
            {"id": t["id"], "email": t.get("email", ""), "sub": t.get("sub", ""),
             "plan_type": t.get("plan_type", ""), "status": t.get("status", "idle"),
             "register_method": t.get("register_method", "email"),
             "session_type": t.get("session_type", ""),
             "probe": _parse_probe(t.get("probe", "")),
             "tags": _split_tags(t.get("tags", "")),
             "expires_at": t.get("expires_at", ""), "source": t.get("source", "stripe")}
            for t in all_tokens
        ]
        await runtime.conn_mgr.broadcast({
            "type": "token_imported", "tokens": token_list,
            "imported": imported, "failed": skipped,
        })
    # Automatically detect session type in the background
    if new_tokens:
        import asyncio
        asyncio.create_task(_probe_new_tokens(new_tokens))
    return {"ok": True, "total": len(emails), "imported": imported, "skipped": skipped, "tokens": new_tokens}


@router.get("/inventory")
async def list_inventory(channel: str | None = None, limit: int = 200):
    """Successful production of inventory (BA Library)。channel When it is not available, press the payment channel(lifting chain branch)isolation filter。"""
    recs = await token_store.list_success(limit=min(int(limit) or 200, 1000), channel=channel)
    out = []
    for r in recs:
        out.append({
            "ba_id": r.get("ba") or "",
            "email": r.get("email") or "",
            "country": r.get("billing_country") or "",
            "paypal_url": r.get("paypal_approve_url") or "",
            "pm_authorize_url": r.get("pm_authorize_url") or "",
            "amount": _fmt_amount(r.get("amount_due"), r.get("currency") or ""),
            "currency": r.get("currency") or "",
            "time": r.get("ts") or "",
            "channel": r.get("payment_channel") or "paypal",
        })
    return {"ok": True, "records": out, "total": len(out), "channel": channel or "all"}


@router.post("/inventory/clear")
async def clear_inventory(body: dict | None = None):
    """Cleared successful inventory。body: {channel?: "paypal"|...} If empty, all channels will be cleared.。"""
    channel = str((body or {}).get("channel") or "").strip().lower() or None
    deleted = await token_store.clear_success(channel)
    return {"ok": True, "deleted": deleted, "channel": channel or "all"}


@router.post("/repair")
async def repair_tokens():
    """Repair inventory Token metadata: Recalculation registration method, remove contaminated email。"""
    fixed = await token_store.repair_metadata()
    all_tokens = await token_store.list_tokens()
    if runtime.conn_mgr:
        token_list = [
            {"id": t["id"], "email": t.get("email", ""), "sub": t.get("sub", ""),
             "account_id": t.get("account_id", ""), "plan_type": t.get("plan_type", ""),
             "register_method": t.get("register_method", "email"),
             "expires_at": t.get("expires_at", ""), "status": t.get("status", "idle"),
             "source": t.get("source", "stripe")}
            for t in all_tokens
        ]
        await runtime.conn_mgr.broadcast({
            "type": "token_imported", "tokens": token_list,
            "imported": 0, "failed": 0,
        })
    return {"ok": True, "fixed": fixed, "total": len(all_tokens)}


@router.delete("/{token_id}")
async def delete_token(token_id: str):
    ok = await token_store.delete_token(token_id)
    return {"ok": ok, "error": "" if ok else "Token does not exist"}


@router.post("/probe")
async def probe_tokens_batch(body: dict | None = None):
    """Batch detection token: session type + Discount qualifications + token state。

    body: {ids?: [token_id...], source?: "stripe"} — ids If empty, detect the specified source all。
    concurrent 3, background execution, Return the number of started。
    """
    body = body or {}
    ids = body.get("ids") or []
    source = str(body.get("source") or "").strip() or None
    if ids:
        toks = []
        for tid in ids:
            t = await token_store.get_token(str(tid))
            if t:
                toks.append(t)
    else:
        toks = await token_store.list_tokens(source=source)
    if not toks:
        return {"ok": False, "started": 0, "error": "no detectable Token"}
    import asyncio
    asyncio.create_task(_probe_new_tokens(toks))
    return {"ok": True, "started": len(toks)}


@router.post("/{token_id}/probe")
async def probe_token_session(token_id: str):
    """Manual complete detection: session type (cs_live/oaics) + Discount qualifications + token state。"""
    tok = await token_store.get_token(token_id)
    if not tok:
        return {"ok": False, "error": "Token does not exist"}
    import asyncio
    stype, _ = await asyncio.to_thread(_probe_token_session, tok)
    tok2 = await token_store.get_token(token_id)
    probe = _parse_probe(tok2.get("probe", "")) if tok2 else {}
    return {"ok": True, "token_id": token_id,
            "session_type": stype,
            "probe": probe}


@router.post("/{token_id}/tags")
async def set_token_tags(token_id: str, body: dict | None = None):
    """set up token Label。body: {tags: ["Promotion", "google"]}"""
    tags = (body or {}).get("tags") or []
    if not isinstance(tags, list):
        return {"ok": False, "error": "tags Must be an array"}
    tok = await token_store.get_token(token_id)
    if not tok:
        return {"ok": False, "error": "Token does not exist"}
    await token_store.set_tags(token_id, [str(x) for x in tags])
    return {"ok": True, "token_id": token_id, "tags": [str(x) for x in tags]}


@router.post("/{token_id}/run")
async def run_single(token_id: str, body: dict | None = None):
    """one Token start link。"""
    if not runtime.orchestrator:
        return {"ok": False, "error": "Engine not ready"}
    options = {
        "max_concurrent": 1,
        "retry_per_stage": (body or {}).get("retry_per_stage", 3),
        "attempts": (body or {}).get("attempts", 8),
        "auto_billing": (body or {}).get("auto_billing", True),
        "require_zero": (body or {}).get("require_zero", True),
        "channel_check": (body or {}).get("channel_check", True),
        "branch": str((body or {}).get("branch") or "paypal"),
    }
    res = await runtime.orchestrator.run_batch([token_id], options)
    return res
