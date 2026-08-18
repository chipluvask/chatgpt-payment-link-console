# -*- coding: utf-8 -*-
"""U.S. tax-free address database (tax-free address store)。

Top five tax-free states: DE(First choice) / NH / MT / OR / AK
Address format: street / city / state / zip / phone (usaddressgen style, City-state-Zip code matching)

support:
  - Built-in templates (DE/NH/MT/OR/AK real city + post code + street)
  - random/Specify state address
  - usaddressgen.com/tax-free-address/ reserved pull (dataUrls: us-data.json / us-cities.json)
"""
from __future__ import annotations

import json
import os
import random
import urllib.request
from typing import Any

# Top five tax-free states + real city/Postcode combination (city/state/zip must match)
TAX_FREE_STATES: dict[str, list[tuple[str, str]]] = {
    "DE": [  # delaware: First choice
        ("Wilmington", "19801"), ("Dover", "19901"), ("Newark", "19711"),
        ("Middletown", "19709"), ("Bear", "19701"),
    ],
    "NH": [  # New Hampshire
        ("Manchester", "03101"), ("Nashua", "03060"), ("Concord", "03301"),
        ("Portsmouth", "03801"), ("Derry", "03038"),
    ],
    "MT": [  # Montana
        ("Billings", "59101"), ("Missoula", "59801"), ("Great Falls", "59401"),
        ("Bozeman", "59715"), ("Helena", "59601"),
    ],
    "OR": [  # oregon
        ("Portland", "97205"), ("Salem", "97301"), ("Eugene", "97401"),
        ("Bend", "97701"), ("Medford", "97501"),
    ],
    "AK": [  # Alaska
        ("Anchorage", "99501"), ("Fairbanks", "99701"), ("Juneau", "99801"),
        ("Wasilla", "99654"), ("Sitka", "99835"),
    ],
}

# street template (usaddressgen style perturbation)
_STREET_TEMPLATES = [
    "{} {} {}",  # number street suffix
]

_STREET_NAMES = [
    "Example Lane", "Sample Street", "Demo Road", "Main Street", "Oak Avenue",
    "Maple Drive", "Cedar Court", "Willow Way", "Pine Street", "Elm Boulevard",
    "Sunset Terrace", "Harbor View", "Market Street", "Highland Avenue",
]

_TAX_FREE_ZIP_RE = re_compiled = None  # noqa: F841  (Placeholder)


def _phone() -> str:
    return f"({random.randint(200, 989)}) {random.randint(200, 989):03d}-{random.randint(1000, 9999):04d}"


def generate_address(state: str = "DE", name: str = "") -> dict[str, str]:
    """Generate a tax-free state address (street/city/state/zip/phone/name match)。"""
    state = str(state or "DE").strip().upper()
    if state not in TAX_FREE_STATES:
        state = "DE"
    city, zip_code = random.choice(TAX_FREE_STATES[state])
    street = f"{random.randint(100, 4999)} {random.choice(_STREET_NAMES)}"
    return {
        "street": street,
        "city": city,
        "state": state,
        "zip": zip_code,
        "phone": _phone(),
        "name": name or "Simon Test",
        "full": f"{street}, {city}, {state} {zip_code}",
    }


def pick_state(prefer: str = "DE") -> str:
    """take state (default DE First choice, Can be specified explicitly)。"""
    s = str(prefer or "").strip().upper()
    if s in TAX_FREE_STATES:
        return s
    # Weighted: DE First choice
    weights = {"DE": 60, "NH": 10, "MT": 10, "OR": 10, "AK": 10}
    pool = []
    for st, w in weights.items():
        pool += [st] * w
    return random.choice(pool)


def list_states() -> list[dict[str, str]]:
    """Return to list of tax-free states (With recommended tags)。"""
    notes = {
        "DE": "First choice · no state/local sales tax",
        "NH": "recommend · Digital goods are tax-free",
        "MT": "recommend · Digital goods are tax-free",
        "OR": "recommend · Digital goods are tax-free",
        "AK": "Some local taxes 7.5%",
    }
    return [{"state": s, "note": notes.get(s, "")} for s in TAX_FREE_STATES]


def fetch_usaddressgen(state: str = "DE") -> dict[str, Any] | None:
    """reserved: from usaddressgen.com Pull the real tax-free address。

    site data: /data/us-data.<hash>.json (Including cities/post code), Reserved implementation here,
    Fallback to local template when network is unavailable。
    """
    try:
        urls = [
            "https://usaddressgen.com/data/us-data.51b467380d1255919aab05ff0d5836ab44b800a9906a1e2bd2d48815aed30996.json",
        ]
        req = urllib.request.Request(urls[0], headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return {"ok": True, "data": data}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


taxfree_store = {
    "generate": generate_address,
    "pick_state": pick_state,
    "list_states": list_states,
    "fetch_usaddressgen": fetch_usaddressgen,
}
