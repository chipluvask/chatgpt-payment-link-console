"""national context CountryContext: Authorized Segment Single Source of Truth (Lift chain country → form/fingerprint/Receive code/Full card linkage)。

Datasheet coverage link available 15 country (BA_COUNTRY_ALIGN_PLAN_20260812 §three)。
Time zone offset does not store dead values, Used during runtime zoneinfo calculate (DST Drift safe)。

Usage:
    from paypal.country_profile import country_context, apply_profile_overrides
    ctx = country_context("TH")
    profile = apply_profile_overrides(dict(BROWSER_PROFILE), ctx)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo

# =============================================================================
# Country static mapping table (Chain available 15 country)
# =============================================================================
# Field: locale / language / timezone(IANA) / lang(2letter) / phone(+prefix) /
#        smsbower_id(digital country code, already 2026-08-12 use getPricesV3 Complete 15 National actual test backfill) /
#        currency / proxy_supported(711 whitelist) / sms_supported(All tested and in stock)
_COUNTRY_MAP: dict[str, dict] = {
    "US": dict(locale="en_US", language="en-US", timezone="America/New_York", lang="en",
               phone="+1", smsbower_id="12", currency="USD", proxy_supported=True, sms_supported=True),
    "GB": dict(locale="en_GB", language="en-GB", timezone="Europe/London", lang="en",
               phone="+44", smsbower_id="16", currency="GBP", proxy_supported=True, sms_supported=True),
    "AU": dict(locale="en_AU", language="en-AU", timezone="Australia/Sydney", lang="en",
               phone="+61", smsbower_id="23", currency="AUD", proxy_supported=True, sms_supported=True),
    "DE": dict(locale="de_DE", language="de-DE", timezone="Europe/Berlin", lang="de",
               phone="+49", smsbower_id="22", currency="EUR", proxy_supported=True, sms_supported=True),
    "JP": dict(locale="ja_JP", language="ja-JP", timezone="Asia/Tokyo", lang="ja",
               phone="+81", smsbower_id="40", currency="JPY", proxy_supported=True, sms_supported=True),
    "TH": dict(locale="th_TH", language="th-TH", timezone="Asia/Bangkok", lang="th",
               phone="+66", smsbower_id="34", currency="THB", proxy_supported=True, sms_supported=True),
    "NL": dict(locale="nl_NL", language="nl-NL", timezone="Europe/Amsterdam", lang="nl",
               phone="+31", smsbower_id="15", currency="EUR", proxy_supported=True, sms_supported=True),
    "VN": dict(locale="vi_VN", language="vi-VN", timezone="Asia/Ho_Chi_Minh", lang="vi",
               phone="+84", smsbower_id="8", currency="VND", proxy_supported=True, sms_supported=True),
    "BH": dict(locale="ar_BH", language="en-BH", timezone="Asia/Bahrain", lang="en",
               phone="+973", smsbower_id="39", currency="BHD", proxy_supported=True, sms_supported=True),
    "AO": dict(locale="pt_AO", language="pt-AO", timezone="Africa/Luanda", lang="pt",
               phone="+244", smsbower_id="36", currency="AOA", proxy_supported=True, sms_supported=True),
    "AE": dict(locale="ar_AE", language="en-AE", timezone="Asia/Dubai", lang="en",
               phone="+971", smsbower_id="21", currency="AED", proxy_supported=True, sms_supported=True),
    "CI": dict(locale="fr_CI", language="fr-CI", timezone="Africa/Abidjan", lang="fr",
               phone="+225", smsbower_id="32", currency="XOF", proxy_supported=True, sms_supported=True),
    "TR": dict(locale="tr_TR", language="tr-TR", timezone="Europe/Istanbul", lang="tr",
               phone="+90", smsbower_id="27", currency="TRY", proxy_supported=True, sms_supported=True),
    "BR": dict(locale="pt_BR", language="pt-BR", timezone="America/Sao_Paulo", lang="pt",
               phone="+55", smsbower_id="73", currency="BRL", proxy_supported=True, sms_supported=True),
    "KR": dict(locale="ko_KR", language="ko-KR", timezone="Asia/Seoul", lang="ko",
               phone="+82", smsbower_id="14", currency="KRW", proxy_supported=True, sms_supported=True),
}

# Actual measured price for receiving the code (2026-08-12, service=ts, USD): BR 0.004 / VN 0.012 / KR 0.014 /
# GB 0.021 / US 0.024 / BH 0.09 / DE 0.124 / NL 0.142 / AO 0.142 / AU 0.187 /
# TH 0.187 / AE 0.187 / CI 0.187 / TR 0.187 / JP 0.357 — budget advice >= 0.05 Start
SMS_PRICE_DEFAULT = "0.05"

# 711 Residential Agent Support Near 200 country (region Parameters: Construct available links in any country, And there is sing-box/QG reveal all the details),
# no longer used 10 country whitelist — front end"No proxy"lay ashes to 711 The complete set shall prevail。
_SUPPORTED_COUNTRIES: frozenset[str] = frozenset({
    # Main country (Actual measurement/Commonly used)
    "US", "GB", "CA", "AU", "DE", "FR", "JP", "SG", "NL", "BR",
    # 711 region Already supported (close 200 Commonly used subsets in junior high schools, Also available in other countries)
    "TH", "VN", "BH", "AO", "AE", "CI", "TR", "KR", "MX", "ID", "PH",
    "MY", "IN", "PK", "BD", "LK", "NP", "HK", "TW", "CN", "MO", "KR",
    "AR", "CL", "CO", "PE", "UY", "PY", "EC", "VE", "BO", "CR", "PA",
    "DO", "GT", "HN", "NI", "SV", "JM", "TT", "CU",
    "BE", "AT", "CH", "IE", "IT", "ES", "PT", "SE", "NO", "DK", "FI",
    "PL", "CZ", "SK", "HU", "RO", "BG", "GR", "HR", "SI", "EE", "LV",
    "LT", "UA", "RU", "BY", "KZ", "UZ", "GE", "AM", "AZ", "MD", "RS",
    "BA", "MK", "AL", "IS", "LU", "MT", "CY",
    "ZA", "EG", "MA", "DZ", "TN", "NG", "GH", "KE", "TZ", "UG", "ET",
    "SN", "CM", "CD", "ZW", "ZM", "MZ", "MW", "BW", "NA", "MU", "SC",
    "SA", "QA", "KW", "OM", "JO", "LB", "IL", "IQ", "YE", "SY", "AF",
    "UZ", "TJ", "KG", "MN", "KH", "LA", "MM", "BT", "MV", "BN", "TL",
    "FJ", "PG", "NZ", "GU",
})

# Email domain name pool for each country (Domain names are national signals, like uol.com.br Not for use in other countries)
_EMAIL_DOMAINS: dict[str, list[str]] = {
    "US": ["gmail.com", "outlook.com", "yahoo.com", "hotmail.com", "icloud.com", "protonmail.com"],
    "GB": ["gmail.com", "outlook.com", "hotmail.co.uk", "yahoo.co.uk", "icloud.com", "btinternet.com"],
    "AU": ["gmail.com", "outlook.com", "yahoo.com.au", "hotmail.com", "icloud.com", "bigpond.com"],
    "DE": ["gmx.de", "web.de", "gmail.com", "outlook.de", "yahoo.de", "t-online.de"],
    "JP": ["gmail.com", "yahoo.co.jp", "icloud.com", "outlook.jp", "docomo.ne.jp", "ezweb.ne.jp"],
    "TH": ["gmail.com", "hotmail.com", "yahoo.com", "outlook.com", "icloud.com", "mail.com"],
    "NL": ["gmail.com", "outlook.com", "hotmail.com", "ziggo.nl", "kpnmail.nl", "icloud.com"],
    "VN": ["gmail.com", "yahoo.com", "outlook.com", "hotmail.com", "mail.com", "zoho.com"],
    "BH": ["gmail.com", "hotmail.com", "outlook.com", "batelco.com.bh", "yahoo.com", "icloud.com"],
    "AO": ["gmail.com", "hotmail.com", "yahoo.com", "outlook.com", "netcabo.co.ao", "mail.com"],
    "AE": ["gmail.com", "hotmail.com", "outlook.com", "yahoo.com", "etisalat.ae", "icloud.com"],
    "CI": ["gmail.com", "yahoo.fr", "hotmail.com", "outlook.com", "icloud.com", "afribone.net"],
    "TR": ["gmail.com", "hotmail.com", "outlook.com", "yahoo.com", "yandex.com", "icloud.com"],
    "KR": ["gmail.com", "naver.com", "hanmail.net", "nate.com", "outlook.com", "kakao.com"],
    "BR": ["gmail.com", "hotmail.com", "outlook.com", "yahoo.com.br", "icloud.com", "bol.com.br"],
}

# Address pool per country: (city, state, postal_samples, street_samples, line2_policy)
# line2_policy: "district"(Brazil bairro) / "apartment"(Apartment number) / "empty"(none)
_ADDRESSES: dict[str, dict] = {
    "US": dict(city="New York", state="NY", postal=("10001", "10013", "10022", "10128"),
               streets=("350 5th Ave", "215 W 34th St", "10 E 33rd St", "55 W 25th St"), line2_policy="apartment"),
    "GB": dict(city="London", state="London", postal=("SW1A 1AA", "E1 6AN", "W1T 4DH", "EC2A 4NE"),
               streets=("10 Downing Street", "221B Baker Street", "1 Broadgate", "45 Fleet Street"), line2_policy="apartment"),
    "AU": dict(city="Sydney", state="NSW", postal=("2000", "2010", "2027", "2031"),
               streets=("1 Macquarie St", "5 Martin Place", "100 George St", "25 Pitt St"), line2_policy="apartment"),
    "DE": dict(city="Berlin", state="Berlin", postal=("10115", "10117", "10245", "10437"),
               streets=("Invalidenstrasse 1", "Unter den Linden 10", "Friedrichstrasse 44", "Torstrasse 88"), line2_policy="empty"),
    "JP": dict(city="Tokyo", state="Tokyo", postal=("100-0001", "150-0002", "104-0061", "160-0022"),
               streets=("1-1 Chiyoda", "2-10-1 Ginza", "3-25-3 Shibuya", "4-8-1 Shinjuku"), line2_policy="empty"),
    "TH": dict(city="Bangkok", state="Bangkok", postal=("10110", "10330", "10400", "10500"),
               streets=("1 Sukhumvit Rd", "22 Ratchadamri Rd", "89 Silom Rd", "45 Phayathai Rd"), line2_policy="apartment"),
    "NL": dict(city="Amsterdam", state="Noord-Holland", postal=("1011 AC", "1012 JS", "1016 EA", "1077 XV"),
               streets=("Damrak 1", "Kalverstraat 20", "Leidseplein 8", "Prinsengracht 263"), line2_policy="apartment"),
    "VN": dict(city="Ho Chi Minh City", state="Ho Chi Minh City", postal=("70000", "71000", "72000", "73000"),
               streets=("1 Nguyen Hue", "10 Le Loi", "25 Dong Khoi", "88 Hai Ba Trung"), line2_policy="apartment"),
    "BH": dict(city="Manama", state="Manama", postal=("300", "316", "338", "404"),
               streets=("1 Government Ave", "15 Diplomatic Area", "26 Salman Ave", "40 Hoora Rd"), line2_policy="apartment"),
    "AO": dict(city="Luanda", state="Luanda", postal=("1000", "2000", "3000", "4000"),
               streets=("1 Marginal", "12 Av 4 de Fevereiro", "30 Rua Amilcar Cabral", "55 Rua da Missao"), line2_policy="apartment"),
    "AE": dict(city="Dubai", state="Dubai", postal=("00000", "11111", "22222", "33333"),
               streets=("1 Sheikh Zayed Rd", "15 Jumeirah Beach Rd", "36 Al Wasl Rd", "70 Trade Centre Rd"), line2_policy="apartment"),
    "CI": dict(city="Abidjan", state="Abidjan", postal=("01 BP 1", "02 BP 2", "03 BP 3", "04 BP 4"),
               streets=("1 Ave de la Republique", "12 Rue du Commerce", "28 Bd de Marseille", "50 Rue des Jardins"), line2_policy="apartment"),
    "TR": dict(city="Istanbul", state="Istanbul", postal=("34000", "34110", "34433", "34710"),
               streets=("1 Istiklal Cd", "20 Bagdat Cd", "45 Barbaros Blv", "70 Ataturk Blv"), line2_policy="apartment"),
    "KR": dict(city="Seoul", state="Seoul", postal=("04524", "06030", "07325", "100-011"),
               streets=("1 Jong-ro", "12 Gangnam-daero", "30 Teheran-ro", "55 Yulgok-ro"), line2_policy="apartment"),
    "BR": dict(city="Sao Paulo", state="SP", postal=("01310-100", "01311-001", "04538-133", "05407-002"),
               streets=("Av Paulista 1000", "Rua Augusta 2000", "Alameda Santos 1300", "Av Brigadeiro Faria Lima 3000"), line2_policy="district"),
}


# Windows none tzdata Package time zoneinfo throw KeyError, Using static datum offsets (Downgrade only for failure, Not blocking)
_TZ_OFFSET_FALLBACK: dict[str, int] = {
    "America/New_York": -300, "Europe/London": 0, "Australia/Sydney": 600,
    "Europe/Berlin": 60, "Asia/Tokyo": 540, "Asia/Bangkok": 420,
    "Europe/Amsterdam": 60, "Asia/Ho_Chi_Minh": 420, "Asia/Bahrain": 180,
    "Africa/Luanda": 60, "Asia/Dubai": 240, "Africa/Abidjan": 0,
    "Europe/Istanbul": 180, "America/Sao_Paulo": 180, "Asia/Seoul": 540,
}


def _tz_offset_minutes(tz_name: str, at: Optional[datetime] = None) -> int:
    """of the current moment UTC offset (minute)。priority IANA+zoneinfo Runtime calculation (DST automatic), Fallback static value on failure。"""
    try:
        zone = ZoneInfo(tz_name)
        dt = at or datetime.now(zone)
        offset = dt.utcoffset()
        return int(offset.total_seconds() // 60) if offset is not None else 0
    except Exception:
        return _TZ_OFFSET_FALLBACK.get(tz_name, 0)


def smsbower_country_id(country: str) -> str:
    """Digital country code of receiving code platform (Contains * Push valuation, Used when implementing getPricesV3 Measured backfill)。"""
    entry = _COUNTRY_MAP.get((country or "").upper())
    if not entry:
        raise KeyError(f"unsupported country: {country}")
    return str(entry["smsbower_id"]).rstrip("*")


def sms_supported(country: str) -> bool:
    entry = _COUNTRY_MAP.get((country or "").upper())
    if not entry:
        return False
    return bool(entry.get("sms_supported")) and not str(entry.get("smsbower_id") or "").endswith("*")


def proxy_supported(country: str) -> bool:
    c = (country or "").upper()
    return c in _SUPPORTED_COUNTRIES


def email_domains(country: str) -> list[str]:
    return list(_EMAIL_DOMAINS.get((country or "").upper(), _EMAIL_DOMAINS["US"]))


def address_pool(country: str) -> dict:
    entry = _ADDRESSES.get((country or "").upper())
    if not entry:
        raise KeyError(f"unsupported country: {country}")
    return entry


# =============================================================================
# CountryContext
# =============================================================================


@dataclass(frozen=True)
class CountryContext:
    country: str                        # ISO2, For example "US" / "JP" / "TH"
    kyc_fields: list                    # Form field whitelist
    id_types: list                      # Optional document types
    locale: str                         # "en_US" / "ja_JP" ...
    language: str                       # "en-US" / "ja-JP" ...
    timezone: str                       # IANA name
    tz_offset_minutes: int              # Runtime calculation (DST Safety)
    lang: str                           # 2alphabetic language (weasley/analytics)
    currency: str                       # Currency
    phone_country: str                  # Mobile phone number country prefix "+1"
    sms_country_id: str                 # Digital country code of receiving code platform
    proxy_country: str                  # acting region (711 Same name)
    proxy_supported: bool = True        # 711 Direct connection availability (For front-end dust removal)
    sms_supported: bool = True          # Code receiving platform support (For front-end dust removal)
    extra: dict = field(default_factory=dict)


def country_context(country: str) -> CountryContext:
    """Assemble country context。kyc_fields/id_types Lazy loading from identity_lib (Avoid circular imports)。"""
    cc = (country or "").strip().upper()
    entry = _COUNTRY_MAP.get(cc)
    if not entry:
        raise KeyError(f"unsupported country: {cc}")
    fields: list = []
    id_types: list = []
    try:
        from paypal.identity_lib import profile_summary
        summary = profile_summary(cc)
        fields = list(summary.get("fields") or [])
        id_types = list(summary.get("id_types") or [])
    except Exception:
        fields = ["DateOfBirth", "Nationality"]
        id_types = []
    return CountryContext(
        country=cc,
        kyc_fields=fields,
        id_types=id_types,
        locale=entry["locale"],
        language=entry["language"],
        timezone=entry["timezone"],
        tz_offset_minutes=_tz_offset_minutes(entry["timezone"]),
        lang=entry["lang"],
        currency=entry["currency"],
        phone_country=entry["phone"],
        sms_country_id=str(entry["smsbower_id"]).rstrip("*"),
        proxy_country=cc,
        proxy_supported=proxy_supported(cc),
        sms_supported=sms_supported(cc),
    )


def apply_profile_overrides(profile: dict, ctx: CountryContext) -> dict:
    """Put national context into fingerprints profile (BROWSER_PROFILE Derived copy)。

    Only country-related signals are covered, hardware signal (GPU/webgl/deviceMemory...) retain template value。
    """
    out = dict(profile or {})
    out.update(
        country=ctx.country,
        language=ctx.language,
        locale=ctx.locale,
        timezone=ctx.timezone,
        timezone_offset_minutes=ctx.tz_offset_minutes,
        timezone_offset_ms=ctx.tz_offset_minutes * 60 * 1000,
    )
    return out


def available() -> list[str]:
    return sorted(_COUNTRY_MAP.keys())