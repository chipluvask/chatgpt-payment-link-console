# -*- coding: utf-8 -*-
"""Direct card pure agreement payment segment: lift chain → Bind card → Payment confirmation → Subscription verification (zero browser)。

process (pure protocol, refer to zkky):
  1. lift chain: checkout(US) → update(TR press0) → oaics short chain
  2. Bind card: POST /backend-api/payments/payment_method → SetupIntent
     → POST /v1/setup_intents/{seti}/confirm (Inline card data) → pm_id
  3. Payment confirmation: POST /v1/confirmation_tokens → ctoken
     → POST /backend-api/payments/checkout/confirm → final seti
     → POST /v1/setup_intents/{final}/confirm → succeeded
  4. Subscription verification: GET /backend-api/subscriptions → plan_type == "plus"

Card source: core/card_store (Built-in test card 4000 0000 0000 0002 / 12/30 / 123)
Tax-free address: core/taxfree_store (DE/NH/MT/OR/AK)
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any

from .bind_card import bind_card, bind_and_pay, list_payment_methods
from .card_store import card_store
from .chain import chatgpt_session, make_session, _req, stage_checkout_live, stage_update_live
from .config import settings
from .taxfree_store import taxfree_store

log = logging.getLogger(__name__)


class DirectPayError(RuntimeError):
    pass


def _pick_proxy(stage: str, country: str) -> str:
    from .proxy_pool import proxy_pool
    try:
        return proxy_pool.pick_for_stage(stage, country)
    except Exception as e:
        raise DirectPayError(f"Agent acquisition failed: {e}") from e


def _run_stage(fn, *args, tries: int = 3, **kw) -> Any:
    last = None
    for i in range(tries):
        try:
            return fn(*args, **kw)
        except Exception as e:
            last = e
            time.sleep(2)
    raise last


def direct_checkout(
    access_token: str,
    session_token: str = "",
    *,
    billing_country: str = "PH",
    currency: str = "PHP",
) -> dict[str, Any]:
    """Straight card chain core: checkout(US) → update(TR press 0) → short chain output。"""
    co_px = _pick_proxy("checkout", "US")
    co = _run_stage(stage_checkout_live, co_px, access_token, session_token,
                    billing_country, currency, "direct")
    if not co.get("ok"):
        raise DirectPayError(f"checkout fail: status={co.get('status')} {co.get('detail')}")
    cs = co["checkout_session_id"]
    entity = co.get("processor_entity") or "openai_llc"

    upd_px = _pick_proxy("update", "TR")
    upd = _run_stage(stage_update_live, upd_px, access_token, session_token,
                     cs, entity, "US", "USD", "direct")
    if not upd.get("ok"):
        raise DirectPayError(f"update press0fail: status={upd.get('status')}")

    # Amount verification (from update body extract)
    from .chain import _extract_amount_minor
    amount = _extract_amount_minor(upd.get("body"))
    if amount not in (0, None):
        raise DirectPayError(f"press0fail: amount={amount}")
    short_link = f"https://chatgpt.com/checkout/{entity}/{cs}"
    return {"short_link": short_link, "cs": cs, "entity": entity,
            "amount": amount or 0, "billing_country": billing_country}


def bind_and_subscribe(
    access_token: str,
    session_token: str = "",
    *,
    account_id: str = "",
    card_id: int | None = None,
    taxfree_state: str = "DE",
    rebind_recheckout: bool = True,
    use_cdp_fallback: bool = False,
    hcaptcha_token: str = "",
) -> dict[str, Any]:
    """Complete direct card pure agreement payment: lift chain → Bind card → Payment confirmation → Subscription verification。

    Args:
        use_cdp_fallback: True=Fallback to when pure protocol fails CDP Browser card binding (default False, Pure protocol first)
        hcaptcha_token: hCaptcha passive token (Optional, Stripe radar_options)
    """
    out: dict[str, Any] = {"ok": False, "step": ""}
    proxy = _pick_proxy("checkout", "US")

    # 0. Get card (card library)
    card = None
    if card_id:
        card = card_store.get_card(card_id)
    if not card:
        card = card_store.pickup_card()
    if not card:
        out.update(step="card", error="No card available in card library")
        return out
    out["card_last4"] = str(card.get("number", ""))[-4:]

    # 1. lift chain (short chain)
    try:
        ch1 = direct_checkout(access_token, session_token)
    except DirectPayError as e:
        out.update(step="checkout1", error=str(e))
        return out
    out["short_link_1"] = ch1["short_link"]
    cs1 = ch1["cs"]
    entity = ch1["entity"]

    # 2. account_id (from JWT extract)
    if not account_id:
        import base64
        try:
            payload_b64 = access_token.split(".")[1]
            payload_b64 += "=" * (-len(payload_b64) % 4)
            jwt = json.loads(base64.urlsafe_b64decode(payload_b64))
            auth_claims = jwt.get("https://api.openai.com/auth") or {}
            account_id = str(auth_claims.get("chatgpt_account_id") or "")
        except Exception:
            account_id = ""
    if not account_id:
        out.update(step="bind", error="Unable to determine account_id (Need to provide account_id)")
        return out

    # 3. Tax-free address (bill)
    addr = taxfree_store["generate"](state=taxfree_state)
    billing = {
        "name": card.get("name") or "Test User",
        "line1": addr.get("street", ""),
        "city": addr.get("city", ""),
        "state": addr.get("state", ""),
        "postal_code": addr.get("zip", ""),
        "country": "US",  # For card binding US address (tax free state)
    }

    # 4. Pure protocol complete process: Bind card + Payment confirmation + Subscription verification
    log.info("Starting pure-protocol bind_and_pay...")
    result = bind_and_pay(
        proxy, access_token, account_id, card, session_token,
        checkout_id=cs1, processor=entity,
        billing=billing, currency="USD",
        fast_verify=True, timeout=30,
        hcaptcha_token=hcaptcha_token,
    )
    out["bind_and_pay"] = result

    if not result.get("ok"):
        # Pure protocol fails, Optional fallback CDP
        if use_cdp_fallback:
            log.warning(f"Pure protocol failed at {result.get('step')}, falling back to CDP...")
            try:
                from .cdp_bind import cdp_bind_card
                import asyncio
                bind = asyncio.new_event_loop().run_until_complete(
                    cdp_bind_card(access_token, account_id, card, session_token)
                )
            except Exception as e:
                bind = {"ok": False, "error": f"{type(e).__name__}: {e}"}
            out["cdp_fallback"] = bind
            if not bind.get("ok"):
                out.update(step="bind", error=f"pure: {result.get('error')} | cdp: {bind.get('error')}")
                return out
            # CDP Only bind the card, No payment confirmation
            out["step"] = "done_bind_only"
            out["pm_id"] = bind.get("pm_id", "")
            out["method"] = "cdp_fallback"
        else:
            out.update(step=result.get("step", "bind"),
                       error=result.get("error", "pure protocol failed"))
            return out
    else:
        out["method"] = "pure_protocol"
        out["pm_id"] = result.get("pm_id", "")
        out["subscription_plan"] = result.get("subscription_plan", "")

    # 5. Re-upload the chain (session refresh, Optional)
    if rebind_recheckout:
        try:
            ch2 = direct_checkout(access_token, session_token)
            out["short_link_2"] = ch2["short_link"]
            out["cs_2"] = ch2["cs"]
        except DirectPayError as e:
            out["recheckout_error"] = str(e)

    out["taxfree_address"] = addr
    out["taxfree_state"] = taxfree_state
    out["ok"] = True
    out["step"] = "done"
    out["subscribe_hint"] = (
        f"Pure protocol card binding+pay{'success' if result.get('ok') else 'Finish(Bind card)'}, "
        f"subscription={result.get('subscription_plan', 'N/A')}"
    )
    return out
