"""Static judge dashboard rendered from the privacy manifest alone (ticket 18).

Public API:
    render_html(manifest, files_base=".") -> str   one self-contained HTML page (inline CSS, no network assets,
                                                   no scripts); never reads release tables, so no row values
    render_csv(manifest) -> str                    before/after aggregates (utility, privacy, baselines, sacrifices)
CLI: ``pets-release dashboard <release_dir> [--out <html>]`` (see ``pets_release.dashboard.cli``).
"""

from pets_release.dashboard.render import render_csv, render_html

__all__ = ["render_csv", "render_html"]
