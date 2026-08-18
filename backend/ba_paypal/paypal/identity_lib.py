"""PayPal Registration form field generation library for each country (Classified by country, Check digit algorithm alignment official/public implementation)。

in accordance with:
- front end bundle main_*.js of kycFields Configuration (gj/_js/main_72d757f6c90e0b683d47_js.js)
- Public verification algorithms for national identity numbers (Thailand mod-11 / United Arab Emirates Luhn / South Korea RRN Weighted mod-11 /
  South Africa Luhn / Argentina CUIT mod-11 / Mexico CURP base37 mod-10 / Vietnam CCCD structure /
  Bahrain CPR Format, Verification is not public, only the format / Brazil CPF mod-11 / Germany IBAN mod-97)
- len(field value) with form maxlength consistent, dateOfBirth use 18+ legal date
"""

from __future__ import annotations

import calendar
from datetime import date
import random
from dataclasses import dataclass, field
from typing import Callable, Optional

# =============================================================================
# Universal check digit tool
# =============================================================================


def _luhn_check_digit(partial: str) -> int:
    """Luhn (mod-10) Check digit: from right to left, Multiply by space 2, >9 reduce 9, sum complement 0/10。"""
    total = 0
    alternate = True
    for ch in reversed(partial):
        d = int(ch)
        if alternate:
            d *= 2
            if d > 9:
                d -= 9
        total += d
        alternate = not alternate
    return 0 if total % 10 == 0 else 10 - (total % 10)


def _verify_luhn(number: str) -> bool:
    total = 0
    alternate = False
    for ch in reversed(number):
        d = int(ch)
        if alternate:
            d *= 2
            if d > 9:
                d -= 9
        total += d
        alternate = not alternate
    return total % 10 == 0


def _mod11_check_digit(base: str, weights) -> tuple[int, int]:
    """mold-11 check: sum(d_i*w_i) mod 11; return (remainder, candidate)。"""
    total = sum(int(d) * w for d, w in zip(base, weights))
    return total % 11, total


def _mod11_check_digit_v2(base: str, weights) -> int:
    """Thailand PIN: check = (11 - sum%11) % 10。"""
    rem, _ = _mod11_check_digit(base, weights)
    return (11 - rem) % 10


def _mod11_check_digit_kr(base: str) -> int:
    """South Korea RRN: (11 - sum%11) mod 10。"""
    rem, _ = _mod11_check_digit(base, [2, 3, 4, 5, 6, 7, 8, 9, 2, 3, 4, 5])
    return (11 - rem) % 10


def _mod11_check_digit_ar(base: str) -> Optional[int]:
    """Argentina CUIT: weights 5,4,3,2,7,6,5,4,3,2; 11->0, 10->illegal(None)。"""
    rem, _ = _mod11_check_digit(base, [5, 4, 3, 2, 7, 6, 5, 4, 3, 2])
    if rem == 0:
        return 0
    check = 11 - rem
    if check == 11:
        return 0
    if check == 10:
        return None
    return check


def _mod97_iban_check_digits(country: str, bban: str) -> str:
    """ISO 13616 IBAN Check digit (mod-97): DE + check + bban。"""
    rearranged = bban + country + "00"
    number = int("".join(str(int(c, 36)) if c.isalpha() else c for c in rearranged))
    return f"{98 - (number % 97):02d}"


# =============================================================================
# common name/date/Mail
# =============================================================================

_EMAIL_DOMAINS = [
    "gmail.com", "hotmail.com", "outlook.com", "yahoo.com",
    "icloud.com", "protonmail.com", "mail.com",
]


def generate_dob(min_year: int = 1965, max_year: int = 2002, fmt: str = "%d/%m/%Y") -> str:
    """Generate legal birthday of majority (default DD/MM/YYYY, PayPal Forms are usually dd/MM/y)。"""
    year = random.randint(min_year, max_year)
    month = random.randint(1, 12)
    day = random.randint(1, calendar.monthrange(year, month)[1])
    return date(year, month, day).strftime(fmt)


def _country_email_domain(country: str) -> Optional[str]:
    """Get email domain name pool by country (national signal), Not included in the country fallback general pool。"""
    try:
        from paypal.country_profile import email_domains
        return random.choice(email_domains(country))
    except Exception:
        return None


def generate_email(first: str, last: str, domain: Optional[str] = None, country: str = "") -> str:
    d = domain or _country_email_domain(country) or random.choice(_EMAIL_DOMAINS)
    return f"{first.lower().replace(' ', '')}.{last.lower().replace(' ', '')}{random.randint(10, 99999)}@{d}"


def generate_password(min_len: int = 10, max_len: int = 16) -> str:
    lower = "abcdefghijklmnopqrstuvwxyz"
    upper = lower.upper()
    required = "0123456789!@#$%&*"
    chars = lower + upper + required
    length = random.randint(min_len, max_len)
    pwd = [random.choice(required)]
    while len(pwd) < length:
        pwd.append(random.choice(chars))
    random.shuffle(pwd)
    return "".join(pwd)


# =============================================================================
# Country phone numbers/Address generation (National Signal Alignment: Number length/prefix/address semantics)
# =============================================================================

# nation -> (length, First place limited) The country's own country is not entirely accurate but has a realistic structure. (only for signup Contact information display,
# actual 2FA The receiving number comes from the code receiving platform, phone Only with phoneCountry Alignment)。
_PHONE_NATIONAL: dict[str, tuple[int, list[str]]] = {
    "US": (10, ["2", "3", "4", "5", "6", "7", "8", "9"]),
    "GB": (10, ["7"]),            # 07XXXXXXXX move
    "AU": (9, ["4"]),             # 04XXXXXXXX move
    "DE": (10, ["1", "2", "3", "4", "5", "6", "7", "8"]),
    "JP": (10, ["7", "8", "9"]),
    "TH": (9, ["6", "8", "9"]),   # 08/09/06XXXXXXXX
    "NL": (9, ["6"]),
    "VN": (9, ["3", "5", "7", "8", "9"]),
    "BH": (8, ["3", "6"]),
    "AO": (9, ["9"]),
    "AE": (9, ["5"]),             # 05XXXXXXXX
    "CI": (10, ["5", "7", "1"]),
    "TR": (10, ["5"]),            # 05XXXXXXXX
    "BR": (10, ["6", "7", "8", "9", "1"]),   # No area code 9xxxx-xxxx (11 Contains area code)
    "KR": (9, ["1"]),             # 01X-XXX-XXXX
}


def _generate_national_phone(country: str) -> str:
    spec = _PHONE_NATIONAL.get(country.upper(), (10, ["1", "2", "3", "4", "5", "6", "7", "8", "9"]))
    length, firsts = spec
    return random.choice(firsts) + "".join(str(random.randint(0, 9)) for _ in range(length - 1))


def generate_country_address(country: str) -> dict:
    """Generate billing addresses by country (Contains line2 Semantics: district/apartment/empty)。"""
    cc = (country or "").upper()
    try:
        from paypal.country_profile import address_pool
        pool = address_pool(cc)
    except Exception:
        pool = dict(city="New York", state="NY", postal=("10001",),
                    streets=("350 5th Ave",), line2_policy="apartment")
    line1 = random.choice(pool["streets"])
    policy = pool.get("line2_policy", "apartment")
    if policy == "district":
        line2 = f"Centro {random.randint(1, 900)}"
    elif policy == "apartment":
        line2 = f"Apt {random.randint(100, 900)}"
    else:
        line2 = ""
    return {
        "line1": line1,
        "line2": line2,
        "city": pool["city"],
        "state": pool["state"],
        "postal_code": random.choice(pool["postal"]),
        "country": cc,
    }


def generate_country_phone(country: str) -> tuple[str, str]:
    """return (phone_country prefix, complete number)。"""
    cc = (country or "").upper()
    try:
        from paypal.country_profile import _COUNTRY_MAP
        prefix = _COUNTRY_MAP[cc]["phone"]
    except Exception:
        prefix = "+1"
    return prefix, f"{prefix}{_generate_national_phone(cc)}"


# =============================================================================
# National cards BIN pool (bin, length, issuer, product_class, cvv_len)
# =============================================================================

CARD_BINS: dict[str, list[tuple[str, int, str, str, int]]] = {
    # BR Pool expansion (2026-08-14): All from public BIN/IIN Table of contents (bincheck/binx/freebinchecker),
    # cover Banco do Brasil / Itau / Bradesco / Caixa / Santander / Nubank / Inter / Mercado Pago / Wise wait
    "BR": [
        ("414709", 16, "VISA", "CREDIT", 3), ("516292", 16, "MASTER_CARD", "CREDIT", 3),
        ("455187", 16, "VISA", "DEBIT", 3), ("504427", 16, "MASTER_CARD", "DEBIT", 3),
        # Banco do Brasil VISA
        ("400130", 16, "VISA", "CREDIT", 3), ("400162", 16, "VISA", "CREDIT", 3),
        ("400168", 16, "VISA", "CREDIT", 3), ("400174", 16, "VISA", "CREDIT", 3),
        ("400178", 16, "VISA", "CREDIT", 3), ("400184", 16, "VISA", "CREDIT", 3),
        ("400187", 16, "VISA", "CREDIT", 3), ("400191", 16, "VISA", "CREDIT", 3),
        ("400196", 16, "VISA", "CREDIT", 3), ("403792", 16, "VISA", "CREDIT", 3),
        ("403797", 16, "VISA", "CREDIT", 3), ("423072", 16, "VISA", "CREDIT", 3),
        ("448460", 16, "VISA", "CREDIT", 3), ("498401", 16, "VISA", "CREDIT", 3),
        ("498406", 16, "VISA", "CREDIT", 3), ("498407", 16, "VISA", "CREDIT", 3),
        ("498408", 16, "VISA", "CREDIT", 3), ("498442", 16, "VISA", "CREDIT", 3),
        ("498453", 16, "VISA", "CREDIT", 3), ("400102", 16, "VISA", "DEBIT", 3),
        # Itau / Itaucard VISA
        ("400234", 16, "VISA", "CREDIT", 3), ("400235", 16, "VISA", "CREDIT", 3),
        ("400247", 16, "VISA", "CREDIT", 3), ("400253", 16, "VISA", "CREDIT", 3),
        ("400268", 16, "VISA", "CREDIT", 3), ("400635", 16, "VISA", "CREDIT", 3),
        ("403798", 16, "VISA", "CREDIT", 3), ("411049", 16, "VISA", "CREDIT", 3),
        ("417874", 16, "VISA", "CREDIT", 3), ("452407", 16, "VISA", "CREDIT", 3),
        ("459078", 16, "VISA", "CREDIT", 3), ("470598", 16, "VISA", "CREDIT", 3),
        ("489423", 16, "VISA", "CREDIT", 3), ("490172", 16, "VISA", "CREDIT", 3),
        # Bradesco VISA
        ("400453", 16, "VISA", "CREDIT", 3), ("400455", 16, "VISA", "CREDIT", 3),
        ("406655", 16, "VISA", "CREDIT", 3), ("406669", 16, "VISA", "CREDIT", 3),
        ("409603", 16, "VISA", "CREDIT", 3), ("429768", 16, "VISA", "CREDIT", 3),
        ("440693", 16, "VISA", "CREDIT", 3), ("455183", 16, "VISA", "CREDIT", 3),
        # Caixa VISA
        ("400236", 16, "VISA", "CREDIT", 3), ("400957", 16, "VISA", "CREDIT", 3),
        ("421960", 16, "VISA", "CREDIT", 3), ("421961", 16, "VISA", "CREDIT", 3),
        ("426055", 16, "VISA", "CREDIT", 3), ("459383", 16, "VISA", "CREDIT", 3),
        ("474539", 16, "VISA", "CREDIT", 3), ("479395", 16, "VISA", "CREDIT", 3),
        # Santander VISA
        ("401638", 16, "VISA", "CREDIT", 3), ("410863", 16, "VISA", "CREDIT", 3),
        ("422061", 16, "VISA", "CREDIT", 3), ("425850", 16, "VISA", "CREDIT", 3),
        ("441524", 16, "VISA", "CREDIT", 3),
        # other BR card issuing bank VISA
        ("401132", 16, "VISA", "CREDIT", 3), ("401165", 16, "VISA", "CREDIT", 3),
        ("402762", 16, "VISA", "CREDIT", 3), ("407843", 16, "VISA", "CREDIT", 3),
        ("409007", 16, "VISA", "CREDIT", 3), ("415274", 16, "VISA", "CREDIT", 3),
        ("446690", 16, "VISA", "CREDIT", 3),
        # BR Mastercard
        ("222985", 16, "MASTER_CARD", "CREDIT", 3), ("230744", 16, "MASTER_CARD", "CREDIT", 3),
        ("234087", 16, "MASTER_CARD", "CREDIT", 3), ("514945", 16, "MASTER_CARD", "CREDIT", 3),
        ("515590", 16, "MASTER_CARD", "CREDIT", 3), ("521397", 16, "MASTER_CARD", "CREDIT", 3),
        ("525663", 16, "MASTER_CARD", "CREDIT", 3), ("539614", 16, "MASTER_CARD", "CREDIT", 3),
        ("541555", 16, "MASTER_CARD", "CREDIT", 3), ("542820", 16, "MASTER_CARD", "CREDIT", 3),
        ("544731", 16, "MASTER_CARD", "CREDIT", 3), ("550209", 16, "MASTER_CARD", "CREDIT", 3),
        ("552236", 16, "MASTER_CARD", "CREDIT", 3), ("552305", 16, "MASTER_CARD", "CREDIT", 3),
        ("553636", 16, "MASTER_CARD", "CREDIT", 3), ("553647", 16, "MASTER_CARD", "CREDIT", 3),
        ("554281", 16, "MASTER_CARD", "CREDIT", 3), ("554775", 16, "MASTER_CARD", "CREDIT", 3),
        ("554953", 16, "MASTER_CARD", "CREDIT", 3), ("556024", 16, "MASTER_CARD", "CREDIT", 3),
        ("558297", 16, "MASTER_CARD", "CREDIT", 3), ("558383", 16, "MASTER_CARD", "CREDIT", 3),
        ("558645", 16, "MASTER_CARD", "CREDIT", 3), ("556670", 16, "MASTER_CARD", "CREDIT", 3),
        ("554417", 16, "MASTER_CARD", "CREDIT", 3), ("549021", 16, "MASTER_CARD", "CREDIT", 3),
    ],
    # US Pool expansion (2026-08-14): public BIN/IIN Table of contents (binlist.io/bincheck.org/creditcardvalidator/bindb),
    # cover Chase / Bank of America / Wells Fargo / Citibank / Capital One / U.S. Bank / Discover / Amex
    "US": [
        # Chase VISA
        ("414720", 16, "VISA", "CREDIT", 3), ("475050", 16, "VISA", "CREDIT", 3),
        ("401135", 16, "VISA", "CREDIT", 3), ("401136", 16, "VISA", "CREDIT", 3),
        ("402297", 16, "VISA", "CREDIT", 3), ("438857", 16, "VISA", "CREDIT", 3),
        ("436610", 16, "VISA", "CREDIT", 3), ("436611", 16, "VISA", "CREDIT", 3),
        ("436617", 16, "VISA", "CREDIT", 3),
        # Bank of America VISA
        ("414716", 16, "VISA", "CREDIT", 3), ("449533", 16, "VISA", "CREDIT", 3),
        ("401901", 16, "VISA", "CREDIT", 3), ("401902", 16, "VISA", "CREDIT", 3),
        ("402076", 16, "VISA", "CREDIT", 3), ("435680", 16, "VISA", "DEBIT", 3),
        ("435681", 16, "VISA", "DEBIT", 3), ("435682", 16, "VISA", "DEBIT", 3),
        # Wells Fargo VISA
        ("416724", 16, "VISA", "DEBIT", 3), ("434256", 16, "VISA", "DEBIT", 3),
        ("434257", 16, "VISA", "DEBIT", 3), ("473099", 16, "VISA", "DEBIT", 3),
        ("475637", 16, "VISA", "DEBIT", 3), ("400151", 16, "VISA", "DEBIT", 3),
        ("400173", 16, "VISA", "DEBIT", 3), ("400205", 16, "VISA", "DEBIT", 3),
        # Citibank
        ("414711", 16, "VISA", "CREDIT", 3), ("400919", 16, "VISA", "CREDIT", 3),
        ("400927", 16, "VISA", "CREDIT", 3), ("230050", 16, "MASTER_CARD", "DEBIT", 3),
        # Capital One
        ("400344", 16, "VISA", "CREDIT", 3), ("401472", 16, "VISA", "CREDIT", 3),
        ("402265", 16, "VISA", "CREDIT", 3), ("486236", 16, "VISA", "CREDIT", 3),
        ("517805", 16, "MASTER_CARD", "CREDIT", 3),
        # U.S. Bank
        ("408022", 16, "VISA", "DEBIT", 3), ("408845", 16, "VISA", "CREDIT", 3),
        ("408846", 16, "VISA", "CREDIT", 3), ("408847", 16, "VISA", "CREDIT", 3),
        ("436618", 16, "VISA", "DEBIT", 3), ("414780", 16, "VISA", "CREDIT", 3),
        # other US card issuing bank
        ("440319", 16, "VISA", "CREDIT", 3), ("415874", 16, "VISA", "DEBIT", 3),
        ("482870", 16, "VISA", "DEBIT", 3),
        ("553370", 16, "MASTER_CARD", "CREDIT", 3), ("548009", 16, "MASTER_CARD", "CREDIT", 3),
        ("475423", 16, "VISA", "DEBIT", 3), ("475427", 16, "VISA", "DEBIT", 3),
        ("517669", 16, "MASTER_CARD", "CREDIT", 3),
        ("517869", 16, "MASTER_CARD", "DEBIT", 3),
        ("601100", 16, "DISCOVER", "CREDIT", 3), ("601101", 16, "DISCOVER", "CREDIT", 3),
        ("373197", 15, "AMEX", "CREDIT", 4), ("373198", 15, "AMEX", "CREDIT", 4),
        ("373432", 15, "AMEX", "CREDIT", 4),
    ],
    # JP Pool expansion: Rakuten / Mitsubishi UFJ Nicos / SMBC / Saison / Mizuho / EPOS / JCB
    "JP": [
        # Rakuten
        ("429769", 16, "VISA", "CREDIT", 3), ("429770", 16, "VISA", "CREDIT", 3),
        ("429771", 16, "VISA", "CREDIT", 3), ("429772", 16, "VISA", "CREDIT", 3),
        ("465993", 16, "VISA", "CREDIT", 3), ("466778", 16, "VISA", "CREDIT", 3),
        ("492371", 16, "VISA", "CREDIT", 3), ("492372", 16, "VISA", "CREDIT", 3),
        # Mitsubishi UFJ Nicos / MUFG
        ("453450", 16, "VISA", "CREDIT", 3), ("521231", 16, "MASTER_CARD", "CREDIT", 3),
        ("521232", 16, "MASTER_CARD", "CREDIT", 3), ("521233", 16, "MASTER_CARD", "CREDIT", 3),
        ("521234", 16, "MASTER_CARD", "CREDIT", 3), ("521253", 16, "MASTER_CARD", "CREDIT", 3),
        ("521255", 16, "MASTER_CARD", "CREDIT", 3), ("521257", 16, "MASTER_CARD", "CREDIT", 3),
        ("222924", 16, "MASTER_CARD", "CREDIT", 3),
        # Sumitomo Mitsui (SMBC)
        ("498001", 16, "VISA", "CREDIT", 3), ("530232", 16, "MASTER_CARD", "CREDIT", 3),
        ("533491", 16, "MASTER_CARD", "CREDIT", 3), ("222880", 16, "MASTER_CARD", "CREDIT", 3),
        ("222897", 16, "MASTER_CARD", "CREDIT", 3),
        # Saison / Mizuho / EPOS
        ("454153", 16, "VISA", "CREDIT", 3), ("454294", 16, "VISA", "CREDIT", 3),
        ("489784", 16, "VISA", "CREDIT", 3), ("377783", 15, "AMEX", "CREDIT", 4),
        # JCB (generalization segment 35xx itself is JCB network, Type constant correspondence)
        ("35", 16, "JCB", "CREDIT", 3),
    ],
    # GB Pool expansion: Barclays / Lloyds / HSBC / NatWest / Santander / RBS / MBNA / Tesco Bank
    "GB": [
        # Barclays VISA
        ("402147", 16, "VISA", "CREDIT", 3), ("402148", 16, "VISA", "CREDIT", 3),
        ("402152", 16, "VISA", "CREDIT", 3), ("409023", 16, "VISA", "CREDIT", 3),
        ("409024", 16, "VISA", "CREDIT", 3), ("409025", 16, "VISA", "CREDIT", 3),
        ("409026", 16, "VISA", "CREDIT", 3), ("412280", 16, "VISA", "CREDIT", 3),
        ("412282", 16, "VISA", "CREDIT", 3), ("412991", 16, "VISA", "CREDIT", 3),
        ("412992", 16, "VISA", "CREDIT", 3), ("412993", 16, "VISA", "CREDIT", 3),
        ("425757", 16, "VISA", "CREDIT", 3), ("426501", 16, "VISA", "CREDIT", 3),
        ("426525", 16, "VISA", "CREDIT", 3), ("427700", 16, "VISA", "CREDIT", 3),
        ("429595", 16, "VISA", "CREDIT", 3), ("447318", 16, "VISA", "CREDIT", 3),
        ("449355", 16, "VISA", "CREDIT", 3), ("451154", 16, "VISA", "CREDIT", 3),
        ("451155", 16, "VISA", "CREDIT", 3), ("461250", 16, "VISA", "CREDIT", 3),
        ("462747", 16, "VISA", "CREDIT", 3), ("485859", 16, "VISA", "CREDIT", 3),
        ("400115", 16, "VISA", "DEBIT", 3), ("408367", 16, "VISA", "DEBIT", 3),
        ("409400", 16, "VISA", "DEBIT", 3), ("409401", 16, "VISA", "DEBIT", 3),
        ("409402", 16, "VISA", "DEBIT", 3), ("430532", 16, "VISA", "DEBIT", 3),
        ("453978", 16, "VISA", "DEBIT", 3), ("453979", 16, "VISA", "DEBIT", 3),
        ("456725", 16, "VISA", "DEBIT", 3), ("465858", 16, "VISA", "DEBIT", 3),
        ("465859", 16, "VISA", "DEBIT", 3), ("465861", 16, "VISA", "DEBIT", 3),
        ("492826", 16, "VISA", "DEBIT", 3), ("492827", 16, "VISA", "DEBIT", 3),
        # Barclays Mastercard
        ("513624", 16, "MASTER_CARD", "CREDIT", 3), ("514021", 16, "MASTER_CARD", "CREDIT", 3),
        ("539616", 16, "MASTER_CARD", "CREDIT", 3), ("540002", 16, "MASTER_CARD", "CREDIT", 3),
        ("542607", 16, "MASTER_CARD", "CREDIT", 3), ("543247", 16, "MASTER_CARD", "CREDIT", 3),
        # Lloyds Mastercard
        ("540055", 16, "MASTER_CARD", "CREDIT", 3), ("540403", 16, "MASTER_CARD", "CREDIT", 3),
        ("540427", 16, "MASTER_CARD", "CREDIT", 3), ("540429", 16, "MASTER_CARD", "CREDIT", 3),
        ("540431", 16, "MASTER_CARD", "CREDIT", 3), ("540436", 16, "MASTER_CARD", "CREDIT", 3),
        ("540437", 16, "MASTER_CARD", "CREDIT", 3), ("540456", 16, "MASTER_CARD", "CREDIT", 3),
        ("540463", 16, "MASTER_CARD", "CREDIT", 3), ("540471", 16, "MASTER_CARD", "CREDIT", 3),
        ("540485", 16, "MASTER_CARD", "CREDIT", 3), ("540493", 16, "MASTER_CARD", "CREDIT", 3),
        ("542309", 16, "MASTER_CARD", "CREDIT", 3), ("542502", 16, "MASTER_CARD", "CREDIT", 3),
        # HSBC
        ("486460", 16, "VISA", "CREDIT", 3), ("485738", 16, "VISA", "CREDIT", 3),
        ("447692", 16, "VISA", "CREDIT", 3), ("540251", 16, "MASTER_CARD", "CREDIT", 3),
        ("540252", 16, "MASTER_CARD", "CREDIT", 3), ("540903", 16, "MASTER_CARD", "CREDIT", 3),
        ("542101", 16, "MASTER_CARD", "CREDIT", 3), ("542597", 16, "MASTER_CARD", "CREDIT", 3),
        ("542854", 16, "MASTER_CARD", "CREDIT", 3), ("543131", 16, "MASTER_CARD", "CREDIT", 3),
        # NatWest / RBS (VISA debit, Mastercard credit)
        ("475110", 16, "VISA", "DEBIT", 3), ("475116", 16, "VISA", "DEBIT", 3),
        ("475117", 16, "VISA", "DEBIT", 3), ("475118", 16, "VISA", "DEBIT", 3),
        ("540964", 16, "MASTER_CARD", "CREDIT", 3), ("542451", 16, "MASTER_CARD", "CREDIT", 3),
        ("542515", 16, "MASTER_CARD", "CREDIT", 3), ("542516", 16, "MASTER_CARD", "CREDIT", 3),
        ("542533", 16, "MASTER_CARD", "CREDIT", 3), ("543166", 16, "MASTER_CARD", "CREDIT", 3),
        ("541170", 16, "MASTER_CARD", "CREDIT", 3), ("542004", 16, "MASTER_CARD", "CREDIT", 3),
        ("542615", 16, "MASTER_CARD", "CREDIT", 3),
        # Santander UK
        ("475714", 16, "VISA", "DEBIT", 3), ("528689", 16, "MASTER_CARD", "CREDIT", 3),
        ("541002", 16, "MASTER_CARD", "CREDIT", 3), ("541361", 16, "MASTER_CARD", "CREDIT", 3),
        ("541603", 16, "MASTER_CARD", "CREDIT", 3), ("541647", 16, "MASTER_CARD", "CREDIT", 3),
        # MBNA / Tesco Bank / Aqua
        ("540635", 16, "MASTER_CARD", "CREDIT", 3), ("540758", 16, "MASTER_CARD", "CREDIT", 3),
        ("512687", 16, "MASTER_CARD", "CREDIT", 3), ("557098", 16, "MASTER_CARD", "CREDIT", 3),
    ],
    # DE Pool expansion: Deutsche Bank / DKB / N26
    "DE": [
        # Deutsche Bank VISA
        ("404546", 16, "VISA", "CREDIT", 3), ("404547", 16, "VISA", "CREDIT", 3),
        ("416090", 16, "VISA", "CREDIT", 3), ("416091", 16, "VISA", "CREDIT", 3),
        ("416092", 16, "VISA", "CREDIT", 3), ("416093", 16, "VISA", "CREDIT", 3),
        ("430514", 16, "VISA", "CREDIT", 3), ("441233", 16, "VISA", "CREDIT", 3),
        ("441258", 16, "VISA", "CREDIT", 3), ("441259", 16, "VISA", "CREDIT", 3),
        ("441260", 16, "VISA", "CREDIT", 3), ("441261", 16, "VISA", "CREDIT", 3),
        ("441262", 16, "VISA", "CREDIT", 3), ("441263", 16, "VISA", "CREDIT", 3),
        ("441264", 16, "VISA", "CREDIT", 3), ("441287", 16, "VISA", "CREDIT", 3),
        ("441288", 16, "VISA", "CREDIT", 3), ("441293", 16, "VISA", "CREDIT", 3),
        ("441298", 16, "VISA", "CREDIT", 3), ("448401", 16, "VISA", "CREDIT", 3),
        ("451853", 16, "VISA", "CREDIT", 3), ("451854", 16, "VISA", "CREDIT", 3),
        ("460190", 16, "VISA", "CREDIT", 3), ("460191", 16, "VISA", "CREDIT", 3),
        ("474588", 16, "VISA", "CREDIT", 3), ("477912", 16, "VISA", "CREDIT", 3),
        ("477913", 16, "VISA", "CREDIT", 3), ("485700", 16, "VISA", "CREDIT", 3),
        ("485701", 16, "VISA", "CREDIT", 3), ("485702", 16, "VISA", "CREDIT", 3),
        ("486455", 16, "VISA", "CREDIT", 3), ("486456", 16, "VISA", "CREDIT", 3),
        # Deutsche Bank Mastercard
        ("512665", 16, "MASTER_CARD", "CREDIT", 3), ("519375", 16, "MASTER_CARD", "CREDIT", 3),
        ("523227", 16, "MASTER_CARD", "CREDIT", 3), ("523230", 16, "MASTER_CARD", "CREDIT", 3),
        ("523276", 16, "MASTER_CARD", "CREDIT", 3), ("545105", 16, "MASTER_CARD", "CREDIT", 3),
        ("545990", 16, "MASTER_CARD", "CREDIT", 3), ("545991", 16, "MASTER_CARD", "CREDIT", 3),
        ("547268", 16, "MASTER_CARD", "CREDIT", 3), ("547341", 16, "MASTER_CARD", "CREDIT", 3),
        ("557011", 16, "MASTER_CARD", "CREDIT", 3),
        # DKB (Lufthansa Miles & More wait)
        ("499897", 16, "VISA", "CREDIT", 3), ("523403", 16, "MASTER_CARD", "CREDIT", 3),
        ("523407", 16, "MASTER_CARD", "CREDIT", 3), ("523412", 16, "MASTER_CARD", "CREDIT", 3),
        ("523417", 16, "MASTER_CARD", "CREDIT", 3), ("523420", 16, "MASTER_CARD", "CREDIT", 3),
        ("523423", 16, "MASTER_CARD", "CREDIT", 3), ("523428", 16, "MASTER_CARD", "CREDIT", 3),
        ("523430", 16, "MASTER_CARD", "CREDIT", 3), ("523435", 16, "MASTER_CARD", "CREDIT", 3),
        ("523437", 16, "MASTER_CARD", "CREDIT", 3), ("523439", 16, "MASTER_CARD", "CREDIT", 3),
        ("523443", 16, "MASTER_CARD", "CREDIT", 3), ("523447", 16, "MASTER_CARD", "CREDIT", 3),
        ("523449", 16, "MASTER_CARD", "CREDIT", 3), ("523451", 16, "MASTER_CARD", "CREDIT", 3),
        ("523453", 16, "MASTER_CARD", "CREDIT", 3), ("523455", 16, "MASTER_CARD", "CREDIT", 3),
        ("523464", 16, "MASTER_CARD", "CREDIT", 3), ("523468", 16, "MASTER_CARD", "CREDIT", 3),
        ("523471", 16, "MASTER_CARD", "CREDIT", 3), ("523472", 16, "MASTER_CARD", "CREDIT", 3),
        ("523476", 16, "MASTER_CARD", "CREDIT", 3), ("523477", 16, "MASTER_CARD", "CREDIT", 3),
        ("523480", 16, "MASTER_CARD", "CREDIT", 3), ("523483", 16, "MASTER_CARD", "CREDIT", 3),
        ("523484", 16, "MASTER_CARD", "CREDIT", 3), ("523488", 16, "MASTER_CARD", "CREDIT", 3),
        ("523491", 16, "MASTER_CARD", "CREDIT", 3), ("523492", 16, "MASTER_CARD", "CREDIT", 3),
        ("523495", 16, "MASTER_CARD", "CREDIT", 3),
        # N26
        ("535584", 16, "MASTER_CARD", "DEBIT", 3), ("535585", 16, "MASTER_CARD", "DEBIT", 3),
        ("535586", 16, "MASTER_CARD", "DEBIT", 3), ("535590", 16, "MASTER_CARD", "DEBIT", 3),
    ],
    # TH Pool expansion: Bangkok Bank / Kasikorn / Krungthai / SCB / Krungsri / UOB / TMB / Thanachart / Citi
    "TH": [
        # Bangkok Bank VISA
        ("404870", 16, "VISA", "CREDIT", 3), ("404871", 16, "VISA", "CREDIT", 3),
        ("404872", 16, "VISA", "CREDIT", 3), ("404873", 16, "VISA", "CREDIT", 3),
        ("404875", 16, "VISA", "CREDIT", 3), ("404876", 16, "VISA", "CREDIT", 3),
        ("448427", 16, "VISA", "CREDIT", 3), ("454624", 16, "VISA", "CREDIT", 3),
        ("454626", 16, "VISA", "CREDIT", 3), ("454627", 16, "VISA", "CREDIT", 3),
        ("454631", 16, "VISA", "CREDIT", 3), ("454632", 16, "VISA", "CREDIT", 3),
        ("473014", 16, "VISA", "CREDIT", 3), ("421315", 16, "VISA", "DEBIT", 3),
        ("454630", 16, "VISA", "DEBIT", 3), ("462288", 16, "VISA", "DEBIT", 3),
        # Bangkok Bank Mastercard
        ("544464", 16, "MASTER_CARD", "CREDIT", 3), ("544469", 16, "MASTER_CARD", "CREDIT", 3),
        ("544482", 16, "MASTER_CARD", "CREDIT", 3), ("544485", 16, "MASTER_CARD", "CREDIT", 3),
        ("544488", 16, "MASTER_CARD", "CREDIT", 3),
        # Kasikorn
        ("402339", 16, "VISA", "CREDIT", 3), ("406230", 16, "VISA", "CREDIT", 3),
        ("428380", 16, "VISA", "CREDIT", 3), ("431508", 16, "VISA", "CREDIT", 3),
        ("438278", 16, "VISA", "CREDIT", 3), ("492141", 16, "VISA", "CREDIT", 3),
        ("541176", 16, "MASTER_CARD", "CREDIT", 3), ("540488", 16, "MASTER_CARD", "CREDIT", 3),
        # Krungthai Card
        ("439111", 16, "VISA", "CREDIT", 3), ("439112", 16, "VISA", "CREDIT", 3),
        ("439113", 16, "VISA", "CREDIT", 3), ("439114", 16, "VISA", "CREDIT", 3),
        ("439121", 16, "VISA", "CREDIT", 3), ("439122", 16, "VISA", "CREDIT", 3),
        ("439127", 16, "VISA", "CREDIT", 3), ("540604", 16, "MASTER_CARD", "CREDIT", 3),
        ("540605", 16, "MASTER_CARD", "CREDIT", 3), ("540716", 16, "MASTER_CARD", "CREDIT", 3),
        # Siam Commercial Bank
        ("434087", 16, "VISA", "CREDIT", 3), ("434088", 16, "VISA", "CREDIT", 3),
        ("434089", 16, "VISA", "CREDIT", 3), ("454852", 16, "VISA", "CREDIT", 3),
        ("490733", 16, "VISA", "CREDIT", 3), ("534442", 16, "MASTER_CARD", "CREDIT", 3),
        ("540492", 16, "MASTER_CARD", "CREDIT", 3), ("541029", 16, "MASTER_CARD", "CREDIT", 3),
        ("541496", 16, "MASTER_CARD", "CREDIT", 3), ("541897", 16, "MASTER_CARD", "CREDIT", 3),
        # Bank of Ayudhya (Krungsri)
        ("424953", 16, "VISA", "CREDIT", 3), ("424954", 16, "VISA", "CREDIT", 3),
        ("450580", 16, "VISA", "CREDIT", 3), ("455205", 16, "VISA", "CREDIT", 3),
        ("455296", 16, "VISA", "CREDIT", 3), ("540430", 16, "MASTER_CARD", "CREDIT", 3),
        ("540474", 16, "MASTER_CARD", "CREDIT", 3), ("541690", 16, "MASTER_CARD", "CREDIT", 3),
        # Citi / TMB / Thanachart / UOB / SCB Thai / Krung Thai / GSB / Aeon
        ("438679", 16, "VISA", "CREDIT", 3), ("454325", 16, "VISA", "CREDIT", 3),
        ("455596", 16, "VISA", "CREDIT", 3), ("540432", 16, "MASTER_CARD", "CREDIT", 3),
        ("436759", 16, "VISA", "CREDIT", 3), ("442308", 16, "VISA", "CREDIT", 3),
        ("540040", 16, "MASTER_CARD", "CREDIT", 3), ("414167", 16, "VISA", "CREDIT", 3),
        ("540180", 16, "MASTER_CARD", "CREDIT", 3), ("541878", 16, "MASTER_CARD", "CREDIT", 3),
        ("407539", 16, "VISA", "CREDIT", 3), ("436807", 16, "VISA", "CREDIT", 3),
        ("437750", 16, "VISA", "CREDIT", 3), ("541859", 16, "MASTER_CARD", "CREDIT", 3),
        ("453215", 16, "VISA", "DEBIT", 3), ("449932", 16, "VISA", "CREDIT", 3),
        ("451485", 16, "VISA", "CREDIT", 3), ("409061", 16, "VISA", "CREDIT", 3),
        ("409062", 16, "VISA", "CREDIT", 3),
    ],
    "KR": [("4", 16, "VISA", "CREDIT", 3), ("53", 16, "MASTER_CARD", "DEBIT", 3), ("35", 16, "JCB", "CREDIT", 3)],
    "AU": [("4", 16, "VISA", "CREDIT", 3), ("52", 16, "MASTER_CARD", "DEBIT", 3)],
    # VN Pool expansion: Vietcombank / Sacombank / VPBank / MB / BIDV / VIB / MSB / SCB / Shinhan / HDBank / SeABank / OCB / VietinBank / LPB / PVComBank / SHB (public IIN Table of contents + SBV official)
    "VN": [
        # Vietcombank
        ("403277", 16, "VISA", "DEBIT", 3), ("428310", 16, "VISA", "DEBIT", 3),
        ("452404", 16, "VISA", "DEBIT", 3), ("477390", 16, "VISA", "DEBIT", 3),
        ("222806", 16, "MASTER_CARD", "CREDIT", 3), ("526418", 16, "MASTER_CARD", "DEBIT", 3),
        # Sacombank
        ("401520", 16, "VISA", "DEBIT", 3), ("422151", 16, "VISA", "DEBIT", 3),
        ("436438", 16, "VISA", "CREDIT", 3), ("455376", 16, "VISA", "CREDIT", 3),
        ("461138", 16, "VISA", "DEBIT", 3), ("461140", 16, "VISA", "CREDIT", 3),
        ("461337", 16, "VISA", "CREDIT", 3), ("466243", 16, "VISA", "CREDIT", 3),
        ("469654", 16, "VISA", "DEBIT", 3), ("472074", 16, "VISA", "CREDIT", 3),
        ("472075", 16, "VISA", "CREDIT", 3), ("486265", 16, "VISA", "CREDIT", 3),
        ("512341", 16, "MASTER_CARD", "CREDIT", 3), ("526830", 16, "MASTER_CARD", "CREDIT", 3),
        ("552332", 16, "MASTER_CARD", "CREDIT", 3), ("517416", 16, "MASTER_CARD", "DEBIT", 3),
        # VPBank
        ("405280", 16, "VISA", "CREDIT", 3), ("406453", 16, "VISA", "CREDIT", 3),
        ("419834", 16, "VISA", "CREDIT", 3), ("454107", 16, "VISA", "CREDIT", 3),
        ("478668", 16, "VISA", "CREDIT", 3), ("454119", 16, "VISA", "DEBIT", 3),
        ("518966", 16, "MASTER_CARD", "CREDIT", 3), ("520399", 16, "MASTER_CARD", "CREDIT", 3),
        ("523975", 16, "MASTER_CARD", "CREDIT", 3), ("524394", 16, "MASTER_CARD", "CREDIT", 3),
        ("520395", 16, "MASTER_CARD", "DEBIT", 3), ("521377", 16, "MASTER_CARD", "DEBIT", 3),
        ("528626", 16, "MASTER_CARD", "DEBIT", 3),
        # MB
        ("472674", 16, "VISA", "CREDIT", 3), ("484803", 16, "VISA", "CREDIT", 3),
        ("484804", 16, "VISA", "CREDIT", 3), ("548566", 16, "MASTER_CARD", "DEBIT", 3),
        # BIDV / VIB
        ("402534", 16, "VISA", "CREDIT", 3), ("436467", 16, "VISA", "CREDIT", 3),
        ("436468", 16, "VISA", "CREDIT", 3), ("457560", 16, "VISA", "DEBIT", 3),
        ("457561", 16, "VISA", "DEBIT", 3),
        ("498766", 16, "VISA", "CREDIT", 3), ("498767", 16, "VISA", "CREDIT", 3),
        ("498768", 16, "VISA", "DEBIT", 3), ("498769", 16, "VISA", "DEBIT", 3),
        # MSB / SCB / Shinhan / HDBank
        ("402204", 16, "VISA", "DEBIT", 3), ("402215", 16, "VISA", "DEBIT", 3),
        ("412189", 16, "VISA", "CREDIT", 3), ("472265", 16, "VISA", "CREDIT", 3),
        ("479155", 16, "VISA", "CREDIT", 3),
        ("453618", 16, "VISA", "DEBIT", 3), ("489516", 16, "VISA", "CREDIT", 3),
        ("489517", 16, "VISA", "CREDIT", 3), ("489518", 16, "VISA", "CREDIT", 3),
        ("510235", 16, "MASTER_CARD", "CREDIT", 3), ("545579", 16, "MASTER_CARD", "CREDIT", 3),
        ("554627", 16, "MASTER_CARD", "CREDIT", 3), ("550796", 16, "MASTER_CARD", "DEBIT", 3),
        ("430389", 16, "VISA", "CREDIT", 3), ("516294", 16, "MASTER_CARD", "CREDIT", 3),
        ("532451", 16, "MASTER_CARD", "CREDIT", 3), ("510995", 16, "MASTER_CARD", "DEBIT", 3),
        ("511409", 16, "MASTER_CARD", "DEBIT", 3), ("521976", 16, "MASTER_CARD", "DEBIT", 3),
        ("416259", 16, "VISA", "CREDIT", 3), ("462478", 16, "VISA", "CREDIT", 3),
        ("515131", 16, "MASTER_CARD", "CREDIT", 3), ("532137", 16, "MASTER_CARD", "DEBIT", 3),
        # SeABank / OCB / VietinBank / LPB / PVComBank / SHB
        ("405082", 16, "VISA", "DEBIT", 3), ("436545", 16, "VISA", "CREDIT", 3),
        ("436546", 16, "VISA", "CREDIT", 3), ("476636", 16, "VISA", "CREDIT", 3),
        ("523611", 16, "MASTER_CARD", "CREDIT", 3), ("540392", 16, "MASTER_CARD", "DEBIT", 3),
        ("442415", 16, "VISA", "DEBIT", 3), ("442416", 16, "VISA", "DEBIT", 3),
        ("421595", 16, "VISA", "DEBIT", 3), ("462842", 16, "VISA", "CREDIT", 3),
        ("462843", 16, "VISA", "CREDIT", 3), ("462844", 16, "VISA", "CREDIT", 3),
        ("469672", 16, "VISA", "CREDIT", 3), ("469673", 16, "VISA", "CREDIT", 3),
        ("413534", 16, "VISA", "CREDIT", 3), ("413535", 16, "VISA", "CREDIT", 3),
        ("406598", 16, "VISA", "CREDIT", 3), ("418248", 16, "VISA", "DEBIT", 3),
        ("511962", 16, "MASTER_CARD", "CREDIT", 3), ("538742", 16, "MASTER_CARD", "CREDIT", 3),
        ("542553", 16, "MASTER_CARD", "CREDIT", 3), ("519501", 16, "MASTER_CARD", "CREDIT", 3),
        ("528645", 16, "MASTER_CARD", "DEBIT", 3), ("533147", 16, "MASTER_CARD", "CREDIT", 3),
        ("533968", 16, "MASTER_CARD", "CREDIT", 3), ("559270", 16, "MASTER_CARD", "CREDIT", 3),
    ],
    "BH": [("4", 16, "VISA", "CREDIT", 3), ("53", 16, "MASTER_CARD", "DEBIT", 3)],
    "AE": [("4", 16, "VISA", "CREDIT", 3), ("51", 16, "MASTER_CARD", "DEBIT", 3)],
    "TR": [("4", 16, "VISA", "CREDIT", 3), ("51", 16, "MASTER_CARD", "DEBIT", 3), ("9792", 16, "TROY", "CREDIT", 3)],
    # NL Pool expansion: ABN AMRO / Rabobank / ING / International Card Services / ANWB / Stripe / Amex
    "NL": [
        ("456353", 16, "VISA", "CREDIT", 3), ("456354", 16, "VISA", "CREDIT", 3),
        ("472906", 16, "VISA", "DEBIT", 3), ("405629", 16, "VISA", "CREDIT", 3),
        ("417274", 16, "VISA", "CREDIT", 3),
        ("400850", 16, "VISA", "CREDIT", 3), ("400851", 16, "VISA", "CREDIT", 3),
        ("400852", 16, "VISA", "CREDIT", 3), ("400853", 16, "VISA", "CREDIT", 3),
        ("400854", 16, "VISA", "CREDIT", 3), ("400855", 16, "VISA", "CREDIT", 3),
        ("400856", 16, "VISA", "CREDIT", 3), ("400857", 16, "VISA", "CREDIT", 3),
        ("400858", 16, "VISA", "CREDIT", 3), ("400859", 16, "VISA", "CREDIT", 3),
        ("522078", 16, "MASTER_CARD", "CREDIT", 3), ("534126", 16, "MASTER_CARD", "CREDIT", 3),
        ("520953", 16, "MASTER_CARD", "CREDIT", 3), ("520639", 16, "MASTER_CARD", "CREDIT", 3),
        ("524886", 16, "MASTER_CARD", "CREDIT", 3), ("532964", 16, "MASTER_CARD", "CREDIT", 3),
        ("532965", 16, "MASTER_CARD", "CREDIT", 3), ("553417", 16, "MASTER_CARD", "CREDIT", 3),
        ("555220", 16, "MASTER_CARD", "CREDIT", 3), ("555221", 16, "MASTER_CARD", "CREDIT", 3),
        ("555308", 16, "MASTER_CARD", "CREDIT", 3), ("555309", 16, "MASTER_CARD", "CREDIT", 3),
        ("555310", 16, "MASTER_CARD", "CREDIT", 3), ("555311", 16, "MASTER_CARD", "CREDIT", 3),
        ("556681", 16, "MASTER_CARD", "CREDIT", 3), ("523635", 16, "MASTER_CARD", "CREDIT", 3),
        ("523636", 16, "MASTER_CARD", "CREDIT", 3),
        ("510008", 16, "MASTER_CARD", "CREDIT", 3), ("541330", 16, "MASTER_CARD", "CREDIT", 3),
        ("375309", 15, "AMEX", "CREDIT", 4), ("375331", 15, "AMEX", "CREDIT", 4),
        ("375335", 15, "AMEX", "CREDIT", 4), ("375368", 15, "AMEX", "CREDIT", 4),
        ("375388", 15, "AMEX", "CREDIT", 4),
    ],
    "CI": [("4", 16, "VISA", "CREDIT", 3), ("51", 16, "MASTER_CARD", "DEBIT", 3)],
    "AO": [("4", 16, "VISA", "CREDIT", 3), ("51", 16, "MASTER_CARD", "DEBIT", 3)],
    # MX Pool expansion (2026-08-14): Banorte / BBVA Bancomer / Banamex / Santander / HSBC / Scotiabank / Azteca / Invex
    "MX": [
        # Banorte VISA
        ("418925", 16, "VISA", "CREDIT", 3), ("491341", 16, "VISA", "CREDIT", 3),
        ("491366", 16, "VISA", "CREDIT", 3), ("491375", 16, "VISA", "CREDIT", 3),
        ("491376", 16, "VISA", "CREDIT", 3), ("491575", 16, "VISA", "CREDIT", 3),
        ("491576", 16, "VISA", "CREDIT", 3), ("493158", 16, "VISA", "CREDIT", 3),
        ("493172", 16, "VISA", "CREDIT", 3), ("493173", 16, "VISA", "CREDIT", 3),
        ("491566", 16, "VISA", "DEBIT", 3), ("495166", 16, "VISA", "DEBIT", 3),
        # Banorte Mastercard
        ("544549", 16, "MASTER_CARD", "CREDIT", 3), ("547078", 16, "MASTER_CARD", "CREDIT", 3),
        ("547096", 16, "MASTER_CARD", "CREDIT", 3),
        # BBVA Bancomer
        ("408176", 16, "VISA", "DEBIT", 3), ("409851", 16, "VISA", "DEBIT", 3),
        ("410177", 16, "VISA", "DEBIT", 3), ("410180", 16, "VISA", "CREDIT", 3),
        ("410181", 16, "VISA", "CREDIT", 3), ("415231", 16, "VISA", "DEBIT", 3),
        ("415327", 16, "VISA", "CREDIT", 3), ("418073", 16, "VISA", "CREDIT", 3),
        ("418075", 16, "VISA", "CREDIT", 3), ("418077", 16, "VISA", "CREDIT", 3),
        ("418080", 16, "VISA", "CREDIT", 3), ("418093", 16, "VISA", "CREDIT", 3),
        ("418094", 16, "VISA", "CREDIT", 3), ("441310", 16, "VISA", "CREDIT", 3),
        ("441311", 16, "VISA", "CREDIT", 3), ("441314", 16, "VISA", "CREDIT", 3),
        ("441312", 16, "VISA", "DEBIT", 3), ("441313", 16, "VISA", "DEBIT", 3),
        ("444085", 16, "VISA", "CREDIT", 3), ("444086", 16, "VISA", "CREDIT", 3),
        ("446117", 16, "VISA", "DEBIT", 3), ("446118", 16, "VISA", "DEBIT", 3),
        ("455500", 16, "VISA", "CREDIT", 3), ("455503", 16, "VISA", "CREDIT", 3),
        ("455504", 16, "VISA", "CREDIT", 3), ("455505", 16, "VISA", "CREDIT", 3),
        ("493160", 16, "VISA", "CREDIT", 3), ("493161", 16, "VISA", "CREDIT", 3),
        ("493162", 16, "VISA", "CREDIT", 3), ("494398", 16, "VISA", "CREDIT", 3),
        ("498585", 16, "VISA", "CREDIT", 3),
        # Banamex / Santander / HSBC / Scotiabank / Azteca / Invex
        ("441541", 16, "VISA", "CREDIT", 3), ("441545", 16, "VISA", "DEBIT", 3),
        ("441549", 16, "VISA", "DEBIT", 3), ("451331", 16, "VISA", "DEBIT", 3),
        ("433465", 16, "VISA", "CREDIT", 3), ("441507", 16, "VISA", "CREDIT", 3),
        ("451299", 16, "VISA", "CREDIT", 3), ("451312", 16, "VISA", "DEBIT", 3),
        ("547046", 16, "MASTER_CARD", "CREDIT", 3),
        ("441551", 16, "VISA", "CREDIT", 3), ("452412", 16, "VISA", "DEBIT", 3),
        ("444449", 16, "VISA", "CREDIT", 3), ("441548", 16, "VISA", "CREDIT", 3),
        ("446137", 16, "VISA", "CREDIT", 3),
    ],
    # IN Pool expansion (2026-08-14): HDFC / ICICI / SBI / Axis
    "IN": [
        # HDFC VISA credit
        ("401403", 16, "VISA", "CREDIT", 3), ("402219", 16, "VISA", "CREDIT", 3),
        ("402359", 16, "VISA", "CREDIT", 3), ("404249", 16, "VISA", "CREDIT", 3),
        ("404276", 16, "VISA", "CREDIT", 3), ("405028", 16, "VISA", "CREDIT", 3),
        ("406578", 16, "VISA", "CREDIT", 3), ("407497", 16, "VISA", "CREDIT", 3),
        ("407498", 16, "VISA", "CREDIT", 3), ("416317", 16, "VISA", "CREDIT", 3),
        ("417410", 16, "VISA", "CREDIT", 3), ("418136", 16, "VISA", "CREDIT", 3),
        ("418218", 16, "VISA", "CREDIT", 3), ("424246", 16, "VISA", "CREDIT", 3),
        ("425698", 16, "VISA", "CREDIT", 3), ("430570", 16, "VISA", "CREDIT", 3),
        ("434155", 16, "VISA", "CREDIT", 3), ("434168", 16, "VISA", "CREDIT", 3),
        ("434677", 16, "VISA", "CREDIT", 3), ("434678", 16, "VISA", "CREDIT", 3),
        ("435376", 16, "VISA", "CREDIT", 3), ("435393", 16, "VISA", "CREDIT", 3),
        ("436152", 16, "VISA", "CREDIT", 3), ("437546", 16, "VISA", "CREDIT", 3),
        ("442142", 16, "VISA", "CREDIT", 3), ("451104", 16, "VISA", "CREDIT", 3),
        ("457262", 16, "VISA", "CREDIT", 3),
        # HDFC VISA debit
        ("400914", 16, "VISA", "DEBIT", 3), ("403875", 16, "VISA", "DEBIT", 3),
        ("405988", 16, "VISA", "DEBIT", 3), ("408981", 16, "VISA", "DEBIT", 3),
        ("414098", 16, "VISA", "DEBIT", 3), ("415921", 16, "VISA", "DEBIT", 3),
        ("416021", 16, "VISA", "DEBIT", 3), ("416233", 16, "VISA", "DEBIT", 3),
        ("418219", 16, "VISA", "DEBIT", 3), ("421340", 16, "VISA", "DEBIT", 3),
        ("423975", 16, "VISA", "DEBIT", 3), ("427879", 16, "VISA", "DEBIT", 3),
        ("438624", 16, "VISA", "DEBIT", 3), ("440384", 16, "VISA", "DEBIT", 3),
        ("440899", 16, "VISA", "DEBIT", 3), ("442378", 16, "VISA", "DEBIT", 3),
        ("445002", 16, "VISA", "DEBIT", 3), ("453561", 16, "VISA", "DEBIT", 3),
        ("458280", 16, "VISA", "DEBIT", 3), ("458281", 16, "VISA", "DEBIT", 3),
        # HDFC Mastercard
        ("222700", 16, "MASTER_CARD", "DEBIT", 3), ("222848", 16, "MASTER_CARD", "DEBIT", 3),
        ("222943", 16, "MASTER_CARD", "DEBIT", 3), ("223406", 16, "MASTER_CARD", "DEBIT", 3),
        ("223487", 16, "MASTER_CARD", "DEBIT", 3), ("222703", 16, "MASTER_CARD", "CREDIT", 3),
        ("558818", 16, "MASTER_CARD", "CREDIT", 3),
        # ICICI / SBI / Axis
        ("421323", 16, "VISA", "DEBIT", 3), ("421630", 16, "VISA", "DEBIT", 3),
        ("447747", 16, "VISA", "CREDIT", 3), ("512622", 16, "MASTER_CARD", "CREDIT", 3),
        ("468805", 16, "VISA", "DEBIT", 3),
    ],
}

CARD_BIN_FALLBACK = "US"


def _pick_card_bin(country: str, used_bins: Optional[set] = None) -> tuple[str, int, str, str, int]:
    """Select by country BIN; Not included -> US general pool + warn; banned Not repeated (used_bins In-session deduplication)。"""
    cc = (country or "").upper()
    pool = CARD_BINS.get(cc)
    if not pool:
        pool = CARD_BINS[CARD_BIN_FALLBACK]
        from loguru import logger
        logger.warning("card bin fallback US for {}", cc)
    candidates = [b for b in pool if not used_bins or b[0] not in used_bins]
    if not candidates:
        candidates = pool
    return random.choice(candidates)


def build_card_number(bin_choice: tuple[str, int, str, str, int]) -> dict:
    """according to BIN Tuple generates card number (Luhn Check digit) + Validity period + CVV。"""
    bin_prefix, length, issuer, product_class, cvv_len = bin_choice
    middle_len = length - len(bin_prefix) - 1
    partial = bin_prefix + "".join(str(random.randint(0, 9)) for _ in range(middle_len))
    number = partial + str(_luhn_check_digit(partial))
    month = random.randint(1, 12)
    year = date.today().year + random.randint(2, 5)
    cvv = "".join(str(random.randint(0, 9)) for _ in range(cvv_len))
    return {
        "number": number,
        "expiry": f"{month:02d}/{year}",
        "cvv": cvv,
        "issuer": issuer,
        "product_class": product_class,
        "bin": bin_prefix,
    }


def generate_country_card(country: str, used_bins: Optional[set] = None) -> dict:
    """Nationalized card data (Consistent with the form country BIN pool)。"""
    return build_card_number(_pick_card_bin(country, used_bins))


def issuer_type_for(number: str) -> str:
    """PayPal CardIssuerType enum Derivation (Contains JCB/TROY, Correction 35xx->AMEX / 9792->VISA Misjudgment)。

    2026-08-14 repair: 50 part Maestro return MASTER_CARD; 6 Duanfen Discover(60/64/65) and MC(622 UnionPay/636-639)。
    """
    prefix2 = number[:2]
    prefix4 = number[:4]
    if prefix2 in {"35", "36"}:
        return "JCB"
    if prefix4 == "9792":
        return "TROY"
    if prefix2 in {"34", "37"}:
        return "AMEX"
    if prefix4 and "2221" <= prefix4 <= "2720":
        return "MASTER_CARD"
    if prefix2.isdigit() and "51" <= prefix2 <= "55":
        return "MASTER_CARD"
    if prefix2 == "50":
        return "MASTER_CARD"
    if prefix2 == "4":
        return "VISA"
    if prefix2 in {"60", "64", "65"}:
        return "DISCOVER"
    if prefix2[0] == "6":
        return "MASTER_CARD"
    return "VISA"


# =============================================================================
# National ID number generator
# =============================================================================


def th_pin() -> str:
    """Thailand 13 citizen number: first place 1-8, weight 13..2 mod-11, Check digit = (11-s%11)%10。"""
    first = random.randint(1, 8)
    rest = "".join(str(random.randint(0, 9)) for _ in range(11))
    base = f"{first}{rest}"
    check = _mod11_check_digit_v2(base, list(range(13, 1, -1)))
    return base + str(check)


def ae_emirates_id() -> str:
    """United Arab Emirates Emirates ID 15 Bit: 784-YYYY-NNNNNNN-C, Luhn check。"""
    year = random.randint(1970, 2000)
    seq = random.randint(0, 9_999_999)
    base = f"784{year:04d}{seq:07d}"
    return base + str(_luhn_check_digit(base))


def kr_rrn() -> str:
    """Korean resident number RRN 13 Bit: YYMMDD + G1-4 + 4place of registration + 2bit sequence + Check digit。
    weight 2,3,4,5,6,7,8,9,2,3,4,5 mod-11。"""
    dob = generate_dob(min_year=1970, max_year=1999, fmt="%y%m%d")
    gender = random.randint(1, 4)
    place = f"{random.randint(0, 99):02d}{random.randint(0, 99):02d}"
    serial = f"{random.randint(0, 99):02d}"
    base = f"{dob}{gender}{place}{serial}"
    return base + str(_mod11_check_digit_kr(base))


def br_cpf() -> str:
    """Brazil CPF 11 Bit mod-11 Double check digit (and models.generate_cpf Algorithm of the same name)。"""
    while True:
        digits = [random.randint(0, 9) for _ in range(9)]
        if not all(d == digits[0] for d in digits):
            break
    for _ in range(2):
        total = sum(d * (len(digits) + 1 - i) for i, d in enumerate(digits))
        check = 0 if total % 11 < 2 else 11 - (total % 11)
        digits.append(check)
    cpf = "".join(str(d) for d in digits)
    return f"{cpf[:3]}.{cpf[3:6]}.{cpf[6:9]}-{cpf[9:]}"


def za_id(gender: str = "F") -> str:
    """South Africa 13 Bit: YYMMDD + 4bit sequence(female<5000/male>=5000) + 0identity + 8 + Luhn。"""
    dob = generate_dob(min_year=1970, max_year=1999, fmt="%y%m%d")
    seq = random.randint(0, 4999) if gender.upper().startswith("F") else random.randint(5000, 9999)
    base = f"{dob}{seq:04d}08"
    return base + str(_luhn_check_digit(base))


def ar_cuit() -> str:
    """Argentina CUIT/CUIL 11 Bit: prefix 20/23/24/27(personal) + 8BitDNI + mod-11。"""
    while True:
        prefix = random.choice(["20", "23", "24", "27"])
        dni = f"{random.randint(0, 9_999_999):08d}"
        check = _mod11_check_digit_ar(prefix + dni)
        if check is not None:
            return f"{prefix}{dni}{check}"


def vn_cccd() -> str:
    """Vietnam 12 Bit CCCD: 3province code + 1sex/century + 2year of birth + 6bit random (No check digit)。"""
    province = random.randint(1, 96)
    gender_century = random.choice(["0", "1", "2", "3"])
    yy = f"{random.randint(40, 99):02d}"
    rand6 = f"{random.randint(0, 999_999):06d}"
    return f"{province:03d}{gender_century}{yy}{rand6}"


def bh_cpr() -> str:
    """Bahrain CPR 9 Bit: YYMM + 4bit random + Check digit(Not officially announced, use Luhn Placeholder)。"""
    dob = generate_dob(min_year=1970, max_year=1999, fmt="%y%m")
    seq = f"{random.randint(0, 9999):04d}"
    base = f"{dob}{seq}"
    return base + str(_luhn_check_digit(base))


def de_iban() -> str:
    """Germany IBAN: DE + 2bit check + BLZ(8) + account(10), mod-97 check。"""
    blz = f"{random.randint(10000000, 99999999)}"
    konto = f"{random.randint(0, 9_999_999_999):010d}"
    bban = blz + konto
    check = _mod97_iban_check_digits("DE", bban)
    return f"DE{check}{bban}"


def _curp_value(ch: str) -> int:
    return int(ch) if ch.isdigit() else ord(ch) - 55


def _curp_internal_consonant(word: str, exclude: str) -> str:
    for ch in word[1:]:
        if ch not in "AEIOU" and ch not in exclude:
            return ch
    return "X"


def mx_curp(names: tuple[str, str, str], dob: str, gender: str = "H", state: str = "DF") -> str:
    """Mexico CURP 18 character: surname1initials+initial vowel+surname2initials+initials+YYMMDD+gender+State code
    +3internal consonants+Same code(00last letter)+base37 mod-10 check。names=(primerAP, segundoAP, nombre)。"""
    p1, p2, n = names
    vowels = "AEIOU"
    first = p1[0]
    vowel = next((c for c in p1[1:] if c in vowels), "X")
    second = p2[0] if p2 else "X"
    given = n[0]
    yymmdd = dob
    cons = (
        _curp_internal_consonant(p1, first)
        + _curp_internal_consonant(p2, second)
        + _curp_internal_consonant(n, given)
    )
    homo = random.choice("0123456789") if int(yymmdd[:2]) < 20 else random.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
    partial = f"{first}{vowel}{second}{given}{yymmdd}{gender}{state}{cons}{homo}"
    total = sum(_curp_value(ch) * (18 - i) for i, ch in enumerate(partial))
    check = (10 - (total % 10)) % 10
    return partial + str(check)


# =============================================================================
# Japanese Katakana (Katakana) generate: Romaji rule conversion (일반 외국인명 → カタカナ)
# =============================================================================

_KATAKANA_MAP = {
    "a": "ア", "i": "イ", "u": "ウ", "e": "エ", "o": "オ",
    "ka": "カ", "ki": "キ", "ku": "ク", "ke": "ケ", "ko": "コ",
    "sa": "サ", "shi": "シ", "su": "ス", "se": "セ", "so": "ソ",
    "ta": "タ", "chi": "チ", "tsu": "ツ", "te": "テ", "to": "ト",
    "na": "ナ", "ni": "ニ", "nu": "ヌ", "ne": "ネ", "no": "ノ",
    "ha": "ハ", "hi": "ヒ", "fu": "フ", "he": "ヘ", "ho": "ホ",
    "ma": "マ", "mi": "ミ", "mu": "ム", "me": "メ", "mo": "モ",
    "ya": "ヤ", "yu": "ユ", "yo": "ヨ",
    "ra": "ラ", "ri": "リ", "ru": "ル", "re": "レ", "ro": "ロ",
    "wa": "ワ", "wo": "ヲ", "n": "ン",
    "ga": "ガ", "gi": "ギ", "gu": "グ", "ge": "ゲ", "go": "ゴ",
    "za": "ザ", "ji": "ジ", "zu": "ズ", "ze": "ゼ", "zo": "ゾ",
    "da": "ダ", "de": "デ", "do": "ド",
    "ba": "バ", "bi": "ビ", "bu": "ブ", "be": "ベ", "bo": "ボ",
    "pa": "パ", "pi": "ピ", "pu": "プ", "pe": "ペ", "po": "ポ",
    "kya": "キャ", "kyu": "キュ", "kyo": "キョ",
    "sha": "シャ", "shu": "シュ", "sho": "ショ",
    "cha": "チャ", "chu": "チュ", "cho": "チョ",
    "nya": "ニャ", "nyu": "ニュ", "nyo": "ニョ",
    "hya": "ヒャ", "hyu": "ヒュ", "hyo": "ヒョ",
    "mya": "ミャ", "myu": "ミュ", "myo": "ミョ",
    "rya": "リャ", "ryu": "リュ", "ryo": "リョ",
    "gya": "ギャ", "gyu": "ギュ", "gyo": "ギョ",
    "ja": "ジャ", "ju": "ジュ", "jo": "ジョ",
    "bya": "ビャ", "byu": "ビュ", "byo": "ビョ",
    "pya": "ピャ", "pyu": "ピュ", "pyo": "ピョ",
}


def latin_to_katakana(name: str) -> str:
    """English name → Katakana (greedy longest match, Unmapped character approximation)。"""
    name = name.lower().replace("-", " ").split(" ")[0]
    out = []
    i = 0
    while i < len(name):
        matched = False
        for ln in (3, 2, 1):
            frag = name[i : i + ln]
            if frag in _KATAKANA_MAP:
                out.append(_KATAKANA_MAP[frag])
                i += ln
                matched = True
                break
        if not matched:
            out.append("ッ")
            i += 1
    # Smallさいlong toneしない: endのーpayけはしない (Nameカナはgenerallyそのまま)
    return "".join(out)


# =============================================================================
# Name pool of various countries (firstName/lastName)
# =============================================================================

_COUNTRY_NAMES: dict[str, tuple[list[str], list[str]]] = {
    "US": (
        ["James", "John", "Robert", "Michael", "William", "David", "Daniel", "Emily", "Anna", "Olivia", "Sarah", "Emma"],
        ["Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis", "Wilson", "Taylor"],
    ),
    "JP": (
        ["Haruto", "Sota", "Yuto", "Riku", "Minato", "Yamato", "Sakura", "Yui", "Hana", "Aoi", "Mei", "Rin", "Kaito", "Ren"],
        ["Sato", "Suzuki", "Takahashi", "Tanaka", "Watanabe", "Ito", "Yamamoto", "Nakamura", "Kobayashi", "Kato"],
    ),
    "GB": (
        ["Oliver", "George", "Harry", "Jack", "Jacob", "Charlie", "Thomas", "Amelia", "Olivia", "Isla", "Poppy", "Emily"],
        ["Smith", "Jones", "Taylor", "Williams", "Brown", "Davies", "Evans", "Wilson", "Thomas", "Roberts"],
    ),
    "MX": (
        ["Juan", "Carlos", "Miguel", "Jose", "Luis", "Fernando", "Maria", "Guadalupe", "Sofia", "Carmen", "Ana", "Paola"],
        ["Hernandez", "Garcia", "Martinez", "Lopez", "Gonzalez", "Perez", "Rodriguez", "Sanchez", "Ramirez", "Cruz"],
    ),
    "TH": (
        ["Somchai", "Somsak", "Somporn", "Anan", "Panya", "Kittisak", "Malee", "Suda", "Nongyao", "Kanokwan", "Wilai", "Pornthip"],
        ["Saetang", "Saetia", "Saeteo", "Thongchai", "Srisuk", "Chairat", "Khamsaen", "Boonsong", "Jaroen", "Preecha"],
    ),
    "NL": (
        ["Daan", "Sem", "Lucas", "Finn", "Levi", "Bram", "Emma", "Sophie", "Mila", "Julia", "Saar", "Lieke"],
        ["De Jong", "Jansen", "De Vries", "Van den Berg", "Van Dijk", "Bakker", "Visser", "Smit", "Mulder", "De Boer"],
    ),
    "VN": (
        ["Nguyen", "Tran", "Minh", "Nam", "Duc", "Hieu", "Hung", "Linh", "Hoa", "Mai", "Lan", "Thu", "Hanh"],
        ["Nguyen", "Tran", "Le", "Pham", "Hoang", "Phan", "Vu", "Dang", "Bui", "Do"],
    ),
    "BH": (
        ["Mohammed", "Ahmed", "Ali", "Hassan", "Husain", "Khalid", "Sara", "Fatima", "Aisha", "Maryam", "Noura", "Zainab"],
        ["Al Khalifa", "Al Sayed", "Al Arrayed", "Abdulla", "Al Mulla", "Al Qassimi", "Karimi", "Buzar", "Kanoo", "Fakhro"],
    ),
    "AO": (
        ["Joao", "Jose", "Manuel", "Carlos", "Antonio", "Pedro", "Maria", "Ana", "Fatima", "Isabel", "Luisa", "Teresa"],
        ["Dos Santos", "Fernandes", "Goncalves", "Pereira", "Rodrigues", "Lopes", "Da Silva", "Martins", "Sousa", "Almeida"],
    ),
    "AE": (
        ["Mohammed", "Ahmed", "Omar", "Abdullah", "Khalid", "Hamdan", "Fatima", "Aisha", "Mariam", "Noura", "Shaikha", "Amna"],
        ["Al Maktoum", "Al Nahyan", "Al Hashimi", "Al Marri", "Al Mazrouei", "Al Mansoori", "Al Shamsi", "Al Zaabi", "Alnuaimi", "Al Blooshi"],
    ),
    "AU": (
        ["Oliver", "William", "Jack", "Noah", "Henry", "Liam", "Charlotte", "Ruby", "Matilda", "Mia", "Chloe", "Zoe"],
        ["Smith", "Jones", "Williams", "Brown", "Wilson", "Taylor", "Thomas", "Johnson", "White", "Martin"],
    ),
    "CI": (
        ["Kouame", "Koffi", "Yao", "N'Guessan", "Kone", "Bamba", "Aya", "Aminata", "Fatou", "Mariam", "Adjoua", "Constance"],
        ["Kouame", "Kone", "Traore", "Bamba", "Coulibaly", "Diarra", "Sangare", "Ouattara", "N'Diaye", "Sylla"],
    ),
    "TR": (
        ["Mehmet", "Mustafa", "Ahmet", "Ali", "Emre", "Huseyin", "Ayse", "Fatma", "Zeynep", "Elif", "Merve", "Esra"],
        ["Yilmaz", "Kaya", "Demir", "Celik", "Sahin", "Yildiz", "Aydin", "Ozturk", "Arslan", "Dogan"],
    ),
    "DE": (
        ["Alexander", "Max", "Paul", "Jonas", "Leon", "Felix", "Lukas", "Anna", "Marie", "Sophie", "Laura", "Julia"],
        ["Muller", "Schmidt", "Schneider", "Fischer", "Weber", "Meyer", "Wagner", "Becker", "Hoffmann", "Schulz"],
    ),
    "BR": (
        ["Joao", "Pedro", "Lucas", "Mateus", "Gabriel", "Rafael", "Maria", "Ana", "Julia", "Larissa", "Camila", "Beatriz"],
        ["Silva", "Santos", "Oliveira", "Souza", "Rodrigues", "Ferreira", "Alves", "Pereira", "Lima", "Gomes"],
    ),
    "KR": (
        ["Minjun", "Seojun", "Dohyun", "Junseo", "Jiho", "Hyunwoo", "Seoyeon", "Jiwon", "Minseo", "Eunji", "Sujin", "Hana"],
        ["Kim", "Lee", "Park", "Choi", "Jung", "Kang", "Cho", "Yoon", "Jang", "Lim"],
    ),
    "RU": (
        ["Alexander", "Dmitry", "Sergey", "Andrey", "Ivan", "Maxim", "Anastasia", "Maria", "Elena", "Olga", "Tatiana", "Natalia"],
        ["Ivanov", "Smirnov", "Kuznetsov", "Popov", "Vasilyev", "Petrov", "Sokolov", "Mikhailov", "Novikov", "Fyodorov"],
    ),
    "IN": (
        ["Aarav", "Vivaan", "Aditya", "Vihaan", "Arjun", "Reyansh", "Diya", "Aadhya", "Anaya", "Saanvi", "Myra", "Ishita"],
        ["Sharma", "Verma", "Gupta", "Kumar", "Singh", "Patel", "Shah", "Reddy", "Nair", "Iyer"],
    ),
    "SA": (
        ["Mohammed", "Abdullah", "Fahad", "Saad", "Khalid", "Turki", "Noura", "Sara", "Lama", "Reem", "Alia", "Jana"],
        ["Al Otaibi", "Al Ghamdi", "Al Harbi", "Al Zahrani", "Al Dossari", "Al Qahtani", "Al Anazi", "Al Mutairi", "Al Shammari", "Al Rashed"],
    ),
    "AR": (
        ["Juan", "Jose", "Carlos", "Pedro", "Martin", "Diego", "Sofia", "Valentina", "Camila", "Martina", "Julieta", "Agustina"],
        ["Gonzalez", "Rodriguez", "Gomez", "Fernandez", "Lopez", "Diaz", "Martinez", "Perez", "Romero", "Alvarez"],
    ),
    "ZA": (
        ["Johannes", "Pieter", "Thabo", "Sipho", "Lungile", "Naledi", "Thandi", "Nomvula", "Zanele", "Ayanda", "Kabelo", "Refilwe"],
        ["Botha", "Van der Merwe", "Nkosi", "Mokoena", "Dlamini", "Naidoo", "Khumalo", "Sithole", "Mahlangu", "Nel"],
    ),
    "HK": (
        ["Ka Ho", "Wing Yin", "Hoi Tung", "Chun Ming", "Ka Wai", "Man Hei", "Yuet Ching", "Tsz Yan", "Wai Sum", "Hiu Tung", "Ching Man", "Kwun Ho"],
        ["Chan", "Lee", "Cheung", "Ho", "Wong", "Ng", "Tam", "Yuen", "Tsang", "Lau"],
    ),
}

# kycFields layer: This country appears in bundle of kycFields mapping, Fields that are not displayed are not collected
_COUNTRY_FIELD_OVERRIDES: dict[str, list[str]] = {
    "US": [],
    "JP": ["Nationality", "DateOfBirth"],
    "MX": ["DateOfBirth"],
    "AU": ["DateOfBirth"],
    "IN": ["Nationality"],
    "CA": ["DateOfBirth", "Occupation"],
    "BR": ["DateOfBirth", "IdentityDocumentType", "IdentityDocumentNumber"],
    "C2": ["DateOfBirth", "IdentityDocumentType", "IdentityDocumentNumber"],
    "CH": ["DateOfBirth", "IdentityDocumentType", "IdentityDocumentNumber"],
    "IL": ["DateOfBirth", "IdentityDocumentType", "IdentityDocumentNumber"],
    "HK": ["DateOfBirth", "Gender", "PlaceOfBirth", "Nationality", "IdentityDocumentType", "IdentityDocumentNumber"],
    "RU": ["CountryOfResidence", "IdentityDocumentType", "IdentityDocumentNumber", "DateOfBirth",
           "SecondaryIdentityDocumentType", "SecondaryIdentityDocumentNumber"],
    "TH": ["DateOfBirth", "Nationality", "IdentityDocumentType", "IdentityDocumentNumber"],
}

_DEFAULT_KYC_FIELDS = ["DateOfBirth", "Nationality"]
_FULL_KYC_FIELDS = [
    "DateOfBirth", "Nationality", "IdentityDocumentType", "IdentityDocumentNumber",
]

_ID_TYPE_ALWAYS = ["NATIONAL_ID", "PASSPORT_NUMBER", "DRIVERS_LICENSE"]
_ID_TYPE_BY_COUNTRY: dict[str, list[str]] = {
    "BR": ["CPF"],
    "KR": ["PASSPORT_NUMBER", "DRIVERS_LICENSE"],
    "RU": ["PASSPORT_NUMBER"],
    "TH": ["NATIONAL_ID"],
    "HK": ["NATIONAL_ID", "PASSPORT_NUMBER", "TEMPORARY_NATIONAL_ID"],
    "AE": ["NATIONAL_ID"],
    "VN": ["NATIONAL_ID"],
    "BH": ["NATIONAL_ID"],
    "AR": ["NATIONAL_ID"],
    "ZA": ["NATIONAL_ID"],
}


@dataclass
class CountryIdentity:
    country_code: str
    first_name: str
    last_name: str
    email: str
    password: str
    dob: str
    nationality: str = ""
    middle_name: str = ""
    kana_first: str = ""
    kana_last: str = ""
    identity_document_type: str = ""
    identity_document_number: str = ""
    crs_tax_details: list[dict] = field(default_factory=list)
    address: dict = field(default_factory=dict)      # line1/line2/city/state/postal_code
    phone_country: str = ""                          # "+1" / "+66" ...
    phone_number: str = ""                           # Complete number including country code
    extra: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "country_code": self.country_code,
            "first_name": self.first_name,
            "last_name": self.last_name,
            "email": self.email,
            "password": self.password,
            "dob": self.dob,
            "nationality": self.nationality,
            "middle_name": self.middle_name,
            "kana_first": self.kana_first,
            "kana_last": self.kana_last,
            "identity_document_type": self.identity_document_type,
            "identity_document_number": self.identity_document_number,
            "crs_tax_details": self.crs_tax_details,
            "address": self.address,
            "phone_country": self.phone_country,
            "phone_number": self.phone_number,
            "extra": self.extra,
        }


@dataclass
class CountryProfile:
    code: str
    fields: list[str]
    id_types: list[str]
    generator: Callable[[], CountryIdentity]
    source: str = ""


_REGISTRY: dict[str, CountryProfile] = {}


def _make_profile(
    code: str,
    fields: list[str],
    id_types: list[str],
    gen: Callable[[], CountryIdentity],
    source: str,
) -> CountryProfile:
    return CountryProfile(code=code, fields=fields, id_types=id_types, generator=gen, source=source)


def _build_profile(country: str, name_pool: tuple[list[str], list[str]], fields: list[str],
                   id_types: list[str], source: str) -> CountryProfile:
    firsts, lasts = name_pool

    def gen() -> CountryIdentity:
        first = random.choice(firsts)
        last = random.choice(lasts)
        phone_prefix, phone_full = generate_country_phone(country)
        ident = CountryIdentity(
            country_code=country,
            first_name=first,
            last_name=last,
            email=generate_email(first, last, country=country),
            password=generate_password(),
            dob=generate_dob(),
            nationality=country,
            address=generate_country_address(country),
            phone_country=phone_prefix,
            phone_number=phone_full,
        )
        if "Nationality" not in fields:
            ident.nationality = ""
        if "IdentityDocumentType" in fields:
            itype = random.choice(id_types) if id_types else "PASSPORT_NUMBER"
            ident.identity_document_type = itype
            ident.identity_document_number = _gen_doc_number(country, itype)
        if country == "JP":
            ident.kana_first = latin_to_katakana(ident.first_name)
            ident.kana_last = latin_to_katakana(ident.last_name)
        return ident

    return _make_profile(country, fields, id_types, gen, source)


def _gen_doc_number(country: str, doc_type: str) -> str:
    if country == "TH":
        return th_pin()
    if country == "BR" and doc_type == "CPF":
        return br_cpf()
    if country == "AE":
        return ae_emirates_id()
    if country == "KR":
        return kr_rrn() if doc_type == "NATIONAL_ID" else f"{random.randint(0, 9_999_999):08d}"
    if country == "AR":
        return ar_cuit()
    if country == "VN":
        return vn_cccd()
    if country == "BH":
        return bh_cpr()
    if country == "ZA":
        return za_id()
    return "".join(str(random.randint(0, 9)) for _ in range(9))


def _resolve_fields(country: str) -> list[str]:
    overrides = _COUNTRY_FIELD_OVERRIDES.get(country)
    if overrides is not None:
        return overrides
    return _FULL_KYC_FIELDS if country in _FULL_KYC_COUNTRIES else _DEFAULT_KYC_FIELDS


def get_country_profile(country: str) -> CountryIdentity:
    """Generate full form identity data by country (cover kycFields Configuration)。"""
    country = country.upper()
    if country in _REGISTRY:
        return _REGISTRY[country].generator()

    if country not in _COUNTRY_NAMES:
        raise KeyError(f"Countries not included: {country}")

    fields = _resolve_fields(country)
    id_types = _ID_TYPE_BY_COUNTRY.get(country, _ID_TYPE_ALWAYS)
    profile = _build_profile(country, _COUNTRY_NAMES[country], fields, id_types, "registry")
    _REGISTRY[country] = profile
    return profile.generator()


_FULL_KYC_COUNTRIES = {
    "AE", "AD", "AR", "BH", "BM", "BS", "BW", "CL", "CO", "CR", "DO", "EC", "FO",
    "GE", "GL", "GT", "HN", "HR", "ID", "IS", "JM", "JO", "KE", "KR", "KW", "KY",
    "KZ", "LS", "MA", "MC", "MD", "MU", "MY", "MZ", "NI", "NZ", "OM", "PA", "PE",
    "PH", "QA", "RS", "SA", "SG", "SN", "SV", "TW", "UY", "VE", "VN", "ZA",
}


def generate_country_data(country: str, count: int = 1) -> list[dict]:
    """Batch generation (for CLI/test/API use)。"""
    return [get_country_profile(country).to_dict() for _ in range(count)]


def available_countries() -> list[str]:
    return sorted(_COUNTRY_NAMES.keys())


def profile_summary(country: str) -> dict:
    """Return the country form field configuration and id types (for api Exposed configuration)。"""
    country = country.upper()
    if country not in _COUNTRY_NAMES:
        raise KeyError(country)
    profile = _REGISTRY.get(country) or _build_profile(
        country, _COUNTRY_NAMES[country],
        _resolve_fields(country),
        _ID_TYPE_BY_COUNTRY.get(country, _ID_TYPE_ALWAYS),
        "static",
    )
    return {
        "country": country,
        "fields": profile.fields,
        "id_types": profile.id_types,
        "source": profile.source,
    }


if __name__ == "__main__":
    import sys

    target = sys.argv[1].upper() if len(sys.argv) > 1 else "US"
    for cc in sorted(_COUNTRY_NAMES):
        if cc == target or target == "ALL":
            try:
                data = get_country_profile(cc)
                print(f"[{cc}] {data.first_name} {data.last_name} | {data.dob} | "
                      f"doc={data.identity_document_type or '-'}:{data.identity_document_number or '-'}")
            except Exception as exc:  # noqa: BLE001
                print(f"[{cc}] ERR {exc}")