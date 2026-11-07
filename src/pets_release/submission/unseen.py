"""Field labels for the unlabelled ``unseen`` export, in the organisers' ``column,privacy_role,subtype`` format."""
from __future__ import annotations

from pets_release.detect import inventory, serialise
from pets_release.kit import Kit, KitError
from pets_release.submission.errors import SubmissionRefused

DATASET = "unseen"
ROLES = frozenset({"direct_identifier", "quasi_identifier", "sensitive_attribute", "technical_identifier",
                   "free_text", "record_key", "non_sensitive"})
SUBTYPES = frozenset(
    ["PERSON_NAME", "NATIONAL_ID", "EMAIL", "PHONE", "STREET_ADDRESS", "POSTCODE", "MUNICIPALITY", "GPS_COORDINATE", "LOCATION_NAME", "BIRTH_DATE", "AGE", "SEX", "LANGUAGE", "NATIONALITY", "IBAN", "PAYMENT_CARD", "CUSTOMER_ID", "ACCOUNT_ID", "EMPLOYEE_ID", "STUDENT_ID", "PATIENT_ID", "CARD_ID", "DEVICE_ID", "IP_ADDRESS", "MAC_ADDRESS", "IMEI", "HOSTNAME", "USERNAME", "URL", "USER_AGENT", "LICENSE_PLATE", "PROPERTY_ID", "METER_ID", "TIMESTAMP", "DATE", "DURATION", "HEALTH_DATA", "DIAGNOSIS_CODE", "FINANCIAL_DATA", "EDUCATION_DATA", "SOCIAL_DATA", "OCCUPATION", "ORG_NAME", "MEASUREMENT", "CATEGORY", "AGGREGATE", "SECRET", "FREE_TEXT", "RECORD_ID", "OTHER"])


def unseen_labels(kit: Kit) -> tuple[bytes, dict]:
    """(CSV bytes, aggregate counts). Every source column gets exactly one row, in source order, with a role and
    subtype from the kit taxonomy; anything else refuses."""
    try:
        tables = kit.load_dataset(DATASET)
    except KitError:
        raise SubmissionRefused("unseen_unavailable") from None
    if len(tables) != 1:
        raise SubmissionRefused("unseen_unavailable")
    (df,) = tables.values()
    if len(df.columns) == 0:
        raise SubmissionRefused("unseen_unavailable")
    inv = inventory.detect_dataset(DATASET, tables)
    if [r["column"] for r in inv] != list(df.columns):
        raise SubmissionRefused("unseen_labels_incomplete")
    if any(r["role"] not in ROLES or r["subtype"] not in SUBTYPES for r in inv):
        raise SubmissionRefused("unseen_labels_vocabulary")
    return serialise.to_unseen_csv(inv).encode("utf-8"), {"columns": len(inv)}
