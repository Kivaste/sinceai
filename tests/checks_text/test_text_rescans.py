"""Per-label text rescans: split and spoken identifiers are refused; placeholders are not hits.

Identifiers are textbook test values (DVV example HETU, Visa test card, IBAN example),
never kit rows.
"""
import pytest

CUSTOMER = "customer"
AGENT = "agent"




def test_hetu_split_across_two_turns_is_refused(gate, release, contract):
    folder = release([[
        (AGENT, "Could I have your personal identity code please?"),
        (CUSTOMER, "Sure, it is 131052"),
        (CUSTOMER, "-308T"),
    ]])
    rec = gate("text.national-ids", folder, contract())
    assert rec["status"] == "fail"
    assert rec["hits"] == 1
    assert rec["denominator"] == {"unit": "turns", "n": 3}
    (v,) = rec["violations"]
    assert v["severity"] == "high"
    assert v["label"] == "NATIONAL_ID"
    assert v["file"] == "turns.csv" and v["column"] == "text"
    assert v["locations"] == [1, 2]


def test_hetu_split_around_a_backchannel_turn_is_refused(gate, release, contract):
    folder = release([[
        (CUSTOMER, "my code is 131052"),
        (AGENT, "ok"),
        (CUSTOMER, "-308T"),
    ]])
    rec = gate("text.national-ids", folder, contract())
    assert rec["status"] == "fail" and rec["hits"] == 1
    assert rec["violations"][0]["locations"] == [0, 2]


def test_fragments_more_than_three_turns_apart_are_not_joined(gate, release, contract):
    folder = release([[
        (CUSTOMER, "my code is 131052"),
        (AGENT, "ok"),
        (CUSTOMER, "hmm"),
        (AGENT, "go on"),
        (CUSTOMER, "-308T"),
    ]])
    rec = gate("text.national-ids", folder, contract())
    assert rec["status"] == "pass" and rec["hits"] == 0


def test_fragments_in_different_conversations_are_not_joined(gate, release, contract):
    folder = release([
        [(CUSTOMER, "my code is 131052")],
        [(CUSTOMER, "-308T")],
    ])
    rec = gate("text.national-ids", folder, contract())
    assert rec["status"] == "pass" and rec["hits"] == 0


def test_hetu_with_wrong_check_character_is_not_a_hit(gate, release, contract):
    folder = release([[(CUSTOMER, "it is 131052-308U")]])
    rec = gate("text.national-ids", folder, contract())
    assert rec["status"] == "pass" and rec["hits"] == 0


def test_spoken_hetu_in_finnish_is_refused(gate, release, contract):
    folder = release([[(CUSTOMER, "yksi kolme yksi nolla viisi kaksi viiva kolme nolla kahdeksan T")]])
    rec = gate("text.national-ids", folder, contract())
    assert rec["status"] == "fail" and rec["hits"] == 1


def test_spoken_phone_number_is_refused(gate, release, contract):
    folder = release([[
        (CUSTOMER, "numeroni on nolla neljä nolla yksi kaksi kolme neljä viisi kuusi seitsemän"),
    ]])
    rec = gate("text.phones", folder, contract())
    assert rec["status"] == "fail" and rec["hits"] == 1
    assert rec["violations"][0]["label"] == "PHONE"


def test_phone_split_across_turns_is_refused(gate, release, contract):
    folder = release([[
        (CUSTOMER, "you can call me on plus 358 40"),
        (CUSTOMER, "123 4567"),
    ]])
    rec = gate("text.phones", folder, contract())
    assert rec["status"] == "fail" and rec["hits"] == 1
    assert rec["violations"][0]["locations"] == [0, 1]


def test_spelled_out_email_is_refused(gate, release, contract):
    folder = release([[
        (CUSTOMER, "it's matti dot meikalainen at example dot com"),
    ]])
    rec = gate("text.emails", folder, contract())
    assert rec["status"] == "fail" and rec["hits"] == 1
    assert rec["violations"][0]["label"] == "EMAIL"


def test_spelled_out_email_in_swedish_split_across_turns_is_refused(gate, release, contract):
    folder = release([[
        (CUSTOMER, "min adress är anna punkt svensson snabel-a"),
        (CUSTOMER, "example punkt se"),
    ]])
    rec = gate("text.emails", folder, contract())
    assert rec["status"] == "fail" and rec["hits"] == 1


def test_ordinary_at_and_full_stop_are_not_an_email(gate, release, contract):
    folder = release([[(CUSTOMER, "I am at home. Thanks for calling at noon.")]])
    rec = gate("text.emails", folder, contract())
    assert rec["status"] == "pass" and rec["hits"] == 0


def test_spoken_card_number_is_refused(gate, release, contract):
    spoken = " ".join(["four"] + ["one"] * 15)
    folder = release([[(CUSTOMER, f"the card is {spoken}")]])
    rec = gate("text.payment-cards", folder, contract())
    assert rec["status"] == "fail" and rec["hits"] == 1
    assert rec["violations"][0]["label"] == "PAYMENT_CARD"


def test_card_split_across_turns_is_refused(gate, release, contract):
    folder = release([[
        (CUSTOMER, "card number 4111 1111"),
        (AGENT, "yes"),
        (CUSTOMER, "1111 1111"),
    ]])
    rec = gate("text.payment-cards", folder, contract())
    assert rec["status"] == "fail" and rec["hits"] == 1


def test_iban_with_spaces_is_refused(gate, release, contract):
    folder = release([[(CUSTOMER, "my account is FI21 1234 5600 0007 85 thanks")]])
    rec = gate("text.ibans", folder, contract())
    assert rec["status"] == "fail" and rec["hits"] == 1


@pytest.mark.parametrize("name", [
    "text.national-ids", "text.phones", "text.emails", "text.payment-cards", "text.ibans",
    "text.account-numbers", "text.ip-addresses", "text.device-ids", "text.usernames",
    "text.property-ids", "text.plates", "text.secrets", "text.urls-with-tokens",
])
def test_placeholders_are_not_hits(gate, release, contract, name):
    folder = release([[
        (CUSTOMER, "my code is [NATIONAL_ID_1] and phone [PHONE_1]"),
        (CUSTOMER, "email [EMAIL_1], card [PAYMENT_CARD_1] [PAYMENT_CARD_2]"),
        (CUSTOMER, "iban [IBAN_1] account number [ACCOUNT_NUMBER_1] ip [IP_ADDRESS_1]"),
        (CUSTOMER, "username [USERNAME_1] password [SECRET_1] plate [LICENSE_PLATE_1]"),
        (CUSTOMER, "see [URL_1] device [DEVICE_ID_1] property [PROPERTY_ID_1]"),
    ]])
    rec = gate(name, folder, contract())
    assert rec["status"] == "pass", rec["violations"]
    assert rec["hits"] == 0
    assert rec["denominator"] == {"unit": "turns", "n": 5}


def test_placeholders_do_not_bridge_fragments(gate, release, contract):
    folder = release([[(CUSTOMER, "4111 1111 [PHONE_1] 1111 1111")]])
    rec = gate("text.payment-cards", folder, contract())
    assert rec["status"] == "pass" and rec["hits"] == 0


@pytest.mark.parametrize("name,text", [
    ("text.ip-addresses", "my router shows 8.8.4.4 as the server"),
    ("text.device-ids", "the MAC is 00:1A:2B:3C:4D:5E"),
    ("text.plates", "the car is ABC-123"),
    ("text.secrets", "my password is Kissa123!"),
    ("text.urls-with-tokens", "open https://example.com/reset?token=abc123def456"),
    ("text.usernames", "my username is matti_m84"),
    ("text.account-numbers", "my customer number is 12345678"),
    ("text.property-ids", "kiinteistötunnus 091-012-0034-0005"),
])
def test_each_label_refuses_a_planted_value(gate, release, contract, name, text):
    folder = release([[(CUSTOMER, text)]])
    rec = gate(name, folder, contract())
    assert rec["status"] == "fail" and rec["hits"] == 1


@pytest.mark.parametrize("name,text", [
    # documentation-range addresses are identifiers in text too
    ("text.ip-addresses", "the server is 192.0.2.10 today"),
    ("text.ip-addresses", "ping 2001:db8::1 please"),
    # a 15-digit Luhn number that is not an Amex card is an IMEI
    ("text.device-ids", "the phone shows 352099001761481"),
])
def test_identifier_is_refused(gate, release, contract, name, text):
    folder = release([[(CUSTOMER, text)]])
    rec = gate(name, folder, contract())
    assert rec["status"] == "fail" and rec["hits"] == 1


@pytest.mark.parametrize("name,text", [
    ("text.payment-cards", "the phone shows 352099001761481"),
    ("text.phones", "my code is 010101-123N"),
    ("text.phones", "my code is 020202-0180"),
    ("text.account-numbers", "account number FI21 1234 5600 0007 85"),
    ("text.secrets", "open https://example.com/reset?token=abc123def456"),
])
def test_value_of_another_label_is_not_a_hit(gate, release, contract, name, text):
    folder = release([[(CUSTOMER, text)]])
    rec = gate(name, folder, contract())
    assert rec["status"] == "pass" and rec["hits"] == 0, name


def test_records_carry_no_values(registry, gate, release, contract):
    folder = release([[(CUSTOMER, "it is 131052-308T and 4111 1111 1111 1111")]])
    statuses = set()
    for name in registry:
        rec = gate(name, folder, contract())
        statuses.add(rec["status"])
        blob = repr(rec)
        assert "131052" not in blob and "4111" not in blob and "308T" not in blob
    assert "fail" in statuses


def test_record_has_exact_checkrecord_keys(gate, release, contract):
    folder = release([[(CUSTOMER, "it is 131052-308T")]])
    rec = gate("text.national-ids", folder, contract())
    assert set(rec) == {"check", "version", "scope", "status", "denominator", "hits", "violations"}
    assert rec["scope"] == "release"
    assert set(rec["violations"][0]) == {
        "check", "label", "severity", "file", "column", "count", "locations"}


def test_missing_text_file_is_an_error(registry, gate, tmp_path, contract):
    (tmp_path / "release").mkdir()
    (tmp_path / "release" / "other.csv").write_text("a\n1\n", encoding="utf-8")
    assert len(registry) == 14
    for name in registry:
        rec = gate(name, tmp_path / "release", contract())
        assert rec["status"] == "error", name


def test_all_text_checks_are_registered_release_scope_turns(registry):
    assert sorted(registry) == sorted([
        "text.national-ids", "text.payment-cards", "text.ibans", "text.account-numbers",
        "text.emails", "text.phones", "text.ip-addresses", "text.device-ids", "text.usernames",
        "text.property-ids", "text.plates", "text.secrets", "text.urls-with-tokens", "text.health",
    ])
    for c in registry.values():
        assert (c.version, c.scope, c.unit) == ("1.0.0", "release", "turns")


def test_text_column_with_only_one_stitching_param_is_an_error(gate, release, contract):
    folder = release([[(CUSTOMER, "hello")]])
    c = contract()
    c["files"]["turns.csv"]["columns"]["text"]["params"] = {"conversation": "conversation_id"}
    rec = gate("text.phones", folder, c)
    assert rec["status"] == "error"


def test_text_column_without_stitching_params_scans_each_row_alone(gate, release, contract):
    folder = release([[(CUSTOMER, "my code is 131052"), (CUSTOMER, "-308T"),
                       (CUSTOMER, "and 131052-308T")]])
    c = contract()
    c["files"]["turns.csv"]["columns"]["text"]["params"] = {"nullable": True}
    rec = gate("text.national-ids", folder, c)
    assert rec["status"] == "fail" and rec["hits"] == 1
    assert rec["violations"][0]["locations"] == [2]


def test_private_ip_in_text_is_low_severity(gate, release, contract):
    folder = release([[(CUSTOMER, "my router is 192.168.1.1")]])
    rec = gate("text.ip-addresses", folder, contract())
    assert rec["status"] == "pass" and rec["hits"] == 1
    assert [v["severity"] for v in rec["violations"]] == ["low"]


def test_undeclared_free_text_column_is_an_error(gate, release, contract):
    folder = release([[(CUSTOMER, "my number is 040 123 4567 call me any time today")]])
    c = contract()
    c["files"]["turns.csv"]["columns"]["text"] = {"form": ".*", "params": {}}
    rec = gate("text.phones", folder, c)
    assert rec["status"] == "error"
