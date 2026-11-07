"""Field inventory: one entry per (table, column) with a role, subtype and the evidence for it.

Signals: value validators, date parsing, cardinality and uniqueness, foreign-key containment between
tables, physiological range and unit signals, a small health lexicon, and header tokens (ignored when the
header is an uninformative index). Evidence strings carry signal names and aggregate fractions only.
"""

from __future__ import annotations

import re

import pandas as pd

from pets_release.detect import signals as S

ROLES = (
    "direct_identifier", "quasi_identifier", "sensitive_attribute", "technical_identifier",
    "free_text", "record_key", "non_sensitive",
)
SAMPLE = 2000
MIN_FK_DISTINCT = 3

MUNICIPALITIES = frozenset(
    "turku helsinki espoo vantaa tampere oulu raisio naantali kaarina lieto salo paimio parainen "
    "uusikaupunki rusko masku mynämäki nousiainen sauvo kemiönsaari loimaa somero vehmaa aura "
    "pori rauma jyväskylä kuopio lahti kouvola joensuu lappeenranta hämeenlinna vaasa seinäjoki "
    "rovaniemi kotka kokkola mikkeli hyvinkää nurmijärvi järvenpää porvoo lohja kirkkonummi kerava "
    "åbo helsingfors esbo vanda tammerfors nådendal pargas kimito".split()
)
HEALTH_WORDS = frozenset(
    "icu died deceased admitted ward discharged positive negative pregnant pregnancy disability "
    "sick sickleave diagnosis chronic surgery therapy medication treated unwell".split()
)

# header token rules: (regex on "_"-joined tokens, role, subtype); first match wins
NAME_RULES: list[tuple[str, str, str]] = [
    (r"hetu|ssn|personal_?id|national_?id|henkilotunnus|henkilötunnus", "direct_identifier", "NATIONAL_ID"),
    (r"e_?mail|sähköposti", "direct_identifier", "EMAIL"),
    (r"phone|mobile|puhelin|gsm", "direct_identifier", "PHONE"),
    (r"iban|bank_?account", "direct_identifier", "IBAN"),
    (r"(^|_)(pan|card_?number|card_?no)($|_)", "direct_identifier", "PAYMENT_CARD"),
    (r"plate|rekisteri", "direct_identifier", "LICENSE_PLATE"),
    (r"address|street|osoite|katu", "direct_identifier", "STREET_ADDRESS"),
    (r"(^|_)(first|last|given|sur|full|family|patient|holder|guardian|physician|author|contact)_?name|^name$|"
     r"_name$|(^|_)(sukunimi|etunimi|nimi)($|_)", "direct_identifier", "PERSON_NAME"),
    (r"(^|_)(ip|src_ip|dst_ip|client_ip)($|_)|ip_addr", "technical_identifier", "IP_ADDRESS"),
    (r"(^|_)mac($|_)", "technical_identifier", "MAC_ADDRESS"),
    (r"host", "technical_identifier", "HOSTNAME"),
    (r"upn|user_?name|login|(^|_)user($|_)|account_?name", "technical_identifier", "USERNAME"),
    (r"imei|device|unit_?id|ambulance_?unit", "technical_identifier", "DEVICE_ID"),
    (r"gsrn|metering|meter_?id|meter_?point", "technical_identifier", "METER_ID"),
    (r"(^|_)(employee|staff|physician|agent|worker)_?id|(^|_)emp_?(no|id)", "technical_identifier", "EMPLOYEE_ID"),
    (r"student_?id|opiskelija", "technical_identifier", "STUDENT_ID"),
    (r"customer_?id|client_?id|asiakas", "technical_identifier", "CUSTOMER_ID"),
    (r"patient_?id", "technical_identifier", "PATIENT_ID"),
    (r"account_?(id|no|number)", "technical_identifier", "ACCOUNT_ID"),
    (r"birth|dob|syntym|born", "quasi_identifier", "BIRTH_DATE"),
    (r"(^|_)age($|_)|^ika$|_ika($|_)", "quasi_identifier", "AGE"),
    (r"(^|_)(sex|gender)($|_)|sukupuoli", "quasi_identifier", "SEX"),
    (r"post_?code|postal|(^|_)zip|postinumero", "quasi_identifier", "POSTCODE"),
    (r"municipal|city|town|kunta|kaupunki", "quasi_identifier", "MUNICIPALITY"),
    (r"(^|_)(lat|lon|lng)($|_)|latitude|longitude|coord", "quasi_identifier", "GPS_COORDINATE"),
    (r"(^|_)(ts|timestamp|datetime)($|_)|_at$|time$", "quasi_identifier", "TIMESTAMP"),
    (r"date|päivä|paiva", "quasi_identifier", "DATE"),
    (r"language|kieli|nationality|citizen|kansalaisuus", "quasi_identifier", "LANGUAGE"),
    (r"employer|occupation|profession|job_?title|ammatti|työnantaja|company|org(anisation|anization)?$",
     "quasi_identifier", "OCCUPATION"),
    (r"icd|diagnos|disease|condition_code|sairaus", "sensitive_attribute", "DIAGNOSIS_CODE"),
    (r"systolic|diastolic|(^|_)bp($|_)|blood|heart|pulse|resp_?rate|spo2|oxygen|temp(erature)?(_c)?$|"
     r"(^|_)temp_|pain|weight|height|bmi|glucose|triage|disposition|readmit|los_|sick|illness|"
     r"absence_?(reason|days)|pregnan|disab|medic|allerg|therap|symptom|vaccin|health", "sensitive_attribute",
     "HEALTH_DATA"),
    (r"income|salary|wage|palkka|tulot|bonus|tax|union|pension|benefit|debt|loan|credit_?score|net_?pay|"
     r"gross|balance|overtime", "sensitive_attribute", "FINANCIAL_DATA"),
    (r"religio|ethnic|political|orientation|union_?fee|special_?support|support_?need|sanction", "sensitive_attribute",
     "SOCIAL_DATA"),
    (r"grade|gpa|score|exam|matricul|credits|absence", "sensitive_attribute", "EDUCATION_DATA"),
    (r"password|secret|token|api_?key|pwd", "technical_identifier", "SECRET"),
    (r"note|text|description|message|comment|complaint|remark|reason|body|transcript|memo|feedback",
     "free_text", "FREE_TEXT"),
    (r"(^|_)id$|_key$|(^|_)uuid$|(^|_)no$", "technical_identifier", "OTHER"),
]
_NAME_RX = [(re.compile(p), r, s) for p, r, s in NAME_RULES]


def _name_hint(name: str) -> tuple[str, str] | None:
    if S.obfuscated(name):
        return None
    joined = "_".join(S.name_tokens(name))
    for rx, role, sub in _NAME_RX:
        if rx.search(joined):
            return role, sub
    return None


def _sample(values: list[str]) -> list[str]:
    if len(values) <= SAMPLE:
        return values
    step = len(values) / SAMPLE
    return [values[int(i * step)] for i in range(SAMPLE)]


def _frac(vals: list[str], fn) -> float:
    return sum(1 for v in vals if fn(v)) / len(vals) if vals else 0.0


def _pct(x: float) -> str:
    return f"{round(100 * x)}%"


class _Col:
    """Aggregate profile of one column."""

    def __init__(self, name: str, series: pd.Series):
        self.name = name
        s = series.fillna("").astype(str).str.strip()
        self.n_rows = len(s)
        nonempty = s[s != ""]
        self.n = len(nonempty)
        self.distinct = int(nonempty.nunique()) if self.n else 0
        self.unique_ratio = self.distinct / self.n if self.n else 0.0
        self.fill = self.n / self.n_rows if self.n_rows else 0.0
        self.values = _sample(nonempty.tolist())
        self.hint = _name_hint(name)
        nums = [S.number(v) for v in self.values]
        self.num_frac = _frac_nums(nums)
        self.nums = [x for x in nums if x is not None]


def _frac_nums(nums: list) -> float:
    return sum(1 for x in nums if x is not None) / len(nums) if nums else 0.0


def _words(v: str) -> int:
    return len(v.split())


def _result(role: str, sub: str, *ev: str) -> tuple[str, str, list[str]]:
    return role, sub, list(ev)


# Follow-up #87: a column with values but no positive signal is not evidence of non-sensitivity (a forgotten
# quasi-identifier must not look free to release), so it gets the cautious role quasi_identifier. Only an empty
# column, which has nothing to release, may be non_sensitive.
UNMATCHED_ROLE = "quasi_identifier"


def _unmatched(sub: str, *ev: str) -> tuple[str, str, list[str]]:
    return _result(UNMATCHED_ROLE, sub, *ev, "no positive signal: cautious default")


def _classify(c: _Col, link: str | None) -> tuple[str, str, list[str]]:
    vals, hint = c.values, c.hint
    if not vals:
        if hint:
            return _result(hint[0], hint[1], f"header:{hint[1].lower()}", "no values")
        return _result("non_sensitive", "OTHER", "empty column")

    # 1. strong value validators (checksums and formats)
    strong: list[tuple[str, float, str, str]] = [
        ("hetu", 0.6, "direct_identifier", "NATIONAL_ID"),
        ("email", 0.6, "direct_identifier", "EMAIL"),
        ("iban", 0.6, "direct_identifier", "IBAN"),
    ]
    fns = {"hetu": S.hetu, "email": S.email, "iban": S.iban}
    for key, thr, role, sub in strong:
        f = _frac(vals, fns[key])
        if f >= thr:
            return _result(role, sub, f"validator:{key} {_pct(f)}")

    f = _frac(vals, S.hetu_shape)
    if f >= 0.8 and c.distinct > 1:
        return _result("direct_identifier", "NATIONAL_ID", f"format:hetu-shape {_pct(f)}")

    f = _frac(vals, S.luhn)
    if f >= 0.8:
        if link == "key":
            return _result("record_key", "CARD_ID", f"validator:luhn {_pct(f)}", "fk-referenced key")
        if c.unique_ratio >= 0.98 and hint and hint[1] == "CARD_ID":
            return _result("record_key", "CARD_ID", f"validator:luhn {_pct(f)}", "unique")
        return _result("direct_identifier", "PAYMENT_CARD", f"validator:luhn {_pct(f)}")

    for key, fn, sub in (("ipv4", S.ipv4, "IP_ADDRESS"), ("ipv6", S.ipv6, "IP_ADDRESS"), ("mac", S.mac, "MAC_ADDRESS")):
        f = _frac(vals, fn)
        if f >= 0.8:
            return _result("technical_identifier", sub, f"validator:{key} {_pct(f)}")

    f = _frac(vals, S.url)
    if f >= 0.8:
        return _result("technical_identifier", "URL", f"validator:url {_pct(f)}")
    f = _frac(vals, S.user_agent)
    if f >= 0.8:
        return _result("technical_identifier", "USER_AGENT", f"validator:user-agent {_pct(f)}")
    f = _frac(vals, S.hex_digest)
    if f >= 0.8:
        return _result("technical_identifier", "OTHER", f"validator:hex-digest {_pct(f)}")

    f = _frac(vals, S.timestamp)
    if f >= 0.8:
        return _result("quasi_identifier", "TIMESTAMP", f"validator:timestamp {_pct(f)}")

    f = _frac(vals, S.icd10)
    if f >= 0.8 and not (c.num_frac > 0.5):
        return _result("sensitive_attribute", "DIAGNOSIS_CODE", f"validator:icd10 {_pct(f)}")

    # 2. dates
    years = [y for y in (S.date_year(v) for v in vals) if y is not None]
    if len(years) / len(vals) >= 0.8:
        span = max(years) - min(years)
        is_birth = (hint and hint[1] == "BIRTH_DATE") or span >= 25
        sub = "BIRTH_DATE" if is_birth else "DATE"
        return _result("quasi_identifier", sub, f"validator:date {_pct(len(years) / len(vals))}", f"year-span:{span}")

    # 3. phone (only when formatted as a phone number, not a plain measure)
    f = _frac(vals, S.phone)
    if f >= 0.7 and not (hint and hint[1] in ("EMPLOYEE_ID", "CUSTOMER_ID", "ACCOUNT_ID", "METER_ID")):
        return _result("direct_identifier", "PHONE", f"validator:phone {_pct(f)}")

    # 4. licence plate
    f = _frac(vals, S.plate)
    if f >= 0.8 and c.distinct > 1:
        return _result("direct_identifier", "LICENSE_PLATE", f"validator:plate {_pct(f)}")

    # 5. free text, person names, addresses
    mean_len = sum(len(v) for v in vals) / len(vals)
    mean_words = sum(_words(v) for v in vals) / len(vals)
    if (mean_len >= 40 and mean_words >= 6) or (hint and hint[0] == "free_text" and mean_words >= 3):
        return _result("free_text", "FREE_TEXT", f"mean-words:{round(mean_words)}", f"mean-len:{round(mean_len)}")

    f = _frac(vals, S.street_address)
    if f >= 0.6:
        return _result("direct_identifier", "STREET_ADDRESS", f"validator:street-address {_pct(f)}")
    f = _frac(vals, S.person_name)
    if f >= 0.7 and c.unique_ratio >= 0.2 and not (hint and hint[1] in ("MUNICIPALITY", "OCCUPATION")):
        return _result("direct_identifier", "PERSON_NAME", f"validator:person-name {_pct(f)}")

    # 6. coordinates
    if c.num_frac >= 0.95 and c.nums:
        has_frac = sum(1 for v in vals if re.search(r"[.,]\d{3,}$", v)) / len(vals) >= 0.8
        if has_frac:
            lo, hi = min(c.nums), max(c.nums)
            if 58.0 <= lo and hi <= 71.0:
                return _result("quasi_identifier", "GPS_COORDINATE", "range:latitude")
            if 19.0 <= lo and hi <= 32.0:
                return _result("quasi_identifier", "GPS_COORDINATE", "range:longitude")

    # 7. small vocabularies
    low = {v.lower() for v in vals}
    if len(low) <= 4 and low <= {"m", "f", "male", "female", "mies", "nainen", "man", "kvinna", "x", "other", "unknown"}:
        return _result("quasi_identifier", "SEX", f"vocabulary:sex distinct={len(low)}")
    if len(low) <= 6 and low <= {"fi", "sv", "en", "fin", "swe", "eng", "suomi", "svenska", "english", "ru", "et"}:
        return _result("quasi_identifier", "LANGUAGE", f"vocabulary:language distinct={len(low)}")
    f = sum(1 for v in vals if v.lower() in MUNICIPALITIES) / len(vals)
    if f >= 0.6:
        return _result("quasi_identifier", "MUNICIPALITY", f"gazetteer:municipality {_pct(f)}")

    # 8. technical / record identifiers
    idf = _frac(vals, S.id_like)
    digits_key = c.num_frac >= 0.99 and all(v.isdigit() for v in vals) and len({len(v) for v in vals}) == 1 and len(vals[0]) >= 5
    if link == "key":
        return _result("record_key", "RECORD_ID", "fk-referenced key", f"unique {_pct(c.unique_ratio)}")
    if link == "ref":
        return _result("technical_identifier", "RECORD_ID", "values contained in another table's key")
    if (idf >= 0.8 or (digits_key and not hint)) and c.distinct > 1:
        if hint and hint[0] == "technical_identifier":
            if c.unique_ratio >= 0.98 and hint[1] in ("OTHER",):
                return _result("record_key", "RECORD_ID", "id-pattern", f"unique {_pct(c.unique_ratio)}")
            return _result(hint[0], hint[1], f"header:{hint[1].lower()}", f"id-pattern {_pct(idf)}")
        if c.unique_ratio >= 0.98:
            return _result("record_key", "RECORD_ID", f"id-pattern {_pct(idf)}", f"unique {_pct(c.unique_ratio)}")
        return _result("technical_identifier", "OTHER", f"id-pattern {_pct(idf)}",
                       f"repeats {_pct(1 - c.unique_ratio)}")

    # 9. numerics: age, money, physiology
    if c.num_frac >= 0.95 and c.nums:
        nums = sorted(c.nums)
        lo, hi, med = nums[0], nums[-1], nums[len(nums) // 2]
        mean = sum(nums) / len(nums)
        decimals = sum(1 for v in vals if re.search(r"[.,]\d{1,2}$", v)) / len(vals)
        ints = all(x == int(x) for x in nums)
        distinct = len(set(nums))
        if hint and hint[0] in ("sensitive_attribute", "quasi_identifier"):
            return _result(hint[0], hint[1] if hint[1] != "DATE" else "MEASUREMENT", f"header:{hint[1].lower()}",
                           f"numeric {_pct(c.num_frac)}")
        if ints and 16 <= lo and hi <= 100 and distinct >= 25 and 25 <= mean <= 60:
            return _result("quasi_identifier", "AGE", "range:age", f"distinct={distinct}")
        if 34.0 <= lo and hi <= 42.5 and decimals >= 0.8 and distinct >= 5:
            return _result("sensitive_attribute", "MEASUREMENT", "range:body-temperature")
        if decimals >= 0.8 and med >= 200 and distinct > 20:
            return _result("sensitive_attribute", "FINANCIAL_DATA", "decimal-amounts", f"median>={int(med // 100) * 100}")
        if ints and 1000 <= med <= 30000 and distinct >= 50 and c.unique_ratio > 0.3:
            return _result("sensitive_attribute", "FINANCIAL_DATA", "integer-amounts")
        return _unmatched("MEASUREMENT", f"numeric {_pct(c.num_frac)}", f"distinct={distinct}")

    # 10. header tokens decide what values could not
    if hint:
        role, sub = hint
        if role == "technical_identifier" and c.unique_ratio >= 0.98 and sub == "OTHER":
            return _result("record_key", "RECORD_ID", f"header:{sub.lower()}", "unique")
        if sub == "PERSON_NAME" and c.distinct <= 30:
            return _result("quasi_identifier", "CATEGORY", "name-token but low cardinality")
        return _result(role, sub, f"header:{sub.lower()}")

    # 11. categorical vocabularies
    tokens = {t for v in vals for t in re.split(r"[^a-zåäö]+", v.lower()) if t}
    health = sum(1 for v in vals if set(re.split(r"[^a-zåäö]+", v.lower())) & HEALTH_WORDS) / len(vals)
    if health >= 0.3 and c.distinct <= 50:
        return _result("sensitive_attribute", "HEALTH_DATA", f"lexicon:health {_pct(health)}")
    if c.distinct <= 2 and low <= {"0", "1", "y", "n", "yes", "no", "true", "false", "kyllä", "ei"}:
        return _unmatched("CATEGORY", "flag")
    if c.distinct <= 60 or c.unique_ratio < 0.3:
        return _unmatched("CATEGORY", f"categorical distinct={c.distinct}")
    if mean_words >= 3:
        return _result("free_text", "FREE_TEXT", f"mean-words:{round(mean_words)}")
    del tokens
    return _unmatched("OTHER", f"distinct={c.distinct}")


def _links(tables: dict[str, pd.DataFrame]) -> dict[tuple[str, str], str]:
    """Foreign-key containment. 'key': unique column whose values another table references.
    'ref': column whose values are contained in a unique key column of another table."""
    keys: dict[tuple[str, str], set[str]] = {}
    for t, df in sorted(tables.items()):
        for col in df.columns:
            s = df[col].fillna("").astype(str).str.strip()
            s = s[s != ""]
            if len(s) >= MIN_FK_DISTINCT and s.nunique() == len(s):
                if max(len(v) for v in s.iloc[:200]) >= 5 or not s.iloc[0].isdigit():  # skip small counters
                    keys[(t, col)] = set(s)
    out: dict[tuple[str, str], str] = {}
    for t, df in sorted(tables.items()):
        for col in df.columns:
            s = df[col].fillna("").astype(str).str.strip()
            s = s[s != ""]
            if len(s) < MIN_FK_DISTINCT:
                continue
            distinct = set(s.drop_duplicates().tolist()[:5000])
            if len(distinct) < MIN_FK_DISTINCT:
                continue
            for (kt, kc), kset in keys.items():
                if kt == t:
                    continue
                if len(distinct & kset) / len(distinct) >= 0.95 and len(kset) >= MIN_FK_DISTINCT:
                    out[(kt, kc)] = "key"
                    if (t, col) not in keys:
                        out.setdefault((t, col), "ref")
                    break
    return out


def detect_table(df: pd.DataFrame, dataset: str, table: str, links: dict[str, str] | None = None) -> list[dict]:
    links = links or {}
    rows = []
    for col in df.columns:
        profile = _Col(str(col), df[col])
        role, sub, ev = _classify(profile, links.get(str(col)))
        if role not in ROLES:
            raise ValueError("classifier produced an unknown role")
        rows.append({"dataset": dataset, "table": table, "column": str(col), "role": role, "subtype": sub,
                     "evidence": ev})
    return rows


def detect_dataset(dataset: str, tables: dict[str, pd.DataFrame]) -> list[dict]:
    links = _links(tables)
    out: list[dict] = []
    for t in sorted(tables):
        per = {col: kind for (tt, col), kind in links.items() if tt == t}
        out.extend(detect_table(tables[t], dataset, t, per))
    return out
