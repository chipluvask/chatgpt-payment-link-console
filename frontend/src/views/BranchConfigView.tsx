import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";
import type { StageName, StageCfg, BranchCfg, BranchName } from "../types";
import { StageSettingsPanel } from "../components/chain/StageSettings";

/* ==========================================================================
   General chain branch configuration page（iDEAL / UPI / Kakao / BLIK / TWINT）
   incoming branchName That is, rendering the seven-segment exit configuration of the branch
   ========================================================================== */

interface Props {
  branchName: BranchName;
  title: string;
  sub: string;
  defaultCountry: string;
  updateCountry: string;
}

export function BranchConfigView({ branchName, title, sub, defaultCountry, updateCountry }: Props) {
  const [branch, setBranch] = useState<BranchCfg | null>(null);
  const [countryOptions, setCountryOptions] = useState<{ code: string; capital?: string }[]>([]);
  const [savingStage, setSavingStage] = useState<string>("");
  const [savingFlags, setSavingFlags] = useState(false);
  const [result, setResult] = useState("");

  const loadBranch = useCallback(async () => {
    try {
      const data = await api("/api/config");
      if (data && data.ok && data.chain?.branches?.[branchName]) {
        setBranch(data.chain.branches[branchName]);
        setResult("");
      } else {
        setBranch(makeMockBranch(branchName, title, defaultCountry, updateCountry));
        setResult("Backend offline，Show default configuration");
      }
    } catch {
      setBranch(makeMockBranch(branchName, title, defaultCountry, updateCountry));
      setResult("Backend offline，Show default configuration");
    }
  }, [branchName, title, defaultCountry, updateCountry]);

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
      await api("/api/config/branch", "POST", { branch: branchName, stages: { [stage]: patch } });
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
      await api("/api/config/branch", "POST", { branch: branchName, ...patch });
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
          <h2 className="page-title">{title}</h2>
          <p className="page-sub">{sub}</p>
        </div>
        <div className="page-actions">
          <button className="btn" onClick={loadBranch}>
            Refresh configuration
          </button>
        </div>
      </div>

      {branch && (
        <StageSettingsPanel
          branchName={branchName}
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
        This page is only responsible for <b>{title}Link egress configuration</b>：choose Token And submit links in batches{" "}
        <b>Token Library</b>（chain branch selection「{title}」）；Check link progress<b>Link monitoring</b>；Look at the output
        <b>successful inventory</b>。
      </div>
    </div>
  );
}

/* ==========================================================================
   Mock branch (Used to render the seven-segment panel when the backend is offline)
   ========================================================================== */
function makeMockBranch(
  branchName: BranchName,
  label: string,
  defaultCountry: string,
  updateCountry: string
): BranchCfg {
  const mkStages = (cc: string[]): Partial<Record<StageName, StageCfg>> => ({
    checkout: { countries: [defaultCountry], timeout: 15, retry: 3 },
    init: { countries: [defaultCountry], timeout: 10, retry: 3 },
    update: { countries: [updateCountry], timeout: 10, retry: 3 },
    provider: { countries: [defaultCountry], timeout: 8, retry: 3 },
    approve: { countries: [defaultCountry], timeout: 6, retry: 3 },
    poll: { countries: [defaultCountry], timeout: 25, retry: 1, poll_interval: 0.75, max_polls: 40 },
    resolve: { countries: [defaultCountry], timeout: 20, retry: 2 },
  });

  return {
    name: branchName,
    label,
    channel: branchName,
    token_source: branchName,
    require_zero: true,
    channel_check: true,
    dual_init: false,
    init0_ccs: [defaultCountry],
    init1_ccs: [defaultCountry],
    init_t_ccs: [defaultCountry],
    follow_checkout: false,
    billing_country: defaultCountry,
    attempts: 8,
    stages: mkStages([defaultCountry]),
  };
}
