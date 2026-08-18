"""Agent management routing。

REST:
- GET  /api/proxy/nodes        - Agent node list
- GET  /api/proxy/health       - Agency Health
- POST /api/proxy/parse        - parse subscription
- POST /api/proxy/fetch-sub    - Pull subscription
- POST /api/proxy/start        - Start node
- POST /api/proxy/stop         - Stop node
- POST /api/proxy/start-all    - start all
- POST /api/proxy/stop-all     - stop all
- GET  /api/proxy/711/status   - 711 complete state (Read only and no modification allowed)
- POST /api/proxy/711/smoke    - 711 smoke test (read only)
- GET  /api/proxy/qg/pools     - QG Tunnel pool list
"""
from __future__ import annotations

from fastapi import APIRouter

from core.proxy_pool import proxy_pool
from .deps import runtime

router = APIRouter(prefix="/api/proxy", tags=["proxy"])


@router.get("/nodes")
async def list_nodes():
    return {"ok": True, "nodes": proxy_pool.list_nodes()}


@router.get("/health")
async def proxy_health():
    nodes = await proxy_pool.health_check()
    # broadcast health status
    if runtime.conn_mgr:
        await runtime.conn_mgr.broadcast({"type": "proxy_health", "nodes": nodes})
    return {"ok": True, "nodes": nodes}


@router.post("/parse")
async def parse_subscription(body: dict):
    raw = body.get("raw", "")
    if not raw.strip():
        return {"ok": False, "count": 0, "error": "raw is empty"}
    count = proxy_pool.parse_subscription(raw)
    nodes = proxy_pool.list_nodes()
    if runtime.conn_mgr:
        await runtime.conn_mgr.broadcast({"type": "proxy_health", "nodes": nodes})
    return {"ok": True, "count": count, "nodes": nodes}


@router.post("/fetch-sub")
async def fetch_subscription(body: dict):
    """Pull subscription link content。"""
    url = body.get("url", "")
    if not url:
        return {"ok": False, "error": "Lack url", "raw": "", "length": 0}
    # Try using curl_cffi pull；Failure return prompt
    try:
        from curl_cffi import requests as curl  # type: ignore
        r = curl.get(url, impersonate="chrome", timeout=15)
        raw = r.text or ""
        return {"ok": True, "raw": raw, "length": len(raw)}
    except Exception as e:
        return {"ok": False, "error": f"Pull failed: {e}", "raw": "", "length": 0}


@router.post("/start")
async def start_node(body: dict):
    name = body.get("name", "")
    ok = proxy_pool.start_node(name)
    if ok and runtime.conn_mgr:
        await runtime.conn_mgr.broadcast({"type": "node_started", "name": name})
    return {"ok": ok, "nodes": proxy_pool.list_nodes()}


@router.post("/stop")
async def stop_node(body: dict):
    name = body.get("name", "")
    ok = proxy_pool.stop_node(name)
    if ok and runtime.conn_mgr:
        await runtime.conn_mgr.broadcast({"type": "node_stopped", "name": name})
    return {"ok": ok, "nodes": proxy_pool.list_nodes()}


@router.post("/start-all")
async def start_all():
    cnt = proxy_pool.start_all()
    nodes = proxy_pool.list_nodes()
    if runtime.conn_mgr:
        await runtime.conn_mgr.broadcast({"type": "proxy_health", "nodes": nodes})
    return {"ok": True, "started": cnt, "nodes": nodes}


@router.post("/stop-all")
async def stop_all():
    cnt = proxy_pool.stop_all()
    nodes = proxy_pool.list_nodes()
    if runtime.conn_mgr:
        await runtime.conn_mgr.broadcast({"type": "proxy_health", "nodes": nodes})
    return {"ok": True, "stopped": cnt, "nodes": nodes}


@router.get("/711/status")
async def proxy_711_status():
    """711 Agent pool complete status (Read only and no modification allowed)。"""
    return {"ok": True, **proxy_pool.proxy711.status()}


@router.post("/711/smoke")
async def proxy_711_smoke():
    """manual trigger 711 smoke test (read only，Do not modify configuration)。"""
    result = await proxy_pool.proxy711.smoke_test()
    return {"ok": True, "result": result}


@router.get("/qg/pools")
async def qg_pools():
    return {"ok": True, "pools": proxy_pool.qg_pools_status()}
