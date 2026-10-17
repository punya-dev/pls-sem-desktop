"""
Model Fit Measures for PLS-SEM (Section 14: FIT-01 to FIT-05).
Implements:
- FIT-01: Standardized Root Mean Square Residual (SRMR) for saturated and estimated models
- FIT-02: Root Mean Squared Residual Covariance (RMS_theta) for reflective blocks
- FIT-03: Exact fit distance criteria (d_ULS, d_G)
- FIT-04/05: Tenenhaus Goodness of Fit (GoF) with literature advisory notes
"""

from typing import List, Dict, Any, Optional, Tuple
import numpy as np
import pandas as pd
from core.thresholds import THRESHOLDS


def compute_model_implied_correlation_matrices(
    X: np.ndarray,
    indicators: List[str],
    construct_indicator_map: Dict[str, List[str]],
    loadings: Dict[str, Dict[str, float]],
    construct_correlations: Dict[str, Dict[str, float]],
    path_matrix: Optional[Dict[str, Dict[str, float]]] = None,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Computes empirical indicator correlation matrix S and model-implied matrices Sigma
    for both saturated and estimated models.
    """
    K = len(indicators)
    ind_to_idx = {ind: i for i, ind in enumerate(indicators)}

    # Empirical correlation matrix S
    S = np.corrcoef(X, rowvar=False)

    # Construct list and index mapping
    construct_names = list(construct_indicator_map.keys())
    c_to_idx = {c: i for i, c in enumerate(construct_names)}
    M = len(construct_names)

    # Empirical construct correlation matrix R_C
    R_C = np.eye(M, dtype=float)
    for c1, c1_idx in c_to_idx.items():
        for c2, c2_idx in c_to_idx.items():
            if c1 != c2:
                val = construct_correlations.get(c1, {}).get(c2) or construct_correlations.get(c2, {}).get(c1) or 0.0
                R_C[c1_idx, c2_idx] = float(val)

    # Implied construct correlations for estimated model
    # Structural model implied: Phi = (I - B)^-1 Psi (I - B)^-T
    B = np.zeros((M, M), dtype=float)
    if path_matrix:
        for to_c, from_map in path_matrix.items():
            if to_c in c_to_idx:
                for from_c, coef in from_map.items():
                    if from_c in c_to_idx:
                        B[c_to_idx[to_c], c_to_idx[from_c]] = float(coef)

    try:
        I_minus_B = np.eye(M) - B
        inv_I_B = np.linalg.inv(I_minus_B)
        # Residual variance matrix Psi
        Psi = np.diag(np.diag(I_minus_B @ R_C @ I_minus_B.T))
        R_C_estimated = inv_I_B @ Psi @ inv_I_B.T
        # Normalize diagonal to 1
        d_sqrt = np.sqrt(np.diag(R_C_estimated))
        d_sqrt[d_sqrt == 0] = 1.0
        R_C_estimated = R_C_estimated / np.outer(d_sqrt, d_sqrt)
    except Exception:
        R_C_estimated = R_C.copy()

    # Build Sigma_saturated and Sigma_estimated
    Sigma_sat = S.copy()
    Sigma_est = S.copy()

    for c1, inds1 in construct_indicator_map.items():
        idx1 = c_to_idx[c1]
        for c2, inds2 in construct_indicator_map.items():
            if c1 == c2:
                continue
            idx2 = c_to_idx[c2]
            rho_sat = R_C[idx1, idx2]
            rho_est = R_C_estimated[idx1, idx2]

            for i1 in inds1:
                k1 = ind_to_idx[i1]
                lam1 = loadings.get(c1, {}).get(i1, 0.0)
                for i2 in inds2:
                    k2 = ind_to_idx[i2]
                    lam2 = loadings.get(c2, {}).get(i2, 0.0)
                    Sigma_sat[k1, k2] = lam1 * rho_sat * lam2
                    Sigma_est[k1, k2] = lam1 * rho_est * lam2

    return S, Sigma_sat, Sigma_est


def calculate_srmr(S: np.ndarray, Sigma: np.ndarray) -> Tuple[float, np.ndarray]:
    """
    Calculates Standardized Root Mean Square Residual (SRMR).
    SRMR = sqrt( mean_{i <= j} (s_ij - sigma_ij)^2 )
    Threshold: < 0.08 indicates acceptable fit (Hair et al.).
    """
    residuals = S - Sigma
    # Unique off-diagonal and diagonal elements
    triu_indices = np.triu_indices_from(residuals)
    res_sq = residuals[triu_indices] ** 2
    srmr_val = float(np.sqrt(np.mean(res_sq)))
    return srmr_val, residuals


def calculate_rms_theta(
    df: pd.DataFrame,
    spec_dict: Dict[str, Any],
    loadings: Dict[str, Dict[str, float]],
    construct_scores: Dict[str, np.ndarray],
) -> Optional[float]:
    """
    Calculates RMS_theta (FIT-02).
    Evaluates correlation of outer residuals across all reflective indicators.
    Threshold: < 0.12 (Hair et al.).
    """
    reflective_constructs = [
        c["id"] for c in spec_dict.get("constructs", [])
        if c.get("type") == "reflective"
    ]
    if not reflective_constructs:
        return None

    residuals = {}
    for c in spec_dict.get("constructs", []):
        cid = c["id"]
        if cid not in reflective_constructs:
            continue
        c_score_raw = construct_scores.get(cid)
        if c_score_raw is None:
            continue
        c_score = np.asarray(c_score_raw, dtype=float)

        c_inds = []
        if "indicators" in c and c["indicators"]:
            c_inds = [ind for ind in c["indicators"] if ind in df.columns]
        else:
            for ind in spec_dict.get("indicators", []):
                i_cid = ind.get("construct_id") or ind.get("construct")
                i_name = ind.get("name") or ind.get("column") or ind.get("id")
                if i_cid == cid and i_name in df.columns:
                    c_inds.append(i_name)
        for iid in c_inds:
            col_vals = df[iid].dropna().values.astype(float)
            if len(col_vals) != len(c_score):
                continue
            # Standardize indicator
            x_norm = (col_vals - np.mean(col_vals)) / (np.std(col_vals, ddof=0) or 1.0)
            lam = loadings.get(cid, {}).get(iid, 0.0)
            # Outer residual: e = x - lambda * Y
            e = x_norm - lam * c_score
            residuals[f"{cid}_{iid}"] = e

    if len(residuals) < 2:
        return None

    res_df = pd.DataFrame(residuals)
    res_corr = res_df.corr().values
    triu_off_diag = np.triu_indices_from(res_corr, k=1)
    if len(triu_off_diag[0]) == 0:
        return None

    rms_theta_val = float(np.sqrt(np.mean(res_corr[triu_off_diag] ** 2)))
    return rms_theta_val


def calculate_exact_fit_criteria(S: np.ndarray, Sigma: np.ndarray) -> Dict[str, float]:
    """
    Calculates exact fit discrepancy statistics (FIT-03):
    - d_ULS = 1/2 sum_{i <= j} (s_ij - sigma_ij)^2
    - d_G = 1/2 sum_k (ln nu_k)^2 where nu_k are eigenvalues of S^-1 * Sigma
    """
    residuals = S - Sigma
    triu_indices = np.triu_indices_from(residuals)
    d_uls = float(0.5 * np.sum(residuals[triu_indices] ** 2))

    d_g = 0.0
    try:
        S_inv = np.linalg.pinv(S)
        prod = S_inv @ Sigma
        eigenvals = np.linalg.eigvals(prod)
        valid_ev = [ev.real for ev in eigenvals if ev.real > 1e-9]
        if valid_ev:
            d_g = float(0.5 * np.sum(np.log(valid_ev) ** 2))
    except Exception:
        d_g = 0.0

    return {"d_uls": d_uls, "d_g": d_g}


def calculate_gof(results: Dict[str, Any]) -> Dict[str, Any]:
    """
    Calculates Tenenhaus Goodness-of-Fit (GoF = sqrt(mean_communality * mean_r2))
    Includes cautionary note (FIT-04, FIT-05).
    """
    meas = results.get("measurement", {})
    struct = results.get("structural", {})

    rel = results.get("reliability_and_validity") or meas.get("reliability", {})
    ave_vals = list(rel.get("ave", {}).values())
    ave_valid = [float(v) for v in ave_vals if v is not None and not np.isnan(v)]

    r2_vals = list(struct.get("r_squared", {}).values())
    r2_valid = [float(v) for v in r2_vals if v is not None and not np.isnan(v)]

    if not ave_valid or not r2_valid:
        return {
            "gof": None,
            "mean_communality": None,
            "mean_r2": None,
            "note": "GoF cannot be calculated when communalities or R2 values are absent.",
        }

    mean_comm = float(np.mean(ave_valid))
    mean_r2 = float(np.mean(r2_valid))
    gof_val = float(np.sqrt(mean_comm * mean_r2))

    return {
        "gof": round(gof_val, 4),
        "mean_communality": round(mean_comm, 4),
        "mean_r2": round(mean_r2, 4),
        "note": "Not recommended as a model fit criterion: Tenenhaus GoF cannot distinguish valid from invalid models (Henseler & Sarstedt, 2013).",
    }


def evaluate_model_fit(
    df: pd.DataFrame,
    spec_dict: Dict[str, Any],
    results: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Main entry point for evaluating all PLS-SEM model fit measures.
    """
    meas = results.get("measurement", {})
    struct = results.get("structural", {})

    # Collect indicators used
    construct_indicator_map = {}
    for c in spec_dict.get("constructs", []):
        cid = c["id"]
        # Try both c["indicators"] and spec_dict["indicators"]
        c_inds = []
        if "indicators" in c and c["indicators"]:
            c_inds = [ind for ind in c["indicators"] if ind in df.columns]
        else:
            for ind in spec_dict.get("indicators", []):
                i_cid = ind.get("construct_id") or ind.get("construct")
                i_name = ind.get("name") or ind.get("column") or ind.get("id")
                if i_cid == cid and i_name in df.columns:
                    c_inds.append(i_name)

        if c_inds:
            construct_indicator_map[cid] = c_inds

    all_indicators = []
    for inds in construct_indicator_map.values():
        all_indicators.extend(inds)

    if len(all_indicators) < 2:
        return {"note": "Model fit requires at least two valid indicators across constructs."}

    sub_df = df[all_indicators].dropna()
    X = sub_df.values.astype(float)

    loadings = meas.get("outer_loadings", {})
    construct_corrs = results.get("construct_correlations") or meas.get("construct_correlations", {})
    paths = struct.get("path_coefficients", {})

    S, Sigma_sat, Sigma_est = compute_model_implied_correlation_matrices(
        X=X,
        indicators=all_indicators,
        construct_indicator_map=construct_indicator_map,
        loadings=loadings,
        construct_correlations=construct_corrs,
        path_matrix=paths,
    )

    srmr_sat, res_sat = calculate_srmr(S, Sigma_sat)
    srmr_est, res_est = calculate_srmr(S, Sigma_est)

    crit_sat = calculate_exact_fit_criteria(S, Sigma_sat)
    crit_est = calculate_exact_fit_criteria(S, Sigma_est)

    construct_scores = results.get("construct_scores") or struct.get("construct_scores", {})
    rms_theta_val = calculate_rms_theta(df, spec_dict, loadings, construct_scores)

    gof_res = calculate_gof(results)

    srmr_thresh = THRESHOLDS.get("model_fit", {}).get("srmr_max", 0.08)
    rms_thresh = THRESHOLDS.get("model_fit", {}).get("rms_theta_max", 0.12)

    return {
        "saturated_model": {
            "srmr": round(srmr_sat, 4),
            "srmr_ok": srmr_sat < srmr_thresh,
            "d_uls": round(crit_sat["d_uls"], 4),
            "d_g": round(crit_sat["d_g"], 4),
        },
        "estimated_model": {
            "srmr": round(srmr_est, 4),
            "srmr_ok": srmr_est < srmr_thresh,
            "d_uls": round(crit_est["d_uls"], 4),
            "d_g": round(crit_est["d_g"], 4),
        },
        "rms_theta": round(rms_theta_val, 4) if rms_theta_val is not None else None,
        "rms_theta_ok": (rms_theta_val < rms_thresh) if rms_theta_val is not None else None,
        "gof": gof_res,
        "thresholds": {
            "srmr": srmr_thresh,
            "rms_theta": rms_thresh,
        },
        "notes": [
            "SRMR < 0.08 indicates acceptable model fit (Hu & Bentler 1999; Hair et al. 2017).",
            "RMS_theta < 0.12 indicates good outer model residual covariance (Lohmöller 1989).",
            gof_res["note"],
        ],
    }
