"""Structured labels through the public seam. All values are synthetic or public test examples
(DVV example HETU 131052-308T, test card 4111 1111 1111 1111, example IBAN FI21 1234 5600 0007 85)."""

from __future__ import annotations

import pytest

from pets_release.redactor import StructuredPass, Turn, redact_conversation


def conv(*turns, cid="c1"):
    ts = []
    for i, t in enumerate(turns):
        speaker, text = t if isinstance(t, tuple) else ("customer", t)
        ts.append(Turn(turn_id=f"{cid}-t{i}", text=text, speaker=speaker, seq=str(i)))
    return redact_conversation(cid, ts, passes=[StructuredPass()])


def found(r):
    return [(s["record_id"].split("-")[-1], s["start"], s["end"], s["label"]) for s in r.spans]


def span_text(texts, s):
    return texts[s]


# ---- NATIONAL_ID -------------------------------------------------------------------------------
def test_hetu_literal():
    r = conv("hetu on 131052-308T kiitos")
    assert found(r) == [("t0", 8, 19, "NATIONAL_ID")]
    assert r.texts["c1-t0"] == "hetu on [NATIONAL_ID_1] kiitos"


def test_hetu_with_bad_checksum_is_not_emitted():
    assert found(conv("hetu on 131052-308U kiitos")) == []


def test_hetu_split_across_two_turns_gives_two_spans_with_exact_offsets():
    a = "henkilötunnus on 131052"
    b = "-308T"
    r = conv(a, ("agent", "joo"), b)
    assert found(r) == [("t0", 17, 23, "NATIONAL_ID"), ("t2", 0, 5, "NATIONAL_ID")]
    phs = {s["placeholder"] for s in r.spans}
    assert phs == {"[NATIONAL_ID_1]"}


def test_hetu_spoken_with_spoken_separator_and_letter_name():
    t = "se on yksi kolme, yksi nolla, viisi kaksi, viiva, kolme nolla kahdeksan, tee"
    r = conv(t)
    start = t.index("yksi kolme")
    assert found(r) == [("t0", start, len(t), "NATIONAL_ID")]


def test_split_value_does_not_join_across_non_continuation_turn():
    # same speaker says something else in between: flushed, the halves never form one phone number
    r = conv("numero on 040 123", "odota hetki etsin sitä nyt tästä laukusta", "4567")
    assert found(r) == []
    joined = conv("numero on 040 123", ("agent", "mm"), "4567")
    assert [x[3] for x in found(joined)] == ["PHONE", "PHONE"]


# ---- PAYMENT_CARD ------------------------------------------------------------------------------
def test_card_literal_luhn():
    r = conv("maksan 4111 1111 1111 1111 nyt")
    assert found(r) == [("t0", 7, 26, "PAYMENT_CARD")]


def test_spoken_card_passes_luhn_after_conversion():
    words = "neljä yksi yksi yksi, " + ", ".join(["yksi yksi yksi yksi"] * 3)
    t = f"no se on {words}"
    r = conv(t)
    assert found(r) == [("t0", t.index("neljä"), len(t), "PAYMENT_CARD")]


def test_spoken_16_digits_failing_luhn_without_cue_not_emitted():
    words = "neljä yksi yksi yksi, " + ", ".join(["yksi yksi yksi yksi"] * 2) + ", yksi yksi yksi kaksi"
    assert found(conv(f"no se on {words}")) == []


def test_four_digit_card_needs_card_cue():
    t = "maksan kortilla joka päättyy 4242"
    assert found(conv(t)) == [("t0", t.index("4242"), len(t), "PAYMENT_CARD")]
    assert found(conv("tilasin 4242 kappaletta")) == []


def test_card_expiry_is_not_a_card_number():
    assert found(conv("kortti on voimassa 09/27 asti")) == []


def test_hetu_tail_alone_needs_hetu_cue():
    r = conv(("agent", "kertoisitko henkilötunnuksesi loppuosan?"), "-308T")
    assert found(r) == [("t1", 0, 5, "NATIONAL_ID")]
    assert found(conv(("agent", "mikä on tuotekoodi?"), "-308T")) == []


def test_repeated_hetu_tail_gets_the_full_hetus_placeholder():
    r = conv("131052-308T", ("agent", "joo"), "-308T")
    assert found(r) == [("t0", 0, 11, "NATIONAL_ID"), ("t2", 0, 5, "NATIONAL_ID")]
    assert [s["placeholder"] for s in r.spans] == ["[NATIONAL_ID_1]", "[NATIONAL_ID_1]"]


def test_partial_hetu_over_turns_after_cue():
    r = conv(("agent", "saisinko henkilötunnuksesi?"), "yksi kolme", ("agent", "joo"), "-308T")
    assert found(r) == [("t1", 0, 10, "NATIONAL_ID"), ("t3", 0, 5, "NATIONAL_ID")]
    r2 = conv(("agent", "saisinko tilausnumeron?"), "yksi kolme", ("agent", "joo"), "-308T")
    assert found(r2) == []


def test_spoken_check_letter_names():
    t = "yksi kolme, yksi nolla, viisi kaksi, viiva, kolme nolla kahdeksan, tee"
    assert found(conv(t)) == [("t0", 0, len(t), "NATIONAL_ID")]


def test_typed_groups_split_by_comma_do_not_merge():
    # street number then postcode: never one account number
    assert found(conv("asiakasnumero kysymys: osoite Testikatu 12 B 14, 20100 Turku")) == []


def test_luhn_does_not_join_short_fragments_across_turns():
    # '4111 1111 1111 111' + '1' passes Luhn when joined; a 1-digit fragment is not a continuation
    r = conv("maksan 4111 1111 1111 111", ("agent", "mm"), "1 kpl")
    assert [x[3] for x in found(r)] == []


def test_hetu_ending_in_check_letter_e_is_not_mistaken_for_an_amount():
    # 120456032 = 31 * 3885678 + 14, and check table index 14 is 'E'
    t = "hetu 120456-032E"
    assert found(conv(t)) == [("t0", 5, 16, "NATIONAL_ID")]


def test_phone_glued_to_house_number_is_still_found():
    t = "Testitie 5 A 3 040 123 4567"
    assert found(conv(t)) == [("t0", t.index("040"), len(t), "PHONE")]


def test_account_cue_in_agents_question():
    r = conv(("agent", "Kan jag få ditt kundnummer eller födelsedatum?"), "Ja, det är nog 41234567")
    assert found(r) == [("t1", 15, 23, "ACCOUNT_NUMBER")]


# ---- denylists ---------------------------------------------------------------------------------
def test_prices_amounts_and_versions_not_emitted():
    texts = [
        "lasku oli 049,90 € ja liittymä 0401,50 euroa",
        "maksoin 1200 euroa ja 0451234 kr",
        "päivitin version 4.12.0.11 ja firmware v2.3.1",
        "reitittimen versio 8.8.4.4 on uusin",
        "laskun summa 0401234,50 euroa",
        "asiakasnumero kysymys: hinta 12345678 €",
    ]
    for t in texts:
        assert found(conv(t)) == [], t


def test_private_and_loopback_ips_not_emitted_public_ip_is():
    for ip in ("192.168.1.1", "10.0.0.1", "172.16.4.2", "127.0.0.1"):
        assert found(conv(f"reititin {ip} ei vastaa")) == [], ip
    t = "julkisen ip osoitteen 100.72.13.5 näen"
    assert found(conv(t)) == [("t0", t.index("100"), t.index(" näen"), "IP_ADDRESS")]


# ---- PHONE -------------------------------------------------------------------------------------
def test_phone_formats():
    for p in ("040 123 4567", "0401234567", "+358 40 123 4567", "+358401234567", "040-1234567"):
        t = f"numero on {p}."
        assert found(conv(t)) == [("t0", 10, 10 + len(p), "PHONE")], p


def test_phone_with_00_prefix_and_parentheses():
    for p in ("0035840 123 4567", "00358 40 123 4567", "(040) 123 4567", "+358 (0)40 123 4567"):
        t = f"numero on {p}."
        spans = found(conv(t))
        assert len(spans) == 1 and spans[0][3] == "PHONE", p
        assert t[spans[0][1]:spans[0][2]].replace("(", "").replace(")", "").endswith("4567"), p


def test_phone_00_prefix_shares_placeholder_with_national_form():
    r = conv("numero on 0035840 123 4567 ja +358 40 123 4567")
    phs = [s["placeholder"] for s in r.spans if s["label"] == "PHONE"]
    assert len(phs) == 2 and phs[0] == phs[1]


def test_spoken_phone_split_over_turns_with_agent_backchannel():
    a = "numero on nolla neljä nolla, yksi kaksi kolme"
    b = "neljä viisi kuusi seitsemän"
    r = conv(a, ("agent", "mm"), b)
    assert found(r) == [("t0", a.index("nolla"), len(a), "PHONE"), ("t2", 0, len(b), "PHONE")]
    assert {s["placeholder"] for s in r.spans} == {"[PHONE_1]"}


def test_same_phone_in_two_formats_gets_one_placeholder():
    r = conv("numero on 040 123 4567", "siis 0401234567", "ja toinen 050 765 4321")
    assert [s["placeholder"] for s in r.spans] == ["[PHONE_1]", "[PHONE_1]", "[PHONE_2]"]


def test_placeholders_do_not_link_across_conversations():
    a = conv("numero on 050 765 4321", "ja 040 123 4567", cid="a")
    b = conv("numero on 040 123 4567", cid="b")
    assert a.texts["a-t1"] == "ja [PHONE_2]"
    assert b.texts["b-t0"] == "numero on [PHONE_1]"


# ---- IBAN / ACCOUNT ----------------------------------------------------------------------------
def test_iban_literal_and_spoken_letters():
    t = "tilinumero on FI21 1234 5600 0007 85."
    assert found(conv(t)) == [("t0", 14, 36, "IBAN")]
    s = "tilille F I kaksi yksi, yksi kaksi kolme neljä, viisi kuusi nolla nolla, nolla nolla nolla seitsemän, kahdeksan viisi"
    assert found(conv(s)) == [("t0", s.index("F I"), len(s), "IBAN")]


def test_iban_bad_checksum_not_emitted():
    assert found(conv("tilinumero on FI21 1234 5600 0007 86.")) == []


def test_account_number_needs_cue():
    t = "asiakasnumeroni on 41234567"
    assert found(conv(t)) == [("t0", 19, 27, "ACCOUNT_NUMBER")]
    assert found(conv("sain 41234567 viestiä")) == []


# ---- EMAIL -------------------------------------------------------------------------------------
def test_email_literal_and_spelled_out():
    t = "osoite on maija.m@posti.example."
    assert found(conv(t)) == [("t0", 10, 31, "EMAIL")]
    s = "osoite on maija piste m at posti piste example kiitos"
    assert found(conv(s)) == [("t0", 10, s.index(" kiitos"), "EMAIL")]
    sv = "adressen är maja snabel-a posti punkt example"
    assert found(conv(sv)) == [("t0", 12, len(sv), "EMAIL")]


def test_spelled_and_literal_email_share_placeholder():
    r = conv("maija piste m at posti piste example", "eli maija.m@posti.example")
    assert [s["placeholder"] for s in r.spans] == ["[EMAIL_1]", "[EMAIL_1]"]


def test_at_in_ordinary_sentence_is_not_email():
    assert found(conv("call me at home tomorrow at noon")) == []


# ---- other structured labels -------------------------------------------------------------------
def test_imei_device_id():
    t = "imei on 490154203237518"
    assert found(conv(t)) == [("t0", 8, 23, "DEVICE_ID")]


def test_property_id_and_plate():
    t = "mökin kiinteistötunnus on 123-456-7-89"
    assert found(conv(t)) == [("t0", t.index("123"), len(t), "PROPERTY_ID")]
    p = "auto on xyz-123 pihalla"
    assert found(conv(p)) == [("t0", 8, 15, "LICENSE_PLATE")]


def test_url_with_token_emitted_public_url_not():
    t = "linkistä https://pay.example/lasku?id=123456 maksamaan"
    assert found(conv(t)) == [("t0", 9, t.index(" maksamaan"), "URL")]
    assert found(conv("katso https://www.example.org/ohjeet.")) == []


def test_secret_and_username_after_cue():
    t = "salasanani on Talvi2024! kiitos"
    assert found(conv(t)) == [("t0", 14, 24, "SECRET")]
    p = "pin on 1234"
    assert found(conv(p)) == [("t0", 7, 11, "SECRET")]
    u = "käyttäjätunnukseni on maijam85"
    assert found(conv(u)) == [("t0", 22, 30, "USERNAME")]


def test_secret_that_starts_like_a_cue_word():
    t = "wifin salasana on varmaan Salasana123"
    assert found(conv(t)) == [("t0", t.index("Salasana123"), len(t), "SECRET")]


def test_two_word_username_cue():
    t = "my user name is maijam85"
    assert found(conv(t)) == [("t0", 16, 24, "USERNAME")]


def test_hetu_followed_by_swedish_ar():
    t = "131052-308T är mitt personnummer"
    assert found(conv(t)) == [("t0", 0, 11, "NATIONAL_ID")]


def test_iban_after_swedish_ar():
    t = "Kontonumret är FI21 1234 5600 0007 85"
    assert found(conv(t)) == [("t0", 15, len(t), "IBAN")]
def test_validated_hetu_is_not_swallowed_by_a_cross_turn_phone():
    # a number ending one turn must not join a complete HETU that starts the next one
    # 010101010 % 31 == 1 -> check character '1'
    # tail '0' + '010101-0101' would read as an 11-digit 0-leading phone number
    r = conv("numero alkaa 0", ("agent", "mm"), "010101-0101 on hetu")
    assert [x[3] for x in found(r)] == ["NATIONAL_ID"]


# ---- review fixes (GPT-6.1 at 943801b) ---------------------------------------------------------
def test_alphabetic_secret_and_username_after_explicit_cue():
    t = "salasanani on Lumiukko"
    assert found(conv(t)) == [("t0", 14, 22, "SECRET")]
    p = "my password is sunflower."
    assert found(conv(p)) == [("t0", 15, 24, "SECRET")]
    u = "käyttäjätunnukseni on maijamaa"
    assert found(conv(u)) == [("t0", 22, 30, "USERNAME")]


def test_prose_after_secret_cue_is_not_a_secret():
    for t in ("salasana on vaihdettu", "salasanani on unohtunut", "my password is wrong",
              "the password is not working", "salasana on liian lyhyt", "lösenordet är fel",
              "salasana on ok"):
        assert found(conv(t)) == [], t


def test_ipv6_compressed_forms():
    t = "julkinen osoite 2a00:1450:4001:82a::200e näkyy"
    assert found(conv(t)) == [("t0", 16, t.index(" näkyy"), "IP_ADDRESS")]
    full = "ip 2a00:1450:4001:082a:0000:0000:0000:200e"
    assert found(conv(full)) == [("t0", 3, len(full), "IP_ADDRESS")]
    for ip in ("::1", "fe80::1", "fd12:3456:789a::1"):
        assert found(conv(f"osoite {ip} ei toimi")) == [], ip


def test_unrelated_other_speaker_turn_flushes_the_join():
    a = "numero on nolla neljä nolla, yksi kaksi kolme"
    b = "neljä viisi kuusi seitsemän"
    r = conv(a, ("agent", "Kerrotteko vielä mikä teidän osoitteenne on"), b)
    assert found(r) == []
    ok = conv(a, ("agent", "joo, jatkakaa"), b)
    assert [x[3] for x in found(ok)] == ["PHONE", "PHONE"]


# ---- review r2 fixes -------------------------------------------------------------------------
def test_split_phone_whose_first_part_already_looks_like_a_phone():
    # '040 1234' alone is a 7-digit 0-leading number; the whole value spans two turns
    a = "numero on 040 1234"
    r = conv(a, ("agent", "mm"), "567")
    assert found(r) == [("t0", 10, len(a), "PHONE"), ("t2", 0, 3, "PHONE")]
    assert {s["placeholder"] for s in r.spans} == {"[PHONE_1]"}


def test_split_iban_over_two_turns():
    a = "tilinumero on FI21 1234 5600"
    r = conv(a, ("agent", "joo"), "0007 85")
    assert found(r) == [("t0", 14, len(a), "IBAN"), ("t2", 0, 7, "IBAN")]
    assert {s["placeholder"] for s in r.spans} == {"[IBAN_1]"}


def test_spelled_email_across_two_turns():
    a = "osoite on maija piste m"
    b = "at posti piste example"
    r = conv(a, ("agent", "joo"), b)
    assert found(r) == [("t0", 10, len(a), "EMAIL"), ("t2", 0, len(b), "EMAIL")]
    assert {s["placeholder"] for s in r.spans} == {"[EMAIL_1]"}
    c = "maija piste m at posti"
    r2 = conv(c, ("agent", "mm"), "piste example")
    assert found(r2) == [("t0", 0, len(c), "EMAIL"), ("t2", 0, 13, "EMAIL")]


def test_spelled_email_does_not_join_across_unrelated_turn():
    r = conv("osoite on maija piste m", ("agent", "mikä on teidän postinumeronne"), "at posti piste example")
    assert [x[0] for x in found(r)] == []


def test_credential_after_intervening_words():
    t = "wifin salasana taitaa olla Kissa2024"
    assert found(conv(t)) == [("t0", t.index("Kissa2024"), len(t), "SECRET")]
    u = "the username for the portal is maijam85"
    assert found(conv(u)) == [("t0", u.index("maijam85"), len(u), "USERNAME")]


def test_general_credential_cue_words():
    for cue in ("verkkoavain", "wlan-avain", "lösen", "tunnussana", "passcode", "access key"):
        t = f"{cue} on Xr7kq2Lm"
        assert found(conv(t)) == [("t0", t.index("Xr7kq2Lm"), len(t), "SECRET")], cue


def test_prefixed_api_keys_and_tokens_without_cue():
    for key in ("sk-live-4eC39HqLyjWDarjtT1zdp7dc", "ghp_" + "a1B2c3D4e5F6g7H8i9J0k1L2m3N4o5P6q7R8",
                "AKIAIOSFODNN7EXAMPLE", "xoxb-1234567890-abcdefghijkl"):
        t = f"tässä {key} kiitos"
        assert found(conv(t)) == [("t0", 6, 6 + len(key), "SECRET")], key


def test_long_hex_after_cue_is_secret():
    t = "api key: 9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08"
    assert found(conv(t)) == [("t0", 9, len(t), "SECRET")]


def test_intervening_words_do_not_reach_prose_or_plain_numbers():
    for t in ("salasana vaihdettiin eilen ja tunnus toimii nyt hyvin",
              "salasana vaihdettiin vuonna 2024",
              "the password was last changed in 2023",
              "pin-koodi lähetetään kirjeellä osoitteeseen Testitie 5"):
        assert [x[3] for x in found(conv(t))] == [], t


def test_validated_identifier_after_a_credential_cue_keeps_its_label():
    t = "tunnus avain on 131052-308T"
    assert found(conv(t)) == [("t0", t.index("131052"), len(t), "NATIONAL_ID")]


# ---- review r3: spelled e-mail over the whole N-turn window -----------------------------------
_EMAIL_SPLITS_2 = {
    "local": ["maija piste", "m at posti piste example"],
    "before-at": ["maija piste m", "at posti piste example"],
    "after-at": ["maija piste m at", "posti piste example"],
    "domain": ["maija piste m at posti", "piste example"],
    "tld": ["maija piste m at posti piste", "example"],
}
_EMAIL_SPLITS_3 = {
    "local+domain": ["maija piste", "m at posti", "piste example"],
    "local+at": ["maija", "piste m", "at posti piste example"],
    "at+tld": ["maija piste m", "at posti piste", "example"],
    "after-at+tld": ["maija piste m at", "posti piste", "example"],
    "domain+tld": ["maija piste m at posti", "piste", "example"],
}


@pytest.mark.parametrize("parts", list(_EMAIL_SPLITS_2.values()), ids=list(_EMAIL_SPLITS_2))
def test_spelled_email_split_over_two_turns_with_backchannel(parts):
    r = conv(parts[0], ("agent", "joo"), parts[1])
    assert found(r) == [("t0", 0, len(parts[0]), "EMAIL"), ("t2", 0, len(parts[1]), "EMAIL")]
    assert {s["placeholder"] for s in r.spans} == {"[EMAIL_1]"}


@pytest.mark.parametrize("parts", list(_EMAIL_SPLITS_3.values()), ids=list(_EMAIL_SPLITS_3))
def test_spelled_email_split_over_three_turns(parts):
    r = conv(*parts)
    assert found(r) == [(f"t{k}", 0, len(p), "EMAIL") for k, p in enumerate(parts)]
    assert {s["placeholder"] for s in r.spans} == {"[EMAIL_1]"}


def test_spelled_email_split_beyond_window_is_not_joined():
    # four same-speaker turns exceed the 3-turn window: never one 4-way span set
    r = conv("maija", "piste m", "at posti", "piste example")
    assert "t0" not in [x[0] for x in found(r)]


def test_sentence_final_dot_does_not_extend_an_address_into_the_next_turn():
    a = "osoite on maija piste m at posti piste example."
    r = conv(a, "Kiitos paljon")
    assert found(r) == [("t0", 10, len(a) - 1, "EMAIL")]


# ---- must-fix #54: a phone number on its own line is not glued to the house number above ----------
@pytest.mark.parametrize("phone", ["0401234567", "040 123 4567", "+358 40 123 4567"])
@pytest.mark.parametrize("house", ["Testikatu 12 B 4", "Testikatu 12", "Testgatan 7 A 3"])
def test_phone_on_own_line_is_not_glued_to_house_number_when_account_cue_is_near(phone, house):
    text = f"Kiitos tilinumero.\n\nTerveisin,\nMatti\n{house}\n{phone}"
    r = conv(text)
    labels = [(text[s["start"]:s["end"]], s["label"]) for s in r.spans]
    assert (phone, "PHONE") in labels
    assert all(lab != "ACCOUNT_NUMBER" for _, lab in labels)
