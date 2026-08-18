import { useEffect, useState } from "react";
import { STAGE_ORDER, STAGE_SHORT, STAGE_CN, OAICS_STAGE_ORDER, OAICS_STAGE_SHORT, OAICS_STAGE_CN, BRANCH_CN } from "../../types";
import type { StageName, BranchName, StageCfg, BranchCfg, OaicsStageName, OaicsBranchCfg } from "../../types";

/* ==========================================================================
   Link link page sharing component: Country drop-down radio selection(auto+search) / branch switch / segment configuration line / seven segment panel
   (PayPal refining / MoMo lift chain / Grok link Common to other link pages)
   ========================================================================== */

export const flag = (cc: string): string => {
  if (!cc || cc.length !== 2) return "";
  const A = 0x1f1e6, Z = 0x1f1ff;
  const c = cc.toUpperCase().charCodeAt(0) - 65;
  const c2 = cc.toUpperCase().charCodeAt(1) - 65;
  if (c < 0 || c > 25 || c2 < 0 || c2 > 25) return "";
  return String.fromCodePoint(A + c, A + c2);
};

/* All candidate countries (ISO 3166 Capital code, history checkout_auto_countries pool) */
export const ALL_COUNTRY_CODES: string[] = `AD,AE,AF,AG,AI,AL,AM,AO,AR,AS,AT,AU,AW,AZ,BA,BB,BD,BE,BF,BG,BH,BI,BJ,BL,BM,BN,BO,BR,BS,BT,BW,BY,BZ,CA,CD,CF,CG,CH,CI,CK,CL,CM,CO,CR,CU,CV,CW,CY,CZ,DE,DJ,DK,DM,DO,DZ,EC,EE,EG,ER,ES,ET,EU,FI,FJ,FO,FR,GA,GB,GD,GE,GF,GH,GI,GL,GM,GN,GP,GQ,GR,GT,GU,GW,GY,HK,HN,HR,HT,HU,ID,IE,IL,IN,IQ,IR,IS,IT,JM,JO,JP,KE,KG,KH,KI,KM,KN,KR,KW,KY,KZ,LA,LB,LC,LI,LK,LR,LS,LT,LU,LV,LY,MA,MC,MD,ME,MG,MK,ML,MM,MN,MO,MQ,MR,MS,MT,MU,MV,MW,MX,MY,MZ,NA,NC,NE,NG,NI,NL,NO,NP,NZ,OM,PA,PE,PF,PG,PH,PK,PL,PM,PR,PT,PW,PY,QA,RE,RO,RS,RU,RW,SA,SB,SC,SD,SE,SG,SI,SK,SL,SM,SN,SO,SR,ST,SV,SX,SY,SZ,TC,TD,TG,TH,TJ,TL,TM,TN,TO,TR,TT,TW,TZ,UA,UG,US,UY,UZ,VC,VE,VG,VI,VN,VU,WS,YE,YT,ZA,ZM,ZW`.split(",");

const AUTO = "auto";

/* --------------------------------------------------------------------------
   Country drop-down radio selection: AUTO(automatic rotation) fixed on top + Full country pool search selection
   - Input box real-time filtering (Case compatible, enter us Sieve out US)
   - Single choice radio style; Select value to save ["auto"] or ["US"] array
   -------------------------------------------------------------------------- */
export function CountrySelect({
  value,
  options,
  onChange,
  blocked = [],
  autoLabel = "AUTO · automatic rotation",
  disabled = false,
}: {
  value: string[];
  options: { code: string; capital?: string }[];
  onChange: (v: string[]) => void;
  blocked?: string[];
  autoLabel?: string;
  disabled?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const sel = value && value.length > 0 ? value[0] : AUTO;
  const display = sel === AUTO ? { code: AUTO, label: autoLabel } : { code: sel, label: `${flag(sel)} ${sel}` };

  const pool = options.length > 0 ? options.map((o) => o.code) : ALL_COUNTRY_CODES;
  const q = query.trim().toUpperCase();
  const filtered = pool.filter((c) => {
    if (c === sel) return false;
    if (blocked.includes(c)) return false;
    if (!q) return true;
    return c.includes(q) || q === c;
  });

  const choose = (code: string) => {
    if (disabled) return;
    onChange(code === AUTO ? [AUTO] : [code]);
    setOpen(false);
    setQuery("");
  };

  return (
    <div style={{ position: "relative", flex: 1, minWidth: 200 }}>
      <button
        className="btn btn-sm"
        style={{
          width: "100%",
          textAlign: "left",
          justifyContent: "space-between",
          gap: 8,
          minHeight: 32,
          ...(disabled
            ? { cursor: "not-allowed", opacity: 0.65, background: "var(--bg-raised)", borderColor: "transparent" }
            : {}),
        }}
        onClick={() => !disabled && setOpen(!open)}
        type="button"
        title={disabled ? "Seven-stage configuration has been followed · read only" : undefined}
      >
        <span
          style={{
            fontSize: 12,
            color: sel === AUTO ? "var(--accent-strong)" : "inherit",
            fontWeight: sel === AUTO ? 600 : 400,
          }}
        >
          {sel === AUTO ? autoLabel : display.label}
        </span>
        <span style={{ opacity: 0.6, fontSize: 10 }}>{disabled ? "🔒" : open ? "▲" : "▼"}</span>
      </button>
      {open && !disabled && (
        <div
          style={{
            position: "absolute",
            top: "100%",
            left: 0,
            right: 0,
            zIndex: 50,
            marginTop: 4,
            background: "var(--bg-card)",
            border: "1px solid var(--border)",
            borderRadius: 10,
            boxShadow: "0 10px 32px rgba(0,0,0,.35)",
            padding: 8,
          }}
        >
          <input
            className="input"
            type="text"
            placeholder="Search country… enter us Sieve out US"
            value={query}
            autoFocus
            onChange={(e) => setQuery(e.target.value)}
            style={{ width: "100%", marginBottom: 6 }}
          />
          <div style={{ maxHeight: 220, overflowY: "auto" }}>
            <label
              style={{
                display: "flex",
                alignItems: "center",
                gap: 8,
                padding: "6px 8px",
                borderRadius: 6,
                fontSize: 12,
                cursor: "pointer",
                background: sel === AUTO ? "var(--accent-dim)" : "transparent",
              }}
            >
              <input
                type="radio"
                checked={sel === AUTO}
                onChange={() => choose(AUTO)}
              />
              <span style={{ fontWeight: 600 }}>AUTO · automatic rotation</span>
              <span className="muted" style={{ fontSize: 10 }}>Dynamic selection of all national pools</span>
            </label>
            {filtered.map((c) => (
              <label
                key={c}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 8,
                  padding: "5px 8px",
                  borderRadius: 6,
                  fontSize: 12,
                  cursor: "pointer",
                  background: sel === c ? "var(--accent-dim)" : "transparent",
                }}
              >
                <input type="radio" checked={sel === c} onChange={() => choose(c)} />
                <span>{flag(c)} {c}</span>
                {q && <span className="muted" style={{ fontSize: 10 }}>✓ match</span>}
              </label>
            ))}
            {filtered.length === 0 && (
              <div className="muted" style={{ fontSize: 12, padding: 6 }}>
                No matching country
              </div>
            )}
          </div>
          <div
            style={{
              display: "flex",
              justifyContent: "flex-end",
              borderTop: "1px solid var(--border-faint)",
              marginTop: 6,
              paddingTop: 6,
            }}
          >
            <button className="btn btn-primary btn-sm" type="button" onClick={() => setOpen(false)}>
              Finish
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

/* --------------------------------------------------------------------------
   branch switch row
   -------------------------------------------------------------------------- */
export function BranchToggle({
  label,
  desc,
  value,
  onChange,
}: {
  label: string;
  desc: string;
  value: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <div className="setting-row">
      <span className="setting-label">{label}</span>
      <div className="setting-control" style={{ gap: 10 }}>
        <label className="switch">
          <input
            type="checkbox"
            checked={value}
            onChange={(e) => onChange(e.target.checked)}
          />
          <span className="switch-track" />
        </label>
        <span className="muted" style={{ fontSize: 11.5 }}>{desc}</span>
      </div>
    </div>
  );
}

/* --------------------------------------------------------------------------
   segment configuration line (Country drop-down radio selection + time out/Try again —— Click on a field to edit, Changes automatically saved)
   Support seven segments (StageName) and OAICS fifth section (OaicsStageName) share
   -------------------------------------------------------------------------- */
export function StageRow({
  stage,
  cfg,
  countries,
  onSave,
  saving,
  shortName,
  cnName,
  isOaics = false,
  desc,
}: {
  stage: StageName | OaicsStageName;
  cfg: StageCfg;
  countries: { code: string; capital?: string }[];
  onSave: (stage: string, patch: Partial<StageCfg>) => void;
  saving: boolean;
  shortName?: string;
  cnName?: string;
  isOaics?: boolean;
  desc?: string;
}) {
  const [sel, setSel] = useState<string[]>(cfg.countries || []);
  const [timeout, setTimeout] = useState(String(cfg.timeout));
  const [retry, setRetry] = useState(String(cfg.retry));
  const [pollInterval, setPollInterval] = useState(String(cfg.poll_interval ?? ""));
  const [maxPolls, setMaxPolls] = useState(String(cfg.max_polls ?? ""));
  const [active, setActive] = useState<"timeout" | "retry" | "poll_interval" | "max_polls" | null>(null);

  useEffect(() => {
    setSel(cfg.countries || []);
    setTimeout(String(cfg.timeout));
    setRetry(String(cfg.retry));
    setPollInterval(String(cfg.poll_interval ?? ""));
    setMaxPolls(String(cfg.max_polls ?? ""));
  }, [cfg]);

  const isPoll = stage === "poll";

  const commit = (patch: Partial<StageCfg>) => {
    onSave(stage, patch);
    setActive(null);
  };

  const short = shortName ?? (isOaics ? OAICS_STAGE_SHORT[stage as OaicsStageName] : STAGE_SHORT[stage as StageName]);
  const cn = cnName ?? (isOaics ? OAICS_STAGE_CN[stage as OaicsStageName] : STAGE_CN[stage as StageName]);

  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: 14,
        padding: "11px 0",
        borderBottom: "1px solid var(--border-faint)",
        flexWrap: "wrap",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 8, width: 130, flexShrink: 0 }}>
        <span
          className="tag"
          style={isOaics
            ? { color: "var(--oaics, #3b82f6)", background: "rgba(59,130,246,.12)", border: "1px solid rgba(59,130,246,.35)" }
            : { color: "var(--accent-strong)", background: "var(--accent-dim)", border: "1px solid rgba(108,108,248,.3)" }}
        >
          {short}
        </span>
        <span style={{ fontWeight: 600, fontSize: 12.5 }}>{cn}</span>
        <span className="muted" style={{ fontSize: 10.5, fontFamily: "var(--font-mono)" }}>
          {stage}
        </span>
      </div>

      <div style={{ flex: 1, minWidth: 220 }}>
        <CountrySelect
          value={sel}
          options={countries}
          onChange={(v) => {
            setSel(v);
            onSave(stage, { countries: v });
          }}
        />
        {desc && (
          <div className="muted" style={{ fontSize: 10.5, marginTop: 4, lineHeight: 1.4 }}>
            {desc}
          </div>
        )}
      </div>

      <div style={{ display: "flex", gap: 8, alignItems: "center", flexShrink: 0 }}>
        <div className="inline-field">
          <label>time out(s)</label>
          <input
            className="input"
            type="number"
            style={active === "timeout" ? undefined : { width: 70, borderColor: "transparent", background: "var(--bg-raised)", cursor: "pointer" }}
            value={timeout}
            onFocus={() => setActive("timeout")}
            onBlur={() => commit({ timeout: parseInt(timeout) || 10 })}
            onChange={(e) => setTimeout(e.target.value)}
          />
        </div>
        <div className="inline-field">
          <label>Try again</label>
          <input
            className="input"
            type="number"
            style={active === "retry" ? undefined : { width: 70, borderColor: "transparent", background: "var(--bg-raised)", cursor: "pointer" }}
            value={retry}
            onFocus={() => setActive("retry")}
            onBlur={() => commit({ retry: parseInt(retry) || 3 })}
            onChange={(e) => setRetry(e.target.value)}
          />
        </div>
        {isPoll && (
          <>
            <div className="inline-field">
              <label>Polling interval(s)</label>
              <input
                className="input"
                type="number"
                step="0.01"
                style={active === "poll_interval" ? undefined : { width: 70, borderColor: "transparent", background: "var(--bg-raised)", cursor: "pointer" }}
                value={pollInterval}
                onFocus={() => setActive("poll_interval")}
                onBlur={() => commit({ poll_interval: parseFloat(pollInterval) || 0.75 })}
                onChange={(e) => setPollInterval(e.target.value)}
              />
            </div>
            <div className="inline-field">
              <label>Maximum rounds</label>
              <input
                className="input"
                type="number"
                style={active === "max_polls" ? undefined : { width: 70, borderColor: "transparent", background: "var(--bg-raised)", cursor: "pointer" }}
                value={maxPolls}
                onFocus={() => setActive("max_polls")}
                onBlur={() => commit({ max_polls: parseInt(maxPolls) || 40 })}
                onChange={(e) => setMaxPolls(e.target.value)}
              />
            </div>
          </>
        )}
        {saving && <span className="muted" style={{ fontSize: 11 }}>Saving…</span>}
      </div>
    </div>
  );
}

/* --------------------------------------------------------------------------
   Seven-segment pipe setting panel (General link page: switch + pairinitexit + Seven sections + flow bar)
   Support sub-column: paypal branch contains oaics fifth section (cs Seven sections / OAICS fifth section)
   -------------------------------------------------------------------------- */
export function StageSettingsPanel({
  branchName,
  branch,
  countries,
  blocked,
  onSaveStage,
  onSaveFlags,
  onSaveOaicsStage,
  onSaveOaicsFlags,
  savingStage,
  savingFlags,
}: {
  branchName: BranchName;
  branch: BranchCfg;
  countries: { code: string; capital?: string }[];
  blocked?: string[];
  onSaveStage: (stage: StageName, patch: Partial<StageCfg>) => void;
  onSaveFlags: (patch: Partial<BranchCfg>) => void;
  onSaveOaicsStage?: (stage: OaicsStageName, patch: Partial<StageCfg>) => void;
  onSaveOaicsFlags?: (patch: Partial<OaicsBranchCfg>) => void;
  savingStage: string;
  savingFlags: boolean;
}) {
  const stages = branch.stages || {};
  const hasOaics = !!branch.oaics;
  const [tab, setTab] = useState<"cs" | "oaics">("cs");
  const chanLabel: Record<string, string> = {
    paypal: "PayPal channel",
    momo: "MoMo channel",
    card: "Card channel",
    link: "link channel",
    pix: "PIX channel",
    ideal: "iDEAL channel",
    upi: "UPI channel",
    kakao: "Kakao Pay channel",
    blik: "BLIK channel",
    twint: "TWINT channel",
  };

  if (hasOaics) {
    return (
      <div className="card settings-panel">
        <div className="card-head">
          <span className="card-title">
            {BRANCH_CN[branchName]} · Lift chain pipe
          </span>
          <span className="card-hint">
            Channel verification: {chanLabel[branch.channel] || branch.channel} · token Library: {branch.token_source || branchName}
          </span>
        </div>
        <div className="pipeline-tabs" style={{ display: "flex", gap: 6, padding: "10px 16px 0" }}>
          <button
            className={`btn btn-sm ${tab === "cs" ? "btn-primary" : "btn-ghost"}`}
            onClick={() => setTab("cs")}
          >
            Original seventh section (cs_live / hosted)
          </button>
          <button
            className={`btn btn-sm ${tab === "oaics" ? "btn-primary" : "btn-ghost"}`}
            onClick={() => setTab("oaics")}
            style={tab === "oaics" ? { background: "var(--oaics, #3b82f6)", borderColor: "var(--oaics, #3b82f6)" } : { color: "var(--oaics, #3b82f6)" }}
          >
            OAICS fifth section (custom pure HTTP) 🔒
          </button>
        </div>
        {tab === "cs" ? (
          <CsStages
            branchName={branchName}
            branch={branch}
            countries={countries}
            onSaveStage={onSaveStage}
            onSaveFlags={onSaveFlags}
            savingStage={savingStage}
            savingFlags={savingFlags}
          />
        ) : (
          <OaicsStages
            branchName={branchName}
            oaics={branch.oaics!}
            csBranch={branch}
            countries={countries}
            onSaveOaicsStage={onSaveOaicsStage || (() => {})}
            onSaveOaicsFlags={onSaveOaicsFlags || (() => {})}
            savingFlags={savingFlags}
          />
        )}
      </div>
    );
  }

  return (
    <CsStages
      branchName={branchName}
      branch={branch}
      countries={countries}
      onSaveStage={onSaveStage}
      onSaveFlags={onSaveFlags}
      savingStage={savingStage}
      savingFlags={savingFlags}
    />
  );
}

function OaicsStages({
  branchName,
  oaics,
  csBranch,
  countries,
  onSaveOaicsStage,
  onSaveOaicsFlags,
  savingFlags,
}: {
  branchName: BranchName;
  oaics: OaicsBranchCfg;
  /** Seven-segment configuration (Read-only mapped data source: oaics Five paragraphs follow seven paragraphs) */
  csBranch: BranchCfg;
  countries: { code: string; capital?: string }[];
  onSaveOaicsStage: (stage: OaicsStageName, patch: Partial<StageCfg>) => void;
  onSaveOaicsFlags: (patch: Partial<OaicsBranchCfg>) => void;
  savingFlags: boolean;
}) {
  /* 2026-08-13: oaics Subconfiguration is obsolete read-only —— Five-section export countries/billing country/Currency follows seven segments
     (rear end pick_oaics_countries direct mapping, This page only displays, All controls are disabled) */
  const MAP_7: Record<OaicsStageName, StageName> = {
    checkout: "checkout",
    taxes: "update",
    provider: "provider",
    confirm: "approve",
    resolve: "resolve",
  };
  const csStages = csBranch.stages || {};
  const csBilling = csBranch.billing_country || "auto";
  const csCountry = (s: StageName): string => {
    const c = (csStages[s] as StageCfg)?.countries;
    if (!c || c.length === 0 || c[0] === "auto") return "auto";
    return c[0];
  };
  return (
    <>
      <div className="card-body" style={{ borderTop: "1px solid var(--border-faint)" }}>
        <div className="section-head">
          <span className="section-title">OAICS Exit Section 5 🔒 read only</span>
          <span className="muted" style={{ fontSize: 11.5 }}>
            oaics_ session ✓ fifth section · Follow the seven-segment configuration (Below is the mapping result, Not editable)
          </span>
        </div>
        <div
          className="note"
          style={{ marginBottom: 10, fontSize: 11.5, padding: "6px 10px" }}
        >
          OAICS Five-section export countries = Seven corresponding sections: checkout←Bill, please · taxes←renew · provider←payment provider ·
          confirm←approve · resolve←parse; billing country/Currency = Seven-dan bill country ({csBilling})
          {" · "}
          <span className="muted">rotation/Follow the seven-segment configuration and link operation.</span>
        </div>
        <div className="setting-row">
          <span className="setting-label">billing country</span>
          <div className="setting-control" style={{ flex: 1, gap: 10 }}>
            <CountrySelect
              value={[csBilling]}
              options={countries}
              autoLabel="AUTO · follow checkout part"
              onChange={() => {}}
              disabled
            />
            <span className="muted" style={{ fontSize: 11.5, width: 90, flexShrink: 0 }}>
              {csBilling !== "auto" ? "Fixed bill country (Seven sections)" : "follow checkout part (Seven sections)"}
            </span>
          </div>
        </div>
        <div className="setting-row">
          <span className="setting-label">always try</span>
          <div className="setting-control" style={{ flex: 1, gap: 10 }}>
            <input
              className="input"
              type="number"
              min={1}
              value={csBranch.attempts || 8}
              disabled
              style={{ width: 140, opacity: 0.65, cursor: "not-allowed", background: "var(--bg-raised)" }}
            />
            <span className="muted" style={{ fontSize: 11.5, width: 90, flexShrink: 0 }}>
              Follow seven paragraphs (Every Token Number of rounds to try)
            </span>
          </div>
        </div>
      </div>
      <div className="card-body" style={{ borderTop: "1px solid var(--border-faint)" }}>
        {OAICS_STAGE_ORDER.map((stage) => {
          const src = MAP_7[stage];
          const cc = csCountry(src);
          return (
            <div key={stage} className="setting-row">
              <span className="setting-label">
                {OAICS_STAGE_SHORT[stage]} {OAICS_STAGE_CN[stage]}
              </span>
              <div className="setting-control" style={{ flex: 1, gap: 10 }}>
                <CountrySelect
                  value={[cc]}
                  options={countries}
                  onChange={() => {}}
                  disabled
                />
                <span className="muted" style={{ fontSize: 11.5, width: 110, flexShrink: 0 }}>
                  ← Seven sections {STAGE_CN[src]} · read only
                </span>
              </div>
            </div>
          );
        })}
      </div>
      <div className="card-body" style={{ borderTop: "1px solid var(--border-faint)" }}>
        <div className="flow-chain" style={{ borderBottom: "none", padding: "2px 0 0" }}>
          {OAICS_STAGE_ORDER.map((stage, i) => {
            const cc = csCountry(MAP_7[stage]);
            const label = cc === "auto" ? "AUTO" : `${flag(cc)}${cc}`;
            return (
              <span key={stage} style={{ display: "inline-flex", alignItems: "center", gap: 8 }}>
                <span className="flow-node" style={{ borderColor: "var(--oaics, #3b82f6)", color: "var(--oaics, #3b82f6)" }}>
                  {OAICS_STAGE_SHORT[stage]} {label}
                </span>
                {i < OAICS_STAGE_ORDER.length - 1 && <span className="flow-arrow">→</span>}
              </span>
            );
          })}
        </div>
      </div>
    </>
  );
}

function CsStages({
  branchName,
  branch,
  countries,
  onSaveStage,
  onSaveFlags,
  savingStage,
  savingFlags,
}: {
  branchName: BranchName;
  branch: BranchCfg;
  countries: { code: string; capital?: string }[];
  onSaveStage: (stage: StageName, patch: Partial<StageCfg>) => void;
  onSaveFlags: (patch: Partial<BranchCfg>) => void;
  savingStage: string;
  savingFlags: boolean;
}) {
  const stages = branch.stages || {};
  const chanLabel: Record<string, string> = {
    paypal: "PayPal channel",
    momo: "MoMo channel",
    card: "Card channel",
    link: "link channel",
    pix: "PIX channel",
    ideal: "iDEAL channel",
    upi: "UPI channel",
    kakao: "Kakao Pay channel",
    blik: "BLIK channel",
    twint: "TWINT channel",
  };

  return (
    <div className="card settings-panel">
      <div className="card-head">
        <span className="card-title">
          {BRANCH_CN[branchName]} · seven sections of pipeline
        </span>
        <span className="card-hint">
          Channel verification: {chanLabel[branch.channel] || branch.channel} · token Library: {branch.token_source || branchName}
          {savingFlags && <span style={{ marginLeft: 8, color: "var(--accent-strong)" }}>Saving…</span>}
        </span>
      </div>
      <div className="card-body">
        <BranchToggle
          label="pair Init"
          desc="init0 Use the exit to get the channel type → init1 Go back to local area to verify the authenticity → init_t transition"
          value={!!branch.dual_init}
          onChange={(v) => onSaveFlags({ dual_init: v })}
        />
        <BranchToggle
          label="Payment channel verification"
          desc={`init returned payment_method_types Must contain ${branch.channel || "paypal"}`}
          value={!!branch.channel_check}
          onChange={(v) => onSaveFlags({ channel_check: v })}
        />
        <BranchToggle
          label="Amount verification"
          desc="init.invoice.amount_due Must be 0 (fail-closed)"
          value={!!branch.require_zero}
          onChange={(v) => onSaveFlags({ require_zero: v })}
        />
        <BranchToggle
          label="segment follow"
          desc="remove update outside the paragraph，The remaining exporting countries follow checkout part"
          value={!!branch.follow_checkout}
          onChange={(v) => onSaveFlags({ follow_checkout: v })}
        />
      </div>

      {branch.dual_init && (
        <div className="card-body" style={{ borderTop: "1px solid var(--border-faint)" }}>
          <div className="section-head">
            <span className="section-title">pair Init exit（init0 → init1 → init_t）</span>
          </div>
          {(
            [
              ["init0_ccs", "init0 · Take the exit", "take payment_method_types"],
              ["init1_ccs", "init1 · Authenticity export", "Local verification"],
              ["init_t_ccs", "init_t · Transitional export", "transition"],
            ] as const
          ).map(([key, label, desc]) => (
            <div className="setting-row" key={key}>
              <span className="setting-label">{label}</span>
              <div className="setting-control" style={{ flex: 1, gap: 10 }}>
                <CountrySelect
                  value={(branch[key] as string[]) || []}
                  options={countries}
                  onChange={(v) => onSaveFlags({ [key]: v })}
                />
                <span className="muted" style={{ fontSize: 11.5, width: 90, flexShrink: 0 }}>{desc}</span>
              </div>
            </div>
          ))}
        </div>
      )}

      <div className="card-body" style={{ borderTop: "1px solid var(--border-faint)" }}>
        <div className="section-head">
          <span className="section-title">billing country</span>
          <span className="muted" style={{ fontSize: 11.5 }}>provider Country of segment billing address · Changes automatically saved</span>
        </div>
        <div className="setting-row">
          <span className="setting-label">billing country</span>
          <div className="setting-control" style={{ flex: 1, gap: 10 }}>
            <CountrySelect
              value={[branch.billing_country || "auto"]}
              options={countries}
              autoLabel="AUTO · follow checkout part"
              onChange={(v) => onSaveFlags({ billing_country: (v[0] || "auto") === "auto" ? "auto" : v[0] })}
            />
            <span className="muted" style={{ fontSize: 11.5, width: 90, flexShrink: 0 }}>
              {branch.billing_country && branch.billing_country !== "auto"
                ? "Fixed bill country"
                : "follow checkout part"}
            </span>
          </div>
        </div>
        <div className="setting-row">
          <span className="setting-label">always try</span>
          <div className="setting-control" style={{ flex: 1, gap: 10 }}>
            <input
              className="input"
              type="number"
              min={1}
              value={branch.attempts || 8}
              onChange={(e) => {
                const v = Math.max(1, +e.target.value);
                onSaveFlags({ attempts: v });
              }}
              style={{ width: 140 }}
            />
            <span className="muted" style={{ fontSize: 11.5, width: 90, flexShrink: 0 }}>
              Every Token Maximum number of rounds to try
            </span>
          </div>
        </div>
      </div>

      <div className="card-body" style={{ borderTop: "1px solid var(--border-faint)" }}>
        {STAGE_ORDER.map((stage) => {
          const sc = (stages[stage] as StageCfg) || { countries: [], timeout: 10, retry: 3 };
          return (
            <StageRow
              key={stage}
              stage={stage}
              cfg={sc}
              countries={countries}
              onSave={(st, patch) => onSaveStage(st as StageName, patch)}
              saving={savingStage === stage}
            />
          );
        })}
      </div>
      <div className="card-body" style={{ borderTop: "1px solid var(--border-faint)" }}>
        <div className="flow-chain" style={{ borderBottom: "none", padding: "2px 0 0" }}>
          {STAGE_ORDER.map((stage, i) => {
            const sc = stages[stage];
            const cc = (sc as StageCfg)?.countries?.[0] || "—";
            const label = cc === "auto" ? "AUTO" : `${flag(cc)}${cc}`;
            return (
              <span key={stage} style={{ display: "inline-flex", alignItems: "center", gap: 8 }}>
                <span className="flow-node">
                  {STAGE_SHORT[stage]} {label}
                </span>
                {i < STAGE_ORDER.length - 1 && <span className="flow-arrow">→</span>}
              </span>
            );
          })}
        </div>
      </div>
    </div>
  );
}
