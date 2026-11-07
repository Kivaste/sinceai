"""Two-tier verify (ticket 17; decisions D18, D20).

CLI (loaded by the dispatcher as ``pets_release.verify.cli:main(argv)``)::

    pets-release verify <release_dir>                       recipient mode
    pets-release verify --full --kit <path> <release_dir>   controller/auditor mode, key from PETS_HMAC_KEY

Exit 0 verified, 1 verify failure, 2 usage error or unknown state (missing release path, kit or key).

Recipient mode validates the manifest with ticket 02 (closed schema, cross-field rules, canonical bytes),
recomputes every file's SHA-256 against ``bindings.files`` (and refuses unbound files), requires every
manifest-claimed release-scope check to be registered at the claimed version and scope, and re-runs every
registered release-scope check from ticket 04's registry. Success prints only
``VERIFIED (limited): N release-checked, M producer-attested`` (N = release-scope checks re-run here,
M = producer-scope checks the manifest claims and recipient mode cannot re-prove).

``--full`` additionally re-runs every registered check (both scopes) with producer context (kit root,
source tables, master key, scenario), requires every claimed check (both scopes) to be registered, checks
the HMAC-SHA256 signature with ticket 06's ``manifest_signing_key`` (alg, keyId and value), that
``bindings.inputs`` covers exactly the tables of the scenario's kit dataset (``kit.input_digests(dataset)``,
withheld tables included; missing or extra fails) with every digest matching, and the bound tool revision against this checkout's git HEAD. Any check
with status fail, error, not_run (or unregistered) fails.

Verify reads nothing but the release folder, the kit and the key: no pass file, no prior result. The
manifest's own gate records are validated for shape but never used as a status.

Python API::

    from pets_release.verify import verify_release, VerifyReport, VerifyUsageError, current_tool_revision
    report = verify_release(path, full=False | True, kit=<path|Kit>, master_key=<MasterKey>)
    report.ok, report.exit_code, report.lines, report.records
"""
from pets_release.verify.core import OK_STATUSES, VerifyReport, VerifyUsageError, verify_release
from pets_release.verify.revision import current_tool_revision

__all__ = ["OK_STATUSES", "VerifyReport", "VerifyUsageError", "current_tool_revision", "verify_release"]
