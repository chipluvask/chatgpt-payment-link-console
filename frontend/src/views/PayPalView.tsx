import { useState, useEffect, useCallback, useRef, useMemo } from "react";
import { useStore } from "../store/useStore";
import { api } from "../api/client";
import type { BAAuthRecord, BAAuthConfig, BAStep, SMAQuote, BAFeedItem, BABaSnap } from "../types";
import { BA_STEPS, BA_STEP_CN } from "../types";

/* ── Authorization monitoring log type (The type is defined in types, store Hold global instance) ── */

const FEED_BADGE: Record<BAFeedItem["level"], string> = {
  ok: "badge-success",
  info: "badge-info",
  warn: "badge-warn",
  err: "badge-danger",
};

const FEED_LABEL: Record<BAFeedItem["level"], string> = {
  ok: "success",
  info: "information",
  warn: "warn",
  err: "fail",
};

const FEED_LEVEL_OPTIONS: { value: string; label: string }[] = [
  { value: "all", label: "All levels" },
  { value: "ok", label: "success" },
  { value: "info", label: "information" },
  { value: "warn", label: "warn" },
  { value: "err", label: "fail" },
];

/** The maximum number of rendering items in the monitoring log panel (Avoid lags in full-page rendering due to high concurrency) */
const FEED_MAX_DISPLAY = 200;

const CAPTCHA_LABELS: Record<string, string> = {
  iq: "IQ (reCAPTCHA Enterprise)",
  pi: "PI (hCaptcha passive)",
  none: "Not triggered",
  "": "—",
};

const STATUS_BADGE: Record<string, string> = {
  pending: "badge-warn",
  running: "badge-info",
  success: "badge-success",
  failed: "badge-danger",
};

/** Authorizing chip: Seconds self-timer (Only re-rendered version chip, Avoid full page re-rendering every second) */
function RunningChip({ r }: { r: BAAuthRecord }) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, []);
  return (
    <div
      className="running-chip"
      title={`${r.ba_token}\nnation ${r.identity_country || r.country || "?"}\n${r.last_msg || ""}`}
    >
      <span className="spinner" />
      <code className="mono">{r.ba_token.slice(0, 14)}…</code>
      <span>{BA_STEP_CN[r.step]}</span>
      <span className="tag">{r.identity_country || r.country || "?"}</span>
      {r.last_msg && <span className="feed-msg">{r.last_msg}</span>}
      <span className="feed-ts">
        {Math.max(0, Math.floor((now - (r.updated_at || now)) / 1000))}s
      </span>
    </div>
  );
}

const STATUS_LABELS: Record<string, string> = {
  pending: "Pending authorization",
  running: "Authorizing",
  success: "Authorized",
  failed: "fail",
};

const SOURCE_LABELS: Record<string, string> = {
  chain: "lift chain",
  manual: "Manual",
  inventory: "backfill",
};

const CAPTCHA_BADGE: Record<string, string> = {
  iq: "badge-info",
  pi: "badge-accent",
  none: "badge-muted",
  "": "badge-muted",
};

export function PayPalView() {
  const pushLog = useStore((s) => s.pushLog);
  const chainStates = useStore((s) => s.chainStates);

  const [baRecords, setBaRecords] = useState<BAAuthRecord[]>([]);
  const [config, setConfig] = useState<BAAuthConfig>({
    sms_provider: "smsbower",
    sms_api_key: "",
    sms_price: "0.05",
    sms_price_min: "0",
    sms_max_attempts: 12,
    sms_timeout: 15,
    exit_country: "BR",
    identity_country: "",
    sms_country: "",
    proxy_type: "711_sticky",
    captcha_strategy: "frontend_disable",
    buyer_mode: "elevation",
    max_retries: 3,
    max_flow_attempts: 2,
    follow_chain_country: true,
    fail_fast_geo: true,
    max_concurrent: 3,
    flow_timeout_s: 120,
  });
  const [loading, setLoading] = useState(false);
  const [filterStatus, setFilterStatus] = useState<string>("all");
  const [detailRecord, setDetailRecord] = useState<BAAuthRecord | null>(null);
  const [countryMeta, setCountryMeta] = useState<Record<string, { sms_supported: boolean; proxy_supported: boolean; sms_country_id: string }>>({});
  const [quotes, setQuotes] = useState<Record<string, SMAQuote[]>>({});
  const [quoteLoading, setQuoteLoading] = useState<string>("");

  // Manual import
  const [importText, setImportText] = useState("");
  const [importCountry, setImportCountry] = useState("");
  const [importEmail, setImportEmail] = useState("");
  const [importing, setImporting] = useState(false);
  const [lastImport, setLastImport] = useState<{ imported: number; exists: number; invalid: number } | null>(null);

  // Batch management
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [search, setSearch] = useState("");

  // Real-time monitoring logs (overall situation store: Switch columns/No loss when remounting)
  const baFeed = useStore((s) => s.baFeed);
  const baSnap = useStore((s) => s.baSnap);
  const pushBaFeed = useStore((s) => s.pushBaFeed);
  const clearBaFeed = useStore((s) => s.clearBaFeed);
  const setBaSnap = useStore((s) => s.setBaSnap);
  const rehydrateBaFeed = useStore((s) => s.rehydrateBaFeed);
  const baFeedRef = useRef<ReturnType<typeof useStore.getState>["baFeed"]>(baFeed);
  baFeedRef.current = baFeed;

  // Monitoring log filtering (Mimic real-time log page: level + Link drop down)
  const [feedLevel, setFeedLevel] = useState<string>("all");
  const [feedToken, setFeedToken] = useState<string>("all");
  const feedStreamRef = useRef<HTMLDivElement>(null);

  const feedTokens = useMemo(() => {
    const seen = new Set<string>();
    baFeed.forEach((f) => seen.add(f.token));
    return Array.from(seen);
  }, [baFeed]);

  const filteredFeed = useMemo(() => {
    return baFeed.filter((f) => {
      if (feedLevel !== "all" && f.level !== feedLevel) return false;
      if (feedToken !== "all" && f.token !== feedToken) return false;
      return true;
    });
  }, [baFeed, feedLevel, feedToken]);

  const displayFeed = useMemo(() => filteredFeed.slice(-FEED_MAX_DISPLAY), [filteredFeed]);

  // Automatic rolling bottom (Filter only when view changes)
  useEffect(() => {
    if (feedStreamRef.current) {
      feedStreamRef.current.scrollTop = feedStreamRef.current.scrollHeight;
    }
  }, [displayFeed]);

  const pendingFromChains = Object.values(chainStates).filter(
    (c) => c.status === "success" && c.url && c.url.includes("ba_token=BA-")
  );

  // use ref holds the latest value, Avoid generating new arrays for each rendering fetchBaRecords dependency changes
  // -> useEffect infinite reruns -> refresh button"Refreshing/refresh"flashing
  const pendingFromChainsRef = useRef<typeof pendingFromChains>([]);
  pendingFromChainsRef.current = pendingFromChains;
  const chainStatesRef = useRef(chainStates);
  chainStatesRef.current = chainStates;

  const fetchBaRecords = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api("/api/paypal/ba/records", "GET");
      if (res && res.records) {
        setBaRecords(res.records);
      }
    } catch {
      const mockRecords: BAAuthRecord[] = pendingFromChainsRef.current.map((c) => {
        const baMatch = c.url?.match(/ba_token=(BA-[A-Za-z0-9]+)/);
        const states = chainStatesRef.current;
        return {
          ba_token: baMatch?.[1] || "",
          email: c.email,
          approve_url: c.url || "",
          status: "pending" as const,
          step: "submit_email" as BAStep,
          country: c.country,
          chain_id: Object.keys(states).find(
            (k) => states[k] === c
          ) || "",
          captcha_type: "",
          sms_phone: "",
          error: "",
          created_at: c.startTime,
          updated_at: Date.now(),
        };
      });
      setBaRecords(mockRecords);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchBaRecords();
    // Only pull once when mounting, Avoid repeated request loops driven by link events
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Pull backend persistence configuration when mounting (Last modified settings), Override local initial defaults
  useEffect(() => {
    (async () => {
      try {
        const res = await api("/api/paypal/ba/config", "GET");
        if (res && res.config && typeof res.config === "object") {
          setConfig((prev) => ({ ...prev, ...res.config }));
        }
      } catch {
        /* Keep frontend default when backend is unavailable */
      }
    })();
  }, []);

  // Configuration changes are automatically saved to the backend (Place the order, Automatically resume next session); 1s Anti-shake prevents continuous input from blowing up the interface
  const saveConfigTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => {
    if (saveConfigTimer.current) clearTimeout(saveConfigTimer.current);
    saveConfigTimer.current = setTimeout(async () => {
      try {
        await api("/api/paypal/ba/config", "POST", config);
      } catch {
        /* Ignore if backend is unavailable */
      }
    }, 1000);
    return () => {
      if (saveConfigTimer.current) clearTimeout(saveConfigTimer.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [config]);

  // The link successfully generates new BA Automatically refresh the authorization queue when
  const lastFetchedPending = useRef(0);
  useEffect(() => {
    if (pendingFromChains.length > lastFetchedPending.current) {
      lastFetchedPending.current = pendingFromChains.length;
      fetchBaRecords();
    }
  }, [pendingFromChains.length, fetchBaRecords]);

  // country metadata (sms/proxy Availability)
  const loadCountryMeta = useCallback(async () => {
    try {
      const res = await api("/api/paypal/identity/countries", "GET");
      if (res && Array.isArray(res.countries)) {
        const meta: Record<string, { sms_supported: boolean; proxy_supported: boolean; sms_country_id: string }> = {};
        for (const c of res.countries as Array<{ code: string; sms_supported: boolean; proxy_supported: boolean; sms_country_id: string }>) {
          meta[c.code] = { sms_supported: c.sms_supported, proxy_supported: c.proxy_supported, sms_country_id: c.sms_country_id };
        }
        setCountryMeta(meta);
      }
    } catch {
      /* Remains empty when backend is unavailable */
    }
  }, []);

  useEffect(() => {
    loadCountryMeta();
  }, [loadCountryMeta]);

  // Real-time monitoring: 3s polling records, Compare the before and after status to generate authorization log stream (feed in global store)
  useEffect(() => {
    let alive = true;
    const tick = async () => {
      try {
        const res = await api("/api/paypal/ba/records", "GET");
        if (!alive || !res || !Array.isArray(res.records)) return;
        const records = res.records as BAAuthRecord[];
        setBaRecords(records);
        // first (store No snapshot, Such as after refreshing): Rebuild baseline, Don’t swipe the screen
        let prev = useStore.getState().baSnap;
        if (prev === null) {
          rehydrateBaFeed(records);
          prev = useStore.getState().baSnap;
        }
        const items: BAFeedItem[] = [];
        const next = new Map<string, BABaSnap>();
        for (const r of records) {
          const snap: BABaSnap = { status: r.status, step: r.step, error: r.error, source: r.source || "", last_msg: r.last_msg || "" };
          next.set(r.ba_token, snap);
          const p = prev?.get(r.ba_token);
          if (!p) {
            items.push({
              ts: Date.now(), token: r.ba_token, level: "info",
              msg: `${r.source === "manual" ? "Manual import" : "join queue"} · nation ${r.country || "?"}`,
            });
            continue;
          }
          if (p.status !== r.status) {
            if (r.status === "running") {
              items.push({ ts: Date.now(), token: r.ba_token, level: "info", msg: `Authorization start · step ${BA_STEP_CN[r.step]}` });
            } else if (r.status === "success") {
              items.push({ ts: Date.now(), token: r.ba_token, level: "ok", msg: "Authorization successful ✓" });
            } else if (r.status === "failed") {
              items.push({ ts: Date.now(), token: r.ba_token, level: "err", msg: `Authorization failed: ${r.error || "unknown reason"}` });
            } else if (r.status === "pending") {
              items.push({ ts: Date.now(), token: r.ba_token, level: "warn", msg: "Re-enlist (Try again)" });
            }
          } else if (r.status === "running" && p.step !== r.step) {
            items.push({ ts: Date.now(), token: r.ba_token, level: "info", msg: `step → ${BA_STEP_CN[r.step]}${r.last_msg ? ` · ${r.last_msg}` : ""}` });
          } else if (r.status === "running" && r.last_msg && p.last_msg !== r.last_msg) {
            items.push({ ts: Date.now(), token: r.ba_token, level: "info", msg: r.last_msg });
          } else if (r.status === "failed" && p.error !== r.error) {
            items.push({ ts: Date.now(), token: r.ba_token, level: "err", msg: `failed update: ${r.error || ""}` });
          }
        }
        if (prev !== null) {
          for (const key of prev.keys()) {
            if (!next.has(key)) {
              items.push({ ts: Date.now(), token: key, level: "warn", msg: "Record deleted" });
            }
          }
        }
        setBaSnap(next);
        items.forEach((item) => pushBaFeed(item));
      } catch {
        /* No error will be reported when the backend is unavailable */
      }
    };
    tick();
    const timer = setInterval(tick, 3000);
    return () => {
      alive = false;
      clearInterval(timer);
    };
  }, [pushBaFeed, setBaSnap, rehydrateBaFeed]);

  const loadQuote = useCallback(
    async (cc: string) => {
      if (!cc) return;
      setQuoteLoading(cc);
      try {
        const res = await api(`/api/paypal/sms/quote?country=${cc}`, "GET");
        if (res && Array.isArray(res.quotes)) {
          setQuotes((q) => ({ ...q, [cc]: res.quotes }));
        } else {
          setQuotes((q) => ({ ...q, [cc]: [] }));
        }
      } catch {
        setQuotes((q) => ({ ...q, [cc]: [] }));
      } finally {
        setQuoteLoading("");
      }
    },
    []
  );

  const ccOptions = useCallback((): string[] => {
    const keys = Object.keys(countryMeta);
    if (keys.length > 0) return keys;
    return ["BR", "US", "GB", "AU", "DE", "JP", "TH", "NL", "VN", "BH", "AO", "AE", "CI", "TR", "KR"];
  }, [countryMeta]);

  // Authorize action: Assemble by the country of this record config (Follow chain countries)
  const buildRecordConfig = useCallback(
    (r: BAAuthRecord): BAAuthConfig => {
      const cc = (config.follow_chain_country ? r.identity_country || r.country : config.identity_country) || r.country || "BR";
      return {
        ...config,
        identity_country: cc,
        sms_country: config.sms_country || cc,
        exit_country: cc,
      };
    },
    [config]
  );

  const handleStartAuth = async (r: BAAuthRecord) => {
    const baToken = r.ba_token;
    if (!baToken) return;
    const cc = (config.follow_chain_country ? r.identity_country || r.country : config.identity_country) || r.country || "BR";
    const meta = countryMeta[cc];
    if (meta && !meta.proxy_supported) {
      pushLog(`nation ${cc} No proxy available (Agent pool not covered), It is recommended to change the country`, "warn", "paypal");
    }
    // Confirm pop-up window: nation → Price quotation
    if (!quotes[cc]) loadQuote(cc);
    const q = quotes[cc];
    const quoteText =
      q && q.length > 0
        ? `${q[0].provider_id} @ $${q[0].price.toFixed(4)} (common ${q.length} Home)`
        : q
          ? "There is no code pickup provider available in this country, May be grayed out/Change country"
          : "Quote inquiry in progress…";
    const confirmText = `Authorized country: ${cc}\nform fields: Birthday/Country of Citizenship/Documents (according to kycFields)\nExport agent: Actual test verification before start-up\nReceive code: ${quoteText}\n\nConfirm that authorization is initiated in the country context?`;
    if (!window.confirm(confirmText)) return;
    pushLog(`BA Authorization start: ${baToken} (nation ${cc})`, "info", "paypal");
    try {
      const res = await api("/api/paypal/ba/authorize", "POST", {
        ba_token: baToken,
        config: buildRecordConfig(r),
      });
      if (res && res.ok) {
        pushLog(`BA Authorization is activated: ${baToken} (nation ${cc})`, "ok", "paypal");
        fetchBaRecords();
      } else if (res && res.error) {
        pushLog(`BA Authorization startup failed: ${res.error}`, "warn", "paypal");
      }
    } catch {
      pushLog(`BA Authorization startup failed (Backend is unavailable): ${baToken}`, "warn", "paypal");
    }
  };

  // Batch start (Universal: Incoming target token list)
  const startBatchTokens = async (tokens: string[], label: string) => {
    if (tokens.length === 0) {
      pushLog("There is no bootable BA Record", "warn", "paypal");
      return;
    }
    const targets = baRecords.filter((r) => tokens.includes(r.ba_token));
    const byCountry: Record<string, number> = {};
    for (const r of targets) {
      const cc = (r.identity_country || r.country || "BR").toUpperCase();
      byCountry[cc] = (byCountry[cc] || 0) + 1;
    }
    const groupText = Object.entries(byCountry)
      .map(([cc, n]) => `${cc} ×${n}`)
      .join(" / ");
    if (!window.confirm(`${label} ${tokens.length} strip:\n${groupText}\n\nEach article is distributed in its own country context. (Concurrency limit ${config.max_concurrent ?? 3})。confirm?`)) return;
    targets.forEach((r) => {
      const cc = (r.identity_country || r.country || "BR").toUpperCase();
      if (!quotes[cc]) loadQuote(cc);
    });
    pushLog(`${label}start up: ${tokens.length} strip BA (${groupText})`, "info", "paypal");
    try {
      const res = await api("/api/paypal/ba/batch", "POST", {
        ba_tokens: tokens,
        config,
      });
      if (res && res.ok) {
        pushLog(`${label}Started: ${res.started}/${res.total} strip`, "ok", "paypal");
        if (res.skipped && Object.keys(res.skipped).length > 0) {
          pushLog(`${label}jump over: ${JSON.stringify(res.skipped)}`, "warn", "paypal");
        }
        fetchBaRecords();
        setSelected(new Set());
      }
    } catch {
      pushLog(`${label}Startup failed (Backend is unavailable)`, "warn", "paypal");
    }
  };

  const handleBatchAuth = () => {
    const pending = baRecords.filter((r) => r.status === "pending");
    startBatchTokens(pending.map((r) => r.ba_token), "Volume licensing");
  };

  // Manual import BA Link / bare token
  const [importError, setImportError] = useState("");
  const handleImport = async () => {
    const text = importText.trim();
    if (!text) return;
    setImporting(true);
    setImportError("");
    try {
      const res = await api("/api/paypal/ba/import", "POST", {
        text,
        country: importCountry || config.identity_country || "",
        email: importEmail.trim(),
        source: "manual",
      });
      if (res && res.ok) {
        const summary = {
          imported: (res.imported || []).length,
          exists: (res.exists || []).length,
          invalid: (res.invalid || []).length,
        };
        setLastImport(summary);
        pushLog(
          `Manual import: New ${summary.imported} / repeat ${summary.exists} / invalid ${summary.invalid}`,
          summary.imported > 0 ? "ok" : "warn",
          "paypal"
        );
        setImportText("");
        setImportEmail("");
        fetchBaRecords();
      } else if (res && res.error) {
        const msg = `Import failed: ${res.error}`;
        setImportError(msg);
        pushLog(msg, "warn", "paypal");
      } else {
        const msg = `Import failed: Backend returns exception (${JSON.stringify(res).slice(0, 120)})`;
        setImportError(msg);
        pushLog(msg, "warn", "paypal");
      }
    } catch (err) {
      const msg = `Import failed: Request exception (${(err as Error)?.message || "Backend is unavailable"})`;
      setImportError(msg);
      pushLog(msg, "warn", "paypal");
    } finally {
      setImporting(false);
    }
  };

  // rerun (failed Try again + success Unified entrance for reruns)
  const handleRetryTokens = async (tokens: string[]) => {
    const targets = baRecords.filter(
      (r) => tokens.includes(r.ba_token) && (r.status === "failed" || r.status === "success")
    );
    if (targets.length === 0) {
      pushLog("There are no reruns in the selected records (failed/success)", "warn", "paypal");
      return;
    }
    const hasSuccess = targets.some((r) => r.status === "success");
    const groupText = [...new Set(targets.map((r) => (r.identity_country || r.country || "BR").toUpperCase()))].join(" / ");
    if (!window.confirm(
      hasSuccess
        ? `rerun ${targets.length} strip BA (Contains authorized records, New access numbers will be consumed/new card)\n${groupText}\nConcurrency limit ${config.max_concurrent ?? 3}。confirm?`
        : `Try again ${targets.length} failed BA (${groupText}, Concurrency limit ${config.max_concurrent ?? 3})?`
    )) return;
    pushLog(`${hasSuccess ? "rerun" : "Batch retry"}: ${targets.length} strip BA (${groupText})`, "info", "paypal");
    try {
      const res = await api("/api/paypal/ba/retry", "POST", {
        ba_tokens: targets.map((r) => r.ba_token),
        config: { ...config, allow_success_retry: hasSuccess },
      });
      if (res && res.ok) {
        pushLog(`Started: ${res.started}/${res.total} strip`, "ok", "paypal");
        if (res.skipped && Object.keys(res.skipped).length > 0) {
          pushLog(`jump over: ${JSON.stringify(res.skipped)}`, "warn", "paypal");
        }
        fetchBaRecords();
        setSelected(new Set());
      }
    } catch {
      pushLog("Rerun failed (Backend is unavailable)", "warn", "paypal");
    }
  };

  // Batch delete
  const handleDeleteTokens = async (tokens: string[]) => {
    const targets = baRecords.filter((r) => tokens.includes(r.ba_token));
    if (targets.length === 0) return;
    const runningN = targets.filter((r) => r.status === "running").length;
    if (!window.confirm(`delete ${targets.length} records?${runningN > 0 ? `\n⚠ ${runningN} The article is being authorized, The task will continue to be executed, Remove from queue only` : ""}`)) return;
    try {
      const res = await api("/api/paypal/ba/delete", "POST", {
        ba_tokens: targets.map((r) => r.ba_token),
      });
      if (res && res.ok) {
        pushLog(`Deleted ${res.deleted} strip BA Record`, "ok", "paypal");
        fetchBaRecords();
        setSelected(new Set());
      }
    } catch {
      pushLog("Delete failed (Backend is unavailable)", "warn", "paypal");
    }
  };

  // Clear (failed / all)
  const handleClear = async (status: "failed" | "all") => {
    const targets = status === "failed"
      ? baRecords.filter((r) => r.status === "failed")
      : baRecords;
    const label = status === "failed" ? "All failure records" : "All records";
    if (targets.length === 0) {
      pushLog(`Nothing to clear${label}`, "warn", "paypal");
      return;
    }
    if (!window.confirm(`Clear${label} (${targets.length} strip)?\nThis operation is irreversible (Tasks already authorized will not be affected)`)) return;
    try {
      const res = await api("/api/paypal/ba/clear", "POST", { status });
      if (res && res.ok) {
        pushLog(`Cleared ${res.removed} records (${res.status})`, "ok", "paypal");
        fetchBaRecords();
        setSelected(new Set());
      }
    } catch {
      pushLog("Clearing failed (Backend is unavailable)", "warn", "paypal");
    }
  };

  const handleCopy = async (r: BAAuthRecord) => {
    try {
      await navigator.clipboard.writeText(r.approve_url || `https://www.paypal.com/agreements/approve?ba_token=${r.ba_token}`);
      pushLog(`Copied BA Link: ${r.ba_token}`, "ok", "paypal");
    } catch {
      pushLog(`Copy failed: ${r.ba_token}`, "warn", "paypal");
    }
  };

  const searchTerm = search.trim().toLowerCase();
  const filteredRecords = baRecords.filter(
    (r) =>
      (filterStatus === "all" || r.status === filterStatus) &&
      (!searchTerm ||
        r.ba_token.toLowerCase().includes(searchTerm) ||
        r.email.toLowerCase().includes(searchTerm))
  );

  const selectedList = baRecords.filter((r) => selected.has(r.ba_token));
  const runningList = baRecords.filter((r) => r.status === "running");

  // Price range statistics for receiving codes (The slider track is mapped according to the actual price of the platform + Display price ranges in ascending order)
  const smsQuoteCc = (config.sms_country || config.identity_country || "BR").toUpperCase();
  const smsQuotes = quotes[smsQuoteCc];
  const smsPrices =
    smsQuotes && smsQuotes.length > 0 ? smsQuotes.map((q) => q.price).sort((a, b) => a - b) : [];
  const smsTrackMin = smsPrices.length > 0 ? smsPrices[0] : 0;
  const smsTrackMax = smsPrices.length > 0 ? smsPrices[smsPrices.length - 1] : 0.5;
  const smsMin = parseFloat(config.sms_price_min || "0") || 0;
  const smsMax = parseFloat(config.sms_price) || 0; // 0 = No limit
  const smsInRange =
    smsPrices.length > 0
      ? smsPrices.filter((p) => p >= smsMin && (smsMax > 0 ? p <= smsMax : true))
      : [];
  const smsInRangeCount = smsInRange.length;

  // orbital percentage <-> price mapping (0~100 integer, Dragging natively by slider)
  const priceToV = (p: number) => {
    if (smsTrackMax <= smsTrackMin) return 100;
    return Math.round(((p - smsTrackMin) / (smsTrackMax - smsTrackMin)) * 100);
  };
  const vToPrice = (v: number) => smsTrackMin + (v / 100) * (smsTrackMax - smsTrackMin);
  const fmtPrice = (p: number) => String(parseFloat(p.toFixed(4)));

  const sliderMinV = smsMin <= 0 ? 0 : Math.min(100, priceToV(smsMin));
  const sliderMaxV = smsMax <= 0 ? 100 : Math.min(100, priceToV(smsMax));

  useEffect(() => {
    if (smsQuoteCc && !quotes[smsQuoteCc]) loadQuote(smsQuoteCc);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [smsQuoteCc]);

  // Check logic
  const toggleSelect = (tok: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(tok)) next.delete(tok);
      else next.add(tok);
      return next;
    });
  };

  const allVisibleSelected =
    filteredRecords.length > 0 && filteredRecords.every((r) => selected.has(r.ba_token));

  const toggleSelectAll = () => {
    setSelected(
      allVisibleSelected ? new Set() : new Set(filteredRecords.map((r) => r.ba_token))
    );
  };

  const stats = {
    total: baRecords.length,
    pending: baRecords.filter((r) => r.status === "pending").length,
    running: baRecords.filter((r) => r.status === "running").length,
    success: baRecords.filter((r) => r.status === "success").length,
    failed: baRecords.filter((r) => r.status === "failed").length,
  };

  const successRate =
    stats.total > 0
      ? ((stats.success / (stats.success + stats.failed || 1)) * 100).toFixed(0)
      : "—";

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h2 className="page-title">PayPal Payment authorization</h2>
          <p className="page-sub">
            PayPal BA (Billing Agreement) Authorization process — Payment authorization executed independently after the chain segment is completed
          </p>
        </div>
        <div className="page-actions">
          <button
            className="btn"
            onClick={fetchBaRecords}
            disabled={loading}
            style={{ minWidth: 78 }}
          >
            {loading ? "Refreshing…" : "refresh"}
          </button>
          <button
            className="btn btn-primary"
            onClick={handleBatchAuth}
            disabled={stats.pending === 0}
          >
            Volume licensing ({stats.pending})
          </button>
        </div>
      </div>

      {/* Compact statistics bar: single line, Does not take up a lot of space */}
      <div
        className="card"
        style={{ marginBottom: 14, padding: "8px 14px", display: "flex", alignItems: "center", gap: 16, flexWrap: "wrap" }}
      >
        <span className="tag">BA total <b style={{ marginLeft: 4 }}>{stats.total}</b></span>
        <span className="tag" style={{ color: "var(--warn)" }}>Pending authorization {stats.pending}</span>
        <span className="tag" style={{ color: "var(--info)" }}>Authorizing {stats.running}</span>
        <span className="tag" style={{ color: "var(--ok)" }}>Authorized {stats.success}</span>
        <span className="tag" style={{ color: "var(--danger)" }}>fail {stats.failed}</span>
        <span className="tag">success rate {successRate}%</span>
        <div style={{ flex: 1 }} />
        <span className="card-hint">3s Auto refresh · See the monitoring flow below for real-time steps.</span>
      </div>

      {/* BA Authorized real-time monitoring */}
      <div className="card" style={{ marginBottom: 14 }}>
        <div className="card-head">
          <span className="card-title">BA Authorized real-time monitoring</span>
          <span className="card-hint">3s polling · real time steps/Take a number/OTP/Authorization result</span>
          <div style={{ flex: 1 }} />
          <select
            className="select"
            style={{ width: 110 }}
            value={feedLevel}
            onChange={(e) => setFeedLevel(e.target.value)}
            title="Filter by log level"
          >
            {FEED_LEVEL_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
          <select
            className="select"
            style={{ width: 130 }}
            value={feedToken}
            onChange={(e) => setFeedToken(e.target.value)}
            title="according to BA Link filtering"
          >
            <option value="all">All links</option>
            {feedTokens.map((tok) => (
              <option key={tok} value={tok}>
                {tok.slice(0, 12)}…
              </option>
            ))}
          </select>
          <span className="tag">Running {stats.running}</span>
          <button className="btn btn-sm btn-ghost" onClick={() => clearBaFeed()}>
            Clear log
          </button>
        </div>
        <div className="card-body">
          {runningList.length > 0 && (
            <div className="running-strip">
              {runningList.map((r) => (
                <RunningChip key={r.ba_token} r={r} />
              ))}
            </div>
          )}
          {displayFeed.length === 0 ? (
            <div className="feed-empty">
              {baFeed.length === 0
                ? "No authorization log yet — When the queue status changes (import/start up/step/Take a number/OTP/success/fail/delete) Shown here in real time"
                : "There are no logs under the current filter conditions"}
            </div>
          ) : (
            <div className="log-panel" style={{ maxHeight: 340 }}>
              <div className="log-body" ref={feedStreamRef}>
                {displayFeed.map((f, i) => (
                  <div className={`log-line ${f.level}`} key={`${f.ts}-${i}`}>
                    <span className="log-ts">
                      {new Date(f.ts).toLocaleTimeString("zh-CN", { hour12: false })}
                    </span>
                    <span
                      className="log-chain"
                      title={`Click to filter this link: ${f.token}`}
                      style={{ cursor: "pointer", textDecoration: "underline dotted" }}
                      onClick={() => {
                        setFeedToken(f.token);
                        setFeedLevel("all");
                      }}
                    >
                      {f.token.slice(0, 8)}
                    </span>
                    <span className="log-msg">{f.msg}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Manually import panels */}
      <div className="card" style={{ marginBottom: 14 }}>
        <div className="card-head">
          <span className="card-title">Manual import BA</span>
          <span className="card-hint">Paste paypal.com/agreements/approve link or naked BA-xxx token, one per line (comma/Can also be separated by spaces)</span>
        </div>
        <div className="card-body">
          <textarea
            className="textarea"
            rows={4}
            placeholder={"https://www.paypal.com/agreements/approve?ba_token=BA-xxxxxxxx\nBA-xxxxxxxx\nBA-yyyyyyyy, https://…approve?ba_token=BA-zzzzzzzz"}
            value={importText}
            onChange={(e) => setImportText(e.target.value)}
            style={{ width: "100%", resize: "vertical" }}
          />
          <div style={{ display: "flex", gap: 8, marginTop: 10, alignItems: "center", flexWrap: "wrap" }}>
            <select
              className="select"
              value={importCountry}
              onChange={(e) => setImportCountry(e.target.value)}
              title="Default country for imported records (You can still follow the configuration when authorizing)"
            >
              <option value="">nation: Follow the exporting country of the chain</option>
              {ccOptions().map((cc) => {
                const meta = countryMeta[cc];
                const disabled = meta ? !meta.sms_supported || !meta.proxy_supported : false;
                return (
                  <option key={cc} value={cc} disabled={disabled}>
                    {cc}
                    {meta && !meta.proxy_supported ? " (No proxy)" : ""}
                    {meta && !meta.sms_supported ? " (No access code)" : ""}
                  </option>
                );
              })}
            </select>
            <input
              className="input"
              style={{ width: 220 }}
              placeholder="Mail (Optional)"
              value={importEmail}
              onChange={(e) => setImportEmail(e.target.value)}
            />
            <button
              className="btn btn-primary"
              onClick={handleImport}
              disabled={importing || !importText.trim()}
              style={{ minWidth: 108 }}
            >
              {importing ? "Importing…" : "Import into queue"}
            </button>
            {lastImport && (
              <span className="setting-hint">
                last import: New {lastImport.imported} / repeat {lastImport.exists} / invalid {lastImport.invalid}
              </span>
            )}
            {importError && (
              <span style={{ color: "var(--danger)", fontSize: 12 }}>{importError}</span>
            )}
          </div>
        </div>
      </div>

      <div className="grid grid-main">
        <div className="card">
          <div className="card-head">
            <span className="card-title">BA authorization queue</span>
            <div className="tabs">
              {["all", "pending", "running", "success", "failed"].map((f) => (
                <button
                  key={f}
                  className={`tab ${filterStatus === f ? "active" : ""}`}
                  onClick={() => setFilterStatus(f)}
                >
                  {f === "all" ? "all" : STATUS_LABELS[f] || f}
                  {f === "all" ? ` (${baRecords.length})` : ` (${baRecords.filter((r) => r.status === f).length})`}
                </button>
              ))}
            </div>
          </div>

          <div
            style={{
              display: "flex",
              gap: 8,
              alignItems: "center",
              padding: "8px 12px",
              borderBottom: "1px solid var(--border-faint)",
              flexWrap: "wrap",
            }}
          >
            <input
              className="input"
              style={{ flex: 1, minWidth: 180, maxWidth: 320 }}
              placeholder="search BA Token / Mail…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
            <span style={{ flex: 1 }} />
            <button
              className="btn btn-sm"
              onClick={() => handleClear("failed")}
              disabled={stats.failed === 0}
            >
              Clearing failed ({stats.failed})
            </button>
            <button
              className="btn btn-sm btn-danger"
              onClick={() => handleClear("all")}
              disabled={baRecords.length === 0}
            >
              Clear all
            </button>
          </div>

          {/* Batch operation bar */}
          {selected.size > 0 && (
            <div
              style={{
                display: "flex",
                gap: 8,
                alignItems: "center",
                padding: "8px 12px",
                borderBottom: "1px solid var(--border-faint)",
                background: "var(--bg-raised)",
                flexWrap: "wrap",
              }}
            >
              <span className="tag">Selected {selected.size}</span>
              <button
                className="btn btn-sm btn-primary"
                onClick={() =>
                  startBatchTokens(
                    selectedList.filter((r) => r.status === "pending").map((r) => r.ba_token),
                    "Authorize selected"
                  )
                }
                disabled={selectedList.every((r) => r.status !== "pending")}
              >
                Authorize selected
              </button>
              <button
                className="btn btn-sm"
                onClick={() => handleRetryTokens([...selected])}
                disabled={selectedList.every((r) => r.status !== "failed" && r.status !== "success")}
              >
                Rerun selected
              </button>
              <button
                className="btn btn-sm btn-danger"
                onClick={() => handleDeleteTokens([...selected])}
              >
                Delete selected
              </button>
              <button className="btn btn-sm btn-ghost" onClick={() => setSelected(new Set())}>
                Deselect
              </button>
            </div>
          )}

          {filteredRecords.length === 0 ? (
            <div className="empty">
              <div className="empty-icon">💳</div>
              <div className="empty-title">
                {pendingFromChains.length === 0 && !importText.trim()
                  ? "None yet BA Record — Automatically import after successful chain extraction, Or paste manually above BA Link"
                  : "No matching records yet"}
              </div>
            </div>
          ) : (
            <div className="table-wrap" style={{ border: "none", borderRadius: 0, borderTop: "1px solid var(--border-faint)" }}>
              <table className="table">
                <thead>
                  <tr>
                    <th style={{ width: 32, textAlign: "center" }}>
                      <input
                        type="checkbox"
                        checked={allVisibleSelected}
                        onChange={toggleSelectAll}
                        onClick={(e) => e.stopPropagation()}
                        style={{ accentColor: "var(--accent)" }}
                      />
                    </th>
                    <th>BA Token</th>
                    <th>Mail</th>
                    <th>state</th>
                    <th>current step</th>
                    <th>Captcha</th>
                    <th>nation</th>
                    <th>form country</th>
                    <th>Acceptance price/Number</th>
                    <th>source</th>
                    <th style={{ textAlign: "right" }}>operate</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredRecords.map((r) => (
                    <tr
                      key={r.ba_token}
                      className={selected.has(r.ba_token) ? "row-selected" : ""}
                      style={{ cursor: "pointer" }}
                      onClick={() => setDetailRecord(r)}
                    >
                      <td style={{ textAlign: "center" }}>
                        <input
                          type="checkbox"
                          checked={selected.has(r.ba_token)}
                          onChange={() => toggleSelect(r.ba_token)}
                          onClick={(e) => e.stopPropagation()}
                          style={{ accentColor: "var(--accent)" }}
                        />
                      </td>
                      <td>
                        <code className="mono">{r.ba_token.slice(0, 16)}…</code>
                      </td>
                      <td>{r.email || "—"}</td>
                      <td>
                        <span className={`badge ${STATUS_BADGE[r.status] || "badge-muted"}`}>
                          {STATUS_LABELS[r.status]}
                        </span>
                      </td>
                      <td>
                        <span className="tag">{BA_STEP_CN[r.step]}</span>
                      </td>
                      <td>
                        <span className={`badge ${CAPTCHA_BADGE[r.captcha_type] || "badge-muted"}`}>
                          {r.captcha_type?.toUpperCase() || "—"}
                        </span>
                      </td>
                      <td>
                        <span className="tag">{r.country || "—"}</span>
                      </td>
                      <td>
                        <span className="tag">{r.identity_country || r.country || "—"}</span>
                      </td>
                      <td>
                        {r.sms_price ? (
                          <span className="tag" title={`provider ${r.sms_provider_id || "?"} · ${r.sms_phone || "No number"}`}>
                            ${Number(r.sms_price).toFixed(4)}
                          </span>
                        ) : (
                          <span style={{ color: "var(--text-faint)" }}>—</span>
                        )}
                      </td>
                      <td>
                        <span className="tag">{SOURCE_LABELS[r.source || "chain"] || r.source || "—"}</span>
                      </td>
                      <td style={{ textAlign: "right", whiteSpace: "nowrap" }}>
                        {r.status === "pending" && (
                          <button
                            className="btn btn-sm"
                            onClick={(e) => {
                              e.stopPropagation();
                              handleStartAuth(r);
                            }}
                          >
                            Authorize
                          </button>
                        )}
                        {(r.status === "failed" || r.status === "success") && (
                          <button
                            className="btn btn-sm"
                            title={
                              r.status === "success"
                                ? "Re-running will consume new accounts/new card, Used for scenarios such as subscription not taking effect"
                                : "Go through the complete authorization process again"
                            }
                            onClick={(e) => {
                              e.stopPropagation();
                              handleRetryTokens([r.ba_token]);
                            }}
                          >
                            rerun
                          </button>
                        )}
                        {r.status === "running" && <span className="spinner" />}
                        <button
                          className="btn btn-sm btn-ghost"
                          onClick={(e) => {
                            e.stopPropagation();
                            handleCopy(r);
                          }}
                        >
                          copy
                        </button>
                        <button
                          className="btn btn-sm btn-danger"
                          onClick={(e) => {
                            e.stopPropagation();
                            handleDeleteTokens([r.ba_token]);
                          }}
                        >
                          delete
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        <div className="card">
          <div className="card-head">
            <span className="card-title">Authorization configuration</span>
          </div>
          <div className="card-body">
            <div className="setting-row">
              <span className="setting-label">Code receiving platform</span>
              <div className="setting-control">
                <select
                  className="select"
                  value={config.sms_provider}
                  onChange={(e) =>
                    setConfig({ ...config, sms_provider: e.target.value })
                  }
                >
                  <option value="smsbower">SMSBower (Already connected)</option>
                  <option value="sms_activate" disabled>SMS-Activate (Not connected)</option>
                  <option value="5sim" disabled>5SIM (Not connected)</option>
                </select>
              </div>
            </div>
            <div className="setting-row">
              <span className="setting-label">Code receiving platform API Key</span>
              <div className="setting-control">
                <input
                  className="input"
                  type="password"
                  value={config.sms_api_key || ""}
                  placeholder="Leave blank to use backend/ba_paypal/.env in key"
                  onChange={(e) =>
                    setConfig({ ...config, sms_api_key: e.target.value })
                  }
                  style={{ width: 260 }}
                />
                <span className="setting-hint">Save in frontend config, Override when authorizing .env (This session only)</span>
              </div>
            </div>
            <div className="setting-row">
              <span className="setting-label">Code receiving price range (USD/Number)</span>
              <div className="setting-control" style={{ minWidth: 380 }}>
                <div className="range-dual-wrap">
                  <div className="range-dual">
                    <div className="range-dual-track" />
                    <div
                      className="range-dual-fill"
                      style={{ left: `${sliderMinV}%`, width: `${Math.max(0, sliderMaxV - sliderMinV)}%` }}
                    />
                    <input
                      type="range"
                      min={0}
                      max={100}
                      step={1}
                      className="range-dual-input range-dual-min"
                      value={sliderMinV}
                      title="Lower bound of interval: Suppliers with prices lower than this will not be called (default 0 = No limit)"
                      onChange={(e) => {
                        const v = Math.min(Number(e.target.value), sliderMaxV);
                        setConfig({
                          ...config,
                          sms_price_min: v <= 0 ? "0" : fmtPrice(vToPrice(v)),
                        });
                      }}
                    />
                    <input
                      type="range"
                      min={0}
                      max={100}
                      step={1}
                      className="range-dual-input range-dual-max"
                      value={sliderMaxV}
                      title="Upper limit of range: Suppliers with prices higher than this will not be called (Drag to the right = No limit)"
                      onChange={(e) => {
                        const v = Math.max(Number(e.target.value), sliderMinV);
                        setConfig({
                          ...config,
                          sms_price: v >= 100 ? "0" : fmtPrice(vToPrice(v)),
                        });
                      }}
                    />
                  </div>
                  <div className="range-dual-labels">
                    <span className="range-dual-val">
                      lower limit {smsMin > 0 ? `$${fmtPrice(smsMin)}` : "$0"}
                    </span>
                    <span className="range-dual-val">
                      upper limit {smsMax > 0 ? `$${fmtPrice(smsMax)}` : "∞ No limit"}
                    </span>
                  </div>
                </div>
                <span className="setting-hint">
                  {smsPrices.length > 0
                    ? `Take numbers in ascending order according to the actual price on the platform: within the range ${smsInRangeCount} Home available · ${smsInRange
                        .slice(0, 5)
                        .map((p) => `$${p.toFixed(4)}`)
                        .join(" / ")}${smsInRange.length > 5 ? " …" : ""} (${smsQuoteCc})`
                    : `Quote inquiry in progress (${smsQuoteCc})…`}
                </span>
              </div>
            </div>
            <div className="setting-row">
              <span className="setting-label">Number change timeout (Second)</span>
              <div className="setting-control">
                <input
                  className="input"
                  type="number"
                  value={config.sms_timeout}
                  onChange={(e) =>
                    setConfig({
                      ...config,
                      sms_timeout: parseInt(e.target.value) || 15,
                    })
                  }
                />
              </div>
            </div>
            <div className="setting-row">
              <span className="setting-label">Number of number retry rounds</span>
              <div className="setting-control">
                <input
                  className="input"
                  type="number"
                  min={1}
                  value={config.sms_max_attempts ?? 12}
                  title="Cool down after all suppliers in the range fail 2s Retry the whole round, Don’t give up until the number of rounds is reached"
                  onChange={(e) =>
                    setConfig({
                      ...config,
                      sms_max_attempts: Math.max(1, parseInt(e.target.value) || 12),
                    })
                  }
                />
                <span className="setting-hint">every round = Try all prices in the range in ascending order; Failure to cool down 2s Another round</span>
              </div>
            </div>
            <div className="setting-row">
              <span className="setting-label">Follow the chain country</span>
              <div className="setting-control">
                <label className="toggle">
                  <input
                    type="checkbox"
                    checked={config.follow_chain_country !== false}
                    onChange={(e) =>
                      setConfig({ ...config, follow_chain_country: e.target.checked })
                    }
                  />
                  <span className={`toggle-slider ${config.follow_chain_country !== false ? "on" : ""}`} />
                </label>
                <span className="setting-hint">
                  {config.follow_chain_country !== false
                    ? "Authorized country = lift chain checkout section exit IP nation"
                    : "Use manual country below"}
                </span>
              </div>
            </div>
            {config.follow_chain_country === false && (
              <div className="setting-row">
                <span className="setting-label">Exporting country</span>
                <div className="setting-control">
                  <select
                    className="select"
                    value={config.identity_country || "BR"}
                    onChange={(e) => {
                      const cc = e.target.value;
                      setConfig({
                        ...config,
                        identity_country: cc,
                        exit_country: cc,
                      });
                      if (!quotes[cc]) loadQuote(cc);
                    }}
                  >
                    {ccOptions().map((cc) => {
                      const meta = countryMeta[cc];
                      const disabled = meta ? !meta.sms_supported || !meta.proxy_supported : false;
                      return (
                        <option key={cc} value={cc} disabled={disabled}>
                          {cc}
                          {meta && !meta.proxy_supported ? " (No proxy)" : ""}
                          {meta && !meta.sms_supported ? " (No access code)" : ""}
                        </option>
                      );
                    })}
                  </select>
                  {quoteLoading === (config.identity_country || "BR") && <span className="spinner" style={{ marginLeft: 8 }} />}
                  {quotes[config.identity_country || "BR"] && (
                    <span className="setting-hint">
                      {quotes[config.identity_country || "BR"].length > 0
                        ? `lowest ${quotes[config.identity_country || "BR"][0].provider_id} $${quotes[config.identity_country || "BR"][0].price.toFixed(4)}`
                        : "No access code supplier in the country"}
                    </span>
                  )}
                </div>
              </div>
            )}
            <div className="setting-row">
              <span className="setting-label">Counter code receiving country</span>
              <div className="setting-control">
                <select
                  className="select"
                  value={config.sms_country || config.identity_country || "BR"}
                  onChange={(e) =>
                    setConfig({ ...config, sms_country: e.target.value })
                  }
                >
                  {ccOptions().map((cc) => (
                    <option key={cc} value={cc}>{cc}</option>
                  ))}
                </select>
                <span className="setting-hint">Default follows export country</span>
              </div>
            </div>
            <div className="setting-row">
              <span className="setting-label">Concurrency limit</span>
              <div className="setting-control">
                <input
                  className="input"
                  type="number"
                  min={1}
                  value={config.max_concurrent ?? 3}
                  onChange={(e) =>
                    setConfig({
                      ...config,
                      max_concurrent: parseInt(e.target.value) || 3,
                    })
                  }
                />
                <span className="setting-hint">Authorization segment independent semaphore (Lifting chain segments are not affected)</span>
              </div>
            </div>
            <div className="setting-row">
              <span className="setting-label">geo Stop if verification fails</span>
              <div className="setting-control">
                <label className="toggle">
                  <input
                    type="checkbox"
                    checked={config.fail_fast_geo !== false}
                    onChange={(e) =>
                      setConfig({ ...config, fail_fast_geo: e.target.checked })
                    }
                  />
                  <span className={`toggle-slider ${config.fail_fast_geo !== false ? "on" : ""}`} />
                </label>
                <span className="setting-hint">Tested agent export countries before launch, Inconsistent and out of process</span>
              </div>
            </div>
            <div className="setting-row">
              <span className="setting-label">Agent type</span>
              <div className="setting-control">
                <select
                  className="select"
                  value={config.proxy_type}
                  onChange={(e) =>
                    setConfig({ ...config, proxy_type: e.target.value })
                  }
                >
                  <option value="711_sticky">711 residential agency (Sticky) — default</option>
                  <option value="singbox">sing-box Node priority</option>
                  <option value="qg">QG Tunnel priority</option>
                </select>
              </div>
            </div>
            <div className="setting-row">
              <span className="setting-label">Captcha Strategy</span>
              <div className="setting-control">
                <select
                  className="select"
                  value={config.captcha_strategy}
                  onChange={(e) =>
                    setConfig({
                      ...config,
                      captcha_strategy: e.target.value,
                    })
                  }
                >
                  <option value="frontend_disable">frontend_disable (local bypass, 8/11 path to success)</option>
                  <option value="manual_required">manual_required (Manual verification)</option>
                </select>
              </div>
            </div>
            <div className="setting-row">
              <span className="setting-label">Maximum retries (Card/process)</span>
              <div className="setting-control">
                <input
                  className="input"
                  type="number"
                  value={config.max_retries}
                  onChange={(e) =>
                    setConfig({
                      ...config,
                      max_retries: parseInt(e.target.value) || 3,
                    })
                  }
                />
              </div>
            </div>
            <div className="setting-row">
              <span className="setting-label">Maximum process attempts</span>
              <div className="setting-control">
                <input
                  className="input"
                  type="number"
                  min={1}
                  value={config.max_flow_attempts ?? 2}
                  onChange={(e) =>
                    setConfig({
                      ...config,
                      max_flow_attempts: parseInt(e.target.value) || 2,
                    })
                  }
                />
              </div>
            </div>
            <div className="setting-row">
              <span className="setting-label">Process timeout (Second)</span>
              <div className="setting-control">
                <input
                  className="input"
                  type="number"
                  min={30}
                  step={10}
                  value={config.flow_timeout_s ?? 120}
                  title="The longest time a single authorization process takes, Timeout forces failure to end (default 120s)"
                  onChange={(e) =>
                    setConfig({
                      ...config,
                      flow_timeout_s: parseInt(e.target.value) || 120,
                    })
                  }
                  style={{ width: 84 }}
                />
                <span className="setting-hint">Timeout forced closing, Prevent authorization stuck and occupy concurrency</span>
              </div>
            </div>
          </div>

          <div className="card-body" style={{ borderTop: "1px solid var(--border-faint)" }}>
            <div className="section-head">
              <span className="section-title">Authorization link</span>
            </div>
            <div className="flow-chain" style={{ borderBottom: "none", padding: "4px 0 0" }}>
              <span className="flow-node">Stripe confirm</span>
              <span className="flow-arrow">→</span>
              <span className="flow-node">pm-redirects/authorize</span>
              <span className="flow-arrow">→</span>
              <span className="flow-node accent">PayPal BA</span>
              <span className="flow-arrow">→</span>
              <span className="flow-node">EUAT</span>
            </div>
          </div>
        </div>
      </div>

      {/* Details popup */}
      {detailRecord && (
        <div className="overlay" onClick={() => setDetailRecord(null)}>
          <div className="sheet" onClick={(e) => e.stopPropagation()}>
            <div className="sheet-head">
              <span className="sheet-title">BA Authorization details</span>
              <button className="icon-btn" onClick={() => setDetailRecord(null)} aria-label="closure">✕</button>
            </div>
            <div className="sheet-body">
              <div className="detail-list">
                <div
                  className="detail-row"
                  style={{ cursor: "pointer" }}
                  title="Click to jump: Monitor flow filters for this link + Queue table locates the record"
                  onClick={() => {
                    setDetailRecord(null);
                    setFeedToken(detailRecord.ba_token);
                    setFeedLevel("all");
                    setFilterStatus("all");
                    setSearch(detailRecord.ba_token);
                  }}
                >
                  <span className="dr-label">BA Token</span>
                  <span className="dr-value" style={{ color: "var(--accent-strong)" }}>
                    {detailRecord.ba_token} <span style={{ fontSize: 11, opacity: 0.6 }}>→ Filter positioning</span>
                  </span>
                </div>
                <div className="detail-row">
                  <span className="dr-label">Mail</span>
                  <span className="dr-value">{detailRecord.email || "—"}</span>
                </div>
                <div className="detail-row">
                  <span className="dr-label">Authorize URL</span>
                  <span className="dr-value" style={{ color: "var(--accent-strong)" }}>
                    {detailRecord.approve_url}
                  </span>
                </div>
                <div className="detail-row">
                  <span className="dr-label">state</span>
                  <span>
                    <span className={`badge ${STATUS_BADGE[detailRecord.status] || "badge-muted"}`}>
                      {STATUS_LABELS[detailRecord.status]}
                    </span>
                  </span>
                </div>
                <div className="detail-row">
                  <span className="dr-label">current step</span>
                  <span className="dr-value">{BA_STEP_CN[detailRecord.step]}</span>
                </div>
                <div className="detail-row">
                  <span className="dr-label">Captcha type</span>
                  <span className="dr-value">
                    {CAPTCHA_LABELS[detailRecord.captcha_type] || "—"}
                  </span>
                </div>
                <div className="detail-row">
                  <span className="dr-label">source</span>
                  <span className="dr-value">
                    {SOURCE_LABELS[detailRecord.source || "chain"] || detailRecord.source || "—"}
                  </span>
                </div>
                <div className="detail-row">
                  <span className="dr-label">Exporting country</span>
                  <span className="dr-value">{detailRecord.country || "—"}</span>
                </div>
                <div className="detail-row">
                  <span className="dr-label">form country</span>
                  <span className="dr-value">{detailRecord.identity_country || detailRecord.country || "—"}</span>
                </div>
                <div className="detail-row">
                  <span className="dr-label">Actual test of agent export</span>
                  <span className="dr-value">
                    {detailRecord.geo_country || detailRecord.proxy_country || "—"}
                    {detailRecord.geo_country && detailRecord.geo_country !== (detailRecord.identity_country || detailRecord.country) ? " ⚠ inconsistent" : ""}
                  </span>
                </div>
                <div className="detail-row">
                  <span className="dr-label">Source link</span>
                  <span className="dr-value">{detailRecord.chain_id || "—"}</span>
                </div>
                <div className="detail-row">
                  <span className="dr-label">SMS Number</span>
                  <span className="dr-value">{detailRecord.sms_phone || "—"}</span>
                </div>
                {detailRecord.sms_price ? (
                  <div className="detail-row">
                    <span className="dr-label">Acceptance price (USD)</span>
                    <span className="dr-value">
                      ${Number(detailRecord.sms_price).toFixed(4)}
                      {detailRecord.sms_provider_id ? ` · provider ${detailRecord.sms_provider_id}` : ""}
                    </span>
                  </div>
                ) : null}
                {detailRecord.last_msg && (
                  <div className="detail-row">
                    <span className="dr-label">recent progress</span>
                    <span className="dr-value" style={{ color: detailRecord.last_level === "err" ? "var(--danger)" : undefined }}>
                      {detailRecord.last_msg}
                    </span>
                  </div>
                )}
                {detailRecord.error && (
                  <div className="detail-row">
                    <span className="dr-label">error message</span>
                    <span className="dr-value" style={{ color: "var(--danger)" }}>
                      {detailRecord.error}
                    </span>
                  </div>
                )}
              </div>
            </div>
            <div className="ba-progress" style={{ borderTop: "1px solid var(--border-faint)" }}>
              {BA_STEPS.map((step) => {
                const stepIdx = BA_STEPS.indexOf(detailRecord.step);
                const curIdx = BA_STEPS.indexOf(step);
                const isDone = curIdx < stepIdx;
                const isCurrent = curIdx === stepIdx;
                return (
                  <div
                    key={step}
                    className={`ba-progress-step ${
                      isDone ? "done" : isCurrent ? "current" : ""
                    }`}
                  >
                    <span className="ba-progress-dot" />
                    <span className="ba-progress-label">{BA_STEP_CN[step]}</span>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}