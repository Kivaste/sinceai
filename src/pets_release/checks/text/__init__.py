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
value is an error. In the verify phase (default) the manifest must bind
``bindings.lexiconDigests["gate-health"]`` to this lexicon's digest; missing or different is
an error. In the gate phase a manifest, if present, must do the same.

Violation ``count`` = number of identifiers found (a split identifier counts once; its
``locations`` list every turn row it touches).

Residual-risk gaps (not detected; listed so they are not mistaken for coverage):
* Swedish personnummer (10/12 digits, Luhn) - collides with phone-number shapes;
* spoken numbers above nine and multipliers ("kaksikymmentä", "tjugo", "twenty",
  "double five", "tupla") - only single spoken digits are converted;
* letters spoken by name ("äf ii", "ef i") - letter-by-letter IBANs and spelled emails
  are caught only when the letters themselves are written;
* identifiers split across more than three turns, or across a middle turn that holds digits
  in the skip-middle window.
"""
from __future__ import annotations

from pets_release.checks.records import Outcome, Violation, locations
from pets_release.checks.registry import register

from . import _detectors, _lexicon, _normalise, _scan

SCOPE = "release"
VERSION = "1.0.0"
UNIT = "turns"
# A contract with no ``text``-form column makes every text check not_applicable (runner-verified).
APPLIES_TO = (_scan.TEXT_FORM,)
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
# The assertion -> check map is owned by the registry (``pets_release.checks.ASSERTION_CHECKS``);
# the assertion names above only say which assertion each text check also backs.


def _violations(name, label, severity, per_field):
    out = []
    for field, hits in per_field:
        if hits:
            out.append(Violation(
                check=name, label=label, severity=severity, file=field.file, column=field.column,
                count=len(hits), locations=locations(r for h in hits for r in h)))
    return tuple(out)


def _not_applicable(release, contract):
    """True when the contract declares no text-form column. The undeclared-free-text guard still
    runs first (via `_scan.load`), so free text hidden under another form is an error."""
    if _scan.text_fields(contract):
        return False
    _scan.load(release, contract)
    return True


def _make(name, label, detector, view):
    def run(release, contract, context):
        if _not_applicable(release, contract):
            return Outcome.not_applicable()
        fields = _scan.load(release, contract)
        per_field = [(f, _scan.detect(f, detector, view)) for f in fields]
        viol = _violations(name, label, "high", per_field)
        if name in LOW_SEVERITY:
            low_label, low_det, low_view = LOW_SEVERITY[name]
            low = [(f, _scan.detect(f, low_det, low_view)) for f in fields]
            viol += _violations(name, low_label, "low", low)
        return Outcome(n=sum(f.n_turns for f in fields), violations=viol)

    run.__name__ = "check_" + name.replace(".", "_").replace("-", "_")
    register(name=name, version=VERSION, scope=SCOPE, unit=UNIT, applies_to=APPLIES_TO)(run)
    return run


for _name, (_assertion, _label, _det, _view) in sorted(TEXT_CHECKS.items()):
    _make(_name, _label, _det, _view)


def _check_lexicon_binding(release, context):
    """Fail closed on the health-lexicon binding.

    Verify phase (the default, as for the registry's file-digest check): the release's
    manifest must exist and bind ``bindings.lexiconDigests["gate-health"]`` to exactly this
    lexicon's digest. Gate phase: a manifest, if one is given (``context["manifest"]``) or
    already present in the release, must do the same; with no manifest yet the bundled
    lexicon is used and its digest is what the writer binds.
    """
    phase = context.get("phase", "verify") if isinstance(context, dict) else "verify"
    manifest = context.get("manifest") if isinstance(context, dict) else None
    if manifest is None:
        manifest = release.manifest()
    if manifest is None:
        if phase == "gate":
            return
        raise _scan.TextCheckError("no manifest to bind the health lexicon")
    if not isinstance(manifest, dict):
        raise _scan.TextCheckError("manifest malformed")
    bindings = manifest.get("bindings")
    digests = bindings.get("lexiconDigests") if isinstance(bindings, dict) else None
    if not isinstance(digests, dict) or LEXICON_NAME not in digests:
        raise _scan.TextCheckError("manifest does not bind the health lexicon")
    if digests[LEXICON_NAME] != _lexicon.digest():
        raise _scan.TextCheckError("health lexicon digest differs from the one bound in the manifest")


@register(name=HEALTH_CHECK, version=VERSION, scope=SCOPE, unit=UNIT, applies_to=APPLIES_TO)
def check_text_health(release, contract, context):
    if _not_applicable(release, contract):
        return Outcome.not_applicable()
    required = contract.get(HEALTH_REQUIRED_KEY, False) if isinstance(contract, dict) else None
    if not isinstance(required, bool):
        raise _scan.TextCheckError("contract does not state whether health in text is forbidden")
    _check_lexicon_binding(release, context)
    fields = _scan.load(release, contract)
    per_field = []
    for f in fields:
        hits = []
        for conv in f.conversations:
            for t, text in enumerate(conv.src):
                masked = _normalise.mask_placeholders(text)
                hits.extend((conv.rows[t],) for _ in _lexicon.health_terms(masked))
        per_field.append((f, hits))
    severity = "high" if required else "low"
    return Outcome(n=sum(f.n_turns for f in fields),
                   violations=_violations(HEALTH_CHECK, "HEALTH", severity, per_field))
