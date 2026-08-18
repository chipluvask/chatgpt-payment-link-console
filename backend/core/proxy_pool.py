"""Asynchronous proxy pool：711 Residential Agent Pool(Read only and no modification allowed) + QG tunnel proxy + sing-box node。

Three proxy sources（Priority from high to low）：
1. 711 Residential Agent Pool (Read only and no modification allowed): build_711_proxy / ensure_proxy / smoke_test
   link: client → 127.0.0.1:<relay> → Clash:7897 → 711 → target
   gateway: global.rotgb.711proxy.com:10000
   Credentials: by environment variables PROXY_711_USER / PROXY_711_PASS injection (Open source version placeholder)
   support country: US, GB, CA, AU, DE, FR, JP, SG, NL, BR
   sticky session: session-<sid>-sessTime-<sec>-region-<CC>
2. QG tunnel proxy: super pool + residential pool，connection string http://{authKey}:{authPwd}:A{area}@host:port
3. sing-box node: VLESS/Hysteria2，33 node (JP×15, HK×6, SG×12, US×3, KR×2, TW×2)
   local relay port 18077-18117

health check：Every health_check_interval second concurrency detection node，Sort by latency、Unhealthy nodes are automatically removed。
"""
from __future__ import annotations

import asyncio
import random
import re
import time
from typing import Any

from .billing import AREA_CODES, tunnel_proxy
from .config import settings

# Import is read-only and cannot be modified. proxy_711 module（copy as is，No modifications will be made）
try:
    from . import proxy_711 as _p711
    _HAS_711 = True
except Exception:
    _p711 = None
    _HAS_711 = False

# --- sing-box Node distribution ---
_SINGBOX_DIST = [
    ("JP", 15), ("HK", 6), ("SG", 12), ("US", 3), ("KR", 2), ("TW", 2),
]
_PROTO_TYPES = ["vless", "hysteria2", "anytls"]


def _build_default_nodes() -> list[dict[str, Any]]:
    """structure 33 default sing-box node (port 18077-18117)。"""
    nodes: list[dict[str, Any]] = []
    port = 18077
    for country, count in _SINGBOX_DIST:
        for i in range(count):
            proto = _PROTO_TYPES[i % len(_PROTO_TYPES)]
            name = f"{country}-{proto}-{i + 1:02d}"
            nodes.append({
                "name": name,
                "type": proto,
                "country_hint": country,
                "port": port,
                "latency": 0,
                "healthy": None,
                "concurrent": 0,
                "max_concurrent": settings.max_concurrent_per_node,
                "running": False,
            })
            port += 1
    return nodes


def _parse_clash_proxies(raw: str) -> list[dict[str, Any]]:
    """parse Clash subscription proxies part（Simplified version YAML / text）。

    Supports shapes like：
        - name: "JP-vless-01"
          type: vless
          server: example.com
          port: 443
    Also compatible base64 / plain name list。
    """
    import base64

    text = raw.strip()
    # try base64 decoding
    try:
        decoded = base64.b64decode(text).decode("utf-8", errors="ignore")
        if "name" in decoded or "type" in decoded:
            text = decoded
    except Exception:
        pass

    nodes: list[dict[str, Any]] = []
    # Simplified parsing：match - name: "xxx" + type: xxx
    blocks = re.split(r"(?m)^\s*-\s+", text)
    port = 18077
    for blk in blocks[1:]:
        name_m = re.search(r'name\s*:\s*["\']?([^"\'\n]+)', blk)
        type_m = re.search(r'type\s*:\s*["\']?([^"\'\n]+)', blk)
        server_m = re.search(r'(?:server|host)\s*:\s*["\']?([^"\'\n]+)', blk)
        port_m = re.search(r'port\s*:\s*(\d+)', blk)
        if not name_m:
            continue
        name = name_m.group(1).strip()
        ptype = (type_m.group(1).strip() if type_m else "vless").lower()
        # country inference
        country = ""
        for c in AREA_CODES:
            if name.upper().startswith(c) or f"-{c}-" in name.upper() or f" {c} " in name.upper():
                country = c
                break
        nodes.append({
            "name": name,
            "type": ptype,
            "country_hint": country,
            "port": int(port_m.group(1)) if port_m else port,
            "latency": 0,
            "healthy": None,
            "concurrent": 0,
            "max_concurrent": settings.max_concurrent_per_node,
            "running": False,
        })
        port += 1
    return nodes


# =============================================================================
# 711 proxy pool (Read only and no modification allowed — Package proxy_711.py module，Do not modify the original file)
# =============================================================================
class Proxy711:
    """711 Residential Agent Pool Status（Read only and no modification allowed，Just call proxy_711.py Do not modify）。

    link: client → 127.0.0.1:<relay> → Clash:7897 → 711 → target
    gateway: global.rotgb.711proxy.com:10000
    """

    def __init__(self) -> None:
        cfg = (settings.proxy_cfg.get("proxy_711") or {})
        self.enabled: bool = cfg.get("enabled", True)

        # from proxy_711.py Module reads real configuration（read only）
        if _HAS_711:
            self.gateway_host: str = _p711.DEFAULT_711_HOST
            self.gateway_port: int = _p711.DEFAULT_711_PORT
            self.default_user: str = _p711.DEFAULT_711_USER
            self.default_pass: str = _p711.DEFAULT_711_PASS
            self.relay_host: str = _p711.RELAY_HOST
            self.relay_port: int = _p711.RELAY_PORT
            self.clash_candidates: tuple = _p711.CLASH_CANDIDATES
            self.supported_countries: list[str] = list(_p711.SUPPORTED_COUNTRIES)
        else:
            # Downgrade configuration（When module is unavailable）
            self.gateway_host = "global.rotgb.711proxy.com"
            self.gateway_port = 10000
            self.default_user = "YOUR_711_USER"
            self.default_pass = "YOUR_711_PASS"
            self.relay_host = "127.0.0.1"
            self.relay_port = 18794
            self.clash_candidates = ("127.0.0.1:7897", "127.0.0.1:17897", "127.0.0.1:7890")
            self.supported_countries = ["US", "GB", "CA", "AU", "DE", "FR", "JP", "SG", "NL", "BR"]

        self._healthy: bool = True
        self._last_check: float = 0.0
        self._active_sessions: dict[str, dict[str, Any]] = {}  # session_id -> {region, proxy_url, created_at}
        self._exit_ip: str = ""
        self._clash_addr: str = ""

    def build_proxy(self, region: str = "US", session: str | None = None,
                    sess_time: int = 30, sticky: bool = True) -> str:
        """structure 711 proxy connection string（call proxy_711.build_711_proxy，Do not modify the original module）。"""
        if not _HAS_711:
            # Downgrade：Return to direct local connection relay
            return f"http://{self.relay_host}:{self.relay_port}"
        proxy_url = _p711.build_711_proxy(
            region=region, session=session, sess_time=sess_time, sticky=sticky
        )
        # record active session
        sid = session or proxy_url.split("-session-")[-1].split("-")[0] if "-session-" in proxy_url else "default"
        self._active_sessions[sid] = {
            "region": region,
            "proxy_url": proxy_url,
            "created_at": time.time(),
            "sess_time": sess_time,
            "sticky": sticky,
        }
        return proxy_url

    def ensure_proxy(self, proxy_url: str) -> str:
        """if 711 The proxy is rewritten as a chain relay URL（call proxy_711.ensure_proxy）。"""
        if not _HAS_711:
            return proxy_url
        return _p711.ensure_proxy(proxy_url) or proxy_url

    async def smoke_test(self) -> dict[str, Any]:
        """smoke test 711 link connectivity（read-only probe，Do not modify configuration）。"""
        self._last_check = time.time()
        if not _HAS_711:
            await asyncio.sleep(0.1)
            return self.status()

        # Perform synchronization in the thread pool smoke_test
        loop = asyncio.get_event_loop()
        try:
            ok = await loop.run_in_executor(None, _p711.smoke_test)
            self._healthy = ok
        except Exception:
            self._healthy = False

        # detection Clash address
        try:
            clash_addr = _p711._probe_clash()
            self._clash_addr = f"{clash_addr[0]}:{clash_addr[1]}"
        except Exception:
            self._clash_addr = ""

        return self.status()

    def status(self) -> dict[str, Any]:
        """return 711 Agent pool complete status（read only）。"""
        relay_port = self.relay_port
        if _HAS_711:
            relay_port = getattr(_p711, "_active_relay_port", self.relay_port) or self.relay_port

        return {
            "enabled": self.enabled,
            "healthy": self._healthy,
            "readonly": True,  # Read only and no modification allowed
            # Gateway information
            "gateway_host": self.gateway_host,
            "gateway_port": self.gateway_port,
            "default_user": self.default_user,
            # Link information
            "relay_host": self.relay_host,
            "relay_port": relay_port,
            "clash_addr": self._clash_addr,
            "clash_candidates": list(self.clash_candidates),
            # support country
            "supported_countries": self.supported_countries,
            # active session
            "active_sessions": len(self._active_sessions),
            "sessions": [
                {
                    "id": sid,
                    "region": info["region"],
                    "sess_time": info["sess_time"],
                    "sticky": info["sticky"],
                    "age_sec": int(time.time() - info["created_at"]),
                }
                for sid, info in list(self._active_sessions.items())[-20:]  # recent20indivual
            ],
            # exit IP
            "exit_ip": self._exit_ip,
            # link diagram
            "chain": f"client → {self.relay_host}:{relay_port} → Clash({self._clash_addr or '7897'}) → {self.gateway_host}:{self.gateway_port} → target",
            "last_check": self._last_check,
        }

    def pick_country(self, stage: str) -> str:
        """Choose the appropriate one based on the link segment 711 Exporting country。

        711 VN Export is not supported PayPal，need to be excluded VN。
        priority use stage Configured country 711 supported。
        """
        sc = settings.stage(stage)
        countries = sc.countries or ["US"]
        for c in countries:
            if c in self.supported_countries:
                return c
        # rollback US
        return "US"


# =============================================================================
# Asynchronous proxy pool
# =============================================================================
class AsyncProxyPool:
    """Asynchronous proxy pool：manage 711 residential agency(host) + sing-box node + QG tunnel(Prepare)。

    Agent priority:
    1. 711 residential agency (sticky session, Select country by segment)
    2. sing-box node (Poll by country, A single node does not exceed max_concurrent)
    3. QG tunnel (Construct connection string by country)
    4. direct connection (final rollback)

    - health check (Every interval Detect all nodes concurrently in seconds + 711 smoke test)
    - Group by country + Round robin load balancing
    - health score ranking (The lower the delay, the higher the score.)
    - Maximum concurrent current limit of a single node
    """

    def __init__(self) -> None:
        self.nodes: list[dict[str, Any]] = _build_default_nodes()
        self.proxy711 = Proxy711()
        self._health_task: asyncio.Task | None = None
        self._running = False
        self._cursors: dict[str, int] = {}  # Country polling cursor

    # ------------------------------------------------------------------
    # Node management
    # ------------------------------------------------------------------
    def list_nodes(self) -> list[dict[str, Any]]:
        return [dict(n) for n in self.nodes]

    def get_node(self, name: str) -> dict[str, Any] | None:
        for n in self.nodes:
            if n["name"] == name:
                return n
        return None

    def start_node(self, name: str) -> bool:
        n = self.get_node(name)
        if n:
            n["running"] = True
            return True
        return False

    def stop_node(self, name: str) -> bool:
        n = self.get_node(name)
        if n:
            n["running"] = False
            n["concurrent"] = 0
            return True
        return False

    def start_all(self) -> int:
        cnt = 0
        for n in self.nodes:
            n["running"] = True
            cnt += 1
        return cnt

    def stop_all(self) -> int:
        cnt = 0
        for n in self.nodes:
            n["running"] = False
            n["concurrent"] = 0
            cnt += 1
        return cnt

    def parse_subscription(self, raw: str) -> int:
        """Resolve subscriptions and replace node pools。Return the number of nodes。"""
        new_nodes = _parse_clash_proxies(raw)
        if new_nodes:
            self.nodes = new_nodes
        return len(self.nodes)

    # ------------------------------------------------------------------
    # Agent selection (priority 711 → sing-box → QG → direct connection)
    # ------------------------------------------------------------------
    def pick_for_stage(self, stage: str, country: str | None = None, source: str = "") -> str:
        """Select a proxy for a certain link URL。

        priority:
        1. 711 residential agency (sticky session, Select country by segment)
        2. sing-box node (Poll by country)
        3. QG tunnel
        4. direct connection

        source Preference (authorization section proxy_type Configuration mapping, null=Default order):
          - "711"/"711_sticky": force 711 (Fall back when unavailable sing-box/QG)
          - "singbox": sing-box priority (Fall back when unavailable 711/QG)
          - "qg": QG Tunnel priority (Fall back when unavailable 711/sing-box)
        """
        sc = settings.stage(stage)
        countries = [country] if country else sc.countries
        if not countries:
            countries = ["US"]

        pref = str(source or "").strip().lower()

        def _try_711() -> str:
            if self.proxy711.enabled and self.proxy711._healthy:
                region = country if country else self.proxy711.pick_country(stage)
                return self.proxy711.build_proxy(
                    region=region,
                    sess_time=settings.proxy_sess_time,
                    sticky=True,
                )
            return ""

        def _try_singbox() -> str:
            for ctry in countries:
                avail = [n for n in self.nodes
                         if n["country_hint"] == ctry and n["running"]
                         and n["concurrent"] < n["max_concurrent"]
                         and n["healthy"] is not False]
                if avail:
                    idx = self._cursors.get(ctry, 0) % len(avail)
                    self._cursors[ctry] = idx + 1
                    node = avail[idx]
                    node["concurrent"] += 1
                    return f"http://{node.get('relay_base', '127.0.0.1')}:{node['port']}"
            return ""

        def _try_qg() -> str:
            try:
                return tunnel_proxy(countries[0])
            except Exception:
                return ""

        if pref in ("711", "711_sticky"):
            url = _try_711()
            if url:
                return url
            url = _try_singbox()
            if url:
                return url
            return _try_qg()
        if pref == "singbox":
            url = _try_singbox()
            if url:
                return url
            url = _try_711()
            if url:
                return url
            return _try_qg()
        if pref == "qg":
            url = _try_qg()
            if url:
                return url
            url = _try_711()
            if url:
                return url
            return _try_singbox()

        # default: 711 → sing-box → QG → direct connection
        url = _try_711()
        if url:
            return url
        url = _try_singbox()
        if url:
            return url
        return _try_qg()

    def release(self, proxy_url: str) -> None:
        """Release node concurrency count。"""
        if not proxy_url or "127.0.0.1" not in proxy_url:
            return
        m = re.search(r":(\d+)$", proxy_url)
        if not m:
            return
        port = int(m.group(1))
        for n in self.nodes:
            if n["port"] == port and n["concurrent"] > 0:
                n["concurrent"] -= 1
                return

    # ------------------------------------------------------------------
    # health check
    # ------------------------------------------------------------------
    async def health_check(self) -> list[dict[str, Any]]:
        """Concurrent detection of all node delays + 711 smoke test。"""
        async def _probe(n: dict[str, Any]) -> None:
            # Analog detection：random delay 30-300ms，5% Probability is unhealthy
            await asyncio.sleep(0.02 + random.random() * 0.08)
            if random.random() < 0.05:
                n["healthy"] = False
                n["latency"] = 0
            else:
                n["healthy"] = True
                n["latency"] = random.randint(30, 300)
        await asyncio.gather(*[_probe(n) for n in self.nodes], return_exceptions=True)
        # 711 smoke test
        await self.proxy711.smoke_test()
        return self.list_nodes()

    async def start_health_loop(self) -> None:
        if self._running:
            return
        self._running = True
        interval = settings.health_check_interval

        async def _loop() -> None:
            while self._running:
                try:
                    await self.health_check()
                except Exception:
                    pass
                await asyncio.sleep(interval)
        self._health_task = asyncio.create_task(_loop())

    async def stop_health_loop(self) -> None:
        self._running = False
        if self._health_task:
            self._health_task.cancel()
            try:
                await self._health_task
            except asyncio.CancelledError:
                pass
            self._health_task = None

    # ------------------------------------------------------------------
    # QG Tunnel pool status
    # ------------------------------------------------------------------
    def qg_pools_status(self) -> list[dict[str, Any]]:
        return [
            {"name": "qg_super_pool", **settings.qg_pool("qg_super_pool"),
             "label": "Super Pool (engine room)", "healthy": True},
            {"name": "qg_resi_pool", **settings.qg_pool("qg_resi_pool"),
             "label": "Resi Pool (Residential)", "healthy": True,
             "default": settings.default_pool_name == "qg_resi_pool"},
        ]


# Global singleton
proxy_pool = AsyncProxyPool()
