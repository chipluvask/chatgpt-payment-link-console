import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";

/* ==========================================================================
   Direct card payment — Bind card + Tax-free address + subscription
   process: lift chain(HTTP) → CDP Bind card → Re-upload the chain → Tax-free address → subscription
   ========================================================================== */

interface CardRecord {
  id: number;
  number: string;
  exp_month: string;
  exp_year: string;
  name: string;
  brand: string;
  uses: number;
  max_uses: number;
  note: string;
}

interface DpRecord {
  id: string;
  status: string;
  step: string;
  card_last4: string;
  taxfree_state: string;
  short_link: string;
  error: string;
}

const TAXFREE_OPTIONS = [
  { code: "DE", note: "First choice · no state/local sales tax" },
  { code: "NH", note: "recommend · Digital goods are tax-free" },
  { code: "MT", note: "recommend · Digital goods are tax-free" },
  { code: "OR", note: "recommend · Digital goods are tax-free" },
  { code: "AK", note: "Some local taxes 7.5%" },
];

export function DirectPayView() {
  const [tokenId, setTokenId] = useState("");
  const [cards, setCards] = useState<CardRecord[]>([]);
  const [records, setRecords] = useState<DpRecord[]>([]);
  const [taxfreeState, setTaxfreeState] = useState("DE");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState("");
  const [addr, setAddr] = useState<Record<string, string> | null>(null);
  const [pollId, setPollId] = useState("");

  /* New card form */
  const [newCard, setNewCard] = useState({ number: "", exp_month: "", exp_year: "", cvc: "", name: "" });

  const loadCards = useCallback(async () => {
    try {
      const d = await api("/api/directpay/cards");
      if (d && d.ok) setCards(d.cards || []);
    } catch { /* silence */ }
  }, []);

  const loadRecords = useCallback(async () => {
    try {
      const d = await api("/api/directpay/records");
      if (d && d.ok) setRecords(d.records || []);
    } catch { /* silence */ }
  }, []);

  useEffect(() => {
    loadCards();
    loadRecords();
  }, [loadCards, loadRecords]);

  /* polling subscribe result */
  useEffect(() => {
    if (!pollId) return;
    const timer = setInterval(async () => {
      const d = await api("/api/directpay/records");
      if (d && d.ok) {
        setRecords(d.records || []);
        const rec = (d.records || []).find((r: DpRecord) => r.id === pollId);
        if (rec && rec.status !== "running") {
          setPollId("");
          clearInterval(timer);
          setResult(
            rec.status === "success"
              ? `✅ Finish — short chain: ${rec.short_link}`
              : `❌ fail (${rec.step}): ${rec.error}`
          );
        }
      }
    }, 3000);
    return () => clearInterval(timer);
  }, [pollId]);

  const handleSubscribe = async () => {
    setLoading(true);
    setResult("");
    try {
      const d = await api("/api/directpay/subscribe", "POST", {
        token_id: tokenId || undefined,
        taxfree_state: taxfreeState,
        rebind_recheckout: true,
      });
      if (d && d.ok && d.record) {
        setPollId(d.record.id);
        setResult(`Task started: ${d.record.id}`);
      } else {
        setResult(`Startup failed: ${(d as any)?.error || "unknown"}`);
      }
    } catch {
      setResult("Startup failed (Backend is unavailable)");
    } finally {
      setLoading(false);
    }
  };

  const handleAddCard = async () => {
    if (!newCard.number) return;
    setLoading(true);
    try {
      const d = await api("/api/directpay/cards", "POST", { ...newCard, max_uses: 10 });
      if (d && d.ok) {
        setNewCard({ number: "", exp_month: "", exp_year: "", cvc: "", name: "" });
        loadCards();
      }
    } catch { /* silence */ }
    finally { setLoading(false); }
  };

  const handleGenAddr = async (state: string) => {
    const d = await api(`/api/directpay/taxfree?state=${state}`);
    if (d && d.ok) setAddr(d.address);
  };

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h2 className="page-title">Direct card payment</h2>
          <p className="page-sub">
            lift chain → CDP Bind card → Re-upload the chain → U.S. tax-free address → subscription
          </p>
        </div>
      </div>

      <div className="grid grid-main">
        {/* Left: Subscription process */}
        <div className="card">
          <div className="card-head">
            <span className="card-title">Subscription process</span>
            <span className="card-hint">Lift the chain segment at Token Library completed · For card binding CDP Browser</span>
          </div>
          <div className="card-body">
            <div className="setting-row">
              <span className="setting-label">Token ID</span>
              <div className="setting-control">
                <input
                  className="input"
                  value={tokenId}
                  onChange={(e) => setTokenId(e.target.value)}
                  placeholder="Leave blank and use the first one token"
                />
              </div>
            </div>
            <div className="setting-row">
              <span className="setting-label">tax free state</span>
              <div className="setting-control">
                <select
                  className="select"
                  value={taxfreeState}
                  onChange={(e) => setTaxfreeState(e.target.value)}
                >
                  {TAXFREE_OPTIONS.map((o) => (
                    <option key={o.code} value={o.code}>{o.code} · {o.note}</option>
                  ))}
                </select>
                <button className="btn btn-sm" onClick={() => handleGenAddr(taxfreeState)}>
                  Generate address
                </button>
              </div>
            </div>
            {addr && (
              <div className="note" style={{ marginTop: 8 }}>
                Tax-free address: {addr.street}, {addr.city}, {addr.state} {addr.zip}
              </div>
            )}
            <button className="btn btn-primary" onClick={handleSubscribe} disabled={loading}>
              {loading ? "Processing…" : "Start subscribing (lift chain+Bind card+duty free)"}
            </button>
            {result && <div className="note" style={{ marginTop: 8 }}>{result}</div>}
          </div>

          <div className="card-head" style={{ borderTop: "1px solid var(--border-faint)", marginTop: 8 }}>
            <span className="card-title">Task record</span>
          </div>
          <div className="table-wrap" style={{ border: "none", borderRadius: 0 }}>
            <table className="table">
              <thead>
                <tr>
                  <th>ID</th><th>state</th><th>step</th><th>Card tail number</th><th>tax free state</th><th>short chain</th>
                </tr>
              </thead>
              <tbody>
                {records.slice(-8).reverse().map((r) => (
                  <tr key={r.id}>
                    <td><code className="mono">{r.id.slice(0, 12)}</code></td>
                    <td>
                      <span className={`badge ${r.status === "success" ? "badge-success" : r.status === "failed" ? "badge-danger" : "badge-info"}`}>
                        {r.status}
                      </span>
                    </td>
                    <td>{r.step}</td>
                    <td>{r.card_last4 || "—"}</td>
                    <td>{r.taxfree_state}</td>
                    <td>
                      {r.short_link ? (
                        <a href={r.short_link} target="_blank" rel="noreferrer" style={{ fontSize: 11 }}>
                          {r.short_link.slice(0, 40)}…
                        </a>
                      ) : r.error ? <span style={{ color: "var(--danger)", fontSize: 11 }}>{r.error.slice(0, 40)}</span> : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* right: card library */}
        <div className="card">
          <div className="card-head">
            <span className="card-title">card library</span>
            <span className="card-hint">Card information used to bind the card · automatic polling</span>
          </div>
          <div className="card-body">
            <div className="grid grid-2">
              <input className="input" placeholder="card number" value={newCard.number} onChange={(e) => setNewCard({ ...newCard, number: e.target.value })} />
              <input className="input" placeholder="moon (MM)" value={newCard.exp_month} onChange={(e) => setNewCard({ ...newCard, exp_month: e.target.value })} />
              <input className="input" placeholder="Year (YY)" value={newCard.exp_year} onChange={(e) => setNewCard({ ...newCard, exp_year: e.target.value })} />
              <input className="input" placeholder="CVV" value={newCard.cvc} onChange={(e) => setNewCard({ ...newCard, cvc: e.target.value })} />
              <input className="input" placeholder="cardholder" value={newCard.name} onChange={(e) => setNewCard({ ...newCard, name: e.target.value })} />
              <button className="btn btn-primary" onClick={handleAddCard} disabled={loading}>add card</button>
            </div>
          </div>
          <div className="table-wrap" style={{ border: "none", borderRadius: 0, borderTop: "1px solid var(--border-faint)" }}>
            <table className="table">
              <thead>
                <tr><th>card number</th><th>Validity period</th><th>cardholder</th><th>Dosage</th></tr>
              </thead>
              <tbody>
                {cards.map((c) => (
                  <tr key={c.id}>
                    <td><code className="mono">{c.number}</code></td>
                    <td>{c.exp_month}/{c.exp_year}</td>
                    <td>{c.name || "—"}</td>
                    <td>{c.uses}/{c.max_uses}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}
