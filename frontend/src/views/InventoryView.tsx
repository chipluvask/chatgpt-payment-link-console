import { useCallback, useEffect, useMemo, useState } from "react";
import { useStore } from "../store/useStore";
import { api } from "../api/client";
import { BRANCH_CN } from "../types";
import type { InventoryRecord, BranchName } from "../types";

const PAGE_SIZES = [50, 100, 200];

/** branch -> Output channels (with backend config branch.channel correspond) */
const BRANCH_CHANNEL: Record<string, string> = {
  paypal: "paypal",
  momo: "momo",
  grok: "card",
  pix: "pix",
  ideal: "ideal",
  upi: "upi",
  kakao: "kakao",
  blik: "blik",
  twint: "twint",
  direct: "card",
};

function normalize(sample: Record<string, unknown>): InventoryRecord {
  return {
    ba_id:
      (sample.ba_id as string) ||
      (sample.ba_token as string) ||
      (sample.id as string) ||
      (sample.chain_id as string) ||
      "",
    email: (sample.email as string) || "",
    country: (sample.country as string) || "",
    paypal_url:
      (sample.paypal_url as string) ||
      (sample.paypal_approve_url as string) ||
      (sample.url as string) ||
      "",
    amount:
      (sample.amount as string | number) ??
      (sample.amount_due as string | number) ??
      "",
    currency: (sample.currency as string) || "",
    time: fmtTime((sample.time as string) || (sample.ts as string) || ""),
    channel: (sample.channel as string) || "",
  };
}

function fmtTime(s: string): string {
  if (!s) return "";
  const d = new Date(s);
  if (isNaN(d.getTime())) return s;
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`;
}

function truncate(s: string, n: number): string {
  if (!s) return "-";
  return s.length > n ? s.slice(0, n) + "…" : s;
}

function flag(cc: string): string {
  if (!cc || cc.length !== 2) return "";
  const a = cc.charCodeAt(0), b = cc.charCodeAt(1);
  if (a < 65 || a > 90 || b < 65 || b > 90) return "";
  return (
    String.fromCodePoint(0x1f1e6 + (a - 65)) +
    String.fromCodePoint(0x1f1e6 + (b - 65))
  );
}

export function InventoryView() {
  const activeBranch = useStore((s) => s.activeBranch);
  const setActiveBranch = useStore((s) => s.setActiveBranch);
  const pushLog = useStore((s) => s.pushLog);

  const [inventory, setInventory] = useState<InventoryRecord[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [search, setSearch] = useState("");
  const [country, setCountry] = useState("all");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(50);
  const [loading, setLoading] = useState(false);
  const [clearing, setClearing] = useState(false);

  const branchChannel = BRANCH_CHANNEL[activeBranch] || "paypal";

  const fetchInventory = useCallback(
    async (channel: string) => {
      setLoading(true);
      try {
        const r = await api(`/api/tokens/inventory?channel=${encodeURIComponent(channel)}&limit=1000`);
        const recs = Array.isArray(r?.records) ? r.records.map((s: Record<string, unknown>) => normalize(s)) : [];
        setInventory(recs);
        setLoaded(true);
      } catch {
        setInventory([]);
        setLoaded(true);
      } finally {
        setLoading(false);
      }
    },
    []
  );

  useEffect(() => {
    setLoaded(false);
    setPage(1);
    setCountry("all");
    fetchInventory(branchChannel);
  }, [branchChannel, fetchInventory]);

  const countries = useMemo(() => {
    const set = new Set<string>();
    inventory.forEach((r) => {
      if (r.country) set.add(r.country);
    });
    return Array.from(set).sort();
  }, [inventory]);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return inventory.filter((r) => {
      if (country !== "all" && r.country !== country) return false;
      if (!q) return true;
      return (
        (r.ba_id || "").toLowerCase().includes(q) ||
        (r.email || "").toLowerCase().includes(q) ||
        (r.country || "").toLowerCase().includes(q)
      );
    });
  }, [inventory, search, country]);

  const shown = filtered.slice(0, 1000);
  const totalPages = Math.max(1, Math.ceil(shown.length / pageSize));
  const currentPage = Math.min(page, totalPages);
  const pageStart = (currentPage - 1) * pageSize;
  const pageItems = shown.slice(pageStart, pageStart + pageSize);

  const pageNumbers = useMemo(() => {
    const arr: number[] = [];
    let start = Math.max(1, currentPage - 3);
    const end = Math.min(totalPages, currentPage + 3);
    if (end - start < 6) start = Math.max(1, end - 6);
    for (let i = start; i <= end; i++) arr.push(i);
    return arr;
  }, [currentPage, totalPages]);

  const handleClearChannel = async () => {
    if (!window.confirm(`Confirm clearing「${BRANCH_CN[activeBranch]}」channel (${branchChannel}) successful inventory ${inventory.length} strip?`)) return;
    setClearing(true);
    try {
      const r = await api("/api/tokens/inventory/clear", "POST", { channel: branchChannel });
      pushLog(`Cleared ${branchChannel} Channel Success Inventory ${r?.deleted ?? 0} strip`, "ok");
      setInventory([]);
      setPage(1);
    } catch (e) {
      pushLog(`Clearing failed: ${e}`, "err");
    } finally {
      setClearing(false);
    }
  };

  const handleClearAll = async () => {
    if (!window.confirm(`Confirm the successful inventory clearing of all channels (Current total ${inventory.length} strip)? This action is irreversible!`)) return;
    setClearing(true);
    try {
      const r = await api("/api/tokens/inventory/clear", "POST", { channel: "" });
      pushLog(`All inventories have been cleared successfully ${r?.deleted ?? 0} strip`, "ok");
      setInventory([]);
      setPage(1);
    } catch (e) {
      pushLog(`Clearing failed: ${e}`, "err");
    } finally {
      setClearing(false);
    }
  };

  const handleExport = () => {
    const headers = [
      "ba_id",
      "email",
      "country",
      "paypal_url",
      "amount",
      "currency",
      "time",
    ];
    const escape = (v: unknown) =>
      `"${String(v ?? "").replace(/"/g, '""')}"`;
    const rows = shown.map((r) =>
      [r.ba_id, r.email, r.country, r.paypal_url, r.amount, r.currency, r.time]
        .map(escape)
        .join(",")
    );
    const csv = "\uFEFF" + headers.join(",") + "\n" + rows.join("\n");
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `inventory_${branchChannel}_${Date.now()}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h2 className="page-title">successful bill (BA) Library</h2>
          <p className="page-sub">
            lifting chain branch: {BRANCH_CN[activeBranch]} · channel {branchChannel} · common {inventory.length} strip
          </p>
        </div>
        <div className="page-actions">
          <select
            className="select"
            style={{ width: 150 }}
            value={activeBranch}
            onChange={(e) => {
              setActiveBranch(e.target.value as BranchName);
              setPage(1);
            }}
          >
            {(Object.keys(BRANCH_CN) as BranchName[]).map((b) => (
              <option key={b} value={b}>
                {BRANCH_CN[b]} ({BRANCH_CHANNEL[b]})
              </option>
            ))}
          </select>
          <input
            className="input"
            style={{ width: 200 }}
            placeholder="search ba_id / email / country"
            value={search}
            onChange={(e) => {
              setSearch(e.target.value);
              setPage(1);
            }}
          />
          <select
            className="select"
            style={{ width: 120 }}
            value={country}
            onChange={(e) => {
              setCountry(e.target.value);
              setPage(1);
            }}
          >
            <option value="all">All countries</option>
            {countries.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
          <button
            className="btn"
            onClick={() => fetchInventory(branchChannel)}
            disabled={loading}
            style={{ minWidth: 62 }}
          >
            {loading ? "loading…" : "refresh"}
          </button>
          <button
            className="btn btn-danger"
            onClick={handleClearChannel}
            disabled={clearing || inventory.length === 0}
          >
            Clear current channel
          </button>
          <button
            className="btn btn-danger"
            onClick={handleClearAll}
            disabled={clearing}
          >
            Clear all
          </button>
          <button
            className="btn btn-primary"
            onClick={handleExport}
            disabled={shown.length === 0}
          >
            Export CSV
          </button>
        </div>
      </div>

      <div className="table-wrap">
        <table className="table">
          <thead>
            <tr>
              <th>BA ID</th>
              <th>Email</th>
              <th>nation</th>
              <th>PayPal URL</th>
              <th className="num">Amount</th>
              <th>Currency</th>
              <th>time</th>
            </tr>
          </thead>
          <tbody>
            {loading && !loaded && (
              <tr>
                <td colSpan={7} className="muted" style={{ textAlign: "center" }}>
                  loading...
                </td>
              </tr>
            )}
            {!loading && loaded && pageItems.length === 0 && (
              <tr>
                <td colSpan={7} className="muted" style={{ textAlign: "center" }}>
                  No data yet — After the channel successfully pulls the link, it will be automatically stored in the warehouse.
                </td>
              </tr>
            )}
            {pageItems.map((r, i) => (
              <tr key={`${r.ba_id}-${i}`}>
                <td className="mono cell-strong">{r.ba_id || "-"}</td>
                <td title={r.email}>{truncate(r.email, 24)}</td>
                <td>{flag(r.country)} {r.country || "-"}</td>
                <td className="mono" style={{ maxWidth: 260 }} title={r.paypal_url}>
                  {truncate(r.paypal_url, 34)}
                </td>
                <td className="num">{r.amount === "" || r.amount == null ? "-" : r.amount}</td>
                <td>{r.currency || "-"}</td>
                <td className="mono">{r.time || "-"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="pagination">
        <div className="page-info">
          No. {currentPage} / {totalPages} Page · common {shown.length} strip
        </div>
        <div className="page-controls">
          <button
            className="page-btn"
            onClick={() => setPage(1)}
            disabled={currentPage <= 1}
          >
            front page
          </button>
          <button
            className="page-btn"
            onClick={() => setPage(currentPage - 1)}
            disabled={currentPage <= 1}
          >
            Previous page
          </button>
          {pageNumbers.map((n) => (
            <button
              key={n}
              className={`page-btn${n === currentPage ? " active" : ""}`}
              onClick={() => setPage(n)}
            >
              {n}
            </button>
          ))}
          <button
            className="page-btn"
            onClick={() => setPage(currentPage + 1)}
            disabled={currentPage >= totalPages}
          >
            Next page
          </button>
          <button
            className="page-btn"
            onClick={() => setPage(totalPages)}
            disabled={currentPage >= totalPages}
          >
            Last page
          </button>
        </div>
        <div className="page-size">
          per page
          <select
            className="select"
            style={{ width: 70 }}
            value={pageSize}
            onChange={(e) => {
              setPageSize(Number(e.target.value));
              setPage(1);
            }}
          >
            {PAGE_SIZES.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
          strip
        </div>
      </div>
    </div>
  );
}
