"""link control routing。

REST:
- POST /api/chain/batch   - Batch start
- POST /api/chain/stop    - stop
- GET  /api/chain/status  - Running status
- POST /api/chain/momo    - MoMo Lift chain start
"""
from __future__ import annotations

from fastapi import APIRouter

from core.momo import momo_patches
from core.token_store import token_store
from .deps import runtime

router = APIRouter(prefix="/api/chain", tags=["chain"])


@router.post("/batch")
async def batch_start(body: dict):
    """Start links in batches。attempts Wait for the default startup parameters to take the branch configuration. (Link configuration page management)。"""
    if not runtime.orchestrator:
        return {"ok": False, "error": "Engine not ready"}
    token_ids = body.get("token_ids", [])
    if not token_ids:
        return {"ok": False, "error": "Not selected Token"}
    branch = str(body.get("branch") or "paypal")
    from core.config import settings
    bcfg = settings.branch(branch)
    options = {
        "max_concurrent": body.get("max_concurrent"),
        "retry_per_stage": body.get("retry_per_stage", 3),
        "attempts": body.get("attempts", bcfg.attempts),
        "auto_billing": body.get("auto_billing", True),
        "require_zero": body.get("require_zero", True),
        "channel_check": body.get("channel_check", True),
        "branch": branch,
    }
    return await runtime.orchestrator.run_batch(token_ids, options)


@router.post("/stop")
async def stop_chain(body: dict):
    """stop link。chain_ids If empty, stop all。"""
    if not runtime.orchestrator:
        return {"ok": False, "error": "Engine not ready"}
    chain_ids = body.get("chain_ids")
    return await runtime.orchestrator.stop_batch(chain_ids)


@router.get("/status")
async def chain_status():
    if not runtime.orchestrator:
        return {"running": False, "active": 0, "queued": 0, "success": 0, "failure": 0}
    return runtime.orchestrator.status()


@router.post("/momo")
async def momo_run(body: dict):
    """MoMo Lift chain start（Go universal AsyncChain，branch=momo parameterization PM/confirm/resolve）。

    fifth floor Patch（momo.py）Already incorporated branch_profile：pm_type=momo、confirm_type=momo、
    resolve regular payment.momo.vn/pay/app。connect_intercept/dns_fix Still needs proxy layer support。
    """
    if not runtime.orchestrator or not runtime.conn_mgr:
        return {"ok": False, "error": "Engine not ready"}
    token_id = body.get("token_id")
    if not token_id:
        return {"ok": False, "error": "Lack token_id"}
    # renew Patch switch（Compatible with old front-ends，Log status only）
    patches = body.get("patches")
    if patches:
        momo_patches.update(patches)
    options = {
        "branch": "momo",
        "max_concurrent": 1,
        "attempts": int(body.get("attempts") or 3),
        "require_zero": False,
        "channel_check": True,
    }
    res = await runtime.orchestrator.run_batch([token_id], options)
    return {"ok": bool(res and res.get("ok")), "total": (res or {}).get("total", 0),
            "patches": momo_patches.to_dict(),
            "note": "momo Walk AsyncChain real link (branch=momo)"}


@router.post("/detect")
async def detect_channel_api(body: dict):
    """Channel detection：checkout(none promo) -> init0(channel) -> update(press0) -> init1(Verification channel+0Yuan)。

    body: {channel: "momo"|"pix"|"ideal"|... , country: "VN", currency: "VND"(Optional),
           update_country: "VN"(Optional, Take branch by default update Configuration), token_id: "123"(Optional)}
    return: {ok, channel, present, zero_ok, methods0, methods1, amount0, amount1, error}
    """
    from core.detect import detect_channel
    from core.proxy_pool import proxy_pool
    from core.config import settings

    channel = str(body.get("channel") or "momo").strip().lower()
    country = str(body.get("country") or "VN").strip().upper()
    currency = str(body.get("currency") or "").strip().upper()
    token_id = str(body.get("token_id") or "").strip()

    # update Exporting country：Explicit or per-branch configuration
    branch = channel
    bcfg = settings.branch(branch)
    upd_stage = bcfg.stages.get("update") if isinstance(bcfg.stages, dict) else None
    upd_countries = upd_stage.countries if upd_stage else []
    update_country = str(body.get("update_country") or "").strip().upper() or (upd_countries[0] if upd_countries else "VN")

    # Pick token
    tok = None
    if token_id:
        tok = await token_store.get_token(token_id)
    else:
        toks = await token_store.list_tokens()
        if toks:
            tok = toks[0]
    if not tok:
        return {"ok": False, "error": "Not found available Token"}
    at = tok.get("access_token") or tok.get("raw") or ""
    st = tok.get("session_token") or ""

    # Substitute agent（checkout exit + update exit）
    try:
        proxy = proxy_pool.pick_for_stage("checkout", country)
        update_proxy = proxy_pool.pick_for_stage("update", update_country)
    except Exception as e:
        return {"ok": False, "error": f"Agent acquisition failed: {e}"}

    import asyncio
    try:
        result = await asyncio.to_thread(
            detect_channel, proxy, at, st, country, currency, channel,
            update_country, update_proxy,
        )
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}
    result["token_id"] = tok.get("id")
    return {"ok": True, **result}
