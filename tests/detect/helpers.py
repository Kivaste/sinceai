"""Synthetic generators for detector tests. Independent implementations of the check digits."""

from __future__ import annotations

import random

HETU_CHECK = "0123456789ABCDEFHJKLMNPRSTUVWXY"
FIRST = ["Aino", "Eero", "Helmi", "Onni", "Ilona", "Veeti", "Sofia", "Leevi", "Venla", "Oskari", "Pihla", "Elias"]
LAST = ["Virtanen", "Korhonen", "Nieminen", "Mäkinen", "Hämäläinen", "Laine", "Heikkinen", "Koskinen", "Salo"]
CITIES = ["Turku", "Raisio", "Naantali", "Kaarina", "Lieto", "Salo", "Paimio", "Parainen"]


def hetu(rng: random.Random) -> str:
    d, m, y = rng.randint(1, 28), rng.randint(1, 12), rng.randint(40, 99)
    n = rng.randint(900, 999)
    body = f"{d:02d}{m:02d}{y:02d}"
    return f"{body}-{n}{HETU_CHECK[int(body + str(n)) % 31]}"


def luhn_card(rng: random.Random) -> str:
    digits = [rng.randint(0, 9) for _ in range(15)]
    total = 0
    for i, d in enumerate(reversed(digits)):
        d = d * 2 if i % 2 == 0 else d
        total += d - 9 if d > 9 else d
    return "".join(map(str, digits)) + str((10 - total % 10) % 10)


def iban(rng: random.Random) -> str:
    bban = "".join(str(rng.randint(0, 9)) for _ in range(14))
    check = 98 - int(bban + "151800") % 97
    return f"FI{check:02d}{bban}"


def name(rng: random.Random) -> str:
    return f"{rng.choice(LAST)} {rng.choice(FIRST)}"


def phone(rng: random.Random) -> str:
    return f"+358 4{rng.randint(0, 9)} {rng.randint(1000000, 9999999)}"


def make_frame(n: int = 400, seed: int = 7) -> dict[str, list[str]]:
    """A synthetic HR-ish table keyed by *obfuscated* headers, plus a truth map by header."""
    rng = random.Random(seed)
    cols: dict[str, list[str]] = {k: [] for k in
                                  ["c01", "c02", "c03", "c04", "c05", "c06", "c07", "c08", "c09", "c10", "c11", "c12"]}
    for i in range(n):
        cols["c01"].append(f"EMP{100000 + i}")
        cols["c02"].append(hetu(rng))
        cols["c03"].append(name(rng))
        cols["c04"].append(f"{rng.choice(FIRST).lower()}.{rng.choice(LAST).lower()}{i}@example.fi")
        cols["c05"].append(phone(rng))
        cols["c06"].append(iban(rng))
        cols["c07"].append(f"{rng.randint(1960, 2003)}-{rng.randint(1, 12):02d}-{rng.randint(1, 28):02d}")
        cols["c08"].append(rng.choice(CITIES))
        cols["c09"].append(f"{rng.randint(2000, 6000)},{rng.randint(0, 99):02d}")
        cols["c10"].append(" ".join(rng.choice(["has", "called", "about", "the", "schedule", "and", "sick", "leave",
                                                "request", "for", "next", "week", "please", "advise", "manager"])
                                    for _ in range(14)) + f" #{i}")
        cols["c11"].append(rng.choice(["M", "F"]))
        cols["c12"].append(f"10.{rng.randint(0, 255)}.{rng.randint(0, 255)}.{rng.randint(1, 254)}")
    return cols


EXPECTED = {
    "c01": "record_key",
    "c02": "direct_identifier",
    "c03": "direct_identifier",
    "c04": "direct_identifier",
    "c05": "direct_identifier",
    "c06": "direct_identifier",
    "c07": "quasi_identifier",
    "c08": "quasi_identifier",
    "c09": "sensitive_attribute",
    "c10": "free_text",
    "c11": "quasi_identifier",
    "c12": "technical_identifier",
}
