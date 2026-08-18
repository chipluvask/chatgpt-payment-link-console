import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";
import type { StageName, StageCfg, BranchCfg, BranchName } from "../types";
import { StageSettingsPanel } from "../components/chain/StageSettings";

/* ==========================================================================
   MoMo lift chain — Lift chain configuration module (Seven-segment export configuration)
   Lift chain starts at Token Library (branch: momo) · output in success inventory · Progress in link monitoring
   ========================================================================== */

export function MomoView() {
  /* ── Section 7 Exit (momo branch) ── */
  const [branch, setBranch] = useState<BranchCfg | null>(null);
  const [countryOptions, setCountryOptions] = useState<{ code: string; capital?: string }[]>([]);
  const [savingStage, setSavingStage] = useState<string>("");
  const [savingFlags, setSavingFlags] = useState(false);
  const [result, setResult] = useState("");

  const loadBranch = useCallback(async () => {
    try {
      const data = await api("/api/config");
      if (data && data.ok && data.chain?.branches?.momo) {
        setBranch(data.chain.branches.momo);
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
      await api("/api/config/branch", "POST", { branch: "momo", stages: { [stage]: patch } });
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
      await api("/api/config/branch", "POST", { branch: "momo", ...patch });
      setBranch((prev) => (prev ? { ...prev, ...patch } : prev));
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
          <h2 className="page-title">MoMo lift chain</h2>
          <p className="page-sub">
            Seven-segment export configuration · Channel verification (momo) · segment follow · billing country — Start at Token Library
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
          branchName="momo"
          branch={branch}
          countries={countryOptions}
          onSaveStage={handleSaveStage}
          onSaveFlags={handleSaveFlags}
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
        This page is only responsible for <b>MoMo Exit configuration of the link</b>：choose Token And submit links in batches{" "}
        <b>Token Library</b>（chain branch selection「MoMo lift chain」）；Check link progress<b>Link monitoring</b>；
        output payment URL look<b>successful inventory</b>。
      </div>
    </div>
  );
}

/* ==========================================================================
   Mock branch (Used to render the seven-segment panel when the backend is offline)
   ========================================================================== */
function makeMockBranch(): BranchCfg {
  const mkStages = (cc: string[]): Partial<Record<StageName, StageCfg>> => ({
    checkout: { countries: cc.length ? cc : ["VN"], timeout: 15, retry: 3 },
    init: { countries: ["VN"], timeout: 10, retry: 3 },
    update: { countries: ["VN"], timeout: 10, retry: 3 },
    provider: { countries: ["VN"], timeout: 8, retry: 3 },
    approve: { countries: ["VN"], timeout: 6, retry: 3 },
    poll: { countries: ["VN"], timeout: 25, retry: 1, poll_interval: 0.75, max_polls: 40 },
    resolve: { countries: ["VN"], timeout: 20, retry: 2 },
  });

  return {
    name: "momo",
    label: "MoMo lift chain",
    channel: "momo",
    token_source: "momo",
    require_zero: true,
    channel_check: true,
    dual_init: true,
    init0_ccs: ["VN"],
    init1_ccs: ["VN"],
    init_t_ccs: ["VN"],
    follow_checkout: true,
    billing_country: "auto",
    attempts: 8,
    stages: mkStages(["VN"]),
  };
}
