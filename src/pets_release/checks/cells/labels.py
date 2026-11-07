"""Per-label identifier rescans over every cell, plus 64-hex and raw-timestamp scans.

One check per export assertion so each assertion binds to its own named check.
"""
from __future__ import annotations

from pets_release.checks.cells import validators as v
from pets_release.checks.cells.common import scan_cells
from pets_release.checks.records import Outcome
from pets_release.checks.registry import register

# check name (= export assertion name) -> (violation label, finder)
LABEL_CHECKS = {
    "nationalIds": ("NATIONAL_ID", v.national_ids),
    "paymentCards": ("PAYMENT_CARD", v.payment_cards),
    "ibans": ("IBAN", v.ibans),
    "accountNumbers": ("ACCOUNT_NUMBER", v.account_numbers),
    "emails": ("EMAIL", v.emails),
    "phones": ("PHONE", v.phones),
    "ipAddresses": ("IP_ADDRESS", v.ip_addresses),
    "deviceIds": ("DEVICE_ID", v.device_ids),
    "usernames": ("USERNAME", v.usernames),
    "propertyIds": ("PROPERTY_ID", v.property_ids),
    "plates": ("LICENSE_PLATE", v.plates),
    "secrets": ("SECRET", v.secrets),
    "urlsWithTokens": ("URL", v.urls_with_tokens),
    "rawTimestamps": ("RAW_TIMESTAMP", v.raw_timestamps),
    "tokenHex64": ("HEX64_OUTSIDE_TOKEN", v.hex64),
}


def _make(name, label, finder):
    def run(release, contract, context):
        n, viol = scan_cells(release, contract, name, label, finder)
        return Outcome(n=n, violations=viol)

    run.__name__ = f"check_{name}"
    register(name=name, version="1", scope="release", unit="cells")(run)
    return run


for _name, (_label, _finder) in sorted(LABEL_CHECKS.items()):
    _make(_name, _label, _finder)
