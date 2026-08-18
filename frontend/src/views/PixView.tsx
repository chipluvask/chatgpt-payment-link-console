import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "../api/client";
import type { StageName, StageCfg, BranchCfg } from "../types";
import { StageSettingsPanel } from "../components/chain/StageSettings";

/* ==========================================================================
   PIX QR code — Configuration module (pix Branch seven-segment configuration) + QR code preview tool
   Lift chain starts at Token Library (branch: PIX QR code) · output in success inventory
   ========================================================================== */

const QR_SIZE = 25;
const CELL_PX = 7;

function hashSeed(str: string): number {
  let h = 0x811c9dc5;
  for (let i = 0; i < str.length; i++) {
    h ^= str.charCodeAt(i);
    h = Math.imul(h, 0x01000193);
  }
  return h >>> 0;
}

function generateQrMatrix(payload: string, size = QR_SIZE): boolean[][] {
  let state = hashSeed(payload) || 1;
  const rand = () => {
    state = (Math.imul(state, 1664525) + 1013904223) >>> 0;
    return state / 0x100000000;
  };

  const matrix: boolean[][] = Array.from({ length: size }, () =>
    Array.from({ length: size }, () => rand() > 0.52)
  );

  const drawFinder = (r0: number, c0: number) => {
    for (let r = 0; r < 7; r++) {
      for (let c = 0; c < 7; c++) {
        const onBorder = r === 0 || r === 6 || c === 0 || c === 6;
        const inCenter = r >= 2 && r <= 4 && c >= 2 && c <= 4;
        matrix[r0 + r][c0 + c] = onBorder || inCenter;
      }
    }
    for (let r = -1; r <= 7; r++) {
      for (let c = -1; c <= 7; c++) {
        const rr = r0 + r;
        const cc = c0 + c;
        if (rr < 0 || rr >= size || cc < 0 || cc >= size) continue;
        if (r === -1 || r === 7 || c === -1 || c === 7) matrix[rr][cc] = false;
      }
    }
  };

  drawFinder(0, 0);
  drawFinder(0, size - 7);
  drawFinder(size - 7, 0);

  return matrix;
}

export function PixView() {
  const [branch, setBranch] = useState<BranchCfg | null>(null);
  const [countryOptions, setCountryOptions] = useState<{ code: string; capital?: string }[]>([]);
  const [savingStage, setSavingStage] = useState<string>("");
  const [savingFlags, setSavingFlags] = useState(false);
  const [result, setResult] = useState("");

  /* ── QR code preview tool ── */
  const [payload, setPayload] = useState("");
  const matrix = useMemo(
    () => (payload ? generateQrMatrix(payload) : null),
    [payload]
  );

  const loadBranch = useCallback(async () => {
    try {
      const data = await api("/api/config");
      if (data && data.ok && data.chain?.branches?.pix) {
        setBranch(data.chain.branches.pix);
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
      await api("/api/config/branch", "POST", { branch: "pix", stages: { [stage]: patch } });
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
      await api("/api/config/branch", "POST", { branch: "pix", ...patch });
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
          <h2 className="page-title">PIX QR code</h2>
          <p className="page-sub">
            Seven-segment export configuration (link channel) + QR code preview tool — Lift chain starts at Token Library
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
          branchName="pix"
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

      <div className="card" style={{ marginTop: 14 }}>
        <div className="card-head">
          <span className="card-title">QR code preview tool</span>
          <span className="card-hint">Paste payload Live preview (PIX BR Code)</span>
        </div>
        <div className="grid grid-2">
          <div style={{ padding: 16 }}>
            <textarea
              className="textarea"
              rows={8}
              value={payload}
              onChange={(e) => setPayload(e.target.value)}
              placeholder="Paste PIX payload Preview QR code…"
            />
          </div>
          <div style={{ padding: 16 }}>
            {!matrix ? (
              <div className="empty" style={{ padding: 28 }}>
                <div className="empty-icon">▦</div>
                <div className="empty-title">waiting for input…</div>
              </div>
            ) : (
              <div className="qr-frame">
                <div
                  style={{
                    display: "grid",
                    gridTemplateColumns: `repeat(${QR_SIZE}, ${CELL_PX}px)`,
                    gridTemplateRows: `repeat(${QR_SIZE}, ${CELL_PX}px)`,
                    width: QR_SIZE * CELL_PX,
                    height: QR_SIZE * CELL_PX,
                  }}
                >
                  {matrix.flatMap((row, r) =>
                    row.map((on, c) => (
                      <div
                        key={`${r}-${c}`}
                        style={{
                          width: CELL_PX,
                          height: CELL_PX,
                          backgroundColor: on ? "#000000" : "#ffffff",
                        }}
                      />
                    ))
                  )}
                </div>
              </div>
            )}
          </div>
        </div>
      </div>

      <div className="note" style={{ marginTop: 14 }}>
        This page is responsible for <b>PIX Link egress configuration</b> and <b>payload Preview</b>：choose Token and submit the link to{" "}
        <b>Token Library</b>（chain branch selection「PIX QR code」）；Check link progress<b>Link monitoring</b>；Look at the output
        <b>successful inventory</b>。
      </div>
    </div>
  );
}

function makeMockBranch(): BranchCfg {
  const mkStages = (cc: string[]): Partial<Record<StageName, StageCfg>> => ({
    checkout: { countries: ["auto"], timeout: 15, retry: 3 },
    init: { countries: ["auto"], timeout: 10, retry: 3 },
    update: { countries: ["BR"], timeout: 10, retry: 3 },
    provider: { countries: ["auto"], timeout: 8, retry: 3 },
    approve: { countries: ["auto"], timeout: 6, retry: 3 },
    poll: { countries: ["auto"], timeout: 25, retry: 1, poll_interval: 0.75, max_polls: 40 },
    resolve: { countries: ["auto"], timeout: 20, retry: 2 },
  });

  return {
    name: "pix",
    label: "PIX QR code",
    channel: "pix",
    token_source: "pix",
    require_zero: true,
    channel_check: true,
    dual_init: false,
    init0_ccs: ["BR"],
    init1_ccs: ["BR"],
    init_t_ccs: ["BR"],
    follow_checkout: true,
    billing_country: "BR",
    attempts: 8,
    stages: mkStages(["BR"]),
  };
}
