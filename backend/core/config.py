"""Configuration loader：read config.yaml，provide the big picture settings Singleton。

Support environment variables MIN_BACKEND_DIR position config.yaml；Fall back to the same directory as the module when missing。
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

try:
    from pydantic import BaseModel
except Exception:  # pragma: no cover - pydantic Downgrade to simple when unavailable dict
    BaseModel = object  # type: ignore[assignment]


class StageConfig(BaseModel):
    countries: list[str] = []
    timeout: int = 10
    retry: int = 3
    poll_interval: float = 0.75
    max_polls: int = 40


# lifting chain branch: paypal(refining) / momo / grok / pix / ideal / upi / kakao / blik / twint / direct(Direct card)
# 2026-08-08 LPM Actual measurement added: bizum(ES) / gopay(ID) / naver_pay(KR) (OpenAI Export full link verification passed)
# 2026-08-11 wallet_adapter Migration new: gcash(PH custom PM) / grabpay(PH) / qris(ID midtrans charge)
BRANCH_NAMES: list[str] = ["paypal", "momo", "grok", "pix", "ideal", "upi", "kakao", "blik", "twint", "direct",
                           "bizum", "gopay", "naver_pay", "gcash", "grabpay", "qris"]

BRANCH_LABELS: dict[str, str] = {
    "paypal": "PayPal refining",
    "momo": "MoMo lift chain",
    "grok": "Grok link",
    "pix": "PIX QR code",
    "ideal": "iDEAL lift chain",
    "upi": "UPI lift chain",
    "kakao": "Kakao Pay lift chain",
    "blik": "BLIK lift chain",
    "twint": "TWINT lift chain",
    "direct": "Straight card chain",
    "bizum": "Bizum lift chain",
    "gopay": "GoPay lift chain",
    "naver_pay": "Naver Pay lift chain",
    "gcash": "GCash lift chain",
    "grabpay": "GrabPay lift chain",
    "qris": "QRIS lift chain",
}

# oaics custom Checkout pure HTTP fifth section (checkout(custom+promo) -> taxes(bill+0Yuan)
# -> provider(elements+ctoken) -> confirm(chatgpt confirm) -> resolve)
OAICS_STAGE_NAMES: list[str] = ["checkout", "taxes", "provider", "confirm", "resolve"]


class BranchConfig(BaseModel):
    label: str = ""
    channel: str = "paypal"          # Payment channel verification target: paypal / momo / card / link
    token_source: str = "stripe"     # token library source tag (isolation token Library)
    require_zero: bool = True        # Amount verification switch
    channel_check: bool = True       # Payment channel verification switch (payment_method_types Including target channels)
    channel_probe: bool = True       # init Rear advance channel detection switch (update part verify_zero Already have channel verification, Can be closed)
    dual_init: bool = False          # pair init switch (init0 Borrow the way US Get channel type -> init1 Go back to local area to verify the authenticity)
    init0_ccs: list[str] = []        # pair init: init0 Country priority list (Take the exit)
    init1_ccs: list[str] = []        # pair init: init1 Country priority list (Authenticity export)
    init_t_ccs: list[str] = []       # pair init: init_t transitional countries
    follow_checkout: bool = False    # segment follow: remove update All segments outside follow checkout part
    billing_country: str = "auto"    # billing country: "auto"=follow checkout Duan Guo, Otherwise the country is fixed
    attempts: int = 8                # Total attempts (Every Token Maximum number of rounds to try)
    stages: dict[str, StageConfig] = {}


def _find_config_path() -> Path:
    env = os.environ.get("MIN_CONFIG_PATH", "").strip()
    if env and Path(env).exists():
        return Path(env)
    here = Path(__file__).resolve().parent.parent  # backend/
    cand = here / "config.yaml"
    if cand.exists():
        return cand
    # Run directory
    cand2 = Path.cwd() / "config.yaml"
    if cand2.exists():
        return cand2
    return cand


class Settings:
    """Global configuration singleton。raw for completeness YAML dict，Provide convenient attribute access。"""

    def __init__(self) -> None:
        self.path: Path = _find_config_path()
        self.raw: dict[str, Any] = {}
        self.reload()

    def reload(self) -> None:
        if self.path.exists():
            with open(self.path, "r", encoding="utf-8") as f:
                self.raw = yaml.safe_load(f) or {}
        else:
            self.raw = {}
        # Parse staging configuration
        self._stages: dict[str, StageConfig] = {}
        stages_raw = (self.raw.get("chain") or {}).get("stages") or {}
        for name, sc in stages_raw.items():
            self._stages[name] = StageConfig(**(sc or {}))
        # Analyze chain branches
        self._branches: dict[str, BranchConfig] = {}
        branches_raw = (self.raw.get("chain") or {}).get("branches") or {}
        for name in BRANCH_NAMES:
            raw_b = branches_raw.get(name) or {}
            if not isinstance(raw_b, dict):
                raw_b = {}
            b_stages: dict[str, StageConfig] = {}
            # paypal Branches fall back to the top level by default chain.stages (Historically compatible)
            stage_src = raw_b.get("stages") if isinstance(raw_b.get("stages"), dict) else (stages_raw if name == "paypal" else {})
            for sname, sc in stage_src.items():
                b_stages[sname] = StageConfig(**(sc or {}))
            self._branches[name] = BranchConfig(
                label=str(raw_b.get("label") or BRANCH_LABELS.get(name, name)),
                channel=str(raw_b.get("channel") or ("paypal" if name == "paypal" else name if name in ("momo", "upi", "kakao", "bizum", "gopay", "naver_pay", "ideal", "blik", "twint", "gcash", "grabpay") else ("gopay" if name == "qris" else "card"))),
                token_source=str(raw_b.get("token_source") or ("stripe" if name == "paypal" else name)),
                require_zero=bool(raw_b.get("require_zero", True)),
                channel_check=bool(raw_b.get("channel_check", True)),
                channel_probe=bool(raw_b.get("channel_probe", True)),
                dual_init=bool(raw_b.get("dual_init", False)),
                init0_ccs=list(raw_b.get("init0_ccs") or []),
                init1_ccs=list(raw_b.get("init1_ccs") or []),
                init_t_ccs=list(raw_b.get("init_t_ccs") or []),
                follow_checkout=bool(raw_b.get("follow_checkout", False)),
                billing_country=str(raw_b.get("billing_country") or "auto"),
                attempts=int(raw_b.get("attempts") or 8),
                stages=b_stages,
            )

    # ---- server ----
    @property
    def host(self) -> str:
        return (self.raw.get("server") or {}).get("host", "0.0.0.0")

    @property
    def port(self) -> int:
        return int((self.raw.get("server") or {}).get("port", 8770))

    @property
    def max_concurrent_chains(self) -> int:
        return int((self.raw.get("server") or {}).get("max_concurrent_chains", 10))

    @property
    def thread_pool_size(self) -> int:
        return int((self.raw.get("server") or {}).get("thread_pool_size", 20))

    @property
    def chain_mode(self) -> str:
        return (self.raw.get("server") or {}).get("chain_mode", "mock")

    @property
    def mock_success_rate(self) -> float:
        return float((self.raw.get("server") or {}).get("mock_success_rate", 0.6))

    @property
    def mock_stage_min(self) -> float:
        return float((self.raw.get("server") or {}).get("mock_stage_min", 0.4))

    @property
    def mock_stage_max(self) -> float:
        return float((self.raw.get("server") or {}).get("mock_stage_max", 1.6))

    # ---- chain ----
    @property
    def require_zero(self) -> bool:
        return bool((self.raw.get("chain") or {}).get("require_zero", True))

    @property
    def auto_billing(self) -> bool:
        return bool((self.raw.get("chain") or {}).get("auto_billing", True))

    @property
    def token_min_interval_ms(self) -> int:
        return int((self.raw.get("chain") or {}).get("token_min_interval_ms", 500))

    @property
    def fail_cooldown_sec(self) -> int:
        return int((self.raw.get("chain") or {}).get("fail_cooldown_sec", 60))

    def stage(self, name: str) -> StageConfig:
        return self._stages.get(name) or StageConfig()

    def branch(self, name: str = "paypal") -> BranchConfig:
        """Press the chain branch to return to the independent seven-segment configuration。Unknown branch rollback paypal。"""
        return self._branches.get(name) or self._branches.get("paypal") or BranchConfig()

    def branch_stage(self, branch: str, name: str) -> StageConfig:
        """Single segment configuration within branch；Roll back to the top level when the branch does not define this section/default。"""
        b = self.branch(branch)
        return b.stages.get(name) or self._stages.get(name) or StageConfig()

    def branch_oaics(self, branch: str = "paypal") -> BranchConfig:
        """[Deprecated-read only] oaics Five paragraph configuration (branches.<branch>.oaics)。

        2026-08-13 The starting link no longer reads the configuration.: oaics country of five sections/billing country/Currency
        All follow seven paragraphs pick_countries mapping (See core/chain.py pick_oaics_countries)。
        Keep this method for frontend only branch_dict Read-only display compatible。
        """
        raw_b = (self.raw.get("chain") or {}).get("branches") or {}
        raw = raw_b.get(branch) or {}
        raw = raw if isinstance(raw, dict) else {}
        oaics_raw = raw.get("oaics")
        oaics_raw = oaics_raw if isinstance(oaics_raw, dict) else {}
        stages: dict[str, StageConfig] = {}
        stage_src = oaics_raw.get("stages") if isinstance(oaics_raw.get("stages"), dict) else {}
        for sname in OAICS_STAGE_NAMES:
            sc = stage_src.get(sname) or {}
            sc = sc if isinstance(sc, dict) else {}
            stages[sname] = StageConfig(**(sc or {}))
        return BranchConfig(
            label=str(oaics_raw.get("label") or "OAICS fifth section"),
            channel=str(oaics_raw.get("channel") or "paypal"),
            token_source=str(oaics_raw.get("token_source") or "stripe"),
            require_zero=bool(oaics_raw.get("require_zero", True)),
            channel_check=bool(oaics_raw.get("channel_check", True)),
            follow_checkout=bool(oaics_raw.get("follow_checkout", False)),
            billing_country=str(oaics_raw.get("billing_country") or "auto"),
            attempts=int(oaics_raw.get("attempts") or 5),
            stages=stages,
        )

    def branch_oaics_stage(self, branch: str, name: str) -> StageConfig:
        """[Deprecated-read only] and branch_oaics Supporting, Link is no longer in use (Show only compatible)。"""
        b = self.branch_oaics(branch)
        return b.stages.get(name) or StageConfig()

    @property
    def branch_names(self) -> list[str]:
        return list(BRANCH_NAMES)

    def branch_dict(self, name: str) -> dict[str, Any]:
        """Branch complete configuration dict（for /api/config output）。"""
        b = self.branch(name)
        stages = {}
        for sname in self.stage_names:
            sc = b.stages.get(sname) or self._stages.get(sname) or StageConfig()
            stages[sname] = {
                "countries": sc.countries,
                "timeout": sc.timeout,
                "retry": sc.retry,
                "poll_interval": sc.poll_interval,
                "max_polls": sc.max_polls,
            }
        ob = self.branch_oaics(name)
        oaics_stages = {}
        for sname in OAICS_STAGE_NAMES:
            sc = ob.stages.get(sname) or StageConfig()
            oaics_stages[sname] = {
                "countries": sc.countries,
                "timeout": sc.timeout,
                "retry": sc.retry,
                "poll_interval": sc.poll_interval,
                "max_polls": sc.max_polls,
            }
        return {
            "name": name,
            "label": b.label,
            "channel": b.channel,
            "token_source": b.token_source,
            "require_zero": b.require_zero,
            "channel_check": b.channel_check,
            "dual_init": b.dual_init,
            "init0_ccs": b.init0_ccs,
            "init1_ccs": b.init1_ccs,
            "init_t_ccs": b.init_t_ccs,
            "follow_checkout": b.follow_checkout,
            "billing_country": b.billing_country,
            "attempts": b.attempts,
            "stages": stages,
            "oaics": {
                "label": ob.label,
                "billing_country": ob.billing_country,
                "attempts": ob.attempts,
                "stages": oaics_stages,
            },
        }

    @property
    def stage_names(self) -> list[str]:
        # 7 Show all segments
        return ["checkout", "init", "update", "provider", "approve", "poll", "resolve"]

    # ---- proxy ----
    @property
    def proxy_cfg(self) -> dict[str, Any]:
        return self.raw.get("proxy") or {}

    def qg_pool(self, name: str = "qg_resi_pool") -> dict[str, Any]:
        pools = self.proxy_cfg
        key = name if name.startswith("qg_") else f"qg_{name}_pool"
        return pools.get(key) or {}

    @property
    def default_pool_name(self) -> str:
        return self.proxy_cfg.get("default_pool", "qg_resi_pool")

    @property
    def health_check_interval(self) -> int:
        return int(self.proxy_cfg.get("health_check_interval", 30))

    @property
    def max_concurrent_per_node(self) -> int:
        return int(self.proxy_cfg.get("max_concurrent_per_node", 3))

    @property
    def proxy_sess_time(self) -> int:
        """711 sticky session Keep alive seconds：Reuse in the same country IP Requires survival across complete links。"""
        return int(self.proxy_cfg.get("sess_time", 600))

    # ---- stripe / tls ----
    @property
    def stripe(self) -> dict[str, Any]:
        return self.raw.get("stripe") or {}

    @property
    def tls(self) -> dict[str, Any]:
        return self.raw.get("tls") or {}

    @property
    def storage(self) -> dict[str, Any]:
        return self.raw.get("storage") or {}

    @property
    def register_pool(self) -> dict[str, Any]:
        """Email registration pool (codex_register) Configuration。"""
        return self.raw.get("register_pool") or {}

    @property
    def db_path(self) -> str:
        p = self.storage.get("db_path", "tokens.db")
        # Relative paths are based on backend Table of contents
        if not os.path.isabs(p):
            p = str(self.path.parent / p)
        return p

    @property
    def momo_cfg(self) -> dict[str, Any]:
        return self.raw.get("momo") or {}

    # ---- web static directory ----
    @property
    def web_dir(self) -> Path:
        return self.path.parent.parent / "web"

    @property
    def backend_dir(self) -> Path:
        return self.path.parent


settings = Settings()
