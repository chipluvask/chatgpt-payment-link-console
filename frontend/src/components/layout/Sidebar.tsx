import { useStore } from "../../store/useStore";
import type { ViewName } from "../../types";

const NAV_GROUPS: { label: string; items: { view: ViewName; icon: string; text: string }[] }[] = [
  {
    label: "monitor",
    items: [
      { view: "overview", icon: "grid", text: "Overview" },
      { view: "chains", icon: "chains", text: "Link monitoring" },
      { view: "logs", icon: "logs", text: "real time log" },
    ],
  },
  {
    label: "resource",
    items: [
      { view: "tokens", icon: "token", text: "Token Library" },
      { view: "proxy", icon: "proxy", text: "proxy pool" },
      { view: "inventory", icon: "inventory", text: "successful inventory" },
      { view: "register", icon: "register", text: "Account registration" },
    ],
  },
  {
    label: "Link configuration",
    items: [
      { view: "paypal_extract", icon: "paypal", text: "PayPal refining" },
      { view: "momo", icon: "momo", text: "MoMo lift chain" },
      { view: "grok", icon: "grok", text: "Grok link" },
      { view: "pix", icon: "pix", text: "PIX QR code" },
      { view: "ideal", icon: "ideal", text: "iDEAL lift chain" },
      { view: "upi", icon: "upi", text: "UPI lift chain" },
      { view: "kakao", icon: "kakao", text: "Kakao Pay" },
      { view: "blik", icon: "blik", text: "BLIK lift chain" },
      { view: "twint", icon: "twint", text: "TWINT lift chain" },
      { view: "bizum", icon: "bizum", text: "Bizum lift chain" },
      { view: "gopay", icon: "gopay", text: "GoPay lift chain" },
      { view: "naver_pay", icon: "naver_pay", text: "Naver Pay" },
      { view: "gcash", icon: "gcash", text: "GCash lift chain" },
      { view: "grabpay", icon: "grabpay", text: "GrabPay lift chain" },
      { view: "qris", icon: "qris", text: "QRIS lift chain" },
      { view: "direct", icon: "direct", text: "Straight card chain" },
    ],
  },
  {
    label: "Payment authorization",
    items: [
      { view: "paypal", icon: "paypal", text: "PayPal Authorize" },
      { view: "direct_pay", icon: "direct", text: "Direct card payment" },
    ],
  },
  {
    label: "analyze",
    items: [
      { view: "analytics", icon: "analytics", text: "Statistical analysis" },
      { view: "samples", icon: "samples", text: "sample record" },
    ],
  },
  {
    label: "system",
    items: [{ view: "settings", icon: "settings", text: "set up" }],
  },
];

const ICONS: Record<string, string> = {
  grid: `<rect x="1.5" y="1.5" width="5.5" height="5.5" rx="1.2" fill="none" stroke="currentColor" stroke-width="1.1"/><rect x="9" y="1.5" width="5.5" height="5.5" rx="1.2" fill="none" stroke="currentColor" stroke-width="1.1"/><rect x="1.5" y="9" width="5.5" height="5.5" rx="1.2" fill="none" stroke="currentColor" stroke-width="1.1"/><rect x="9" y="9" width="5.5" height="5.5" rx="1.2" fill="none" stroke="currentColor" stroke-width="1.1"/>`,
  chains: `<path d="M2 4h3l2 2 2-2h5M2 8h3l2 2 2-2h5M2 12h3l2 2 2-2h5" fill="none" stroke="currentColor" stroke-width="1.1" stroke-linecap="round" stroke-linejoin="round"/>`,
  logs: `<rect x="1.5" y="2" width="13" height="12" rx="1.6" fill="none" stroke="currentColor" stroke-width="1.1"/><line x1="4" y1="5.5" x2="12" y2="5.5" stroke="currentColor" stroke-width="1.1" stroke-linecap="round"/><line x1="4" y1="8" x2="10" y2="8" stroke="currentColor" stroke-width="1.1" stroke-linecap="round"/><line x1="4" y1="10.5" x2="8" y2="10.5" stroke="currentColor" stroke-width="1.1" stroke-linecap="round"/>`,
  token: `<circle cx="8" cy="5.5" r="2.6" fill="none" stroke="currentColor" stroke-width="1.1"/><path d="M2.5 13.6a5.5 5.5 0 0 1 11 0" fill="none" stroke="currentColor" stroke-width="1.1" stroke-linecap="round"/>`,
  proxy: `<circle cx="8" cy="8" r="6" fill="none" stroke="currentColor" stroke-width="1.1"/><path d="M2 8h12M8 2c2.2 2.2 2.2 9.8 0 12M8 2c-2.2 2.2-2.2 9.8 0 12" fill="none" stroke="currentColor" stroke-width="1.1"/>`,
  inventory: `<path d="M2 4l6-2.2L14 4v8L8 14.2 2 12V4z" fill="none" stroke="currentColor" stroke-width="1.1" stroke-linejoin="round"/><path d="M2 4l6 2.2L14 4M8 6.2V14" fill="none" stroke="currentColor" stroke-width="1.1" stroke-linejoin="round"/>`,
  register: `<circle cx="5.5" cy="5" r="2.2" fill="none" stroke="currentColor" stroke-width="1.1"/><path d="M2 12.5a3.5 3.5 0 0 1 7 0" fill="none" stroke="currentColor" stroke-width="1.1" stroke-linecap="round"/><path d="M11 4.5l2 2M13 2l-3.4 3.4 2 2L15 4l-2-2z" fill="none" stroke="currentColor" stroke-width="1.1" stroke-linejoin="round"/><line x1="11.4" y1="6.4" x2="13.4" y2="8.4" stroke="currentColor" stroke-width="1.1" stroke-linecap="round"/>`,
  momo: `<rect x="2" y="3" width="12" height="10" rx="2" fill="none" stroke="currentColor" stroke-width="1.1"/><circle cx="5.5" cy="8" r="1.2" fill="currentColor"/><circle cx="10.5" cy="8" r="1.2" fill="currentColor"/>`,
  grok: `<path d="M8 2L3 14h2.5L8 8l2.5 6H13L8 2z" fill="none" stroke="currentColor" stroke-width="1.1" stroke-linejoin="round"/>`,
  pix: `<rect x="2" y="2" width="5" height="5" rx="0.8" fill="none" stroke="currentColor" stroke-width="1.1"/><rect x="9" y="2" width="5" height="5" rx="0.8" fill="none" stroke="currentColor" stroke-width="1.1"/><rect x="2" y="9" width="5" height="5" rx="0.8" fill="none" stroke="currentColor" stroke-width="1.1"/><rect x="9.5" y="9.5" width="1.5" height="1.5" fill="currentColor"/><rect x="12" y="9.5" width="1.5" height="1.5" fill="currentColor"/><rect x="9.5" y="12" width="1.5" height="1.5" fill="currentColor"/>`,
  ideal: `<circle cx="8" cy="8" r="5.5" fill="none" stroke="currentColor" stroke-width="1.1"/><path d="M8 2.5v11M4 8h8" stroke="currentColor" stroke-width="1.1" stroke-linecap="round"/>`,
  upi: `<path d="M2.5 5h11M2.5 8h11M2.5 11h11" stroke="currentColor" stroke-width="1.1" stroke-linecap="round"/><path d="M4 5l-1.5 3L4 11" stroke="currentColor" stroke-width="1.1" stroke-linecap="round" stroke-linejoin="round"/>`,
  kakao: `<path d="M8 2.5c-3 0-5.5 2.2-5.5 5 0 1.9 1.3 3.5 3.2 4.4l-.8 2.6 2.9-1.7c.7.2 1.4.3 2.2.3 3 0 5.5-2.2 5.5-5s-2.5-5-5.5-5z" fill="none" stroke="currentColor" stroke-width="1.1" stroke-linejoin="round"/>`,
  blik: `<rect x="3" y="2.5" width="10" height="7" rx="1.4" fill="none" stroke="currentColor" stroke-width="1.1"/><path d="M5 9.5v3h6v-3" stroke="currentColor" stroke-width="1.1" stroke-linecap="round"/>`,
  twint: `<rect x="2" y="2" width="12" height="12" rx="2" fill="none" stroke="currentColor" stroke-width="1.1"/><path d="M5 11l2-4 2 2.5L11 5l1 6" fill="none" stroke="currentColor" stroke-width="1.1" stroke-linecap="round" stroke-linejoin="round"/>`,
  bizum: `<path d="M2 5.5h12l-1.6 7H3.6L2 5.5z" fill="none" stroke="currentColor" stroke-width="1.1" stroke-linejoin="round"/><path d="M5.5 4.5L8 2l2.5 2.5" fill="none" stroke="currentColor" stroke-width="1.1" stroke-linecap="round" stroke-linejoin="round"/><path d="M6.5 8h3" stroke="currentColor" stroke-width="1.1" stroke-linecap="round"/>`,
  gopay: `<path d="M2.5 10.5l3-6 2.5 4.5 2-3.5 3.5 5H2.5z" fill="none" stroke="currentColor" stroke-width="1.1" stroke-linejoin="round"/><circle cx="11.5" cy="3.5" r="1.4" fill="currentColor"/>`,
  naver_pay: `<path d="M2 4h12l-1 8H4L2 4z" fill="none" stroke="currentColor" stroke-width="1.1" stroke-linejoin="round"/><path d="M5.5 8.5V6M10.5 8.5V6M8 10.5v-1" stroke="currentColor" stroke-width="1.1" stroke-linecap="round"/>`,
  gcash: `<circle cx="6" cy="8" r="4.2" fill="none" stroke="currentColor" stroke-width="1.1"/><circle cx="10" cy="8" r="4.2" fill="none" stroke="currentColor" stroke-width="1.1"/><path d="M8 3.8v8.4" stroke="currentColor" stroke-width="1.1"/>`,
  grabpay: `<path d="M2 5.5h12l-1.2 7.5H3.2L2 5.5z" fill="none" stroke="currentColor" stroke-width="1.1" stroke-linejoin="round"/><path d="M5 5.5L6.5 2h3L11 5.5" fill="none" stroke="currentColor" stroke-width="1.1" stroke-linejoin="round"/>`,
  qris: `<rect x="2" y="2" width="4.5" height="4.5" rx="0.8" fill="none" stroke="currentColor" stroke-width="1.1"/><rect x="9.5" y="2" width="4.5" height="4.5" rx="0.8" fill="none" stroke="currentColor" stroke-width="1.1"/><rect x="2" y="9.5" width="4.5" height="4.5" rx="0.8" fill="none" stroke="currentColor" stroke-width="1.1"/><rect x="10" y="10" width="1.4" height="1.4" fill="currentColor"/><rect x="12.6" y="10" width="1.4" height="1.4" fill="currentColor"/><rect x="10" y="12.6" width="1.4" height="1.4" fill="currentColor"/><rect x="12.6" y="12.6" width="1.4" height="1.4" fill="currentColor"/>`,
  direct: `<path d="M2 3.5h12M2 8h12M2 12.5h12" stroke="currentColor" stroke-width="1.1" stroke-linecap="round"/><circle cx="6" cy="5.5" r="1.2" fill="currentColor"/><circle cx="10" cy="10" r="1.2" fill="currentColor"/>`,
  paypal: `<path d="M4 2h6.5c2 0 3.5 1.3 3.5 3.3 0 2.3-1.8 3.7-4.2 3.7H8.2L7.5 14H5l1.5-9.5H4V2z" fill="none" stroke="currentColor" stroke-width="1.1" stroke-linejoin="round"/><path d="M3.5 3.5H2" stroke="currentColor" stroke-width="1.1" stroke-linecap="round"/>`,
  analytics: `<path d="M2 13V3M2 13h12" fill="none" stroke="currentColor" stroke-width="1.1" stroke-linecap="round"/><rect x="4" y="9" width="2.5" height="4" fill="currentColor" opacity="0.6"/><rect x="7.5" y="6" width="2.5" height="7" fill="currentColor" opacity="0.6"/><rect x="11" y="8" width="2.5" height="5" fill="currentColor" opacity="0.6"/>`,
  samples: `<path d="M3 2h7l3 3v9H3V2z" fill="none" stroke="currentColor" stroke-width="1.1" stroke-linejoin="round"/><path d="M10 2v3h3" fill="none" stroke="currentColor" stroke-width="1.1" stroke-linejoin="round"/><line x1="5" y1="8" x2="11" y2="8" stroke="currentColor" stroke-width="1.1" stroke-linecap="round"/><line x1="5" y1="10.5" x2="9" y2="10.5" stroke="currentColor" stroke-width="1.1" stroke-linecap="round"/>`,
  settings: `<circle cx="8" cy="8" r="2.2" fill="none" stroke="currentColor" stroke-width="1.1"/><path d="M8 1v2M8 13v2M1 8h2M13 8h2M3 3l1.5 1.5M11.5 11.5L13 13M3 13l1.5-1.5M11.5 4.5L13 3" fill="none" stroke="currentColor" stroke-width="1.1" stroke-linecap="round"/>`,
};

export function Sidebar() {
  const currentView = useStore((s) => s.currentView);
  const setView = useStore((s) => s.setView);
  const tokens = useStore((s) => s.tokens);
  const nodes = useStore((s) => s.nodes);
  const chainStates = useStore((s) => s.chainStates);
  const stats = useStore((s) => s.stats);

  const activeChains = Object.values(chainStates).filter((c) => c.status === "running").length;
  const totalSuccess = stats.success || 0;
  const totalFail = stats.failure || 0;
  const total = totalSuccess + totalFail;
  const rate = total > 0 ? ((totalSuccess / total) * 100).toFixed(0) : "—";

  // Count pending authorizations from successful links BA quantity
  const pendingBa = Object.values(chainStates).filter(
    (c) => c.status === "success" && c.url && c.url.includes("ba_token=BA-")
  ).length;

  const counts: Partial<Record<ViewName, { text: string; cls?: string }>> = {
    chains: { text: String(activeChains || ""), cls: activeChains > 0 ? "nav-count-live" : "" },
    tokens: { text: String(tokens.length || "") },
    proxy: { text: String(nodes.length || "") },
    inventory: { text: String(totalSuccess), cls: "nav-count-gold" },
    paypal: { text: String(pendingBa || ""), cls: pendingBa > 0 ? "nav-count-live" : "" },
    paypal_extract: { text: String(activeChains || ""), cls: activeChains > 0 ? "nav-count-live" : "" },
  };

  return (
    <nav className="sidebar">
      <div className="sidebar-brand">
        <span className="brand-mark" />
        <span className="brand-text">console</span>
      </div>
      {NAV_GROUPS.map((group) => (
        <div key={group.label} className="sidebar-group">
          <p className="sidebar-label">{group.label}</p>
          {group.items.map((item) => (
            <a
              key={item.view}
              className={`nav-item ${currentView === item.view ? "active" : ""}`}
              onClick={() => setView(item.view)}
            >
              <svg viewBox="0 0 16 16" className="nav-icon" dangerouslySetInnerHTML={{ __html: ICONS[item.icon] || "" }} />
              <span className="nav-text">{item.text}</span>
              {counts[item.view]?.text && (
                <span className={`nav-count ${counts[item.view]?.cls || ""}`}>
                  {counts[item.view]?.text}
                </span>
              )}
            </a>
          ))}
        </div>
      ))}
      <div className="sidebar-footer">
        <div className="sidebar-stat">
          <span className="ss-label">Successful accumulation</span>
          <span className="ss-value">{totalSuccess}</span>
        </div>
        <div className="sidebar-stat">
          <span className="ss-label">success rate</span>
          <span className="ss-value">{rate}%</span>
        </div>
      </div>
    </nav>
  );
}
