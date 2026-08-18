import { useWebSocket } from "./hooks/useWebSocket";
import { useStore } from "./store/useStore";
import { TitleBar } from "./components/layout/TitleBar";
import { Sidebar } from "./components/layout/Sidebar";
import { OverviewView } from "./views/OverviewView";
import { ChainsView } from "./views/ChainsView";
import { LogsView } from "./views/LogsView";
import { TokensView } from "./views/TokensView";
import { ProxyView } from "./views/ProxyView";
import { InventoryView } from "./views/InventoryView";
import { MomoView } from "./views/MomoView";
import { GrokView } from "./views/GrokView";
import { PixView } from "./views/PixView";
import { BranchConfigView } from "./views/BranchConfigView";
import { DirectView } from "./views/DirectView";
import { PayPalView } from "./views/PayPalView";
import { DirectPayView } from "./views/DirectPayView";
import { PayPalExtractView } from "./views/PayPalExtractView";
import { AnalyticsView } from "./views/AnalyticsView";
import { SamplesView } from "./views/SamplesView";
import { SettingsView } from "./views/SettingsView";
import { RegisterView } from "./views/RegisterView";

export default function App() {
  useWebSocket();
  const view = useStore((s) => s.currentView);

  return (
    <div className="window">
      <TitleBar />
      <div className="body">
        <Sidebar />
        <main className="content">
          {view === "overview" && <OverviewView />}
          {view === "chains" && <ChainsView />}
          {view === "logs" && <LogsView />}
          {view === "tokens" && <TokensView />}
          {view === "proxy" && <ProxyView />}
          {view === "inventory" && <InventoryView />}
          {view === "momo" && <MomoView />}
          {view === "grok" && <GrokView />}
          {view === "pix" && <PixView />}
          {view === "ideal" && (
            <BranchConfigView branchName="ideal" title="iDEAL lift chain" sub="Seven-segment export configuration (iDEAL channel) · NL bill EUR" defaultCountry="NL" updateCountry="VN" />
          )}
          {view === "upi" && (
            <BranchConfigView branchName="upi" title="UPI lift chain" sub="Seven-segment export configuration (UPI channel) · IN bill INR" defaultCountry="IN" updateCountry="VN" />
          )}
          {view === "kakao" && (
            <BranchConfigView branchName="kakao" title="Kakao Pay lift chain" sub="Seven-segment export configuration (Kakao channel) · KR bill KRW" defaultCountry="KR" updateCountry="VN" />
          )}
          {view === "blik" && (
            <BranchConfigView branchName="blik" title="BLIK lift chain" sub="Seven-segment export configuration (BLIK channel) · PL bill PLN" defaultCountry="PL" updateCountry="PL" />
          )}
          {view === "twint" && (
            <BranchConfigView branchName="twint" title="TWINT lift chain" sub="Seven-segment export configuration (TWINT channel) · CH bill CHF" defaultCountry="CH" updateCountry="VN" />
          )}
          {view === "bizum" && (
            <BranchConfigView branchName="bizum" title="Bizum lift chain" sub="Seven-segment export configuration (Bizum channel) · ES bill EUR · Mobile phone authorization chain" defaultCountry="ES" updateCountry="VN" />
          )}
          {view === "gopay" && (
            <BranchConfigView branchName="gopay" title="GoPay lift chain" sub="Seven-segment export configuration (GoPay channel) · ID bill IDR · Midtrans landing" defaultCountry="ID" updateCountry="VN" />
          )}
          {view === "naver_pay" && (
            <BranchConfigView branchName="naver_pay" title="Naver Pay lift chain" sub="Seven-segment export configuration (Naver Pay channel) · KR bill KRW · NicePay landing" defaultCountry="KR" updateCountry="VN" />
          )}
          {view === "gcash" && (
            <BranchConfigView branchName="gcash" title="GCash lift chain" sub="Seven-segment export configuration (GCash channel) · PH bill PHP · Adyen landing" defaultCountry="PH" updateCountry="VN" />
          )}
          {view === "grabpay" && (
            <BranchConfigView branchName="grabpay" title="GrabPay lift chain" sub="Seven-segment export configuration (GrabPay channel) · PH bill PHP · Grab landing" defaultCountry="PH" updateCountry="VN" />
          )}
          {view === "qris" && (
            <BranchConfigView branchName="qris" title="QRIS lift chain" sub="Seven-segment export configuration (QRIS channel) · ID bill IDR · Midtrans Charge" defaultCountry="ID" updateCountry="VN" />
          )}
          {view === "direct" && <DirectView />}
          {view === "paypal" && <PayPalView />}
          {view === "direct_pay" && <DirectPayView />}
          {view === "register" && <RegisterView />}
          {view === "paypal_extract" && <PayPalExtractView />}
          {view === "analytics" && <AnalyticsView />}
          {view === "samples" && <SamplesView />}
          {view === "settings" && <SettingsView />}
        </main>
      </div>
    </div>
  );
}
