import { useEffect, useState, useCallback } from "react";
import { useStore } from "../store/useStore";
import { api } from "../api/client";
import type { ProxyNode } from "../types";

/** 711 Agent pool status (Read only and no modification allowed) */
interface Proxy711Status {
  enabled: boolean;
  healthy: boolean;
  readonly: boolean;
  gateway_host: string;
  gateway_port: number;
  default_user: string;
  relay_host: string;
  relay_port: number;
  clash_addr: string;
  clash_candidates: string[];
  supported_countries: string[];
  active_sessions: number;
  sessions: Array<{
    id: string;
    region: string;
    sess_time: number;
    sticky: boolean;
    age_sec: number;
  }>;
  exit_ip: string;
  chain: string;
  last_check: number;
}

function flag(cc: string): string {
  if (!cc || cc.length !== 2) return "";
  const cp = 0x1f1e6 + (cc.charCodeAt(0) - 65) * 0x100 + (cc.charCodeAt(1) - 65);
  return String.fromCodePoint(cp);
}

export function ProxyView() {
  const nodes = useStore((s) => s.nodes);
  const qgPool = useStore((s) => s.qgPool);
  const pushLog = useStore((s) => s.pushLog);

  const [subUrl, setSubUrl] = useState("");
  const [subRaw, setSubRaw] = useState("");
  const [result, setResult] = useState("");
  const [busy, setBusy] = useState(false);
  const [status711, setStatus711] = useState<Proxy711Status | null>(null);
  const [smokeBusy, setSmokeBusy] = useState(false);
  const [smokeResult, setSmokeResult] = useState("");

  const load711 = useCallback(async () => {
    try {
      const r = await api("/api/proxy/711/status");
      if (r) {
        const { ok, ...rest } = r;
        setStatus711(rest as Proxy711Status);
      }
    } catch {
      setStatus711(null);
    }
  }, []);

  useEffect(() => {
    load711();
  }, [load711]);

  const handleSmoke = async () => {
    setSmokeBusy(true);
    setSmokeResult("Under test...");
    try {
      const r = await api("/api/proxy/711/smoke", "POST");
      if (r?.result) {
        const healthy = r.result.healthy;
        setSmokeResult(healthy ? "✓ Link is normal" : "✗ Link abnormality");
        pushLog(`711 smoke test: ${healthy ? "success" : "fail"}`, healthy ? "ok" : "err");
        await load711();
      } else {
        setSmokeResult("No return");
      }
    } catch (e) {
      setSmokeResult("fail: " + (e as Error).message);
      pushLog("711 Smoke test failed", "err");
    } finally {
      setSmokeBusy(false);
    }
  };

  const handleFetchSub = async () => {
    if (!subUrl.trim()) {
      setResult("Please enter subscription URL");
      return;
    }
    setBusy(true);
    try {
      const r = await api("/api/proxy/fetch-sub", "POST", { url: subUrl });
      if (r && typeof r.raw === "string") {
        setSubRaw(r.raw);
        setResult(`Obtained ${r.length ?? r.raw.length} byte`);
      } else {
        setResult("No content returned");
      }
    } catch (e) {
      setResult("Pull failed: " + (e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const handleParse = async () => {
    if (!subRaw.trim()) {
      setResult("Please paste or pull subscription content");
      return;
    }
    setBusy(true);
    try {
      const r = await api("/api/proxy/parse", "POST", { raw: subRaw });
      if (r && Array.isArray(r.nodes)) {
        useStore.setState({ nodes: r.nodes });
        setResult(`Parsing completed: ${r.count ?? r.nodes.length} nodes`);
      } else {
        setResult("Parsing failed");
      }
    } catch (e) {
      setResult("Parsing failed: " + (e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const handleHealth = async () => {
    setBusy(true);
    try {
      const r = await api("/api/proxy/health");
      if (r && Array.isArray(r.nodes)) {
        useStore.setState({ nodes: r.nodes });
        setResult("Health check completed");
      }
      await load711();
    } catch (e) {
      setResult("Health check failed: " + (e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const handleStart = async (name: string) => {
    try {
      const r = await api("/api/proxy/start", "POST", { name });
      if (r && Array.isArray(r.nodes)) useStore.setState({ nodes: r.nodes });
      pushLog(`Start node: ${name}`, "info");
    } catch (e) {
      pushLog("Startup failed: " + (e as Error).message, "err");
    }
  };

  const handleStop = async (name: string) => {
    try {
      const r = await api("/api/proxy/stop", "POST", { name });
      if (r && Array.isArray(r.nodes)) useStore.setState({ nodes: r.nodes });
      pushLog(`Stop node: ${name}`, "info");
    } catch (e) {
      pushLog("Stop failed: " + (e as Error).message, "err");
    }
  };

  const handleStartAll = async () => {
    setBusy(true);
    try {
      const r = await api("/api/proxy/start-all", "POST");
      if (r && Array.isArray(r.nodes)) useStore.setState({ nodes: r.nodes });
      setResult(`Started ${r.started ?? 0} nodes`);
    } catch (e) {
      setResult("Startup failed: " + (e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const handleStopAll = async () => {
    setBusy(true);
    try {
      const r = await api("/api/proxy/stop-all", "POST");
      if (r && Array.isArray(r.nodes)) useStore.setState({ nodes: r.nodes });
      setResult(`Stopped ${r.stopped ?? 0} nodes`);
    } catch (e) {
      setResult("Stop failed: " + (e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const nodeByCountry = nodes.reduce<Record<string, number>>((acc, n) => {
    const c = n.country_hint || "?";
    acc[c] = (acc[c] || 0) + 1;
    return acc;
  }, {});
  const healthyCount = nodes.filter((n) => n.healthy === true).length;
  const runningCount = nodes.filter((n) => n.running).length;

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h2 className="page-title">proxy pool</h2>
          <p className="page-sub">711 residential agency (host) · sing-box node · QG tunnel (Prepare)</p>
        </div>
        <div className="page-actions">
          <button className="btn" onClick={handleHealth} disabled={busy}>
            health check
          </button>
          <button className="btn btn-primary" onClick={handleStartAll} disabled={busy}>
            start all
          </button>
          <button className="btn btn-danger" onClick={handleStopAll} disabled={busy}>
            stop all
          </button>
        </div>
      </div>

      {/* ===== 711 Residential Agent Pool (main agent — Read only and no modification allowed) ===== */}
      <div className="card" style={{ marginBottom: 14 }}>
        <div className="card-head">
          <span className="card-title">711 Residential Agent Pool</span>
          <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
            <span className="badge badge-warn">Read only and no modification allowed</span>
            <span className="card-hint">main agent · client → relay → Clash → 711 → target</span>
            {status711 && (
              <span className={`health-dot ${status711.healthy ? "healthy" : "unhealthy"}`} />
            )}
            <button
              className="btn btn-sm"
              onClick={handleSmoke}
              disabled={smokeBusy || !status711?.enabled}
            >
              {smokeBusy ? "Under test..." : "smoke test"}
            </button>
            {smokeResult && (
              <span
                style={{
                  color: smokeResult.startsWith("✓") ? "var(--ok)" : "var(--danger)",
                  fontSize: 11,
                }}
              >
                {smokeResult}
              </span>
            )}
          </div>
        </div>

        {status711 ? (
          <>
            <div className="flow-chain">
              <span className="muted">client</span>
              <span className="flow-arrow">→</span>
              <span className="flow-node">{status711.relay_host}:{status711.relay_port}</span>
              <span className="flow-arrow">→</span>
              <span className="flow-node">Clash ({status711.clash_addr || "7897"})</span>
              <span className="flow-arrow">→</span>
              <span className="flow-node accent">
                {status711.gateway_host}:{status711.gateway_port}
              </span>
              <span className="flow-arrow">→</span>
              <span className="muted">target</span>
            </div>

            <div className="detail-grid">
              <div className="detail-cell">
                <div className="dc-label">gateway</div>
                <div className="dc-value">{status711.gateway_host}:{status711.gateway_port}</div>
              </div>
              <div className="detail-cell">
                <div className="dc-label">trunk port</div>
                <div className="dc-value">{status711.relay_host}:{status711.relay_port}</div>
              </div>
              <div className="detail-cell">
                <div className="dc-label">Clash port</div>
                <div className="dc-value">{status711.clash_addr || "Not detected"}</div>
                <div style={{ fontSize: 10, color: "var(--text-3)" }}>
                  candidate: {status711.clash_candidates?.join(" / ") || "7897"}
                </div>
              </div>
              <div className="detail-cell">
                <div className="dc-label">active Session</div>
                <div className="dc-value" style={{ color: "var(--accent-strong)" }}>
                  {status711.active_sessions}
                </div>
              </div>
            </div>

            <div className="card-body">
              <div className="section-head">
                <span className="section-title">support country (711 Residential agents reachable)</span>
              </div>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
                {status711.supported_countries?.map((cc) => (
                  <span className="country-tag" key={cc}>
                    {flag(cc)} {cc}
                  </span>
                ))}
              </div>
            </div>

            {status711.sessions && status711.sessions.length > 0 && (
              <div className="card-body" style={{ borderTop: "1px solid var(--border-faint)" }}>
                <div className="section-head">
                  <span className="section-title">
                    active Session (recent {Math.min(status711.sessions.length, 20)})
                  </span>
                </div>
                <div style={{ display: "flex", flexDirection: "column", gap: 3 }}>
                  {status711.sessions.map((s, i) => (
                    <div
                      key={s.id || i}
                      style={{
                        display: "grid",
                        gridTemplateColumns: "1fr 60px 60px 60px",
                        gap: 8,
                        fontSize: 11,
                        fontFamily: "var(--font-mono)",
                        padding: "4px 0",
                      }}
                    >
                      <span className="ellipsis">
                        {flag(s.region)} {s.id}
                      </span>
                      <span className="muted">{s.region}</span>
                      <span className="muted">{s.sess_time}s</span>
                      <span className="muted">{s.age_sec}sforward</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            <div
              style={{
                padding: "8px 16px",
                borderTop: "1px solid var(--border-faint)",
                fontSize: 11,
                fontFamily: "var(--font-mono)",
                color: "var(--text-3)",
              }}
            >
              Default username: {status711.default_user} · sticky session Format: session-&lt;sid&gt;-sessTime-&lt;sec&gt;-region-&lt;CC&gt;
            </div>
          </>
        ) : (
          <div className="empty">
            <div className="empty-icon">🔄</div>
            <div className="empty-title">load 711 In status...</div>
          </div>
        )}
      </div>

      {/* ===== QG tunnel pool (Prepare agent) ===== */}
      <div className="card" style={{ marginBottom: 14 }}>
        <div className="card-head">
          <span className="card-title">QG tunnel pool</span>
          <span className="card-hint">Prepare agent · Qingguo Tunnel · super pool(engine room) + residential pool</span>
        </div>
        <div className="card-body">
          <div className="grid grid-3">
            <div className="mini-card">
              <div className="mini-card-label">Super tunnel</div>
              <div className="mini-card-value">
                <span className={`badge ${qgPool.superState === "active" ? "badge-success" : "badge-muted"}`}>
                  {qgPool.superState || "unknown"}
                </span>
              </div>
            </div>
            <div className="mini-card">
              <div className="mini-card-label">Resi tunnel</div>
              <div className="mini-card-value">
                <span className={`badge ${qgPool.resiState === "active" ? "badge-success" : "badge-muted"}`}>
                  {qgPool.resiState || "unknown"}
                </span>
              </div>
            </div>
            <div className="mini-card">
              <div className="mini-card-label">Default pool</div>
              <div className="mini-card-value">{qgPool.defaultPool || "unknown"}</div>
            </div>
          </div>
        </div>
      </div>

      {/* ===== sing-box Node subscription ===== */}
      <div className="card" style={{ marginBottom: 14 }}>
        <div className="card-head">
          <span className="card-title">sing-box node</span>
          <span className="card-hint">
            {nodes.length} node · healthy {healthyCount} · run {runningCount} ·{" "}
            {Object.entries(nodeByCountry).map(([c, n]) => `${c}×${n}`).join(" ")}
          </span>
        </div>
        <div className="inline-fields">
          <input
            className="input"
            style={{ flex: 1, minWidth: 200 }}
            placeholder="subscription URL"
            value={subUrl}
            onChange={(e) => setSubUrl(e.target.value)}
          />
          <button className="btn" onClick={handleFetchSub} disabled={busy}>
            pull
          </button>
        </div>
        <div style={{ padding: "0 16px 12px" }}>
          <textarea
            className="textarea"
            rows={3}
            placeholder="Subscribe for original content (base64 / JSON / list)"
            value={subRaw}
            onChange={(e) => setSubRaw(e.target.value)}
          />
        </div>
        <div className="btn-row">
          <button className="btn btn-primary btn-sm" onClick={handleParse} disabled={busy}>
            parse
          </button>
          {result && <span className="muted">{result}</span>}
        </div>
      </div>

      <div className="table-wrap">
        <table className="table">
          <thead>
            <tr>
              <th>name</th>
              <th>type</th>
              <th>nation</th>
              <th>port</th>
              <th className="num">Delay</th>
              <th>healthy</th>
              <th className="num">concurrent</th>
              <th style={{ textAlign: "right" }}>operate</th>
            </tr>
          </thead>
          <tbody>
            {nodes.length === 0 && (
              <tr>
                <td colSpan={8} className="muted" style={{ textAlign: "center" }}>
                  No node yet
                </td>
              </tr>
            )}
            {nodes.map((n) => (
              <tr key={n.name}>
                <td className="cell-strong">{n.name}</td>
                <td>
                  <span className="tag">{n.type || "-"}</span>
                </td>
                <td>{flag(n.country_hint)} {n.country_hint || "-"}</td>
                <td className="mono">{n.port ?? "-"}</td>
                <td className="num">{n.latency != null ? `${n.latency} ms` : "-"}</td>
                <td>
                  <span className={`health-dot ${
                    n.healthy === true ? "healthy" : n.healthy === false ? "unhealthy" : ""
                  }`} />
                </td>
                <td className="num">
                  {n.concurrent ?? 0}/{n.max_concurrent ?? 0}
                </td>
                <td style={{ textAlign: "right" }}>
                  {n.running ? (
                    <button className="btn btn-ghost btn-sm" onClick={() => handleStop(n.name)}>
                      stop
                    </button>
                  ) : (
                    <button className="btn btn-ghost btn-sm" onClick={() => handleStart(n.name)}>
                      start up
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
