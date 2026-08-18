import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";
import type { StageName, StageCfg, BranchCfg, OaicsStageName, OaicsBranchCfg } from "../types";
import { StageSettingsPanel } from "../components/chain/StageSettings";

/* ==========================================================================
   PayPal refining — Lift chain configuration module (Seven-segment export configuration)
   Lift chain starts at Token Library (branch: paypal) · output in success inventory · Progress in link monitoring
   ========================================================================== */

export function PayPalExtractView() {
  /* ── Section 7 Exit (paypal branch) ── */
  const [branch, setBranch] = useState<BranchCfg | null>(null);
  const [countryOptions, setCountryOptions] = useState<{ code: string; capital?: string }[]>([]);
  const [savingStage, setSavingStage] = useState<string>("");
  const [savingFlags, setSavingFlags] = useState(false);
  const [result, setResult] = useState("");

  const loadBranch = useCallback(async () => {
    try {
      const data = await api("/api/config");
      if (data && data.ok && data.chain?.branches?.paypal) {
        setBranch(data.chain.branches.paypal);
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
      await api("/api/config/branch", "POST", { branch: "paypal", stages: { [stage]: patch } });
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
      await api("/api/config/branch", "POST", { branch: "paypal", ...patch });
      setBranch((prev) => (prev ? { ...prev, ...patch } : prev));
    } catch {
      // silence
    } finally {
      setSavingFlags(false);
    }
  };

  const handleSaveOaicsStage = async (stage: OaicsStageName, patch: Partial<StageCfg>) => {
    setSavingStage(stage);
    try {
      await api("/api/config/branch", "POST", {
        branch: "paypal",
        oaics: {
          billing_country: branch?.oaics?.billing_country,
          attempts: branch?.oaics?.attempts,
          stages: { [stage]: patch },
        },
      });
      setBranch((prev) => {
        if (!prev?.oaics) return prev;
        return {
          ...prev,
          oaics: {
            ...prev.oaics,
            stages: { ...prev.oaics.stages, [stage]: { ...(prev.oaics.stages[stage] as StageCfg), ...patch } as StageCfg },
          },
        };
      });
    } catch {
      // silence
    } finally {
      setSavingStage("");
    }
  };

  const handleSaveOaicsFlags = async (patch: Partial<OaicsBranchCfg>) => {
    setSavingFlags(true);
    try {
      await api("/api/config/branch", "POST", {
        branch: "paypal",
        oaics: { ...(branch?.oaics || {}), ...patch } as any,
      });
      setBranch((prev) => (prev ? { ...prev, oaics: { ...(prev.oaics || ({} as OaicsBranchCfg)), ...patch } } : prev));
    } catch {
      // silence
    } finally {
      setSavingFlags(false);
    }
  };

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h2 className="page-title">PayPal refining</h2>
          <p className="page-sub">
            Dual link configuration · Original seventh section (cs_live / hosted) + OAICS fifth section (custom pure HTTP)
          </p>
        </div>
        <div className="page-actions">
          <button className="btn" onClick={loadBranch}>
            Refresh configuration
          </button>
        </div>
      </div>

      {branch && (
        <StageSettingsPanel
          branchName="paypal"
          branch={branch}
          countries={countryOptions}
          onSaveStage={handleSaveStage}
          onSaveFlags={handleSaveFlags}
          onSaveOaicsStage={handleSaveOaicsStage}
          onSaveOaicsFlags={handleSaveOaicsFlags}
          savingStage={savingStage}
          savingFlags={savingFlags}
        />
      )}

      {result && (
        <div className="note" style={{ marginTop: 14 }}>
          {result}
        </div>
      )}

      <div className="note" style={{ marginTop: 14 }}>
        This page is only responsible for <b>PayPal Refining the egress configuration of the link</b>：choose Token And submit links in batches{" "}
        <b>Token Library</b>（chain branch selection「PayPal refining」）；Check link progress<b>Link monitoring</b>；
        output BA look<b>successful inventory</b>。PayPal Payment authorization is a separate process，See<b>Payment authorization</b>Page。
      </div>
    </div>
  );
}

/* ==========================================================================
   Mock branch (Used to render the seven-segment panel when the backend is offline)
   ========================================================================== */
function makeMockBranch(): BranchCfg {
  const mkStages = (cc: string[]): Partial<Record<StageName, StageCfg>> => ({
    checkout: { countries: ["auto"], timeout: 15, retry: 3 },
    init: { countries: ["auto"], timeout: 10, retry: 3 },
    update: { countries: ["US"], timeout: 10, retry: 3 },
    provider: { countries: ["auto"], timeout: 8, retry: 3 },
    approve: { countries: ["auto"], timeout: 6, retry: 3 },
    poll: { countries: ["auto"], timeout: 25, retry: 1, poll_interval: 0.75, max_polls: 40 },
    resolve: { countries: ["auto"], timeout: 20, retry: 2 },
  });

  return {
    name: "paypal",
    label: "PayPal refining",
    channel: "paypal",
    token_source: "stripe",
    require_zero: true,
    channel_check: true,
    dual_init: false,
    init0_ccs: ["auto"],
    init1_ccs: ["US"],
    init_t_ccs: ["auto"],
    follow_checkout: false,
    billing_country: "auto",
    attempts: 8,
    stages: mkStages([]),
    oaics: {
      label: "OAICS fifth section",
      billing_country: "auto",
      attempts: 5,
      stages: {
        checkout: { countries: ["US"], timeout: 15, retry: 3 },
        taxes: { countries: ["US"], timeout: 15, retry: 3 },
        provider: { countries: ["US"], timeout: 20, retry: 3 },
        confirm: { countries: ["US"], timeout: 20, retry: 3 },
        resolve: { countries: ["US"], timeout: 20, retry: 2 },
      },
    },
  };
}
