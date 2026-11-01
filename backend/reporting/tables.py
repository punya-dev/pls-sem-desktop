"""
Table Exporter and Registry Module (Section 26: REP-01).
Implements TABLE_REGISTRY mapping all PLS-SEM results to tabular structures.
Supports CSV, TSV, XLSX, JSON, and Clipboard text with configurable rounding.
"""

from typing import List, Dict, Any, Optional, Tuple, Union
import io
import csv
import json
import pandas as pd
import numpy as np


def _format_cell(val: Any, decimals: int = 3) -> str:
    if val is None or (isinstance(val, float) and (np.isnan(val) or np.isinf(val))):
        return "-"
    if isinstance(val, (float, np.floating)):
        return f"{val:.{decimals}f}"
    if isinstance(val, (int, np.integer)):
        return str(val)
    if isinstance(val, bool):
        return "Yes" if val else "No"
    return str(val)


def extract_path_coefficients_table(results: Dict[str, Any], decimals: int = 3) -> Dict[str, Any]:
    struct = results.get("structural", {})
    paths = struct.get("path_coefficients", {})
    constructs = list(paths.keys())

    all_targets = sorted(list(dict.fromkeys(
        [t for c in constructs for t in paths[c].keys()]
    )))

    columns = ["From / To"] + all_targets
    rows = []
    for c in constructs:
        row = [c]
        for t in all_targets:
            val = paths.get(c, {}).get(t)
            row.append(_format_cell(val, decimals))
        rows.append(row)

    return {"title": "Path Coefficients", "columns": columns, "rows": rows}


def extract_outer_loadings_table(results: Dict[str, Any], decimals: int = 3) -> Dict[str, Any]:
    meas = results.get("measurement", {})
    loadings = meas.get("outer_loadings", {})
    rows = []
    for cid, inds in loadings.items():
        for iid, val in inds.items():
            rows.append([cid, iid, _format_cell(val, decimals)])
    return {
        "title": "Outer Loadings",
        "columns": ["Construct", "Indicator", "Outer Loading"],
        "rows": rows,
    }


def extract_outer_weights_table(results: Dict[str, Any], decimals: int = 3) -> Dict[str, Any]:
    meas = results.get("measurement", {})
    weights = meas.get("outer_weights", {})
    rows = []
    for cid, inds in weights.items():
        for iid, val in inds.items():
            rows.append([cid, iid, _format_cell(val, decimals)])
    return {
        "title": "Outer Weights",
        "columns": ["Construct", "Indicator", "Outer Weight"],
        "rows": rows,
    }


def extract_r2_f2_table(results: Dict[str, Any], decimals: int = 3) -> Dict[str, Any]:
    struct = results.get("structural", {})
    r2_map = struct.get("r_squared", {})
    r2_adj_map = struct.get("r_squared_adj", {})
    f2_map = struct.get("f_squared", {})

    rows = []
    for cid, r2_val in r2_map.items():
        r2_adj = r2_adj_map.get(cid)
        # Find f2 into this construct
        f2_items = []
        for src, targets in f2_map.items():
            if cid in targets:
                f2_items.append(f"{src}: {_format_cell(targets[cid], decimals)}")
        f2_str = ", ".join(f2_items) if f2_items else "-"

        rows.append([
            cid,
            _format_cell(r2_val, decimals),
            _format_cell(r2_adj, decimals),
            f2_str,
        ])

    return {
        "title": "R-squared and f-squared",
        "columns": ["Endogenous Construct", "R-squared", "Adjusted R-squared", "f-squared (from predictors)"],
        "rows": rows,
    }


def extract_reliability_table(results: Dict[str, Any], decimals: int = 3) -> Dict[str, Any]:
    rel = results.get("reliability_and_validity", {})
    alphas = rel.get("cronbachs_alpha", {})
    crs = rel.get("composite_reliability", {})
    rho_as = rel.get("rho_a", {})
    aves = rel.get("ave", {})

    all_constructs = sorted(list(dict.fromkeys(
        list(alphas.keys()) + list(crs.keys()) + list(rho_as.keys()) + list(aves.keys())
    )))

    rows = []
    for cid in all_constructs:
        rows.append([
            cid,
            _format_cell(alphas.get(cid), decimals),
            _format_cell(rho_as.get(cid), decimals),
            _format_cell(crs.get(cid), decimals),
            _format_cell(aves.get(cid), decimals),
        ])

    return {
        "title": "Construct Reliability and Validity",
        "columns": ["Construct", "Cronbach's Alpha", "rho_A", "Composite Reliability (rho_c)", "AVE"],
        "rows": rows,
    }


def extract_fornell_larcker_table(results: Dict[str, Any], decimals: int = 3) -> Dict[str, Any]:
    rel = results.get("reliability_and_validity", {})
    fl = rel.get("fornell_larcker", {})
    constructs = list(fl.keys())
    columns = ["Construct"] + constructs
    rows = []
    for c1 in constructs:
        row = [c1]
        for c2 in constructs:
            row.append(_format_cell(fl.get(c1, {}).get(c2), decimals))
        rows.append(row)
    return {"title": "Fornell-Larcker Criterion", "columns": columns, "rows": rows}


def extract_htmt_table(results: Dict[str, Any], decimals: int = 3) -> Dict[str, Any]:
    rel = results.get("reliability_and_validity", {})
    htmt = rel.get("htmt", {})
    constructs = list(htmt.keys())
    columns = ["Construct"] + constructs
    rows = []
    for c1 in constructs:
        row = [c1]
        for c2 in constructs:
            row.append(_format_cell(htmt.get(c1, {}).get(c2), decimals))
        rows.append(row)
    return {"title": "Heterotrait-Monotrait Ratio (HTMT)", "columns": columns, "rows": rows}


def extract_cross_loadings_table(results: Dict[str, Any], decimals: int = 3) -> Dict[str, Any]:
    meas = results.get("measurement", {})
    cl = meas.get("cross_loadings", {})
    indicators = list(cl.keys())
    if not indicators:
        return {"title": "Cross-Loadings", "columns": ["Indicator"], "rows": []}

    constructs = sorted(list(cl[indicators[0]].keys()))
    columns = ["Indicator"] + constructs
    rows = []
    for ind in indicators:
        row = [ind]
        for c in constructs:
            row.append(_format_cell(cl.get(ind, {}).get(c), decimals))
        rows.append(row)
    return {"title": "Cross-Loadings", "columns": columns, "rows": rows}


def extract_vif_table(results: Dict[str, Any], decimals: int = 3) -> Dict[str, Any]:
    meas = results.get("measurement", {})
    struct = results.get("structural", {})

    outer_vif = meas.get("outer_vif", {})
    inner_vif = struct.get("inner_vif", {})

    rows = []
    for cid, inds in outer_vif.items():
        if isinstance(inds, dict):
            for iid, val in inds.items():
                rows.append(["Outer (Measurement)", cid, iid, _format_cell(val, decimals)])

    for target, preds in inner_vif.items():
        if isinstance(preds, dict):
            for pred, val in preds.items():
                rows.append(["Inner (Structural)", target, pred, _format_cell(val, decimals)])

    return {
        "title": "Collinearity Statistics (VIF)",
        "columns": ["Type", "Construct / Target", "Indicator / Predictor", "VIF"],
        "rows": rows,
    }


def extract_effects_table(results: Dict[str, Any], decimals: int = 3) -> Dict[str, Any]:
    struct = results.get("structural", {})
    effects = struct.get("effects", [])
    rows = []
    for eff in effects:
        rows.append([
            eff.get("from"),
            eff.get("to"),
            _format_cell(eff.get("direct"), decimals),
            _format_cell(eff.get("indirect"), decimals),
            _format_cell(eff.get("total"), decimals),
        ])
    return {
        "title": "Total, Direct, and Indirect Effects",
        "columns": ["From", "To", "Direct Effect", "Indirect Effect", "Total Effect"],
        "rows": rows,
    }


def extract_bootstrap_table(results: Dict[str, Any], decimals: int = 3) -> Dict[str, Any]:
    sig = results.get("significance", {})
    params = sig.get("parameters", {})
    rows = []
    for p_name, st in params.items():
        ci = st.get("ci_percentile", [None, None])
        rows.append([
            p_name,
            _format_cell(st.get("original"), decimals),
            _format_cell(st.get("mean"), decimals),
            _format_cell(st.get("se"), decimals),
            _format_cell(st.get("t_stat"), decimals),
            _format_cell(st.get("p_value"), 4),
            f"[{_format_cell(ci[0], decimals)}, {_format_cell(ci[1], decimals)}]",
        ])
    return {
        "title": "Bootstrapping Results",
        "columns": ["Parameter", "Original (O)", "Sample Mean (M)", "Standard Error (SE)", "t-statistic", "p-value", "95% CI"],
        "rows": rows,
    }


def extract_gaussian_copula_table(results: Dict[str, Any], decimals: int = 3) -> Dict[str, Any]:
    gc = results.get("gaussian_copula", {})
    rows = []
    for test in gc.get("endogeneity_tests", []):
        ci = f"[{_format_cell(test.get('ci_lower'), decimals)}, {_format_cell(test.get('ci_upper'), decimals)}]"
        rows.append([
            test.get("relationship", ""),
            test.get("gc_construct", ""),
            _format_cell(test.get("original"), decimals),
            _format_cell(test.get("mean"), decimals),
            _format_cell(test.get("se"), decimals),
            _format_cell(test.get("t_stat"), decimals),
            _format_cell(test.get("p_value"), 4),
            ci,
            "Yes" if test.get("is_significant") else "No",
        ])
    return {
        "title": "Gaussian Copula Endogeneity Tests",
        "columns": ["Relationship", "Copula Construct", "Original", "Sample Mean", "SE", "t-statistic", "p-value", "95% CI", "Significant (p < .05)"],
        "rows": rows,
    }


def extract_copula_wald_table(results: Dict[str, Any], decimals: int = 3) -> Dict[str, Any]:
    gc = results.get("gaussian_copula", {})
    wald = gc.get("wald_tests", {})
    rows = []
    for tgt, stats_dict in wald.get("per_target", {}).items():
        rows.append([
            f"Target: {tgt}",
            _format_cell(stats_dict.get("statistic"), decimals),
            str(stats_dict.get("df", "")),
            _format_cell(stats_dict.get("p_value"), 4),
            "Significant" if stats_dict.get("significant") else "Not Significant",
        ])
    ov = wald.get("overall", {})
    if ov:
        rows.append([
            "Overall Model",
            _format_cell(ov.get("statistic"), decimals),
            str(ov.get("df", "")),
            _format_cell(ov.get("p_value"), 4),
            "Significant" if ov.get("significant") else "Not Significant",
        ])
    return {
        "title": "Joint Wald Tests (Endogeneity)",
        "columns": ["Scope", "Chi-Square (W)", "df", "p-value", "Interpretation"],
        "rows": rows,
    }


def extract_copula_diagnostics_table(results: Dict[str, Any], decimals: int = 3) -> Dict[str, Any]:
    gc = results.get("gaussian_copula", {})
    rows = []
    for diag in gc.get("regressor_diagnostics", []):
        ad = diag.get("anderson_darling", {})
        cvm = diag.get("cramer_von_mises", {})
        ad_str = f"{_format_cell(ad.get('statistic'), decimals)} (p={_format_cell(ad.get('p_value'), 3)})"
        cvm_str = f"{_format_cell(cvm.get('statistic'), decimals)} (p={_format_cell(cvm.get('p_value'), 3)})"
        warnings_str = "; ".join(diag.get("warnings", [])) or "OK (Non-normal supported)"
        rows.append([
            diag.get("construct", ""),
            diag.get("role", ""),
            _format_cell(diag.get("skewness"), decimals),
            _format_cell(diag.get("excess_kurtosis"), decimals),
            ad_str,
            cvm_str,
            _format_cell(diag.get("corr_p_cp"), decimals),
            warnings_str,
        ])
    return {
        "title": "Copula Regressor Diagnostics",
        "columns": ["Construct", "Role", "Skewness", "Excess Kurtosis", "Anderson-Darling (p)", "Cramer-von Mises (p)", "Corr(P, C(P))", "Assessment"],
        "rows": rows,
    }


def extract_copula_correction_table(results: Dict[str, Any], decimals: int = 3) -> Dict[str, Any]:
    gc = results.get("gaussian_copula", {})
    rows = []
    for eff in gc.get("effects_of_correction", []):
        ci = f"[{_format_cell(eff.get('diff_ci_lower'), decimals)}, {_format_cell(eff.get('diff_ci_upper'), decimals)}]"
        rows.append([
            eff.get("relationship", ""),
            _format_cell(eff.get("stage1_coefficient"), decimals),
            _format_cell(eff.get("stage2_coefficient"), decimals),
            _format_cell(eff.get("difference"), decimals),
            _format_cell(eff.get("diff_se"), decimals),
            ci,
            _format_cell(eff.get("diff_pvalue"), 4),
        ])
    return {
        "title": "Effect of Copula Correction",
        "columns": ["Relationship", "Stage 1 (without GC)", "Stage 2 (with GC)", "Difference", "Diff SE", "Diff 95% CI", "Diff p-value"],
        "rows": rows,
    }


def extract_redundancy_table(results: Dict[str, Any], decimals: int = 3) -> Dict[str, Any]:
    red_rows = results.get("convergent_validity_redundancy", [])
    has_bootstrap = any("bootstrap" in r for r in red_rows)

    if has_bootstrap:
        columns = [
            "Formative Construct",
            "Global Item Construct",
            "Path Coefficient",
            "Mean",
            "SE",
            "t Value",
            "p Value",
            "95% CI",
            "R-squared of Global Item",
            "Threshold",
            "Result",
        ]
        rows = []
        for r in red_rows:
            b = r.get("bootstrap", {})
            ci_str = f"[{_format_cell(b.get('ci_low'), decimals)}, {_format_cell(b.get('ci_high'), decimals)}]" if b.get("ci_low") is not None else "-"
            rows.append([
                str(r.get("formative_construct", "")),
                str(r.get("global_construct", "")),
                _format_cell(r.get("path_coefficient"), decimals),
                _format_cell(b.get("mean"), decimals),
                _format_cell(b.get("se"), decimals),
                _format_cell(b.get("t_stat"), decimals),
                _format_cell(b.get("p_value"), 4),
                ci_str,
                _format_cell(r.get("r_squared"), decimals),
                str(r.get("threshold", "0.70")),
                str(r.get("result", "")),
            ])
    else:
        columns = [
            "Formative Construct",
            "Global Item Construct",
            "Path Coefficient",
            "R-squared of Global Item",
            "Threshold",
            "Result",
        ]
        rows = []
        for r in red_rows:
            rows.append([
                str(r.get("formative_construct", "")),
                str(r.get("global_construct", "")),
                _format_cell(r.get("path_coefficient"), decimals),
                _format_cell(r.get("r_squared"), decimals),
                str(r.get("threshold", "0.70")),
                str(r.get("result", "")),
            ])

    return {
        "title": "Convergent Validity (Redundancy Analysis)",
        "columns": columns,
        "rows": rows,
    }


def extract_nonlinear_effects_table(results: Dict[str, Any], decimals: int = 3) -> Dict[str, Any]:
    nl_rows = results.get("nonlinear_effects", [])
    columns = [
        "Predictor",
        "Target",
        "Linear Effect (b1)",
        "Quadratic Effect (b2)",
        "SE",
        "t Value",
        "p Value",
        "95% CI",
        "f²",
        "f² Rating",
        "Turning Point (SD)",
        "Shape",
    ]
    rows = []
    for r in nl_rows:
        ci_str = f"[{_format_cell(r.get('ci_lower'), decimals)}, {_format_cell(r.get('ci_upper'), decimals)}]" if r.get("ci_lower") is not None else "-"
        tp_str = f"{_format_cell(r.get('turning_point'), decimals)} ({'inside' if r.get('turning_point_in_range') else 'outside'})" if r.get("turning_point") is not None else "-"
        rows.append([
            str(r.get("predictor_name") or r.get("predictor", "")),
            str(r.get("target_name") or r.get("target", "")),
            _format_cell(r.get("linear_effect"), decimals),
            _format_cell(r.get("quadratic_effect"), decimals),
            _format_cell(r.get("standard_error"), decimals),
            _format_cell(r.get("t_statistic"), decimals),
            _format_cell(r.get("p_value"), decimals),
            ci_str,
            _format_cell(r.get("f_squared"), decimals),
            str(r.get("f_squared_rating", "-")),
            tp_str,
            str(r.get("shape", "-")),
        ])

    return {
        "title": "Nonlinear (Quadratic) Effects",
        "columns": columns,
        "rows": rows,
    }


TABLE_EXTRACTORS = {
    "path_coefficients": extract_path_coefficients_table,
    "outer_loadings": extract_outer_loadings_table,
    "outer_weights": extract_outer_weights_table,
    "r_squared": extract_r2_f2_table,
    "reliability": extract_reliability_table,
    "fornell_larcker": extract_fornell_larcker_table,
    "htmt": extract_htmt_table,
    "cross_loadings": extract_cross_loadings_table,
    "vif": extract_vif_table,
    "effects": extract_effects_table,
    "bootstrap": extract_bootstrap_table,
    "gaussian_copula": extract_gaussian_copula_table,
    "copula": extract_gaussian_copula_table,
    "copula_endogeneity": extract_gaussian_copula_table,
    "copula_wald": extract_copula_wald_table,
    "copula_diagnostics": extract_copula_diagnostics_table,
    "copula_correction": extract_copula_correction_table,
    "convergent_validity_redundancy": extract_redundancy_table,
    "redundancy": extract_redundancy_table,
    "convergent_validity": extract_redundancy_table,
    "nonlinear_effects": extract_nonlinear_effects_table,
    "quadratic": extract_nonlinear_effects_table,
}



def export_table_to_format(
    table_data: Dict[str, Any],
    export_format: str = "csv",
) -> Tuple[bytes, str, str]:
    """
    Exports a table dictionary {title, columns, rows} to the requested format.
    Returns (content_bytes, media_type, filename).
    """
    fmt = export_format.lower()
    title_slug = table_data.get("title", "table").lower().replace(" ", "_")
    columns = table_data.get("columns", [])
    rows = table_data.get("rows", [])

    if fmt == "csv":
        output = io.StringIO()
        writer = csv.writer(output, quoting=csv.QUOTE_MINIMAL)
        writer.writerow(columns)
        writer.writerows(rows)
        content = output.getvalue().encode("utf-8")
        return content, "text/csv", f"{title_slug}.csv"

    elif fmt == "tsv":
        output = io.StringIO()
        writer = csv.writer(output, delimiter="\t", quoting=csv.QUOTE_MINIMAL)
        writer.writerow(columns)
        writer.writerows(rows)
        content = output.getvalue().encode("utf-8")
        return content, "text/tab-separated-values", f"{title_slug}.tsv"

    elif fmt == "xlsx":
        df = pd.DataFrame(rows, columns=columns)
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            sheet_name = title_slug[:31]  # Excel 31 char limit
            df.to_excel(writer, sheet_name=sheet_name, index=False)
        content = output.getvalue()
        return content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", f"{title_slug}.xlsx"

    elif fmt == "clipboard_text":
        lines = ["\t".join(columns)]
        for r in rows:
            lines.append("\t".join(str(c) for c in r))
        content = "\n".join(lines).encode("utf-8")
        return content, "text/plain", f"{title_slug}.txt"

    else:  # JSON
        content = json.dumps(table_data, indent=2).encode("utf-8")
        return content, "application/json", f"{title_slug}.json"
