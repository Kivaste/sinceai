"""#114, verify path: ``pets-release verify`` loads the manifest strictly (seam: the real verify CLI).

Row (trigger -> result): a duplicate top-level key whose first value carries a card, the last (signed) value
being the real one -> limited verify exit 1 with ``manifest: $: not-json``; the card is never echoed.
Synthetic fixture rows only; the card is the published test number.
"""
from __future__ import annotations

CARD = "4111111111111111"


def test_verify_cli_refuses_a_duplicate_key_manifest(bed, tb, verify_cli):
    raw = (bed / tb.MANIFEST).read_bytes()
    assert raw.startswith(b"{")
    ok = verify_cli(bed, env={"PETS_HMAC_KEY": tb.KEY})
    assert ok.returncode == 0, ok.stdout  # control: the unplanted bed verifies
    # under plain json.loads the last value wins, i.e. exactly the signed manifest
    (bed / tb.MANIFEST).write_bytes(b'{"release":{"note":"call back card ' + CARD.encode() + b'"},' + raw[1:])
    r = verify_cli(bed, env={"PETS_HMAC_KEY": tb.KEY})
    assert r.returncode == 1, r.stdout
    assert "manifest: $: not-json" in r.stdout, r.stdout
    assert CARD not in r.stdout + r.stderr
