"""
Consistent Partial Least Squares (PLSc) Module (Section 23: PLC-01 to PLC-05).
Implements correction for attenuation in reflective measurement models (Dijkstra & Henseler 2015):
- Disattenuation of construct correlations using Dijkstra-Henseler rho_A
- Correction of outer loadings
- Consistent OLS structural path estimation using corrected correlation matrix
- Consistent R2, f2, and indirect effects
"""

from typing import List, Dict, Any, Optional, Tuple
import numpy as np
import pandas as pd
from core.stats_utils import nearest_psd
from engine.pls.effects import calculate_effects


def apply_plsc_correction(
    results_pls: Dict[str, Any],
    spec_dict: Dict[str, Any],
    n_samples: int = 100,
) -> Dict[str, Any]:
    """
    Applies PLSc disattenuation and structural correction (PLC-02).
    Reflective multi-item constructs are disattenuated using rho_A.
    Formative composites and single-item constructs are treated as error-free (rho = 1).
    """
    meas = results_pls.get("measurement", {})
    struct = results_pls.get("structural", {})
    rel = results_pls.get("reliability_and_validity") or meas.get("reliability", {})

    constructs = spec_dict.get("constructs", [])
    c_names = [c["id"] for c in constructs]
    c_to_idx = {cid: i for i, cid in enumerate(c_names)}
    M = len(c_names)

    # 1. Identify reliability rho_A per construct
    rho_a_map = rel.get("rho_a", {})
    rho_factors: Dict[str, float] = {}
    warnings: List[str] = []

    for c in constructs:
        cid = c["id"]
        c_type = c.get("type", "reflective")
        # Check number of indicators
        if "indicators" in c and c["indicators"]:
            c_inds = list(c["indicators"])
        else:
            c_inds = [
                (ind.get("name") or ind.get("column") or ind.get("id"))
                for ind in spec_dict.get("indicators", [])
                if (ind.get("construct_id") or ind.get("construct")) == cid
            ]

        if c_type != "reflective" or len(c_inds) < 2:
            rho_factors[cid] = 1.0  # Error-free composite or single item
        else:
            r_val = rho_a_map.get(cid)
            if r_val is None or np.isnan(r_val) or r_val <= 0:
                rho_factors[cid] = 1.0
            elif r_val > 1.0:
                warnings.append(f"Construct '{cid}' has rho_A > 1 ({round(r_val, 4)}). Capped at 1.0.")
                rho_factors[cid] = 1.0
            else:
                rho_factors[cid] = float(r_val)

    # 2. Correct construct correlation matrix
    orig_corr = results_pls.get("construct_correlations") or meas.get("construct_correlations", {})
    R_corr = np.eye(M, dtype=float)
    for c1, i in c_to_idx.items():
        for c2, j in c_to_idx.items():
            if i != j:
                val = orig_corr.get(c1, {}).get(c2) or orig_corr.get(c2, {}).get(c1) or 0.0
                R_corr[i, j] = float(val)

    R_consistent = np.eye(M, dtype=float)
    for i, c1 in enumerate(c_names):
        for j, c2 in enumerate(c_names):
            if i == j:
                R_consistent[i, j] = 1.0
            else:
                denom = np.sqrt(rho_factors[c1] * rho_factors[c2])
                denom = max(1e-6, denom)
                corr_val = R_corr[i, j] / denom
                # Clamp correlation to [-1, 1]
                R_consistent[i, j] = np.clip(corr_val, -1.0, 1.0)

    # Ensure positive definiteness
    eigenvals = np.linalg.eigvalsh(R_consistent)
    if np.min(eigenvals) < 1e-6:
        R_consistent = nearest_psd(R_consistent)
        warnings.append("Disattenuated construct correlation matrix required nearest-PSD correction.")

    # 3. Correct outer loadings: lambda^c = w * sqrt(rho_A) / (w' w)
    weights = meas.get("outer_weights", {})
    loadings_consistent: Dict[str, Dict[str, float]] = {}

    for c in constructs:
        cid = c["id"]
        loadings_consistent[cid] = {}
        c_weights = weights.get(cid, {})
        if not c_weights:
            continue

        w_vec = np.array(list(c_weights.values()), dtype=float)
        w_norm_sq = np.sum(w_vec ** 2) or 1.0
        rho_sqrt = np.sqrt(rho_factors[cid])

        for iid, w_val in c_weights.items():
            if rho_factors[cid] == 1.0:
                # Keep original loading for single item or formative
                loadings_consistent[cid][iid] = float(meas.get("outer_loadings", {}).get(cid, {}).get(iid, w_val))
            else:
                lam_c = float(w_val * rho_sqrt / w_norm_sq)
                loadings_consistent[cid][iid] = round(lam_c, 4)

    # 4. Re-estimate structural model via OLS on consistent correlation matrix
    # Identify paths into each endogenous construct
    paths = spec_dict.get("paths", [])
    predictors_per_target: Dict[str, List[str]] = {}
    for p in paths:
        from_c = p.get("from") or p.get("from_node")
        to_c = p.get("to") or p.get("to_node")
        if to_c not in predictors_per_target:
            predictors_per_target[to_c] = []
        if from_c not in predictors_per_target[to_c]:
            predictors_per_target[to_c].append(from_c)

    path_coeffs_consistent: Dict[str, Dict[str, float]] = {c: {} for c in c_names}
    r2_consistent: Dict[str, float] = {}
    r2_adj_consistent: Dict[str, float] = {}

    for to_c, preds in predictors_per_target.items():
        if not preds:
            continue
        y_idx = c_to_idx[to_c]
        p_indices = [c_to_idx[p] for p in preds]

        R_pp = R_consistent[np.ix_(p_indices, p_indices)]
        r_py = R_consistent[p_indices, y_idx]

        try:
            betas = np.linalg.pinv(R_pp) @ r_py
            r2 = float(np.dot(r_py, betas))
            r2 = max(0.0, min(1.0, r2))
        except Exception:
            betas = np.zeros(len(preds))
            r2 = 0.0

        for p_name, beta_val in zip(preds, betas):
            path_coeffs_consistent[to_c][p_name] = round(float(beta_val), 4)

        k_pred = len(preds)
        r2_adj = 1.0 - (1.0 - r2) * (n_samples - 1) / max(1, n_samples - k_pred - 1)
        r2_consistent[to_c] = round(r2, 4)
        r2_adj_consistent[to_c] = round(r2_adj, 4)

    # 5. Compute consistent direct, indirect, and total effects
    effects_decomp = calculate_effects(path_coeffs_consistent, c_names)

    # Format consistent correlations as nested dict
    corr_consistent_dict: Dict[str, Dict[str, float]] = {}
    for i, c1 in enumerate(c_names):
        corr_consistent_dict[c1] = {}
        for j, c2 in enumerate(c_names):
            corr_consistent_dict[c1][c2] = round(float(R_consistent[i, j]), 4)

    results_plsc = {
        "is_consistent": True,
        "warnings": warnings,
        "rho_factors": rho_factors,
        "measurement": {
            "outer_loadings": loadings_consistent,
            "outer_weights": weights,
            "construct_correlations": corr_consistent_dict,
            "reliability": meas.get("reliability", {}),
            "discriminant_validity": meas.get("discriminant_validity", {}),
        },
        "structural": {
            "path_coefficients": path_coeffs_consistent,
            "r_squared": r2_consistent,
            "r_squared_adj": r2_adj_consistent,
            "effects": effects_decomp.get("effects_summary", []),
            "specific_indirect": effects_decomp.get("specific_indirect", []),
        },
        "effects_decomposition": effects_decomp,
        "results_pls_original": results_pls,
    }

    return results_plsc
