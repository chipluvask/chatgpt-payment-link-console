"""concurrent scheduler：AsyncChainOrchestrator + WebSocket Connection management + statistical aggregation。

Concurrency model：
- asyncio event loop + ThreadPoolExecutor(max_workers=thread_pool_size) Package curl_cffi Synchronous call
- AsyncChainOrchestrator: Semaphore Current limiting + asyncio.gather Batch execution
- Intra-link parallelism: approve+poll Can be parallelized, PMPrecomputed on creation confirm body (exist chain.py Inside)

WebSocket: ConnectionManager Manage active connections，broadcast Push real-time link status。
statistics: success/failure/byCountry/failByCountry/reasons/stageMatrix real-time aggregation。
"""
from __future__ import annotations

import asyncio
import json
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from .chain import AsyncChain, ChainResult, DISPLAY_STAGES
from .config import settings
from .token_store import token_store


# =============================================================================
# WebSocket connection manager
# =============================================================================
class ConnectionManager:
    """manage WebSocket connect，Support broadcast events。"""

    def __init__(self) -> None:
        self.active: list[asyncio.Queue] = []

    async def connect(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=2048)
        self.active.append(q)
        return q

    def disconnect(self, q: asyncio.Queue) -> None:
        if q in self.active:
            self.active.remove(q)

    async def broadcast(self, event: dict[str, Any]) -> None:
        """Broadcast events to all connections。Discard when queue is full（avoid blocking）。"""
        dead: list[asyncio.Queue] = []
        for q in self.active:
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                dead.append(q)
        for q in dead:
            self.disconnect(q)

    async def send(self, q: asyncio.Queue, event: dict[str, Any]) -> None:
        try:
            q.put_nowait(event)
        except asyncio.QueueFull:
            pass


# =============================================================================
# Global statistics aggregation
# =============================================================================
class StatsAggregator:
    """Cumulative statistics：success/failure/byCountry/reasons/stageMatrix。"""

    def __init__(self) -> None:
        self.success: int = 0
        self.failure: int = 0
        self.byCountry: dict[str, int] = {}
        self.failByCountry: dict[str, int] = {}
        self.reasons: dict[str, int] = {}
        self.stageMatrix: dict[str, dict[str, dict[str, int]]] = {
            s: {} for s in DISPLAY_STAGES
        }
        self.latencies: list[float] = []

    def record_success(self, country: str, elapsed: float) -> None:
        self.success += 1
        self.byCountry[country] = self.byCountry.get(country, 0) + 1
        if elapsed > 0:
            self.latencies.append(round(elapsed, 2))
            if len(self.latencies) > 1000:
                self.latencies = self.latencies[-500:]

    def record_failure(self, country: str, reason_code: str) -> None:
        self.failure += 1
        if country:
            self.failByCountry[country] = self.failByCountry.get(country, 0) + 1
        if reason_code:
            self.reasons[reason_code] = self.reasons.get(reason_code, 0) + 1

    def record_stage(self, stage: str, country: str, ok: bool) -> None:
        if stage not in self.stageMatrix:
            self.stageMatrix[stage] = {}
        cell = self.stageMatrix[stage].setdefault(country, {"ok": 0, "fail": 0})
        cell["ok" if ok else "fail"] += 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "failure": self.failure,
            "byCountry": self.byCountry,
            "failByCountry": self.failByCountry,
            "reasons": self.reasons,
            "stageMatrix": self.stageMatrix,
        }

    def reset(self) -> None:
        self.success = 0
        self.failure = 0
        self.byCountry = {}
        self.failByCountry = {}
        self.reasons = {}
        self.stageMatrix = {s: {} for s in DISPLAY_STAGES}
        self.latencies = []


# =============================================================================
# concurrent scheduler
# =============================================================================
class AsyncChainOrchestrator:
    """Concurrent link scheduler。

    - Semaphore Current limiting max_concurrent
    - asyncio.gather Batch execution (No interruption on failure)
    - real time push chain_start/stage_*/chain_success/chain_failure/batch_progress
    """

    def __init__(self, conn_mgr: ConnectionManager) -> None:
        self.conn_mgr = conn_mgr
        self.stats = StatsAggregator()
        self.semaphore = asyncio.Semaphore(settings.max_concurrent_chains)
        self.executor = ThreadPoolExecutor(max_workers=settings.thread_pool_size)
        self.active_chains: dict[str, AsyncChain] = {}
        self.chain_states: dict[str, dict[str, Any]] = {}
        self._batch_running = False
        self._batch_stop = False
        self._batch_task: asyncio.Task | None = None
        self._batch_start_time: float = 0.0
        self._batch_total = 0
        self._batch_done = 0

    # ------------------------------------------------------------------
    # event broadcast
    # ------------------------------------------------------------------
    async def emit(self, event: dict[str, Any]) -> None:
        """link events -> broadcast + Update internal status。"""
        # renew chain_states
        cid = event.get("chain_id", "")
        etype = event.get("type", "")
        if etype == "chain_start" and cid:
            self.chain_states[cid] = {
                "stages": {}, "status": "running",
                "email": event.get("email", ""),
                "token_sub": event.get("token_sub", ""),
                "startTime": time.time() * 1000,
                "attempt": event.get("attempt", 1),
            }
        elif etype in ("stage_try", "stage_ok", "stage_fail") and cid:
            cs = self.chain_states.get(cid)
            if cs:
                stage = event.get("stage", "")
                state = {"run": "run", "ok": "ok", "fail": "fail"}.get(etype.replace("stage_", ""), "")
                if state:
                    cs["stages"][stage] = {
                        "state": state,
                        "country": event.get("country", ""),
                        "tryN": event.get("try_n", 1),
                        "maxTry": event.get("max_try", 3),
                    }
        elif etype == "chain_success" and cid:
            cs = self.chain_states.get(cid)
            if cs:
                cs["status"] = "success"
                cs["url"] = event.get("paypal_approve_url", "")
                # Freezing takes time: The timer will no longer accumulate after the terminal state
                cs["endTime"] = time.time() * 1000
                cs["elapsed"] = round(float(event.get("elapsed") or 0) or
                                     (cs["endTime"] - cs.get("startTime", cs["endTime"])) / 1000, 2)
            self.stats.record_success(event.get("country", ""), event.get("elapsed", 0))
        elif etype == "chain_failure" and cid:
            cs = self.chain_states.get(cid)
            if cs:
                cs["status"] = "failed"
                cs["reason"] = event.get("reason_code", "")
                cs["endTime"] = time.time() * 1000
                cs["elapsed"] = round((cs["endTime"] - cs.get("startTime", cs["endTime"])) / 1000, 2)
            self.stats.record_failure(event.get("country", ""), event.get("reason_code", ""))

        # stage matrix record
        if etype == "stage_ok" and cid:
            self.stats.record_stage(event.get("stage", ""), event.get("country", ""), True)
        elif etype == "stage_fail" and cid:
            self.stats.record_stage(event.get("stage", ""), event.get("country", ""), False)

        await self.conn_mgr.broadcast(event)

    # ------------------------------------------------------------------
    # Single link execution (Contains attempts Try again)
    # ------------------------------------------------------------------
    async def run_chain(self, token: dict[str, Any], options: dict[str, Any]) -> ChainResult:
        attempts = int(options.get("attempts", 8))
        chain_id = uuid.uuid4().hex[:8]
        result = ChainResult()
        async with self.semaphore:
            for attempt in range(1, attempts + 1):
                if self._batch_stop:
                    result.reason_code = "network_error"
                    result.reason_text = "Batch task has stopped"
                    break
                chain = AsyncChain(chain_id, token, attempt, options, self.emit, self.executor)
                self.active_chains[chain_id] = chain
                try:
                    result = await chain.execute()
                except asyncio.CancelledError:
                    result.reason_code = "network_error"
                    result.reason_text = "link canceled"
                    break
                finally:
                    self.active_chains.pop(chain_id, None)
                if result.success:
                    break
                # After failure, cool down briefly and try again.
                if attempt < attempts and not self._batch_stop:
                    await asyncio.sleep(0.5)
        # renew token state
        try:
            await token_store.set_status(token["id"], "success" if result.success else "failed")
            await self.conn_mgr.broadcast({
                "type": "token_status", "token_id": token["id"],
                "status": "success" if result.success else "failed",
            })
        except Exception:
            pass
        # record sample
        try:
            await token_store.add_sample(
                success=result.success, email=result.email, chain_id=chain_id,
                reason_code=result.reason_code, reason_text=result.reason_text,
                paypal_url=result.paypal_approve_url, amount_due=result.amount_due,
                currency=result.currency, country=result.country,
                stage_reached=result.stage_reached,
                payload=json.dumps({
                    "pm_authorize_url": result.pm_authorize_url,
                    "stage_geo": result.stage_geo,
                }, ensure_ascii=False),
                actual_country=result.actual_country,
                requested_country=result.requested_country,
                exit_ip=result.exit_ip,
                geo_confidence=result.geo_confidence,
            )
        except Exception:
            pass
        # Successfully put into storage (Mark output by branch channel, branch isolation)
        if result.success:
            try:
                branch_name = str(options.get("branch") or "paypal")
                channel = settings.branch(branch_name).channel
                # Authorization segment countries must follow checkout exit IP nation (result.country),
                # rather than billing countries (billing_country) — PayPal form country/fingerprint/The receiving code is aligned according to the exporting country.
                exit_cc = str(result.country or result.actual_country or "").upper()
                await token_store.add_success(
                    email=result.email, ba=result.ba_token,
                    paypal_url=result.paypal_approve_url, pm_url=result.pm_authorize_url,
                    amount_due=result.amount_due, currency=result.currency,
                    country=result.billing_country or exit_cc,
                    channel=channel,
                    exit_country=exit_cc,
                )
                # paypal channel: BA Automatically enter the authorization queue, And broadcast notification to the front end to refresh
                if channel == "paypal" and result.paypal_approve_url:
                    from core.ba_queue import import_from_url
                    imported = import_from_url(
                        result.paypal_approve_url,
                        email=result.email,
                        country=exit_cc or result.billing_country,
                        chain_id=chain_id,
                    )
                    if imported:
                        await self.conn_mgr.broadcast({
                            "type": "ba_imported",
                            "ba_token": result.ba_token,
                            "email": result.email,
                        })
            except Exception:
                pass
        return result

    # ------------------------------------------------------------------
    # Batch execution
    # ------------------------------------------------------------------
    async def run_batch(self, token_ids: list[str], options: dict[str, Any]) -> dict[str, Any]:
        if self._batch_running:
            return {"ok": False, "error": "A batch task is already running"}
        # load tokens
        tokens: list[dict[str, Any]] = []
        for tid in token_ids:
            t = await token_store.get_token(tid)
            if t:
                tokens.append(t)
        if not tokens:
            return {"ok": False, "error": "Not found valid Token"}
        self._batch_running = True
        self._batch_stop = False
        self._batch_total = len(tokens)
        self._batch_done = 0
        self._batch_start_time = time.time()
        self.chain_states = {}
        # Notification frontend: A new round begins, Clear remaining progress from the previous round
        await self.conn_mgr.broadcast({
            "type": "batch_start", "total": len(tokens), "running": True,
        })
        # Concurrency upper limit default = Number of selected items (No current limit)，Only if passed explicitly max_concurrent time limit
        max_conc = int(options.get("max_concurrent") or len(tokens) or 1)
        self.semaphore = asyncio.Semaphore(max(1, max_conc))

        async def _run_all() -> None:
            success = 0
            failure = 0

            async def _one(t: dict[str, Any]) -> None:
                nonlocal success, failure
                try:
                    await token_store.set_status(t["id"], "running")
                    await self.conn_mgr.broadcast(
                        {"type": "token_status", "token_id": t["id"], "status": "running"})
                    r = await self.run_chain(t, options)
                    if r.success:
                        success += 1
                    else:
                        failure += 1
                except Exception:
                    failure += 1
                finally:
                    self._batch_done += 1
                    await self.conn_mgr.broadcast({
                        "type": "batch_progress",
                        "done": self._batch_done, "total": self._batch_total,
                        "success": success, "failure": failure,
                    })
                    await self.conn_mgr.broadcast({"type": "stats_update", "stats": self.stats.to_dict()})

            # The semaphore is already present run_chain Inside，Directly here gather
            tasks = [asyncio.create_task(_one(t)) for t in tokens]
            await asyncio.gather(*tasks, return_exceptions=True)

            elapsed = time.time() - self._batch_start_time
            await self.conn_mgr.broadcast({
                "type": "batch_done", "success": success, "failure": failure,
                "elapsed": round(elapsed, 2),
            })
            self._batch_running = False

        self._batch_task = asyncio.create_task(_run_all())
        return {"ok": True, "total": len(tokens), "max_concurrent": max_conc}

    async def stop_batch(self, chain_ids: list[str] | None = None) -> dict[str, Any]:
        self._batch_stop = True
        if chain_ids:
            for cid in chain_ids:
                ch = self.active_chains.get(cid)
                if ch:
                    ch.cancel()
        else:
            for ch in list(self.active_chains.values()):
                ch.cancel()
        # When stopping, the batch status must be reset and the front end notified, otherwise _run_all After being cancelled
        # The closing code is not executed, _batch_running permanent True (front end"stop all"Always red/Can be ordered)
        self._batch_running = False
        if self._batch_task:
            self._batch_task.cancel()
            try:
                await self._batch_task
            except asyncio.CancelledError:
                pass
            except Exception:
                pass
        await self.conn_mgr.broadcast({
            "type": "batch_done", "success": 0, "failure": 0,
            "elapsed": round(time.time() - self._batch_start_time, 2),
        })
        return {"ok": True, "stopped": len(self.active_chains)}

    # ------------------------------------------------------------------
    # Status query
    # ------------------------------------------------------------------
    def status(self) -> dict[str, Any]:
        active = sum(1 for c in self.chain_states.values() if c.get("status") == "running")
        success = sum(1 for c in self.chain_states.values() if c.get("status") == "success")
        failed = sum(1 for c in self.chain_states.values() if c.get("status") == "failed")
        queued = max(0, self._batch_total - self._batch_done - active) if self._batch_running else 0
        return {
            "running": self._batch_running,
            "active": active,
            "queued": queued,
            "success": success,
            "failure": failed,
            "total": self._batch_total,
            "done": self._batch_done,
            "chains": [
                {"chain_id": cid, **c} for cid, c in list(self.chain_states.items())[:50]
            ],
        }

    def sync_payload(self) -> dict[str, Any]:
        """WebSocket sync event payload。"""
        return {
            "type": "sync",
            "chains": self.chain_states,
            "stats": self.stats.to_dict(),
            "running": self._batch_running,
            "latencies": self.stats.latencies[-100:],
        }

    async def shutdown(self) -> None:
        self._batch_stop = True
        for ch in list(self.active_chains.values()):
            ch.cancel()
        if self._batch_task:
            self._batch_task.cancel()
            try:
                await self._batch_task
            except asyncio.CancelledError:
                pass
        self.executor.shutdown(wait=False)
