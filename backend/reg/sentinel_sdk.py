# -*- coding: utf-8 -*-
"""
sentinel_sdk.py — generate OpenAI Required for registration OpenAI-Sentinel-Token / SO-Token。

Repair guide（No. 4-8 point）Alignment：
  4. No handwriting splicing token，Load official Sentinel SDK internal logic
  5. so-token from /req of so Field，The generation method is similar to PoW，exist SDK Inside
  6. observer wait 5000ms（official sdk.js constant Xn=5e3）
  7. create_account First /req，flow=oauth_create_account
  8. from requirements generate sentinel token + so-token

Strategy：
  - oauth_create_account：real t+so。default pure（sentinel_pure_vm pure Python obt/collector VM，
    none Chrome）；OPENAI_SENTINEL_MODE=browser|node|auto Can be changed。
  - username_password_create：Same as above
  - authorize_continue：pure Python t=dx（Server side loose）

The log only records the length/model/Does it contain p、t、so，Never print token plain text。
"""
import os
import json
import time
import uuid
import random
import base64
from typing import Optional, Dict, Any

# Retry with tape curl_cffi Session Gasket
try:
    from .cf_shim import requests, Session
except Exception:
    import curl_cffi.requests as requests
    from curl_cffi.requests import Session

SENTINEL_REQ_URL = "https://sentinel.openai.com/backend-api/sentinel/req"
SENTINEL_VERSION = "20260219f9f6"
# official sdk.js constant Xn=5e3
OBSERVER_WAIT_MS = 5000
IMPERSONATE = "chrome131"

# most recent /req Reason for failure（for pure-vm Error remarks；Do not print token plain text）
_LAST_REQ_ERROR: Optional[str] = None


def _is_711_like_proxy(url: Optional[str]) -> bool:
    """711 Residential / local machine 711 Relay is not available for sentinel.openai.com（export quilt CF or CONNECT unstable）。"""
    if not url:
        return False
    low = str(url).lower()
    if "711proxy" in low or "rotgb" in low:
        return True
    if "127.0.0.1:18792" in low or "localhost:18792" in low:
        return True
    try:
        from core import proxy_711 as _p711
        if _p711.is_711_proxy(url):
            return True
    except Exception:
        pass
    return False


def _sentinel_egress_candidates(explicit_proxies=None) -> list:
    """sentinel /req Export candidate（by priority）。

    Actual measurement（Mainland side of the machine）：
      - Really direct connection sentinel.openai.com → Cloudflare 403 HTML（No JSON）
      - via this machine Clash(HTTP_PROXY=127.0.0.1:7897) → 200 JSON
      - through 711 Residential → unstable / Do not apply

    old implementation proxies=None only「happen」eat libcurl of HTTP_PROXY env；
    env When it is cleared or the process is not inherited, it becomes 403 → pure: /req fail or not JSON。
    Explicit detection here Clash / env，and chatgpt._local_or_env_proxies Alignment。
    """
    import socket

    seen = set()
    out = []

    def _add(px):
        if px is None:
            key = "__direct__"
            if key not in seen:
                seen.add(key)
                out.append(None)
            return
        if isinstance(px, dict):
            u = (px.get("https") or px.get("http") or "").strip()
        else:
            u = str(px).strip()
        if not u or _is_711_like_proxy(u):
            return
        key = u.lower()
        if key in seen:
            return
        seen.add(key)
        out.append({"http": u, "https": u})

    # 1) The caller explicitly passes in（No 711）
    if explicit_proxies:
        _add(explicit_proxies)

    # 2) environment variables（jump over 711）
    for k in (
        "HTTPS_PROXY", "HTTP_PROXY", "https_proxy", "http_proxy",
        "ALL_PROXY", "all_proxy",
    ):
        v = (os.environ.get(k) or "").strip()
        if v:
            _add(v)

    # 3) Detect this machine Clash mixed-port
    for item in ("127.0.0.1:7897", "127.0.0.1:17897", "127.0.0.1:7890", "127.0.0.1:10809"):
        host, port_s = item.rsplit(":", 1)
        try:
            sock = socket.create_connection((host, int(port_s)), timeout=0.5)
            sock.close()
            _add(f"http://{item}")
        except OSError:
            continue

    # 4) It’s really straight to the point（overseas VPS Wait for direct connection to the scene）
    _add(None)
    return out if out else [None]


# ---------------------------------------------------------------------------
# client Proof-of-Work generator（pure Python，used for /req body of p with envelope p）
# ---------------------------------------------------------------------------

class SentinelTokenGenerator:
    MAX_ATTEMPTS = 500000
    ERROR_PREFIX = "wQ8Lk5FbGpA2NcR9dShT6gYjU7VxZ4D"

    def __init__(
        self,
        device_id=None,
        user_agent=None,
        screen=None,
        languages=None,
        hardware_concurrency=None,
    ):
        self.device_id = device_id or str(uuid.uuid4())
        self.user_agent = user_agent or (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/131.0.0.0 Safari/537.36"
        )
        self.screen = screen or "1920x1080"
        if languages is None:
            self.languages = ("en-US", "en")
        elif isinstance(languages, (list, tuple)):
            self.languages = tuple(languages)
        else:
            self.languages = (str(languages),)
        self.hardware_concurrency = int(hardware_concurrency or 8)
        self.requirements_seed = str(random.random())
        self.sid = str(uuid.uuid4())

    @staticmethod
    def _fnv1a_32(text):
        h = 2166136261
        for ch in text:
            h ^= ord(ch)
            h = (h * 16777619) & 0xFFFFFFFF
        h ^= h >> 16
        h = (h * 2246822507) & 0xFFFFFFFF
        h ^= h >> 13
        h = (h * 3266489909) & 0xFFFFFFFF
        h ^= h >> 16
        return format(h & 0xFFFFFFFF, "08x")

    def _get_config(self):
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        date_str = now.strftime("%a %b %d %Y %H:%M:%S GMT+0000 (Coordinated Universal Time)")
        perf_now = random.uniform(1000, 50000)
        time_origin = time.time() * 1000 - perf_now
        nav_prop = random.choice(
            [
                "vendorSub", "productSub", "vendor", "maxTouchPoints",
                "scheduling", "userActivation", "doNotTrack", "geolocation",
                "connection", "plugins", "mimeTypes", "pdfViewerEnabled",
                "webkitTemporaryStorage", "webkitPersistentStorage",
                "hardwareConcurrency", "cookieEnabled", "credentials",
                "mediaDevices", "permissions", "locks", "ink",
            ]
        )
        lang0 = self.languages[0] if self.languages else "en-US"
        lang_joined = ",".join(self.languages) if self.languages else "en-US,en"
        return [
            self.screen,
            date_str,
            4294705152,
            random.random(),
            self.user_agent,
            f"https://sentinel.openai.com/sentinel/{SENTINEL_VERSION}/sdk.js",
            None,
            None,
            lang0,
            lang_joined,
            random.random(),
            f"{nav_prop}\u2212undefined",
            random.choice(["location", "implementation", "URL", "documentURI", "compatMode"]),
            random.choice(["Object", "Function", "Array", "Number", "parseFloat", "undefined"]),
            perf_now,
            self.sid,
            "",
            self.hardware_concurrency,
            time_origin,
        ]

    @staticmethod
    def _b64_encode(data):
        raw = json.dumps(data, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        return base64.b64encode(raw).decode("ascii")

    def _run_check(self, start_time, seed, difficulty, config, nonce):
        config[3] = nonce
        config[9] = round((time.time() - start_time) * 1000)
        encoded = self._b64_encode(config)
        digest = self._fnv1a_32(seed + encoded)
        if digest[: len(difficulty)] <= difficulty:
            return encoded + "~S"
        return None

    def generate_token(self, seed=None, difficulty=None):
        seed = seed or self.requirements_seed
        difficulty = difficulty or "0"
        start_time = time.time()
        config = self._get_config()
        for nonce in range(self.MAX_ATTEMPTS):
            value = self._run_check(start_time, seed, difficulty, config, nonce)
            if value:
                return "gAAAAAB" + value
        return "gAAAAAB" + self.ERROR_PREFIX + self._b64_encode(str(None))

    def generate_requirements_token(self):
        config = self._get_config()
        config[3] = 1
        config[9] = round(random.uniform(5, 50))
        return "gAAAAAC" + self._b64_encode(config)


# ---------------------------------------------------------------------------
# /req Challenge acquisition + pure Python Envelope assembly（Use only for loose steps）
# ---------------------------------------------------------------------------

def fetch_sentinel_challenge(device_id, flow, proxies, request_p=None, fp=None):
    """POST /req，Return to complete JSON（Contains token / turnstile / proofofwork / so）。

    fp Optional：and chatgpt Matching fingerprint alignment UA / sec-ch-ua / impersonate。

    proxies:
      - None  → Automatically select outlet：env HTTP_PROXY / local machine Clash → It’s really straight to the point
      - dict  → Use this agent first（711 will be ignored and fallback to the local exit）
    Write on failure _LAST_REQ_ERROR（status / CF 403 / Exception summary），for pure-vm Remark。
    """
    global _LAST_REQ_ERROR
    _LAST_REQ_ERROR = None

    ua = None
    screen = None
    languages = None
    hw = None
    impersonate = IMPERSONATE
    sec_ch_ua = '"Not:A-Brand";v="99", "Google Chrome";v="131", "Chromium";v="131"'
    sec_platform = '"Windows"'
    if isinstance(fp, dict):
        ua = fp.get("ua")
        scr = fp.get("screen") or {}
        if scr.get("width") and scr.get("height"):
            screen = f"{scr['width']}x{scr['height']}"
        languages = fp.get("languages")
        hw = fp.get("hardware_concurrency")
        impersonate = fp.get("impersonate") or IMPERSONATE
        cfp = fp.get("chrome_fp") or {}
        if cfp.get("sec-ch-ua"):
            sec_ch_ua = cfp["sec-ch-ua"]
        if cfp.get("sec-ch-ua-platform"):
            sec_platform = cfp["sec-ch-ua-platform"]
        elif fp.get("os_platform"):
            sec_platform = f'"{fp["os_platform"]}"'
    generator = SentinelTokenGenerator(
        device_id=device_id, user_agent=ua, screen=screen,
        languages=languages, hardware_concurrency=hw,
    )
    if request_p is None:
        request_p = generator.generate_requirements_token()
    body = {"p": str(request_p), "id": device_id, "flow": flow}
    body_data = json.dumps(body, separators=(",", ":"))
    headers = {
        "Content-Type": "text/plain;charset=UTF-8",
        "Accept": "*/*",
        "Accept-Encoding": "gzip, deflate, br, zstd",
        "Referer": f"https://sentinel.openai.com/backend-api/sentinel/frame.html?sv={SENTINEL_VERSION}",
        "Origin": "https://sentinel.openai.com",
        "User-Agent": generator.user_agent,
        "sec-ch-ua": sec_ch_ua,
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": sec_platform,
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin",
    }

    # Export candidate：explicit proxy（If not 711）→ env/Clash → direct connection
    candidates = _sentinel_egress_candidates(proxies)
    errors = []

    for attempt, px in enumerate(candidates):
        px_label = "direct"
        if isinstance(px, dict):
            u = px.get("https") or px.get("http") or ""
            px_label = u.split("@")[-1] if "@" in u else u
        for retry in range(2):
            try:
                resp = requests.post(
                    SENTINEL_REQ_URL,
                    data=body_data,
                    headers=headers,
                    proxies=px,
                    impersonate=impersonate,
                    timeout=20,
                )
                status = resp.status_code
                text = resp.text or ""
                if status != 200:
                    # CF 403 Commonly seen in mainland China
                    hint = ""
                    low = text[:200].lower()
                    if status == 403 and ("cloudflare" in low or "attention required" in low):
                        hint = " (Cloudflare 403，Requires local machine Clash/HTTP_PROXY exit，Don’t really connect directly)"
                    errors.append(f"px={px_label} status={status}{hint}")
                    # 403/5xx：Change to the next exit；Only retry once with the same exit
                    if status in (403, 429, 502, 503, 520, 521, 522, 523, 524):
                        break
                    continue
                try:
                    data = resp.json()
                except Exception as je:
                    errors.append(
                        f"px={px_label} status=200 non-JSON "
                        f"ct={resp.headers.get('content-type')} err={je}"
                    )
                    continue
                if not isinstance(data, dict) or not data.get("token"):
                    errors.append(
                        f"px={px_label} JSON lack token keys="
                        f"{list(data.keys()) if isinstance(data, dict) else type(data).__name__}"
                    )
                    continue
                _LAST_REQ_ERROR = None
                return data
            except Exception as e:
                errors.append(
                    f"px={px_label} {type(e).__name__}: {str(e)[:120]}"
                )
                time.sleep(0.3 * (retry + 1))
                continue

    _LAST_REQ_ERROR = "; ".join(errors[-6:]) if errors else "unknown"
    return None


def build_sentinel_token(device_id, flow, proxies=None, t_mode="dx"):
    """pure Python envelope（t non-realistic solution）。Only for loose steps，cannot be used for create_account。

    t_mode:
      "dx"    -> turnstile.dx original value（authorize_continue Loosely available）
      "empty" -> t=""（username_password_create pure Python rollback）
    """
    if not device_id:
        return None
    # sentinel.openai.com：automatic env/Clash exit（Don’t force true direct connection，See fetch_sentinel_challenge）
    challenge = fetch_sentinel_challenge(device_id, flow, proxies, request_p=None)
    if not isinstance(challenge, dict):
        return None
    c_value = str(challenge.get("token") or "").strip()
    if not c_value:
        return None

    t_raw = (challenge.get("turnstile") or {}).get("dx")
    if t_mode == "empty":
        t_value = ""
    else:
        t_value = "" if t_raw is None else str(t_raw).strip()

    pow_data = challenge.get("proofofwork") or {}
    generator = SentinelTokenGenerator(device_id=device_id, user_agent=None)
    if pow_data.get("required") and pow_data.get("seed"):
        p_value = generator.generate_token(
            seed=str(pow_data.get("seed")),
            difficulty=str(pow_data.get("difficulty", "0")),
        )
    else:
        p_value = ""

    envelope = json.dumps(
        {"p": p_value, "t": t_value, "c": c_value,
         "id": device_id, "flow": flow},
        separators=(",", ":"), ensure_ascii=False,
    )
    return envelope


# ---------------------------------------------------------------------------
# official SDK path：Node (quickjs fake DOM) / real browser
# ---------------------------------------------------------------------------

_BROWSER_REQUIRED_FLOWS = ("oauth_create_account", "username_password_create")


# Morphological heuristic（from camoufox_captured.json[23] True solution vs Node fake DOM Actual measurement）
# real t≈1332 / real so≈520；Node Fake t≈950–1012 / Fake so≈400–404。
# local t_ok Originally only checked if it was not empty，will「Junk fingerprint package」when successful。See NOBROWSER_TSO_REVERSE.md。
_T_LEN_MIN_LIKELY = 1150
_SO_LEN_MIN_LIKELY = 460


def _validate_envelope(sentinel_token: Optional[str], so_token: Optional[str] = None):
    """Check envelope：t Can't be '0'/null；create_account need so Field。

    Attached is the morphological heuristic t_morph_ok / so_morph_ok：
      real Chrome solved t/so significantly longer than Node fake DOM of「false success」Bag。
      Does not replace server-side cryptography verification，Just avoid node Path false positive ok。
    """
    t_ok = False
    so_ok = False
    t_len = 0
    so_field_len = 0
    t_prefix = ""
    so_prefix = ""
    if sentinel_token:
        try:
            env = json.loads(sentinel_token) if isinstance(sentinel_token, str) else sentinel_token
            if isinstance(env, dict):
                t_val = env.get("t")
                t_str = str(t_val or "")
                t_len = len(t_str)
                t_prefix = t_str[:16]
                t_ok = bool(t_val) and t_str not in ("0", "null", "None", "")
        except Exception:
            pass
    if so_token:
        try:
            so_env = json.loads(so_token) if isinstance(so_token, str) else so_token
            if isinstance(so_env, dict) and so_env.get("so"):
                so_ok = True
                so_str = str(so_env.get("so") or "")
                so_field_len = len(so_str)
                so_prefix = so_str[:16]
            elif isinstance(so_token, str) and len(so_token) > 20:
                # bare so The string is also considered a partial success.（but create_account To capture the package, you need the entire package）
                so_ok = False
        except Exception:
            pass
    t_morph_ok = t_ok and t_len >= _T_LEN_MIN_LIKELY
    so_morph_ok = (not so_ok) or (so_field_len >= _SO_LEN_MIN_LIKELY)
    return {
        "t_ok": t_ok,
        "so_ok": so_ok,
        "t_len": t_len,
        "so_field_len": so_field_len,
        "t_morph_ok": t_morph_ok,
        "so_morph_ok": so_morph_ok,
        "t_prefix": t_prefix,
        "so_prefix": so_prefix,
    }


def _node_sdk_tokens(flow: str, did: str, logger=None):
    """Try using Node Run official sdk.js generate sentinel + so。

    Notice：fake DOM Down turnstile often solved t='0'，sessionObserverToken often null。
    If the verification fails, return ok=False，Browser rollback by caller。
    """
    log = logger or (lambda _m: None)
    try:
        from . import sentinel_quickjs as sq
    except Exception as e:
        return {"ok": False, "error": f"import sentinel_quickjs: {e}"}

    logs = []
    try:
        # new interface：one output token + so（internal 5000ms observer wait）
        if hasattr(sq, "build_tokens_quickjs"):
            r = sq.build_tokens_quickjs(
                device_id=did, flow=flow, observer_wait_ms=OBSERVER_WAIT_MS,
                logger=lambda m: logs.append(m))
            if isinstance(r, dict) and r.get("sentinel_token"):
                v = _validate_envelope(r.get("sentinel_token"), r.get("so_token"))
                # create_account hard steps：Unless empty, the form is required to be close to the browser's true solution
                # （Node fake DOM often t_ok=so_ok=True but t≈1k/so≈400，Server rejects）
                need_so = flow in _BROWSER_REQUIRED_FLOWS
                morph_pass = v.get("t_morph_ok") and (v.get("so_morph_ok") if need_so else True)
                if v["t_ok"] and (not need_so or v["so_ok"]) and morph_pass:
                    return {
                        "ok": True, "mode": "node-sdk",
                        "sentinel_token": r.get("sentinel_token"),
                        "so_token": r.get("so_token"),
                        "sdk_version": SENTINEL_VERSION,
                        "observer_wait_ms": OBSERVER_WAIT_MS,
                        **v,
                    }
                return {
                    "ok": False, "mode": "node-sdk",
                    "error": (
                        f"node Output is invalid/Short shape t_ok={v['t_ok']} so_ok={v['so_ok']} "
                        f"t_len={v['t_len']} so_len={v.get('so_field_len')} "
                        f"t_morph={v.get('t_morph_ok')} so_morph={v.get('so_morph_ok')} "
                        f"logs={'; '.join(logs)[:200]}"
                    ),
                    **v,
                }
        # old interface：only sentinel envelope
        tok = sq.build_sentinel_token_quickjs(
            device_id=did, flow=flow, logger=lambda m: logs.append(m))
        if tok:
            v = _validate_envelope(tok, None)
            if v["t_ok"] and flow not in _BROWSER_REQUIRED_FLOWS:
                return {
                    "ok": True, "mode": "node-sdk",
                    "sentinel_token": tok, "so_token": None,
                    "sdk_version": SENTINEL_VERSION, **v,
                }
            return {
                "ok": False, "mode": "node-sdk",
                "error": f"node t invalid t_ok={v['t_ok']} t_len={v['t_len']} "
                         f"(fake DOM often return t='0') logs={'; '.join(logs)[:200]}",
                **v,
            }
        return {"ok": False, "mode": "node-sdk",
                "error": "; ".join(logs) or "build_sentinel_token_quickjs Return empty"}
    except Exception as e:
        return {"ok": False, "mode": "node-sdk",
                "error": f"{type(e).__name__}: {e}"}


def _browser_sdk_tokens(flow: str, did: str, logger=None):
    """reality Chrome + official SDK：token(flow) → wait 5000ms → sessionObserverToken(flow)。"""
    log = logger or (lambda _m: None)
    try:
        from . import sentinel_browser as _sb
        r = _sb.generate_tokens(
            flow, did=did, proxy="",
            observer_wait_ms=OBSERVER_WAIT_MS,
            logger=log,
        )
        st = r.get("sentinel_token")
        so = r.get("so_token")
        v = _validate_envelope(st, so)
        ok = bool(st) and v["t_ok"] and (flow not in _BROWSER_REQUIRED_FLOWS or v["so_ok"])
        return {
            "ok": ok,
            "mode": "browser",
            "sentinel_token": st,
            "so_token": so,
            "sdk_version": r.get("sdk_version") or SENTINEL_VERSION,
            "observer_wait_ms": r.get("observer_wait_ms", OBSERVER_WAIT_MS),
            "error": None if ok else (
                r.get("error") or f"browser Incomplete output t_ok={v['t_ok']} so_ok={v['so_ok']}"
            ),
            **v,
        }
    except Exception as e:
        return {"ok": False, "mode": "browser",
                "sentinel_token": None, "so_token": None,
                "error": f"{type(e).__name__}: {e}"}


def _sentinel_mode() -> str:
    """create_account of t/so Generate strategy。

    OPENAI_SENTINEL_MODE:
      pure    — pure Python obt/collector VM，none Chrome/Node（default；See sentinel_pure_vm）
      browser — reality Chrome + official SDK（rollback / control）
      node    — Node fake DOM Run official sdk.js（Often short in shape）
      auto    — pure → browser → node
    """
    m = (os.environ.get("OPENAI_SENTINEL_MODE") or "pure").strip().lower()
    if m in ("pure", "pure-vm", "vm"):
        return "pure"
    if m in ("browser", "node", "auto", "node-sdk", "chrome"):
        if m in ("node-sdk",):
            return "node"
        if m in ("chrome",):
            return "browser"
        return m
    return "pure"


def _pure_vm_tokens(flow: str, did: str, logger=None, fp=None):
    """P2+P3: pure Python Turnstile/Collector VM，Does not start Chrome。

    fp: Optional matching fingerprint dict（chatgpt.choose_fp），and HTTP Session Alignment。
    """
    log = logger or (lambda _m: None)
    try:
        from . import sentinel_pure_vm as pure
    except Exception as e:
        return {"ok": False, "mode": "pure-vm", "error": f"import sentinel_pure_vm: {e}"}

    try:
        ua = None
        screen = None
        languages = None
        hw = None
        if isinstance(fp, dict):
            ua = fp.get("ua")
            scr = fp.get("screen") or {}
            if scr.get("width") and scr.get("height"):
                screen = f"{scr['width']}x{scr['height']}"
            languages = fp.get("languages")
            hw = fp.get("hardware_concurrency")
        gen = SentinelTokenGenerator(
            device_id=did, user_agent=ua, screen=screen,
            languages=languages, hardware_concurrency=hw,
        )
        request_p = gen.generate_requirements_token()
        # sentinel.openai.com：Automatically move env/Clash exit（It’s really connected to the mainland CF 403）
        challenge = fetch_sentinel_challenge(
            did, flow, None, request_p=request_p, fp=fp,
        )
        if not isinstance(challenge, dict):
            detail = _LAST_REQ_ERROR or "No response"
            return {
                "ok": False, "mode": "pure-vm",
                "error": f"/req fail or not JSON: {detail}",
            }

        cdp_path = (os.environ.get("OPENAI_SENTINEL_CDP_SNAPSHOT") or "").strip()
        cdp_snap = None
        if cdp_path and os.path.isfile(cdp_path):
            try:
                with open(cdp_path, "r", encoding="utf-8") as f:
                    cdp_snap = json.load(f)
                log(f"[pure] loaded CDP snapshot keys={list(cdp_snap)[:8]}")
            except Exception as e:
                log(f"[pure] CDP snapshot load fail: {e}")

        packed = pure.build_pure_envelopes(
            challenge, request_p,
            device_id=did, flow=flow,
            user_agent=gen.user_agent,
            cdp_snapshot=cdp_snap,
            fp=fp if isinstance(fp, dict) else None,
        )
        st, so = packed.get("sentinel_token"), packed.get("so_token")
        v = _validate_envelope(st, so)
        need_so = flow in _BROWSER_REQUIRED_FLOWS
        morph_pass = v.get("t_morph_ok") and (v.get("so_morph_ok") if need_so else True)
        ok = bool(st) and v["t_ok"] and (not need_so or v["so_ok"]) and morph_pass
        if ok:
            log(
                f"[pure] ok t_len={v.get('t_len')} so_len={v.get('so_field_len')} "
                f"steps_t={packed.get('steps_t')} steps_so="
                f"{packed.get('steps_collector')}+{packed.get('steps_snapshot')}"
            )
        else:
            log(
                f"[pure] fail t_ok={v.get('t_ok')} so_ok={v.get('so_ok')} "
                f"t_len={v.get('t_len')} so_len={v.get('so_field_len')} "
                f"t_morph={v.get('t_morph_ok')} so_morph={v.get('so_morph_ok')} "
                f"err={packed.get('error')}"
            )
        return {
            "ok": ok,
            "mode": "pure-vm",
            "sentinel_token": st,
            "so_token": so,
            "sdk_version": SENTINEL_VERSION,
            "observer_wait_ms": 0,
            "error": None if ok else (
                packed.get("error")
                or f"pure-vm Insufficient form t_len={v.get('t_len')} so_len={v.get('so_field_len')}"
            ),
            **v,
            "steps_t": packed.get("steps_t"),
            "steps_collector": packed.get("steps_collector"),
            "steps_snapshot": packed.get("steps_snapshot"),
        }
    except Exception as e:
        return {
            "ok": False, "mode": "pure-vm",
            "sentinel_token": None, "so_token": None,
            "error": f"{type(e).__name__}: {e}",
        }


def sentinel_for(
    flow: str,
    proxy: Optional[str] = None,
    did: Optional[str] = None,
    fp: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """generated for a step Sentinel envelope。did Must be passed in（=oai-did）。

    oauth_create_account / username_password_create：
      - default pure（sentinel_pure_vm：Turnstile + collector event sampling + snapshot）
      - OPENAI_SENTINEL_MODE=browser|node|auto Can be changed；auto = pure→browser→node
      - morphological access control t≥1150 / so≥460；No rollback「none so fake envelope」
    fp: Optional matching fingerprint（chatgpt.choose_fp），make pure-vm and HTTP head/TLS same set。
    """
    if not did:
        return {"ok": False, "mode": "none", "sentinel_token": None,
                "so_token": None, "oai_did": None, "cf_turnstile_response": None,
                "sdk_version": SENTINEL_VERSION, "so_present": False,
                "sentinel_len": 0, "so_len": 0,
                "observer_wait_ms": OBSERVER_WAIT_MS,
                "error": "Lack did(oai-did)，Unable to bind device"}

    logs = []
    _log = lambda m: logs.append(m)

    # ── create_account：real t + so（priority pure VM，Can be rolled back browser/node）──
    if flow in _BROWSER_REQUIRED_FLOWS:
        mode = _sentinel_mode()
        pure_r: Dict[str, Any] = {}
        node_r: Dict[str, Any] = {}
        br: Dict[str, Any] = {}

        def _pack_ok(src: Dict[str, Any], mode_name: str) -> Dict[str, Any]:
            st, so = src.get("sentinel_token"), src.get("so_token")
            return {
                "ok": True, "mode": mode_name,
                "sentinel_token": st, "so_token": so,
                "oai_did": did, "cf_turnstile_response": None,
                "sdk_version": src.get("sdk_version") or SENTINEL_VERSION,
                "so_present": bool(so),
                "sentinel_len": len(st or ""), "so_len": len(so or ""),
                "observer_wait_ms": src.get("observer_wait_ms", OBSERVER_WAIT_MS),
                "t_ok": src.get("t_ok"), "so_ok": src.get("so_ok"),
                "t_len": src.get("t_len"), "so_field_len": src.get("so_field_len"),
                "t_morph_ok": src.get("t_morph_ok"), "so_morph_ok": src.get("so_morph_ok"),
                "error": None,
            }

        # 1) pure-vm（default / auto priority）— none Chrome；incoming fp Matching alignment
        if mode in ("pure", "auto"):
            pure_r = _pure_vm_tokens(flow, did, logger=_log, fp=fp)
            if pure_r.get("ok") and pure_r.get("sentinel_token") and pure_r.get("so_token"):
                return _pack_ok(pure_r, "pure-vm")

        # 2) browser（explicit browser，or auto exist pure after failure）
        if mode in ("browser", "auto"):
            br = _browser_sdk_tokens(flow, did, logger=_log)
            if br.get("ok") and br.get("sentinel_token") and br.get("so_token"):
                return _pack_ok(br, "browser")

        # 3) node（only mode=node or auto final rollback）
        if mode in ("node", "auto"):
            node_r = _node_sdk_tokens(flow, did, logger=_log)
            if node_r.get("ok") and node_r.get("sentinel_token") and node_r.get("so_token"):
                if mode == "node":
                    _log("WARN: OPENAI_SENTINEL_MODE=node — fake DOM t/so May be rejected by the server")
                return _pack_ok(node_r, node_r.get("mode") or "node-sdk")

        # 4) fail
        reason_parts = [f"sentinel_mode={mode}"]
        if pure_r.get("error"):
            reason_parts.append(f"pure: {pure_r['error']}")
        if br.get("error"):
            reason_parts.append(f"browser: {br['error']}")
        if node_r.get("error"):
            reason_parts.append(f"node: {node_r['error']}")
        if logs:
            reason_parts.append(" | ".join(logs[-3:]))
        st_fb = (pure_r.get("sentinel_token") or br.get("sentinel_token")
                 or node_r.get("sentinel_token"))
        so_fb = (pure_r.get("so_token") or br.get("so_token") or node_r.get("so_token"))
        return {
            "ok": False, "mode": "sdk-failed",
            "sentinel_token": st_fb,
            "so_token": so_fb,
            "oai_did": did, "cf_turnstile_response": None,
            "sdk_version": SENTINEL_VERSION, "so_present": bool(so_fb),
            "sentinel_len": len(st_fb or ""),
            "so_len": len(so_fb or ""),
            "observer_wait_ms": OBSERVER_WAIT_MS,
            "error": "oauth_create_account Need to be real t+so（pure-vm/browser/node None of them passed the form access control）；"
                     + ("; ".join(reason_parts) or "all modes failed"),
        }

    # ── remaining steps：pure Python ──
    _T_MODE = {"authorize_continue": "dx", "username_password_create": "empty"}
    envelope = build_sentinel_token(did, flow, None, t_mode=_T_MODE.get(flow, "empty"))
    if not envelope:
        return {"ok": False, "mode": "python", "sentinel_token": None,
                "so_token": None, "oai_did": did, "cf_turnstile_response": None,
                "sdk_version": SENTINEL_VERSION, "so_present": False,
                "sentinel_len": 0, "so_len": 0,
                "observer_wait_ms": 0,
                "error": "build_sentinel_token Return empty（/req failed or token Missing）"}
    return {"ok": True, "mode": "python", "sentinel_token": envelope,
            "so_token": None, "oai_did": did, "cf_turnstile_response": None,
            "sdk_version": SENTINEL_VERSION, "so_present": False,
            "sentinel_len": len(envelope), "so_len": 0,
            "observer_wait_ms": 0, "error": None}


def close_browser():
    """Close browser SDK Example（Called after the process exits or registration is completed）。"""
    try:
        from . import sentinel_browser as _sb
        _sb.close_all_browsers()
    except Exception:
        pass


if __name__ == "__main__":
    import sys
    p = sys.argv[1] if len(sys.argv) > 1 else "oauth_create_account"
    did_arg = sys.argv[2] if len(sys.argv) > 2 else str(uuid.uuid4())
    m = sentinel_for(p, proxy=None, did=did_arg)
    print(json.dumps({k: v for k, v in m.items()
                     if k not in ("sentinel_token", "so_token", "cf_turnstile_response")},
                    ensure_ascii=False, indent=2))
    close_browser()
