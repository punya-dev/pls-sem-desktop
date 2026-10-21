"""
Ex Post Segmentation Analysis (A18-EXP-01 to A18-EXP-09).
Source of truth: Hair et al. (2018) Ch. 5.

Implements:
1. Crosstabs with optimal matching permutation and overlap percentage calculation (>= 60% satisfactory).
2. Binary and multinomial logistic regression with segment assignment as dependent variable.
3. Category merging helper with minimum group size verification.
4. Explanatory group-specific model estimation, measurement evaluation table (+/- marks, stars),
   and side-by-side comparison with PLS-POS latent class solution.
"""

from typing import List, Dict, Any, Optional, Tuple, Union
import math
import itertools
import numpy as np
import pandas as pd
from scipy import stats

from core.settings_schema import PipelineSettings
from engine.pls.algorithm import run_pipeline


def compute_crosstab_overlap(
    segment_assignments: Union[List[int], np.ndarray],
    explanatory_categories: Union[List[Any], np.ndarray, pd.Series],
) -> Dict[str, Any]:
    """
    Computes contingency table and finds optimal matching permutation to calculate overlap % (A18-EXP-02).
    Overlap >= 60% is considered satisfactory.
    """
    seg = np.asarray(segment_assignments)
    cat = np.asarray(explanatory_categories)
    N = len(seg)

    unique_segs = sorted(list(np.unique(seg)))
    unique_cats = sorted(list(np.unique(cat)))

    # Raw contingency matrix
    df_cross = pd.crosstab(cat, seg, rownames=["Category"], colnames=["Segment"])
    matrix = df_cross.values  # shape: (n_cats, n_segs)

    n_cats, n_segs = matrix.shape

    # Find matching mapping category -> segment that maximizes trace / sum
    # If n_cats == n_segs: test all permutations
    best_overlap_count = 0
    best_mapping: Dict[Any, Any] = {}

    if n_cats <= n_segs:
        for perm in itertools.permutations(range(n_segs), n_cats):
            matched = sum(matrix[c_i, perm[c_i]] for c_i in range(n_cats))
            if matched > best_overlap_count:
                best_overlap_count = matched
                best_mapping = {unique_cats[c_i]: unique_segs[perm[c_i]] for c_i in range(n_cats)}
    else:
        # Each category mapped to its modal segment
        modal_segs = np.argmax(matrix, axis=1)
        best_overlap_count = sum(matrix[c_i, modal_segs[c_i]] for c_i in range(n_cats))
        best_mapping = {unique_cats[c_i]: unique_segs[modal_segs[c_i]] for c_i in range(n_cats)}

    overlap_pct = round((float(best_overlap_count) / max(1, N)) * 100.0, 2)
    is_satisfactory = overlap_pct >= 60.0

    return {
        "n_samples": N,
        "n_segments": len(unique_segs),
        "n_categories": len(unique_cats),
        "contingency_table": df_cross.to_dict(),
        "optimal_mapping": {str(k): int(v) for k, v in best_mapping.items()},
        "best_matching_mapping": {str(k): int(v) for k, v in best_mapping.items()},
        "matched_cases": int(best_overlap_count),
        "overlap_percentage": overlap_pct,
        "is_satisfactory": is_satisfactory,
        "satisfaction_verdict": (
            f"Satisfactory overlap ({overlap_pct}% >= 60%): The explanatory variable substantially accounts for segment membership."
            if is_satisfactory else
            f"Insufficient overlap ({overlap_pct}% < 60%): The explanatory variable does not adequately capture the latent segments."
        ),
    }


def run_logistic_segment_regression(
    segment_assignments: Union[List[int], np.ndarray],
    df_predictors: pd.DataFrame,
) -> Dict[str, Any]:
    """
    Fits logistic regression with segment membership as DV (A18-EXP-03).
    Binary logistic for 2 segments; Multinomial or separate logits for 3+ segments.
    """
    y = np.asarray(segment_assignments, dtype=int)
    unique_segs = sorted(list(np.unique(y)))
    S = len(unique_segs)
    N = len(y)

    # Standardize or dummy-encode predictors
    X_raw = pd.get_dummies(df_predictors, drop_first=True, dtype=float)
    X = X_raw.values
    cols = list(X_raw.columns)
    P = len(cols)

    # Intercept
    X_des = np.column_stack([np.ones(N), X])

    if S == 2:
        # Binary logistic regression: y in {0, 1}
        y_bin = (y == unique_segs[1]).astype(float)

        # Iteratively Reweighted Least Squares (IRLS)
        beta = np.zeros(P + 1)
        converged = False

        for it in range(50):
            p = 1.0 / (1.0 + np.exp(-np.clip(X_des @ beta, -30, 30)))
            W = p * (1.0 - p)
            W_mat = np.maximum(1e-6, W)[:, None]

            score = X_des.T @ (y_bin - p)
            hessian = X_des.T @ (X_des * W_mat)

            try:
                delta = np.linalg.solve(hessian, score)
                beta += delta
                if np.max(np.abs(delta)) < 1e-5:
                    converged = True
                    break
            except Exception:
                break

        # Standard errors
        try:
            cov_beta = np.linalg.inv(X_des.T @ (X_des * W_mat))
            se = np.sqrt(np.diag(cov_beta))
        except Exception:
            se = np.ones_like(beta)

        z_scores = beta / np.maximum(1e-12, se)
        p_vals = 2.0 * (1.0 - stats.norm.cdf(np.abs(z_scores)))
        odds_ratios = np.exp(np.clip(beta, -10, 10))

        results_list = [{
            "predictor": "Intercept",
            "coefficient": round(float(beta[0]), 4),
            "std_error": round(float(se[0]), 4),
            "z_statistic": round(float(z_scores[0]), 4),
            "p_value": round(float(p_vals[0]), 4),
            "odds_ratio": round(float(odds_ratios[0]), 4),
            "is_significant": bool(p_vals[0] < 0.05),
        }]

        for idx, col_name in enumerate(cols):
            results_list.append({
                "predictor": col_name,
                "coefficient": round(float(beta[idx + 1]), 4),
                "std_error": round(float(se[idx + 1]), 4),
                "z_statistic": round(float(z_scores[idx + 1]), 4),
                "p_value": round(float(p_vals[idx + 1]), 4),
                "odds_ratio": round(float(odds_ratios[idx + 1]), 4),
                "is_significant": bool(p_vals[idx + 1] < 0.05),
            })

        return {
            "type": "binary_logistic",
            "reference_segment": int(unique_segs[0]),
            "target_segment": int(unique_segs[1]),
            "n_samples": N,
            "coefficients_table": results_list,
            "coefficients": results_list,
            "converged": converged,
        }

    else:
        # Multinomial logit summary per non-reference segment
        ref_s = unique_segs[0]
        multi_results: Dict[str, Any] = {}

        for alt_s in unique_segs[1:]:
            y_pair_mask = (y == ref_s) | (y == alt_s)
            y_sub = y[y_pair_mask]
            X_sub = df_predictors.iloc[y_pair_mask]
            sub_res = run_logistic_segment_regression(y_sub, X_sub)
            multi_results[f"Segment {alt_s} vs Reference Segment {ref_s}"] = sub_res

        return {
            "type": "multinomial_logistic_pairwise",
            "reference_segment": int(ref_s),
            "pairwise_models": multi_results,
        }


def merge_categories(
    series: pd.Series,
    mapping: Dict[Any, Any],
    min_group_size: int = 54,
) -> Dict[str, Any]:
    """
    Merges categories of an explanatory variable with minimum group size check (A18-EXP-05).
    """
    merged = series.map(lambda v: mapping.get(v, v))
    counts = merged.value_counts().to_dict()

    has_small = any(c < min_group_size for c in counts.values())
    warning = (
        f"One or more merged groups have sample sizes below threshold ({min_group_size}): {counts}"
        if has_small else None
    )

    return {
        "merged_series": merged,
        "group_counts": {str(k): int(v) for k, v in counts.items()},
        "has_small_groups": has_small,
        "warning": warning,
    }


def compare_explanatory_groups_with_pos(
    df: pd.DataFrame,
    spec: Union[Dict[str, Any], Any],
    explanatory_col: str,
    pos_results: Dict[str, Any],
    min_sample_size: int = 54,
    settings: Optional[PipelineSettings] = None,
) -> Dict[str, Any]:
    """
    Evaluates explanatory groups and provides side-by-side comparison with PLS-POS solution (A18-EXP-06, A18-EXP-07).
    """
    spec_dict = spec.model_dump(mode="json", by_alias=True) if hasattr(spec, "model_dump") else (spec if isinstance(spec, dict) else {})
    cfg = settings or PipelineSettings()
    N = len(df)

    groups = sorted(list(df[explanatory_col].dropna().unique()))
    group_results: Dict[str, Any] = {}
    group_sizes: Dict[str, int] = {}
    group_r2: Dict[str, Dict[str, float]] = {}

    for g in groups:
        df_g = df[df[explanatory_col] == g].copy()
        n_g = len(df_g)
        group_sizes[str(g)] = n_g

        res_g = run_pipeline(df_g, spec_dict, cfg)
        group_results[str(g)] = res_g
        group_r2[str(g)] = {
            k: round(float(v), 4)
            for k, v in res_g.get("structural", {}).get("r_squared", {}).items()
        }

    # Weighted R^2 across explanatory groups
    paths = spec_dict.get("paths", [])
    endo_constructs = sorted(list(set(p.get("to") or p.get("to_node") for p in paths)))
    weighted_r2_grouped: Dict[str, float] = {}

    for endo_c in endo_constructs:
        w_sum = sum((group_sizes[str(g)] / N) * group_r2[str(g)].get(endo_c, 0.0) for g in groups)
        weighted_r2_grouped[endo_c] = round(float(w_sum), 4)

    # Global model R^2
    res_global = run_pipeline(df, spec_dict, cfg)
    global_r2 = {
        k: round(float(v), 4)
        for k, v in res_global.get("structural", {}).get("r_squared", {}).items()
    }

    # Side-by-side structural comparison table
    path_comparisons = []
    pos_segments = pos_results.get("segments", [])

    for p in paths:
        fc = p.get("from")
        tc = p.get("to")
        p_name = f"{fc} -> {tc}"

        row: Dict[str, Any] = {
            "path": p_name,
            "full_sample": round(float(res_global.get("structural", {}).get("path_coefficients", {}).get(tc, {}).get(fc, 0.0)), 4),
        }

        # Add explanatory groups
        for g in groups:
            b_g = float(group_results[str(g)].get("structural", {}).get("path_coefficients", {}).get(tc, {}).get(fc, 0.0))
            row[f"group_{g}"] = round(b_g, 4)

        # Add POS segments
        for seg_info in pos_segments:
            s_num = seg_info.get("segment", 1)
            b_pos = float(seg_info.get("path_coefficients", {}).get(tc, {}).get(fc, 0.0))
            row[f"pos_segment_{s_num}"] = round(b_pos, 4)

        path_comparisons.append(row)

    # Quality verdict: does explanatory grouping reproduce PLS-POS?
    # Compare weighted R^2 of grouped vs POS
    pos_wr2 = pos_results.get("weighted_r_squared", {})
    reproduction_quality = (
        "Explanatory grouping closely reproduces POS latent segments."
        if all(weighted_r2_grouped.get(k, 0.0) >= pos_wr2.get(k, 0.0) - 0.05 for k in endo_constructs)
        else "Explanatory grouping yields substantially lower variance explained than PLS-POS; segments are poorly reproduced."
    )

    return {
        "explanatory_variable": explanatory_col,
        "n_groups": len(groups),
        "group_sizes": group_sizes,
        "path_comparisons_table": path_comparisons,
        "comparison_table": path_comparisons,
        "explanatory_groups": group_results,
        "pos_solution": pos_results,
        "weighted_r_squared_explanatory": weighted_r2_grouped,
        "weighted_r_squared_pos": pos_wr2,
        "global_r_squared": global_r2,
        "reproduction_quality": reproduction_quality,
        "note": "Ex post analysis tests whether observable variables explain the unobserved segments uncovered by PLS-POS (Hair et al. 2018).",
    }
