import { useMemo, useState } from "react";
import { useStore } from "../store/useStore";
import { api } from "../api/client";
import { STAGE_ORDER } from "../types";

const MAX_CONCURRENCY = 5;

export function OverviewView() {
  const chainStates = useStore((s) => s.chainStates);
  const stats = useStore((s) => s.stats);
  const latencies = useStore((s) => s.latencies);
  const tokens = useStore((s) => s.tokens);
  const logLines = useStore((s) => s.logLines);
  const selectedTokenIds = useStore((s) => s.selectedTokenIds);
  const pushLog = useStore((s) => s.pushLog);
  const setView = useStore((s) => s.setView);
  const batchRunning = useStore((s) => s.batchRunning);
  const setBatchRunning = useStore((s) => s.setBatchRunning);
  const [busy, setBusy] = useState(false);

  const chainList = useMemo(
    () => Object.entries(chainStates).map(([id, c]) => ({ id, ...c })),
    [chainStates]
  );

  const activeCount = useMemo(
    () => chainList.filter((c) => c.status === "running").length,
    [chainList]
  );

  const successCount = stats.success;
  const failedCount = stats.failure;
  const totalCount = successCount + failedCount;
  const successRate = totalCount > 0 ? (successCount / totalCount) * 100 : 0;

  const p95 = useMemo(() => {
    if (latencies.length === 0) return 0;
    const sorted = [...latencies].sort((a, b) => a - b);
    const idx = Math.min(sorted.length - 1, Math.floor(sorted.length * 0.95));
    return sorted[idx];
  }, [latencies]);

  const topChains = useMemo(() => {
    return [...chainList]
      .sort((a, b) => {
        const aRunning = a.status === "running" ? 1 : 0;
        const bRunning = b.status === "running" ? 1 : 0;
        if (aRunning !== bRunning) return bRunning - aRunning;
        return b.startTime - a.startTime;
      })
      .slice(0, 8);
  }, [chainList]);

  const recentLogs = useMemo(() => logLines.slice(-15), [logLines]);

  const handleBatchStart = async () => {
    const ids = Array.from(selectedTokenIds);
    if (ids.length === 0) {
      pushLog("No token selected，Please go to the token page to select the token you want to run", "warn");
      setView("tokens");
      return;
    }
    setBusy(true);
    try {
      await api("/api/chain/batch", "POST", { token_ids: ids, branch: useStore.getState().activeBranch });
      pushLog(`Batch start ${ids.length} tokens`, "ok");
      setBatchRunning(true);
    } catch (e) {
      pushLog(`Batch startup failed: ${e}`, "err");
    } finally {
      setBusy(false);
    }
  };

  const handleStopAll = async () => {
    setBusy(true);
    try {
      await api("/api/chain/stop", "POST", {});
      pushLog("Stop all command sent", "info");
      setBatchRunning(false);
    } catch (e) {
      pushLog(`Stop failed: ${e}`, "err");
    } finally {
      setBusy(false);
    }
  };

  const activeRatio =
    MAX_CONCURRENCY > 0 ? (activeCount / MAX_CONCURRENCY) * 100 : 0;

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h2 className="page-title">Overview</h2>
          <p className="page-sub">System status overview and key indicators</p>
        </div>
        <div className="page-actions">
          <button className="btn btn-primary" onClick={handleBatchStart} disabled={busy || batchRunning}>
            Batch start
          </button>
          <button className="btn btn-danger" onClick={handleStopAll} disabled={busy || !batchRunning}>
            stop all
          </button>
        </div>
      </div>

      <div className="grid grid-3" style={{ marginBottom: 16 }}>
        <div className="stat-card">
          <span className="stat-label">active link</span>
          <div className="stat-value">
            {activeCount}
            <span style={{ color: "var(--text-3)", fontSize: 14 }}> / {MAX_CONCURRENCY}</span>
          </div>
          <div className="stat-foot">
            <div className="progress" style={{ flex: 1 }}>
              <div className="progress-bar" style={{ width: `${Math.min(100, activeRatio)}%` }} />
            </div>
          </div>
        </div>
        <div className="stat-card">
          <span className="stat-label">success</span>
          <div className="stat-value" style={{ color: "var(--ok)" }}>{successCount}</div>
          <div className="stat-foot">Cumulative chain withdrawal success</div>
        </div>
        <div className="stat-card">
          <span className="stat-label">fail</span>
          <div className="stat-value" style={{ color: "var(--danger)" }}>{failedCount}</div>
          <div className="stat-foot">Cumulative link failures</div>
        </div>
        <div className="stat-card">
          <span className="stat-label">success rate</span>
          <div className="stat-value">{successRate.toFixed(1)}%</div>
          <div className="stat-sub">
            <span>success <b>{successCount}</b></span>
            <span>fail <b>{failedCount}</b></span>
          </div>
        </div>
        <div className="stat-card">
          <span className="stat-label">P95 Delay</span>
          <div className="stat-value">
            {p95.toFixed(0)}
            <span style={{ color: "var(--text-3)", fontSize: 14 }}> ms</span>
          </div>
          <div className="stat-foot">sample {latencies.length} strip</div>
        </div>
        <div className="stat-card">
          <span className="stat-label">Token number</span>
          <div className="stat-value">{tokens.length}</div>
          <div className="stat-foot">Selected {selectedTokenIds.size}</div>
        </div>
      </div>

      <div className="grid grid-main">
        <div className="card">
          <div className="card-head">
            <span className="card-title">active link</span>
            <button className="btn btn-ghost btn-sm" onClick={() => setView("chains")}>
              View all →
            </button>
          </div>
          {topChains.length === 0 ? (
            <div className="empty">
              <div className="empty-icon">⏳</div>
              <div className="empty-title">No active link yet</div>
              <div className="empty-hint">exist Token After selecting the token in the library, click「Batch start」Start lifting the chain</div>
            </div>
          ) : (
            <div className="mini-chains">
              {topChains.map((c) => (
                <div className="mini-chain" key={c.id}>
                  <span className="mc-id">#{c.id.slice(0, 8)}</span>
                  <span className="mc-email">{c.email || c.tokenSub || "—"}</span>
                  <span className="mini-dots">
                    {STAGE_ORDER.map((stage) => {
                      const sd = c.stages[stage];
                      return (
                        <span
                          className={`mini-dot${sd ? ` ${sd.state}` : ""}`}
                          key={stage}
                          title={stage}
                        />
                      );
                    })}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="card">
          <div className="card-head">
            <span className="card-title">recent events</span>
            <button className="btn btn-ghost btn-sm" onClick={() => setView("logs")}>
              View all →
            </button>
          </div>
          {recentLogs.length === 0 ? (
            <div className="empty">
              <div className="empty-icon">📡</div>
              <div className="empty-title">No logs yet</div>
            </div>
          ) : (
            <div className="mini-log">
              {recentLogs.map((l, i) => (
                <div className={`ml ${l.level}`} key={i}>
                  <span className="ts">{l.ts}</span>
                  <span>{l.msg}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
