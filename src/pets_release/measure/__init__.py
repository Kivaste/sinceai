"""Measurer: fills the manifest's `measured.*` (scorecard before/after, person-k, published baselines).

    measure(scenario, *, root, original_dir, protected_dir, rowmaps, lineage, record_keys, out_dir,
            person_k=None, search=None, redaction=None) -> dict   the `measured` block, schema-validated
    person_k_components(PersonK, *, k) -> list[dict]              aggregate person-k privacy components
    baseline_rows(root, scenario, dataset) -> list[dict]          B0 / B2 / B2-k rows from the kit's results
    measured_errors(block) -> list[str]                           schema errors of a `measured` block
    MeasureRejected                                               content-free reason code on any failure
"""

from pets_release.measure.baselines import baseline_rows
from pets_release.measure.core import measure, measured_errors
from pets_release.measure.errors import MeasureRejected
from pets_release.measure.k import person_k_components

__all__ = ["MeasureRejected", "baseline_rows", "measure", "measured_errors", "person_k_components"]
