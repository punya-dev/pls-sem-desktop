"""
Redundancy Analysis (Convergent Validity of Formative Constructs) Module.
Following Hair et al. (2022), A Primer on PLS-SEM (3rd ed.) and SmartPLS 4.

In SmartPLS 4, redundancy analysis is an ordinary PLS-SEM model:
1. One formative construct X_F (Mode B, 2..n indicators).
2. One single-item global construct X_G (loading = 1.000, 1 global indicator).
3. One structural path X_F -> X_G.
4. Standard PLS-SEM algorithm (path weighting, 3000 max iter, 1e-7 stop, mean replacement).
5. Convergent validity is supported if path coefficient >= 0.70 (R² >= 0.50).
"""

from typing import Dict, List, Any, Optional, Tuple
import numpy as np
import pandas as pd


def detect_redundancy_patterns(model_spec: Any) -> List[Dict[str, Any]]:
    """
    Detects whether a model consists of redundancy analysis pair(s):
    formative construct (Mode B, >= 2 indicators) -> single-item construct (1 indicator).
    Returns a list of detected redundancy pairs, or [] if the model is NOT a redundancy model.
    """
    if hasattr(model_spec, "model_dump"):
        spec_dict = model_spec.model_dump(mode="json", by_alias=True)
    elif isinstance(model_spec, dict):
        spec_dict = model_spec
    else:
        return []

    constructs_raw = spec_dict.get("constructs", [])
    if not constructs_raw:
        return []

    construct_map = {}
    for c in constructs_raw:
        cid = str(c.get("id"))
        c_type_raw = str(c.get("type", "reflective")).lower()
        c_mode_raw = str(c.get("outer_mode", "")).upper()
        is_formative = ("formative" in c_type_raw) or ("B" in c_mode_raw)
        indicators = [str(i) for i in c.get("indicators", [])]
        construct_map[cid] = {
            "id": cid,
            "name": str(c.get("name") or cid),
            "is_formative": is_formative,
            "indicators": indicators,
            "num_indicators": len(indicators),
        }

    paths_raw = spec_dict.get("paths", [])
    if not paths_raw:
        return []

    edges: List[Tuple[str, str]] = []
    for p in paths_raw:
        u = str(p.get("from") or p.get("from_node") or p.get("source"))
        v = str(p.get("to") or p.get("to_node") or p.get("target"))
        if u and v and u in construct_map and v in construct_map:
            edges.append((u, v))

    if not edges:
        return []

    # Count in-degrees and out-degrees
    in_deg: Dict[str, int] = {cid: 0 for cid in construct_map}
    out_deg: Dict[str, int] = {cid: 0 for cid in construct_map}
    for u, v in edges:
        out_deg[u] += 1
        in_deg[v] += 1

    # Check that EVERY edge is an isolated formative -> single-item path
    pairs = []
    for u, v in edges:
        src = construct_map[u]
        tgt = construct_map[v]

        # Source must be formative with >= 2 indicators
        if not src["is_formative"] or src["num_indicators"] < 2:
            return []
        # Target must have exactly 1 indicator
        if tgt["num_indicators"] != 1:
            return []
        # Source must have in_degree 0 and out_degree 1
        if in_deg[u] != 0 or out_deg[u] != 1:
            return []
        # Target must have in_degree 1 and out_degree 0
        if in_deg[v] != 1 or out_deg[v] != 0:
            return []

        pairs.append({
            "source": u,
            "target": v,
            "source_name": src["name"],
            "target_name": tgt["name"],
            "source_indicators": src["indicators"],
            "target_indicators": tgt["indicators"],
        })

    # Ensure no extra connected constructs outside these pairs
    used_constructs = set()
    for p in pairs:
        used_constructs.add(p["source"])
        used_constructs.add(p["target"])

    for cid in construct_map:
        if cid not in used_constructs and (in_deg[cid] > 0 or out_deg[cid] > 0):
            return []

    return pairs


def compute_convergent_validity_redundancy(
    results: Dict[str, Any],
    model_spec: Any,
    bootstrap_results: Optional[Dict[str, Any]] = None,
) -> Optional[List[Dict[str, Any]]]:
    """
    Computes the Convergent Validity (Redundancy Analysis) quality criteria table
    if the model matches the redundancy pattern.
    Returns None if not a redundancy analysis model.
    """
    pairs = detect_redundancy_patterns(model_spec)
    if not pairs:
        return None

    struct = results.get("structural", {})
    path_matrix = struct.get("path_coefficients", {})
    r2_map = struct.get("r_squared", {})

    # Index bootstrap path results if available
    boot_path_map: Dict[Tuple[str, str], Dict[str, Any]] = {}
    if bootstrap_results and isinstance(bootstrap_results, dict):
        for bp in bootstrap_results.get("paths", []):
            b_from = str(bp.get("from") or bp.get("from_name", ""))
            b_to = str(bp.get("to") or bp.get("to_name", ""))
            boot_path_map[(b_from, b_to)] = bp

    rows = []
    for pair in pairs:
        src = pair["source"]
        tgt = pair["target"]
        src_name = pair["source_name"]
        tgt_name = pair["target_name"]

        beta = float(path_matrix.get(tgt, {}).get(src, 0.0))
        r2 = float(r2_map.get(tgt, beta ** 2))
        supported = beta >= 0.70
        verdict = "Supported (>= 0.70)" if supported else "Not supported (< 0.70)"

        item: Dict[str, Any] = {
            "formative_construct": src_name,
            "formative_id": src,
            "global_construct": tgt_name,
            "global_id": tgt,
            "path_coefficient": round(beta, 4),
            "r_squared": round(r2, 4),
            "threshold": 0.70,
            "supported": supported,
            "result": verdict,
            "note": "Hair et al. (2022): path coefficient of at least 0.70 (R² of at least 0.50). If not met, consider adding indicators that cover the domain of the construct.",
        }

        # Check for bootstrap statistics
        boot_item = boot_path_map.get((src, tgt)) or boot_path_map.get((src_name, tgt_name))
        if boot_item:
            item["bootstrap"] = {
                "original": round(float(boot_item.get("original", beta)), 4),
                "mean": round(float(boot_item.get("mean", beta)), 4),
                "se": round(float(boot_item.get("se", 0.0)), 4),
                "t_stat": round(float(boot_item.get("t_stat", 0.0)), 4),
                "p_value": round(float(boot_item.get("p_value", 0.0)), 4),
                "ci_low": round(float(boot_item.get("ci_low", 0.0)), 4),
                "ci_high": round(float(boot_item.get("ci_high", 0.0)), 4),
                "significance": str(boot_item.get("significance", "")),
            }

        rows.append(item)

    return rows


def attach_bootstrap_to_redundancy(results: Dict[str, Any], bootstrap_results: Dict[str, Any]) -> None:
    """Attaches bootstrap significance metrics to existing convergent_validity_redundancy entries."""
    if not results or not bootstrap_results:
        return

    red_rows = results.get("convergent_validity_redundancy")
    if not red_rows or not isinstance(red_rows, list):
        return

    boot_path_map: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for bp in bootstrap_results.get("paths", []):
        b_from = str(bp.get("from") or bp.get("from_name", ""))
        b_to = str(bp.get("to") or bp.get("to_name", ""))
        boot_path_map[(b_from, b_to)] = bp

    for item in red_rows:
        src = item.get("formative_id") or item.get("formative_construct")
        tgt = item.get("global_id") or item.get("global_construct")
        boot_item = boot_path_map.get((src, tgt)) or boot_path_map.get((item.get("formative_construct"), item.get("global_construct")))
        if boot_item:
            item["bootstrap"] = {
                "original": round(float(boot_item.get("original", item.get("path_coefficient", 0.0))), 4),
                "mean": round(float(boot_item.get("mean", 0.0)), 4),
                "se": round(float(boot_item.get("se", 0.0)), 4),
                "t_stat": round(float(boot_item.get("t_stat", 0.0)), 4),
                "p_value": round(float(boot_item.get("p_value", 0.0)), 4),
                "ci_low": round(float(boot_item.get("ci_low", 0.0)), 4),
                "ci_high": round(float(boot_item.get("ci_high", 0.0)), 4),
                "significance": str(boot_item.get("significance", "")),
            }


def validate_redundancy_candidate(
    df: pd.DataFrame,
    construct_id: str,
    construct_name: str,
    indicators: List[str],
    is_formative: bool,
    global_item: str,
) -> Dict[str, Any]:
    """
    Validates a candidate construct and global item pairing for redundancy analysis wizard:
    - Construct must be formative.
    - Global item must not be one of its indicators.
    - Global item must be numeric/metric with some variance.
    - Warns (does not block) if |corr(sum of indicators, global item)| < 0.3.
    - Warns if global item has fewer than 5 distinct values.
    """
    errors: List[str] = []
    warnings: List[str] = []

    if not is_formative:
        errors.append(f"Construct '{construct_name}' is not formative. Redundancy analysis assesses convergent validity of formative constructs only.")

    if not indicators or len(indicators) < 2:
        errors.append(f"Formative construct '{construct_name}' must have at least 2 indicators.")

    if global_item in indicators:
        errors.append(f"Global item '{global_item}' cannot be one of the construct's own formative indicators.")

    if global_item not in df.columns:
        # Check case-insensitive match
        df_cols_lower = {str(c).strip().lower(): c for c in df.columns}
        matched = df_cols_lower.get(str(global_item).strip().lower())
        if matched:
            global_item = matched
        else:
            errors.append(f"Global item '{global_item}' not found in dataset columns.")

    corr_val = None
    unique_count = 0

    if not errors and global_item in df.columns:
        # Check numeric and variance
        y_raw = pd.to_numeric(df[global_item], errors='coerce')
        valid_y = y_raw.dropna()
        if len(valid_y) < 5:
            errors.append(f"Global item '{global_item}' has insufficient non-missing rows ({len(valid_y)}).")
        elif valid_y.std() < 1e-12:
            errors.append(f"Global item '{global_item}' has zero variance (constant column).")
        else:
            unique_count = int(valid_y.nunique())
            if unique_count < 5:
                warnings.append(f"Global item '{global_item}' has fewer than 5 distinct values ({unique_count}). Single-item constructs ideally have continuous or wide-scale measures.")

            # Calculate correlation with sum of formative indicators
            valid_inds = [i for i in indicators if i in df.columns]
            if len(valid_inds) == len(indicators):
                X_df = df[valid_inds].apply(pd.to_numeric, errors='coerce')
                valid_mask = valid_y.index.intersection(X_df.dropna().index)
                if len(valid_mask) > 10:
                    sum_x = X_df.loc[valid_mask].sum(axis=1)
                    y_sub = valid_y.loc[valid_mask]
                    if sum_x.std() > 1e-12 and y_sub.std() > 1e-12:
                        corr_val = float(np.corrcoef(sum_x, y_sub)[0, 1])
                        if abs(corr_val) < 0.3:
                            warnings.append(
                                f"Low correlation (|r| = {abs(corr_val):.3f} < 0.30) between '{global_item}' and sum of indicators of '{construct_name}'. "
                                "Hair et al. (2022) recommend a strong relationship for redundancy analysis."
                            )

    return {
        "is_valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "correlation": round(corr_val, 4) if corr_val is not None else None,
        "unique_values_count": unique_count,
    }


def build_redundancy_model_spec(
    construct_id: str,
    construct_name: str,
    indicators: List[str],
    global_item: str,
    dataset_id: Optional[str] = None,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """
    Builds the model specification and diagram layout for a Redundancy Analysis model:
    Constructs: <CONSTRUCT>_F (formative, Mode B) -> <CONSTRUCT>_G (reflective, Mode A, single item).
    """
    f_id = f"{construct_id}_F"
    f_name = f"{construct_name}_F"
    g_id = f"{construct_id}_G"
    g_name = f"{construct_name}_G"

    spec = {
        "constructs": [
            {
                "id": f_id,
                "name": f_name,
                "type": "formative",
                "outer_mode": "B",
                "indicators": list(indicators),
            },
            {
                "id": g_id,
                "name": g_name,
                "type": "reflective",
                "outer_mode": "A",
                "indicators": [global_item],
            },
        ],
        "paths": [
            {
                "from": f_id,
                "to": g_id,
            }
        ],
    }
    if dataset_id:
        spec["dataset_id"] = dataset_id

    # Layout: formative on left (x=240, y=280), global on right (x=600, y=280)
    layout = {
        "nodes": [
            {
                "id": f_id,
                "name": f_name,
                "x": 240,
                "y": 280,
                "isLatent": True,
                "type": "formative",
            },
            {
                "id": g_id,
                "name": g_name,
                "x": 600,
                "y": 280,
                "isLatent": True,
                "type": "reflective",
            },
        ],
        "edges": [
            {
                "id": f"edge_{f_id}_{g_id}",
                "sourceId": f_id,
                "targetId": g_id,
                "source": f_id,
                "target": g_id,
            }
        ],
    }

    # Add indicator layout positions
    k_f = len(indicators)
    y_start_f = 280 - (k_f - 1) * 30
    for idx, ind in enumerate(indicators):
        layout["nodes"].append({
            "id": f"ind_{f_id}_{idx}",
            "name": ind,
            "x": 80,
            "y": y_start_f + idx * 60,
            "isLatent": False,
            "parentId": f_id,
        })

    layout["nodes"].append({
        "id": f"ind_{g_id}_0",
        "name": global_item,
        "x": 760,
        "y": 280,
        "isLatent": False,
        "parentId": g_id,
    })

    return spec, layout

