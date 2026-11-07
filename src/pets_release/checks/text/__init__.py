"""Gate text checks (release scope), registered with the shared checks registry.

One check per validated identifier label, run over every declared text field (contract form
``text`` with ``params.conversation`` and ``params.order``) using this package's own
conversation-level normaliser and N-turn stitching; plus ``text.health`` against the
versioned gate health lexicon. Imports nothing from the detector, redactor, pseudonymiser or
transforms. Helper modules are private (``_*.py``) so registry discovery skips them; every
registration lives here.

``text.health`` reads ``contract["healthInTextRequired"]``: ``true`` makes lexicon hits high
severity (refuse); ``false`` or absent keeps them low severity (counted residual risk, so the
``healthInText`` assertion may only be emitted when the contract sets it ``true``); any other
value is an error. If ``context["manifest"]`` (or the release's manifest in verify) binds a digest for
``gate-health`` in ``bindings.lexiconDigests``, it must equal this lexicon's digest.

Violation ``count`` = number of identifiers found (a split identifier counts once; its
``locations`` list every turn row it touches).
"""
from __future__ import annotations

from pets_release.checks.records import Outcome, Violation, locations
from pets_release.checks.registry import register

from . import _detectors, _lexicon, _scan

SCOPE = "release"
VERSION = "1.0.0"
UNIT = "turns"
HEALTH_CHECK = "text.health"
HEALTH_REQUIRED_KEY = "healthInTextRequired"
LEXICON_NAME = _lexicon.LEXICON_NAME
LEXICON_VERSION = _lexicon.LEXICON_VERSION
LEXICON_PATH = _lexicon.LEXICON_PATH
lexicon_digest = _lexicon.digest

# check name -> (export assertion, label, detector, view)
TEXT_CHECKS = {
    "text.national-ids": ("nationalIds", "NATIONAL_ID", _detectors.national_ids, "digit"),
    "text.payment-cards": ("paymentCards", "PAYMENT_CARD", _detectors.payment_cards, "digit"),
    "text.ibans": ("ibans", "IBAN", _detectors.ibans, "digit"),
    "text.account-numbers": ("accountNumbers", "ACCOUNT_NUMBER", _detectors.account_numbers, "digit"),
    "text.emails": ("emails", "EMAIL", _detectors.emails, "email"),
    "text.phones": ("phones", "PHONE", _detectors.phones, "digit"),
    "text.ip-addresses": ("ipAddresses", "IP_ADDRESS", _detectors.ip_addresses, "digit"),
    "text.device-ids": ("deviceIds", "DEVICE_ID", _detectors.device_ids, "digit"),
    "text.usernames": ("usernames", "USERNAME", _detectors.usernames, "digit"),
    "text.property-ids": ("propertyIds", "PROPERTY_ID", _detectors.property_ids, "digit"),
    "text.plates": ("plates", "LICENSE_PLATE", _detectors.plates, "digit"),
    "text.secrets": ("secrets", "SECRET", _detectors.secrets, "digit"),
    "text.urls-with-tokens": ("urlsWithTokens", "URL", _detectors.urls_with_tokens, "digit"),
}
# check name -> low-severity detector (counted as residual risk, never refused)
LOW_SEVERITY = {"text.ip-addresses": ("IP_ADDRESS", _detectors.private_ip_addresses, "digit")}
# export assertion -> text check name (healthInText included)
ASSERTION_CHECKS = {a: name for name, (a, _l, _d, _v) in TEXT_CHECKS.items()}
ASSERTION_CHECKS["healthInText"] = HEALTH_CHECK


def _violations(name, label, severity, per_field):
    out = []
    for field, hits in per_field:
        if hits:
            out.append(Violation(
                check=name, label=label, severity=severity, file=field.file, column=field.column,
                count=len(hits), locations=locations(r for h in hits for r in h)))
    return tuple(out)


def _make(name, label, detector, view):
    def run(release, contract, context):
        fields = _scan.load(release, contract)
        per_field = [(f, _scan.detect(f, detector, view)) for f in fields]
        viol = _violations(name, label, "high", per_field)
        if name in LOW_SEVERITY:
            low_label, low_det, low_view = LOW_SEVERITY[name]
            low = [(f, _scan.detect(f, low_det, low_view)) for f in fields]
            viol += _violations(name, low_label, "low", low)
        return Outcome(n=sum(f.n_turns for f in fields), violations=viol)

    run.__name__ = "check_" + name.replace(".", "_").replace("-", "_")
    register(name=name, version=VERSION, scope=SCOPE, unit=UNIT)(run)
    return run


for _name, (_assertion, _label, _det, _view) in sorted(TEXT_CHECKS.items()):
    _make(_name, _label, _det, _view)


def _bound_digest(release, context):
    manifest = context.get("manifest") if isinstance(context, dict) else None
    if manifest is None and hasattr(release, "manifest"):
        manifest = release.manifest()
    if not isinstance(manifest, dict):
        return None
    return ((manifest.get("bindings") or {}).get("lexiconDigests") or {}).get(LEXICON_NAME)


@register(name=HEALTH_CHECK, version=VERSION, scope=SCOPE, unit=UNIT)
def check_text_health(release, contract, context):
    required = contract.get(HEALTH_REQUIRED_KEY, False) if isinstance(contract, dict) else None
    if not isinstance(required, bool):
        raise _scan.TextCheckError("contract does not state whether health in text is forbidden")
    bound = _bound_digest(release, context)
    if bound is not None and bound != _lexicon.digest():
        raise _scan.TextCheckError("health lexicon digest differs from the one bound in the manifest")
    fields = _scan.load(release, contract)
    per_field = []
    for f in fields:
        hits = []
        for conv in f.conversations:
            for t, text in enumerate(conv.raw):
                hits.extend((conv.rows[t],) for _ in _lexicon.health_terms(text))
        per_field.append((f, hits))
    severity = "high" if required else "low"
    return Outcome(n=sum(f.n_turns for f in fields),
                   violations=_violations(HEALTH_CHECK, "HEALTH", severity, per_field))
