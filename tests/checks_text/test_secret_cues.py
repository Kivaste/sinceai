"""Guard for the secret-cue defect class (third sighting, review r3 of ticket 05).

Every secret-type cue (general-knowledge fi/sv/en) must catch its value whether written
contiguously, space-separated, as spoken digits, or in the turn after the cue. Values are
synthetic.
"""
import pytest

C = "customer"

CVV_CUES = ["CVV", "CVC", "CVV2", "card verification code", "turvakoodi", "säkerhetskod", "security code"]
PIN_CUES = ["PIN", "PIN code", "PIN-koodi", "PIN-kod", "pinkod", "tunnusluku"]
OTP_CUES = [
    "OTP", "one-time code", "one time password", "verification code", "confirmation code",
    "authentication code", "SMS code", "login code", "access code", "vahvistuskoodi",
    "varmennuskoodi", "kertakäyttökoodi", "kertakäyttösalasana", "tekstiviestikoodi",
    "engångskod", "engångslösenord", "verifieringskod", "bekräftelsekod",
]
PASSWORD_CUES = ["password", "passcode", "passphrase", "salasana", "tunnussana", "lösenord",
                 "API key", "api-avain", "token"]

VALUES = {
    # kind: (contiguous, spaced, spoken)
    "cvv": ("482", "4 8 2", "four eight two"),
    "pin": ("4821", "4 8 2 1", "neljä kahdeksan kaksi yksi"),
    "otp": ("482913", "482 913", "fyra åtta två nio ett tre"),
    "password": ("Kissa123", "k 4 x 9 q", "kissa one two three"),
}
FORMS = ["contiguous", "spaced", "spoken", "next-turn"]

CASES = [(cue, kind, form)
         for kind, cues in (("cvv", CVV_CUES), ("pin", PIN_CUES), ("otp", OTP_CUES), ("password", PASSWORD_CUES))
         for cue in cues for form in FORMS]


def _turns(cue, kind, form):
    contiguous, spaced, spoken = VALUES[kind]
    if form == "next-turn":
        return [f"my {cue} is", spaced]
    value = {"contiguous": contiguous, "spaced": spaced, "spoken": spoken}[form]
    return [f"my {cue} is {value} thanks"]


@pytest.mark.parametrize("cue,kind,form", CASES)
def test_every_secret_cue_catches_its_value_in_every_form(gate, release, contract, cue, kind, form):
    turns = _turns(cue, kind, form)
    folder = release([[(C, t) for t in turns]])
    rec = gate("text.secrets", folder, contract())
    assert rec["status"] == "fail" and rec["hits"] == 1, (cue, form)
    assert rec["violations"][0]["locations"] == list(range(len(turns)))


@pytest.mark.parametrize("text", [
    "my password is wrong", "the PIN is 12", "the CVV is 12345", "verification code was sent",
    "my one-time code is 12", "the token expired yesterday",
])
def test_secret_cue_without_a_valid_value_is_not_a_hit(gate, release, contract, text):
    folder = release([[(C, text)]])
    rec = gate("text.secrets", folder, contract())
    assert rec["status"] == "pass" and rec["hits"] == 0, text
