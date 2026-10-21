"""
Importance-Performance Map Analysis (IPMA) (Section 17: IPM-01 to IPM-07).
Source of truth: Hair et al. (2017) Ch. 8.
Rescales construct and indicator scores to a 0-100 scale,
calculates unstandardized total effects (importance) vs mean construct performance,
and maps constructs/indicators into four priority action quadrants.
"""

from typing import List, Dict, Any, Optional, Tuple, Union
import numpy as np
import pandas as pd

from core.settings_schema import PipelineSettings
from engine.pls.algorithm import run_pipeline


def analyze_ipma(
    df: pd.DataFrame,
    spec: Union[Dict[str, Any], Any],
    target_construct: str,
    scale_bounds: Optional[Dict[str, Tuple[float, float]]] = None,
    level: str = "both",  # "construct", "indicator", or "both"
    settings: Optional[PipelineSettings] = None,
) -> Dict[str, Any]:
    """
    Executes Importance-Performance Map Analysis on a target endogenous construct.
    """
    spec_dict = spec.model_dump(mode="json", by_alias=True) if hasattr(spec, "model_dump") else (spec if isinstance(spec, dict) else {})
    cfg = settings or PipelineSettings()
    bounds = scale_bounds or {}

    # Run baseline PLS model
    res = run_pipeline(df, spec_dict, cfg)
    meas = res.get("measurement", {})
    struct = res.get("structural", {})
    weights = meas.get("outer_weights", {})
    effects = struct.get("effects", [])

    constructs = spec_dict.get("constructs", [])
    c_map = {c["id"]: c for c in constructs}

    # Verify target is endogenous
    paths = spec_dict.get("paths", [])
    targets = set(p.get("to") or p.get("to_node") for p in paths)
    if target_construct not in targets:
        raise ValueError(
            f"IPMA target '{target_construct}' is not an endogenous construct. "
            f"Endogenous constructs available: {list(targets)}"
        )

    # 1. Rescale all indicators to 0-100: x' = ((x - min) / (max - min)) * 100
    rescaled_indicators: Dict[str, np.ndarray] = {}
    indicator_raw_stats: Dict[str, Dict[str, float]] = {}

    from engine.pls.algorithm import parse_model_spec
    constructs_dict, ind_col_map, paths_list = parse_model_spec(spec_dict)
    col_to_iid = {col: iid for iid, col in ind_col_map.items()}

    all_inds = []
    c_to_inds: Dict[str, List[str]] = {}
    for cid, c_info in constructs_dict.items():
        cols = []
        for iid in c_info.get("indicators", []):
            col = ind_col_map.get(iid, iid)
            if col in df.columns:
                if col not in cols:
                    cols.append(col)
                if col not in all_inds:
                    all_inds.append(col)
        c_to_inds[cid] = cols

    for col_name in all_inds:
        col_vals = df[col_name].dropna().values.astype(float)
        iid = col_to_iid.get(col_name, col_name)
        # Bounds: user-specified or observed
        if col_name in bounds:
            s_min, s_max = bounds[col_name]
        elif iid in bounds:
            s_min, s_max = bounds[iid]
        else:
            s_min = float(np.min(col_vals))
            s_max = float(np.max(col_vals))

        denom = max(1e-12, s_max - s_min)
        rescaled_col = ((col_vals - s_min) / denom) * 100.0
        # Clip to [0, 100]
        rescaled_col = np.clip(rescaled_col, 0.0, 100.0)
        rescaled_indicators[col_name] = rescaled_col
        rescaled_indicators[iid] = rescaled_col

        indicator_raw_stats[col_name] = {
            "min": s_min,
            "max": s_max,
            "raw_mean": float(np.mean(col_vals)),
            "raw_std": float(np.std(col_vals, ddof=0)) or 1.0,
            "rescaled_mean": float(np.mean(rescaled_col)),
        }
        indicator_raw_stats[iid] = indicator_raw_stats[col_name]

    # 2. Compute unstandardized outer weights and rescaled construct scores
    # w_tilde_k = w_k / sigma_k, then normalized so sum(w_tilde) = 1 per construct
    unstd_weights: Dict[str, Dict[str, float]] = {}
    rescaled_construct_scores: Dict[str, np.ndarray] = {}
    construct_performance: Dict[str, float] = {}
    construct_std: Dict[str, float] = {}

    warnings: List[str] = []

    for cid, inds in c_to_inds.items():
        if not inds:
            continue
        c_weights = weights.get(cid, {})
        w_raw = np.array([float(c_weights.get(col_to_iid.get(col, col), c_weights.get(col, 0.0))) for col in inds], dtype=float)
        sigmas = np.array([indicator_raw_stats[col]["raw_std"] for col in inds], dtype=float)

        w_tilde = w_raw / sigmas
        sum_w_tilde = np.sum(w_tilde)
        if abs(sum_w_tilde) > 1e-12:
            w_norm = w_tilde / sum_w_tilde
        else:
            w_norm = np.ones(len(inds)) / len(inds)

        unstd_weights[cid] = {col: float(wn) for col, wn in zip(inds, w_norm)}

        # Check for negative weights
        for col, wn in zip(inds, w_norm):
            if wn < 0:
                warnings.append(f"Indicator '{col}' in construct '{cid}' has a negative unstandardized weight ({round(wn, 4)}). Verify indicator polarity/coding.")

        # Compute rescaled construct score Y' = sum w_norm * x'
        X_rescaled = np.column_stack([rescaled_indicators[col] for col in inds])
        y_prime = X_rescaled @ w_norm
        y_prime = np.clip(y_prime, 0.0, 100.0)

        rescaled_construct_scores[cid] = y_prime
        construct_performance[cid] = float(np.mean(y_prime))
        construct_std[cid] = float(np.std(y_prime, ddof=0)) or 1.0

    target_perf = construct_performance[target_construct]
    target_sigma = construct_std[target_construct]

    # 3. Compute construct-level importance (unstandardized total effects)
    # importance = total_effect_std * (sigma_target / sigma_pred)
    construct_importance: Dict[str, float] = {}
    construct_std_effects: Dict[str, float] = {}

    for eff in effects:
        if eff.get("to") == target_construct:
            fc = eff.get("from")
            tot_std = float(eff.get("total", 0.0))
            construct_std_effects[fc] = tot_std

            pred_sigma = construct_std.get(fc, 1.0)
            unstd_importance = tot_std * (target_sigma / pred_sigma)
            construct_importance[fc] = unstd_importance

    # 4. Classify quadrants based on mean importance and performance
    pred_cids = list(construct_importance.keys())
    if pred_cids:
        mean_c_importance = float(np.mean([construct_importance[c] for c in pred_cids]))
        mean_c_performance = float(np.mean([construct_performance[c] for c in pred_cids]))
    else:
        mean_c_importance = 0.0
        mean_c_performance = 50.0

    construct_quadrants = []
    for cid in pred_cids:
        imp = construct_importance[cid]
        perf = construct_performance[cid]

        if imp >= mean_c_importance and perf < mean_c_performance:
            quadrant = "concentrate_here"  # High importance, low performance
            quadrant_num = "II"
        elif imp >= mean_c_importance and perf >= mean_c_performance:
            quadrant = "keep_up_good_work"  # High importance, high performance
            quadrant_num = "I"
        elif imp < mean_c_importance and perf < mean_c_performance:
            quadrant = "low_priority"  # Low importance, low performance
            quadrant_num = "III"
        else:
            quadrant = "possible_overkill"  # Low importance, high performance
            quadrant_num = "IV"

        construct_quadrants.append({
            "construct_id": cid,
            "construct_name": constructs_dict.get(cid, {}).get("name", cid),
            "importance": round(imp, 4),
            "performance": round(perf, 4),
            "importance_standardized": round(construct_std_effects.get(cid, 0.0), 4),
            "quadrant": quadrant,
            "quadrant_number": quadrant_num,
        })

    # 5. Indicator-level IPMA (importance_k = construct_importance * w_tilde_k)
    indicator_quadrants = []
    for cid in pred_cids:
        c_imp = construct_importance[cid]
        for iid in c_to_inds.get(cid, []):
            wn = unstd_weights[cid].get(iid, 0.0)
            ind_imp = c_imp * wn
            ind_perf = indicator_raw_stats[iid]["rescaled_mean"]

            indicator_quadrants.append({
                "indicator": iid,
                "construct_id": cid,
                "importance": round(float(ind_imp), 4),
                "performance": round(float(ind_perf), 4),
                "unstandardized_weight": round(float(wn), 4),
            })

    return {
        "target_construct": target_construct,
        "target_performance": round(target_perf, 4),
        "mean_importance": round(mean_c_importance, 4),
        "mean_performance": round(mean_c_performance, 4),
        "constructs": construct_quadrants,
        "indicators": indicator_quadrants if level in ("indicator", "both") else [],
        "warnings": warnings,
        "quadrant_definitions": {
            "concentrate_here": "Quadrant II: High Importance, Low Performance (Key area for improvement)",
            "keep_up_good_work": "Quadrant I: High Importance, High Performance (Maintain current strength)",
            "low_priority": "Quadrant III: Low Importance, Low Performance (Secondary priority)",
            "possible_overkill": "Quadrant IV: Low Importance, High Performance (Over-allocation of resources)",
        },
    }
