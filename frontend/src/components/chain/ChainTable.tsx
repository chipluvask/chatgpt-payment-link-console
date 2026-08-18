import { memo, useMemo, useState } from "react";
import { STAGE_ORDER, STAGE_SHORT, STAGE_CN, OAICS_STAGE_CN } from "../../types";
import type { ChainState, StageName, OaicsStageName } from "../../types";

/** OAICS 5 segments map to 7 segment column: section that does not go (init/poll) for undefined, skip directly */
const OAICS_COL_MAP: Record<StageName, OaicsStageName | undefined> = {
  checkout: "checkout",
  init: undefined,
  update: "taxes",
  provider: "provider",
  approve: "confirm",
  poll: undefined,
  resolve: "resolve",
};

const fmtDur = (sec: number) => {
  if (sec == null || isNaN(sec)) return "—";
  if (sec < 60) return sec.toFixed(1) + "s";
  const m = Math.floor(sec / 60), s = Math.floor(sec % 60);
  return `${m}m${s}s`;
};

interface Row {
  id: string;
  cs: ChainState;
}

interface Props {
  chainList: Row[];
  onClick?: (url: string, meta: string) => void;
}

function ChainTableInner({ chainList, onClick }: Props) {
  const [filter, setFilter] = useState<string>("all");

  const counts = useMemo(() => {
    let running = 0, success = 0, failed = 0;
    for (const { cs } of chainList) {
      if (cs.status === "running") running++;
      else if (cs.status === "success") success++;
      else if (cs.status === "failed") failed++;
    }
    return { running, success, failed };
  }, [chainList]);

  const shown = filter === "all"
    ? chainList
    : chainList.filter(({ cs }) => cs.status === filter);

  return (
    <div className="card">
      <div className="card-head">
        <span className="card-title">Link list（{chainList.length}）</span>
        <div style={{ display: "flex", gap: 4 }}>
          {(
            [
              ["all", `all ${chainList.length}`],
              ["running", `active ${counts.running}`],
              ["success", `success ${counts.success}`],
              ["failed", `fail ${counts.failed}`],
            ] as const
          ).map(([k, label]) => (
            <button
              key={k}
              className={`btn btn-sm ${filter === k ? "btn-primary" : "btn-ghost"}`}
              onClick={() => setFilter(k)}
            >
              {label}
            </button>
          ))}
        </div>
      </div>
      <div className="table-wrap" style={{ border: "none", borderRadius: 0 }}>
        <table className="table">
          <thead>
            <tr>
              <th style={{ width: 80 }}>link</th>
              <th>Email / Sub</th>
              {STAGE_ORDER.map((s) => (
                <th key={s} style={{ textAlign: "center", minWidth: 58 }} title={STAGE_CN[s]}>
                  <span style={{ color: "var(--text-2)" }}>{STAGE_SHORT[s]}</span>
                </th>
              ))}
              <th style={{ width: 64 }}>time consuming</th>
              <th style={{ width: 110 }}>state</th>
              {onClick && <th style={{ width: 64 }}>operate</th>}
            </tr>
          </thead>
          <tbody>
            {shown.map(({ id, cs }) => {
              const email = cs.email || cs.tokenSub || id;
              // The terminal state is solidified using the backend elapsed, Real-time timing only during operation
              const elapsed =
                cs.elapsed ??
                (cs.status === "running" && cs.startTime ? (Date.now() - cs.startTime) / 1000 : 0);
              const handleClick = () => {
                if (cs.status === "success" && cs.url && onClick) {
                  let meta = `chain: ${id}`;
                  if (cs.email) meta += ` · ${cs.email}`;
                  if (cs.country) meta += ` · ${cs.country}`;
                  onClick(cs.url, meta);
                }
              };
              return (
                <tr key={id} className={cs.status === "running" ? "row-selected" : ""}>
                  <td>
                    <span className="tag">#{id.slice(0, 8)}</span>
                    {cs.linkMode === "oaics" && (
                      <span className="tag" style={{ color: "var(--oaics, #3b82f6)", background: "rgba(59,130,246,.12)", border: "1px solid rgba(59,130,246,.35)", fontSize: 10, marginLeft: 4 }}>OAICS</span>
                    )}
                    {cs.channelDetect && (
                      <div className="cell-sub" style={{ marginTop: 2 }}>
                        <span
                          className={`badge ${cs.channelDetect.present ? "badge-success" : "badge-danger"}`}
                          title={`Channel detection: ${cs.channelDetect.channel} @ ${cs.channelDetect.country || ""} · types: ${(cs.channelDetect.methods || []).join(", ") || "none"}`}
                          style={{ fontSize: 10 }}
                        >
                          {cs.channelDetect.channel}
                          {cs.channelDetect.present ? " ✓" : " ✗"}
                        </span>
                      </div>
                    )}
                  </td>
                  <td>
                    <div className="cell-strong" style={{ fontSize: 12 }}>
                      {email}
                    </div>
                    <div className="cell-sub">
                      attempt {cs.attempt || 1}
                    </div>
                  </td>
                  {STAGE_ORDER.map((s) => {
                    const isOaics = cs.linkMode === "oaics";
                    let oaicsSrc: OaicsStageName | undefined;
                    if (isOaics) oaicsSrc = OAICS_COL_MAP[s];
                    const sd = isOaics
                      ? (oaicsSrc ? cs.stages[oaicsSrc] : undefined)
                      : cs.stages[s];
                    const title = isOaics && oaicsSrc
                      ? `${OAICS_STAGE_CN[oaicsSrc]} (OAICS)${sd?.country ? " · " + sd.country : ""}`
                      : `${STAGE_CN[s]}${sd?.country ? " · " + sd.country : ""}`;
                    let cls = "stage-cell chain-cell" + (isOaics ? " oaics" : "");
                    let label = "";
                    if (!oaicsSrc && isOaics) {
                      // oaics section that does not go: skip directly
                      label = "·";
                    } else if (sd?.state === "ok") {
                      cls += " ok";
                      label = sd.country || "✓";
                    } else if (sd?.state === "fail") {
                      cls += " fail";
                      label = "✗";
                    } else if (sd?.state === "run") {
                      cls += " run";
                      label = `try ${sd.tryN || 1}/${sd.maxTry || 3}`;
                    } else {
                      label = "·";
                    }
                    return (
                      <td key={s} style={{ textAlign: "center" }}>
                        <span className={cls} title={title}>
                          <span className="stage-dot" />
                          <span className="stage-try">{label}</span>
                        </span>
                      </td>
                    );
                  })}
                  <td>
                    <span className="muted" style={{ fontFamily: "var(--font-mono)", fontSize: 11 }}>
                      {fmtDur(elapsed)}
                    </span>
                  </td>
                  <td>
                    {cs.status === "success" ? (
                      <span className="badge badge-success">✓ success</span>
                    ) : cs.status === "failed" ? (
                      <span className="badge badge-danger" title={cs.reasonText || cs.reason || ""}>
                        ✗ {cs.reasonText || cs.reason || "fail"}
                      </span>
                    ) : cs.status === "running" ? (
                      <span className="badge badge-info">Running</span>
                    ) : (
                      <span className="badge badge-muted">{cs.status || "wait"}</span>
                    )}
                  </td>
                  {onClick && (
                    <td style={{ textAlign: "center" }}>
                      <button
                        className="btn btn-ghost btn-sm"
                        disabled={cs.status !== "success" || !cs.url}
                        onClick={handleClick}
                      >
                        BA
                      </button>
                    </td>
                  )}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export const ChainTable = memo(ChainTableInner);
