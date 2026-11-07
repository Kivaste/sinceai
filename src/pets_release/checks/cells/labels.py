"""Per-label identifier rescans over every cell, plus 64-hex and raw-timestamp scans.

One check per export assertion so each assertion binds to its own named check.
"""
from __future__ import annotations

from pets_release.checks.cells import _validators as v
from pets_release.checks.cells._common import scan_cells
from pets_release.checks.records import Outcome
from pets_release.checks.registry import register

# check name (= export assertion name) -> (violation label, finder)
LABEL_CHECKS = {
    "rescan.national-ids": ("NATIONAL_ID", v.national_ids),
    "rescan.payment-cards": ("PAYMENT_CARD", v.payment_cards),
    "rescan.ibans": ("IBAN", v.ibans),
    "rescan.account-numbers": ("ACCOUNT_NUMBER", v.account_numbers),
    "rescan.emails": ("EMAIL", v.emails),
    "rescan.phones": ("PHONE", v.phones),
    "rescan.ip-addresses": ("IP_ADDRESS", v.ip_addresses),
    "rescan.device-ids": ("DEVICE_ID", v.device_ids),
    "rescan.usernames": ("USERNAME", v.usernames),
    "rescan.property-ids": ("PROPERTY_ID", v.property_ids),
    "rescan.plates": ("LICENSE_PLATE", v.plates),
    "rescan.secrets": ("SECRET", v.secrets),
    "rescan.urls-with-tokens": ("URL", v.urls_with_tokens),
    "rescan.raw-timestamps": ("RAW_TIMESTAMP", v.raw_timestamps),
    "release.token-hex64": ("HEX64_OUTSIDE_TOKEN", v.hex64),
}


def _make(name, label, finder):
    def run(release, contract, context):
        n, viol = scan_cells(release, contract, name, label, finder)
        return Outcome(n=n, violations=viol)

    run.__name__ = "check_" + name.replace(".", "_").replace("-", "_")
    register(name=name, version="1.0.0", scope="release", unit="cells")(run)
    return run


for _name, (_label, _finder) in sorted(LABEL_CHECKS.items()):
    _make(_name, _label, _finder)
