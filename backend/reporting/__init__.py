"""
Reporting and Export Module.
Exposes table extraction, summary templates, narrative generation, and PDF export.
"""

from reporting.tables import (
    TABLE_EXTRACTORS,
    export_table_to_format,
    extract_path_coefficients_table,
    extract_outer_loadings_table,
    extract_outer_weights_table,
    extract_r2_f2_table,
    extract_reliability_table,
    extract_fornell_larcker_table,
    extract_htmt_table,
    extract_cross_loadings_table,
    extract_vif_table,
    extract_effects_table,
    extract_bootstrap_table,
)

from reporting.templates import (
    build_reflective_summary,
    build_formative_summary,
    build_discriminant_validity_summary,
    build_structural_summary,
    build_fit_summary,
)

from reporting.narrative import generate_narrative_report
from reporting.pdf_export import generate_pdf_report

__all__ = [
    "TABLE_EXTRACTORS",
    "export_table_to_format",
    "extract_path_coefficients_table",
    "extract_outer_loadings_table",
    "extract_outer_weights_table",
    "extract_r2_f2_table",
    "extract_reliability_table",
    "extract_fornell_larcker_table",
    "extract_htmt_table",
    "extract_cross_loadings_table",
    "extract_vif_table",
    "extract_effects_table",
    "extract_bootstrap_table",
    "build_reflective_summary",
    "build_formative_summary",
    "build_discriminant_validity_summary",
    "build_structural_summary",
    "build_fit_summary",
    "generate_narrative_report",
    "generate_pdf_report",
]
