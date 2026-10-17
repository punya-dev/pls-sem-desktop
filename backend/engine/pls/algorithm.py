"""
PLS-SEM Pure Estimation Core & Pipeline Engine.
Implements Wold's Lohmöller Partial Least Squares Path Modeling algorithm:
- Initial outer weights: equal (default), Lohmöller (+1 with -1 on last), individual, sum scores
- Inner weighting schemes: path, factor, centroid
- Mode A (reflective, bivariate regression) and Mode B (formative, multiple regression)
- Per-construct weighting override (e.g. sum scores per construct)
- Convergence via sum of absolute outer weight changes (ALG-07) with iteration history (RES-15)
- Sign alignment: dominant (default) or none (for bootstrap replicates)
- Structural path estimation via standardized OLS, R², adjusted R², f² effect sizes (fixed score)
- Inner VIF and Outer VIF
- Direct, specific indirect, total indirect, and total effects decomposition
- Measurement metrics: outer loadings, outer weights, indicator reliability (loading²)
- Internal consistency & validity: Cronbach's alpha, Composite Reliability (rho_c), Dijkstra-Henseler's rho_A, AVE
- Full cross-loadings matrix (all indicators x all construct scores)
- Fornell-Larcker matrix (sqrt(AVE) on diagonal for reflective constructs, null for formative/single-item)
- HTMT matrix (Heterotrait-Monotrait Ratio)
- Consistent PLS (PLSc) disattenuation and correction
"""

import math
from typing import Dict, List, Optional, Tuple, Any, Union
import numpy as np
import pandas as pd
from scipy import stats

from core.settings_schema import PipelineSettings
from core.stats_utils import (
    weighted_mean,
    weighted_std,
    pairwise_correlation_matrix,
    nearest_psd,
)
from engine.pls.effects import calculate_effects


def standardize_matrix(X: np.ndarray, weights: Optional[np.ndarray] = None) -> np.ndarray:
    """Standardizes columns of X to zero mean and unit variance (ddof=0)."""
    if weights is not None:
        mean = weighted_mean(X, weights, axis=0)
        std = weighted_std(X, weights, ddof=0, axis=0)
    else:
        mean = np.mean(X, axis=0)
        std = np.std(X, axis=0, ddof=0)
    std = np.where(std == 0, 1.0, std)
    return (X - mean) / std


def calculate_vif(X: np.ndarray) -> List[float]:
    """
    Calculates Variance Inflation Factor (VIF) for columns of matrix X.
    If 1 column, VIF is 1.0.
    """
    n_vars = X.shape[1]
    if n_vars <= 1:
        return [1.0] * n_vars

    vifs = []
    for i in range(n_vars):
        y = X[:, i]
        X_others = np.delete(X, i, axis=1)
        X_design = np.column_stack([np.ones(len(y)), X_others])
        try:
            beta, _, _, _ = np.linalg.lstsq(X_design, y, rcond=None)
            y_pred = X_design @ beta
            ss_tot = np.sum((y - np.mean(y)) ** 2)
            ss_res = np.sum((y - y_pred) ** 2)
            r2 = 1.0 - (ss_res / ss_tot) if ss_tot > 0 else 0.0
            r2 = max(0.0, min(r2, 0.999999))
            vif = 1.0 / (1.0 - r2)
        except Exception:
            vif = 1.0
        vifs.append(float(vif))
    return vifs


def parse_model_spec(model_spec: Any) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, str], List[Tuple[str, str]]]:
    """Parses model_spec into constructs dict, indicator_col_map, and paths list."""
    if hasattr(model_spec, "model_dump"):
        spec_dict = model_spec.model_dump(by_alias=True)
    elif isinstance(model_spec, dict):
        spec_dict = model_spec
    else:
        raise TypeError("model_spec must be a ModelSpec instance or dictionary")

    constructs = {}
    for c in spec_dict.get("constructs", []):
        cid = str(c["id"])
        c_type = str(c.get("type", "reflective")).lower()
        constructs[cid] = {
            "id": cid,
            "name": c.get("name", cid),
            "type": c_type,
            "indicators": list(c.get("indicators", [])),
            "weighting": c.get("weighting", "estimated"),
            "predefined_weights": c.get("predefined_weights", {}),
            "outer_mode": c.get("outer_mode", None),
        }

    indicator_col_map = {}
    for ind in spec_dict.get("indicators", []):
        iid = str(ind.get("id") or ind.get("name") or ind.get("column"))
        col = str(ind.get("column") or ind.get("name") or iid)
        indicator_col_map[iid] = col

    for c in constructs.values():
        for iid in c["indicators"]:
            if iid not in indicator_col_map:
                indicator_col_map[iid] = iid

    paths = []
    for p in spec_dict.get("paths", []):
        from_c = p.get("from") or p.get("from_node")
        to_c = p.get("to") or p.get("to_node")
        if from_c and to_c:
            paths.append((str(from_c), str(to_c)))

    return constructs, indicator_col_map, paths


def estimate_pls(
    construct_data_norm: Dict[str, np.ndarray],
    constructs: Dict[str, Dict[str, Any]],
    paths: List[Tuple[str, str]],
    settings: PipelineSettings,
    obs_weights: Optional[np.ndarray] = None,
) -> Dict[str, Any]:
    """
    Pure mathematical PLS-SEM estimation core on standardized indicator matrices.
    """
    construct_ids = list(constructs.keys())
    n_constructs = len(construct_ids)
    c_idx_map = {cid: idx for idx, cid in enumerate(construct_ids)}
    n_samples = next(iter(construct_data_norm.values())).shape[0]

    # Build adjacency matrix for inner paths: adj[i, j] == 1 means i -> j
    adj = np.zeros((n_constructs, n_constructs), dtype=float)
    for from_c, to_c in paths:
        if from_c in c_idx_map and to_c in c_idx_map:
            adj[c_idx_map[from_c], c_idx_map[to_c]] = 1.0

    # Step 1: Initialize outer weights
    weights: Dict[str, np.ndarray] = {}
    for cid in construct_ids:
        k = construct_data_norm[cid].shape[1]
        c_weighting = constructs[cid].get("weighting", "estimated")

        if c_weighting == "predefined" and constructs[cid].get("predefined_weights"):
            pre_w = constructs[cid]["predefined_weights"]
            w = np.array([float(pre_w.get(iid, 1.0 / np.sqrt(k))) for iid in constructs[cid]["indicators"]], dtype=float)
        elif settings.initial_weights == "lohmoller":
            w = np.ones(k, dtype=float)
            if k > 1:
                w[-1] = -1.0
        elif settings.initial_weights == "individual" and settings.individual_initial_weights:
            w = np.array([float(settings.individual_initial_weights.get(iid, 1.0 / np.sqrt(k))) for iid in constructs[cid]["indicators"]], dtype=float)
        elif settings.initial_weights == "sum_scores" or c_weighting == "sum_scores":
            w = np.ones(k, dtype=float)
        else:
            w = np.ones(k, dtype=float) / np.sqrt(k)

        # Normalize outer weight so that Var(X w) = 1
        X_c = construct_data_norm[cid]
        y_temp = X_c @ w
        std_temp = weighted_std(y_temp, obs_weights, ddof=0) if obs_weights is not None else np.std(y_temp, ddof=0)
        weights[cid] = w / (std_temp if std_temp > 0 else 1.0)

    # Initial construct scores Y
    Y = np.zeros((n_samples, n_constructs), dtype=float)
    for cid, idx in c_idx_map.items():
        X_norm = construct_data_norm[cid]
        y_raw = X_norm @ weights[cid]
        Y[:, idx] = standardize_matrix(y_raw.reshape(-1, 1), obs_weights).ravel()

    # Step 2: Iterative Wold Algorithm
    converged = False
    iteration = 0
    stop_criterion_history: List[Dict[str, Any]] = []

    # If max_iter == 0 or all constructs are sum_scores, skip iterative loop
    skip_iteration = (settings.max_iter == 0) or all(c.get("weighting") == "sum_scores" for c in constructs.values())

    while iteration < settings.max_iter and not converged and not skip_iteration:
        iteration += 1
        old_weights = {cid: weights[cid].copy() for cid in construct_ids}

        # 2a: Inner Approximation: Inner weights E
        E = np.zeros((n_constructs, n_constructs), dtype=float)
        corr_Y = np.corrcoef(Y, rowvar=False) if n_constructs > 1 else np.array([[1.0]])
        if np.isnan(corr_Y).any():
            corr_Y = np.nan_to_num(corr_Y, nan=0.0)

        if settings.inner_weighting == "centroid":
            for i in range(n_constructs):
                for j in range(n_constructs):
                    if adj[i, j] == 1.0 or adj[j, i] == 1.0:
                        E[i, j] = np.sign(corr_Y[i, j]) if corr_Y[i, j] != 0 else 1.0

        elif settings.inner_weighting == "factor":
            for i in range(n_constructs):
                for j in range(n_constructs):
                    if adj[i, j] == 1.0 or adj[j, i] == 1.0:
                        E[i, j] = corr_Y[i, j]

        else:  # 'path' scheme (Lohmöller standard)
            for j in range(n_constructs):
                preds = [i for i in range(n_constructs) if adj[i, j] == 1.0]
                if preds:
                    if len(preds) == 1:
                        E[preds[0], j] = corr_Y[preds[0], j]
                    else:
                        Y_preds = Y[:, preds]
                        try:
                            b, _, _, _ = np.linalg.lstsq(Y_preds, Y[:, j], rcond=None)
                            for p_pos, p in enumerate(preds):
                                E[p, j] = b[p_pos]
                        except Exception:
                            for p in preds:
                                E[p, j] = corr_Y[p, j]

                succs = [k for k in range(n_constructs) if adj[j, k] == 1.0]
                for k in succs:
                    E[k, j] = corr_Y[k, j]

        # Inner proxy scores Y_tilde
        Y_tilde = np.zeros_like(Y)
        for j in range(n_constructs):
            connected = [i for i in range(n_constructs) if E[i, j] != 0]
            if connected:
                inner_score = np.zeros(n_samples)
                for i in connected:
                    inner_score += E[i, j] * Y[:, i]
            else:
                inner_score = Y[:, j]

            Y_tilde[:, j] = standardize_matrix(inner_score.reshape(-1, 1), obs_weights).ravel()

        # 2b: Outer Weights Update
        for cid, j in c_idx_map.items():
            if constructs[cid].get("weighting") == "sum_scores":
                continue  # Fixed equal weights for sum score construct

            X_norm = construct_data_norm[cid]
            c_mode = constructs[cid].get("outer_mode")
            if not c_mode:
                c_mode = "A" if constructs[cid]["type"] == "reflective" else "B"

            y_inner = Y_tilde[:, j]

            if c_mode.upper() == "A":
                # Mode A: Bivariate regression / covariance
                if obs_weights is not None:
                    w_norm = obs_weights / np.sum(obs_weights)
                    w_new = (X_norm.T * w_norm) @ y_inner
                else:
                    w_new = (X_norm.T @ y_inner) / n_samples
            else:
                # Mode B (Formative): Multiple regression of inner score on indicators
                try:
                    if obs_weights is not None:
                        W_sqrt = np.sqrt(obs_weights)[:, None]
                        w_new, _, _, _ = np.linalg.lstsq(X_norm * W_sqrt, y_inner * W_sqrt.ravel(), rcond=None)
                    else:
                        w_new, _, _, _ = np.linalg.lstsq(X_norm, y_inner, rcond=None)
                except Exception:
                    w_new = (X_norm.T @ y_inner) / n_samples

            # Normalize outer weights so Var(X w) = 1
            y_outer = X_norm @ w_new
            std_outer = weighted_std(y_outer, obs_weights, ddof=0) if obs_weights is not None else np.std(y_outer, ddof=0)
            if std_outer > 1e-12:
                weights[cid] = w_new / std_outer
            else:
                weights[cid] = np.ones_like(w_new) / np.sqrt(len(w_new))

        # 2c: Update construct scores Y
        for cid, j in c_idx_map.items():
            X_norm = construct_data_norm[cid]
            y_raw = X_norm @ weights[cid]
            Y[:, j] = standardize_matrix(y_raw.reshape(-1, 1), obs_weights).ravel()

        # 2d: Convergence Check: sum of absolute changes across ALL outer weights (ALG-07)
        total_weight_diff = sum(
            float(np.sum(np.abs(weights[cid] - old_weights[cid])))
            for cid in construct_ids
        )
        stop_criterion_history.append({"iteration": iteration, "change": total_weight_diff})

        if total_weight_diff < settings.tolerance:
            converged = True

    if skip_iteration:
        converged = True
        iteration = 0

    # Step 3: Sign Alignment
    # Dominant sign alignment: flip construct so sum of loadings is positive (settings.sign_convention == "dominant")
    loadings: Dict[str, np.ndarray] = {}
    for cid, j in c_idx_map.items():
        X_norm = construct_data_norm[cid]
        y_j = Y[:, j]
        if obs_weights is not None:
            w_norm = obs_weights / np.sum(obs_weights)
            c_loadings = (X_norm.T * w_norm) @ y_j
        else:
            c_loadings = (X_norm.T @ y_j) / n_samples

        if settings.sign_convention == "dominant" and np.sum(c_loadings) < 0:
            weights[cid] = -weights[cid]
            Y[:, j] = -Y[:, j]
            c_loadings = -c_loadings

        loadings[cid] = c_loadings

    # Step 4: Structural Model Estimation (Standardized Betas)
    path_coefs: Dict[str, Dict[str, float]] = {cid: {} for cid in construct_ids}
    path_matrix = np.zeros((n_constructs, n_constructs), dtype=float)
    r_squared: Dict[str, float] = {}
    r_squared_adj: Dict[str, float] = {}
    f_squared: Dict[str, Dict[str, float]] = {cid: {} for cid in construct_ids}
    inner_vif: Dict[str, Dict[str, float]] = {cid: {} for cid in construct_ids}

    for j_idx, target_cid in enumerate(construct_ids):
        pred_indices = [i for i in range(n_constructs) if adj[i, j_idx] == 1.0]
        if not pred_indices:
            continue

        y_target = Y[:, j_idx]
        X_preds = Y[:, pred_indices]
        k_preds = len(pred_indices)

        if obs_weights is not None:
            W_sqrt = np.sqrt(obs_weights)[:, None]
            beta, _, _, _ = np.linalg.lstsq(X_preds * W_sqrt, y_target * W_sqrt.ravel(), rcond=None)
        else:
            beta, _, _, _ = np.linalg.lstsq(X_preds, y_target, rcond=None)

        y_hat = X_preds @ beta
        ss_tot = np.sum((y_target - np.mean(y_target)) ** 2)
        ss_res = np.sum((y_target - y_hat) ** 2)
        r2 = float(1.0 - (ss_res / ss_tot)) if ss_tot > 0 else 0.0
        r2 = max(0.0, min(r2, 1.0))
        r_squared[target_cid] = r2

        # Adjusted R²: 1 - (1 - R²) * (n - 1) / (n - k - 1)
        if n_samples - k_preds - 1 > 0:
            r2_adj = float(1.0 - (1.0 - r2) * (n_samples - 1) / (n_samples - k_preds - 1))
        else:
            r2_adj = r2
        r_squared_adj[target_cid] = max(0.0, r2_adj)

        for p_pos, p_idx in enumerate(pred_indices):
            source_cid = construct_ids[p_idx]
            val = float(beta[p_pos])
            path_coefs[target_cid][source_cid] = val
            path_matrix[p_idx, j_idx] = val

        # f² effect sizes via fixed-score method (STR-06)
        if k_preds > 1 and r2 < 1.0:
            for p_pos, p_idx in enumerate(pred_indices):
                source_cid = construct_ids[p_idx]
                other_preds = [idx for idx in pred_indices if idx != p_idx]
                X_reduced = Y[:, other_preds]
                if obs_weights is not None:
                    W_sqrt = np.sqrt(obs_weights)[:, None]
                    b_red, _, _, _ = np.linalg.lstsq(X_reduced * W_sqrt, y_target * W_sqrt.ravel(), rcond=None)
                else:
                    b_red, _, _, _ = np.linalg.lstsq(X_reduced, y_target, rcond=None)
                y_red_hat = X_reduced @ b_red
                ss_red_res = np.sum((y_target - y_red_hat) ** 2)
                r2_excl = max(0.0, float(1.0 - (ss_red_res / ss_tot)))
                f2 = (r2 - r2_excl) / (1.0 - r2)
                f_squared[target_cid][source_cid] = float(max(0.0, f2))
        elif k_preds == 1 and r2 < 1.0:
            source_cid = construct_ids[pred_indices[0]]
            f2 = r2 / (1.0 - r2)
            f_squared[target_cid][source_cid] = float(max(0.0, f2))

        # Inner VIF
        if k_preds > 1:
            vifs = calculate_vif(X_preds)
            for p_pos, p_idx in enumerate(pred_indices):
                source_cid = construct_ids[p_idx]
                inner_vif[target_cid][source_cid] = float(vifs[p_pos])
        elif k_preds == 1:
            source_cid = construct_ids[pred_indices[0]]
            inner_vif[target_cid][source_cid] = 1.0

    # Step 5: Direct, Specific Indirect, Total Indirect, Total Effects
    effects_res = calculate_effects(path_matrix, construct_ids)

    # Step 6: Measurement Model Metrics
    outer_weights_dict: Dict[str, Dict[str, float]] = {}
    outer_loadings_dict: Dict[str, Dict[str, float]] = {}
    indicator_reliability_dict: Dict[str, Dict[str, float]] = {}
    outer_vif_dict: Dict[str, Dict[str, float]] = {}

    cronbachs_alpha: Dict[str, Optional[float]] = {}
    composite_reliability: Dict[str, Optional[float]] = {}
    rho_a: Dict[str, Optional[float]] = {}
    ave: Dict[str, Optional[float]] = {}

    for cid in construct_ids:
        inds = constructs[cid]["indicators"]
        w_c = weights[cid]
        l_c = loadings[cid]
        X_norm = construct_data_norm[cid]
        k_ind = len(inds)
        is_reflective = (constructs[cid]["type"] == "reflective")

        outer_weights_dict[cid] = {iid: float(w_c[pos]) for pos, iid in enumerate(inds)}
        outer_loadings_dict[cid] = {iid: float(l_c[pos]) for pos, iid in enumerate(inds)}
        indicator_reliability_dict[cid] = {iid: float(l_c[pos] ** 2) for pos, iid in enumerate(inds)}

        # Outer VIF
        if k_ind > 1:
            ovifs = calculate_vif(X_norm)
            outer_vif_dict[cid] = {iid: float(ovifs[pos]) for pos, iid in enumerate(inds)}
        else:
            outer_vif_dict[cid] = {inds[0]: 1.0}

        # For single-item constructs, internal consistency and AVE are not interpretable (REF-12)
        if k_ind == 1:
            ave[cid] = 1.0
            composite_reliability[cid] = 1.0
            cronbachs_alpha[cid] = 1.0
            rho_a[cid] = 1.0
            continue

        # For formative constructs, AVE, CR, alpha are not interpreted (FOR-17)
        if not is_reflective:
            ave[cid] = None
            composite_reliability[cid] = None
            cronbachs_alpha[cid] = None
            rho_a[cid] = 1.0
            continue

        # Reflective multi-item metrics:
        # 1. AVE
        ave_val = float(np.mean(l_c ** 2))
        ave[cid] = ave_val

        # 2. Composite Reliability (rho_c)
        sum_l = float(np.sum(l_c))
        sum_e = float(np.sum(1.0 - l_c ** 2))
        denom_cr = (sum_l ** 2) + sum_e
        cr_val = (sum_l ** 2) / denom_cr if denom_cr > 0 else 0.0
        composite_reliability[cid] = float(cr_val)

        # 3. Cronbach's Alpha
        corr_m = np.corrcoef(X_norm, rowvar=False)
        sum_all_corr = float(np.sum(corr_m))
        if sum_all_corr > 0:
            alpha_val = (k_ind / (k_ind - 1)) * (1.0 - (k_ind / sum_all_corr))
        else:
            alpha_val = 0.0
        cronbachs_alpha[cid] = float(max(0.0, min(alpha_val, 1.0)))

        # 4. Dijkstra-Henseler's rho_A (PLC-01)
        S_mat = np.corrcoef(X_norm, rowvar=False)
        w_vec = w_c
        w_sq_sum = np.sum(w_vec ** 2)
        num = (w_sq_sum ** 2) * (w_vec @ S_mat @ w_vec - np.sum((w_vec ** 2) * np.diag(S_mat)))
        denom = (w_sq_sum ** 2) - np.sum(w_vec ** 4)
        rho_a_val = float(num / denom) if abs(denom) > 1e-12 else cr_val
        rho_a[cid] = float(max(0.0, min(rho_a_val, 1.0)))

    # Step 7: Cross Loadings Matrix (REF-07 / RES-11)
    # Correlation between EVERY indicator in the model and EVERY construct score
    cross_loadings: Dict[str, Dict[str, float]] = {}
    for cid_owner in construct_ids:
        inds_owner = constructs[cid_owner]["indicators"]
        X_owner = construct_data_norm[cid_owner]
        for pos, iid in enumerate(inds_owner):
            cross_loadings[iid] = {}
            x_var = X_owner[:, pos]
            for j_idx, cid_target in enumerate(construct_ids):
                y_target = Y[:, j_idx]
                r_val = float(np.corrcoef(x_var, y_target)[0, 1])
                cross_loadings[iid][cid_target] = r_val

    # Step 8: Discriminant Validity
    construct_corr = np.corrcoef(Y, rowvar=False) if n_constructs > 1 else np.array([[1.0]])

    # Fornell-Larcker: sqrt(AVE) on diagonal for reflective constructs, null for formative/single-item (REF-08)
    fornell_larcker: Dict[str, Dict[str, Optional[float]]] = {c1: {} for c1 in construct_ids}
    for i, c1 in enumerate(construct_ids):
        for j, c2 in enumerate(construct_ids):
            if i == j:
                is_refl = constructs[c1]["type"] == "reflective"
                is_multi = len(constructs[c1]["indicators"]) > 1
                if is_refl and is_multi and ave[c1] is not None:
                    fornell_larcker[c1][c2] = float(math.sqrt(max(0.0, ave[c1])))
                else:
                    fornell_larcker[c1][c2] = None
            else:
                fornell_larcker[c1][c2] = float(construct_corr[i, j])

    # HTMT Ratio (REF-09)
    htmt: Dict[str, Dict[str, float]] = {c1: {} for c1 in construct_ids}
    for i, c1 in enumerate(construct_ids):
        for j, c2 in enumerate(construct_ids):
            if i == j:
                htmt[c1][c2] = 1.0
                continue

            X1 = construct_data_norm[c1]
            X2 = construct_data_norm[c2]
            k1 = X1.shape[1]
            k2 = X2.shape[1]

            cross_corr = np.abs(np.corrcoef(X1, X2, rowvar=False)[:k1, k1:])
            mean_cross = float(np.mean(cross_corr))

            if k1 > 1:
                within1 = np.abs(np.corrcoef(X1, rowvar=False))
                tril1 = np.tril_indices(k1, k=-1)
                mean_within1 = float(np.mean(within1[tril1])) if len(tril1[0]) > 0 else 1.0
            else:
                mean_within1 = 1.0

            if k2 > 1:
                within2 = np.abs(np.corrcoef(X2, rowvar=False))
                tril2 = np.tril_indices(k2, k=-1)
                mean_within2 = float(np.mean(within2[tril2])) if len(tril2[0]) > 0 else 1.0
            else:
                mean_within2 = 1.0

            denom_htmt = math.sqrt(max(1e-12, mean_within1 * mean_within2))
            htmt[c1][c2] = float(mean_cross / denom_htmt)

    # Step 9: Construct scores dictionary
    scores_dict = {cid: [float(val) for val in Y[:, idx]] for idx, cid in enumerate(construct_ids)}

    return {
        "converged": converged,
        "iterations": iteration,
        "stop_criterion_history": stop_criterion_history,
        "n_samples": n_samples,
        "construct_scores": scores_dict,
        "construct_correlations": {
            c1: {c2: float(construct_corr[i, j]) for j, c2 in enumerate(construct_ids)}
            for i, c1 in enumerate(construct_ids)
        },
        "structural": {
            "path_coefficients": path_coefs,
            "r_squared": r_squared,
            "r_squared_adj": r_squared_adj,
            "f_squared": f_squared,
            "inner_vif": inner_vif,
            "effects": effects_res["effects_summary"],
            "specific_indirect": effects_res["specific_indirect"],
        },
        "effects_decomposition": effects_res,
        "measurement": {
            "outer_weights": outer_weights_dict,
            "outer_loadings": outer_loadings_dict,
            "indicator_reliability": indicator_reliability_dict,
            "outer_vif": outer_vif_dict,
            "cross_loadings": cross_loadings,
        },
        "reliability_and_validity": {
            "cronbachs_alpha": cronbachs_alpha,
            "composite_reliability": composite_reliability,
            "rho_a": rho_a,
            "ave": ave,
            "fornell_larcker": fornell_larcker,
            "htmt": htmt,
        },
    }


def run_pipeline(
    df: pd.DataFrame,
    model_spec: Any,
    settings: Optional[Union[PipelineSettings, Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    Unified entry point for the entire PLS-SEM estimation pipeline (Rule 2 / Task P0-2).
    Every feature (bootstrapping, blindfolding, permutation, MGA, PLSc, moderation)
    must call this function.
    """
    if settings is None:
        cfg = PipelineSettings()
    elif isinstance(settings, dict):
        cfg = PipelineSettings(**settings)
    else:
        cfg = settings

    constructs, ind_col_map, paths = parse_model_spec(model_spec)
    construct_ids = list(constructs.keys())

    # 1. Collect required columns
    all_required_cols: List[str] = []
    for c in constructs.values():
        for iid in c["indicators"]:
            col = ind_col_map.get(iid, iid)
            if col not in df.columns:
                raise KeyError(f"Indicator '{iid}' mapped to column '{col}' not found in dataset columns.")
            all_required_cols.append(col)

    unique_required_cols = list(dict.fromkeys(all_required_cols))

    # 2. Extract and sanitize numeric subset
    sub_data = df[unique_required_cols].copy()
    for col in unique_required_cols:
        sub_data[col] = pd.to_numeric(sub_data[col], errors='coerce')

    # Replace missing markers
    for mv in cfg.missing_codes:
        sub_data = sub_data.replace(mv, np.nan)
        try:
            mv_num = float(mv)
            sub_data = sub_data.replace(mv_num, np.nan)
            if mv_num.is_integer():
                sub_data = sub_data.replace(int(mv_num), np.nan)
        except (ValueError, TypeError):
            pass

    # 3. Missing treatment (MIS-01, MIS-02, MIS-03)
    if cfg.missing_treatment == "mean":
        for col in unique_required_cols:
            c_mean = sub_data[col].mean()
            if pd.notna(c_mean):
                sub_data[col] = sub_data[col].fillna(c_mean)
        sub_data = sub_data.dropna()
    elif cfg.missing_treatment == "listwise":
        sub_data = sub_data.dropna()
    else:
        # Default fallback to mean replacement
        for col in unique_required_cols:
            c_mean = sub_data[col].mean()
            if pd.notna(c_mean):
                sub_data[col] = sub_data[col].fillna(c_mean)
        sub_data = sub_data.dropna()

    n_samples = len(sub_data)
    if n_samples < 5:
        raise ValueError(f"Insufficient valid data rows ({n_samples}) for PLS-SEM estimation.")

    # 4. Observation weights (if weighted PLS)
    obs_weights = None
    if cfg.weight_column and cfg.weight_column in df.columns:
        raw_w = pd.to_numeric(df.loc[sub_data.index, cfg.weight_column], errors='coerce').fillna(1.0).to_numpy(dtype=float)
        # Normalize weights to mean 1
        obs_weights = raw_w / np.mean(raw_w) if np.mean(raw_w) > 0 else np.ones(n_samples)

    # 5. Build standardized block matrices
    construct_data_norm: Dict[str, np.ndarray] = {}
    for cid, cinfo in constructs.items():
        cols = [ind_col_map.get(iid, iid) for iid in cinfo["indicators"]]
        X_c = sub_data[cols].to_numpy(dtype=float)
        construct_data_norm[cid] = standardize_matrix(X_c, obs_weights)

    # 6. Execute pure estimation core
    raw_results = estimate_pls(
        construct_data_norm=construct_data_norm,
        constructs=constructs,
        paths=paths,
        settings=cfg,
        obs_weights=obs_weights,
    )

    # 7. Consistent PLS (PLSc) disattenuation if requested (Section 23)
    spec_dict = model_spec.model_dump(by_alias=True) if hasattr(model_spec, "model_dump") else (model_spec if isinstance(model_spec, dict) else {})
    if cfg.consistent:
        from engine.pls.plsc import apply_plsc_correction
        raw_results = apply_plsc_correction(raw_results, spec_dict=spec_dict, n_samples=n_samples)

    # 8. Model fit evaluation (Section 14: FIT-01 to FIT-05)
    try:
        from engine.pls.fit import evaluate_model_fit
        raw_results["fit"] = evaluate_model_fit(sub_data, spec_dict, raw_results)
    except Exception as e:
        raw_results["fit"] = {"error": str(e)}

    # Friendly construct and indicator display names
    construct_names = {}
    for cid, cinfo in constructs.items():
        cname = cinfo.get("name")
        if not cname or cname.startswith("node_") or cname.upper().startswith("LATENT"):
            cols = [ind_col_map.get(iid, iid) for iid in cinfo["indicators"]]
            stems = [c.rsplit("_", 1)[0].rsplit("-", 1)[0] for c in cols if c]
            if stems and len(set(s.upper() for s in stems)) == 1:
                cname = stems[0].upper()
        construct_names[cid] = cname or cid

    indicator_names = {iid: ind_col_map.get(iid, iid) for iid in ind_col_map}

    raw_results["algorithm"] = "pls"
    raw_results["construct_names"] = construct_names
    raw_results["indicator_names"] = indicator_names
    raw_results["settings"] = cfg.model_dump()

    return raw_results


class PLSAlgorithm:
    """
    Backward-compatible object-oriented wrapper over run_pipeline and estimate_pls.
    """

    def __init__(
        self,
        scheme: str = "path",
        max_iter: int = 300,
        tol: float = 1e-7,
        sign_alignment: bool = True,
        missing_treatment: str = "mean",
        missing_values: Optional[List[Any]] = None,
    ):
        self.scheme = scheme
        self.max_iter = max_iter
        self.tol = tol
        self.sign_alignment = sign_alignment
        self.missing_treatment = missing_treatment
        self.missing_values = missing_values if missing_values is not None else [-99, "-99"]

    def _parse_spec(self, model_spec: Any):
        return parse_model_spec(model_spec)

    def fit(self, data: pd.DataFrame, model_spec: Any, missing_treatment: Optional[str] = None) -> Dict[str, Any]:
        eff_treatment = missing_treatment or self.missing_treatment or "mean"
        settings = PipelineSettings(
            inner_weighting=self.scheme,
            max_iter=self.max_iter,
            tolerance=self.tol,
            sign_convention="dominant" if self.sign_alignment else "none",
            missing_treatment=eff_treatment,
            missing_codes=self.missing_values,
        )
        return run_pipeline(data, model_spec, settings)

    def bootstrap(
        self,
        data: pd.DataFrame,
        model_spec: Any,
        n_boot: int = 500,
        seed: Optional[int] = 42,
        progress_callback: Optional[Any] = None,
        cancel_event: Optional[Any] = None,
    ) -> Dict[str, Any]:
        from engine.pls.bootstrap import ParallelBootstrapper

        booter = ParallelBootstrapper()
        return booter.run(
            data=data,
            model_spec=model_spec,
            n_boot=n_boot,
            seed=seed,
            scheme=self.scheme,
            max_iter=self.max_iter,
            tol=self.tol,
            sign_alignment=self.sign_alignment,
            progress_callback=progress_callback,
            cancel_event=cancel_event,
        )


def run_pls(
    data: pd.DataFrame,
    model_spec: Any,
    scheme: str = "path",
    bootstrap: bool = False,
    n_boot: int = 500,
) -> Dict[str, Any]:
    """Convenience wrapper for PLS-SEM."""
    algo = PLSAlgorithm(scheme=scheme)
    res = algo.fit(data, model_spec)
    if bootstrap:
        res["significance"] = algo.bootstrap(data, model_spec, n_boot=n_boot)
    return res
