import { useEffect, useMemo, useRef, useState } from "react";
import { useStore } from "../store/useStore";
import { api } from "../api/client";
import { BRANCH_CN } from "../types";
import type { Token, BranchName } from "../types";

/* ==========================================================================
   Token Library — Inventory mailbox + Lift chain startup entrance
   - Isolate by chain branch token Library (source)
   - Batch chain lifting / Single line lift chain / Mention again (success、You can try again if you fail.)
   - Status distinction: Unmentioned chain / Carrying the chain / Already mentioned chain / fail / cool down / Invalid
   - combo / Registration method (When importing from JWT Metadata parsing, Subsequent access to the detection interface)
   ========================================================================== */

/** branch -> token library source tag (with backend config branch.token_source correspond) */
const BRANCH_TOKEN_SOURCE: Record<string, string> = {
  paypal: "stripe",
  momo: "momo",
  grok: "grok",
  pix: "pix",
  ideal: "ideal",
  upi: "upi",
  kakao: "kakao",
  blik: "blik",
  twint: "twint",
  direct: "direct",
  register: "register",
};

/** drop down options: lifting chain branch + Register account source (source=register) */
const TOKEN_SOURCE_OPTIONS: { key: string; label: string; source: string }[] = [
  ...(Object.keys(BRANCH_CN) as BranchName[]).map((b) => ({
    key: b,
    label: `lift chain: ${BRANCH_CN[b]} (${BRANCH_TOKEN_SOURCE[b]})`,
    source: BRANCH_TOKEN_SOURCE[b],
  })),
  { key: "register", label: "Register an account (register)", source: "register" },
];

function activeBranchTokenSource(b: string): string {
  return BRANCH_TOKEN_SOURCE[b] || "stripe";
}

const STATUS_BADGE: Record<string, { label: string; cls: string }> = {
  idle: { label: "Unmentioned chain", cls: "badge-muted" },
  running: { label: "Carrying the chain", cls: "badge-info" },
  success: { label: "Already mentioned chain", cls: "badge-success" },
  failed: { label: "fail", cls: "badge-danger" },
  cooldown: { label: "cool down", cls: "badge-warn" },
  expired: { label: "Invalid", cls: "badge-danger" },
};

const STATUS_OPTIONS = Object.entries({
  all: "All status",
  idle: "Unmentioned chain",
  running: "Carrying the chain",
  success: "Already mentioned chain",
  failed: "fail",
  cooldown: "cool down",
  expired: "Invalid",
});

/** local parsing JWT payload (No signature verification, For importing defocus calibration preview)
 *  JWS 3 part (plain text payload) / JWE 5 part (alg=dir encryption, payload incomprehensible, mark jwe) */
function jwtMeta(jwt: string): { email: string; sub: string; account_id: string; plan_type: string; jwe: boolean } | null {
  const parts = jwt.trim().split(".");
  if (parts.length < 3 || parts.length > 5) return null;
  const b64url = (s: string) => {
    const b64 = s.replace(/-/g, "+").replace(/_/g, "/");
    return b64 + "=".repeat((4 - (b64.length % 4)) % 4);
  };
  try {
    const header = JSON.parse(atob(b64url(parts[0])));
    if ((header.alg || "").toLowerCase() === "dir" || parts.length >= 4) {
      // JWE encryption session token: No clear text fields
      return { email: "", sub: "", account_id: "", plan_type: "", jwe: true };
    }
    const payload = JSON.parse(atob(b64url(parts[1])));
    const auth = payload["https://api.openai.com/auth"] || {};
    const prof = payload["https://api.openai.com/profile"] || {};
    const email = (prof && typeof prof === "object" && prof.email) || payload.email || "";
    return {
      email: String(email || ""),
      sub: String(payload.sub || ""),
      account_id: String(auth.user_id || ""),
      plan_type: String(auth.chatgpt_plan_type || auth.plan || payload.plan || "free"),
      jwe: false,
    };
  } catch {
    return null;
  }
}

interface CalibItem {
  ok: boolean;
  email: string;
  plan: string;
  err: string;
}
interface CalibResult {
  total: number;
  ok: number;
  fail: number;
  items: CalibItem[];
  firstErr: string;
}

function methodLabel(m: string): string {
  if (m === "email") return "Mail";
  if (m === "phone") return "cell phone";
  if (m === "google") return "Google";
  if (m === "apple") return "Apple";
  return m || "-";
}

export function TokensView() {
  const tokens = useStore((s) => s.tokens);
  const selectedTokenIds = useStore((s) => s.selectedTokenIds);
  const toggleTokenSelect = useStore((s) => s.toggleTokenSelect);
  const selectAllTokens = useStore((s) => s.selectAllTokens);
  const clearTokenSelection = useStore((s) => s.clearTokenSelection);
  const pushLog = useStore((s) => s.pushLog);
  const activeBranch = useStore((s) => s.activeBranch);
  const setActiveBranch = useStore((s) => s.setActiveBranch);
  const [sourceFilter, setSourceFilter] = useState<string>(() => BRANCH_TOKEN_SOURCE[activeBranch] || "stripe");

  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [raw, setRaw] = useState("");
  const [result, setResult] = useState("");
  const [calib, setCalib] = useState<CalibResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [probingId, setProbingId] = useState("");
  const [editingTagsId, setEditingTagsId] = useState("");
  const [editingTagsVal, setEditingTagsVal] = useState("");
  const [tagFilter, setTagFilter] = useState("");
  const [poolUrl, setPoolUrl] = useState("");
  const [poolResult, setPoolResult] = useState("");
  const [poolBusy, setPoolBusy] = useState(false);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);

  const PAGE_SIZES = [10, 20, 50, 100];

  const tokenSource = (t: Token): string => (t as any).source || "stripe";

  /** Current view label: register source "Register an account", Otherwise, use the Chinese name of the branch */
  const viewBranchLabel = sourceFilter === "register" ? "Register an account" : BRANCH_CN[activeBranch] || activeBranch;

  /** defense: tags May be an array/string/undefined */
  const tagsOf = (t: any): string[] =>
    Array.isArray(t?.tags) ? t.tags : typeof t?.tags === "string" && t.tags ? t.tags.split(",").map((s: string) => s.trim()).filter(Boolean) : [];

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return tokens.filter((t) => {
      if (tokenSource(t) !== sourceFilter) return false;
      if (statusFilter !== "all" && t.status !== statusFilter) return false;
      if (tagFilter && !tagsOf(t).includes(tagFilter)) return false;
      if (!q) return true;
      return (
        (t.email || "").toLowerCase().includes(q) ||
        (t.sub || "").toLowerCase().includes(q) ||
        (t.account_id || "").toLowerCase().includes(q)
      );
    });
  }, [tokens, search, statusFilter, sourceFilter, tagFilter]);

  const allTags = useMemo(() => {
    const set = new Set<string>();
    tokens.forEach((t) => {
      if (tokenSource(t) !== sourceFilter) return;
      tagsOf(t).forEach((tag) => set.add(tag));
    });
    return Array.from(set).sort();
  }, [tokens, sourceFilter]);

  const totalPages = Math.max(1, Math.ceil(filtered.length / pageSize));
  const safePage = Math.min(page, totalPages);
  const pageTokens = useMemo(
    () => filtered.slice((safePage - 1) * pageSize, safePage * pageSize),
    [filtered, safePage, pageSize]
  );

  useEffect(() => {
    setPage(1);
  }, [search, statusFilter, sourceFilter, pageSize, tagFilter]);

  const allSelected =
    pageTokens.length > 0 && pageTokens.every((t) => selectedTokenIds.has(t.id));

  const togglePageSelect = () => {
    if (allSelected) {
      pageTokens.forEach((t) => {
        if (selectedTokenIds.has(t.id)) toggleTokenSelect(t.id);
      });
    } else {
      pageTokens.forEach((t) => {
        if (!selectedTokenIds.has(t.id)) toggleTokenSelect(t.id);
      });
    }
  };

  const statBadges = useMemo(() => {
    const c: Record<string, number> = {};
    for (const t of tokens) {
      if (tokenSource(t) !== sourceFilter) continue;
      c[t.status || "idle"] = (c[t.status || "idle"] || 0) + 1;
    }
    return c;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tokens, sourceFilter]);

  const handleRefresh = async () => {
    setBusy(true);
    try {
      const r = await api("/api/tokens");
      if (r && Array.isArray(r.tokens)) {
        useStore.setState({ tokens: r.tokens });
        const cur = r.tokens.filter((t: Token) => tokenSource(t) === sourceFilter);
        setResult(`Refreshed，common ${r.tokens.length} indivual Token（${sourceFilter} Library ${cur.length} indivual）`);
      } else {
        setResult("Refresh failed: Return data exception");
      }
    } catch (e) {
      setResult("Refresh failed: " + (e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const handleRepair = async () => {
    setBusy(true);
    try {
      const r = await api("/api/tokens/repair", "POST", {});
      setResult(`Metadata repair completed: Correction ${r?.fixed ?? 0} strip / common ${r?.total ?? 0} strip`);
      const tokensR = await api("/api/tokens");
      if (tokensR && Array.isArray(tokensR.tokens)) {
        useStore.setState({ tokens: tokensR.tokens });
      }
    } catch (e) {
      setResult("Repair failed: " + (e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const handleProbe = async (t: Token) => {
    setProbingId(t.id);
    try {
      const r = await api(`/api/tokens/${t.id}/probe`, "POST", {});
      const stype = r?.session_type || "";
      const probe = r?.probe || {};
      useStore.setState((s) => ({
        tokens: s.tokens.map((x) => (x.id === t.id ? { ...x, session_type: stype, probe } : x)),
      }));
      const pe = probe.token_error || "";
      setResult(`Detection completed: ${t.email || t.sub} → ${stype || "unknown"}${pe ? ` · ${pe}` : ""}${probe.promo ? ` · discount:${probe.promo === "yes" ? "have" : probe.promo}` : ""}`);
    } catch (e) {
      setResult("Detection failed: " + (e as Error).message);
    } finally {
      setProbingId("");
    }
  };

  const probeProgress = useStore((s) => s.probeProgress);

  const probingNow = probeProgress.total > 0 && probeProgress.done < probeProgress.total;
  const handleBatchProbe = async () => {
    const ids = filtered.map((t) => t.id);
    if (ids.length === 0) {
      setResult("There is nothing detectable under the current filter Token");
      return;
    }
    useStore.setState({ probeProgress: { done: 0, total: ids.length } });
    setResult(`Batch detection starts: ${ids.length} indivual Token，Real-time updates every time a piece is completed…`);
    try {
      const r = await api("/api/tokens/probe", "POST", { ids });
      if (r && r.ok) {
        pushLog(`Batch detection starts: ${r.started ?? 0} indivual`, "ok");
        setResult(`Batch detection has started ${r.started ?? 0} indivual Token，Real-time updates every time a piece is completed…`);
      } else {
        setResult("Batch detection failed to start: " + (r?.error || "unknown error"));
        useStore.setState({ probeProgress: { done: 0, total: 0 } });
      }
    } catch (e) {
      setResult("Batch detection failed to start: " + (e as Error).message);
      useStore.setState({ probeProgress: { done: 0, total: 0 } });
    }
  };

  /** drop down options: Existing tags + Default commonly used tags */
  const PRESET_TAGS = ["Promotion", "No discount", "revoked", "Expired", "Current limiting", "cs_live", "oaics", "Google", "Mail", "cell phone"];
  const tagOptions = useMemo(() => {
    const seen = new Set<string>();
    const out: { value: string; preset: boolean }[] = [];
    allTags.forEach((t) => { if (!seen.has(t)) { seen.add(t); out.push({ value: t, preset: false }); } });
    PRESET_TAGS.forEach((t) => { if (!seen.has(t)) { seen.add(t); out.push({ value: t, preset: true }); } });
    return out;
  }, [allTags]);

  const saveTags = async (t: Token, raw: string) => {
    const tags = raw.split(",").map((s) => s.trim()).filter(Boolean);
    try {
      const r = await api(`/api/tokens/${t.id}/tags`, "POST", { tags });
      if (r && r.ok) {
        useStore.setState((s) => ({
          tokens: s.tokens.map((x) => (x.id === t.id ? { ...x, tags: r.tags || [] } : x)),
        }));
      }
    } catch { /* ignore */ }
  };

  const sessionBadge = (st: string | undefined) => {
    if (!st) return { label: "Not detected", cls: "badge-muted" };
    if (st === "cs_live") return { label: "cs_live", cls: "badge-success" };
    if (st === "oaics") return { label: "oaics", cls: "badge-accent" };
    if (st.startsWith("error")) return { label: st.slice(0, 18), cls: "badge-danger" };
    return { label: st, cls: "badge-muted" };
  };

  const tokenErrBadge = (pe: string | undefined) => {
    if (!pe) return null;
    if (pe.includes("revoke")) return { label: pe, cls: "badge-danger" };
    if (pe.includes("Expired")) return { label: pe, cls: "badge-warn" };
    if (pe.includes("Current limiting")) return { label: pe, cls: "badge-warn" };
    return { label: pe.slice(0, 14), cls: "badge-danger" };
  };

  const promoBadge = (promo: string | undefined) => {
    if (!promo) return null;
    if (promo === "yes") return { label: "discount✓", cls: "badge-success" };
    if (promo === "no") return { label: "No discount", cls: "badge-muted" };
    return { label: promo.slice(0, 14), cls: "badge-warn" };
  };

  /** Recursively collect account objects (compatible mail-otp-server Export: array / sub2api.accounts / codex·codexmanager.tokens) */
function collectTokens(o: any, out: CalibItem[]) {
  if (!o || typeof o !== "object") return;
  if (Array.isArray(o)) {
    o.forEach((x) => collectTokens(x, out));
    return;
  }
  const tokens = o.tokens && typeof o.tokens === "object" ? o.tokens : {};
  const creds = o.credentials && typeof o.credentials === "object" ? o.credentials : {};
  const user = o.user && typeof o.user === "object" ? o.user : {};
  const account = o.account && typeof o.account === "object" ? o.account : {};
  const meta = o.meta && typeof o.meta === "object" ? o.meta : {};
  const at = String(
    o.accessToken || o.access_token ||
    tokens.accessToken || tokens.access_token ||
    creds.accessToken || creds.access_token || ""
  ).trim();
  const st = String(o.sessionToken || o.session_token || creds.sessionToken || creds.session_token || "").trim();
  const email = String(o.email || user.email || account.email || meta.label || "");
  const parsed = at && jwtMeta(at);
  if (parsed) {
    out.push({
      ok: true,
      email: parsed.jwe ? "JWE encryption session token" : email || parsed.email || at.slice(0, 20) + "…",
      plan: parsed.jwe ? "jwe" : parsed.plan_type,
      err: "",
    });
    return;
  }
  if (st && jwtMeta(st)) {
    // only session token entry (as alone JWE)
    out.push({ ok: true, email: "only session token (none access token)", plan: "jwe", err: "" });
    return;
  }
  for (const k of ["accounts", "tokens", "credentials"]) {
    if (o[k] && typeof o[k] === "object") collectTokens(o[k], out);
  }
}

  const calibrateText = (text: string) => {
    const items: CalibItem[] = [];
    // whole paragraph JSON (object / array / sub2api / codex Waiting for packaging)
    try {
      const whole = JSON.parse(text.trim());
      if (whole && typeof whole === "object") {
        collectTokens(whole, items);
        if (items.length > 0) {
          const ok = items.filter((i) => i.ok).length;
          const fail = items.length - ok;
          setCalib({
            total: items.length,
            ok,
            fail,
            items,
            firstErr: items.find((i) => !i.ok)?.err || "",
          });
          return;
        }
      }
    } catch {
      /* If the entire paragraph fails to be parsed, it will be line by line. */
    }
    const lines = text.split("\n");
    for (const line of lines) {
      const t = line.trim();
      if (!t) continue;
      if (t.startsWith("{") || t.startsWith("[")) {
        try {
          const o = JSON.parse(t);
          collectTokens(o, items);
          continue;
        } catch {
          // Inside the industry JSON fail, fall naked JWT determination
        }
      }
      const meta = jwtMeta(t);
      if (meta) {
        items.push({
          ok: true,
          email: meta.jwe ? "JWE encryption session token" : meta.email || meta.sub.slice(0, 20) + "…",
          plan: meta.jwe ? "jwe" : meta.plan_type,
          err: "",
        });
      } else {
        items.push({ ok: false, email: "", plan: "", err: "No JWT / No JSON" });
      }
    }
    const ok = items.filter((i) => i.ok).length;
    const fail = items.length - ok;
    setCalib({
      total: items.length,
      ok,
      fail,
      items,
      firstErr: items.find((i) => !i.ok)?.err || "",
    });
  };

  const handleCalibrate = () => calibrateText(raw);

  const [filesInfo, setFilesInfo] = useState<string[]>([]);
  const [dragging, setDragging] = useState(false);
  const [reading, setReading] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const dirInputRef = useRef<HTMLInputElement>(null);

  const readFiles = async (list: FileList | File[]) => {
    const arr = Array.from(list);
    if (arr.length === 0) return;
    setReading(true);
    try {
      const texts = await Promise.all(arr.map((f) => f.text()));
      const joined = texts.join("\n");
      setRaw(joined);
      setFilesInfo(arr.map((f) => f.name));
      setResult(`Read ${arr.length} files, common ${joined.length} character, Calibrating…`);
      setCalib(null);
      // setRaw Take effect asynchronously, Calibrate directly with text
      calibrateText(joined);
    } catch (e) {
      setResult("Failed to read file: " + (e as Error).message);
    } finally {
      setReading(false);
    }
  };

  const handleImport = async () => {
    if (!raw.trim()) {
      setResult("Please paste Token JSON");
      return;
    }
    setBusy(true);
    try {
      const r = await api("/api/tokens/import", "POST", {
        raw,
        source: sourceFilter,
      });
      const tokensR = await api("/api/tokens");
      if (tokensR && Array.isArray(tokensR.tokens)) {
        useStore.setState({ tokens: tokensR.tokens });
      }
      setResult(`Import completed: success ${r.imported ?? 0}, fail ${r.failed ?? 0}, Communist Party of Kuwait ${tokensR?.tokens?.length ?? 0} indivual`);
    } catch (e) {
      setResult("Import failed: " + (e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const handleClear = () => {
    setRaw("");
    setResult("");
  };

  const handlePoolImport = async () => {
    setPoolBusy(true);
    setPoolResult("Pull from registration pool…");
    try {
      const r = await api("/api/tokens/import-from-pool", "POST", {
        base_url: poolUrl.trim() || undefined,
        source: sourceFilter,
      });
      if (r && r.ok) {
        setPoolResult(`pull ${r.total ?? 0}, import ${r.imported ?? 0}, Deduplication and skipping ${r.skipped ?? 0}`);
        const tokensR = await api("/api/tokens");
        if (tokensR && Array.isArray(tokensR.tokens)) {
          useStore.setState({ tokens: tokensR.tokens });
        }
      } else {
        setPoolResult(r?.error || "Import failed");
      }
    } catch (e) {
      setPoolResult("abnormal: " + (e as Error).message);
    } finally {
      setPoolBusy(false);
    }
  };

  const runChain = async (ids: string[]) => {
    if (ids.length === 0) return;
    setBusy(true);
    try {
      const res = await api("/api/chain/batch", "POST", {
        token_ids: ids,
        branch: sourceFilter === "register" ? "paypal" : activeBranch,
      });
      const label = ids.length === 1
        ? (tokens.find((t) => t.id === ids[0])?.email || ids[0])
        : `${ids.length} indivual Token`;
      if (res && res.error) {
        pushLog(`${viewBranchLabel} Failed to start the chain: ${res.error}`, "err");
        setResult(`Startup failed: ${res.error}`);
      } else {
        pushLog(`${viewBranchLabel} Lift chain start: ${label}`, "ok");
        setResult(`Started ${ids.length} indivual Token of ${viewBranchLabel} lift chain`);
      }
    } catch (e) {
      pushLog(`${viewBranchLabel} Failed to start the chain: ${(e as Error).message}`, "err");
      setResult("Startup failed: Backend is unavailable");
    } finally {
      setBusy(false);
    }
  };

  const handleBatchStart = () => {
    const ids = Array.from(selectedTokenIds);
    if (ids.length === 0) {
      pushLog("Please check first Token", "warn");
      return;
    }
    runChain(ids);
  };

  const handleRunOne = (t: Token) => {
    runChain([t.id]);
  };

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h2 className="page-title">Token Library</h2>
          <p className="page-sub">
            Inventory mailbox · {sourceFilter === "register" ? "Register an account" : `${viewBranchLabel} Chain entrance`} · token Library {sourceFilter}
          </p>
        </div>
        <div className="page-actions">
          <select
            className="select"
            style={{ width: 200 }}
            value={sourceFilter}
            onChange={(e) => {
              const v = e.target.value;
              setSourceFilter(v);
              clearTokenSelection();
            }}
          >
            {TOKEN_SOURCE_OPTIONS.map((o) => (
              <option key={o.key} value={o.source}>
                {o.label}
              </option>
            ))}
          </select>
          <input
            className="input"
            style={{ width: 200 }}
            placeholder="search email / sub / account_id"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
          <select
            className="select"
            style={{ width: 110 }}
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
          >
            {STATUS_OPTIONS.map(([v, label]) => (
              <option key={v} value={v}>
                {label}
              </option>
            ))}
          </select>
          <select
            className="select"
            style={{ width: 130 }}
            value={tagFilter}
            onChange={(e) => setTagFilter(e.target.value)}
          >
            <option value="">All tags</option>
            {tagOptions.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.value}{opt.preset ? " ⚡" : ""}
              </option>
            ))}
          </select>
          {tagFilter && (
            <button
              className="btn btn-ghost btn-sm"
              onClick={() => setTagFilter("")}
              title="Clear tag filter"
            >
              Clear✕
            </button>
          )}
          <button className="btn" onClick={handleRefresh} disabled={busy}>
            refresh
          </button>
          <button
            className="btn btn-ghost"
            onClick={handleRepair}
            disabled={busy}
            title="Recalculate registration methods and clear tainted mailboxes (user-xxx)"
          >
            Reparse metadata
          </button>
        </div>
      </div>

      <div className="card" style={{ marginBottom: 14 }}>
        <div className="card-head">
          <span className="card-title">Batch chain lifting — {viewBranchLabel}</span>
          <span className="card-hint">
            Just check a few and mention a few · Segment retry/always try/The billing country is「{viewBranchLabel}」Link configuration page · Already mentioned chain/failed Token Can be recalled
          </span>
        </div>
        <div className="card-body tight">
          <div className="inline-fields">
            <span className="badge badge-info">Selected {selectedTokenIds.size}</span>
            <span className="muted" style={{ fontSize: 12 }}>common {filtered.length} strip</span>
            <button
              className="btn btn-ghost btn-sm"
              onClick={togglePageSelect}
              disabled={pageTokens.length === 0}
            >
              {allSelected ? "Unselect all on this page" : "Select all on this page"}
            </button>
            <button
              className="btn btn-ghost btn-sm"
              onClick={handleBatchProbe}
              disabled={probingNow || filtered.length === 0}
              title="Detect all under current filter Token session type/Discount qualifications/token state"
            >
              {probingNow ? `Detecting ${probeProgress.done}/${probeProgress.total}` : `Batch detection (${filtered.length})`}
            </button>
            {probingNow && (
              <span className="badge badge-info" style={{ minWidth: 60 }}>
                {Math.round((probeProgress.done / probeProgress.total) * 100)}%
              </span>
            )}
            <button
              className="btn btn-primary"
              onClick={handleBatchStart}
              disabled={busy || selectedTokenIds.size === 0}
            >
              Batch chain lifting
            </button>
          </div>
          {result && (
            <div className="muted" style={{ marginTop: 8, fontSize: 12 }}>
              {result}
            </div>
          )}
        </div>
      </div>

      <div className="card" style={{ marginBottom: 14 }}>
        <div className="card-body tight" style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
          {Object.entries(STATUS_BADGE).map(([st, cfg]) => {
            const n = statBadges[st] || 0;
            if (n === 0) return null;
            return (
              <span key={st} className={`badge ${cfg.cls}`}>
                {cfg.label} {n}
              </span>
            );
          })}
          {Object.keys(statBadges).length === 0 && (
            <span className="muted" style={{ fontSize: 12 }}>This branch library is currently unavailable Token</span>
          )}
        </div>
      </div>

      <div className="card" style={{ marginBottom: 14 }}>
        <div className="card-head">
          <span className="card-title">import Token → {viewBranchLabel} Library</span>
          <span className="card-hint">
            Paste / Select file / Select folder / Drag and drop import · Automatically parse all GPT Export format (raw / session / cpa /
            sub2api / codex2api / codexmanager / cockpit / codex / JWT / JWE)
          </span>
        </div>
        <input
          ref={fileInputRef}
          type="file"
          multiple
          style={{ display: "none" }}
          onChange={(e) => {
            if (e.target.files) readFiles(e.target.files);
            e.target.value = "";
          }}
        />
        <input
          ref={dirInputRef}
          type="file"
          multiple
          {...({ webkitdirectory: "", directory: "" } as any)}
          style={{ display: "none" }}
          onChange={(e) => {
            if (e.target.files) readFiles(e.target.files);
            e.target.value = "";
          }}
        />
        <div
          className={"import-dropzone" + (dragging ? " dropzone-active" : "")}
          style={{ padding: "14px 16px 0" }}
          onDragOver={(e) => {
            e.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDragging(false);
            readFiles(e.dataTransfer.files);
          }}
        >
          <textarea
            className="textarea"
            rows={5}
            placeholder='{"accessToken":"...","sub":"..."} or one per line JWT/JSON（Defocus automatic calibration）· Or drag files here'
            value={raw}
            onChange={(e) => {
              setRaw(e.target.value);
              setCalib(null);
            }}
            onBlur={handleCalibrate}
          />
          {dragging && (
            <div className="dropzone-hint">
              <span style={{ fontSize: 18 }}>📥</span> Release the mouse to import the file…
            </div>
          )}
        </div>
        {filesInfo.length > 0 && (
          <div style={{ padding: "10px 16px 0", display: "flex", gap: 6, flexWrap: "wrap" }}>
            {filesInfo.slice(0, 10).map((n, i) => (
              <span key={i} className="tag file-item" style={{ animationDelay: `${i * 40}ms`, fontSize: 10.5 }}>
                {n}
              </span>
            ))}
            {filesInfo.length > 10 && (
              <span className="tag file-item" style={{ fontSize: 10.5 }}>+{filesInfo.length - 10} files</span>
            )}
          </div>
        )}
        {calib && calib.total > 0 && (
          <div className="card-body tight" style={{ margin: "10px 16px 0", border: "1px solid var(--border-faint)" }}>
            <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
              <span className={`badge ${calib.ok > 0 ? "badge-success" : "badge-muted"}`}>
                efficient {calib.ok}
              </span>
              <span className="badge badge-muted">common {calib.total} OK</span>
              {calib.fail > 0 && (
                <span className="badge badge-danger" title={calib.firstErr}>
                  invalid {calib.fail} · {calib.firstErr}
                </span>
              )}
              <span className="muted" style={{ fontSize: 11 }}>
                Defocus calibration · Preview (forward {Math.min(calib.items.length, 6)} strip):
              </span>
            </div>
            <div style={{ marginTop: 6, display: "flex", flexDirection: "column", gap: 2 }}>
              {calib.items.slice(0, 6).map((it, i) => (
                <div key={i} className="mono" style={{ fontSize: 11, display: "flex", gap: 8 }}>
                  <span style={{ color: it.ok ? "var(--ok)" : "var(--danger)" }}>
                    {it.ok ? "✓" : "✗"}
                  </span>
                  <span style={{ flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                    {it.ok ? (it.email || "-") : it.err}
                  </span>
                  {it.ok && <span className="tag" style={{ fontSize: 10 }}>{it.plan}</span>}
                </div>
              ))}
            </div>
          </div>
        )}
        <div className="btn-row">
          <button
            className="btn btn-primary"
            onClick={() => {
              handleCalibrate();
              handleImport();
            }}
            disabled={busy || reading}
          >
            {busy ? "Importing…" : "import"}
          </button>
          <button className="btn" onClick={() => fileInputRef.current?.click()} disabled={busy || reading}>
            {reading ? "Reading…" : "📄 Select file"}
          </button>
          <button className="btn" onClick={() => dirInputRef.current?.click()} disabled={busy || reading}>
            Select folder
          </button>
          <button
            className="btn"
            onClick={() => {
              handleClear();
              setCalib(null);
              setFilesInfo([]);
            }}
          >
            Clear
          </button>
          {result && <span className="muted">{result}</span>}
        </div>
      </div>

      <div className="card" style={{ marginBottom: 14 }}>
        <div className="card-head">
          <span className="card-title">Import from registration pool → {viewBranchLabel} Library</span>
          <span className="card-hint">
            pull codex_register Unused email/token · access_token + email Double deduplication
          </span>
        </div>
        <div className="btn-row" style={{ flexWrap: "wrap" }}>
          <input
            className="input"
            style={{ flex: 1, minWidth: 260 }}
            placeholder="Register pool address（default config.register_pool.base_url）"
            value={poolUrl}
            onChange={(e) => setPoolUrl(e.target.value)}
          />
          <button className="btn btn-primary" onClick={handlePoolImport} disabled={poolBusy}>
            {poolBusy ? "Pulling…" : "Pull and import"}
          </button>
          {poolResult && <span className="muted">{poolResult}</span>}
        </div>
      </div>

      <div className="table-wrap">
        <table className="table">
          <thead>
            <tr>
              <th style={{ width: 34 }}>
                <input
                  type="checkbox"
                  checked={allSelected}
                  onChange={togglePageSelect}
                />
              </th>
              <th>Email / Sub</th>
              <th>combo</th>
              <th>Registration method</th>
              <th>detection</th>
              <th>Label</th>
              <th>last run</th>
              <th>state</th>
              <th className="row-action" style={{ textAlign: "right" }}>operate</th>
            </tr>
          </thead>
          <tbody>
            {pageTokens.length === 0 && (
              <tr>
                <td colSpan={9} className="muted" style={{ textAlign: "center" }}>
                  No data yet — import Token Or switch the chain branch
                </td>
              </tr>
            )}
            {pageTokens.map((t) => {
              const badge = STATUS_BADGE[t.status || "idle"] || STATUS_BADGE.idle;
              const isRunning = t.status === "running";
              const sbadge = sessionBadge((t as any).session_type);
              const probe = (t as any).probe || {};
              const terr = tokenErrBadge(probe.token_error);
              const pbadge = promoBadge(probe.promo);
              const paypal = probe.paypal ? "· paypal" : "";
              return (
                <tr
                  key={t.id}
                  className={selectedTokenIds.has(t.id) ? "row-selected" : ""}
                >
                  <td>
                    <input
                      type="checkbox"
                      checked={selectedTokenIds.has(t.id)}
                      onChange={() => toggleTokenSelect(t.id)}
                      disabled={isRunning}
                    />
                  </td>
                  <td>
                    <div className="cell-strong">{t.email || "-"}</div>
                    <div className="cell-sub">{t.sub || t.account_id || "-"}</div>
                  </td>
                  <td>
                    <span className="tag">{t.plan_type || "free"}</span>
                  </td>
                  <td>{methodLabel(t.register_method)}</td>
                  <td>
                    <div style={{ display: "flex", flexWrap: "wrap", gap: 4, maxWidth: 150 }}>
                      <span className={`badge ${sbadge.cls}`} title={(t as any).session_type || "Automatic detection after import / Manual click detection"}>
                        {sbadge.label}
                      </span>
                      {pbadge && <span className={`badge ${pbadge.cls}`} title="Promotional Eligibility Detection (update injection promo)">{pbadge.label}</span>}
                      {terr && <span className={`badge ${terr.cls}`} title="checkout returned token state">{terr.label}</span>}
                      {paypal && <span className="tag" title="init show paypal Channels available">paypal✓</span>}
                    </div>
                  </td>
                  <td>
                    {editingTagsId === t.id ? (
                      <input
                        className="input"
                        style={{ width: 110 }}
                        autoFocus
                        value={editingTagsVal}
                        placeholder="comma separated"
                        onChange={(e) => setEditingTagsVal(e.target.value)}
                        onBlur={() => {
                          saveTags(t, editingTagsVal);
                          setEditingTagsId("");
                        }}
                        onKeyDown={(e) => {
                          if (e.key === "Enter") {
                            saveTags(t, editingTagsVal);
                            setEditingTagsId("");
                          } else if (e.key === "Escape") {
                            setEditingTagsId("");
                          }
                        }}
                      />
                    ) : (
                      <div
                        style={{ display: "flex", flexWrap: "wrap", gap: 3, maxWidth: 150, cursor: "text" }}
                        onClick={() => {
                          setEditingTagsVal(tagsOf(t).join(", "));
                          setEditingTagsId(t.id);
                        }}
                        title="Click to edit the label (comma separated)"
                      >
                        {tagsOf(t).length === 0 ? (
                          <span className="muted" style={{ fontSize: 11 }}>+ Label</span>
                        ) : (
                          tagsOf(t).map((tag) => (
                            <span key={tag} className="tag" style={{ background: "var(--accent-dim)", color: "var(--accent)" }}>{tag}</span>
                          ))
                        )}
                      </div>
                    )}
                  </td>
                  <td className="muted" style={{ fontSize: 11 }}>
                    {t.last_run_at ? t.last_run_at.slice(0, 19).replace("T", " ") : "never"}
                  </td>
                  <td>
                    <span className={`badge ${badge.cls}`}>{badge.label}</span>
                  </td>
                  <td style={{ textAlign: "right", whiteSpace: "nowrap" }}>
                    <button
                      className="btn btn-ghost btn-sm"
                      onClick={() => handleProbe(t)}
                      disabled={busy || isRunning || probingId === t.id}
                      title="Probe session type / Discount qualifications / token state"
                    >
                      {probingId === t.id ? "Detecting…" : "detection"}
                    </button>
                    <button
                      className="btn btn-ghost btn-sm"
                      onClick={() => handleRunOne(t)}
                      disabled={busy || isRunning}
                    >
                      {isRunning ? "Carrying the chain…" : t.status === "success" ? "Mention again" : t.status === "failed" ? "Mention again" : "lift chain"}
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <div className="pager" style={{ display: "flex", gap: 8, alignItems: "center", marginTop: 12, flexWrap: "wrap" }}>
        <span className="muted" style={{ fontSize: 12 }}>
          {filtered.length === 0 ? "0 strip" : `${(safePage - 1) * pageSize + 1}-${Math.min(safePage * pageSize, filtered.length)} / ${filtered.length} strip`}
        </span>
        <button
          className="btn btn-sm"
          onClick={() => setPage(safePage - 1)}
          disabled={safePage <= 1}
        >
          Previous page
        </button>
        <span className="muted" style={{ fontSize: 12 }}>
          No. {safePage} / {totalPages} Page
        </span>
        <button
          className="btn btn-sm"
          onClick={() => setPage(safePage + 1)}
          disabled={safePage >= totalPages}
        >
          Next page
        </button>
        <select
          className="select select-sm"
          style={{ width: 90 }}
          value={pageSize}
          onChange={(e) => setPageSize(Number(e.target.value))}
        >
          {PAGE_SIZES.map((n) => (
            <option key={n} value={n}>{n} strip/Page</option>
          ))}
        </select>
      </div>
    </div>
  );
}
