import { useEffect, useState, useCallback } from "react";
import { api } from "../api/client";
import type { StageName, StageCfg, BranchName, BranchCfg } from "../types";

/* ==========================================================================
   type definition
   ========================================================================== */
interface ServerCfg {
  host: string;
  port: number;
  max_concurrent_chains: number;
  thread_pool_size: number;
  chain_mode: string;
  mock_success_rate: number;
  mock_stage_min: number;
  mock_stage_max: number;
}
interface ChainCfg {
  require_zero: boolean;
  auto_billing: boolean;
  token_min_interval_ms: number;
  fail_cooldown_sec: number;
  stages: Partial<Record<StageName, StageCfg>>;
  branches: Partial<Record<BranchName, BranchCfg>>;
}
interface StripeCfg {
  init_version?: string;
  runtime_version?: string;
  checkout_url?: string;
  approve_url?: string;
  init_url_tmpl?: string;
  update_url_tmpl?: string;
  pm_url?: string;
  confirm_url_tmpl?: string;
  poll_url_tmpl?: string;
}
interface TLSCfg {
  impersonate?: string;
  user_agent?: string;
  accept_language?: string;
}
interface ProxyCfg {
  default_pool: string;
  health_check_interval: number;
  max_concurrent_per_node: number;
  qg_super_pool?: { host: string; port: number; auth_key: string; auth_pwd: string };
  qg_resi_pool?: { host: string; port: number; auth_key: string; auth_pwd: string };
  proxy_711?: Record<string, any>;
}
interface MomoPatch {
  name: string;
  desc: string;
  enabled: boolean;
}
interface MomoCfg {
  enabled: boolean;
  patches: MomoPatch[];
}
interface PayPalCfg {
  ba_url_pattern: string;
  pm_redirect_pattern: string;
  blocked_countries: string[];
  success_criteria: string[];
}
interface BillingTemplate {
  country: string;
  name: string;
  city: string;
  state: string;
  postal_code: string;
  line1: string;
  currency: string;
  area_code: number;
}
interface AppConfig {
  server: ServerCfg;
  chain: ChainCfg;
  stripe: StripeCfg;
  tls: TLSCfg;
  proxy: ProxyCfg;
  momo: MomoCfg;
  paypal: PayPalCfg;
}

/* ==========================================================================
   Auxiliary
   ========================================================================== */
const maskKey = (k?: string): string => {
  if (!k) return "—";
  if (k.length <= 8) return "••••";
  return `${k.slice(0, 4)}••••${k.slice(-4)}`;
};

const flag = (cc: string): string => {
  if (!cc || cc.length !== 2) return "";
  const A = 0x1f1e6, Z = 0x1f1ff;
  const c = cc.toUpperCase().charCodeAt(0) - 65;
  const c2 = cc.toUpperCase().charCodeAt(1) - 65;
  if (c < 0 || c > 25 || c2 < 0 || c2 > 25) return "";
  return String.fromCodePoint(A + c, A + c2);
};

/* ==========================================================================
   Bill template row
   ========================================================================== */
function BillingRow({ t }: { t: BillingTemplate }) {
  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "36px 60px 1fr 1fr 90px 60px",
        gap: 10,
        padding: "7px 0",
        borderBottom: "1px solid var(--border-faint)",
        alignItems: "center",
        fontSize: 12,
      }}
    >
      <span>{flag(t.country)}</span>
      <span className="tag">{t.country}</span>
      <span>{t.name}</span>
      <span className="muted">{t.city}</span>
      <span className="muted mono">{t.postal_code}</span>
      <span className="tag">{t.currency}</span>
    </div>
  );
}

/* ==========================================================================
   main component
   ========================================================================== */
export function SettingsView() {
  const [config, setConfig] = useState<AppConfig | null>(null);
  const [templates, setTemplates] = useState<BillingTemplate[]>([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState("");
  const [showAllTemplates, setShowAllTemplates] = useState(false);
  const [billingFilter, setBillingFilter] = useState("");

  const loadConfig = useCallback(async () => {
    setLoading(true);
    setErr("");
    try {
      const data = await api("/api/config");
      if (data && data.ok) {
        setConfig({
          server: data.server,
          chain: data.chain,
          stripe: data.stripe,
          tls: data.tls,
          proxy: data.proxy,
          momo: data.momo,
          paypal: data.paypal,
        });
      } else {
        setErr((data && data.error) || "Failed to load configuration");
        setConfig(makeMockConfig());
      }
    } catch {
      setErr("Backend not connected，Show default configuration");
      setConfig(makeMockConfig());
    } finally {
      setLoading(false);
    }
  }, []);

  const loadTemplates = useCallback(async () => {
    try {
      const data = await api("/api/billing/templates");
      if (data && data.ok) {
        setTemplates(data.templates);
      }
    } catch {
      // Silently fails
    }
  }, []);

  useEffect(() => {
    loadConfig();
    loadTemplates();
  }, [loadConfig, loadTemplates]);

  if (loading) {
    return (
      <div className="page">
        <div className="page-head">
          <h2 className="page-title">set up</h2>
        </div>
        <div className="card">
          <div className="empty">
            <div className="empty-icon">🔄</div>
            <div className="empty-title">loading…</div>
          </div>
        </div>
      </div>
    );
  }

  if (!config) {
    return (
      <div className="page">
        <div className="page-head">
          <h2 className="page-title">set up</h2>
        </div>
        <div className="card">
          <div className="empty">
            <div className="empty-title">{err || "No configuration data yet"}</div>
          </div>
        </div>
      </div>
    );
  }

  const server = config.server || ({} as ServerCfg);
  const chain = config.chain || ({} as ChainCfg);
  const stripe = config.stripe || ({} as StripeCfg);
  const tls = config.tls || ({} as TLSCfg);
  const proxy = config.proxy || ({} as ProxyCfg);
  const momo = config.momo || ({ enabled: false, patches: [] } as MomoCfg);
  const momoPatches = momo.patches || [];
  const paypal = config.paypal || ({
    ba_url_pattern: "",
    pm_redirect_pattern: "",
    blocked_countries: [],
    success_criteria: [],
  } as PayPalCfg);

  const filteredTemplates = billingFilter
    ? templates.filter(
        (t) =>
          t.country.toLowerCase().includes(billingFilter.toLowerCase()) ||
          t.name.toLowerCase().includes(billingFilter.toLowerCase())
      )
    : templates;

  const toggleMini = (on: boolean) => (
    <span className={`badge ${on ? "badge-success" : "badge-muted"}`}>
      {on ? "ON" : "OFF"}
    </span>
  );

  return (
    <div className="page">
      {/* 0. GitHub Open source watermark */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 12,
          padding: "10px 16px",
          marginBottom: 14,
          borderRadius: 10,
          border: "1px solid var(--border)",
          background: "linear-gradient(135deg, rgba(88,166,255,0.08), rgba(255,255,255,0.02))",
          fontSize: 12.5,
          color: "var(--text-2)",
        }}
      >
        <span style={{ fontSize: 20, lineHeight: 1 }}>⭐</span>
        <span style={{ flex: 1 }}>
          <span style={{ fontWeight: 600, color: "var(--text-1)" }}>The project has been open source</span>
          — If you think this project has helped you，welcome to GitHub Click Star Support it，smoothly Fork Thanks for collecting 🙏
        </span>
        <a
          href="https://github.com/mio-cc/freepp"
          target="_blank"
          rel="noopener noreferrer"
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: 6,
            padding: "5px 12px",
            borderRadius: 999,
            background: "var(--accent)",
            color: "#fff",
            fontSize: 12,
            fontWeight: 600,
            textDecoration: "none",
            whiteSpace: "nowrap",
          }}
        >
          ⭐ github.com/mio-cc/freepp
        </a>
      </div>

      <div className="page-head">
        <div>
          <h2 className="page-title">set up</h2>
          <p className="page-sub">
            billing country · PayPal Authorize · Stripe fingerprint · TLS · acting · MoMo patch · server
            {err && <span style={{ color: "var(--warn)" }}> ({err})</span>}
          </p>
        </div>
        <div className="page-actions">
          <button className="btn btn-sm" onClick={loadConfig}>
            refresh
          </button>
        </div>
      </div>

      {/* 1. Billing country configuration */}
      <div className="card settings-panel">
        <div className="card-head">
          <span className="card-title">Billing country configuration</span>
          <span className="card-hint">Payment Method billing_details · Close to exporting countries</span>
        </div>
        <div className="card-body">
          <div className="setting-row">
            <span className="setting-label">Automatic bill close</span>
            <div className="setting-control">
              {toggleMini(chain.auto_billing)}
              <span className="muted" style={{ fontSize: 11.5 }}>
                {chain.auto_billing ? "billing address follow provider segment exporting country" : "Countries using fixed bills"}
              </span>
            </div>
          </div>
          <div className="setting-row">
            <span className="setting-label">Number of bill templates</span>
            <div className="setting-control">
              <span className="badge badge-accent">{templates.length || "—"}</span>
              <span className="muted" style={{ fontSize: 11.5 }}>countries available</span>
            </div>
          </div>
          <div className="setting-row">
            <span className="setting-label">Token interval</span>
            <div className="setting-control">
              <span className="tag">{chain.token_min_interval_ms}ms</span>
            </div>
          </div>
          <div className="setting-row">
            <span className="setting-label">Failure to cool down</span>
            <div className="setting-control">
              <span className="tag">{chain.fail_cooldown_sec}s</span>
            </div>
          </div>
        </div>

        <div className="card-body" style={{ borderTop: "1px solid var(--border-faint)" }}>
          <div className="section-head">
            <span className="section-title">bill template</span>
            <button
              className="btn btn-ghost btn-sm"
              onClick={() => setShowAllTemplates(!showAllTemplates)}
            >
              {showAllTemplates ? "close" : `Expand all (${templates.length})`}
            </button>
          </div>
          <div style={{ display: "flex", gap: 8, marginBottom: 8 }}>
            <input
              className="input"
              style={{ width: 240 }}
              type="search"
              placeholder="Search country code or name…"
              value={billingFilter}
              onChange={(e) => setBillingFilter(e.target.value)}
            />
          </div>
          {showAllTemplates && (
            <div>
              <div
                style={{
                  display: "grid",
                  gridTemplateColumns: "36px 60px 1fr 1fr 90px 60px",
                  gap: 10,
                  padding: "7px 0",
                  fontSize: 10,
                  fontWeight: 600,
                  letterSpacing: "0.08em",
                  textTransform: "uppercase",
                  color: "var(--text-3)",
                  borderBottom: "1px solid var(--border)",
                }}
              >
                <span></span>
                <span>nation</span>
                <span>Name</span>
                <span>City</span>
                <span>post code</span>
                <span>Currency</span>
              </div>
              {filteredTemplates.length > 0 ? (
                filteredTemplates.map((t) => <BillingRow key={t.country} t={t} />)
              ) : (
                <div className="empty" style={{ padding: 16 }}>No matching template</div>
              )}
            </div>
          )}
        </div>
      </div>

      {/* 3. PayPal Payment authorization */}
      <div className="card settings-panel">
        <div className="card-head">
          <span className="card-title">PayPal Payment authorization</span>
          <span className="card-hint">BA (Billing Agreement) Approve · Lift chain target</span>
        </div>
        <div className="card-body">
          <div className="section-head">
            <span className="section-title">Successful judgment（All three conditions are met simultaneously）</span>
          </div>
          <div className="bar-list" style={{ padding: "4px 0 10px" }}>
            {paypal.success_criteria.map((c, i) => (
              <div className="bar-row" key={i}>
                <span className="patch-idx">{i + 1}</span>
                <span style={{ fontSize: 12, color: "var(--text-2)" }}>{c}</span>
              </div>
            ))}
          </div>
          <div className="setting-row">
            <span className="setting-label">BA URL model</span>
            <div className="setting-control">
              <code className="tag" style={{ wordBreak: "break-all" }}>{paypal.ba_url_pattern}</code>
            </div>
          </div>
          <div className="setting-row">
            <span className="setting-label">PM Redirect model</span>
            <div className="setting-control">
              <code className="tag" style={{ wordBreak: "break-all" }}>{paypal.pm_redirect_pattern}</code>
            </div>
          </div>
        </div>
        <div className="card-body" style={{ borderTop: "1px solid var(--border-faint)" }}>
          <div className="section-head">
            <span className="section-title">Stripe API endpoint</span>
          </div>
          <div className="mini-grid" style={{ padding: 0 }}>
            <div className="mini-card">
              <div className="mini-card-label">Checkout</div>
              <div className="mini-card-value" style={{ fontSize: 11 }}>{stripe.checkout_url || "—"}</div>
            </div>
            <div className="mini-card">
              <div className="mini-card-label">Approve</div>
              <div className="mini-card-value" style={{ fontSize: 11 }}>{stripe.approve_url || "—"}</div>
            </div>
            <div className="mini-card">
              <div className="mini-card-label">Payment Method</div>
              <div className="mini-card-value" style={{ fontSize: 11 }}>{stripe.pm_url || "—"}</div>
            </div>
            <div className="mini-card">
              <div className="mini-card-label">Confirm</div>
              <div className="mini-card-value" style={{ fontSize: 11 }}>{stripe.confirm_url_tmpl || "—"}</div>
            </div>
            <div className="mini-card">
              <div className="mini-card-label">Poll</div>
              <div className="mini-card-value" style={{ fontSize: 11 }}>{stripe.poll_url_tmpl || "—"}</div>
            </div>
          </div>
        </div>
        <div className="card-body" style={{ borderTop: "1px solid var(--border-faint)" }}>
          <div className="section-head">
            <span className="section-title">PayPal Not supported / Risk control high-risk countries</span>
          </div>
          <div className="country-tags">
            {paypal.blocked_countries.map((c) => (
              <span key={c} className="country-tag country-tag-blocked">
                {flag(c)} {c}
              </span>
            ))}
          </div>
        </div>
      </div>

      {/* 4. Stripe Init fingerprint */}
      <div className="card settings-panel">
        <div className="card-head">
          <span className="card-title">Stripe Init fingerprint</span>
          <span className="card-hint">payment_pages init Version · runtime</span>
        </div>
        <div className="mini-grid">
          <div className="mini-card">
            <div className="mini-card-label">Stripe Init Version</div>
            <div className="mini-card-value" style={{ fontSize: 11 }}>{stripe.init_version || "—"}</div>
            <div className="mini-card-desc">Stripe payment_pages init API Version fingerprint</div>
          </div>
          <div className="mini-card">
            <div className="mini-card-label">Init URL template</div>
            <div className="mini-card-value" style={{ fontSize: 11 }}>
              {stripe.init_url_tmpl || "https://api.stripe.com/v1/payment_pages/{cs}/init"}
            </div>
            <div className="mini-card-desc">{"{cs}"} = checkout_session_id</div>
          </div>
          <div className="mini-card">
            <div className="mini-card-label">Runtime Version</div>
            <div className="mini-card-value">{stripe.runtime_version || "—"}</div>
            <div className="mini-card-desc">stripe.js runtime version</div>
          </div>
          <div className="mini-card">
            <div className="mini-card-label">Update URL template</div>
            <div className="mini-card-value" style={{ fontSize: 11 }}>
              {stripe.update_url_tmpl || "https://api.stripe.com/v1/payment_pages/{cs}/update"}
            </div>
            <div className="mini-card-desc">S3 Amount Guard Section (update) Request address</div>
          </div>
        </div>
      </div>

      {/* 5. TLS fingerprint */}
      <div className="card settings-panel">
        <div className="card-head">
          <span className="card-title">TLS fingerprint</span>
          <span className="card-hint">curl_cffi impersonate</span>
        </div>
        <div className="card-body">
          <div className="setting-row">
            <span className="setting-label">impersonate</span>
            <div className="setting-control">
              <code className="tag">{tls.impersonate || "chrome"}</code>
            </div>
          </div>
          <div className="setting-row">
            <span className="setting-label">User-Agent</span>
            <div className="setting-control">
              <code className="tag" style={{ wordBreak: "break-all" }}>{tls.user_agent || "—"}</code>
            </div>
          </div>
          <div className="setting-row">
            <span className="setting-label">Accept-Language</span>
            <div className="setting-control">
              <code className="tag">{tls.accept_language || "—"}</code>
            </div>
          </div>
        </div>
      </div>

      {/* 6. Agent configuration */}
      <div className="card settings-panel">
        <div className="card-head">
          <span className="card-title">Agent configuration</span>
          <span className="card-hint">Qingguo Tunnel · 711 proxy pool</span>
        </div>
        <div className="card-body">
          <div className="setting-row">
            <span className="setting-label">Default pool</span>
            <div className="setting-control">
              <code className="tag">{proxy.default_pool}</code>
            </div>
          </div>
          <div className="setting-row">
            <span className="setting-label">health check interval</span>
            <div className="setting-control"><span className="tag">{proxy.health_check_interval}s</span></div>
          </div>
          <div className="setting-row">
            <span className="setting-label">Maximum concurrency per node</span>
            <div className="setting-control"><span className="tag">{proxy.max_concurrent_per_node}</span></div>
          </div>
          {proxy.qg_resi_pool && (
            <div className="setting-row">
              <span className="setting-label">residential pool (resi)</span>
              <div className="setting-control">
                <code className="tag">{proxy.qg_resi_pool.host}:{proxy.qg_resi_pool.port}</code>
                <span className="muted" style={{ fontSize: 11.5 }}>
                  key: {maskKey(proxy.qg_resi_pool.auth_key)}
                </span>
              </div>
            </div>
          )}
          {proxy.qg_super_pool && (
            <div className="setting-row">
              <span className="setting-label">Computer room pool (super)</span>
              <div className="setting-control">
                <code className="tag">{proxy.qg_super_pool.host}:{proxy.qg_super_pool.port}</code>
                <span className="muted" style={{ fontSize: 11.5 }}>
                  key: {maskKey(proxy.qg_super_pool.auth_key)}
                </span>
              </div>
            </div>
          )}
          {proxy.proxy_711 && proxy.proxy_711.enabled && (
            <div className="setting-row">
              <span className="setting-label">711 proxy pool</span>
              <div className="setting-control">
                <span className="badge badge-accent">Enabled</span>
                <span className="muted" style={{ fontSize: 11.5 }}>
                  relay: {proxy.proxy_711.relay_base}:{proxy.proxy_711.relay_port_start}-
                  {proxy.proxy_711.relay_port_end}
                </span>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* 7. MoMo patch */}
      <div className="card settings-panel">
        <div className="card-head">
          <span className="card-title">MoMo chain patch</span>
          <span className="card-hint">fifth floor Patch · {momo.enabled ? "Enabled" : "Not enabled"}</span>
        </div>
        <div className="patch-list">
          {momoPatches.map((p, i) => (
            <div className="patch-row" key={p.name}>
              <div className="patch-meta">
                <span className="patch-idx">{i + 1}</span>
                <div className="patch-text">
                  <div className="patch-name">
                    {p.name}{" "}
                    <span className={`badge ${p.enabled ? "badge-success" : "badge-muted"}`}>
                      {p.enabled ? "Enabled" : "Not enabled"}
                    </span>
                  </div>
                  <div className="patch-desc">{p.desc}</div>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* 8. Server configuration */}
      <div className="card settings-panel">
        <div className="card-head">
          <span className="card-title">Server configuration</span>
          <span className="card-hint">FastAPI · {server.chain_mode} model</span>
        </div>
        <div className="card-body">
          <div className="setting-row">
            <span className="setting-label">listening address</span>
            <div className="setting-control">
              <code className="tag">{server.host}:{server.port}</code>
            </div>
          </div>
          <div className="setting-row">
            <span className="setting-label">Maximum concurrent links</span>
            <div className="setting-control"><span className="tag">{server.max_concurrent_chains}</span></div>
          </div>
          <div className="setting-row">
            <span className="setting-label">Thread pool size</span>
            <div className="setting-control"><span className="tag">{server.thread_pool_size}</span></div>
          </div>
          <div className="setting-row">
            <span className="setting-label">link mode</span>
            <div className="setting-control">
              <span className={`badge ${server.chain_mode === "live" ? "badge-success" : "badge-warn"}`}>
                {server.chain_mode}
              </span>
              {server.chain_mode === "mock" && (
                <span className="muted" style={{ fontSize: 11.5 }}>
                  success rate {Math.round(server.mock_success_rate * 100)}%
                </span>
              )}
            </div>
          </div>
        </div>
      </div>

      <div className="muted" style={{ marginTop: 12, fontSize: 12 }}>
        System level configuration；Each chain branch（PayPal refining / MoMo lift chain / Grok link / PIX QR code）of
        Seven-segment outlets and switches are configured independently in each link page
      </div>
    </div>
  );
}

/* ==========================================================================
   Mock Configuration (Used when the backend is offline)
   ========================================================================== */
function makeMockConfig(): AppConfig {
  const mkStages = (cc: string[]): Partial<Record<StageName, StageCfg>> => ({
    checkout: { countries: cc, timeout: 15, retry: 3 },
    init: { countries: cc, timeout: 10, retry: 3 },
    update: { countries: cc, timeout: 10, retry: 3 },
    provider: { countries: cc, timeout: 8, retry: 3 },
    approve: { countries: cc, timeout: 6, retry: 3 },
    poll: { countries: cc, timeout: 25, retry: 1, poll_interval: 0.75, max_polls: 40 },
    resolve: { countries: cc, timeout: 20, retry: 2 },
  });

  const mkBranch = (
    name: BranchName,
    label: string,
    channel: string,
    token_source: string,
    cc: string[],
    extra: Partial<BranchCfg> = {}
  ): BranchCfg => ({
    name,
    label,
    channel,
    token_source,
    require_zero: true,
    channel_check: true,
    dual_init: false,
    init0_ccs: cc.slice(0, 1),
    init1_ccs: cc,
    init_t_ccs: [],
    follow_checkout: false,
    billing_country: "auto",
    attempts: 8,
    stages: mkStages(cc),
    ...extra,
  });

  return {
    server: {
      host: "0.0.0.0",
      port: 8770,
      max_concurrent_chains: 10,
      thread_pool_size: 20,
      chain_mode: "mock",
      mock_success_rate: 0.6,
      mock_stage_min: 0.4,
      mock_stage_max: 1.6,
    },
    chain: {
      require_zero: true,
      auto_billing: true,
      token_min_interval_ms: 500,
      fail_cooldown_sec: 60,
      stages: mkStages(["US", "GB"]),
      branches: {
        paypal: mkBranch("paypal", "PayPal refining", "paypal", "stripe", ["US", "GB", "AU"]),
        momo: mkBranch("momo", "MoMo lift chain", "momo", "momo", ["VN"], {
          require_zero: false,
          dual_init: true,
          follow_checkout: true,
        }),
        grok: mkBranch("grok", "Grok link", "card", "grok", ["US"], {
          require_zero: false,
          follow_checkout: true,
        }),
        pix: mkBranch("pix", "PIX QR code", "link", "pix", ["BR"], {
          follow_checkout: true,
        }),
      },
    },
    stripe: {
      init_version: "2025-03-31.basil; checkout_server_update_beta=v1; checkout_manual_approval_preview=v1",
      runtime_version: "6f8494a281",
      checkout_url: "https://chatgpt.com/backend-api/payments/checkout",
      approve_url: "https://chatgpt.com/backend-api/payments/checkout/approve",
      init_url_tmpl: "https://api.stripe.com/v1/payment_pages/{cs}/init",
      update_url_tmpl: "https://api.stripe.com/v1/payment_pages/{cs}/update",
      pm_url: "https://api.stripe.com/v1/payment_methods",
      confirm_url_tmpl: "https://api.stripe.com/v1/payment_pages/{cs}/confirm",
      poll_url_tmpl: "https://api.stripe.com/v1/payment_pages/{cs}",
    },
    tls: {
      impersonate: "chrome",
      user_agent: "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36",
      accept_language: "en-US,en;q=0.9",
    },
    proxy: {
      default_pool: "qg_resi_pool",
      health_check_interval: 30,
      max_concurrent_per_node: 3,
      qg_super_pool: { host: "overseas.tunnel.qg.net", port: 16629, auth_key: "VT****KP", auth_pwd: "6B****EF" },
      qg_resi_pool: { host: "overseas.tunnel.qg.net", port: 14408, auth_key: "VX****1B", auth_pwd: "9D****1C" },
      proxy_711: { enabled: true, relay_base: "127.0.0.1", clash_port: 7897, relay_port_start: 18077, relay_port_end: 18117 },
    },
    momo: {
      enabled: false,
      patches: [
        { name: "connect_intercept", desc: "L1: intercept api.stripe.com CONNECT", enabled: true },
        { name: "dns_fix", desc: "L2: Clash fake-ip DoH Reparse", enabled: true },
        { name: "pm_inject", desc: "L3: payment_method injection", enabled: true },
        { name: "confirm_build", desc: "L4: confirm payload structure", enabled: true },
        { name: "resolve_regex", desc: "L5: MoMo pay URL regular", enabled: true },
      ],
    },
    paypal: {
      ba_url_pattern: "https://www.paypal.com/agreements/approve?ba_token=...",
      pm_redirect_pattern: "https://pm-redirects.stripe.com/authorize/...",
      blocked_countries: ["AF", "BY", "CU", "EG", "IR", "KP", "LY", "MM", "RU", "SD", "SO", "SS", "SY", "YE"],
      success_criteria: [
        "init.invoice.amount_due == 0 (zero amount)",
        "redirect match pm-redirects.stripe.com/authorize/",
        "final URL match paypal.com/agreements/approve?ba_token=",
      ],
    },
  };
}
