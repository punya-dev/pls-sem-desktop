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
