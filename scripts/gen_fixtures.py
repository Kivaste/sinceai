"""Deterministic synthetic mini-kit generator (ticket 03).

Writes small health and customer_service tables that use the challenge kit's table and column
names, sized so the required utility tasks (H-U2/4/6/7/8, CS-U1/3/4/5) run and score.

Every value comes from vocabularies defined in this file and one seeded PRNG. The script reads no
input file and no environment variable, so the same code always writes byte-identical CSVs.

    python scripts/gen_fixtures.py [--out tests/fixtures/minikit]
"""

from __future__ import annotations

import argparse
import csv
import random
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

SEED = 20251108
DEFAULT_OUT = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "minikit"
TS = "%Y-%m-%dT%H:%M:%S"

# --------------------------------------------------------------------------- schema (names only)
ED_VISITS_COLUMNS = [
    "visit_id", "patient_hetu", "patient_name", "date_of_birth", "sex", "phone", "home_address",
    "postcode", "municipality", "arrival_ts", "arrival_mode", "ambulance_unit", "triage",
    "chief_complaint", "icd10_primary", "icd10_secondary", "systolic_bp", "diastolic_bp",
    "heart_rate", "resp_rate", "temp_c", "spo2", "pain_nrs", "attending_physician_id",
    "attending_physician_name", "discharge_ts", "los_minutes", "disposition", "readmit_30d",
]
LAB_COLUMNS = [
    "lab_id", "visit_id", "test_code", "test_name", "value", "unit", "ref_range",
    "abnormal_flag", "sampled_ts",
]
NOTE_COLUMNS = [
    "note_id", "visit_id", "note_type", "author_staff_id", "author_name", "written_ts",
    "language", "note_text",
]
STATS_COLUMNS = ["stat_id", "week", "municipality", "age_band", "sex", "diagnosis_group", "visits"]
CUSTOMER_COLUMNS = [
    "customer_id", "customer_number", "full_name", "hetu", "street_address", "postcode", "city",
    "email", "phone", "preferred_language", "customer_since", "products", "contract_number",
    "payment_method", "iban", "marketing_consent", "payment_default_flag", "accessibility_needs",
]
CONVERSATION_COLUMNS = [
    "conversation_id", "customer_id", "agent_id", "agent_name", "channel", "language",
    "started_ts", "intent", "sentiment", "csat", "resolved", "handle_time_s", "n_turns", "split",
    "agent_note",
]
TURN_COLUMNS = ["turn_id", "conversation_id", "seq", "speaker", "ts", "text"]

# --------------------------------------------------------------------------- synthetic vocabularies
FIRST_A = ["Ka", "Mi", "To", "Lu", "Ve", "Ni", "Sa", "Ra", "Ju", "Ha", "Pe", "Ol"]
FIRST_B = ["rin", "lo", "mas", "vi", "ko", "ra", "ten", "mo", "ssa", "ni"]
LAST_A = ["Kor", "Vael", "Mast", "Ruut", "Pello", "Hark", "Sund", "Tuur", "Lind", "Nyk", "Aal", "Vir"]
LAST_B = ["ainen", "ola", "mäki", "berg", "nen", "koski", "lund", "ström"]
STREET_STEM = ["SynthKoivu", "SynthKuusi", "SynthPajan", "SynthMeri", "SynthHarju", "SynthLehto", "SynthNiitty", "SynthRinne", "SynthKallio", "SynthAallon"]
STREET_END = ["katu", "tie", "kuja", "polku"]
MUNICIPALITIES = [
    "Pellonmaa", "Harjuvalli", "Kivilahti", "Rantalinna", "Suvikoski", "Ylikorpi", "Alamäki",
    "Tuulisaari", "Havukoski", "Linnanvuori",
]
POSTCODES = [
    "00100", "00520", "02100", "20100", "20540", "21200", "33100", "50100", "80100", "90100",
]
MUNI_WEIGHTS = [20, 16, 13, 11, 9, 7, 6, 5, 4, 3]
NON_RESIDENT = "non-resident"
PHYSICIANS = [(f"SYNP-{i:03d}", f"{LAST_A[i]}{LAST_B[i % len(LAST_B)]}") for i in range(12)]
NURSES = [(f"SYNR-{i:03d}", f"{LAST_A[(i + 3) % 12]}{LAST_B[(i + 2) % len(LAST_B)]}") for i in range(10)]

# code -> (group, complaint phrases). Codes are public ICD-10 identifiers.
ICD_GROUPS = [
    ("I21.4", "cardiovascular", ["chest pain radiating to the arm", "pressure behind the breastbone"]),
    ("I48.9", "cardiovascular", ["irregular heartbeat", "palpitations since morning"]),
    ("I63.9", "neurological", ["sudden weakness on one side", "slurred speech"]),
    ("G45.9", "neurological", ["transient numbness in the hand", "short episode of blurred vision"]),
    ("R55", "other", ["fainted at home", "brief loss of consciousness"]),
    ("Z03.9", "other", ["observation after a minor event", "requested check-up"]),
    ("J18.9", "respiratory", ["cough with fever and breathlessness", "productive cough for a week"]),
    ("J44.1", "respiratory", ["worsening breathlessness", "wheeze and cough"]),
    ("J10.1", "ILI", ["fever, aching muscles and dry cough", "sudden fever with chills"]),
    ("J06.9", "ILI", ["sore throat and runny nose with fever", "cold symptoms with a fever"]),
    ("J21.0", "RSV", ["infant with fast breathing and cough", "child with wheeze and poor feeding"]),
    ("H66.9", "other_infection", ["earache and fever", "ear pain in a child"]),
    ("R50.9", "other_infection", ["fever of unknown cause", "high temperature for three days"]),
    ("A08.4", "gastrointestinal", ["vomiting and diarrhoea", "stomach cramps and nausea"]),
    ("K35.8", "gastrointestinal", ["pain in the lower right abdomen", "abdominal pain with fever"]),
    ("N20.0", "urological", ["severe flank pain", "colicky pain and blood in urine"]),
    ("N39.0", "urological", ["burning on urination and fever", "frequent urination with pain"]),
    ("S52.5", "injury", ["fell on ice and hurt the wrist", "wrist pain after a fall"]),
    ("S72.0", "injury", ["fall with hip pain", "cannot bear weight after a slip"]),
    ("F10.0", "intoxication", ["found drowsy after drinking", "intoxicated and confused"]),
    ("T78.2", "allergy", ["swelling of the lips after a meal", "hives and itching"]),
    ("F41.0", "mental_health", ["panic attack", "overwhelming anxiety"]),
    ("F32.9", "mental_health", ["low mood and exhaustion", "feels hopeless"]),
    ("E10.1", "endocrine", ["high blood sugar and thirst", "nausea with high glucose"]),
    ("E87.1", "endocrine", ["weakness and low sodium on a test", "confusion and thirst"]),
    ("M54.5", "musculoskeletal", ["low back pain", "back pain after lifting"]),
    ("L03.1", "skin", ["red swollen painful leg", "spreading skin redness"]),
    ("O20.0", "pregnancy", ["bleeding in early pregnancy", "cramping in early pregnancy"]),
    ("A41.9", "infection_severe", ["fever, chills and low blood pressure", "rigors and confusion"]),
]
GROUP_BASE_CRP = {
    "infection_severe": 140, "respiratory": 55, "other_infection": 40, "gastrointestinal": 25,
    "urological": 35, "skin": 45, "ILI": 30, "RSV": 28, "cardiovascular": 8, "neurological": 6,
    "injury": 5, "endocrine": 9, "mental_health": 3, "intoxication": 4, "allergy": 4,
    "musculoskeletal": 6, "pregnancy": 4, "other": 4,
}
GROUP_FEVER = {"ILI": 1.9, "RSV": 1.6, "infection_severe": 2.2, "respiratory": 1.2, "other_infection": 1.5,
               "urological": 1.0, "skin": 0.8, "gastrointestinal": 0.6}
TRIAGE = ["A", "B", "C", "D", "E"]
TRIAGE_WEIGHTS = [3, 14, 38, 30, 15]
TRIAGE_LOS = {"A": 420, "B": 300, "C": 220, "D": 150, "E": 90}
ARRIVAL_MODES = ["walk-in", "ambulance", "helicopter", "police"]
ARRIVAL_WEIGHTS = [66, 30, 1, 3]
DISPOSITIONS = ["home", "admitted_ward", "icu", "transfer", "died", "left_without_being_seen", "cancelled_duplicate"]
DISPOSITION_WEIGHTS = [66, 18, 3, 3, 1, 4, 5]
HOUR_WEIGHTS = [2, 1, 1, 1, 1, 2, 3, 5, 7, 9, 10, 10, 9, 8, 8, 8, 8, 7, 6, 5, 4, 3, 3, 2]
NOTE_LANGS = ["fi", "sv", "en"]
NOTE_TEXT = {
    "fi": "Potilas {name} tuli vastaanotolle, vointi arvioitu, jatkotoimet sovittu.",
    "sv": "Patienten {name} kom till mottagningen, tillståndet bedömdes, fortsatt vård överenskommen.",
    "en": "Patient {name} arrived for assessment, condition reviewed, follow-up agreed.",
}

N_PATIENTS = 900
N_VISITS = 1500
N_ROUND_ROBIN = 1200  # first visits cycle through every ICD code so each group has plenty of rows

# customer service
INTENT_CLASSES = [
    "billing_question", "payment_extension", "invoice_copy", "plan_change", "roaming_activation",
    "sim_replacement", "network_outage", "slow_internet", "router_setup", "contract_cancellation",
    "address_change", "electricity_contract", "price_increase", "device_warranty", "data_privacy_request",
]
INTENT_TEXT = {
    "billing_question": (
        ["I do not understand the amount on my latest bill", "why is this month's bill so high"],
        ["the bill shows a charge for an extra service", "the total on the bill is larger than usual"],
        ["I have explained each line of the bill and corrected the extra charge", "the bill lines are explained and a credit is booked"],
    ),
    "payment_extension": (
        ["I need more time to pay my invoice", "can I postpone the due date of my payment"],
        ["I can pay after the next salary arrives", "I would like to split the payment into parts"],
        ["I have moved the due date by two weeks", "a payment plan is now set up for you"],
    ),
    "invoice_copy": (
        ["please send me a copy of my invoice", "I lost last month's invoice and need a copy"],
        ["I need the invoice document for my accountant", "I need a paper copy of the invoice"],
        ["the invoice copy has been sent to your email", "a copy of the invoice is on its way"],
    ),
    "plan_change": (
        ["I want to change my mobile plan", "I would like a cheaper subscription"],
        ["my current plan has too little data", "I want unlimited data in my subscription"],
        ["your subscription is now changed to the new plan", "the new plan starts from the next billing period"],
    ),
    "roaming_activation": (
        ["I am travelling abroad and need roaming", "please activate roaming for my trip"],
        ["I leave for a holiday outside Europe tomorrow", "I need data roaming during the journey"],
        ["roaming is now active on your number", "the roaming package is switched on until your return"],
    ),
    "sim_replacement": (
        ["my SIM card is broken and I need a new one", "I lost my phone and need a replacement SIM"],
        ["the old SIM card does not register any more", "please block the lost card and send a new SIM"],
        ["a replacement SIM card is on its way", "the old SIM is blocked and a new one is ordered"],
    ),
    "network_outage": (
        ["there is no mobile signal in my area", "the network is down at my house"],
        ["calls have failed since this morning", "my neighbours also have no signal"],
        ["there is a known outage in your area and the repair is under way", "the outage is logged and engineers are working on it"],
    ),
    "slow_internet": (
        ["my internet connection is very slow", "the broadband speed is far below what I pay for"],
        ["video calls keep freezing in the evening", "a speed test shows a tiny fraction of my plan"],
        ["I have refreshed the line and the speed should improve", "a line test is done and the speed is now back to normal"],
    ),
    "router_setup": (
        ["I need help to set up my new router", "the router will not connect after installation"],
        ["the router lights are blinking red", "I cannot find the wifi password for the router"],
        ["the router is configured and the wifi name is set", "after a reset the router is online again"],
    ),
    "contract_cancellation": (
        ["I want to cancel my contract", "I would like to terminate my subscription"],
        ["I am moving to a different provider", "I no longer need the service"],
        ["the cancellation is registered and takes effect at the end of the notice period", "your contract ends after the notice period"],
    ),
    "address_change": (
        ["I have moved and need to update my address", "please change the delivery address on my account"],
        ["my new address starts next week", "the invoices should go to my new home"],
        ["the address on your account is updated", "I have saved the new address for your invoices"],
    ),
    "electricity_contract": (
        ["I want to switch my electricity contract", "question about my electricity tariff"],
        ["I would like a fixed price for the electricity", "my electricity contract is ending soon"],
        ["the new electricity contract starts next month", "a fixed price electricity offer is booked for you"],
    ),
    "price_increase": (
        ["why did the price of my subscription go up", "I received a letter about a price increase"],
        ["the monthly fee is higher than before", "nobody told me the price would change"],
        ["the price change is explained and a loyalty discount is applied", "I have added a discount to offset the price rise"],
    ),
    "device_warranty": (
        ["my phone broke and it is under warranty", "the screen of my new device stopped working"],
        ["the device is only five months old", "the battery of the phone swells and drains fast"],
        ["a warranty repair is arranged and a courier collects the device", "the warranty claim is approved and a replacement ships today"],
    ),
    "data_privacy_request": (
        ["I want to see what personal data you hold about me", "please delete my personal data"],
        ["I would like a copy of my stored data", "I withdraw my consent for marketing"],
        ["your data request is registered and answered within the legal time", "the privacy team will send the data export to you"],
    ),
}
AGENT_OPEN = {
    "en": "Hello and thank you for contacting Testiverkko customer service, how can I help you today",
    "fi": "Hei ja kiitos yhteydenotostasi Testiverkko asiakaspalvelu, miten voin auttaa tänään",
    "sv": "Hej och tack för att du kontaktar Testiverkko kundtjänst, hur kan jag hjälpa dig idag",
}
AGENT_CLOSE = {
    "en": "Is there anything else I can help you with today, thank you for contacting us and have a nice day",
    "fi": "Voinko auttaa vielä jossakin muussa, kiitos yhteydenotostasi ja mukavaa päivää",
    "sv": "Kan jag hjälpa dig med något annat idag, tack för att du kontaktade oss och ha en fin dag",
}
AGENT_ASK = "Could you please confirm your name and your customer number so I can find your account"
AGENT_CHECK = "Thank you, I found your account and I am checking the details now"
CUSTOMER_THANKS = "Thank you very much for your help, that solves my problem"
CHANNELS = ["chat", "phone", "email"]
LANGUAGES = ["en", "fi", "sv"]
SENTIMENTS = ["negative", "neutral", "positive"]
PRODUCTS = ["mobile", "broadband", "electricity", "tv", "mobile;broadband", "mobile;electricity", "broadband;tv"]
PAYMENT_METHODS = ["invoice", "direct_debit", "card"]
ACCESSIBILITY = ["", "", "", "", "", "", "hearing", "visual"]

N_CUSTOMERS = 160
N_TRAIN = 195
N_EVAL = 60


# --------------------------------------------------------------------------- helpers
def _first(rng: random.Random) -> str:
    return rng.choice(FIRST_A) + rng.choice(FIRST_B)


def _last(rng: random.Random) -> str:
    return rng.choice(LAST_A) + rng.choice(LAST_B)


def _street(rng: random.Random) -> str:
    return f"{rng.choice(STREET_STEM)}{rng.choice(STREET_END)} {rng.randint(1, 80)}"


def _phone(rng: random.Random) -> str:
    return f"+358 40 555 {rng.randint(0, 9999):04d}"


def _hetu(rng: random.Random, dob: datetime, female: bool, used: set[str]) -> str:
    """Valid, unique identity code for one person: real century sign, the person's own birth date,
    mod-31 check character, and an individual number in the reserved 900-999 test range."""
    base = f"{dob.day:02d}{dob.month:02d}{dob.year % 100:02d}"
    sign = "A" if dob.year >= 2000 else "-"
    start = rng.randint(900, 998)
    for step in range(100):
        ind = 900 + (start - 900 + step) % 99
        if (ind % 2 == 0) != female:  # even individual number = female
            ind += 1
        code = f"{base}{sign}{ind:03d}{'0123456789ABCDEFHJKLMNPRSTUVWXY'[int(base + f'{ind:03d}') % 31]}"
        if code not in used:
            used.add(code)
            return code
    raise RuntimeError("no free individual number for this birth date")


def _iban(rng: random.Random, used: set[str]) -> str:
    """Valid Finnish IBAN (18 chars, mod-97 check digits) with a synthetic 99xxxx bank part."""
    while True:
        bban = "99" + "".join(str(rng.randint(0, 9)) for _ in range(12))
        check = 98 - int(bban + "151800") % 97  # F=15, I=18, then "00" for the check digits
        iban = f"FI{check:02d}{bban}"
        if iban not in used:
            used.add(iban)
            return " ".join([iban[i:i + 4] for i in range(0, 16, 4)] + [iban[16:]])

def _age_band(age: int) -> str:
    lo = min(age // 10 * 10, 80)
    return "80+" if lo >= 80 else f"{lo}-{lo + 9}"


def _write(path: Path, header: list[str], rows: list[list[str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh, lineterminator="\n")
        writer.writerow(header)
        writer.writerows(rows)


# --------------------------------------------------------------------------- health
def _health(dest: Path, rng: random.Random, used_hetu: set[str]) -> None:
    patients = []
    for i in range(N_PATIENTS):
        female = rng.random() < 0.52
        age_roll = rng.random()
        year = 2025 - (rng.randint(0, 9) if age_roll < 0.08 else rng.randint(10, 95))
        dob = datetime(year, rng.randint(1, 12), rng.randint(1, 28))
        mi = rng.choices(range(len(MUNICIPALITIES)), MUNI_WEIGHTS)[0]
        municipality = NON_RESIDENT if rng.random() < 0.03 else MUNICIPALITIES[mi]
        patients.append({
            "hetu": _hetu(rng, dob, female, used_hetu), "name": f"{_first(rng)} {_last(rng)}", "dob": dob,
            "sex": "F" if female else "M", "phone": _phone(rng), "address": _street(rng),
            "postcode": POSTCODES[mi], "municipality": municipality,
        })

    raw = []  # (arrival, patient_index, icd index)
    for n in range(N_VISITS):
        p = rng.randrange(N_PATIENTS)
        day = rng.randrange(365)
        hour = rng.choices(range(24), HOUR_WEIGHTS)[0]
        arrival = datetime(2025, 1, 1) + timedelta(days=day, hours=hour, minutes=rng.randrange(60), seconds=rng.randrange(60))
        code_i = n % len(ICD_GROUPS) if n < N_ROUND_ROBIN else rng.randrange(len(ICD_GROUPS))
        raw.append((arrival, p, code_i))
        if rng.random() < 0.10 and n >= N_ROUND_ROBIN:  # a quick return visit by the same patient
            back = arrival + timedelta(days=rng.randint(2, 25), hours=rng.randint(0, 5), minutes=rng.randrange(60))
            if back.year == 2025:
                raw.append((back, p, rng.randrange(len(ICD_GROUPS))))
    raw.sort(key=lambda r: (r[0], r[1], r[2]))

    last_seen: dict[int, list[datetime]] = {}
    for arrival, p, _ in raw:
        last_seen.setdefault(p, []).append(arrival)

    visits, labs, notes = [], [], []
    stats: Counter = Counter()
    lab_n = note_n = 0
    for n, (arrival, p, code_i) in enumerate(raw, start=1):
        pat = patients[p]
        code, group, phrases = ICD_GROUPS[code_i]
        visit_id = f"SYNV-{n:06d}"
        triage = rng.choices(TRIAGE, TRIAGE_WEIGHTS)[0]
        mode = rng.choices(ARRIVAL_MODES, ARRIVAL_WEIGHTS)[0]
        disposition = rng.choices(DISPOSITIONS, DISPOSITION_WEIGHTS)[0]
        los = max(15, int(rng.gauss(TRIAGE_LOS[triage], TRIAGE_LOS[triage] * 0.35)))
        discharge = arrival + timedelta(minutes=los)
        temp = min(41.8, max(35.2, round(rng.gauss(36.9 + GROUP_FEVER.get(group, 0.0), 0.5), 1)))
        crp = max(0.6, round((temp - 36.6) * 14 + GROUP_BASE_CRP[group] * rng.uniform(0.4, 1.6) + rng.uniform(0, 4), 1))
        age = arrival.year - pat["dob"].year
        later = [t for t in last_seen[p] if t > arrival and (t - arrival) <= timedelta(days=30)]
        phys_id, phys_name = rng.choice(PHYSICIANS)
        secondary = rng.choice(ICD_GROUPS)[0] if rng.random() < 0.12 else ""
        visits.append([
            visit_id, pat["hetu"], pat["name"], pat["dob"].strftime("%Y-%m-%d"), pat["sex"], pat["phone"],
            pat["address"], pat["postcode"], pat["municipality"], arrival.strftime(TS), mode,
            f"SYNU-{rng.randint(1, 9):02d}" if mode == "ambulance" else "", triage, rng.choice(phrases),
            code, secondary, str(rng.randint(95, 175)), str(rng.randint(55, 100)), str(rng.randint(52, 125)),
            str(rng.randint(11, 26)), f"{temp:.1f}", str(rng.randint(90, 100)), str(rng.randint(0, 9)),
            phys_id, phys_name, discharge.strftime(TS), str(los), disposition, "1" if later else "0",
        ])
        sampled = (arrival + timedelta(minutes=35)).strftime(TS)
        lab_rows = [("P-CRP", "C-reactive protein", f"{crp:.1f}" if crp >= 1 else "<1", "mg/L", "<3", "H" if crp > 3 else "")]
        if rng.random() < 0.7:
            k = round(rng.uniform(3.2, 5.4), 1)
            lab_rows.append(("P-K", "Potassium", f"{k:.1f}", "mmol/L", "3.5-5.0", "H" if k > 5.0 else ("L" if k < 3.5 else "")))
        if rng.random() < 0.5:
            hb = round(rng.uniform(95, 165))
            lab_rows.append(("B-Hb", "Haemoglobin", str(hb), "g/L", "117-175", "L" if hb < 117 else ""))
        for test_code, test_name, value, unit, ref, flag in lab_rows:
            lab_n += 1
            labs.append([f"SYNL-{lab_n:06d}", visit_id, test_code, test_name, value, unit, ref, flag, sampled])
        lang = rng.choice(NOTE_LANGS)
        author_id, author_name = rng.choice(NURSES if n % 2 else PHYSICIANS)
        note_n += 1
        notes.append([
            f"SYNN-{note_n:06d}", visit_id, "nurse_triage" if n % 2 else "physician", author_id, author_name,
            (arrival + timedelta(minutes=10)).strftime(TS), lang, NOTE_TEXT[lang].format(name=pat["name"]),
        ])
        if disposition != "cancelled_duplicate":
            iso = arrival.isocalendar()
            stats[(f"{iso[0]}-W{iso[1]:02d}", pat["municipality"], _age_band(age), pat["sex"], group)] += 1

    stat_rows = [
        [f"SYNS-{i:06d}", *key, str(count)] for i, (key, count) in enumerate(sorted(stats.items()), start=1)
    ]
    out = dest / "health"
    _write(out / "ed_visits.csv", ED_VISITS_COLUMNS, visits)
    _write(out / "lab_results.csv", LAB_COLUMNS, labs)
    _write(out / "clinical_notes.csv", NOTE_COLUMNS, notes)
    _write(out / "published_weekly_stats.csv", STATS_COLUMNS, stat_rows)


# --------------------------------------------------------------------------- customer service
def _customer_service(dest: Path, rng: random.Random, used_hetu: set[str]) -> None:
    used_iban: set[str] = set()
    customers = []
    for i in range(1, N_CUSTOMERS + 1):
        female = rng.random() < 0.5
        dob = datetime(rng.randint(1945, 2005), rng.randint(1, 12), rng.randint(1, 28))
        first, last = _first(rng), _last(rng)
        customers.append({
            "id": f"SYNC-{i:05d}", "name": f"{first} {last}", "number": f"SYN{rng.randint(1000000, 9999999)}",
            "hetu": _hetu(rng, dob, female, used_hetu), "street": _street(rng),
            "postcode": rng.choice(POSTCODES), "city": rng.choice(MUNICIPALITIES),
            "email": f"{first.lower()}.{last.lower()}@example.test", "phone": _phone(rng),
            "lang": rng.choice(LANGUAGES), "iban": _iban(rng, used_iban),
        })
    cust_rows = []
    for c in customers:
        since = datetime(2012, 1, 1) + timedelta(days=rng.randrange(4500))
        cust_rows.append([
            c["id"], c["number"], c["name"], c["hetu"], c["street"], c["postcode"], c["city"], c["email"],
            c["phone"], c["lang"], since.strftime("%Y-%m-%d"), rng.choice(PRODUCTS),
            f"SYN-CN-{rng.randint(100000, 999999)}", rng.choice(PAYMENT_METHODS), c["iban"],
            rng.choice(["true", "false"]), "1" if rng.random() < 0.06 else "0", rng.choice(ACCESSIBILITY),
        ])

    agents = [(f"SYNA-{i:03d}", f"{_first(rng)} {_last(rng)}") for i in range(1, 13)]
    splits = ["train"] * N_TRAIN + ["eval"] * N_EVAL
    # cycle intents so every class is present in both splits, then shuffle assignment order
    intents = [INTENT_CLASSES[i % len(INTENT_CLASSES)] for i in range(len(splits))]
    rng.shuffle(intents)

    conv_rows, turn_rows = [], []
    turn_n = 0
    for k, (split, intent) in enumerate(zip(splits, intents), start=1):
        cust = rng.choice(customers)
        agent_id, agent_name = rng.choice(agents)
        channel = rng.choice(CHANNELS)
        language = rng.choices(LANGUAGES, [6, 3, 1])[0]
        started = datetime(2025, 1, 1) + timedelta(days=rng.randrange(365), hours=rng.randint(7, 20), minutes=rng.randrange(60))
        openers, details, fixes = INTENT_TEXT[intent]
        contact = f"my name is {cust['name']} and my customer number is {cust['number']}"
        extras = [
            f"you can reach me at {cust['phone']}", f"my email is {cust['email']}",
            f"I live at {cust['street']}", f"my account number is {cust['iban']}",
        ]
        script = [
            ("agent", AGENT_OPEN[language]),
            ("customer", f"Hello, {rng.choice(openers)}"),
            ("agent", AGENT_ASK),
            ("customer", f"Yes, {contact}, {rng.choice(extras)}"),
            ("agent", AGENT_CHECK),
            ("customer", f"Well, {rng.choice(details)}"),
            ("agent", f"I understand, {rng.choice(fixes)}"),
            ("customer", CUSTOMER_THANKS),
            ("agent", AGENT_CLOSE[language]),
        ]
        if rng.random() < 0.3:  # shorter contacts exist too
            script = script[:2] + script[3:4] + script[5:]
        ts = started
        for seq, (speaker, text) in enumerate(script, start=1):
            turn_n += 1
            ts = ts + timedelta(seconds=rng.randint(15, 90))
            turn_rows.append([f"SYNT-{turn_n:07d}", f"SYNQ-{k:05d}", str(seq), speaker, ts.strftime(TS), text])
        handle = int(abs(rng.gauss(240 + 25 * INTENT_CLASSES.index(intent), 70))) + 60
        sentiment = rng.choices(SENTIMENTS, [3, 5, 4])[0]
        csat = "" if rng.random() < 0.58 else str({"negative": rng.randint(1, 3), "neutral": rng.randint(2, 4), "positive": rng.randint(4, 5)}[sentiment])
        resolved = "true" if rng.random() < (0.55 + 0.02 * (INTENT_CLASSES.index(intent) % 10)) else "false"
        conv_rows.append([
            f"SYNQ-{k:05d}", cust["id"], agent_id, agent_name, channel, language, started.strftime(TS), intent,
            sentiment, csat, resolved, str(handle), str(len(script)), split,
            f"Customer {cust['name']} contacted us about {intent.replace('_', ' ')}.",
        ])

    out = dest / "customer_service"
    _write(out / "customers.csv", CUSTOMER_COLUMNS, cust_rows)
    _write(out / "conversations.csv", CONVERSATION_COLUMNS, conv_rows)
    _write(out / "turns.csv", TURN_COLUMNS, turn_rows)


# --------------------------------------------------------------------------- entry points
def generate(dest) -> Path:
    """Write the synthetic mini-kit under ``dest`` (health/ and customer_service/). Idempotent."""
    dest = Path(dest)
    used_hetu: set[str] = set()  # one identity code per person across every table\n    _health(dest, random.Random(f"{SEED}:health"), used_hetu)
    _customer_service(dest, random.Random(f"{SEED}:customer_service"), used_hetu)
    return dest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="destination folder")
    args = parser.parse_args(argv)
    generate(args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
