"""Min-Implant v2 backend entry：FastAPI (ASGI) + WebSocket + Static file service。

start up:
    cd backend
    python -m uvicorn app:app --host 0.0.0.0 --port 8770
or:
    python app.py

Function:
- REST API (tokens / chain / proxy / stats / config / billing / paypal)
- WebSocket /ws Real-time push link status
- Static file service (web/dist — frontend/ React Panel building products)
- Initialize on startup SQLite / proxy pool / scheduler
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

# Make sure the current directory is in sys.path (python app.py When running directly)
_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from api.chain import router as chain_router
from api.config import router as config_router
from api.proxy import router as proxy_router
from api.stats import router as stats_router
from api.tokens import router as tokens_router
from api.paypal import router as paypal_router
from api.directpay import router as directpay_router
from api.register import router as register_router
from api.deps import runtime
from core.config import settings
from core.orchestrator import AsyncChainOrchestrator, ConnectionManager
from core.proxy_pool import proxy_pool
from core.token_store import token_store

def _parse_probe(raw):
    try:
        import json
        d = json.loads(raw or '{}')
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def _split_tags(raw):
    return [x for x in (str(raw or '').split(',')) if x.strip()]



# =============================================================================
# life cycle
# =============================================================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    # ---- start up ----
    # 1. Token storage
    await token_store.init()
    await token_store.reset_running()
    # 1b. BA authorization queue: Clear out the zombies left over from the last process running (Task dies with old process,
    #     Queue status has no chance to be written back, The front end will always display"Authorizing"; There are no old tasks in the new process)
    try:
        from core.ba_queue import mark_stale as _ba_mark_stale
        _stale = _ba_mark_stale(older_than_ms=0)
        if _stale:
            print(f"[min-implant] BA queue cleaning zombies running: {_stale} strip")
    except Exception:
        pass
    # 2. WebSocket Connection management + scheduler
    conn_mgr = ConnectionManager()
    orchestrator = AsyncChainOrchestrator(conn_mgr)
    runtime.conn_mgr = conn_mgr
    runtime.orchestrator = orchestrator
    runtime.started = True
    # 3. Agent pool health check loop
    await proxy_pool.start_health_loop()
    # 3b. Registration function: api798 Email extraction channel (The card secret file is injected through environment variables, Don't leave the warehouse)
    try:
        from reg import engine as _reg_engine
        from reg.channel_api798 import load_mailboxes, build_channel
        _kml = os.environ.get("REG_API798_MAILBOXES", "").strip()
        if _kml and os.path.isfile(_kml):
            _mbs = load_mailboxes(_kml)
            if _mbs:
                _reg_engine.register_email_channel("api798", build_channel(_mbs))
                print(f"[min-implant] Registration channel api798 Loaded {len(_mbs)} mailbox")
    except Exception as _e:
        print(f"[min-implant] Registration channel api798 Loading failed: {_e}")
    # 4. Initial health check
    try:
        nodes = await proxy_pool.health_check()
        await conn_mgr.broadcast({"type": "proxy_health", "nodes": nodes})
    except Exception:
        pass
    print(f"[min-implant] Backend started -> http://{settings.host}:{settings.port}")
    print(f"[min-implant] link mode: {settings.chain_mode} | curl_cffi: {_has_curl()}")
    print(f"[min-implant] static directory: {settings.web_dir}")
    yield
    # ---- closure ----
    await proxy_pool.stop_health_loop()
    await orchestrator.shutdown()
    await token_store.close()
    print("[min-implant] Backend is down")


def _has_curl() -> bool:
    try:
        from core.chain import _HAS_CURL  # type: ignore
        return _HAS_CURL
    except Exception:
        return False


# =============================================================================
# FastAPI application
# =============================================================================
app = FastAPI(
    title="Min-Implant v2",
    description="$0 ChatGPT Plus -> PayPal BA Approve Chain lifting engine",
    version="2.0.0",
    lifespan=lifespan,
)

# CORS (All are allowed during the development period)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# mount REST routing
app.include_router(tokens_router)
app.include_router(chain_router)
app.include_router(proxy_router)
app.include_router(stats_router)
app.include_router(config_router)
app.include_router(paypal_router)
app.include_router(directpay_router)
app.include_router(register_router)


# =============================================================================
# Static file service
# =============================================================================
_web_dir = settings.web_dir
_dist_dir = _web_dir / "dist"

# 【abandoned】Native JS Management desk (web/index.html + web/static/*) Already at 2026-08-15 Remove。
# The old front-end is an early handwritten page, has been frontend/ (React+Vite) completely replace;
# Currently the only frontend = frontend Source code → vite build → web/dist, Served directly from the backend。
# If you need to restore the old version, Can git checkout history commit retrieve web/index.html and web/static/,
# and remount here "/static"。
# _static_dir = _web_dir / "static"
# if _static_dir.exists():
#     app.mount("/static", StaticFiles(directory=str(_static_dir)), name="static")

if _dist_dir.exists():
    # Servo vite Build product (web/dist): Currently the only frontend
    app.mount("/assets", StaticFiles(directory=str(_dist_dir / "assets")), name="dist-assets")


@app.get("/")
async def index():
    """Return to front-end homepage (vite Build product web/dist, Currently the only frontend)。"""
    dist_index = _dist_dir / "index.html"
    if dist_index.exists():
        resp = FileResponse(str(dist_index))
        resp.headers["Cache-Control"] = "no-cache"
        return resp
    return JSONResponse({"ok": True, "service": "min-implant-v2", "version": "2.0.0",
                         "message": "Frontend not found，Please execute first frontend: npm run build (The product is output to ../web/dist)"})


# =============================================================================
# WebSocket
# =============================================================================
@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    conn_mgr = runtime.conn_mgr
    if not conn_mgr:
        await ws.close(code=1011, reason="Engine not ready")
        return
    q = await conn_mgr.connect()
    # Push initial sync
    try:
        orchestrator = runtime.orchestrator
        sync = orchestrator.sync_payload() if orchestrator else {"type": "sync"}
        # Comes with tokens / nodes
        tokens = await token_store.list_tokens()
        sync["tokens"] = [
            {"id": t["id"], "email": t.get("email", ""), "sub": t.get("sub", ""),
             "account_id": t.get("account_id", ""), "plan_type": t.get("plan_type", ""),
             "register_method": t.get("register_method", "email"),
             "session_type": t.get("session_type", ""),
             "probe": _parse_probe(t.get("probe", "")),
             "tags": _split_tags(t.get("tags", "")),
             "expires_at": t.get("expires_at", ""), "status": t.get("status", "idle"),
             "source": t.get("source", "stripe")}
            for t in tokens
        ]
        sync["nodes"] = proxy_pool.list_nodes()
        await ws.send_text(json.dumps(sync, ensure_ascii=False, default=str))
    except Exception:
        pass

    # Send tasks in the background：Push queue events to the client
    async def _sender():
        try:
            while True:
                event = await q.get()
                await ws.send_text(json.dumps(event, ensure_ascii=False, default=str))
        except WebSocketDisconnect:
            pass
        except Exception:
            pass

    sender_task = asyncio.create_task(_sender())
    try:
        # receive loop：Handle client messages (sync_request wait)
        while True:
            raw = await ws.receive_text()
            try:
                msg = json.loads(raw)
            except Exception:
                continue
            mtype = msg.get("type")
            if mtype == "sync_request":
                orchestrator = runtime.orchestrator
                sync = orchestrator.sync_payload() if orchestrator else {"type": "sync"}
                tokens = await token_store.list_tokens()
                sync["tokens"] = [
                    {"id": t["id"], "email": t.get("email", ""), "sub": t.get("sub", ""),
                     "account_id": t.get("account_id", ""), "plan_type": t.get("plan_type", ""),
                     "status": t.get("status", "idle"),
                     "register_method": t.get("register_method", "email"),
                     "session_type": t.get("session_type", ""),
                     "probe": _parse_probe(t.get("probe", "")),
                     "tags": _split_tags(t.get("tags", "")),
                     "expires_at": t.get("expires_at", ""),
                     "source": t.get("source", "stripe")}
                    for t in tokens
                ]
                sync["nodes"] = proxy_pool.list_nodes()
                await ws.send_text(json.dumps(sync, ensure_ascii=False, default=str))
            elif mtype == "ping":
                await ws.send_text(json.dumps({"type": "pong"}))
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        sender_task.cancel()
        conn_mgr.disconnect(q)
        try:
            await sender_task
        except asyncio.CancelledError:
            pass


# =============================================================================
# health check endpoint
# =============================================================================
@app.get("/api/health")
async def health():
    return {
        "ok": True, "service": "min-implant-v2", "version": "2.0.0",
        "chain_mode": settings.chain_mode,
        "curl_cffi": _has_curl(),
        "web_dir": str(settings.web_dir),
        "web_exists": settings.web_dir.exists(),
    }


# =============================================================================
# Run directly
# =============================================================================
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app:app",
        host=settings.host,
        port=settings.port,
        reload=False,
        log_level=settings.raw.get("logging", {}).get("level", "info").lower(),
    )

