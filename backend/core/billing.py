"""State Bill Template + Qingguo Tunnel proxy connection string structure。

Data comes from the original config.py / geo_data / name_data / qg_area_codes（Already inline，Remove external dependencies）。
for all ALL_COUNTRIES generate"Close to exporting countries"of payment_method billing_details template。

Connection string format（Specify country，Change every request IP）：
    http://{authKey}:{authPwd}:A{areaCode}@overseas.tunnel.qg.net:{port}
"""
from __future__ import annotations

from typing import Any

from .config import settings

# --- Qingguo Tunnel Overseas Area Code (area_code) Featured table ---
# whole 218 country from https://www.qg.net/doc/1975.html；Inline mainstream here 40 country。
AREA_CODES: dict[str, int] = {
    "US": 8, "GB": 2, "JP": 9, "HK": 11, "SG": 14, "KR": 16, "TW": 17,
    "AU": 13, "CA": 6, "DE": 21, "FR": 23, "NL": 27, "IE": 33, "BE": 34,
    "BR": 41, "MX": 43, "AR": 44, "CL": 45, "TH": 51, "VN": 52, "ID": 53,
    "MY": 54, "PH": 55, "IN": 56, "NZ": 61, "IT": 66, "ES": 67, "PT": 68,
    "SE": 71, "NO": 72, "DK": 73, "FI": 74, "CH": 76, "AT": 77, "PL": 81,
    "TR": 91, "AE": 101, "SA": 102, "IL": 103, "ZA": 111, "EG": 112,
}

# --- PayPal Not supported / Risk control blacklist of high-risk countries (OFAC + PayPal) ---
PAYPAL_BLOCKED: frozenset[str] = frozenset({
    "IR", "SY", "KP", "CU", "SD", "SS", "SO", "YE", "LY", "AF", "MM", "BY", "RU",
})

# --- whole ISO 3166 Country table (216 country, Same origin as the front-end country drop-down) ---
# used for: Full coverage of bill templates + Front-end country selection (auto + 200+ nation)
ISO_COUNTRIES: list[str] = (
    "AD,AE,AF,AG,AI,AL,AM,AO,AR,AS,AT,AU,AW,AZ,BA,BB,BD,BE,BF,BG,BH,BI,BJ,BL,BM,BN,"
    "BO,BR,BS,BT,BW,BY,BZ,CA,CD,CF,CG,CH,CI,CK,CL,CM,CO,CR,CU,CV,CW,CY,CZ,DE,DJ,DK,"
    "DM,DO,DZ,EC,EE,EG,ER,ES,ET,EU,FI,FJ,FO,FR,GA,GB,GD,GE,GF,GH,GI,GL,GM,GN,GP,GQ,"
    "GR,GT,GU,GW,GY,HK,HN,HR,HT,HU,ID,IE,IL,IN,IQ,IR,IS,IT,JM,JO,JP,KE,KG,KH,KI,KM,"
    "KN,KR,KW,KY,KZ,LA,LB,LC,LI,LK,LR,LS,LT,LU,LV,LY,MA,MC,MD,ME,MG,MK,ML,MM,MN,MO,"
    "MQ,MR,MS,MT,MU,MV,MW,MX,MY,MZ,NA,NC,NE,NG,NI,NL,NO,NP,NZ,OM,PA,PE,PF,PG,PH,PK,"
    "PL,PM,PR,PT,PW,PY,QA,RE,RO,RS,RU,RW,SA,SB,SC,SD,SE,SG,SI,SK,SL,SM,SN,SO,SR,ST,"
    "SV,SX,SY,SZ,TC,TD,TG,TH,TJ,TL,TM,TN,TO,TR,TT,TW,TZ,UA,UG,US,UY,UZ,VC,VE,VG,VI,"
    "VN,VU,WS,YE,YT,ZA,ZM,ZW"
).split(",")

# All candidate countries: ISO Full table + AREA_CODES union, exclude blacklist
ALL_COUNTRIES: list[str] = sorted(
    set(ISO_COUNTRIES) | set(AREA_CODES) - set(PAYPAL_BLOCKED)
)

# --- geographical data: (capital, Zip code sample, Currency) ---
GEO: dict[str, tuple[str, str, str]] = {
    "US": ("New York", "10001", "USD"),
    "GB": ("London", "SW1A 1AA", "GBP"),
    "JP": ("Tokyo", "100-0001", "JPY"),
    "HK": ("Hong Kong", "999077", "HKD"),
    "SG": ("Singapore", "048583", "SGD"),
    "KR": ("Seoul", "04524", "KRW"),
    "TW": ("Taipei", "100", "TWD"),
    "AU": ("Canberra", "2600", "AUD"),
    "CA": ("Ottawa", "K1A 0B1", "CAD"),
    "DE": ("Berlin", "10115", "EUR"),
    "FR": ("Paris", "75001", "EUR"),
    "NL": ("Amsterdam", "1011 AC", "EUR"),
    "IE": ("Dublin", "D01 F5P2", "EUR"),
    "BE": ("Brussels", "1000", "EUR"),
    "BR": ("Brasilia", "70040", "BRL"),
    "MX": ("Mexico City", "01000", "MXN"),
    "AR": ("Buenos Aires", "C1000", "ARS"),
    "CL": ("Santiago", "8320000", "CLP"),
    "TH": ("Bangkok", "10110", "THB"),
    "VN": ("Hanoi", "100000", "VND"),
    "ID": ("Jakarta", "10110", "IDR"),
    "MY": ("Kuala Lumpur", "50000", "MYR"),
    "PH": ("Manila", "1000", "PHP"),
    "IN": ("New Delhi", "110001", "INR"),
    "NZ": ("Wellington", "6011", "NZD"),
    "IT": ("Rome", "00100", "EUR"),
    "ES": ("Madrid", "28001", "EUR"),
    "PT": ("Lisbon", "1000-001", "EUR"),
    "SE": ("Stockholm", "111 21", "SEK"),
    "NO": ("Oslo", "0150", "NOK"),
    "DK": ("Copenhagen", "1050", "DKK"),
    "FI": ("Helsinki", "00100", "EUR"),
    "CH": ("Bern", "3000", "CHF"),
    "AT": ("Vienna", "1010", "EUR"),
    "PL": ("Warsaw", "00-001", "PLN"),
    "TR": ("Ankara", "06010", "TRY"),
    "AE": ("Abu Dhabi", "00000", "AED"),
    "SA": ("Riyadh", "11564", "SAR"),
    "IL": ("Jerusalem", "9100000", "ILS"),
    "ZA": ("Pretoria", "0001", "ZAR"),
    "EG": ("Cairo", "11511", "EGP"),
}

# --- localized names ---
NAMES: dict[str, str] = {
    "US": "John Smith", "GB": "James Wilson", "JP": "Haruto Sato",
    "HK": "Tai Man Chan", "SG": "Wei Ming Tan", "KR": "Min Jun Kim",
    "TW": "Wei Chen", "AU": "Jack Thompson", "CA": "William Brown",
    "DE": "Lukas Mueller", "FR": "Lucas Martin", "NL": "Daan de Vries",
    "IE": "Sean Murphy", "BE": "Luc Dubois", "BR": "Lucas Silva",
    "MX": "Diego Garcia", "AR": "Mateo Gonzalez", "CL": "Benjamin Lopez",
    "TH": "Somchai Jaidee", "VN": "Minh Nguyen", "ID": "Budi Santoso",
    "MY": "Ahmad Rahman", "PH": "Juan Santos", "IN": "Arjun Kumar",
    "NZ": "Oliver Wilson", "IT": "Alessandro Rossi", "ES": "Hugo Garcia",
    "PT": "Joao Silva", "SE": "Erik Andersson", "NO": "Lars Hansen",
    "DK": "Magnus Nielsen", "FI": "Matti Korhonen", "CH": "Luis Keller",
    "AT": "Paul Hofer", "PL": "Jan Kowalski", "TR": "Yusuf Yilmaz",
    "AE": "Ahmed Al Mansoori", "SA": "Abdullah Al Saud", "IL": "David Cohen",
    "ZA": "Thabo Mokoena", "EG": "Omar Hassan",
}

# mainstream 12 National real landmark street address；For other purposes "1 {capital} Main Street" Placeholder
_OVERRIDE_LINE1: dict[str, str] = {
    "US": "350 5th Ave", "AU": "1 Macquarie St", "GB": "10 Downing Street",
    "NL": "Damrak 1", "DE": "Invalidenstrasse 1", "FR": "10 Rue de Rivoli",
    "IE": "1 O'Connell Street", "BE": "Rue Neuve 1", "JP": "1-1 Chiyoda",
    "BR": "Av Paulista 1000", "HK": "1 Queens Road Central", "MO": "Av da Amizade 1",
}


def _build_billing_templates() -> dict[str, dict[str, str]]:
    templates: dict[str, dict[str, str]] = {}
    for ctry in ALL_COUNTRIES:
        geo = GEO.get(ctry)
        if geo is None:
            # lack GEO country: Use the country code to find out (The bill template still needs to be submitted)
            capital, postal, _currency = ctry, "00000", "USD"
        else:
            capital, postal, _currency = geo
        name = NAMES.get(ctry, "John Doe")
        line1 = _OVERRIDE_LINE1.get(ctry, f"1 {capital} Main Street")
        templates[ctry] = {
            "country": ctry,
            "city": capital,
            "state": capital,
            "postal_code": postal,
            "line1": line1,
            "name": name,
        }
    if "US" not in templates:
        templates["US"] = {
            "country": "US", "city": "New York", "state": "NY",
            "postal_code": "10001", "line1": "350 5th Ave", "name": "John Doe",
        }
    return templates


BILLING_TEMPLATES: dict[str, dict[str, str]] = _build_billing_templates()

# checkout business country/currency matrix
CHECKOUT_MATRIX: list[tuple[str, str]] = [
    ("US", "USD"),
    ("AU", "AUD"),
]

# billing country -> Currency (GEO No. 3 List)
_BILLING_CURRENCY: dict[str, str] = {}
for _c, (_cap, _pc, _cur) in GEO.items():
    if _cur:
        _BILLING_CURRENCY[_c] = _cur

# Eurozone (official use EUR): European Union Eurozone 20 country + small country that adopts unilaterally
_EUR_COUNTRIES: frozenset[str] = frozenset({
    "AD", "AT", "BE", "CY", "DE", "EE", "ES", "FI", "FR", "GR", "HR", "IE",
    "IT", "LT", "LU", "LV", "MC", "ME", "MT", "NL", "PT", "SI", "SK", "SM", "VA",
})

# non-euro countries ISO 4217 Currency table (GEO Coverage for countries not covered, Old _EUR_COUNTRIES countries that mistakenly belong to the euro area)
CURRENCY_BY_COUNTRY: dict[str, str] = {
    "AF": "AFN", "AL": "ALL", "AM": "AMD", "AO": "AOA", "AR": "ARS", "AW": "AWG",
    "AZ": "AZN", "BA": "BAM", "BB": "BBD", "BD": "BDT", "BG": "BGN", "BH": "BHD",
    "BI": "BIF", "BM": "BMD", "BN": "BND", "BO": "BOB", "BS": "BSD", "BT": "BTN",
    "BW": "BWP", "BY": "BYN", "BZ": "BZD", "CD": "CDF", "CF": "XAF", "CG": "XAF",
    "CM": "XAF", "CN": "CNY", "CO": "COP", "CR": "CRC", "CU": "CUP", "CV": "CVE",
    "CW": "ANG", "CZ": "CZK", "DJ": "DJF", "DO": "DOP", "DZ": "DZD", "EG": "EGP",
    "ER": "ERN", "ET": "ETB", "FO": "DKK", "FJ": "FJD", "GA": "XAF", "GE": "GEL",
    "GH": "GHS", "GI": "GIP", "GL": "DKK", "GM": "GMD", "GN": "GNF", "GQ": "XAF",
    "GT": "GTQ", "GY": "GYD", "HN": "HNL", "HT": "HTG", "HU": "HUF", "IQ": "IQD",
    "IR": "IRR", "IS": "ISK", "JM": "JMD", "JO": "JOD", "KE": "KES", "KG": "KGS",
    "KH": "KHR", "KM": "KMF", "KW": "KWD", "KY": "KYD", "KZ": "KZT", "LA": "LAK",
    "LB": "LBP", "LI": "CHF", "LK": "LKR", "LR": "LRD", "LS": "LSL", "LY": "LYD",
    "MA": "MAD", "MD": "MDL", "MG": "MGA", "MK": "MKD", "MM": "MMK", "MN": "MNT",
    "MO": "MOP", "MR": "MRU", "MU": "MUR", "MV": "MVR", "MW": "MWK", "MZ": "MZN",
    "NA": "NAD", "NG": "NGN", "NI": "NIO", "NP": "NPR", "OM": "OMR", "PA": "PAB",
    "PE": "PEN", "PG": "PGK", "PK": "PKR", "PY": "PYG", "QA": "QAR", "RO": "RON",
    "RS": "RSD", "RU": "RUB", "RW": "RWF", "SB": "SBD", "SC": "SCR", "SD": "SDG",
    "SH": "SHP", "SL": "SLL", "SO": "SOS", "SR": "SRD", "SS": "SSP", "ST": "STN",
    "SV": "SVC", "SY": "SYP", "SZ": "SZL", "TJ": "TJS", "TM": "TMT", "TN": "TND",
    "TO": "TOP", "TT": "TTD", "TZ": "TZS", "UA": "UAH", "UG": "UGX", "UY": "UYU",
    "UZ": "UZS", "VE": "VES", "VU": "VUV", "WS": "WST", "YE": "YER", "ZM": "ZMW",
    "ZW": "ZWL",
    # West African CFA Franc / east caribbean dollar / Pacific franc zone
    "BJ": "XOF", "BF": "XOF", "CI": "XOF", "GW": "XOF", "ML": "XOF",
    "NE": "XOF", "SN": "XOF", "TG": "XOF",
    "AG": "XCD", "AI": "XCD", "DM": "XCD", "GD": "XCD", "KN": "XCD",
    "LC": "XCD", "MS": "XCD", "VC": "XCD",
    "PF": "XPF", "NC": "XPF", "WF": "XPF",
}


def billing_currency(country: str) -> str:
    """The currency corresponding to the billing country (US->USD, AU->AUD, Eurozone->EUR, The rest press GEO/ISO 4217), Unknown fallback USD。"""
    c = (country or "").upper()
    if c == "US":
        return "USD"
    if c == "AU":
        return "AUD"
    if c in _EUR_COUNTRIES:
        return "EUR"
    if c in _BILLING_CURRENCY:
        return _BILLING_CURRENCY[c]
    if c in CURRENCY_BY_COUNTRY:
        return CURRENCY_BY_COUNTRY[c]
    for cc, cur in CHECKOUT_MATRIX:
        if cc == c:
            return cur
    return "USD"


def billing_for(country: str, auto: bool = True, fallback: str = "US") -> dict[str, str]:
    """Return billing address based on export country。

    auto=True:  The bill is close to the exporting country。
    auto=False: according to fallback country。
    Fallback if any country is missing US。
    """
    key = (country or fallback).upper()
    return dict(BILLING_TEMPLATES.get(key) or BILLING_TEMPLATES[fallback])


def tunnel_proxy(country: str, pool: str | None = None) -> str:
    """Construct Qingguo Tunnel proxy connection string（Specify country，Change every request IP）。"""
    if pool is None:
        pool = settings.default_pool_name
    p = settings.qg_pool(pool)
    if not p:
        p = settings.qg_pool("qg_resi_pool")
    area = AREA_CODES.get((country or "").upper())
    if area is None:
        raise ValueError(f"unknown country area_code: {country}")
    return f"http://{p['auth_key']}:{p['auth_pwd']}:A{area}@{p['host']}:{p['port']}"


def list_billing_templates() -> list[dict[str, str]]:
    """Return to the list of all bill templates（for /api/billing/templates）。"""
    return [dict(v, country=k) for k, v in sorted(BILLING_TEMPLATES.items())]
