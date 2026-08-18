"""statistics + sample + Recipe routing。

REST:
- GET /api/stats             - Cumulative statistics
- GET /api/samples           - Sample query (?success=true|false)
- GET /api/formulas          - Success recipe

Notice: /api/config and /api/billing/templates Migrated to api/config.py，
      No more registration here to avoid routing conflicts。
"""
from __future__ import annotations

from fastapi import APIRouter

from core.config import settings
from core.token_store import token_store
from .deps import runtime

router = APIRouter(prefix="/api", tags=["stats"])


@router.get("/stats")
async def stats():
    if runtime.orchestrator:
        s = runtime.orchestrator.stats.to_dict()
        latencies = runtime.orchestrator.stats.latencies[-100:]
    else:
        s = {"success": 0, "failure": 0, "byCountry": {}, "failByCountry": {},
             "reasons": {}, "stageMatrix": {}}
        latencies = []
    # The cumulative number of samples in the merged database
    try:
        succ, fail = await token_store.count_samples()
        s["success"] = max(s["success"], succ)
        s["failure"] = max(s["failure"], fail)
    except Exception:
        pass
    return {"ok": True, "stats": s, "latencies": latencies}


@router.get("/samples")
async def samples(success: str | None = None, limit: int = 100):
    """Sample query。success=true only successful, success=false only failed, If not passed on, all。"""
    if success is None:
        rows = await token_store.list_samples(limit=limit)
    elif success.lower() == "true":
        rows = await token_store.list_samples(success=True, limit=limit)
    else:
        rows = await token_store.list_samples(success=False, limit=limit)
    # Compatible with front-end fields
    out = []
    for r in rows:
        out.append({
            "ts": r.get("ts", ""), "email": r.get("email", ""),
            "success": bool(r.get("success", 0)),
            "reason_code": r.get("reason_code", ""),
            "reason_text": r.get("reason_text", ""),
            "paypal_approve_url": r.get("paypal_approve_url", ""),
            "amount_due": r.get("amount_due", 0),
            "currency": r.get("currency", ""),
            "country": r.get("country", ""),
            "stage_reached": r.get("stage_reached", ""),
            "chain_id": r.get("chain_id", ""),
            "actual_country": r.get("actual_country", ""),
            "requested_country": r.get("requested_country", ""),
            "exit_ip": r.get("exit_ip", ""),
            "geo_confidence": r.get("geo_confidence", 0.0),
        })
    return {"ok": True, "samples": out, "total": len(out)}


@router.get("/formulas")
async def formulas():
    """Success recipe：Generate recommended combinations based on segmented country strategies。"""
    formulas = [
        {"name": "US-main chain (USD $0)",
         "checkout": "US", "init": "US", "provider": "US",
         "approve": "US", "poll": "US", "resolve": "US", "success_count": 0},
        {"name": "JP-approve stable chain",
         "checkout": "US", "init": "AU", "provider": "US",
         "approve": "JP", "poll": "JP", "resolve": "JP", "success_count": 0},
        {"name": "HK-transit chain",
         "checkout": "GB", "init": "US", "provider": "US",
         "approve": "HK", "poll": "US", "resolve": "US", "success_count": 0},
    ]
    return {"ok": True, "formulas": formulas}



