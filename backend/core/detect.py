# -*- coding: utf-8 -*-
"""Channel detection（channel detection）：Detect a certain payment channel in a certain country checkout Is it available and compressible? 0 Yuan。

and paypal Link-complete mode：
  1. checkout Without promo（Get the truth first payment_method_types，not be promo filter out channels）
  2. init0 Confirm that the target channel is payment_method_types inside
  3. update injection promo press 0 Yuan
  4. init1 verify：The channel is still there and amount_due == 0

refer to D:\\tidy\\upl-main\\detect_payment_methods.py + v2 paypal link（Verified）：
  - pix of C7 Record"BR bring promo filter out pix"→ There must be no promo Get channels，Press again 0
  - All links（momo/pix/ideal/upi/kakao/blik/twint）All"Channel first, pressure later 0"
"""
from __future__ import annotations

import logging
import uuid
from typing import Any

from .billing import billing_currency
from .chain import chatgpt_session, make_session, _req, stage_update_live
from .config import settings

log = logging.getLogger(__name__)

# Common channels ignored during detection
IGNORED_METHODS = {"card", "paypal", "link"}

# Channel alias（Stripe Return name -> branch name）
CHANNEL_ALIASES: dict[str, tuple[str, ...]] = {
    "momo": ("momo",),
    "pix": ("pix",),
    "ideal": ("ideal",),
    "upi": ("upi",),
    "kakao": ("kakao", "kakaopay", "kakao_pay"),
    "naver_pay": ("naver_pay", "naverpay"),
    "bizum": ("bizum",),
    "gopay": ("gopay", "go_pay", "gopay_id"),
    "blik": ("blik",),
    "twint": ("twint",),
    "paypal": ("paypal",),
    "card": ("card",),
    "link": ("link",),
}


def _init_once(proxy: str, pk: str, cs: str, timeout: int) -> dict[str, Any]:
    """run once Stripe init，Return the parsed dict（Contains invoice/payment_method_types/init_checksum）。"""
    body = {
        "browser_locale": "en-US", "browser_timezone": "Asia/Shanghai",
        "elements_session_client[client_betas][0]": "custom_checkout_server_updates_1",
        "elements_session_client[client_betas][1]": "custom_checkout_manual_approval_1",
        "elements_session_client[elements_init_source]": "custom_checkout",
        "elements_session_client[referrer_host]": "chatgpt.com",
        "elements_session_client[stripe_js_id]": "stripe_js_detect",
        "elements_session_client[locale]": "en",
        "elements_session_client[is_aggregation_expected]": "false",
        "elements_options_client[saved_payment_method][enable_save]": "never",
        "elements_options_client[saved_payment_method][enable_redisplay]": "never",
        "key": pk, "_stripe_version": settings.stripe.get(
            "init_version",
            "2025-03-31.basil; checkout_server_update_beta=v1; checkout_manual_approval_preview=v1",
        ),
    }
    s = make_session(proxy)
    try:
        r = _req(s, "POST", f"https://api.stripe.com/v1/payment_pages/{cs}/init", data=body,
                 headers={"Origin": "https://pay.openai.com", "Referer": "https://pay.openai.com/",
                          "Accept": "application/json",
                          "Content-Type": "application/x-www-form-urlencoded"},
                 timeout=max(10, timeout))
        try:
            d = r.json()
        except Exception:
            d = {"raw": (r.text or "")[:500]}
        d = d if isinstance(d, dict) else {}
        return {"status": r.status_code, "ok": r.status_code < 400, "init": d}
    finally:
        s.close()


def probe_token(
    access_token: str,
    session_token: str = "",
    proxy: str = "",
    country: str = "US",
    currency: str = "",
    timeout: int = 20,
) -> dict[str, Any]:
    """Complete account detection: session type + token state + Discount qualifications + paypal channel。

    1. checkout(none promo): judge cs_live_* / oaics_*, 401/429 judge token state
    2. cs_live hour init: Record amount_due and payment_method_types (paypal Is it available)
    3. update injection promo: 200=Qualified for discounts / 403 promotion not available=Not eligible

    return {session_type, cs, entity, token, token_error, promo, paypal, amount,
          status, detail, error}
    """
    cc = (country or "US").upper()
    cur = currency or billing_currency(cc)
    out: dict[str, Any] = {
        "session_type": "", "cs": "", "entity": "",
        "token": "ok", "token_error": "",
        "promo": "", "paypal": False, "amount": None,
        "status": 0, "detail": "", "error": "",
    }
    s = chatgpt_session(proxy, access_token, session_token)
    path = "/backend-api/payments/checkout"
    payload = {
        "entry_point": "all_plans_pricing_modal",
        "plan_name": "chatgptplusplan",
        "billing_details": {"country": cc, "currency": cur},
        "checkout_ui_mode": "custom",
        "check_card_proxy": True,
    }
    # 2026-08-13: Detect and build orders to align production links (warmup + common_headers + custom model),
    # Ensure that the detected session type is consistent with the actual link creation order。
    device_id = str(uuid.uuid4().hex[:16])
    try:
        from . import oaics_proto as _op
        _op.warmup_chatgpt_page(s, country=cc, device_id=device_id)
        probe_headers = {
            **_op.common_headers(country=cc, device_id=device_id,
                                 referer="https://chatgpt.com/", route=path),
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            "Origin": "https://chatgpt.com",
        }
    except Exception:
        probe_headers = {"Referer": "https://chatgpt.com/",
                         "x-openai-target-path": path, "x-openai-target-route": path}
    try:
        try:
            r = _req(s, "POST", "https://chatgpt.com" + path, json=payload,
                     headers=probe_headers,
                     timeout=max(10, timeout))
        except Exception as e:
            out["error"] = f"checkout Request failed: {type(e).__name__}: {str(e)[:150]}"
            return out
        out["status"] = r.status_code
        try:
            d = r.json()
        except Exception:
            d = {"raw": (r.text or "")[:500]}
        d = d if isinstance(d, dict) else {}
        # 401 The error body may be {"error": {"message", "code"}} or {"detail": "..."}
        err = d.get("error") if isinstance(d.get("error"), dict) else {}
        detail = str(d.get("detail") or err.get("message") or d.get("message") or "")
        err_code = str(err.get("code") or "")
        out["detail"] = detail[:160]
        if r.status_code >= 400:
            if r.status_code == 401:
                low = (detail + " " + err_code).lower()
                if "invalidated" in low or "token_invalidated" in low:
                    out["token"] = "invalidated"
                    out["token_error"] = "token revoked"
                elif "expired" in low or "token_expired" in low:
                    out["token"] = "expired"
                    out["token_error"] = "token Expired"
                else:
                    out["token"] = "unauthorized"
                    out["token_error"] = f"401 Unauthorized: {detail[:40]}"
            elif r.status_code == 429:
                out["token"] = "rate_limited"
                out["token_error"] = "Trigger current limit"
            else:
                out["token"] = f"http_{r.status_code}"
                out["token_error"] = f"HTTP {r.status_code}"
            return out
        cs = d.get("checkout_session_id") or d.get("id") or ""
        if not cs:
            out["error"] = f"checkout none checkout_session_id: {str(d)[:200]}"
            return out
        out["cs"] = cs
        out["entity"] = d.get("processor_entity") or ""
        if cs.startswith("oaics_"):
            out["session_type"] = "oaics"
        elif cs.startswith("cs_live_") or cs.startswith("cs_"):
            out["session_type"] = "cs_live"
        else:
            out["session_type"] = "unknown"

        # 2) cs_live: init Record amount and channel (oaics right Stripe init 404, jump over)
        pk = d.get("publishable_key") or ""
        if out["session_type"] == "cs_live" and pk:
            try:
                initr = _init_once(proxy, pk, cs, timeout)
                d0 = initr.get("init") or {}
                if initr.get("ok") and isinstance(d0, dict):
                    invoice = d0.get("invoice") if isinstance(d0.get("invoice"), dict) else {}
                    if "amount_due" in invoice:
                        out["amount"] = int(invoice.get("amount_due"))
                    raw = d0.get("payment_method_types")
                    methods = [str(m).lower() for m in raw] if isinstance(raw, list) else []
                    out["paypal"] = "paypal" in methods
            except Exception:
                pass

        # 3) update injection promo Detect Discount Eligibility (200=have, 403 promotion not available=none)
        try:
            upd = stage_update_live(proxy, access_token, session_token, cs, out["entity"] or "openai_llc",
                                    cc, cur, "paypal")
            body = str(upd.get("body") or "")
            if upd.get("ok"):
                out["promo"] = "yes"
            else:
                st2 = upd.get("status")
                if st2 == 403 and ("promotion" in body.lower() or "not available" in body.lower()):
                    out["promo"] = "no"
                else:
                    out["promo"] = f"err:{st2}"
        except Exception as e:
            out["promo"] = f"err:{type(e).__name__}:{str(e)[:40]}"
        return out
    finally:
        s.close()


def probe_session_type(access_token: str, session_token: str = "", proxy: str = "",
                       country: str = "US", currency: str = "", timeout: int = 20) -> dict[str, Any]:
    """Compatible packaging: Only session type identification is returned (old interface)。"""
    r = probe_token(access_token, session_token, proxy, country, currency, timeout)
    return {
        "session_type": r.get("session_type") or "",
        "cs": r.get("cs") or "",
        "entity": r.get("entity") or "",
        "status": r.get("status") or 0,
        "detail": r.get("detail") or "",
        "error": r.get("error") or (r.get("token_error") or ""),
    }


def detect_channel(
    proxy: str,
    access_token: str,
    session_token: str,
    country: str,
    currency: str = "",
    channel: str = "momo",
    update_country: str = "VN",
    update_proxy: str = "",
    timeout: int = 15,
) -> dict[str, Any]:
    """Complete detection：checkout(none promo) -> init0(channel) -> update(press0) -> init1(Verification channel+0Yuan)。

    return {channel, present, zero_ok, methods0, methods1, amount0, amount1,
          country, currency, update_country, error}
    """
    out: dict[str, Any] = {
        "channel": channel,
        "present": False,
        "zero_ok": False,
        "methods0": [],
        "methods1": [],
        "amount0": None,
        "amount1": None,
        "country": country,
        "currency": currency or billing_currency(country),
        "update_country": update_country,
        "error": "",
    }
    cc = (country or "").upper()
    cur = currency or billing_currency(cc)

    # 1) checkout Without promo（Real channel list）
    s = chatgpt_session(proxy, access_token, session_token)
    path = "/backend-api/payments/checkout"
    payload = {
        "entry_point": "all_plans_pricing_modal",
        "plan_name": "chatgptplusplan",
        "billing_details": {"country": cc, "currency": cur},
        "checkout_ui_mode": "hosted",
    }
    try:
        try:
            r = _req(s, "POST", "https://chatgpt.com" + path, json=payload,
                     headers={"Referer": "https://chatgpt.com/",
                              "x-openai-target-path": path, "x-openai-target-route": path},
                     timeout=max(10, timeout))
        except Exception as e:
            out["error"] = f"checkout Request failed: {type(e).__name__}: {str(e)[:150]}"
            return out
        try:
            d = r.json()
        except Exception:
            d = {"raw": (r.text or "")[:500]}
        d = d if isinstance(d, dict) else {}
        if r.status_code >= 400:
            out["error"] = f"checkout status={r.status_code}: {str(d)[:200]}"
            return out
        cs = d.get("checkout_session_id") or d.get("id") or ""
        pk = d.get("publishable_key") or ""
        entity = d.get("processor_entity") or ("openai_llc" if cc == "US" else "openai_ie")
        if not cs or not pk:
            out["error"] = f"checkout none cs/pk: {str(d)[:200]}"
            return out
    finally:
        s.close()

    # 2) init0 Get channels
    init0 = _init_once(proxy, pk, cs, timeout)
    if not init0.get("ok"):
        out["error"] = f"init0 status={init0.get('status')}: {str(init0.get('init'))[:200]}"
        return out
    d0 = init0.get("init") or {}
    invoice0 = d0.get("invoice") if isinstance(d0.get("invoice"), dict) else {}
    if "amount_due" in invoice0:
        out["amount0"] = int(invoice0.get("amount_due"))
    raw0 = d0.get("payment_method_types")
    methods0 = list(dict.fromkeys(str(m).lower() for m in raw0)) if isinstance(raw0, list) else []
    out["methods0"] = methods0
    aliases = CHANNEL_ALIASES.get(channel, (channel,))
    present0 = any(m in aliases for m in methods0)
    out["present"] = present0
    if not present0:
        out["error"] = f"init0 Channel does not exist: {channel} not in {methods0}"
        return out

    # 3) update press 0 Yuan（update_country export agent）
    try:
        upd = stage_update_live(update_proxy or proxy, access_token, session_token, cs, entity, cc, cur, "paypal")
        if not upd.get("ok"):
            out["error"] = f"update press0fail status={upd.get('status')}: {str(upd.get('body'))[:200]}"
            return out
    except Exception as e:
        out["error"] = f"update press0abnormal: {type(e).__name__}: {str(e)[:150]}"
        return out

    # 4) init1 verify：The channel is still there and 0 Yuan
    init1 = _init_once(proxy, pk, cs, timeout)
    if not init1.get("ok"):
        out["error"] = f"init1 status={init1.get('status')}: {str(init1.get('init'))[:200]}"
        return out
    d1 = init1.get("init") or {}
    invoice1 = d1.get("invoice") if isinstance(d1.get("invoice"), dict) else {}
    if "amount_due" in invoice1:
        out["amount1"] = int(invoice1.get("amount_due"))
    raw1 = d1.get("payment_method_types")
    methods1 = list(dict.fromkeys(str(m).lower() for m in raw1)) if isinstance(raw1, list) else []
    out["methods1"] = methods1
    present1 = any(m in aliases for m in methods1)
    zero_ok = out["amount1"] == 0
    out["zero_ok"] = zero_ok and present1
    if not present1:
        out["error"] = f"press0Back channel lost: {channel} not in {methods1}"
    elif not zero_ok:
        out["error"] = f"press0fail: amount_due={out['amount1']}"
    return out
