import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";
import type { StageName, StageCfg, BranchCfg } from "../types";
import { CountrySelect, StageRow } from "../components/chain/StageSettings";

/* ==========================================================================
   Straight card chain — Simplified configuration page (only 2 part: checkout → update press 0)
   pay.153 ph_short model: proxy pool 1=US create PH/PHP Checkout, proxy pool 2=TR Apply Offers
   ========================================================================== */

const DIRECT_STAGES: StageName[] = ["checkout", "update"];

export function DirectView() {
  const [branch, setBranch] = useState<BranchCfg | null>(null);
  const [countryOptions, setCountryOptions] = useState<{ code: string; capital?: string }[]>([]);
  const [savingStage, setSavingStage] = useState<string>("");
  const [savingFlags, setSavingFlags] = useState(false);
  const [result, setResult] = useState("");

  const loadBranch = useCallback(async () => {
    try {
      const data = await api("/api/config");
      if (data && data.ok && data.chain?.branches?.direct) {
        setBranch(data.chain.branches.direct);
        setResult("");
      } else {
        setBranch(makeMockBranch());
        setResult("Backend offline，Show default configuration");
      }
    } catch {
      setBranch(makeMockBranch());
      setResult("Backend offline，Show default configuration");
    }
  }, []);

  const loadCountries = useCallback(async () => {
    try {
      const data = await api("/api/billing/templates");
      if (data && data.ok && Array.isArray(data.templates)) {
        setCountryOptions(
          data.templates.map((t: any) => ({
            code: t.country,
            capital: `${t.city} · ${t.currency}`,
          }))
        );
      }
    } catch {
      setCountryOptions([]);
    }
  }, []);

  useEffect(() => {
    loadBranch();
    loadCountries();
  }, [loadBranch, loadCountries]);

  const handleSaveStage = async (stage: StageName, patch: Partial<StageCfg>) => {
    setSavingStage(stage);
    try {
      await api("/api/config/branch", "POST", { branch: "direct", stages: { [stage]: patch } });
      setBranch((prev) => {
        if (!prev) return prev;
        return {
          ...prev,
          stages: { ...prev.stages, [stage]: { ...(prev.stages[stage] as StageCfg), ...patch } as StageCfg },
        };
      });
    } catch {
      // silence
    } finally {
      setSavingStage("");
    }
  };

  const handleSaveFlags = async (patch: Partial<BranchCfg>) => {
    setSavingFlags(true);
    try {
      await api("/api/config/branch", "POST", { branch: "direct", ...patch });
      setBranch((prev) => (prev ? { ...prev, ...patch } : prev));
    } catch {
      // silence
    } finally {
      setSavingFlags(false);
    }
  };

  const stages = branch?.stages || {};

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h2 className="page-title">Straight card chain</h2>
          <p className="page-sub">
            checkout(US exit / PH bill) → update(TR outlet pressure 0) → output checkout short chain
          </p>
        </div>
        <div className="page-actions">
          <button className="btn" onClick={loadBranch}>
            Refresh configuration
          </button>
        </div>
      </div>

      <div className="card settings-panel">
        <div className="card-head">
          <span className="card-title">Direct card · two sections of pipe</span>
          <span className="card-hint">
            channel: card · token Library: direct
            {savingFlags && <span style={{ marginLeft: 8, color: "var(--accent-strong)" }}>Saving…</span>}
          </span>
        </div>
        <div className="card-body">
          <div className="setting-row">
            <span className="setting-label">billing country</span>
            <div className="setting-control" style={{ flex: 1, gap: 10 }}>
              <CountrySelect
                value={[branch?.billing_country || "PH"]}
                options={countryOptions}
                autoLabel="AUTO · follow checkout part"
                onChange={(v) => onSaveFlagsWrapper(v, handleSaveFlags, setSavingFlags)}
              />
              <span className="muted" style={{ fontSize: 11.5, width: 90, flexShrink: 0 }}>
                Fixed bill country
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
                value={branch?.attempts || 8}
                onChange={(e) => handleSaveFlags({ attempts: Math.max(1, +e.target.value) })}
                style={{ width: 140 }}
              />
              <span className="muted" style={{ fontSize: 11.5, width: 90, flexShrink: 0 }}>
                Every Token Maximum number of rounds to try
              </span>
            </div>
          </div>
        </div>

        <div className="card-body" style={{ borderTop: "1px solid var(--border-faint)" }}>
          {DIRECT_STAGES.map((stage) => {
            const sc = (stages[stage] as StageCfg) || { countries: [], timeout: 45, retry: 3 };
            return (
              <StageRow
                key={stage}
                stage={stage}
                cfg={sc}
                countries={countryOptions}
                onSave={(st, patch) => handleSaveStage(st as StageName, patch)}
                saving={savingStage === stage}
              />
            );
          })}
        </div>
        <div className="card-body" style={{ borderTop: "1px solid var(--border-faint)" }}>
          <div className="flow-chain" style={{ borderBottom: "none", padding: "2px 0 0" }}>
            {DIRECT_STAGES.map((stage, i) => {
              const sc = stages[stage];
              const cc = (sc as StageCfg)?.countries?.[0] || "—";
              const label = cc === "auto" ? "AUTO" : cc;
              return (
                <span key={stage} style={{ display: "inline-flex", alignItems: "center", gap: 8 }}>
                  <span className="flow-node">
                    {stage.toUpperCase()} {label}
                  </span>
                  {i < DIRECT_STAGES.length - 1 && <span className="flow-arrow">→</span>}
                </span>
              );
            })}
            <span className="flow-arrow">→</span>
            <span className="flow-node accent">short chain</span>
          </div>
        </div>
      </div>

      <div className="note" style={{ marginTop: 14 }}>
        <b>pay.153 formula</b>：proxy pool 1 use <b>US</b> create PH/PHP Checkout，proxy pool 2 use{" "}
        <b>TR</b> Apply Offers（press 0）。short chain output：<code>chatgpt.com/checkout/openai_llc/oaics_…</code>
      </div>

      {result && (
        <div className="note" style={{ marginTop: 14 }}>
          {result}
        </div>
      )}
    </div>
  );
}

function onSaveFlagsWrapper(
  v: string[],
  save: (patch: Partial<BranchCfg>) => void,
  setSaving: (b: boolean) => void
) {
  setSaving(true);
  try {
    save({ billing_country: (v[0] || "auto") === "auto" ? "auto" : v[0] });
  } finally {
    setSaving(false);
  }
}

function makeMockBranch(): BranchCfg {
  const mkStages = (): Partial<Record<StageName, StageCfg>> => ({
    checkout: { countries: ["US"], timeout: 45, retry: 3 },
    update: { countries: ["TR"], timeout: 45, retry: 3 },
  });
  return {
    name: "direct",
    label: "Straight card chain",
    channel: "card",
    token_source: "direct",
    require_zero: true,
    channel_check: false,
    dual_init: false,
    init0_ccs: [],
    init1_ccs: [],
    init_t_ccs: [],
    follow_checkout: false,
    billing_country: "PH",
    attempts: 8,
    stages: mkStages(),
  };
}
