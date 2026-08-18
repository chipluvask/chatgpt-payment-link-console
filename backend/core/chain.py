"""asynchronous 7 segment link engine：$0 ChatGPT Plus -> PayPal BA Approve lift chain。

Link order fixed: checkout -> init -> [update amount guard] -> provider(PM+confirm)
              -> approve -> poll -> resolve

Three conditions for success determination：
1. init.invoice.amount_due == 0
2. redirect match ^https://pm-redirects\.stripe\.com/authorize/
3. final URL match ^https://www\.paypal\.com/agreements/approve\?ba_token=

dual mode：
- mock: Simulate the time consumption and success or failure of each stage，No internet required/acting/reality Token，For front-end display
- live: pass ThreadPoolExecutor Package curl_cffi Synchronous call，Execute real HTTP ask

curl_cffi use impersonate="chrome" conduct TLS Fingerprint camouflage。
"""
from __future__ import annotations

import asyncio
import json
import random
import re
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Optional

from .billing import billing_for, billing_currency, CHECKOUT_MATRIX, PAYPAL_BLOCKED
from .config import settings
from .proxy_pool import proxy_pool
from .token_store import token_store
from .branch_profile import branch_profile
from .geo_probe import probe_country as _geo_probe_country, bind_settings as _geo_bind_settings
from .link_helpers import (
    find_submission_attempt,
    is_paypal_ba_approve_url,
    extract_redirect_url,
    extract_qr_artifacts,
    follow_gateway_redirect,
    is_scannable_artifact,
    setup_intent_redirect,
    stripe_confirm_error_diagnostics,
)

_geo_bind_settings(settings)

# =============================================================================
# Constants and Regularities
# =============================================================================
STRIPE_INIT_VERSION = settings.stripe.get(
    "init_version",
    "2025-03-31.basil; checkout_server_update_beta=v1; checkout_manual_approval_preview=v1",
)
STRIPE_RUNTIME_VERSION = settings.stripe.get("runtime_version", "6f8494a281")
USER_AGENT = settings.tls.get(
    "user_agent",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36",
)
CURL_IMPERSONATE = settings.tls.get("impersonate", "chrome")

# fake chain/True chain determination rule
RE_PM_AUTHORIZE = re.compile(r"^https://pm-redirects\.stripe\.com/authorize/")
RE_PAYPAL_BA = re.compile(r"^https://www\.paypal\.com/agreements/approve\?ba_token=[A-Za-z0-9-]+$")
RE_PAYPAL_BA_SEARCH = re.compile(r"https://www\.paypal\.com/agreements/approve\?ba_token=[A-Za-z0-9-]+")

# 7 Show all segments: checkout -> init -> update -> provider -> approve -> poll -> resolve
DISPLAY_STAGES = ["checkout", "init", "update", "provider", "approve", "poll", "resolve"]
ALL_STAGES = ["checkout", "init", "update", "provider", "approve", "poll", "resolve"]

# Failure reason code (14 kind)
REASON_CODES = {
    "checkout_failed": "checkout Segment failed",
    "init_failed": "init Segment failed",
    "non_zero_amount": "The amount is not 0 (guard interception)",
    "paypal_unsupported": "current checkout Not supported paypal",
    "provider_failed": "provider Segment failed (PM/confirm)",
    "pm_creation_failed": "payment_method Creation failed",
    "confirm_failed": "confirm Segment failed",
    "approve_failed": "approve Segment failed",
    "approve_blocked": "approve quilt ChatGPT Risk control rejection (result=blocked)",
    "no_redirect": "Not obtained pm-redirects Jump",
    "poll_timeout": "poll Poll timeout",
    "resolve_failed": "resolve Parsing failed",
    "network_error": "network error",
    "tls_error": "TLS Fingerprint error",
    "proxy_error": "proxy error",
}

# Event callback type: async (event_dict) -> None
Emitter = Callable[[dict[str, Any]], Awaitable[None]]


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


# =============================================================================
# curl_cffi encapsulation (Optional: downgrade when missing mock)
# =============================================================================
try:
    from curl_cffi import requests as _curl  # type: ignore
    _HAS_CURL = True
except Exception:  # pragma: no cover
    _curl = None
    _HAS_CURL = False


def make_session(proxy: str):
    """create curl_cffi Session (chrome TLS fingerprint)。"""
    s = _curl.Session(impersonate=CURL_IMPERSONATE)
    s.headers.update({"User-Agent": USER_AGENT, "Accept-Language": "en-US,en;q=0.9"})
    if proxy:
        s.proxies = {"http": proxy, "https": proxy}
    return s


def _req(session, method: str, url: str, **kw):
    """bring TLS Retry on failure(close verify)request。"""
    verify = kw.pop("verify", True)
    attempts = [verify]
    if verify and url.startswith("https://"):
        attempts.append(False)
    last = None
    for v in attempts:
        try:
            return session.request(method, url, verify=v, **kw)
        except Exception as exc:
            last = exc
            low = f"{type(exc).__name__}:{exc}".lower()
            if v and any(m in low for m in ("certificate", "ssl", "curl: (60)")):
                continue
            raise
    if last:
        raise last
    raise RuntimeError("request_failed")


def chatgpt_session(proxy: str, access_token: str, session_token: str = "",
                    device_id: str = ""):
    s = make_session(proxy)
    device_id = str(device_id or "").strip() or str(uuid.uuid4())
    cookie = [f"oai-did={device_id}"]
    if session_token:
        cookie += [f"__Secure-next-auth.session-token={session_token}",
                   f"next-auth.session-token={session_token}"]
    s.headers.update({
        "Authorization": f"Bearer {access_token}",
        "Accept": "*/*", "Content-Type": "application/json",
        "Origin": "https://chatgpt.com", "Referer": "https://chatgpt.com/",
        "oai-device-id": device_id, "oai-language": "en-US",
        "Cookie": "; ".join(cookie),
    })
    return s


# =============================================================================
# reality HTTP Link segments (control original chain.py, Asynchronous execution via thread pool)
# =============================================================================
def _checkout_detail(raw) -> str:
    if not isinstance(raw, dict):
        return ""
    for k in ("detail", "message", "error"):
        v = raw.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
        if isinstance(v, dict) and v.get("message"):
            return str(v["message"]).strip()
    return ""


def stage_checkout_live(proxy, access_token, session_token, country, currency, branch="paypal",
                        promo_inline=False, ui_mode="hosted", sentinel_headers=None,
                        cookie_jar=None, device_id: str = ""):
    from .branch_profile import branch_profile

    prof = branch_profile(branch)
    s = chatgpt_session(proxy, access_token, session_token)
    if device_id:
        try:
            from . import oaics_proto as _op
            s.headers["Cookie"] = _op._cookie_header(device_id, session_token, cookie_jar)
        except Exception:
            pass
    path = "/backend-api/payments/checkout"
    payload = {
        "entry_point": "all_plans_pricing_modal", "plan_name": "chatgptplusplan",
        "billing_details": {"country": country, "currency": currency},
        "checkout_ui_mode": ui_mode,
    }
    if ui_mode == "custom":
        payload["check_card_proxy"] = True
    if promo_inline or prof.get("checkout_promo", True):
        payload["promo_campaign"] = {
            "promo_campaign_id": "plus-1-month-free", "is_coupon_from_query_param": False,
        }
    headers = {"Referer": "https://chatgpt.com/",
               "x-openai-target-path": path, "x-openai-target-route": path}
    if sentinel_headers:
        headers.update(sentinel_headers)
    # 2026-08-13: Alignment link-pp Order creation context — Same session warm-up page type CF cookie +
    # Complete browser header (OAI-Language billing country / client Version / oai-session-id / sec-ch-ua family)。
    # Discount qualifications when actual measurement is missing (0 Yuan) Not effective, Full price for order creation。
    if device_id:
        try:
            from . import oaics_proto as _op
            _op.warmup_chatgpt_page(s, country=country, device_id=device_id)
            headers = {
                **_op.common_headers(country=country, device_id=device_id,
                                     referer="https://chatgpt.com/", route=path),
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
                **headers,
            }
        except Exception:
            pass
    try:
        r = _req(s, "POST", "https://chatgpt.com" + path, json=payload,
                 headers=headers,
                 timeout=settings.branch_stage(branch, "checkout").timeout)
        if cookie_jar:
            try:
                from . import oaics_proto as _op
                _op._merge_set_cookie(cookie_jar, r)
            except Exception:
                pass
        try:
            d = r.json()
        except Exception:
            d = {"raw": (r.text or "")[:800]}
        d = d if isinstance(d, dict) else {}
        return {"status": r.status_code, "ok": 200 <= r.status_code < 300,
                "checkout_session_id": d.get("checkout_session_id") or d.get("id") or "",
                "publishable_key": d.get("publishable_key") or "",
                "processor_entity": d.get("processor_entity") or d.get("processorEntity") or "",
                "detail": _checkout_detail(d), "raw": d}
    finally:
        s.close()


def stage_update_live(proxy, access_token, session_token, cs, entity, bill, cur, branch="paypal"):
    """Double exit section 2：exist update_region Export to built checkout session injection promo (press 0 Yuan)。

    copy v1 Verified request body: POST /backend-api/payments/checkout/update
    """
    s = chatgpt_session(proxy, access_token, session_token)
    path = "/backend-api/payments/checkout/update"
    body = {
        "checkout_session_id": cs,
        "processor_entity": entity,
        "plan_name": "chatgptplusplan",
        "price_interval": "month",
        "seat_quantity": 1,
        "promo_campaign": {
            "promo_campaign_id": "plus-1-month-free",
            "is_coupon_from_query_param": False,
        },
    }
    if branch == "direct":
        # Direct card (ph_short): TR exit + US Bill pressure 0 (pay.153 formula)
        body["billing_details"] = {"country": "US", "currency": "USD"}
    else:
        body["billing_details"] = {"country": bill, "currency": cur}
    body["checkout_ui_mode"] = "hosted"
    try:
        r = _req(s, "POST", "https://chatgpt.com" + path, json=body,
                 headers={
                     "Referer": f"https://chatgpt.com/checkout/{entity}/{cs}",
                     "x-openai-target-path": path,
                     "x-openai-target-route": path,
                 },
                 timeout=settings.branch_stage(branch, "update").timeout)
        try:
            d = r.json()
        except Exception:
            d = {"raw": (r.text or "")[:800]}
        d = d if isinstance(d, dict) else {}
        return {"status": r.status_code, "ok": 200 <= r.status_code < 300, "body": d}
    finally:
        s.close()


def stage_init_live(proxy, pk, cs, branch="paypal"):
    s = make_session(proxy)
    body = {
        "browser_locale": "en-US", "browser_timezone": "Asia/Shanghai",
        "elements_session_client[client_betas][0]": "custom_checkout_server_updates_1",
        "elements_session_client[client_betas][1]": "custom_checkout_manual_approval_1",
        "elements_session_client[elements_init_source]": "custom_checkout",
        "elements_session_client[referrer_host]": "chatgpt.com",
        "elements_session_client[stripe_js_id]": str(uuid.uuid4()),
        "elements_session_client[locale]": "en",
        "elements_session_client[is_aggregation_expected]": "false",
        "elements_options_client[saved_payment_method][enable_save]": "never",
        "elements_options_client[saved_payment_method][enable_redisplay]": "never",
        "key": pk, "_stripe_version": STRIPE_INIT_VERSION,
    }
    try:
        r = _req(s, "POST", f"https://api.stripe.com/v1/payment_pages/{cs}/init", data=body,
                 headers={"Origin": "https://pay.openai.com", "Referer": "https://pay.openai.com/",
                          "Accept": "application/json",
                          "Content-Type": "application/x-www-form-urlencoded"},
                 timeout=settings.branch_stage(branch, "init").timeout)
        try:
            d = r.json()
        except Exception:
            d = {"raw": (r.text or "")[:500]}
        return {"status": r.status_code, "ok": r.status_code < 400, "init": d}
    finally:
        s.close()


def verify_zero(init: dict, require_zero: bool = True, channel_check: bool = True,
                channel: str = "paypal") -> dict:
    """amount guard + Payment channel verification。

    - channel_check=True: check init.payment_method_types Including target channels (paypal/momo/card/link)
      → Skip when there is no channel verification (like momo Linked init Return only card/momo)
    - require_zero=True: amount_due Must be 0 (fail-closed)
    """
    invoice = init.get("invoice") if isinstance(init.get("invoice"), dict) else {}
    if "amount_due" not in invoice:
        raise RuntimeError("Unable to confirm Stripe Amount due on invoice")
    ad = int(invoice.get("amount_due"))
    currency = str(init.get("currency") or invoice.get("currency") or "").lower()
    if channel_check:
        methods = init.get("payment_method_types")
        if not isinstance(methods, list) or channel not in {str(m).lower() for m in methods}:
            raise ChannelMismatch(channel, methods or [])
    if require_zero and ad != 0:
        raise NonZeroAmount(ad, currency)
    return {"amount_due": ad, "currency": currency, "zero_verified": (ad == 0)}


class ChannelMismatch(Exception):
    """Payment channel verification failed: init returned payment_method_types Does not include target channels。"""

    def __init__(self, channel: str, methods: list):
        super().__init__(f"init Does not include target channels {channel}: {methods}")
        self.channel = channel
        self.methods = methods


class NonZeroAmount(Exception):
    def __init__(self, amount: int, currency: str):
        super().__init__(f"amount_due={amount} {currency} No 0")
        self.amount = amount
        self.currency = currency


def _extract_amount_minor(payload: Any) -> int | None:
    """from checkout/update Response to recursively withdraw amount (Straight card chain: checkout_amount_minor compatible)。

    priority field: checkout_amount_minor / invoice.amount_due / total.taxInclusive / total.total
    / minorUnitsAmount dict / amount_due / amount_total。
    """
    if isinstance(payload, dict):
        for key in ("checkout_amount_minor", "amount_due", "amountDue", "amount_total", "amountTotal"):
            v = payload.get(key)
            if isinstance(v, int):
                return v
            if isinstance(v, str) and v.strip().lstrip("-").isdigit():
                return int(v.strip())
        # LPM non-pressure0link: The server's real-time payable amount is total_summary.due Subject to (tax included/exchange rate recalculation)
        total_summary = payload.get("total_summary")
        if isinstance(total_summary, dict) and total_summary.get("due") is not None:
            tv = total_summary.get("due")
            if isinstance(tv, int):
                return tv
            if isinstance(tv, str) and tv.strip().lstrip("-").isdigit():
                return int(tv.strip())
        invoice = payload.get("invoice")
        if isinstance(invoice, dict) and isinstance(invoice.get("amount_due"), int):
            return int(invoice["amount_due"])
        # minorUnitsAmount dict: {minorUnitsAmount: int}
        if "minorUnitsAmount" in payload and isinstance(payload.get("minorUnitsAmount"), int):
            return int(payload["minorUnitsAmount"])
        if "minor_units_amount" in payload and isinstance(payload.get("minor_units_amount"), int):
            return int(payload["minor_units_amount"])
        # total structure first: taxInclusive > total > subtotal
        total = payload.get("total")
        if isinstance(total, dict):
            for k in ("taxInclusive", "total", "due"):
                tv = total.get(k)
                if isinstance(tv, dict) and isinstance(tv.get("minorUnitsAmount"), int):
                    return int(tv["minorUnitsAmount"])
                if isinstance(tv, int):
                    return tv
        for v in payload.values():
            r = _extract_amount_minor(v)
            if r is not None:
                return r
    elif isinstance(payload, list):
        for v in payload:
            r = _extract_amount_minor(v)
            if r is not None:
                return r
    return None


def build_ctx(init: dict) -> dict:
    ctx = {"stripe_js_id": str(uuid.uuid4()),
           "elements_session_id": f"elements_session_{uuid.uuid4().hex[:11]}"}
    config_id = str(init.get("config_id") or "").strip() if isinstance(init, dict) else ""
    ctx["config_id"] = config_id
    ctx["elements_session_config_id"] = config_id or str(uuid.uuid4())
    return ctx


def extract_redirect(payload: Any) -> str:
    if isinstance(payload, dict):
        na = payload.get("next_action")
        if isinstance(na, dict):
            if na.get("type") == "redirect_to_url":
                ru = na.get("redirect_to_url")
                if isinstance(ru, dict) and ru.get("url"):
                    return str(ru["url"]).strip()
            if na.get("type") == "upi_handle_redirect_or_display_qr_code":
                # UPI: hosted_instructions_url As a navigation target after confirmation
                hi = na.get("upi_handle_redirect_or_display_qr_code")
                if isinstance(hi, dict) and isinstance(hi.get("hosted_instructions_url"), str):
                    return str(hi["hosted_instructions_url"]).strip()
        for k in ("setup_intent", "payment_intent"):
            n = payload.get(k)
            if isinstance(n, dict):
                found = extract_redirect(n)
                if found:
                    return found
                if isinstance(n.get("stripe_hosted_url"), str) and n["stripe_hosted_url"].startswith("http"):
                    return n["stripe_hosted_url"].strip()
        m = RE_PAYPAL_BA_SEARCH.search(json.dumps(payload, ensure_ascii=False))
        if m:
            return m.group(0)
        m2 = re.search(r"https://pm-redirects\.stripe\.com/authorize/[^\"'\s<>]+",
                       json.dumps(payload, ensure_ascii=False))
        if m2:
            return m2.group(0)
    return ""


def stage_payment_method_live(proxy, pk, cs, init, country, ctx, branch="paypal"):
    from .branch_profile import branch_profile

    prof = branch_profile(branch)
    b = billing_for(country)
    body = {
        "billing_details[name]": b["name"],
        "billing_details[email]": f"{re.sub(r'[^a-z0-9]+', '.', b['name'].lower()).strip('.')}.{uuid.uuid4().hex[:6]}@example.com",
        "billing_details[address][country]": b["country"],
        "billing_details[address][line1]": b["line1"],
        "billing_details[address][city]": b["city"],
        "billing_details[address][state]": b["state"],
        "billing_details[address][postal_code]": b["postal_code"],
        "type": prof["pm_type"],
        "payment_user_agent": f"stripe.js/{STRIPE_RUNTIME_VERSION}; stripe-js-v3/{STRIPE_RUNTIME_VERSION}; payment-element; deferred-intent",
        "referrer": prof["referrer"],
        "time_on_page": str(25000 + (uuid.uuid4().int % 30000)),
        "client_attribution_metadata[checkout_session_id]": cs,
        "client_attribution_metadata[client_session_id]": ctx["stripe_js_id"],
        "client_attribution_metadata[elements_session_id]": ctx["elements_session_id"],
        "client_attribution_metadata[merchant_integration_source]": "elements",
        "client_attribution_metadata[merchant_integration_subtype]": "payment-element",
        "client_attribution_metadata[merchant_integration_version]": "2021",
        "client_attribution_metadata[payment_intent_creation_flow]": "deferred",
        "client_attribution_metadata[payment_method_selection_flow]": "automatic",
        "client_attribution_metadata[merchant_integration_additional_elements][0]": "payment",
        "client_attribution_metadata[merchant_integration_additional_elements][1]": "address",
        "key": pk, "_stripe_version": STRIPE_INIT_VERSION,
    }
    # config_id only from init response; oaics Session None init -> Empty string will trigger Stripe 400
    # parameter_invalid_empty, must skip
    if ctx.get("config_id"):
        body["client_attribution_metadata[checkout_config_id]"] = ctx["config_id"]
        body["client_attribution_metadata[elements_session_config_id]"] = (
            ctx.get("elements_session_config_id") or ctx["config_id"])
    body.update(prof["pm_extra"])
    s = make_session(proxy)
    try:
        r = _req(s, "POST", "https://api.stripe.com/v1/payment_methods", data=body,
                 timeout=settings.branch_stage(branch, "provider").timeout)
        d = r.json() if r.text else {}
        pm = str(d.get("id") or "")
        if not pm.startswith("pm_"):
            raise RuntimeError("payment_method Creation failed")
        return pm
    finally:
        s.close()


def stage_amount_live(proxy, pk, cs, timeout=10):
    """GET payment_pages Get the real-time invoice amount from the server (General ledger/cope)。

    LPM channel (bizum/gopay/kakao/naver/upi) non-pressure0link: The server may include tax/exchange rate
    Recalculate the amount payable (like into the invoice sooner of upcoming_invoice_mismatch),
    confirm of expected_amount Must be based on server real-time value, rather than init Snapshot。
    """
    s = make_session(proxy)
    try:
        r = _req(s, "GET", f"https://api.stripe.com/v1/payment_pages/{cs}",
                 headers={"Origin": "https://pay.openai.com", "Accept": "application/json"},
                 timeout=timeout)
        if r.status_code != 200:
            return None
        d = r.json() if r.text else {}
        inv = d.get("invoice") if isinstance(d, dict) else None
        if isinstance(inv, dict) and isinstance(inv.get("amount_due"), int):
            return int(inv["amount_due"])
        ts = d.get("total_summary") if isinstance(d, dict) else None
        if isinstance(ts, dict) and isinstance(ts.get("total"), int):
            return int(ts["total"])
        return None
    finally:
        s.close()


def stage_confirm_live(proxy, pk, cs, init, pm, ctx, country, entity, require_zero=True,
                       channel_check=True, channel="paypal", branch="paypal"):
    from .branch_profile import branch_profile

    gate = verify_zero(init, require_zero=require_zero, channel_check=channel_check, channel=channel)
    # LPM non-pressure0link: expected_amount Real-time payment amount using server (tax included/exchange rate recalculation), otherwise
    # checkout_upcoming_invoice_mismatch (bizum 2300, gopay px, kakao/naver 29,
    # upi 1999 The actual measurements are all based on the server total_summary.total Subject to)
    if not require_zero:
        live_amt = stage_amount_live(proxy, pk, cs)
        if isinstance(live_amt, int) and live_amt >= 0:
            gate = {**gate, "amount_due": live_amt}
    hosted = str(init.get("url") or "")
    if hosted:
        return_url = hosted
    else:
        ent = entity or ("openai_llc" if country == "US" else "openai_ie")
        success = f"https://chatgpt.com/checkout/verify?stripe_session_id={cs}&processor_entity={ent}&plan_type=plus"
        return_url = (f"https://checkout.stripe.com/c/pay/{cs}?returned_from_redirect=true"
                      f"&ui_mode=custom&return_url={success}")
    body = {
        "guid": uuid.uuid4().hex, "muid": uuid.uuid4().hex, "sid": uuid.uuid4().hex,
        "payment_method": pm, "init_checksum": str(init.get("init_checksum") or ""),
        "version": STRIPE_RUNTIME_VERSION, "expected_amount": str(gate["amount_due"]),
        "expected_payment_method_type": branch_profile(channel or branch)["confirm_type"],
        "return_url": return_url,
        "elements_session_client[session_id]": ctx["elements_session_id"],
        "elements_session_client[locale]": "en",
        "elements_session_client[referrer_host]": "chatgpt.com",
        "elements_session_client[is_aggregation_expected]": "false",
        "elements_session_client[elements_init_source]": "custom_checkout",
        "elements_session_client[stripe_js_id]": ctx["stripe_js_id"],
        "elements_session_client[client_betas][0]": "custom_checkout_server_updates_1",
        "elements_session_client[client_betas][1]": "custom_checkout_manual_approval_1",
        "elements_options_client[saved_payment_method][enable_save]": "never",
        "elements_options_client[saved_payment_method][enable_redisplay]": "never",
        "client_attribution_metadata[client_session_id]": ctx["stripe_js_id"],
        "client_attribution_metadata[checkout_session_id]": cs,
        "client_attribution_metadata[checkout_config_id]": ctx.get("config_id") or "",
        "client_attribution_metadata[elements_session_id]": ctx["elements_session_id"],
        "client_attribution_metadata[elements_session_config_id]": ctx.get("elements_session_config_id") or "",
        "client_attribution_metadata[merchant_integration_source]": "checkout",
        "client_attribution_metadata[merchant_integration_subtype]": "payment-element",
        "client_attribution_metadata[merchant_integration_version]": "custom",
        "client_attribution_metadata[payment_intent_creation_flow]": "deferred",
        "client_attribution_metadata[payment_method_selection_flow]": "automatic",
        "client_attribution_metadata[merchant_integration_additional_elements][0]": "payment",
        "client_attribution_metadata[merchant_integration_additional_elements][1]": "address",
        "consent[terms_of_service]": "accepted",
        "key": pk, "_stripe_version": STRIPE_INIT_VERSION,
    }
    s = make_session(proxy)
    try:
        url = f"https://api.stripe.com/v1/payment_pages/{cs}/confirm"
        hdrs = {"Origin": "https://pay.openai.com", "Referer": return_url.split("#", 1)[0],
                "Accept": "application/json",
                "Content-Type": "application/x-www-form-urlencoded"}
        timeout = settings.branch_stage(branch, "provider").timeout
        r = _req(s, "POST", url, data=body, headers=hdrs, timeout=timeout)
        if r.status_code == 400 and "terms of service" in (r.text or "").lower():
            r = _req(s, "POST", url, data=body, headers=hdrs, timeout=timeout)
        if r.status_code == 400 and "checkout_amount_mismatch" in (r.text or ""):
            new_init = stage_init_live(proxy, pk, cs, branch).get("init") or {}
            if new_init.get("init_checksum"):
                body["init_checksum"] = str(new_init.get("init_checksum"))
            try:
                ngate = verify_zero(new_init, require_zero=require_zero,
                                    channel_check=channel_check, channel=channel)
                body["expected_amount"] = str(ngate["amount_due"])
            except Exception:
                pass
            r = _req(s, "POST", url, data=body, headers=hdrs, timeout=timeout)
        if r.status_code in {400, 429, 500, 502, 503}:
            time.sleep(2)
            r = _req(s, "POST", url, data=body, headers=hdrs, timeout=timeout)
        d = r.json() if r.text else {}
        redirect = extract_redirect(d) or extract_redirect_url(d)
        state = ""
        sub = find_submission_attempt(d)
        if isinstance(sub, dict):
            state = str(sub.get("state") or "")
        diagnostics = ""
        if r.status_code >= 400:
            diagnostics = stripe_confirm_error_diagnostics(r, cs, pm, init)
        return {"redirect": redirect, "confirm_state": state, "diagnostics": diagnostics,
                "artifacts": extract_qr_artifacts(d)}
    finally:
        s.close()


def stage_ctoken_oaics_live(proxy, pk, cs, billing_country, elements=None, p1_token="",
                            customer="", name="", timeout=30):
    """oaics Conversational confirmation token create (Browser Empirical Protocol, 08-12 CDP Fetch Capture packets)。

    Stripe /v1/confirmation_tokens + payment_method_data inline paypal complete data:
    mandate_data + client_context(customer) + attribution + Optional radar hcaptcha P1。
    ctoken Need to be in elements/sessions initialization (cuss_secret) Created after, for confirm use。
    return {"status", "ctoken", "body"}
    """
    from .billing import billing_for
    b = billing_for(billing_country or "US")
    sid = uuid.uuid4().hex
    esid = elements.get("session_id") if isinstance(elements, dict) else None
    esid = esid or f"elements_session_{uuid.uuid4().hex[:12]}"
    ecfg = elements.get("config_id") if isinstance(elements, dict) else None
    ecfg = ecfg or sid
    body = {
        "payment_method_data[type]": "paypal",
        "payment_method_data[billing_details][name]": name or b["name"],
        "payment_method_data[billing_details][address][line1]": b["line1"],
        "payment_method_data[billing_details][address][city]": b["city"],
        "payment_method_data[billing_details][address][country]": b["country"],
        "payment_method_data[billing_details][address][postal_code]": b["postal_code"],
        "payment_method_data[billing_details][address][state]": b["state"],
        "payment_method_data[billing_details][phone]": "",
        "payment_method_data[payment_user_agent]": f"stripe.js/{STRIPE_RUNTIME_VERSION}; stripe-js-v3/{STRIPE_RUNTIME_VERSION}; payment-element; deferred-intent",
        "payment_method_data[referrer]": "https://chatgpt.com",
        "payment_method_data[time_on_page]": "59028",
        "payment_method_data[client_attribution_metadata][client_session_id]": sid,
        "payment_method_data[client_attribution_metadata][merchant_integration_source]": "elements",
        "payment_method_data[client_attribution_metadata][merchant_integration_subtype]": "payment-element",
        "payment_method_data[client_attribution_metadata][merchant_integration_version]": "2021",
        "payment_method_data[client_attribution_metadata][payment_intent_creation_flow]": "deferred",
        "payment_method_data[client_attribution_metadata][payment_method_selection_flow]": "merchant_specified",
        "payment_method_data[client_attribution_metadata][elements_session_id]": esid,
        "payment_method_data[client_attribution_metadata][elements_session_config_id]": ecfg,
        "payment_method_data[guid]": uuid.uuid4().hex,
        "payment_method_data[muid]": uuid.uuid4().hex,
        "payment_method_data[sid]": uuid.uuid4().hex,
        "setup_future_usage": "off_session",
        "mandate_data[customer_acceptance][type]": "online",
        "mandate_data[customer_acceptance][online][infer_from_client]": "true",
        "client_context[currency]": "usd",
        "client_context[mode]": "subscription",
        "client_context[payment_method_types][0]": "paypal",
        "client_context[payment_method_types][1]": "link",
        "client_context[payment_method_types][2]": "card",
        "client_attribution_metadata[client_session_id]": sid,
        "client_attribution_metadata[merchant_integration_source]": "elements",
        "client_attribution_metadata[merchant_integration_subtype]": "payment-element",
        "client_attribution_metadata[merchant_integration_version]": "2021",
        "client_attribution_metadata[payment_intent_creation_flow]": "deferred",
        "client_attribution_metadata[payment_method_selection_flow]": "merchant_specified",
        "client_attribution_metadata[elements_session_id]": esid,
        "client_attribution_metadata[elements_session_config_id]": ecfg,
        "set_as_default_payment_method": "false",
        "key": pk,
        "_stripe_version": STRIPE_INIT_VERSION,
    }
    if p1_token:
        body["payment_method_data[radar_options][hcaptcha_token]"] = p1_token
    if customer:
        body["client_context[customer]"] = customer
    s = make_session(proxy)
    try:
        r = _req(s, "POST", "https://api.stripe.com/v1/confirmation_tokens", data=body,
                 headers={"Referer": "https://js.stripe.com/", "Accept": "application/json",
                          "Content-Type": "application/x-www-form-urlencoded"},
                 timeout=max(15, timeout))
        d = r.json() if r.text else {}
        d = d if isinstance(d, dict) else {}
        ct = str(d.get("id") or "")
        return {"status": r.status_code, "ctoken": ct, "body": d}
    finally:
        s.close()


def stage_confirm_oaics_live(proxy, access_token, session_token, cs, entity, ctoken,
                             billing_country="US", branch="paypal", timeout=30,
                             attestation="", extra_headers=None):
    """oaics confirm (Browser Empirical Protocol, 08-12 Fetch Capture packets):

    POST /backend-api/payments/checkout/confirm
    body: {"checkout_session_id", "confirm_token": ctoken, "selected_payment_method_type": "paypal"}
    attestation for oai-web-deployment-attestation (Front-end deployment proof, ~1h efficient, Passable
    MIN_OAICS_ATTESTATION injection; When missing, the server enters strict verification., Known to trigger
    customer_tax_location_invalid Waiting for risk control)。
    return {redirect, confirm_state, status, detail}
    """
    s = chatgpt_session(proxy, access_token, session_token)
    path = "/backend-api/payments/checkout/confirm"
    body = {
        "checkout_session_id": cs,
        "confirm_token": ctoken,
        "selected_payment_method_type": "paypal",
    }
    hdrs = {"Referer": f"https://chatgpt.com/checkout/{entity}/{cs}",
            "x-openai-target-path": path, "x-openai-target-route": path}
    if attestation:
        hdrs["oai-web-deployment-attestation"] = attestation
        hdrs.setdefault("oai-language", "zh-CN")
    if extra_headers:
        hdrs.update(extra_headers)
    out = {"redirect": "", "confirm_state": "", "status": 0, "detail": ""}
    try:
        try:
            r = _req(s, "POST", "https://chatgpt.com" + path, json=body,
                     headers=hdrs, timeout=max(15, timeout))
        except Exception as e:
            out["detail"] = f"Request exception: {type(e).__name__}: {str(e)[:120]}"
            return out
        out["status"] = r.status_code
        try:
            d = r.json()
        except Exception:
            d = {"raw": (r.text or "")[:500]}
        d = d if isinstance(d, dict) else {}
        out["detail"] = str(d.get("detail") or d.get("message") or "")[:200]
        if r.status_code < 400:
            redirect = extract_redirect(d) or extract_redirect_url(d)
            state = ""
            sub = find_submission_attempt(d)
            if isinstance(sub, dict):
                state = str(sub.get("state") or "")
            out["redirect"] = redirect
            out["confirm_state"] = state
            return out
        return out
    finally:
        s.close()


def stage_approve_live(proxy, access_token, session_token, cs, entity, branch="paypal"):
    s = chatgpt_session(proxy, access_token, session_token)
    try:
        try:
            _req(s, "POST", "https://chatgpt.com/backend-api/sentinel/ping", json={},
                 headers={"x-openai-target-path": "/backend-api/sentinel/ping",
                          "x-openai-target-route": "/backend-api/sentinel/ping"}, timeout=4)
        except Exception:
            pass
        path = "/backend-api/payments/checkout/approve"
        payload = {"checkout_session_id": cs, "processor_entity": entity}
        last_result = ""
        d: dict = {}
        r = None
        for attempt in range(1, 4):
            if attempt > 1:
                time.sleep(3)
            r = _req(s, "POST", "https://chatgpt.com" + path, json=payload,
                     headers={"Referer": f"https://chatgpt.com/checkout/{entity}/{cs}",
                              "x-openai-target-path": path, "x-openai-target-route": path},
                     timeout=settings.branch_stage(branch, "approve").timeout)
            if r.status_code >= 400:
                break
            d = r.json() if r.text else {}
            last_result = str(d.get("result") or "") if isinstance(d, dict) else ""
            if last_result == "approved" or (last_result and last_result != "blocked"):
                break
        ok = r is not None and r.status_code < 400 and last_result != "blocked"
        return {"ok": ok, "result": last_result,
                "redirect": extract_redirect(d) or extract_redirect_url(d)}
    finally:
        s.close()


def stage_poll_live(proxy, pk, cs, timeout=None, branch="paypal"):
    if timeout is None:
        timeout = settings.branch_stage(branch, "poll").timeout
    s = make_session(proxy)
    deadline = time.monotonic() + max(1.0, timeout)
    params = {
        "elements_session_client[client_betas][0]": "custom_checkout_server_updates_1",
        "elements_session_client[client_betas][1]": "custom_checkout_manual_approval_1",
        "elements_session_client[elements_init_source]": "custom_checkout",
        "elements_session_client[referrer_host]": "chatgpt.com",
        "elements_session_client[session_id]": f"elements_session_{uuid.uuid4().hex[:11]}",
        "elements_session_client[stripe_js_id]": str(uuid.uuid4()),
        "elements_session_client[locale]": "en",
        "elements_session_client[is_aggregation_expected]": "false",
        "elements_options_client[saved_payment_method][enable_save]": "never",
        "elements_options_client[saved_payment_method][enable_redisplay]": "never",
        "key": pk, "_stripe_version": STRIPE_INIT_VERSION,
    }
    hdrs = {"Origin": "https://pay.openai.com", "Referer": "https://pay.openai.com/",
            "Accept": "application/json"}
    try:
        interval = settings.branch_stage(branch, "poll").poll_interval
        while time.monotonic() < deadline:
            r = _req(s, "GET", f"https://api.stripe.com/v1/payment_pages/{cs}",
                     params=params, headers=hdrs, timeout=30)
            if r.status_code == 200:
                d = r.json() if r.text else {}
                url = extract_redirect(d) or extract_redirect_url(d)
                if url:
                    return {"redirect": url, "artifacts": extract_qr_artifacts(d)}
            time.sleep(interval)
        return ""
    finally:
        s.close()


def stage_resolve_live(proxy, intermediate, timeout=None, branch="paypal"):
    from .branch_profile import branch_profile

    prof = branch_profile(branch)
    success_re = prof["resolve_re"]
    search_re = prof["resolve_search_re"]
    if timeout is None:
        timeout = settings.branch_stage(branch, "resolve").timeout
    url = (intermediate or "").strip()
    if branch == "paypal" and is_paypal_ba_approve_url(url):
        return url
    if success_re and success_re.match(url):
        return url
    if not RE_PM_AUTHORIZE.match(url) and not (search_re and search_re.search(url)):
        return ""
    s = make_session(proxy)
    deadline = time.monotonic() + max(3.0, timeout)
    current = url
    seen: set[str] = set()
    try:
        from urllib.parse import urljoin
        while current and time.monotonic() < deadline and current not in seen:
            seen.add(current)
            remain = max(2.0, min(6.0, deadline - time.monotonic()))
            r = _req(s, "GET", current, timeout=remain, allow_redirects=False)
            loc = str(r.headers.get("Location") or r.headers.get("location") or "").strip()
            if branch == "paypal" and is_paypal_ba_approve_url(loc):
                return loc
            if success_re and success_re.match(loc):
                return loc
            if search_re:
                m = search_re.search(loc or "")
                if m:
                    return m.group(0)
                m2 = search_re.search(r.text or "")
                if m2:
                    return m2.group(0)
            if r.status_code in {301, 302, 303, 307, 308} and loc:
                current = urljoin(current, loc)
                continue
            break
        return ""
    finally:
        s.close()


def _oaics_poll_context(proxy, access_token, session_token, cs, entity, timeout=20):
    """oaics Polling alternative: GET OpenAI checkout context, Try to extract pm-redirects Link。

    oaics (custom_checkout_session) right Stripe payment_pages GET 404,
    from OpenAI end checkout context try to find paypal authorize Where to go。
    """
    s = chatgpt_session(proxy, access_token, session_token)
    try:
        path = f"/backend-api/payments/checkout/{entity}/{cs}"
        r = _req(s, "GET", "https://chatgpt.com" + path,
                 headers={"Referer": f"https://chatgpt.com/checkout/{entity}/{cs}",
                          "x-openai-target-path": path, "x-openai-target-route": path},
                 timeout=max(10, timeout))
        if r.status_code >= 400:
            return ""
        text = r.text or ""
        m = re.search(r"https://pm-redirects\.stripe\.com/authorize/[^\"'\s<>]+", text)
        if m:
            return m.group(0)
        m2 = re.search(r"https://www\.paypal\.com/agreements/approve\?ba_token=[A-Za-z0-9-]+", text)
        return m2.group(0) if m2 else ""
    finally:
        s.close()


# =============================================================================
# Country selection
# =============================================================================
def pick_countries(attempt_idx: int, branch: str = "paypal") -> dict[str, str]:
    """No. attempt_idx(0-based) on attempts，Which country to choose for each paragraph?。

    According to the independent seven-segment configuration of the chain branch, the country is obtained (Do not mix with each other)。
    - follow_checkout=True: remove update All segments outside follow checkout part (segment follow)
    - pair init: init Duan Zou init0(Take the exit) -> init1(Authenticity export) -> init_t(transition)

    Country selection rules:
    - countries for ["auto"] or empty → auto model: full amount ALL_COUNTRIES rotation (dynamic priority country + long tail)
    - countries for ["US"] Single value → Lock the country manually (override priority)
    """
    cfg = settings.branch(branch)
    st = lambda name: settings.branch_stage(branch, name)  # noqa: E731

    def _auto_pool() -> list[str]:
        from .billing import ALL_COUNTRIES
        return [c for c in ALL_COUNTRIES if c not in PAYPAL_BLOCKED] or ["US"]

    def _pick(name: str, countries: list[str]) -> str:
        lst = countries or []
        if not lst or lst == ["auto"]:
            lst = _auto_pool()
        offset = attempt_idx + (sum(ord(c) for c in name) % max(1, len(lst)))
        return lst[offset % len(lst)]

    co = st("checkout")
    countries_co = co.countries or ["auto"]
    checkout_cc = _pick("checkout", countries_co)
    # Currency follows billing country (US=USD / AU=AUD / Europe EUR)
    billing_cc = (cfg.billing_country or "auto").upper()
    if billing_cc in ("AUTO", ""):
        billing_cc = checkout_cc
    currency = billing_currency(billing_cc)
    pick: dict[str, str] = {
        "checkout": checkout_cc,
        "_billing": billing_cc,
        "_currency": currency,
    }

    follow = cfg.follow_checkout
    for stage in ("init", "update", "provider", "approve", "poll", "resolve"):
        if follow and stage != "update":
            pick[stage] = checkout_cc
        elif stage == "update":
            # update part: Export agent country configuration preference (TH priority, for injection promo)
            upd_list = st("update").countries or ["TH"]
            pick[stage] = upd_list[0] if upd_list and upd_list != ["auto"] else "TH"
        else:
            pick[stage] = _pick(stage, st(stage).countries)

    # pair init: cover init Section is three rounds (init0/init1/init_t priority list)
    if cfg.dual_init:
        pick["init0"] = _pick("init0", cfg.init0_ccs)
        pick["init1"] = _pick("init1", cfg.init1_ccs)
        pick["init_t"] = _pick("init_t", cfg.init_t_ccs or [pick["init1"]])
    return pick


def pick_oaics_countries(attempt_idx: int, branch: str = "paypal") -> dict[str, str]:
    """oaics fifth section (checkout/taxes/provider/confirm/resolve) Export country mapping (Follow the seven-segment configuration)。

    2026-08-13 change: oaics Subconfiguration is obsolete read-only (branches.<branch>.oaics No longer participates in link decisions),
    five-section country / billing country / The currency directly takes seven segments pick_countries The actual effective results of
    (follow_checkout / update First choice / rotation Wait for the seven paragraph rules to take effect):
        oaics checkout <- Seven sections checkout   (Jiandan export)
        oaics taxes    <- Seven sections update     (bill submission+0meta-check, correspond update press0 Responsibilities)
        oaics provider <- Seven sections provider   (payment provider)
        oaics confirm  <- Seven sections approve    (confirm/approve)
        oaics resolve  <- Seven sections resolve    (parse final URL)
        billing country/Currency    <- Seven sections billing_country / billing_currency
    """
    pick7 = pick_countries(attempt_idx, branch)
    return {
        "checkout": pick7["checkout"],
        "taxes": pick7["update"],
        "provider": pick7["provider"],
        "confirm": pick7["approve"],
        "resolve": pick7["resolve"],
        "_billing": pick7["_billing"],
        "_currency": pick7["_currency"],
    }


# =============================================================================
# Asynchronous link engine
# =============================================================================
class ChainResult:
    def __init__(self) -> None:
        self.success: bool = False
        self.paypal_approve_url: str = ""
        self.pm_authorize_url: str = ""
        self.amount_due: int = 0
        self.currency: str = ""
        self.country: str = ""
        self.billing_country: str = ""
        # Export real geography (Multi-source detection)
        self.actual_country: str = ""
        self.requested_country: str = ""
        self.exit_ip: str = ""
        self.geo_confidence: float = 0.0
        self.stage_geo: dict[str, dict] = {}  # Detection details for each section {stage: {country, ip, city, confidence, requested}}
        self.reason_code: str = ""
        self.reason_text: str = ""
        self.stage_reached: str = ""
        self.elapsed: float = 0.0
        self.ba_token: str = ""
        self.email: str = ""
        self.token_id: str = ""
        # unified outcome contract (protocol_payment.v1)
        self.link_type: str = ""
        self.artifacts: dict[str, Any] = {}  # qr_image_url/qr_png_url/qr_data/hosted_instructions_url/deep_link/pix_code
        self.retryable: bool = False
        self.error_stage: str = ""
        self.requires_reconciliation: bool = False
        self.side_effect_started: bool = False

    def to_protocol_result(self, payment_method: str = "") -> dict[str, Any]:
        """Convert to ProtocolResult contract dict (With desensitization)。"""
        from .link_helpers import ProtocolResult

        ok = self.success
        status = "completed" if ok else ("unknown" if self.requires_reconciliation else "failed")
        url = self.paypal_approve_url or self.pm_authorize_url
        pm = payment_method or (self.link_type or ("paypal" if "BA-" in (self.ba_token or "") else "unknown"))
        result = ProtocolResult(
            payment_method=pm,
            ok=ok,
            status=status,
            operation="extract_link",
            url=url,
            link_type=self.link_type or ("paypal_ba" if "BA-" in (self.ba_token or "") else ""),
            message=self.reason_text or "",
            error=self.reason_text or "",
            error_code=self.reason_code or "",
            error_stage=self.error_stage or self.stage_reached or "",
            retryable=bool(self.retryable),
            side_effect_started=bool(self.side_effect_started),
            requires_reconciliation=bool(self.requires_reconciliation),
            artifacts=dict(self.artifacts or {}),
        )
        return result.to_dict()


class AsyncChain:
    """Single asynchronous link。execute() Run complete 7 part，pass emitter Push events。"""

    def __init__(self, chain_id: str, token: dict[str, Any], attempt: int,
                 options: dict[str, Any], emitter: Emitter,
                 executor: Any | None = None) -> None:
        self.chain_id = chain_id
        self.token = token
        self.attempt = attempt
        self.options = options
        self.emit = emitter
        self.executor = executor
        self.branch_name = str(options.get("branch") or "paypal")
        self.branch_cfg = settings.branch(self.branch_name)
        self.pick = pick_countries(attempt - 1, self.branch_name)
        self.pick_oaics = pick_oaics_countries(attempt - 1, self.branch_name)
        self.access_token = token.get("access_token") or token.get("raw") or ""
        self.session_token = token.get("session_token") or ""
        self.email = token.get("email") or token.get("sub") or ""
        self.result = ChainResult()
        self.result.email = self.email
        self.result.token_id = token.get("id", "")
        self._cancelled = False
        self._stage_states: dict[str, dict] = {}
        self.oaics_mode: bool = False
        self._oaics_device_id: str = ""
        self._oaics_cookie_jar: dict[str, str] = {}
        # Detect shunt before lifting chain: Detected as oaics When forced to just walk oaics fifth section, Build a non- oaics Session failed directly, No downgrade
        self._oaics_only: bool = False
        # =====================================================================
        # 【Deprecated】S0 Independent session type detection segment (2026-08-14 Remove):
        #   Original process: execute Use at the beginning checkout part IP Additional order detection session type (oaics/cs_live),
        #   Then divide the traffic according to the detection results.。shortcoming: detection=Create an order one more time, trigger 429 And it is repeated with the link establishment order.。
        #   current process: Session type changed to S1 Dynamic determination of order creation results (Whatever you build, go away):
        #     oaics_  -> OAICS fifth section; cs_live_ -> Seven-segment main chain。
        #   The following fields are reserved for historical semantics only, no more S0 detection assignment (keep empty string):
        #   _detected_session / _probe_billing_cc / _probe_currency
        #   Front-end link monitoring list"explore"Column deleted synchronously。
        # =====================================================================
        self._detected_session: str = ""
        self._probe_billing_cc: str = ""
        self._probe_currency: str = ""
        self._stage_geo: dict[str, dict] = {}  # Each real exit detection record
        # Reuse in the same country: The latter part of the same country directly reuses the previous part. sticky session (same IP), No new draws IP
        self._proxy_by_country: dict[str, str] = {}  # country -> proxy_url
        self._geo_by_proxy: dict[str, dict] = {}    # proxy_url -> Detection results (same IP No repeated detection)

    def cancel(self) -> None:
        self._cancelled = True

    async def _emit(self, evt: dict[str, Any]) -> None:
        evt.setdefault("chain_id", self.chain_id)
        if self.oaics_mode and str(evt.get("type") or "").startswith("stage_"):
            evt.setdefault("link_mode", "oaics")
        await self.emit(evt)

    async def _run_in_executor(self, fn, *args, **kwargs):
        loop = asyncio.get_event_loop()
        if self.executor:
            return await loop.run_in_executor(self.executor, lambda: fn(*args, **kwargs))
        return await loop.run_in_executor(None, lambda: fn(*args, **kwargs))

    def _pick_proxy(self, stage: str, country: str | None = None) -> str:
        """Select a proxy for a certain link：live Selected via agent pool in mode 711/node/QG，mock Return empty。

        Reuse in the same country: The same country has already drawn an agent(sticky session)，Subsequent segments in the same country will directly reuse the same IP，
        Do not redraw new IP。
        exception: update Segments are independent IP exit(Form country and update IP separate countries)，
        press 0 injection promo Must use independent export IP，Therefore, the reuse cache is not used。
        """
        if settings.chain_mode != "live" or not _HAS_CURL:
            return ""
        key = (country or "").upper()
        if stage != "update" and key and key in self._proxy_by_country:
            return self._proxy_by_country[key]
        try:
            proxy_url = proxy_pool.pick_for_stage(stage, country)
        except Exception:
            return ""
        if stage != "update" and key and proxy_url:
            self._proxy_by_country[key] = proxy_url
        return proxy_url

    # ------------------------------------------------------------------
    # Single segment execution（mock + live unified entrance）
    # ------------------------------------------------------------------
    def _geo_evt(self, evt: dict[str, Any]) -> dict[str, Any]:
        """Attach the detected real exit geographical information of the segment to the event.(Used for progress bar to display real country)。"""
        g = self._stage_geo.get(evt.get("stage") or "")
        if g:
            evt["actual_country"] = g.get("actual_country", "")
            evt["exit_ip"] = g.get("exit_ip", "")
            evt["geo_confidence"] = g.get("geo_confidence", 0.0)
            evt["requested_country"] = evt.get("country", "")
        return evt

    async def _probe_stage(self, stage: str, country: str, proxy_url: str) -> None:
        """Detect the real country of export before using a proxy/City/IP，record and emit geo_probe event。

        same IP Reuse: same proxy(Same country sticky session)If it has been detected, the result will be reused directly.,
        Do not send detection requests repeatedly (geo_probe event zone reused mark)。
        """
        if not proxy_url or settings.chain_mode != "live":
            return
        cached = self._geo_by_proxy.get(proxy_url)
        if cached is not None:
            self._stage_geo[stage] = dict(cached, requested=country)
            await self._emit({
                "type": "geo_probe", "stage": stage, "country": country,
                "reused": True, "from_stage": cached.get("stage", ""),
                **{k: cached[k] for k in ("actual_country", "exit_ip", "geo_confidence", "city", "ok") if k in cached},
            })
            return
        try:
            probe = await self._run_in_executor(_geo_probe_country, proxy_url)
            geo = {
                "requested": country, "stage": stage,
                "actual_country": probe.get("country", ""),
                "exit_ip": probe.get("ip", ""),
                "geo_confidence": probe.get("confidence", 0.0),
                "city": probe.get("city", ""),
                "sources": probe.get("sources", []),
                "ok": probe.get("ok", False),
                "error": probe.get("error", ""),
                "ts": probe.get("ts", ""),
            }
        except Exception as e:  # If the detection fails, the link will not be blocked., mark empty
            geo = {"requested": country, "stage": stage, "actual_country": "",
                   "exit_ip": "", "geo_confidence": 0.0, "city": "",
                   "sources": [], "ok": False,
                   "error": f"{type(e).__name__}: {e}", "ts": ""}
        self._geo_by_proxy[proxy_url] = geo
        self._stage_geo[stage] = geo
        await self._emit({
            "type": "geo_probe", "stage": stage, "country": country,
            "reused": False,
            **{k: geo[k] for k in ("actual_country", "exit_ip", "geo_confidence", "city", "ok", "requested") if k in geo},
        })

    def _apply_result_geo(self) -> None:
        """Aggregate the real export information of each piece into ChainResult(Pick checkout priority)。"""
        self.result.requested_country = self.result.country or ""
        geos = list(self._stage_geo.values())
        g = self._stage_geo.get("checkout") or (geos[0] if geos else {})
        self.result.actual_country = (g.get("actual_country") or "").upper()
        self.result.exit_ip = g.get("exit_ip", "")
        self.result.geo_confidence = g.get("geo_confidence", 0.0)
        self.result.stage_geo = dict(self._stage_geo)

    def _result_geo_kw(self) -> dict[str, Any]:
        """chain_success/failure Real exit information attached to the event。"""
        return {
            "requested_country": self.result.requested_country,
            "actual_country": self.result.actual_country,
            "exit_ip": self.result.exit_ip,
            "geo_confidence": self.result.geo_confidence,
        }

    async def _run_stage(self, stage: str, fn_live, *args, fail_reason: str = "network_error") -> Any:
        sc = settings.branch_stage(self.branch_name, stage)
        display = stage  # 7All segments are displayed independently
        max_try = sc.retry
        country = self.pick.get(stage, "US")
        last_err = ""
        for try_n in range(1, max_try + 1):
            if self._cancelled:
                raise asyncio.CancelledError()
            try:
                live_args = None
                if settings.chain_mode == "live" and _HAS_CURL:
                    live_args = list(args)
                    if live_args and live_args[0] is None:
                        proxy = self._pick_proxy(stage, country)
                        live_args[0] = proxy
                        await self._probe_stage(display, country, proxy)
                evt_try = {"type": "stage_try", "stage": display, "country": country,
                           "try_n": try_n, "max_try": max_try}
                await self._emit(self._geo_evt(evt_try))
                if live_args is not None:
                    res = await self._run_in_executor(fn_live, *live_args)
                else:
                    res = await self._mock_stage(stage)
                evt_ok = {"type": "stage_ok", "stage": display, "country": country}
                await self._emit(self._geo_evt(evt_ok))
                self._stage_states[stage] = {"state": "ok", "country": country}
                return res
            except asyncio.CancelledError:
                raise
            except NonZeroAmount as e:
                # Amount guard failed：fail-closed，Do not retry
                evt_fail = {"type": "stage_fail", "stage": display, "country": country,
                            "detail": str(e)[:300]}
                await self._emit(self._geo_evt(evt_fail))
                self._stage_states[stage] = {"state": "fail", "country": country}
                raise
            except Exception as e:
                last_err = f"{type(e).__name__}: {e}"
                if try_n < max_try:
                    evt_retry = {"type": "stage_retry", "stage": display, "country": country,
                                 "error": last_err, "try_n": try_n, "max_try": max_try}
                    await self._emit(self._geo_evt(evt_retry))
                    await asyncio.sleep(min(2.0, 0.5 * try_n))
                else:
                    evt_fail = {"type": "stage_fail", "stage": display, "country": country,
                                "detail": last_err[:300]}
                    await self._emit(self._geo_evt(evt_fail))
                    self._stage_states[stage] = {"state": "fail", "country": country}
        raise ChainStageError(fail_reason, last_err)

    async def _mock_stage(self, stage: str) -> dict:
        """Analog single segment：Random time consuming + Judgment based on success rate。Simulate by branch channel type。"""
        lo = settings.mock_stage_min
        hi = settings.mock_stage_max
        await asyncio.sleep(random.uniform(lo, hi))
        # poll Segment simulation polling multi-step
        if stage == "poll":
            steps = random.randint(2, 6)
            for _ in range(steps):
                await asyncio.sleep(settings.branch_stage(self.branch_name, "poll").poll_interval)
        rate = settings.mock_success_rate
        if random.random() > rate:
            raise RuntimeError(f"mock_{stage}_random_fail")
        channel = self.branch_cfg.channel
        # Return simulated data
        if stage == "checkout":
            return {"checkout_session_id": f"cs_mock_{uuid.uuid4().hex[:12]}",
                    "publishable_key": "pk_live_mock", "processor_entity": "openai_llc"}
        if stage == "init":
            # pair init hour: init0 Use the exit to get the channel type, init1 Local verification (Return here uniformly)
            return {"init": {"invoice": {"amount_due": 0}, "currency": "usd",
                             "payment_method_types": [channel], "init_checksum": "ic_mock"}}
        if stage == "update":
            return {"amount_due": 0, "currency": "usd", "zero_verified": True}
        if stage == "provider":
            return {"pm_id": f"pm_mock_{uuid.uuid4().hex[:8]}",
                    "redirect": f"https://pm-redirects.stripe.com/authorize/mock_{uuid.uuid4().hex[:10]}",
                    "confirm_state": "requires_approval"}
        if stage == "approve":
            return {"ok": True, "result": "approved"}
        if stage == "poll":
            return {"redirect": f"https://pm-redirects.stripe.com/authorize/mock_{uuid.uuid4().hex[:10]}"}
        if stage == "resolve":
            hex8 = uuid.uuid4().hex[:12]
            if self.branch_name == "bizum":
                return {"url": f"https://checkout.stripe.com/c/pay/cs_live_mock_{hex8}"}
            if self.branch_name == "gopay":
                return {"url": f"https://app.midtrans.com/snap/v4/redirection/mock_{hex8}"}
            if self.branch_name in ("naver_pay", "kakao"):
                return {"url": f"https://pay.nicepay.co.kr/v1/checkout/pay/mock_{hex8}"}
            if self.branch_name == "upi":
                return {"url": f"https://payments.stripe.com/upi/instructions/mock_{hex8}"}
            ba = f"BA-{uuid.uuid4().hex[:16].upper()}"
            return {"url": f"https://www.paypal.com/agreements/approve?ba_token={ba}"}
        return {}

    def _oaics_mint_sentinel(self, flow: str, page_url: str,
                             proxy: str = "") -> Optional[dict[str, str]]:
        """mint OpenAI Sentinel head (Alignment link-pp: Stablize device tie cookie header)。

        within the chain device unified (self._oaics_device_id), cookie_header Constructed from the same session;
        fail/Disable/No live return None (Caller downgrade to None sentinel direct connection)。
        """
        if not self._oaics_device_id or settings.chain_mode != "live":
            return None
        try:
            from ..ba_paypal.sentinel_mint import try_mint_sentinel
        except Exception:
            return None
        import os as _os
        if _os.environ.get("MIN_OAICS_SENTINEL") == "0":
            return None
        from . import oaics_proto as _op
        billing_cc = str(self.pick_oaics.get("_billing") or "US")
        _prof = _op._profile(billing_cc)
        cookie_header = _op._cookie_header(
            self._oaics_device_id, self.session_token, self._oaics_cookie_jar or None)
        main, so = try_mint_sentinel(
            flow=flow, device_id=self._oaics_device_id, user_agent=_op._CHROME_UA,
            proxy=proxy,
            page_url=page_url or "https://chatgpt.com/",
            language=_prof["browser_language"], timezone=_prof["browser_timezone"],
            cookie_header=cookie_header)
        out: dict[str, str] = {}
        if main:
            out["OpenAI-Sentinel-Token"] = main
        if so:
            out["OpenAI-Sentinel-SO-Token"] = so
        return out or None

    # ------------------------------------------------------------------
    # oaics lift chain (OpenAI custom_checkout_session) + cs_live rollback
    # ------------------------------------------------------------------
    async def _execute_oaics_paypal(self, t0: float, co: dict, country: str,
                                    skip_update: bool = False,
                                    device_id: str = "") -> bool:
        """oaics custom Checkout pure HTTP lift chain (Alignment link-pp state machine):

        checkout(custom+promo) -> fetch state -> taxes -> strict 0 meta polling
        -> elements/sessions(amount=0+betas) -> ctoken(inline paypal)
        -> checkgpt confirm(Optional sentinel) -> redirect Straight out, No rules Stripe
        intent confirm(seti_/pi_ + ctoken Reuse) -> redirect -> resolve。
        not pass cs_live_ of update/init/approve/poll。Any failure throws an exception。"""
        import os as _os
        from . import oaics_proto as op

        cs = co.get("checkout_session_id") or ""
        pk = co.get("publishable_key") or ""
        entity = co.get("processor_entity") or "openai_llc"
        billing_cc = self.pick_oaics.get("_billing", country)
        currency = self.pick_oaics.get("_currency", "USD")
        prof = op._jwt_profile(self.access_token)
        email = str(prof.get("email") or self.email or "")
        name = str(prof.get("name") or "")
        if not name:
            from .billing import billing_for
            name = billing_for(billing_cc).get("name") or "John Doe"
        from .billing import billing_for as _bf
        b = _bf(billing_cc)
        billing = {
            "name": name, "email": email,
            "address": {
                "country": b.get("country", billing_cc),
                "line1": b.get("line1", ""), "line2": b.get("line2", ""),
                "city": b.get("city", ""), "state": b.get("state", ""),
                "postal_code": b.get("postal_code", ""),
            },
        }
        provider_country = self.pick_oaics.get("provider", country)
        confirm_country = self.pick_oaics.get("confirm", country)
        pm_proxy = self._pick_proxy("provider", provider_country)
        device_id = device_id or str(uuid.uuid4())

        def mint_sentinel(flow: str, did: str, page_url: str = "",
                          cookie_header: str = ""):
            return self._oaics_mint_sentinel(flow, page_url, pm_proxy) or {}

        confirm_page_url = f"https://chatgpt.com/checkout/{entity}/{cs}"
        cookie_header = op._cookie_header(device_id, self.session_token,
                                          self._oaics_cookie_jar or None)

        # S2 bill (fetch state + taxes + 0 meta polling); taxes The section exit is the exit of this section, provider Subsequent multiplexing of independent segments
        taxes_country = self.pick_oaics.get("taxes", "US")
        taxes_proxy = self._pick_proxy("taxes", taxes_country)
        await self._probe_stage("taxes", taxes_country, taxes_proxy)
        await self._emit(self._geo_evt({"type": "stage_try", "stage": "taxes",
                                        "country": taxes_country, "try_n": 1, "max_try": 1}))
        try:
            state = await self._run_in_executor(
                op.fetch_oaics_checkout_state, taxes_proxy, self.access_token,
                self.session_token, cs, entity, country=billing_cc,
                device_id=device_id, cookie_jar=self._oaics_cookie_jar)
            tax_state = await self._run_in_executor(
                op.submit_oaics_checkout_taxes, taxes_proxy, self.access_token,
                self.session_token, cs, entity, billing=billing,
                country=billing_cc, currency=currency, device_id=device_id,
                cookie_jar=self._oaics_cookie_jar)
            # 2026-08-13: 0 Meta-check following configuration (branches.<branch>.require_zero /
            # options.require_zero)。Skip strict when closed 0 meta polling, Full price and walk away directly
            # ctoken/confirm chain (Actual full price oaics Can also mention BA)。
            chk_zero = self.branch_cfg.require_zero and self.options.get("require_zero", True)
            if chk_zero:
                state = await self._run_in_executor(
                    op.wait_for_oaics_zero, taxes_proxy, self.access_token,
                    self.session_token, cs, entity, country=billing_cc,
                    currency=currency, device_id=device_id,
                    initial_payload=tax_state or state,
                    cookie_jar=self._oaics_cookie_jar)
            else:
                state = tax_state or state
            methods = op.oaics_payment_method_types(state)
            detected_currency = op.oaics_checkout_currency(state)
            if detected_currency and detected_currency != currency:
                raise ChainStageError(
                    "non_zero_amount",
                    f"OAICS The currency is inconsistent with the billing country: expected={currency}, actual={detected_currency}")
        except op.OaicsPromoNotApplied as e:
            await self._emit(self._geo_evt({"type": "stage_fail", "stage": "taxes",
                                            "country": taxes_country, "detail": str(e)[:300]}))
            self._stage_states["taxes"] = {"state": "fail", "country": taxes_country}
            raise ChainStageError("non_zero_amount", str(e)) from e
        except op.OaicsAuthError as e:
            await self._emit(self._geo_evt({"type": "stage_fail", "stage": "taxes",
                                            "country": taxes_country, "detail": str(e)[:300]}))
            self._stage_states["taxes"] = {"state": "fail", "country": taxes_country}
            raise ChainStageError("checkout_failed", str(e)) from e
        except op.OaicsPaypalUnsupported as e:
            await self._emit(self._geo_evt({"type": "stage_fail", "stage": "taxes",
                                            "country": taxes_country, "detail": str(e)[:300]}))
            self._stage_states["taxes"] = {"state": "fail", "country": taxes_country}
            raise ChainStageError("paypal_unsupported", str(e)) from e
        except Exception as e:
            await self._emit(self._geo_evt({"type": "stage_fail", "stage": "taxes",
                                            "country": taxes_country,
                                            "detail": f"{type(e).__name__}: {str(e)[:300]}"}))
            self._stage_states["taxes"] = {"state": "fail", "country": taxes_country}
            raise ChainStageError("non_zero_amount",
                                  f"oaics bill/0Metavalidation failed: {type(e).__name__}: {str(e)[:400]}") from e
        await self._emit(self._geo_evt({"type": "stage_ok", "stage": "taxes",
                                        "country": taxes_country}))
        self._stage_states["taxes"] = {"state": "ok", "country": taxes_country}
        if chk_zero:
            self.result.amount_due = 0
        else:
            try:
                obs = op.oaics_amount_observations(state)
                self.result.amount_due = int(next((v for _, v in obs if v is not None), 0) or 0)
            except Exception:
                self.result.amount_due = 0
        self.result.currency = str(currency or "USD").upper()
        self.result.billing_country = billing_cc
        self.result.stage_reached = "taxes"

        # S2.5 preheat checkout The page gets the front-end deployment context (attestation/sessionId; Failed to downgrade)
        attestation = str(_os.environ.get("MIN_OAICS_ATTESTATION") or "").strip()
        if not attestation:
            try:
                bootstrap_ctx = await self._run_in_executor(
                    op.bootstrap_oaics_checkout_context, pm_proxy, self.access_token,
                    self.session_token, cs, entity, country=billing_cc,
                    device_id=device_id, cookie_jar=self._oaics_cookie_jar)
                attestation = str((bootstrap_ctx or {}).get("attestation") or "").strip()
            except Exception:
                attestation = ""

        # S2.6 cpmt_ Custom payment method branch (payment_method_types not exposed paypal This is the way to go)
        redirect = ""
        if "paypal" not in (methods or []):
            try:
                cpmt_methods = op.oaics_custom_payment_methods(state)
            except Exception:
                cpmt_methods = []
            if cpmt_methods:
                try:
                    cpmt_sentinel = mint_sentinel("checkout_session_approval", device_id,
                                                  confirm_page_url, cookie_header) or None
                    cpmt_redirect, _ = await self._run_in_executor(
                        lambda: op.oaics_custom_paypal_redirect(
                            pm_proxy, self.access_token, self.session_token, cs, entity,
                            country=billing_cc, currency=currency, device_id=device_id,
                            sentinel_headers=cpmt_sentinel, attestation=attestation,
                            cookie_jar=self._oaics_cookie_jar))
                    redirect = cpmt_redirect
                    self.result.pm_authorize_url = redirect
                except op.OaicsConfirmBlocked as e:
                    await self._emit(self._geo_evt({"type": "stage_fail", "stage": "confirm",
                                                    "country": confirm_country,
                                                    "detail": f"OaicsConfirmBlocked: {str(e)[:500]}"}))
                    self._stage_states["confirm"] = {"state": "fail", "country": confirm_country}
                    raise ChainStageError("approve_blocked",
                                          f"oaics cpmt blocked: {str(e)[:500]}") from e
                except op.PayPalFundingUnavailable as e:
                    await self._emit(self._geo_evt({"type": "stage_fail", "stage": "taxes",
                                                    "country": taxes_country,
                                                    "detail": str(e)[:300]}))
                    self._stage_states["taxes"] = {"state": "fail", "country": taxes_country}
                    raise ChainStageError("paypal_unsupported", str(e)) from e
                except Exception as e:
                    await self._emit(self._geo_evt({"type": "stage_fail", "stage": "provider",
                                                    "country": provider_country}))
                    self._stage_states["provider"] = {"state": "fail", "country": provider_country}
                    raise ChainStageError(
                        "provider_failed",
                        f"oaics cpmt Failed to lift chain: {type(e).__name__}: {str(e)[:150]}") from e

        # S3 provider (Standard only paypal path): elements/sessions -> ctoken (inline paypal, Optional P1)
        if not redirect:
            p1_token = str(_os.environ.get("MIN_OAICS_P1") or "")
            customer = str(_os.environ.get("MIN_OAICS_CUSTOMER") or "")
            cuss = op._oaics_find_string(
                state, ("customer_session_client_secret", "customerSessionClientSecret"))
            if not cuss:
                raise ChainStageError("provider_failed", "oaics checkout none customer_session_client_secret")
            await self._probe_stage("provider", provider_country, pm_proxy)
            await self._emit(self._geo_evt({"type": "stage_try", "stage": "provider",
                                            "country": provider_country, "try_n": 1, "max_try": 1}))
            try:
                elements = await self._run_in_executor(
                    op.create_oaics_elements_session, pm_proxy, pk, cuss,
                    country=billing_cc, currency=currency,
                    methods=methods or ["paypal", "link", "card"])
                if customer:
                    elements["customer"] = customer
                ctoken = await self._run_in_executor(
                    op.create_oaics_paypal_confirmation_token, pm_proxy, pk, elements,
                    billing=billing, currency=currency, p1_token=p1_token)
                if not str(ctoken).startswith(("ctoken_", "ct_")):
                    raise RuntimeError("ctoken Creation failed")
            except Exception as e:
                await self._emit(self._geo_evt({"type": "stage_fail", "stage": "provider",
                                                "country": provider_country}))
                self._stage_states["provider"] = {"state": "fail", "country": provider_country}
                raise ChainStageError("provider_failed",
                                      f"oaics ctoken Creation failed: {type(e).__name__}: {str(e)[:150]}") from e
            await self._emit(self._geo_evt({"type": "stage_ok", "stage": "provider",
                                            "country": provider_country}))
            self._stage_states["provider"] = {"state": "ok", "country": provider_country}
            self.result.stage_reached = "provider"

            # S4 confirm (sentinel header optional; blocked Try again)
            await self._emit(self._geo_evt({"type": "stage_try", "stage": "confirm",
                                            "country": confirm_country, "try_n": 1, "max_try": 1}))
            sentinel_headers = mint_sentinel("checkout_session_approval", device_id,
                                             confirm_page_url, cookie_header) or None
            try:
                app_confirm = await self._run_in_executor(
                    op.confirm_oaics_standard_paypal, pm_proxy, self.access_token,
                    self.session_token, cs, entity, ctoken, country=billing_cc,
                    device_id=device_id, sentinel_headers=sentinel_headers,
                    attestation=attestation, cookie_jar=self._oaics_cookie_jar)
            except op.OaicsConfirmBlocked:
                sentinel_headers = mint_sentinel("checkout_session_approval", device_id,
                                                 confirm_page_url, cookie_header) or None
                try:
                    app_confirm = await self._run_in_executor(
                        op.confirm_oaics_standard_paypal, pm_proxy, self.access_token,
                        self.session_token, cs, entity, ctoken, country=billing_cc,
                        device_id=device_id, sentinel_headers=sentinel_headers,
                        attestation=attestation, cookie_jar=self._oaics_cookie_jar)
                except op.OaicsConfirmBlocked as e:
                    await self._emit(self._geo_evt({"type": "stage_fail", "stage": "confirm",
                                                    "country": confirm_country,
                                                    "detail": f"OaicsConfirmBlocked: {str(e)[:500]}"}))
                    self._stage_states["confirm"] = {"state": "fail", "country": confirm_country}
                    raise ChainStageError("approve_blocked",
                                          f"oaics confirm blocked: {str(e)[:500]}") from e
            except op.OaicsAuthError as e:
                raise ChainStageError("confirm_failed", str(e)) from e
            except op.PayPalFundingUnavailable as e:
                await self._emit(self._geo_evt({"type": "stage_fail", "stage": "confirm",
                                                "country": confirm_country,
                                                "detail": f"PayPalFundingUnavailable: {str(e)[:500]}"}))
                self._stage_states["confirm"] = {"state": "fail", "country": confirm_country}
                raise ChainStageError("paypal_unsupported", str(e)) from e
            except Exception as e:
                await self._emit(self._geo_evt({"type": "stage_fail", "stage": "confirm",
                                                "country": confirm_country,
                                                "detail": f"{type(e).__name__}: {str(e)[:500]}"}))
                self._stage_states["confirm"] = {"state": "fail", "country": confirm_country}
                raise ChainStageError("confirm_failed",
                                      f"oaics confirm: {type(e).__name__}: {str(e)[:500]}") from e
            redirect = extract_redirect(app_confirm) or extract_redirect_url(app_confirm)
            if not redirect:
                try:
                    intent_confirm = await self._run_in_executor(
                        op.confirm_oaics_paypal_intent, pm_proxy, ctoken, app_confirm, elements)
                except op.PayPalFundingUnavailable as e:
                    await self._emit(self._geo_evt({"type": "stage_fail", "stage": "confirm",
                                                    "country": confirm_country,
                                                    "detail": f"PayPalFundingUnavailable: {str(e)[:500]}"}))
                    self._stage_states["confirm"] = {"state": "fail", "country": confirm_country}
                    raise ChainStageError("paypal_unsupported", str(e)) from e
                except Exception as e:
                    await self._emit(self._geo_evt({"type": "stage_fail", "stage": "confirm",
                                                    "country": confirm_country,
                                                    "detail": f"{type(e).__name__}: {str(e)[:500]}"}))
                    self._stage_states["confirm"] = {"state": "fail", "country": confirm_country}
                    raise ChainStageError(
                        "confirm_failed",
                        f"oaics intent confirm: {type(e).__name__}: {str(e)[:500]}") from e
                redirect = extract_redirect(intent_confirm) or extract_redirect_url(intent_confirm)
            if not redirect:
                await self._emit(self._geo_evt({"type": "stage_fail", "stage": "confirm",
                                                "country": confirm_country}))
                self._stage_states["confirm"] = {"state": "fail", "country": confirm_country}
                raise ChainStageError("no_redirect", "oaics confirm/intent No return jump")
            await self._emit(self._geo_evt({"type": "stage_ok", "stage": "confirm",
                                            "country": confirm_country}))
            self._stage_states["confirm"] = {"state": "ok", "country": confirm_country}
            self.result.pm_authorize_url = redirect
            self.result.stage_reached = "confirm"

        # S5 resolve (Follow jump chain extraction BA Link)
        resolve_country = self.pick_oaics.get("resolve", country)
        final_url = await self._run_in_executor(
            stage_resolve_live, self._pick_proxy("resolve", resolve_country),
            redirect, None, self.branch_name)
        if not final_url:
            await self._emit(self._geo_evt({"type": "stage_fail", "stage": "resolve",
                                            "country": resolve_country}))
            self._stage_states["resolve"] = {"state": "fail", "country": resolve_country}
            raise ChainStageError("resolve_failed", "oaics resolve No results")
        await self._emit(self._geo_evt({"type": "stage_ok", "stage": "resolve",
                                        "country": resolve_country}))
        self._stage_states["resolve"] = {"state": "ok", "country": resolve_country}

        # Successful ending
        self.result.success = True
        self.result.paypal_approve_url = final_url
        m = re.search(r"ba_token=([A-Za-z0-9-]+)", final_url)
        self.result.ba_token = m.group(1) if m else ""
        self.result.stage_reached = "resolve"
        self.result.elapsed = time.monotonic() - t0
        self._apply_result_geo()
        await self._emit({
            "type": "chain_success",
            "paypal_approve_url": final_url,
            "pm_authorize_url": redirect,
            "country": self.result.country,
            "email": self.email,
            "amount": self.result.amount_due,
            "currency": self.result.currency,
            "ba_token": self.result.ba_token,
            "branch": self.branch_name,
            "link_type": "paypal_ba",
            "link_mode": "oaics",
            "elapsed": round(self.result.elapsed, 2),
            **self._result_geo_kw(),
        })
        return True

    # ------------------------------------------------------------------
    # full link
    # ------------------------------------------------------------------
    async def execute(self) -> ChainResult:
        t0 = time.monotonic()
        try:
            await self._emit({"type": "chain_start", "email": self.email,
                              "token_sub": self.token.get("sub", ""), "attempt": self.attempt})
            country = self.pick["checkout"]
            # billing country/Currency: follow config billing_country (auto -> exporting country), Currency EUR Waiting for billing country
            billing_cc = self.pick.get("_billing", country)
            currency = self.pick.get("_currency", "USD")
            checkout_proxy = ""

            # 2026-08-14: S0 Independent detection segment has been removed (detection=Create an order one more time, trigger 429 And it is repeated with the link establishment order.)。
            # Session type changed to S1 Dynamic determination of order creation results (Whatever you build, go away): oaics_ -> oaics chain,
            # cs_live_ -> Seven-segment main chain; token.session_type Historical values ​​are only used for"No downgrade"Semantics。

            # S1 checkout (billing_details billing country+Currency; Export agent press pick nation)
            # paypal Session type offload (2026-08-14 Starting from nothing S0 Independent detection section, use S1 Order creation result + history
            # session_type reveal all the details; history S0 Detection fields are obsolete, See __init__ Comment):
            #   oaics   -> Only use oaics Configuration (oaics billing country + custom Create an order), Build a non- oaics Session failed directly, No downgrade
            #   cs_live -> Go directly to the seven-section main chain (Seven-dan bill country + hosted Create an order), don't try oaics
            #   Not labeled   -> Keep original behavior: First custom try, Build a non- oaics Then roll back seven sections of the main chain
            if self.branch_name == "paypal":
                detected = self._detected_session or str(self.token.get("session_type") or "").strip().lower()
                self._oaics_only = detected == "oaics"
                if detected == "oaics":
                    # 【Deprecated】_probe_billing_cc/_probe_currency from S0 detection section (Removed),
                    # Always empty, This branch only retains semantic compatibility (bill country to follow pick_oaics default value)。
                    if self._probe_billing_cc:
                        self.pick_oaics["_billing"] = self._probe_billing_cc
                        self.pick_oaics["_currency"] = self._probe_currency or billing_currency(self._probe_billing_cc)
                if detected == "cs_live":
                    # Seven-dan bill country/Currency (hosted Create an order, Walk the original seven sections update/init main chain)
                    billing_cc = self.pick.get("_billing", country)
                    currency = self.pick.get("_currency", "USD")
                    co = await self._run_stage(
                        "checkout", stage_checkout_live,
                        None, self.access_token, self.session_token, billing_cc, currency,
                        self.branch_name,
                        fail_reason="checkout_failed")
                else:
                    # oaics / Not detected: oaics billing country + custom Create an order (oaics_only downgrade is prohibited)
                    billing_cc = self.pick_oaics.get("_billing", billing_cc)
                    currency = self.pick_oaics.get("_currency", currency)
                    self._oaics_device_id = str(uuid.uuid4())
                    self._oaics_cookie_jar = {}
                    checkout_proxy = self._pick_proxy("checkout", country)
                    create_sentinel = await self._run_in_executor(
                        self._oaics_mint_sentinel, "chatgpt_checkout",
                        "https://chatgpt.com/", checkout_proxy)
                    co = await self._run_stage(
                        "checkout", stage_checkout_live,
                        None, self.access_token, self.session_token, billing_cc, currency,
                        self.branch_name, True, "custom", create_sentinel,
                        self._oaics_cookie_jar, self._oaics_device_id,
                        fail_reason="checkout_failed")
            else:
                co = await self._run_stage("checkout", stage_checkout_live,
                                           None, self.access_token, self.session_token, billing_cc, currency,
                                           self.branch_name,
                                           fail_reason="checkout_failed")
            if settings.chain_mode == "live" and _HAS_CURL:
                if not co.get("ok"):
                    raise ChainStageError(
                        "checkout_failed",
                        f"Order creation failed: HTTP {co.get('status')} {str(co.get('detail') or '')[:120]}")
                cs = co["checkout_session_id"]
                pk = co["publishable_key"]
                entity = co.get("processor_entity") or ("openai_llc" if country == "US" else "openai_ie")
            else:
                cs = co["checkout_session_id"]
                pk = co["publishable_key"]
                entity = "openai_llc"
            if self.branch_name == "paypal" and not str(cs or "").startswith("oaics_"):
                if self._oaics_only:
                    # history oaics But this time it was built oaics session: No downgrade, Change IP Re-create order and try again
                    # (Align reference items link-pp engine: OaicsCheckoutRequiredError -> Change proxy and try again,
                    #  until attempts Fail until exhausted)
                    retry_limit = max(1, int(self.options.get("attempts")
                                             or self.branch_cfg.attempts or 8))
                    retry_n = 0
                    while retry_n < retry_limit and not str(cs or "").startswith("oaics_"):
                        retry_n += 1
                        self._stage_states.clear()
                        self.result = ChainResult()
                        self.result.email = self.email
                        self.result.token_id = self.token.get("id", "")
                        checkout_proxy = self._pick_proxy("checkout", country)
                        create_sentinel = await self._run_in_executor(
                            self._oaics_mint_sentinel, "chatgpt_checkout",
                            "https://chatgpt.com/", checkout_proxy)
                        co = await self._run_stage(
                            "checkout", stage_checkout_live,
                            None, self.access_token, self.session_token, billing_cc, currency,
                            self.branch_name, True, "custom", create_sentinel,
                            self._oaics_cookie_jar, self._oaics_device_id,
                            fail_reason="checkout_failed")
                        cs = co.get("checkout_session_id") or ""
                        if str(cs or "").startswith("oaics_"):
                            pk = co.get("publishable_key") or ""
                            entity = co.get("processor_entity") or (
                                "openai_llc" if country == "US" else "openai_ie")
                            self.result.country = country
                            self.result.stage_reached = "checkout"
                            break
                    if not str(cs or "").startswith("oaics_"):
                        # Retry exhausted still not oaics: No downgrade based on history, fail
                        self.result.reason_code = "oaics_session_mismatch"
                        self.result.reason_text = (
                            f"history oaics but try again {retry_n} This time we still built something wrong oaics session: {str(cs or '')[:24]}")
                        self.result.stage_reached = "checkout"
                        await self._finish_failure()
                        return self.result
                else:
                    # Downgrade path: The session is cs_live_ (No account custom checkout), Sync bill for this session
                    # ensure update press0 and create Bill consistent
                    self.pick["_billing"] = billing_cc
                    self.pick["_currency"] = currency
            self.result.country = country
            self.result.stage_reached = "checkout"

            # oaics session (OpenAI custom_checkout_session): priority oaics lift chain;
            # update press0 promo Not available(403)The next round of changes checkout inline promo;
            # Failure to do so will result in the original country/Export as is checkout rollback, still oaics keep walking, Until success or reaching the upper limit
            oaics_rounds = 0
            MAX_OAICS_ROUNDS = max(1, int(self.options.get("attempts")
                                          or self.branch_cfg.attempts or 8))
            promo_inline = False
            while self.branch_name == "paypal" and str(cs or "").startswith("oaics_"):
                oaics_rounds += 1
                self.oaics_mode = True
                try:
                    done = await self._execute_oaics_paypal(
                        t0, co, country, skip_update=promo_inline,
                        device_id=self._oaics_device_id)
                    if done:
                        return self.result
                except ChainStageError as e:
                    self.result.reason_code = e.reason_code
                    self.result.reason_text = str(e)
                    if e.reason_code == "promo_unavailable" and not promo_inline:
                        # Change route: checkout Directly inline promo (v1 old link path)
                        promo_inline = True
                except Exception as e:
                    self.result.reason_code = "oaics_failed"
                    self.result.reason_text = f"oaics Process failed: {type(e).__name__}: {str(e)[:400]}"
                if oaics_rounds >= MAX_OAICS_ROUNDS:
                    self.result.reason_code = "oaics_fallback_failed"
                    self.result.reason_text = (
                        f"oaics continuous {oaics_rounds} Round failed, give up: {self.result.reason_text}")
                    self.result.stage_reached = "checkout"
                    await self._finish_failure()
                    return self.result
                # rollback: Reset segment status and results only, Original billing country/Export as is checkout (promo_inline on demand)
                # 2026-08-14: Alignment link-pp engine Change IP Semantics — Forced replacement of new exits every round IP
                # (Reuse the same IP Place orders repeatedly, Server promo Qualification press IP/Time fluctuation, Change IP Just have a chance to hit 0 Yuan)
                self._stage_states.clear()
                self.result = ChainResult()
                self.result.email = self.email
                self.result.token_id = self.token.get("id", "")
                checkout_proxy = self._pick_proxy("checkout", country)
                create_sentinel = await self._run_in_executor(
                    self._oaics_mint_sentinel, "chatgpt_checkout",
                    "https://chatgpt.com/", checkout_proxy)
                co = await self._run_stage(
                    "checkout", stage_checkout_live,
                    None, self.access_token, self.session_token, billing_cc, currency,
                    self.branch_name, True, "custom", create_sentinel,
                    self._oaics_cookie_jar, self._oaics_device_id,
                    fail_reason="checkout_failed")
                if self.branch_name != "paypal" or not str(co.get("checkout_session_id") or "").startswith("oaics_"):
                    if self._oaics_only:
                        # Detected as oaics: After retrying, the result is still not oaics session, Direct failure without downgrade
                        self.result.reason_code = "oaics_session_mismatch"
                        self.result.reason_text = (
                            f"oaics After the process is retried, a non- oaics session: {str(co.get('checkout_session_id') or '')[:24]}")
                        self.result.stage_reached = "checkout"
                        await self._finish_failure()
                        return self.result
                    self.oaics_mode = False
                    break
                cs = co["checkout_session_id"]
                pk = co["publishable_key"]
                entity = co.get("processor_entity") or "openai_llc"
                self.result.country = country
                self.result.stage_reached = "checkout"

            # S2 init (pair init: init0 Use the exit to get the channel type -> init1 Go back to local area to verify the authenticity -> init_t transition)
            # direct Direct card: none Stripe init, mark ok jump over
            init = {}
            if self.branch_name == "direct":
                await self._emit({"type": "stage_try", "stage": "init",
                                  "country": self.pick.get("init", country), "try_n": 1, "max_try": 1})
                await self._emit({"type": "stage_ok", "stage": "init",
                                  "country": self.pick.get("init", country)})
                self._stage_states["init"] = {"state": "ok", "country": self.pick.get("init", country)}
                self.result.stage_reached = "init"
            elif self.branch_cfg.dual_init:
                # init0: Take the exit (init0_ccs) take payment_method_types
                initr0 = await self._run_stage("init", stage_init_live, None, pk, cs,
                                               self.branch_name,
                                               fail_reason="init_failed")
                init0 = initr0.get("init", {}) if isinstance(initr0, dict) else {}
                # init1: Return to local (init1_ccs) Verify, Get the last round result
                initr1 = await self._run_stage("init", stage_init_live, None, pk, cs,
                                               self.branch_name,
                                               fail_reason="init_failed")
                init1 = initr1.get("init", {}) if isinstance(initr1, dict) else {}
                # merge: init1 priority, Missing field fallback init0
                init = {**init0, **init1}
                self.result.stage_reached = "init"
                self._init_rounds = {"init0": init0, "init1": init1}
            else:
                initr = await self._run_stage("init", stage_init_live, None, pk, cs,
                                              self.branch_name,
                                              fail_reason="init_failed")
                init = initr.get("init", {}) if isinstance(initr, dict) else {}
                self.result.stage_reached = "init"

            # S3 update / Dual outlet injection promo press 0 Yuan + amount guard + Payment channel verification
            # Channel verification is not done in init: update part verify_zero The amount has been verified simultaneously(require_zero)
            # and payment channels(channel_check)，Tighten in one place。
            chk_channel = self.branch_cfg.channel
            chk_check = self.branch_cfg.channel_check and self.options.get("channel_check", True)
            chk_zero = self.branch_cfg.require_zero and self.options.get("require_zero", True)
            try:
                if settings.chain_mode == "live" and _HAS_CURL:
                    # update part: exist update_region Export to built checkout session injection promo
                    upd_country = self.pick.get("update", country)
                    upd_proxy = self._pick_proxy("update", upd_country)
                    await self._probe_stage("update", upd_country, upd_proxy)
                    await self._emit(self._geo_evt({"type": "stage_try", "stage": "update",
                                                    "country": upd_country, "try_n": 1, "max_try": 1}))
                    upd = await self._run_in_executor(
                        stage_update_live, upd_proxy, self.access_token, self.session_token,
                        cs, entity, self.pick.get("_billing", country),
                        self.pick.get("_currency", "USD"), self.branch_name)
                    if not upd.get("ok"):
                        await self._emit(self._geo_evt({"type": "stage_fail", "stage": "update",
                                                        "country": upd_country}))
                        self._stage_states["update"] = {"state": "fail", "country": upd_country}
                        raise ChainStageError(
                            "non_zero_amount",
                            f"update status={upd.get('status')} body={json.dumps(upd.get('body'), ensure_ascii=False)[:300]}")
                    await self._emit(self._geo_evt({"type": "stage_ok", "stage": "update",
                                                    "country": upd_country}))
                    self._stage_states["update"] = {"state": "ok", "country": upd_country}
                    if self.branch_name == "direct":
                        # Direct card: from update body Withdrawal amount verification (checkout_state.total), No need Stripe init
                        amount = _extract_amount_minor(upd.get("body"))
                        gate = {"amount_due": amount, "currency": self.pick.get("_currency", "USD"),
                                "zero_verified": (amount == 0)}
                        if chk_zero and amount != 0:
                            raise NonZeroAmount(amount or -1, str(gate["currency"]))
                        self.result.stage_reached = "update"
                    else:
                        # update register promo Run again after success init Get new amount_due
                        initr = await self._run_stage("init", stage_init_live, None, pk, cs,
                                                      self.branch_name,
                                                      fail_reason="init_failed")
                        init = initr.get("init", {}) if isinstance(initr, dict) else {}
                        self.result.stage_reached = "init"
                        gate = await self._run_stage("update", lambda *_: verify_zero(
                            init, require_zero=chk_zero, channel_check=chk_check, channel=chk_channel),
                                                     fail_reason="non_zero_amount")
                else:
                    # mock model: no reality Stripe, The simulated amount passed the verification
                    await self._emit(self._geo_evt({"type": "stage_try", "stage": "update",
                                                    "country": self.pick.get("update", country),
                                                    "try_n": 1, "max_try": 1}))
                    await self._emit(self._geo_evt({"type": "stage_ok", "stage": "update",
                                                    "country": self.pick.get("update", country)}))
                    self._stage_states["update"] = {"state": "ok", "country": self.pick.get("update", country)}
                    gate = {"amount_due": 0 if chk_zero else None,
                            "currency": self.pick.get("_currency", "USD"),
                            "zero_verified": True}
            except NonZeroAmount as e:
                self.result.reason_code = "non_zero_amount"
                self.result.reason_text = f"amount_due={e.amount} {e.currency} No 0"
                self.result.stage_reached = "init"
                await self._finish_failure()
                return self.result
            except ChannelMismatch as e:
                self.result.reason_code = "paypal_unsupported"
                self.result.reason_text = str(e)
                self.result.stage_reached = "init"
                await self._finish_failure()
                return self.result
            except ChainStageError as e:
                if "paypal" in str(e) or "channel" in str(e) or "channel" in str(e).lower():
                    self.result.reason_code = "paypal_unsupported"
                else:
                    self.result.reason_code = "non_zero_amount"
                self.result.reason_text = str(e)
                await self._finish_failure()
                return self.result
            self.result.amount_due = gate.get("amount_due", 0)
            self.result.currency = gate.get("currency", "")
            self.result.stage_reached = "update"

            # Straight card chain: truncate path (checkout none promo -> update press 0 -> verify -> Produce short link)
            # output: https://chatgpt.com/checkout/{entity}/{cs_id}
            prof2 = branch_profile(self.branch_name)
            if prof2.get("truncate_after_update"):
                # jump over init/provider/approve/poll/resolve, direct success
                ent = entity or ("openai_llc" if country == "US" else "openai_ie")
                final_url = f"https://chatgpt.com/checkout/{ent}/{cs}"
                self.result.success = True
                self.result.paypal_approve_url = final_url
                self.result.stage_reached = "resolve"
                self.result.elapsed = time.monotonic() - t0
                self._apply_result_geo()
                # Mark subsequent segments as ok (Link monitoring display)
                for _s in ("provider", "approve", "poll", "resolve"):
                    await self._emit({"type": "stage_try", "stage": _s,
                                      "country": self.pick.get(_s, country), "try_n": 1, "max_try": 1})
                    await self._emit({"type": "stage_ok", "stage": _s,
                                      "country": self.pick.get(_s, country)})
                    self._stage_states[_s] = {"state": "ok", "country": self.pick.get(_s, country)}
                await self._emit({
                    "type": "chain_success",
                    "paypal_approve_url": final_url,
                    "pm_authorize_url": "",
                    "country": self.result.country,
                    "email": self.email,
                    "amount": self.result.amount_due,
                    "currency": self.result.currency,
                    "ba_token": "",
                    "branch": self.branch_name,
                    "link_mode": "cs",
                    "elapsed": round(self.result.elapsed, 2),
                    **self._result_geo_kw(),
                })
                return self.result

            ctx = build_ctx(init)

            # S4 provider (PM + confirm)
            provider_country = self.pick["provider"]
            # billing country: Use this if a fixed country is configured, Otherwise follow checkout billing country (auto)
            bc = (self.branch_cfg.billing_country or "auto").upper()
            billing_country = self.pick["_billing"] if bc in ("AUTO", "") else bc
            self.result.billing_country = billing_country
            try:
                if settings.chain_mode == "live" and _HAS_CURL:
                    pm_proxy = self._pick_proxy("provider", provider_country)
                    await self._probe_stage("provider", provider_country, pm_proxy)
                    pm = await self._run_in_executor(
                        stage_payment_method_live, pm_proxy, pk, cs, init, billing_country, ctx,
                        self.branch_name)
                    await self._emit(self._geo_evt({"type": "stage_try", "stage": "provider",
                                                    "country": provider_country, "try_n": 1, "max_try": 1}))
                    cf = await self._run_in_executor(
                        stage_confirm_live, pm_proxy, pk, cs, init, pm, ctx, provider_country, entity,
                        chk_zero, chk_check, chk_channel, self.branch_name)
                    await self._emit(self._geo_evt({"type": "stage_ok", "stage": "provider",
                                                    "country": provider_country}))
                    self._stage_states["provider"] = {"state": "ok", "country": provider_country}
                    redirect = cf.get("redirect", "")
                    state = cf.get("confirm_state", "")
                else:
                    pr = await self._mock_stage("provider")
                    await self._emit({"type": "stage_try", "stage": "provider",
                                      "country": provider_country, "try_n": 1, "max_try": 1})
                    await self._emit({"type": "stage_ok", "stage": "provider", "country": provider_country})
                    self._stage_states["provider"] = {"state": "ok", "country": provider_country}
                    redirect = pr.get("redirect", "")
                    state = pr.get("confirm_state", "")
            except Exception as e:
                self._stage_states["provider"] = {"state": "fail", "country": provider_country}
                await self._emit(self._geo_evt({"type": "stage_fail", "stage": "provider",
                                                "country": provider_country}))
                self.result.reason_code = "provider_failed"
                self.result.reason_text = str(e)
                self.result.stage_reached = "provider"
                await self._finish_failure()
                return self.result
            self.result.stage_reached = "provider"

            # S5 approve (only if none redirect and requires_approval hour)
            approve_country = self.pick["approve"]
            if not redirect and state == "requires_approval":
                try:
                    ap = await self._run_stage("approve", stage_approve_live,
                                               None, self.access_token, self.session_token, cs, entity,
                                               self.branch_name,
                                               fail_reason="approve_failed")
                    if isinstance(ap, dict):
                        # approve quilt ChatGPT Risk control rejection (result=blocked): fail fast,
                        # Don't continue to poll Misjudged as no_redirect
                        if str(ap.get("result") or "") == "blocked":
                            self.result.reason_code = "approve_blocked"
                            self.result.reason_text = "approve return result=blocked (ChatGPT Risk control refuses approval)"
                            self.result.stage_reached = "approve"
                            self._stage_states["approve"] = {"state": "fail", "country": approve_country}
                            await self._emit(self._geo_evt({"type": "stage_fail", "stage": "approve",
                                                            "country": approve_country, "error": "result=blocked"}))
                            await self._finish_failure()
                            return self.result
                        redirect = ap.get("redirect", "") or redirect
                except ChainStageError as e:
                    self.result.reason_code = "approve_failed"
                    self.result.reason_text = str(e)
                    self.result.stage_reached = "approve"
                    await self._finish_failure()
                    return self.result
            else:
                # jump over approve part，direct mark ok
                await self._emit({"type": "stage_try", "stage": "approve",
                                  "country": approve_country, "try_n": 1, "max_try": 1})
                await self._emit({"type": "stage_ok", "stage": "approve", "country": approve_country})
                self._stage_states["approve"] = {"state": "ok", "country": approve_country}
            self.result.stage_reached = "approve"

            # S6 poll
            if not redirect:
                try:
                    poll_res = await self._run_stage("poll", stage_poll_live, None, pk, cs,
                                                     None, self.branch_name, fail_reason="poll_timeout")
                    redirect = poll_res.get("redirect", "") if isinstance(poll_res, dict) else str(poll_res or "")
                    poll_artifacts = poll_res.get("artifacts", {}) if isinstance(poll_res, dict) else {}
                except ChainStageError as e:
                    self.result.reason_code = "poll_timeout"
                    self.result.reason_text = str(e)
                    self.result.stage_reached = "poll"
                    await self._finish_failure()
                    return self.result
            else:
                poll_artifacts = {}
                await self._emit({"type": "stage_try", "stage": "poll",
                                  "country": self.pick["poll"], "try_n": 1, "max_try": 1})
                await self._emit({"type": "stage_ok", "stage": "poll", "country": self.pick["poll"]})
                self._stage_states["poll"] = {"state": "ok", "country": self.pick["poll"]}
            # check pm-redirects
            prof = branch_profile(self.branch_name)
            resolve_re = prof["resolve_re"]
            search_re = prof["resolve_search_re"]
            if not redirect or not (RE_PM_AUTHORIZE.match(redirect) or (search_re and search_re.search(redirect))):
                self.result.reason_code = "no_redirect"
                self.result.reason_text = f"redirect no match pm-redirects: {redirect[:80]}"
                self.result.stage_reached = "poll"
                self._stage_states["poll"] = {"state": "fail", "country": self.pick["poll"]}
                await self._emit({"type": "stage_fail", "stage": "poll", "country": self.pick["poll"]})
                await self._finish_failure()
                return self.result
            self.result.pm_authorize_url = redirect
            if poll_artifacts:
                self.result.artifacts.update(poll_artifacts)
            self.result.stage_reached = "poll"

            # S7 resolve
            try:
                rs = await self._run_stage("resolve", stage_resolve_live,
                                           None, redirect, None, self.branch_name, fail_reason="resolve_failed")
                final_url = rs.get("url", "") if isinstance(rs, dict) else ""
            except ChainStageError as e:
                self.result.reason_code = "resolve_failed"
                self.result.reason_text = str(e)
                self.result.stage_reached = "resolve"
                await self._finish_failure()
                return self.result
            # Verification final URL（By branch rule）
            if not final_url or not (resolve_re and resolve_re.match(final_url)):
                self.result.reason_code = "resolve_failed"
                self.result.reason_text = f"final URL no match {self.branch_name}: {final_url[:80]}"
                self.result.stage_reached = "resolve"
                self._stage_states["resolve"] = {"state": "fail", "country": self.pick["resolve"]}
                await self._emit({"type": "stage_fail", "stage": "resolve", "country": self.pick["resolve"]})
                await self._finish_failure()
                return self.result

            # success
            self.result.success = True
            self.result.paypal_approve_url = final_url
            m = re.search(r"ba_token=([A-Za-z0-9-]+)", final_url)
            self.result.ba_token = m.group(1) if m else ""
            self.result.stage_reached = "resolve"
            self.result.elapsed = time.monotonic() - t0
            self._apply_result_geo()
            # No paypal branch: follow Go to the gateway page to grab QR/Deep chain products (momo/pix/upi/kakao/...)
            if self.branch_name != "paypal" and final_url:
                gw_proxy = ""
                if settings.chain_mode == "live" and _HAS_CURL:
                    gw_proxy = self._pick_proxy("resolve", self.pick["resolve"])
                try:
                    gw = await self._run_in_executor(follow_gateway_redirect, gw_proxy, final_url)
                    if isinstance(gw, dict):
                        gw_artifacts = {k: v for k, v in gw.items() if k not in ("final_url", "error") and v}
                        if gw_artifacts:
                            self.result.artifacts.update(gw_artifacts)
                except Exception:
                    pass
            # Unified contract fields
            art = self.result.artifacts or {}
            if self.branch_name == "paypal":
                self.result.link_type = "paypal_ba"
            elif art.get("qr_image_url") or art.get("qr_png_url"):
                self.result.link_type = f"{self.branch_name}_qr"
            elif art.get("deep_link") or art.get("pix_code"):
                self.result.link_type = f"{self.branch_name}_deeplink"
            else:
                self.result.link_type = f"{self.branch_name}_url"
            self.result.error_stage = ""
            self.result.retryable = False
            self.result.requires_reconciliation = self.branch_name != "paypal" and bool(
                art.get("hosted_instructions_url") or art.get("qr_data")
            )
            await self._emit({
                "type": "chain_success",
                "paypal_approve_url": final_url,
                "pm_authorize_url": redirect,
                "country": self.result.country,
                "email": self.email,
                "amount": self.result.amount_due,
                "currency": self.result.currency,
                "ba_token": self.result.ba_token,
                "branch": self.branch_name,
                "link_type": self.result.link_type,
                "artifacts": self.result.artifacts,
                "link_mode": "oaics" if self.oaics_mode else "cs",
                "elapsed": round(self.result.elapsed, 2),
                **self._result_geo_kw(),
            })
            return self.result

        except asyncio.CancelledError:
            self.result.reason_code = "network_error"
            self.result.reason_text = "link canceled"
            await self._finish_failure()
            raise
        except Exception as e:
            self.result.reason_code = "network_error"
            self.result.reason_text = f"{type(e).__name__}: {e}"
            await self._finish_failure()
            return self.result

    async def _finish_failure(self) -> None:
        self.result.elapsed = time.monotonic() - 0  # Overridden by the caller
        self._apply_result_geo()
        self.result.error_stage = self.result.stage_reached or ""
        self.result.retryable = self.result.reason_code in {
            "network_error", "proxy_error", "tls_error", "poll_timeout", "checkout_failed", "init_failed",
        }
        await self._emit({
            "type": "chain_failure",
            "reason_code": self.result.reason_code,
            "reason_text": self.result.reason_text,
            "country": self.result.country,
            "stage_reached": self.result.stage_reached,
            "error_stage": self.result.error_stage,
            "retryable": self.result.retryable,
            "email": self.email,
            "link_mode": "oaics" if (self.oaics_mode or self._oaics_only) else "cs",
            **self._result_geo_kw(),
        })


class ChainStageError(Exception):
    def __init__(self, reason_code: str, detail: str = ""):
        self.reason_code = reason_code
        super().__init__(f"{reason_code}: {detail}" if detail else reason_code)
