import { useEffect, useState, useCallback, useRef } from "react";
import { useStore } from "../store/useStore";
import { api } from "../api/client";
import type { RegEvent, RegAccount, RegStatus } from "../types";

const EMAIL_MODES: { value: string; label: string; hint: string }[] = [
  { value: "mailtm", label: "Mail.tm Temporary mailbox", hint: "Zero dependency online API，Direct number retrieval" },
];

const TYPE_CN: Record<string, string> = {
  start: "start",
  log: "log",
  progress: "schedule",
  complete: "Finish",
  error: "mistake",
};

const STATUS_CN: Record<string, string> = {
  active: "survive",
  pending: "To be verified",
  expired: "Expired",
  suspended: "freeze",
  deactivated: "deactivate",
  logout: "Sign out",
  disabled: "Invalid",
  revoked: "revoke",
  unknown: "unknown",
};

const STATUS_BADGE: Record<string, string> = {
  active: "badge-success",
  pending: "badge-warn",
  expired: "badge-warn",
  suspended: "badge-warn",
  deactivated: "badge-muted",
  logout: "badge-muted",
  disabled: "badge-danger",
  revoked: "badge-danger",
  unknown: "badge-muted",
};

const MODE_BADGE: Record<string, string> = {
  mailtm: "badge-info",
  "163": "badge-accent",
};

const PLAN_BADGE: Record<string, string> = {
  plus: "badge-accent",
  pro: "badge-accent",
  team: "badge-warn",
  free: "badge-muted",
};

interface RegDetail extends RegAccount {
  password?: string | null;
  access_token?: string | null;
  session_token?: string | null;
  refresh_token?: string | null;
}

function maskSecret(s: string | null | undefined): string {
  if (!s) return "—";
  if (s.length <= 24) return s;
  return s.slice(0, 12) + "…" + s.slice(-8);
}

export function RegisterView() {
  const pushLog = useStore((s) => s.pushLog);

  const [status, setStatus] = useState<RegStatus | null>(null);
  const [channels, setChannels] = useState<string[]>(["mailtm"]);
  const [count, setCount] = useState(1);
  const [emailMode, setEmailMode] = useState<string>("mailtm");
  const [cooldown, setCooldown] = useState(30);
  const [proxy, setProxy] = useState("");
  const [busy, setBusy] = useState(false);

  const [events, setEvents] = useState<RegEvent[]>([]);
  const [since, setSince] = useState(0);
  const [accounts, setAccounts] = useState<RegAccount[]>([]);
  const [stats, setStats] = useState<{ total: number; active: number; disabled: number } | null>(null);
  const [progress, setProgress] = useState<{ index: number; total: number; success: number; failed: number } | null>(null);
  const [search, setSearch] = useState("");
  const [filterStatus, setFilterStatus] = useState("");
  const [detail, setDetail] = useState<RegDetail | null>(null);
  const [logLevel, setLogLevel] = useState("all");
  const logRef = useRef<HTMLDivElement>(null);
  const mountedRef = useRef(true);

  const loadStatus = useCallback(async () => {
    try {
      const r = await api<RegStatus & { channels?: string[] }>("/api/register/status");
      if (r?.ok) {
        setStatus(r);
        if (Array.isArray(r.channels) && r.channels.length) setChannels(r.channels);
        if (r.last_seq) setSince((prev) => Math.max(prev, r.last_seq));
      }
    } catch { /* ignore */ }
  }, []);

  const loadAccounts = useCallback(async () => {
    try {
      const params = new URLSearchParams();
      if (search.trim()) params.set("search", search.trim());
      if (filterStatus) params.set("status", filterStatus);
      const r = await api<{ ok: boolean; items: RegAccount[] }>(
        "/api/register/accounts?" + params.toString()
      );
      if (r?.ok) setAccounts(r.items);
    } catch { /* ignore */ }
  }, [search, filterStatus]);

  const loadStats = useCallback(async () => {
    try {
      const r = await api<{ ok: boolean; total: number; active: number; disabled: number }>("/api/register/stats");
      if (r?.ok) setStats(r);
    } catch { /* ignore */ }
  }, []);

  const pollEvents = useCallback(async () => {
    if (!mountedRef.current) return;
    try {
      const r = await api<{ ok: boolean; events: RegEvent[]; last_seq: number }>(
        "/api/register/events?since=" + since
      );
      if (r?.ok && r.events.length) {
        setEvents((prev) => [...prev, ...r.events].slice(-500));
        setSince(r.last_seq);
        for (const ev of r.events) {
          if (ev.type === "log" && ev.message) {
            pushLog(`[register] ${ev.message}`, ev.stage === "engine" ? "warn" : "info");
          }
          if (ev.type === "progress" && ev.index !== undefined) {
            setProgress({ index: ev.index, total: ev.total ?? 0, success: ev.success ?? 0, failed: ev.failed ?? 0 });
          }
          if (ev.type === "complete") setProgress(null);
        }
      }
    } catch { /* ignore */ }
  }, [since, pushLog]);

  useEffect(() => {
    mountedRef.current = true;
    loadStatus();
    loadAccounts();
    loadStats();
    const t1 = setInterval(loadStatus, 3000);
    const t2 = setInterval(pollEvents, 3000);
    const t3 = setInterval(() => { loadAccounts(); loadStats(); }, 6000);
    return () => {
      mountedRef.current = false;
      clearInterval(t1); clearInterval(t2); clearInterval(t3);
    };
  }, [loadStatus, loadAccounts, loadStats, pollEvents]);

  useEffect(() => {
    if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight;
  }, [events]);

  const handleStart = async () => {
    setBusy(true);
    try {
      const r = await api<{ ok: boolean; error?: string }>("/api/register/start", "POST", {
        count: Number(count) || 1,
        email_mode: emailMode,
        cooldown: Number(cooldown) || 30,
        proxy: proxy.trim() || undefined,
      });
      if (r?.ok) {
        pushLog(`Registration task has started: ${count} indivual (${EMAIL_MODES.find((m) => m.value === emailMode)?.label})`, "ok");
        setEvents([]);
        setSince(0);
        setProgress(null);
        await loadStatus();
      } else {
        pushLog(`Startup failed: ${r?.error || "unknown reason"}`, "err");
      }
    } catch (e) {
      pushLog("Startup failed: " + (e as Error).message, "err");
    } finally {
      setBusy(false);
    }
  };

  const handleStop = async () => {
    try {
      const r = await api<{ ok: boolean; stopped: boolean }>("/api/register/stop", "POST");
      pushLog(r?.stopped ? "Stop requested（Stop after running the current number）" : "There are currently no running tasks", r?.stopped ? "warn" : "info");
    } catch (e) {
      pushLog("Stop failed: " + (e as Error).message, "err");
    }
  };

  const handleDelete = async (id: number) => {
    if (!window.confirm("Confirm to delete the registered account record？")) return;
    try {
      const r = await api(`/api/register/accounts/${id}`, "DELETE");
      if (r?.ok) {
        pushLog(`Account deleted #${id}`, "ok");
        loadAccounts();
        loadStats();
      }
    } catch (e) {
      pushLog("Delete failed: " + (e as Error).message, "err");
    }
  };

  const handleDetail = async (id: number) => {
    try {
      const r = await api<{ ok: boolean; account: RegDetail }>(`/api/register/accounts/${id}`);
      if (r?.ok) setDetail(r.account);
    } catch { /* ignore */ }
  };

  const successRate = stats && stats.total > 0 ? ((stats.active / stats.total) * 100).toFixed(0) : "—";
  const visibleEvents = events.filter((ev) => {
    if (logLevel === "all") return true;
    if (logLevel === "err") return ev.type === "error" || (ev.type === "log" && /(fail|mistake|error|fail|✗)/i.test(ev.message || ""));
    if (logLevel === "ok") return ev.type === "complete" || ev.type === "progress" || (ev.type === "log" && /(success|✓|OK|ok=)/i.test(ev.message || ""));
    return true;
  });

  return (
    <div className="view">
      <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 14 }}>
        <h2 className="page-title">Account registration</h2>
        <span className={`badge ${status?.running ? "badge-info" : "badge-muted"}`}>
          {status?.running ? "● Task running" : "○ idle"}
        </span>
      </div>

      {/* Statistics card */}
      <div className="stat-grid" style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))", gap: 10, marginBottom: 14 }}>
        <div className="stat-card">
          <div className="stat-label">Cumulative registration</div>
          <div className="stat-value">{stats?.total ?? "—"}</div>
          <div className="stat-foot">All channels</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">survive</div>
          <div className="stat-value" style={{ color: "var(--ok)" }}>{stats?.active ?? "—"}</div>
          <div className="stat-foot">alive</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Invalid</div>
          <div className="stat-value" style={{ color: "var(--danger)" }}>{stats?.disabled ?? "—"}</div>
          <div className="stat-foot">disabled</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">survival rate</div>
          <div className="stat-value">{successRate}%</div>
          <div className="stat-foot">active / total</div>
        </div>
      </div>

      {/* mission control */}
      <section className="card" style={{ marginBottom: 14 }}>
        <div className="card-head">
          <span className="card-title">Batch registration</span>
          {progress && (
            <span className="running-chip" style={{ marginLeft: 8 }}>
              No. {progress.index}/{progress.total} Number · success {progress.success} · fail {progress.failed}
            </span>
          )}
        </div>
        <div className="form-grid" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(170px, 1fr))", marginTop: 12 }}>
          <label className="field">
            <span className="field-label">Number of registrations</span>
            <input className="input" type="number" min={1} max={200} value={count}
              onChange={(e) => setCount(Math.min(Math.max(Number(e.target.value) || 1, 1), 200))} />
          </label>
          <label className="field">
            <span className="field-label">Email channel</span>
            <select className="select" value={emailMode} onChange={(e) => setEmailMode(e.target.value)}>
              {channels.map((c) => (
                <option key={c} value={c}>{EMAIL_MODES.find((m) => m.value === c)?.label || c}</option>
              ))}
            </select>
            <span className="field-hint">{EMAIL_MODES.find((m) => m.value === emailMode)?.hint || "Custom channels"}</span>
          </label>
          <label className="field">
            <span className="field-label">Room cooling (Second)</span>
            <input className="input" type="number" min={0} max={600} value={cooldown}
              onChange={(e) => setCooldown(Number(e.target.value) || 0)} />
          </label>
          <label className="field">
            <span className="field-label">Export agent</span>
            <input className="input" type="text" placeholder="Leave blank = automatic 711 relay"
              value={proxy} onChange={(e) => setProxy(e.target.value)} />
            <span className="field-hint">http://user:pass@host:port or 711 address</span>
          </label>
        </div>
        {progress && (
          <div className="progress" style={{ marginTop: 14 }}>
            <div className="progress-bar" style={{ width: `${(progress.index / progress.total) * 100}%` }} />
          </div>
        )}
        <div className="btn-row" style={{ marginTop: 14 }}>
          <button className="btn btn-primary" disabled={busy || !!status?.running} onClick={handleStart}>
            {busy ? "Starting…" : "Start registration"}
          </button>
          <button className="btn btn-stop-live" disabled={!status?.running} onClick={handleStop}>
            Stop task
          </button>
          <span className="muted" style={{ alignSelf: "center" }}>
            Successful account automatically enters Token Library（source=register），Can be used directly to lift the chain
          </span>
        </div>
      </section>

      {/* real time log */}
      <section className="card" style={{ marginBottom: 14 }}>
        <div className="card-head">
          <span className="card-title">real time log</span>
          <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
            <select className="select" style={{ width: 130 }} value={logLevel} onChange={(e) => setLogLevel(e.target.value)}>
              <option value="all">all</option>
              <option value="ok">success</option>
              <option value="err">fail/mistake</option>
            </select>
            <button className="btn btn-sm" onClick={() => setEvents([])}>Clear</button>
          </div>
        </div>
        <div className="log-panel" style={{ marginTop: 8 }}>
          <div className="log-body" ref={logRef} style={{ maxHeight: 300 }}>
            {visibleEvents.length === 0 && (
              <div className="empty" style={{ padding: "28px 0" }}>
                <div className="empty-title">No logs yet</div>
                <div className="empty-hint">Refresh in real time after starting the task</div>
              </div>
            )}
            {visibleEvents.map((ev) => {
              const cls =
                ev.type === "error" ? "err" :
                ev.type === "complete" ? "ok" :
                ev.type === "log" ? (/fail|fail|error/i.test(ev.message || "") ? "warn" : "info") :
                "info";
              return (
                <div key={ev.seq} className={`log-line ${cls}`}>
                  <span className="log-ts">{ev.ts?.slice(11, 19)}</span>
                  <span className="log-chain">{TYPE_CN[ev.type] || ev.type}</span>
                  <span className="log-msg">
                    {ev.message || (ev.type === "progress" ? `No. ${ev.index}/${ev.total} number completed` : "")}
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      </section>

      {/* Account form */}
      <section className="card">
        <div className="card-head">
          <span className="card-title">Register an account</span>
          <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
            <select className="select" style={{ width: 110 }} value={filterStatus} onChange={(e) => setFilterStatus(e.target.value)}>
              <option value="">All status</option>
              <option value="active">survive</option>
              <option value="disabled">Invalid</option>
            </select>
            <input className="input" placeholder="Search mailbox…" value={search}
              onChange={(e) => setSearch(e.target.value)} style={{ width: 200 }} />
            <button className="btn btn-sm" onClick={() => { loadAccounts(); loadStats(); }}>refresh</button>
          </div>
        </div>
        <div className="table-wrap" style={{ marginTop: 8 }}>
          <table className="table">
            <thead>
              <tr>
                <th className="num">ID</th>
                <th>Mail</th>
                <th>channel</th>
                <th>combo</th>
                <th>state</th>
                <th>error code</th>
                <th>Registration time</th>
                <th>Token</th>
                <th className="num">operate</th>
              </tr>
            </thead>
            <tbody>
              {accounts.length === 0 && (
                <tr>
                  <td colSpan={9}>
                    <div className="empty" style={{ padding: "24px 0" }}>
                      <div className="empty-title">No registration record yet</div>
                      <div className="empty-hint">After starting the registration task，The results will be displayed here</div>
                    </div>
                  </td>
                </tr>
              )}
              {accounts.map((a) => (
                <tr key={a.id}>
                  <td className="num mono">{a.id}</td>
                  <td className="mono">{a.email}</td>
                  <td>
                    <span className={`badge ${MODE_BADGE[a.email_mode || ""] || "badge-muted"}`}>
                      {a.email_mode || "—"}
                    </span>
                  </td>
                  <td>
                    <span className={`badge ${PLAN_BADGE[a.plan_type || ""] || "badge-muted"}`}>
                      {a.plan_type || "—"}
                    </span>
                  </td>
                  <td>
                    <span className={`badge ${STATUS_BADGE[a.alive_status] || "badge-muted"}`}>
                      {STATUS_CN[a.alive_status] || a.alive_status}
                    </span>
                  </td>
                  <td className="mono">{a.error_code || "—"}</td>
                  <td className="mono">{a.register_ts?.slice(0, 19) || a.created_at?.slice(0, 19) || "—"}</td>
                  <td>
                    {a.has_access_token && <span className="badge badge-info">at</span>}
                    {a.has_session_token && <span className="badge badge-info" style={{ marginLeft: 4 }}>st</span>}
                    {!a.has_access_token && <span className="badge badge-muted">none</span>}
                  </td>
                  <td className="num">
                    <button className="btn btn-sm" onClick={() => handleDetail(a.id)}>Details</button>
                    <button className="btn btn-sm btn-danger" style={{ marginLeft: 4 }} onClick={() => handleDelete(a.id)}>delete</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {/* Details popup */}
      {detail && (
        <div className="overlay" onClick={() => setDetail(null)}>
          <div className="sheet" onClick={(e) => e.stopPropagation()}>
            <div className="sheet-head">
              <span className="sheet-title">Account details #{detail.id}</span>
              <button className="icon-btn" onClick={() => setDetail(null)} aria-label="closure">✕</button>
            </div>
            <div className="sheet-body">
              <div className="detail-list">
                <div className="detail-row">
                  <span className="dr-label">Mail</span>
                  <span className="dr-value mono">{detail.email}</span>
                </div>
                <div className="detail-row">
                  <span className="dr-label">password</span>
                  <span className="dr-value mono">{maskSecret(detail.password)}</span>
                </div>
                <div className="detail-row">
                  <span className="dr-label">AccessToken</span>
                  <span className="dr-value mono" style={{ wordBreak: "break-all" }}>{maskSecret(detail.access_token)}</span>
                </div>
                <div className="detail-row">
                  <span className="dr-label">SessionToken</span>
                  <span className="dr-value mono" style={{ wordBreak: "break-all" }}>{maskSecret(detail.session_token)}</span>
                </div>
                <div className="detail-row">
                  <span className="dr-label">RefreshToken</span>
                  <span className="dr-value mono" style={{ wordBreak: "break-all" }}>{maskSecret(detail.refresh_token)}</span>
                </div>
                <div className="detail-row">
                  <span className="dr-label">combo</span>
                  <span className="dr-value">{detail.plan_type || "—"}</span>
                </div>
                <div className="detail-row">
                  <span className="dr-label">state</span>
                  <span className="dr-value">
                    <span className={`badge ${STATUS_BADGE[detail.alive_status] || "badge-muted"}`}>
                      {STATUS_CN[detail.alive_status] || detail.alive_status}
                    </span>
                    {" "}
                    <span className={`badge ${detail.status === "active" ? "badge-success" : "badge-danger"}`}>
                      {detail.status}
                    </span>
                  </span>
                </div>
                <div className="detail-row">
                  <span className="dr-label">channel</span>
                  <span className="dr-value">{detail.email_mode || "—"}</span>
                </div>
                <div className="detail-row">
                  <span className="dr-label">Source email</span>
                  <span className="dr-value mono">{detail.source_email || "—"}</span>
                </div>
                <div className="detail-row">
                  <span className="dr-label">Registration time</span>
                  <span className="dr-value mono">{detail.register_ts || detail.created_at || "—"}</span>
                </div>
                {detail.error_detail && (
                  <div className="detail-row">
                    <span className="dr-label">Reason for failure</span>
                    <span className="dr-error" style={{ wordBreak: "break-all" }}>{detail.error_detail}</span>
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}