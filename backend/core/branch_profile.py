# -*- coding: utf-8 -*-
"""Portrait of chain branch（branch profiles）：All payment channels are in 7 Difference points on segment links。

Each branch definition：
  - pm_type:                payment_method Created type（paypal/momo/pix/ideal/upi/kakao/blik/twint/card）
  - confirm_type:           confirm of expected_payment_method_type
  - pm_extra:               PM body extra fields（like pix of billing_details[tax_id]=CPF）
  - resolve_re:             resolve Segment Success Judgment Regularity
  - resolve_search_re:      resolve follow 302 chain time Location/Regular search in the text
  - output_key:             ChainResult The output field name of（paypal_approve_url / payment_url ...）
  - require_ba:             True=output BA token Semantics（paypal），False=output payment URL（momo/pix wait）
  - referrer:               PM/confirm of referrer（paypal=momo of chatgpt.com，ideal May be different）

Recipe source（D:\\tidy historical realization）：
  - paypal:  v2 Verified link（init_checksum Underline + attribution full set + consent tos）
  - momo:    v1/v2 core/momo.py fifth floor Patch（type=momo + VN bill + payment.momo.vn/pay/app）
  - pix:     pix-core-open-source + pix-qr-extractor（C7 Empirical evidence：Full price PaymentIntent + tax_id CPF +
             next_action.pix_display_qr_code；0 Yuan pressure will be filtered out pix）
  - ideal:   upl-main/ideal_qr_extract.py（NL/VN/NL；type=ideal + NL bill + bank transfer URL）
  - upi:     upl-main/upi/upi_extract.py（IN/VN/IN；payments.stripe.com/upi/instructions）
  - kakao:   upl-main/kakao/kakao_extract.py（KR/VN/KR；nicepay/kakao Jump）
  - blik:    upl-main/blik/blik_qr_extract.py（PL/PL/PL；Stripe Interface submission BLIK Code）
  - twint:   upl-main/twint/twint_extract.py（CH/VN/CH）
"""
from __future__ import annotations

import re
from typing import Any

# ---- Each branch successfully produces regular rules ----

RE_PAYPAL_BA = re.compile(r"^https://www\.paypal\.com/agreements/approve\?ba_token=[A-Za-z0-9-]+$")
RE_PAYPAL_BA_SEARCH = re.compile(r"https://www\.paypal\.com/agreements/approve\?ba_token=[A-Za-z0-9-]+")
RE_PM_AUTHORIZE = re.compile(r"^https://pm-redirects\.stripe\.com/authorize/")

RE_MOMO_PAY = re.compile(r"^https://payment\.momo\.vn/pay/app/[A-Za-z0-9]+")
RE_MOMO_PAY_SEARCH = re.compile(r"https://payment\.momo\.vn/pay/app/[A-Za-z0-9]+")

RE_DIRECT_LINK = re.compile(r"^https://chatgpt\.com/checkout/[a-z_]+/[A-Za-z0-9_-]+$")

RE_PIX_URL = re.compile(r"^https://(?:pay\.openai\.com|checkout\.stripe\.com)/[^\s\"']+")
RE_PIX_QR = re.compile(r"br\.gov\.bcb\.pix[^\s\"']+")

RE_IDEAL_URL = re.compile(r"^https://[^\s\"']+")
RE_UPI_URL = re.compile(r"^https://payments\.stripe\.com/upi/[^\s\"']+")
RE_UPI_URL_SEARCH = re.compile(r"https://payments\.stripe\.com/upi/[^\s\"']+")
RE_KAKAO_URL = re.compile(r"^https://[^\s\"']+(?:nicepay|kakao)[^\s\"']*", re.I)
RE_NAVER_URL = re.compile(r"^https://[^\s\"']+(?:nicepay|naver)[^\s\"']*", re.I)
RE_GOPAY_URL = re.compile(r"^https://[^\s\"']+(?:midtrans|snap)[^\s\"']*", re.I)
RE_BIZUM_URL = re.compile(r"^https://checkout\.stripe\.com/c/[^\s\"']+")
RE_BIZUM_SEARCH = re.compile(r"https://checkout\.stripe\.com/c/[^\s\"']+")
RE_BLIK_URL = re.compile(r"^https://[^\s\"']+")
RE_TWINT_URL = re.compile(r"^https://[^\s\"']+")
# Wallet channel (wallet_adapter transplant): gcash=Adyen, grabpay=Grab, qris=Midtrans
RE_GCASH_URL = re.compile(r"^https://checkoutshopper-live\.adyen\.com/[^\s\"']+")
RE_GCASH_SEARCH = re.compile(r"https://checkoutshopper[^\"'\s<>]+adyen\.com/[^\s\"']+")
RE_GRABPAY_URL = re.compile(r"^https://[^\s\"']*(?:grab\.com|grabpay\.com)[^\s\"']*", re.I)
RE_GRABPAY_SEARCH = re.compile(r"https://[^\s\"']*(?:grab\.com|grabpay\.com)[^\s\"']*", re.I)
RE_QRIS_URL = re.compile(r"^https://[^\s\"']*(?:midtrans|snap)[^\s\"']*", re.I)
RE_QRIS_SEARCH = re.compile(r"https://[^\s\"']*(?:midtrans|snap)[^\s\"']*", re.I)


def _pm_type(branch: str) -> str:
    return {
        "paypal": "paypal",
        "momo": "momo",
        "pix": "pix",
        "ideal": "ideal",
        "upi": "upi",
        "kakao": "kakao",
        "blik": "blik",
        "twint": "twint",
        "bizum": "bizum",
        "gopay": "gopay",
        "naver_pay": "naver_pay",
        "gcash": "gcash",
        "grabpay": "grabpay",
        "qris": "gopay",  # qris exist Stripe Side to side gopay PM Seed establishment (midtrans charge branch)
        "grok": "card",
        "direct": "card",  # Straight card chain: none Stripe PM, only output checkout short link
    }.get(branch, branch)


def _pm_extra(branch: str, country: str = "") -> dict[str, str]:
    """PM body extra fields（by branch）。"""
    if branch == "pix":
        # pix-core-open-source: billing_details[tax_id] put CPF (The caller has generated a valid CPF)
        from .link_helpers import generate_valid_cpf

        cpf = generate_valid_cpf()
        return {"billing_details[tax_id]": cpf}
    return {}


def _resolve_regexes(branch: str) -> tuple[re.Pattern | None, re.Pattern | None]:
    """return (success_re, search_re)。"""
    if branch == "paypal":
        return RE_PAYPAL_BA, RE_PAYPAL_BA_SEARCH
    if branch == "momo":
        return RE_MOMO_PAY, RE_MOMO_PAY_SEARCH
    if branch == "upi":
        return RE_UPI_URL, RE_UPI_URL_SEARCH
    if branch == "direct":
        return RE_DIRECT_LINK, RE_DIRECT_LINK
    if branch == "pix":
        return RE_PIX_URL, RE_PIX_QR
    if branch == "kakao":
        return RE_KAKAO_URL, RE_KAKAO_URL
    if branch == "naver_pay":
        return RE_NAVER_URL, RE_NAVER_URL
    if branch == "gopay":
        return RE_GOPAY_URL, RE_GOPAY_URL
    if branch == "qris":
        return RE_QRIS_URL, RE_QRIS_SEARCH
    if branch == "gcash":
        return RE_GCASH_URL, RE_GCASH_SEARCH
    if branch == "grabpay":
        return RE_GRABPAY_URL, RE_GRABPAY_SEARCH
    if branch == "bizum":
        # bizum No channel jump (await_authorization), output hosted checkout Page by user
        # Done on mobile Bizum Authorize; extract_redirect Get to the bottom of everything stripe_hosted_url
        return RE_BIZUM_URL, RE_BIZUM_SEARCH
    if branch == "ideal":
        return RE_IDEAL_URL, RE_IDEAL_URL
    if branch == "blik":
        return RE_BLIK_URL, RE_BLIK_URL
    if branch == "twint":
        return RE_TWINT_URL, RE_TWINT_URL
    return RE_IDEAL_URL, RE_IDEAL_URL


def branch_profile(branch: str) -> dict[str, Any]:
    """Return to branch image dict。"""
    b = str(branch or "paypal").lower()
    success_re, search_re = _resolve_regexes(b)
    return {
        "branch": b,
        "pm_type": _pm_type(b),
        "confirm_type": _pm_type(b),
        "pm_extra": _pm_extra(b),
        "resolve_re": success_re,
        "resolve_search_re": search_re,
        "output_key": "paypal_approve_url" if b == "paypal" else "payment_url",
        "require_ba": b == "paypal",
        "referrer": "https://chatgpt.com",
        # checkout Whether to bring promo_campaign: All links checkout Without promo (Get the real channel first),
        # update segment reinjection promo press 0 Yuan (upl-main Full link "Channel first, pressure later 0" model)
        "checkout_promo": False,
        # update press 0 Is it required after amount_due=0（All links must be pressed 0）
        "require_zero": True,
        # truncation mode: direct exist update press 0 Output after verification checkout short link,
        # not pass Stripe init/provider/approve/poll/resolve
        "truncate_after_update": b == "direct",
    }
