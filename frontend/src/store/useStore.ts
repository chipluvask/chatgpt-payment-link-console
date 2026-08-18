import { create } from "zustand";
import type {
  Token, ProxyNode, ChainState, Stats, Sample,
  InventoryRecord, LogEntry, ViewName, WSEvent, StageName, StageData, BranchName,
  BAFeedItem, BABaSnap, BAAuthRecord,
} from "../types";
import { STAGE_ORDER } from "../types";

const LOG_MAX = 1000;
const BA_FEED_MAX = 300;

interface StoreState {
  /* ── navigation ── */
  currentView: ViewName;
  setView: (v: ViewName) => void;

  /* ── lifting chain branch ── */
  activeBranch: BranchName;
  setActiveBranch: (b: BranchName) => void;

  /* ── connect ── */
  wsStatus: "online" | "offline" | "connecting" | "error";
  setWsStatus: (s: StoreState["wsStatus"]) => void;

  /* ── data ── */
  tokens: Token[];
  nodes: ProxyNode[];
  chainStates: Record<string, ChainState>;
  stats: Stats;
  latencies: number[];
  inventory: InventoryRecord[];
  inventoryLoaded: boolean;
  samples: { success: Sample[]; failure: Sample[] };
  samplesLoaded: { success: boolean; failure: boolean };
  sampleTab: "success" | "failure";
  logLines: LogEntry[];

  /* ── Run in batches ── */
  batchRunning: boolean;
  runStartTime: number;
  selectedTokenIds: Set<string>;
  batchTotal: number;
  batchDone: number;

  /* ── Batch detection progress ── */
  probeProgress: { done: number; total: number };

  /* ── QG tunnel pool ── */
  qgPool: { superState: string; resiState: string; defaultPool: string };

  /* ── log ── */
  pushLog: (msg: string, level?: LogEntry["level"], chainId?: string) => void;
  clearLog: () => void;

  /* ── BA Authorization monitoring feed (overall situation, split column/Refresh without loss) ── */
  baFeed: BAFeedItem[];
  baSnap: Map<string, BABaSnap> | null;
  pushBaFeed: (item: BAFeedItem) => void;
  clearBaFeed: () => void;
  setBaSnap: (snap: Map<string, BABaSnap> | null) => void;
  rehydrateBaFeed: (records: BAAuthRecord[]) => void;

  /* ── WebSocket event handling ── */
  handleEvent: (evt: WSEvent) => void;

  /* ── operate ── */
  toggleTokenSelect: (id: string) => void;
  selectAllTokens: () => void;
  clearTokenSelection: () => void;
  setBatchRunning: (r: boolean) => void;
  setSampleTab: (t: "success" | "failure") => void;
}

const tag = () => new Date().toLocaleTimeString("zh-CN", { hour12: false });

export const useStore = create<StoreState>((set, get) => ({
  currentView: "overview",
  setView: (v) => set({ currentView: v }),

  activeBranch: "paypal",
  setActiveBranch: (b) => set({ activeBranch: b }),

  wsStatus: "offline",
  setWsStatus: (s) => set({ wsStatus: s }),

  tokens: [],
  nodes: [],
  chainStates: {},
  stats: { success: 0, failure: 0, byCountry: {}, failByCountry: {}, reasons: {}, stageMatrix: {} },
  latencies: [],
  inventory: [],
  inventoryLoaded: false,
  samples: { success: [], failure: [] },
  samplesLoaded: { success: false, failure: false },
  sampleTab: "success",
  logLines: [],

  batchRunning: false,
  runStartTime: 0,
  selectedTokenIds: new Set(),
  batchTotal: 0,
  batchDone: 0,

  probeProgress: { done: 0, total: 0 },

  qgPool: { superState: "—", resiState: "—", defaultPool: "resi" },

  pushLog: (msg, level = "info", chainId = "") =>
    set((s) => {
      const lines = [...s.logLines, { ts: tag(), msg, level, chainId }];
      if (lines.length > LOG_MAX) lines.shift();
      return { logLines: lines };
    }),

  clearLog: () => set({ logLines: [] }),

  baFeed: [],
  baSnap: null,
  pushBaFeed: (item) =>
    set((s) => {
      const feed = [...s.baFeed, item];
      if (feed.length > BA_FEED_MAX) feed.shift();
      return { baFeed: feed };
    }),
  clearBaFeed: () => set({ baFeed: [], baSnap: null }),
  setBaSnap: (snap) => set({ baSnap: snap }),
  rehydrateBaFeed: (records) => {
    // mount/After refresh: Rebuild baseline using current record (running show"Resume monitoring", Final display result),
    // and create baSnap baseline, Subsequent polling incremental comparison
    const now = Date.now();
    const snap = new Map<string, BABaSnap>();
    const items: BAFeedItem[] = [];
    for (const r of records || []) {
      const key = r.ba_token;
      snap.set(key, {
        status: r.status,
        step: r.step,
        error: r.error,
        source: r.source || "",
        last_msg: r.last_msg || "",
      });
      if (r.status === "running") {
        items.push({
          ts: now, token: key, level: "info",
          msg: `Monitor recovery · Authorizing · ${r.step === "submit_email" ? "Submit email" : r.step}`,
        });
      } else if (r.status === "success") {
        items.push({ ts: now, token: key, level: "ok", msg: "Authorization successful ✓" });
      } else if (r.status === "failed") {
        items.push({ ts: now, token: key, level: "err", msg: `Authorization failed: ${r.error || "unknown reason"}` });
      }
    }
    set((s) => ({ baSnap: snap, baFeed: [...items.reverse(), ...s.baFeed].slice(0, BA_FEED_MAX) }));
  },

  handleEvent: (evt) => {
    const s = get();
    switch (evt.type) {
      case "sync": {
        const patch: Partial<StoreState> = {};
        if (evt.tokens) patch.tokens = evt.tokens;
        if (evt.stats) patch.stats = evt.stats;
        if (evt.chains) patch.chainStates = evt.chains;
        if (evt.nodes) patch.nodes = evt.nodes;
        if (evt.inventory) { patch.inventory = evt.inventory; patch.inventoryLoaded = true; }
        if (evt.qg_pool) patch.qgPool = evt.qg_pool;
        if (evt.latencies) patch.latencies = evt.latencies;
        if (evt.running !== undefined) {
          patch.batchRunning = evt.running;
          patch.runStartTime = evt.running ? Date.now() : 0;
        }
        set(patch);
        s.pushLog("Status synchronized", "info");
        break;
      }
      case "chain_start": {
        set((st) => ({
          chainStates: {
            ...st.chainStates,
            [evt.chain_id]: {
              stages: {}, status: "running",
              email: evt.email || "", tokenSub: evt.token_sub || "",
              startTime: Date.now(), attempt: evt.attempt || 1,
              country: evt.country || "",
              linkMode: (evt.link_mode as ChainState["linkMode"]) || "",
            },
          },
        }));
        s.pushLog(`link up — ${evt.email || evt.token_sub || evt.chain_id}`, "info", evt.chain_id);
        break;
      }
      case "channel_detect": {
        const cs = s.chainStates[evt.chain_id];
        if (cs) {
          set((st) => ({
            chainStates: {
              ...st.chainStates,
              [evt.chain_id]: {
                ...cs,
                channelDetect: {
                  channel: evt.channel,
                  methods: evt.methods,
                  present: evt.present,
                  country: evt.country,
                },
              },
            },
          }));
        }
        s.pushLog(
          `Channel detection: ${evt.channel} ${evt.present ? "✓ exist" : "✗ does not exist"} (${(evt.methods || []).join(", ") || "none"})`,
          evt.present ? "ok" : "warn",
          evt.chain_id
        );
        break;
      }
      case "geo_probe": {
        const cs = s.chainStates[evt.chain_id];
        if (cs) {
          const stages = { ...cs.stages };
          const prev = stages[evt.stage as StageName] || ({
            state: "run", country: evt.country || "", tryN: 1, maxTry: 1,
          } as StageData);
          const actual = evt.actual_country || "";
          const drifted = !!actual && !!evt.country && actual !== evt.country;
          const reusedFrom = evt.reused ? (evt.from_stage || "") : "";
          stages[evt.stage as StageName] = {
            ...prev,
            actualCountry: actual,
            exitIp: evt.exit_ip || "",
            geoConfidence: Number(evt.geo_confidence ?? 0),
            drifted,
            reusedFrom,
          } as StageData;
          set((st) => ({
            chainStates: {
              ...st.chainStates,
              [evt.chain_id]: {
                ...cs,
                stages,
                actualCountry: evt.stage === "checkout" ? actual : (cs.actualCountry || actual),
                exitIp: evt.stage === "checkout" ? (evt.exit_ip || cs.exitIp) : (cs.exitIp || evt.exit_ip),
                geoConfidence: evt.stage === "checkout" ? Number(evt.geo_confidence ?? 0) : cs.geoConfidence,
              },
            },
          }));
        }
        if (evt.ok) {
          const drift = evt.actual_country && evt.country && evt.actual_country !== evt.country
            ? ` ⚠ drift ${evt.country}→${evt.actual_country}` : "";
          const reuse = evt.reused ? ` [Reuse ${evt.from_stage || ""} exit]` : "";
          s.pushLog(`${evt.stage} Export real country: ${evt.actual_country || "unknown"} (${evt.exit_ip || evt.country})${drift}${reuse}`, "info", evt.chain_id);
        }
        break;
      }
      case "stage_try": {
        const cs = s.chainStates[evt.chain_id];
        if (cs) {
          const stages = { ...cs.stages };
          stages[evt.stage as StageName] = {
            state: "run", country: evt.country,
            tryN: evt.try_n, maxTry: evt.max_try,
          } as StageData;
          const linkMode = (evt.link_mode as ChainState["linkMode"])
            || (evt.stage === "taxes" || evt.stage === "confirm"
              ? "oaics" as const : cs.linkMode || "");
          set((st) => ({
            chainStates: { ...st.chainStates, [evt.chain_id]: { ...cs, stages, country: evt.country || cs.country, linkMode } },
          }));
        }
        s.pushLog(`${evt.stage} ▷ try ${evt.try_n}/${evt.max_try} via ${evt.country}`, "info", evt.chain_id);
        break;
      }
      case "stage_ok": {
        const cs = s.chainStates[evt.chain_id];
        if (cs) {
          const stages = { ...cs.stages };
          const prev = stages[evt.stage as StageName];
          stages[evt.stage as StageName] = { ...(prev || {}), state: "ok", country: evt.country } as StageData;
          const linkMode = (evt.link_mode as ChainState["linkMode"]) || cs.linkMode || "";
          const patch: ChainState = { ...cs, stages, linkMode };
          // 【Deprecated】S0 Detection segment event handling (2026-08-14 Detection segment removal, The backend no longer sends probe event; Keep compatible)
          if (evt.stage === "probe" && evt.detected) patch.detected = String(evt.detected);
          set((st) => ({
            chainStates: { ...st.chainStates, [evt.chain_id]: patch },
          }));
        }
        s.pushLog(`${evt.stage} ✓ (${evt.country})`, "ok", evt.chain_id);
        break;
      }
      case "stage_fail": {
        const cs = s.chainStates[evt.chain_id];
        if (cs) {
          const stages = { ...cs.stages };
          const prev = stages[evt.stage as StageName];
          stages[evt.stage as StageName] = { ...(prev || {}), state: "fail", country: evt.country } as StageData;
          const linkMode = (evt.link_mode as ChainState["linkMode"]) || cs.linkMode || "";
          set((st) => ({
            chainStates: { ...st.chainStates, [evt.chain_id]: { ...cs, stages, linkMode } },
          }));
        }
        s.pushLog(`${evt.stage} ✗ ultimately failed [${evt.country}]${evt.detail ? `: ${evt.detail}` : ""}`, "err", evt.chain_id);
        break;
      }
      case "chain_success": {
        const cs = s.chainStates[evt.chain_id];
        if (cs) {
          const lat = cs.startTime ? (Date.now() - cs.startTime) / 1000 : 0;
          set((st) => ({
            chainStates: {
              ...st.chainStates,
              [evt.chain_id]: {
                ...cs,
                status: "success", url: evt.paypal_approve_url,
                linkMode: (evt.link_mode as ChainState["linkMode"]) || cs.linkMode || "",
                actualCountry: evt.actual_country || cs.actualCountry || evt.country,
                exitIp: evt.exit_ip || cs.exitIp,
                geoConfidence: evt.geo_confidence ?? cs.geoConfidence,
                // Freezing takes time: No longer continues timing after success
                elapsed: evt.elapsed != null ? Number(evt.elapsed) : lat,
                endTime: Date.now(),
              },
            },
            latencies: lat > 0 ? [...st.latencies, lat].slice(-500) : st.latencies,
            stats: {
              ...st.stats,
              success: (st.stats.success || 0) + 1,
              byCountry: {
                ...st.stats.byCountry,
                [evt.actual_country || evt.country]: (st.stats.byCountry[evt.actual_country || evt.country] || 0) + 1,
              },
            },
          }));
        }
        s.pushLog(`SUCCESS — BA URL Obtained (${evt.actual_country || evt.country})`, "ok", evt.chain_id);
        break;
      }
      case "chain_failure": {
        const cs = s.chainStates[evt.chain_id];
        if (cs) {
          const lat = cs.startTime ? (Date.now() - cs.startTime) / 1000 : 0;
          set((st) => ({
            chainStates: {
              ...st.chainStates,
              [evt.chain_id]: {
                ...cs,
                status: "failed", reason: evt.reason_code, reasonText: evt.reason_text,
                linkMode: (evt.link_mode as ChainState["linkMode"]) || cs.linkMode || "",
                actualCountry: evt.actual_country || cs.actualCountry || evt.country,
                exitIp: evt.exit_ip || cs.exitIp,
                geoConfidence: evt.geo_confidence ?? cs.geoConfidence,
                elapsed: evt.elapsed != null ? Number(evt.elapsed) : lat,
                endTime: Date.now(),
              },
            },
            stats: {
              ...st.stats,
              failure: (st.stats.failure || 0) + 1,
              failByCountry: {
                ...st.stats.failByCountry,
                [evt.actual_country || evt.country]: (st.stats.failByCountry[evt.actual_country || evt.country] || 0) + 1,
              },
              reasons: {
                ...st.stats.reasons,
                [evt.reason_code]: (st.stats.reasons[evt.reason_code] || 0) + 1,
              },
            },
          }));
        }
        s.pushLog(`FAILED — ${evt.reason_code}: ${evt.reason_text || evt.error}`, "err", evt.chain_id);
        break;
      }
      case "batch_start": {
        // A new round begins: Clear remaining progress from the previous round, Reset batch count
        set({
          chainStates: {},
          batchRunning: true,
          runStartTime: Date.now(),
          batchTotal: evt.total || 0,
          batchDone: 0,
        });
        s.pushLog(`Batch start — ${evt.total || "?"} strip`, "info");
        break;
      }
      case "batch_progress": {
        set({ batchDone: evt.done || 0, batchTotal: evt.total || 0 });
        break;
      }
      case "batch_done": {
        set({ batchRunning: false, runStartTime: 0 });
        s.pushLog(`Completed in batches: success ${evt.success} / fail ${evt.failure} / time consuming ${evt.elapsed}s`, "info");
        break;
      }
      case "stats_update": {
        if (evt.stats) set({ stats: evt.stats });
        break;
      }
      case "proxy_health": {
        set({ nodes: evt.nodes || [] });
        s.pushLog(`Health check completed，${(evt.nodes || []).length} nodes`, "info");
        break;
      }
      case "node_started":
      case "node_stopped": {
        s.pushLog(`node ${evt.name} ${evt.type === "node_started" ? "Started" : "Stopped"}`, "info");
        if (evt.nodes) set({ nodes: evt.nodes });
        break;
      }
      case "token_imported": {
        if (evt.tokens) set({ tokens: evt.tokens });
        s.pushLog(`Import completed: ${evt.imported} strip, fail ${evt.failed}`, evt.failed > 0 ? "warn" : "ok");
        break;
      }
      case "token_status": {
        set((st) => ({
          tokens: st.tokens.map((t) => t.id === evt.token_id ? { ...t, status: evt.status } : t),
        }));
        break;
      }
      case "probe_done": {
        // Single detection completed: Update this in real time token session type + Complete detection results (promo/paypal/token state)
        set((st) => ({
          tokens: st.tokens.map((t) =>
            t.id === evt.token_id
              ? {
                  ...t,
                  session_type: evt.session_type || t.session_type,
                  probe: evt.probe || t.probe,
                }
              : t
          ),
        }));
        break;
      }
      case "probe_progress": {
        set({ probeProgress: { done: evt.done || 0, total: evt.total || 0 } });
        break;
      }
      default:
        break;
    }
  },

  toggleTokenSelect: (id) =>
    set((s) => {
      const next = new Set(s.selectedTokenIds);
      if (next.has(id)) next.delete(id); else next.add(id);
      return { selectedTokenIds: next };
    }),

  selectAllTokens: () =>
    set((s) => {
      const next = new Set(s.selectedTokenIds);
      if (next.size < s.tokens.length) s.tokens.forEach((t) => next.add(t.id));
      else next.clear();
      return { selectedTokenIds: next };
    }),

  clearTokenSelection: () => set({ selectedTokenIds: new Set() }),

  setBatchRunning: (r) =>
    set({ batchRunning: r, runStartTime: r ? Date.now() : 0 }),

  setSampleTab: (t) => set({ sampleTab: t }),
}));
