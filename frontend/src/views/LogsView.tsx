import { useEffect, useMemo, useRef, useState } from "react";
import { useStore } from "../store/useStore";
import type { LogEntry } from "../types";

const TAG_MAP: Record<LogEntry["level"], string> = {
  ok: "OK",
  info: "INFO",
  warn: "WARN",
  err: "ERR",
};

const LEVEL_OPTIONS: { value: string; label: string }[] = [
  { value: "all", label: "All levels" },
  { value: "ok", label: "OK" },
  { value: "info", label: "INFO" },
  { value: "warn", label: "WARN" },
  { value: "err", label: "ERR" },
];

const MAX_DISPLAY = 200;

export function LogsView() {
  const logLines = useStore((s) => s.logLines);
  const clearLog = useStore((s) => s.clearLog);

  const [levelFilter, setLevelFilter] = useState<string>("all");
  const [chainFilter, setChainFilter] = useState<string>("all");

  const streamRef = useRef<HTMLDivElement>(null);

  const chainIds = useMemo(() => {
    const seen = new Set<string>();
    logLines.forEach((l) => {
      if (l.chainId) seen.add(l.chainId);
    });
    return Array.from(seen);
  }, [logLines]);

  const filtered = useMemo(() => {
    return logLines.filter((l) => {
      if (levelFilter !== "all" && l.level !== levelFilter) return false;
      if (chainFilter !== "all" && l.chainId !== chainFilter) return false;
      return true;
    });
  }, [logLines, levelFilter, chainFilter]);

  const display = useMemo(
    () => filtered.slice(-MAX_DISPLAY),
    [filtered]
  );

  useEffect(() => {
    if (streamRef.current) {
      streamRef.current.scrollTop = streamRef.current.scrollHeight;
    }
  }, [display]);

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h2 className="page-title">real time log</h2>
          <p className="page-sub">System operation log stream（recent {MAX_DISPLAY} strip）</p>
        </div>
        <div className="page-actions">
          <select
            className="select"
            style={{ width: 120 }}
            value={levelFilter}
            onChange={(e) => setLevelFilter(e.target.value)}
          >
            {LEVEL_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
          <select
            className="select"
            style={{ width: 120 }}
            value={chainFilter}
            onChange={(e) => setChainFilter(e.target.value)}
          >
            <option value="all">All links</option>
            {chainIds.map((id) => (
              <option key={id} value={id}>
                {id.slice(0, 8)}
              </option>
            ))}
          </select>
          <button className="btn btn-ghost" onClick={clearLog}>
            Clear
          </button>
        </div>
      </div>

      <div className="log-panel">
        <div className="log-body" ref={streamRef} style={{ maxHeight: "calc(100vh - 220px)" }}>
          {display.length === 0 ? (
            <div className="empty">
              <div className="empty-icon">📡</div>
              <div className="empty-title">No logs yet</div>
              <div className="empty-hint">After the link is started, the log will be displayed here in real time.</div>
            </div>
          ) : (
            display.map((l, i) => (
              <div className={`log-line ${l.level}`} key={i}>
                <span className="log-ts">{l.ts}</span>
                {l.chainId && <span className="log-chain">{l.chainId.slice(0, 6)}</span>}
                <span className="log-msg">{l.msg}</span>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
