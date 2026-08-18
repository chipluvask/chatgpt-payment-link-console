import { useEffect, useMemo, useState } from "react";
import { useStore } from "../store/useStore";
import { api } from "../api/client";
import { STAGE_ORDER, STAGE_SHORT, STAGE_CN } from "../types";
import { ChainTable } from "../components/chain/ChainTable";
import { SuccessSheet } from "../components/chain/SuccessSheet";

interface SheetState {
  url: string;
  meta: string;
}

export function ChainsView() {
  const chainStates = useStore((s) => s.chainStates);
  const batchTotal = useStore((s) => s.batchTotal);
  const batchDone = useStore((s) => s.batchDone);
  const batchRunning = useStore((s) => s.batchRunning);
  const pushLog = useStore((s) => s.pushLog);

  const [, setTick] = useState(0);
  useEffect(() => {
    const timer = setInterval(() => setTick((n) => n + 1), 1000);
    return () => clearInterval(timer);
  }, []);

  const [busy, setBusy] = useState(false);
  const [sheet, setSheet] = useState<SheetState | null>(null);

  const chainList = useMemo(
    () => Object.entries(chainStates).map(([id, cs]) => ({ id, cs })),
    [chainStates]
  );

  const activeCount = chainList.filter(({ cs }) => cs.status === "running").length;
  const successCount = chainList.filter(({ cs }) => cs.status === "success").length;
  const failedCount = chainList.filter(({ cs }) => cs.status === "failed").length;
  const queuedCount = Math.max(0, batchTotal - batchDone - activeCount);
  /** When there is a running link or batches queued, Stop button enters available active state */
  const hasActivity = activeCount > 0 || batchRunning || queuedCount > 0;

  const handleStop = async () => {
    setBusy(true);
    try {
      await api("/api/chain/stop", "POST", {});
      pushLog("Stop signal sent", "info");
    } catch (e) {
      pushLog(`Stop failed: ${e}`, "err");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h2 className="page-title">Link monitoring</h2>
          <p className="page-sub">per link 7 Segment Pipeline Progress、Exporting countries and time taken</p>
        </div>
        <div className="page-actions">
          {hasActivity ? (
            <button
              className="btn btn-danger btn-stop-live"
              onClick={handleStop}
              disabled={busy}
              title={`stop all: ${activeCount} Running, ${queuedCount} Queuing up`}
            >
              {busy ? "Sending…" : `■ stop all (active ${activeCount + queuedCount})`}
            </button>
          ) : (
            <button className="btn btn-ghost" disabled title="There are currently no links running">
              stop all
            </button>
          )}
        </div>
      </div>

      <div className="inline-fields" style={{ marginBottom: 14 }}>
        <span className="badge badge-info">active {activeCount}</span>
        <span className="badge badge-success">success {successCount}</span>
        <span className="badge badge-danger">fail {failedCount}</span>
        <span className="badge badge-muted">queue {queuedCount}</span>
      </div>

      {chainList.length === 0 ? (
        <div className="card">
          <div className="empty">
            <div className="empty-icon">🔗</div>
            <div className="empty-title">Link not started yet</div>
            <div className="empty-hint">Go to each link page to select Token After starting the chain</div>
          </div>
        </div>
      ) : (
        <ChainTable chainList={chainList} onClick={(url, meta) => setSheet({ url, meta })} />
      )}

      {sheet && (
        <SuccessSheet
          url={sheet.url}
          meta={sheet.meta}
          onClose={() => setSheet(null)}
        />
      )}
    </div>
  );
}
