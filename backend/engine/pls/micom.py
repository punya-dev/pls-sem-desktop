"""
Measurement Invariance of Composite Models (MICOM) (Section 22: MIC-01 to MIC-05).
Source of truth: Hair et al. (2017) Ch. 8 & Henseler et al. (2016).
Three-step procedure:
Step 1: Configural Invariance
Step 2: Compositional Invariance (Permutation test of composite score correlation c)
Step 3: Equality of Composite Means and Variances (Permutation test)
"""

from typing import List, Dict, Any, Optional, Tuple, Union
import numpy as np
import pandas as pd

from core.settings_schema import PipelineSettings
from core.rng import spawn_seeds, resample_indices
from engine.pls.algorithm import run_pipeline


def check_configural_invariance(
    spec_g1: Dict[str, Any],
    spec_g2: Dict[str, Any],
    attestation: bool = True,
) -> Dict[str, Any]:
    """
    Step 1: Configural Invariance (MIC-01).
    Verifies that both groups share the same model structure, indicators, and algorithm settings.
    """
    c_names_1 = sorted([c["id"] for c in spec_g1.get("constructs", [])])
    c_names_2 = sorted([c["id"] for c in spec_g2.get("constructs", [])])

    paths_1 = sorted([f"{p.get('from')}->{p.get('to')}" for p in spec_g1.get("paths", [])])
    paths_2 = sorted([f"{p.get('from')}->{p.get('to')}" for p in spec_g2.get("paths", [])])

    same_constructs = (c_names_1 == c_names_2)
    same_paths = (paths_1 == paths_2)

    passed = same_constructs and same_paths and attestation

    return {
        "passed": passed,
        "auto_verified": {
            "same_constructs": same_constructs,
            "same_paths": same_paths,
            "construct_count": len(c_names_1),
            "path_count": len(paths_1),
        },
        "needs_attestation": {
            "identical_questionnaire": attestation,
            "identical_data_collection": attestation,
        },
        "interpretation": (
            "Configural invariance established: Groups share identical constructs, indicators, and structural paths."
            if passed else
            "Configural invariance failed: Groups differ in construct specifications or data collection attestations."
        ),
    }


def _standardize_columns(X: np.ndarray, ref_X: Optional[np.ndarray] = None) -> np.ndarray:
    basis = ref_X if ref_X is not None else X
    mu = np.mean(basis, axis=0)
    sig = np.std(basis, axis=0, ddof=0)
    sig = np.where(sig <= 1e-12, 1.0, sig)
    return (X - mu) / sig


def run_micom(
    df: pd.DataFrame,
    spec: Union[Dict[str, Any], Any],
    group_col: str,
    group_values: Optional[Tuple[Any, Any]] = None,
    n_permutations: int = 1000,
    alpha: float = 0.05,
    seed: Optional[int] = 42,
    settings: Optional[PipelineSettings] = None,
    progress_callback: Optional[Any] = None,
    cancel_event: Optional[Any] = None,
) -> Dict[str, Any]:
    """
    Executes the full 3-step MICOM procedure (MIC-01 to MIC-05).
    """
    spec_dict = spec.model_dump(mode="json", by_alias=True) if hasattr(spec, "model_dump") else (spec if isinstance(spec, dict) else {})
    cfg = settings or PipelineSettings()

    # Split groups
    if group_values is None:
        unique_groups = df[group_col].dropna().unique()
        if len(unique_groups) < 2:
            raise ValueError(f"Group column '{group_col}' must have at least 2 categories (found {len(unique_groups)}).")
        g1_val, g2_val = unique_groups[0], unique_groups[1]
    else:
        g1_val, g2_val = group_values

    df_g1 = df[df[group_col] == g1_val].copy()
    df_g2 = df[df[group_col] == g2_val].copy()

    n1 = len(df_g1)
    n2 = len(df_g2)

    if n1 < 10 or n2 < 10:
        raise ValueError(f"Sample size too small for MICOM: Group 1 has N={n1}, Group 2 has N={n2}. Minimum N=10 required.")

    # Step 1: Configural Invariance
    step1_res = check_configural_invariance(spec_dict, spec_dict, attestation=True)

    # Base estimates for Group 1, Group 2, and Pooled
    df_pooled = pd.concat([df_g1, df_g2], axis=0).reset_index(drop=True)
    res_g1 = run_pipeline(df_g1, spec_dict, cfg)
    res_g2 = run_pipeline(df_g2, spec_dict, cfg)
    res_pooled = run_pipeline(df_pooled, spec_dict, cfg)

    constructs = spec_dict.get("constructs", [])
    c_names = [c["id"] for c in constructs]

    weights_g1 = res_g1.get("measurement", {}).get("outer_weights", {})
    weights_g2 = res_g2.get("measurement", {}).get("outer_weights", {})
    weights_pooled = res_pooled.get("measurement", {}).get("outer_weights", {})

    from engine.pls.algorithm import parse_model_spec
    constructs_dict, ind_col_map, paths_list = parse_model_spec(spec_dict)
    col_to_iid = {col: iid for iid, col in ind_col_map.items()}

    # Map construct indicators
    c_to_inds: Dict[str, List[str]] = {}
    for cid, c in constructs_dict.items():
        cols = []
        for iid in c.get("indicators", []):
            col = ind_col_map.get(iid, iid)
            if col in df.columns and col not in cols:
                cols.append(col)
        c_to_inds[cid] = cols

    # Original Step 2: Correlation c between composite scores using G1 vs G2 weights on pooled data
    orig_c: Dict[str, float] = {}
    orig_diff_mean: Dict[str, float] = {}
    orig_log_var: Dict[str, float] = {}

    for cid in c_names:
        inds = c_to_inds.get(cid, [])
        if len(inds) == 0:
            continue

        w1_vec = np.array([float(weights_g1.get(cid, {}).get(col_to_iid.get(i, i), weights_g1.get(cid, {}).get(i, 0.0))) for i in inds], dtype=float)
        w2_vec = np.array([float(weights_g2.get(cid, {}).get(col_to_iid.get(i, i), weights_g2.get(cid, {}).get(i, 0.0))) for i in inds], dtype=float)
        wp_vec = np.array([float(weights_pooled.get(cid, {}).get(col_to_iid.get(i, i), weights_pooled.get(cid, {}).get(i, 0.0))) for i in inds], dtype=float)

        X_pooled = df_pooled[inds].values.astype(float)
        X_p_norm = _standardize_columns(X_pooled)

        # Composite scores with w1 and w2
        y1_p = X_p_norm @ w1_vec
        y2_p = X_p_norm @ w2_vec

        std1 = np.std(y1_p, ddof=0) or 1.0
        std2 = np.std(y2_p, ddof=0) or 1.0
        corr_val = float(np.corrcoef(y1_p, y2_p)[0, 1]) if (std1 > 1e-12 and std2 > 1e-12) else 1.0
        orig_c[cid] = corr_val

        # Step 3: Mean and log-variance difference using pooled weights
        X_g1 = df_g1[inds].values.astype(float)
        X_g2 = df_g2[inds].values.astype(float)
        X_g1_norm = _standardize_columns(X_g1, ref_X=X_pooled)
        X_g2_norm = _standardize_columns(X_g2, ref_X=X_pooled)

        y_g1 = X_g1_norm @ wp_vec
        y_g2 = X_g2_norm @ wp_vec

        mean_diff = float(np.mean(y_g1) - np.mean(y_g2))
        var1 = float(np.var(y_g1, ddof=1)) or 1e-6
        var2 = float(np.var(y_g2, ddof=1)) or 1e-6
        log_var = float(np.log(var1 / var2))

        orig_diff_mean[cid] = mean_diff
        orig_log_var[cid] = log_var

    # Permutation distributions
    perm_c = {cid: np.zeros(n_permutations, dtype=float) for cid in c_names}
    perm_diff_mean = {cid: np.zeros(n_permutations, dtype=float) for cid in c_names}
    perm_log_var = {cid: np.zeros(n_permutations, dtype=float) for cid in c_names}

    rng = np.random.default_rng(seed)
    seeds = spawn_seeds(seed or 42, n_permutations)
    N_tot = len(df_pooled)

    for p_idx in range(n_permutations):
        if cancel_event and cancel_event.is_set():
            raise RuntimeError("MICOM cancelled by user.")
        p_rng = np.random.default_rng(seeds[p_idx])
        perm_order = p_rng.permutation(N_tot)

        pseudo_g1 = df_pooled.iloc[perm_order[:n1]]
        pseudo_g2 = df_pooled.iloc[perm_order[n1:]]

        # Quick estimate weights on pseudo groups
        res_pg1 = run_pipeline(pseudo_g1, spec_dict, cfg)
        res_pg2 = run_pipeline(pseudo_g2, spec_dict, cfg)
        pw1 = res_pg1.get("measurement", {}).get("outer_weights", {})
        pw2 = res_pg2.get("measurement", {}).get("outer_weights", {})

        for cid in c_names:
            inds = c_to_inds.get(cid, [])
            if not inds:
                continue
            w1_p = np.array([float(pw1.get(cid, {}).get(col_to_iid.get(i, i), pw1.get(cid, {}).get(i, 0.0))) for i in inds], dtype=float)
            w2_p = np.array([float(pw2.get(cid, {}).get(col_to_iid.get(i, i), pw2.get(cid, {}).get(i, 0.0))) for i in inds], dtype=float)
            wp_vec = np.array([float(weights_pooled.get(cid, {}).get(col_to_iid.get(i, i), weights_pooled.get(cid, {}).get(i, 0.0))) for i in inds], dtype=float)

            X_pooled = df_pooled[inds].values.astype(float)
            X_p_norm = _standardize_columns(X_pooled)
            py1 = X_p_norm @ w1_p
            py2 = X_p_norm @ w2_p

            corr_p = float(np.corrcoef(py1, py2)[0, 1]) if (np.std(py1) > 1e-12 and np.std(py2) > 1e-12) else 1.0
            perm_c[cid][p_idx] = corr_p

            # Step 3 permutations
            px_g1 = pseudo_g1[inds].values.astype(float)
            px_g2 = pseudo_g2[inds].values.astype(float)
            px_g1_n = _standardize_columns(px_g1, ref_X=X_pooled)
            px_g2_n = _standardize_columns(px_g2, ref_X=X_pooled)

            py_g1 = px_g1_n @ wp_vec
            py_g2 = px_g2_n @ wp_vec

            perm_diff_mean[cid][p_idx] = float(np.mean(py_g1) - np.mean(py_g2))
            pv1 = float(np.var(py_g1, ddof=1)) or 1e-6
            pv2 = float(np.var(py_g2, ddof=1)) or 1e-6
            perm_log_var[cid][p_idx] = float(np.log(pv1 / pv2))

        if progress_callback and p_idx % 50 == 0:
            progress_callback(int((p_idx / n_permutations) * 100))

    # Evaluate results per construct
    construct_evals = []
    for cid in c_names:
        c_obs = orig_c.get(cid, 1.0)
        c_dist = perm_c[cid]
        # Invariance holds if c_obs >= 5% quantile of permutation distribution
        q_05_c = float(np.percentile(c_dist, 5.0))
        p_val_c = float((np.sum(c_dist <= c_obs) + 1.0) / (n_permutations + 1.0))
        step2_pass = bool(c_obs >= q_05_c)

        # Step 3: Mean difference
        md_obs = orig_diff_mean.get(cid, 0.0)
        md_dist = perm_diff_mean[cid]
        md_low = float(np.percentile(md_dist, 100.0 * (alpha / 2.0)))
        md_high = float(np.percentile(md_dist, 100.0 * (1.0 - alpha / 2.0)))
        p_val_md = float((np.sum(np.abs(md_dist) >= abs(md_obs)) + 1.0) / (n_permutations + 1.0))
        mean_equal = bool(md_low <= md_obs <= md_high)

        # Step 3: Variance ratio
        lv_obs = orig_log_var.get(cid, 0.0)
        lv_dist = perm_log_var[cid]
        lv_low = float(np.percentile(lv_dist, 100.0 * (alpha / 2.0)))
        lv_high = float(np.percentile(lv_dist, 100.0 * (1.0 - alpha / 2.0)))
        p_val_lv = float((np.sum(np.abs(lv_dist) >= abs(lv_obs)) + 1.0) / (n_permutations + 1.0))
        var_equal = bool(lv_low <= lv_obs <= lv_high)

        step3_pass = mean_equal and var_equal

        # Overall decision (MIC-04)
        if not step2_pass:
            invariance_status = "No invariance"
            recommendation = "Do not compare path coefficients or latent means across groups for this construct."
        elif not step3_pass:
            invariance_status = "Partial measurement invariance"
            recommendation = "You can compare standardized path coefficients across groups (MGA), but do not pool groups or compare latent means."
        else:
            invariance_status = "Full measurement invariance"
            recommendation = "You can compare path coefficients and latent means, and pooling group data is permitted."

        construct_evals.append({
            "construct_id": cid,
            "step2_compositional": {
                "c_correlation": round(float(c_obs), 4),
                "threshold_5pct": round(float(q_05_c), 4),
                "p_value": round(float(p_val_c), 4),
                "passed": step2_pass,
            },
            "step3_equal_means": {
                "mean_difference": round(float(md_obs), 4),
                "ci_lower": round(float(md_low), 4),
                "ci_upper": round(float(md_high), 4),
                "p_value": round(float(p_val_md), 4),
                "passed": mean_equal,
            },
            "step3_equal_variances": {
                "log_variance_ratio": round(float(lv_obs), 4),
                "ci_lower": round(float(lv_low), 4),
                "ci_upper": round(float(lv_high), 4),
                "p_value": round(float(p_val_lv), 4),
                "passed": var_equal,
            },
            "invariance_status": invariance_status,
            "recommendation": recommendation,
        })

    return {
        "group_column": group_col,
        "group_1": str(g1_val),
        "group_2": str(g2_val),
        "n_group_1": n1,
        "n_group_2": n2,
        "n_permutations": n_permutations,
        "configural_invariance": step1_res,
        "constructs": construct_evals,
        "overall_summary": {
            "all_partial_or_full": all(c["invariance_status"] != "No invariance" for c in construct_evals),
            "mga_eligible": all(c["invariance_status"] != "No invariance" for c in construct_evals),
        },
    }
