"""
Finite Mixture PLS (FIMIX-PLS) for Unobserved Heterogeneity (Section 21: LAT-01 to LAT-05).
Source of truth: Hair et al. (2017) Ch. 8 & Sarstedt et al. (2011).
Fits mixture regressions on endogenous construct latent scores across S = 1..K segments.
Computes comprehensive model selection criteria (AIC, AIC3, AIC4, BIC, CAIC, MDL5, Entropy).
"""

from typing import List, Dict, Any, Optional, Tuple, Union
import math
import numpy as np
import pandas as pd
from scipy import stats

from core.settings_schema import PipelineSettings
from engine.pls.algorithm import run_pipeline


def _fit_single_fimix_em(
    X_preds: np.ndarray,
    Y_target: np.ndarray,
    n_segments: int,
    max_iter: int = 500,
    tol: float = 1e-8,
    seed: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Fits EM algorithm for a single target endogenous construct across S segments.
    """
    N, K_preds = X_preds.shape
    S = n_segments
    rng = np.random.default_rng(seed)

    if S == 1:
        # Standard OLS
        X_design = np.column_stack([np.ones(N), X_preds])
        coefs, _, _, _ = np.linalg.lstsq(X_design, Y_target, rcond=None)
        residuals = Y_target - X_design @ coefs
        var_e = float(np.mean(residuals ** 2)) or 1e-6
        ll = float(np.sum(stats.norm.logpdf(Y_target, loc=X_design @ coefs, scale=math.sqrt(var_e))))
        return {
            "log_likelihood": ll,
            "proportions": [1.0],
            "coefficients": [coefs.tolist()],
            "variances": [var_e],
            "posteriors": np.ones((N, 1), dtype=float),
            "converged": True,
            "iterations": 1,
        }

    # Multiple random initializations of posteriors (Dirichlet)
    best_ll = -np.inf
    best_res = None

    for rep in range(5):
        post = rng.dirichlet(np.ones(S), size=N)
        X_design = np.column_stack([np.ones(N), X_preds])
        P_cols = X_design.shape[1]

        betas = np.zeros((S, P_cols), dtype=float)
        variances = np.ones(S, dtype=float) * (float(np.var(Y_target)) or 1.0)
        pi = np.ones(S, dtype=float) / S

        prev_ll = -np.inf
        converged = False

        for it in range(max_iter):
            # M-step: WLS for each segment
            pi = np.mean(post, axis=0)
            pi = np.clip(pi, 1e-6, 1.0)
            pi = pi / np.sum(pi)

            for s in range(S):
                w_s = post[:, s]
                w_sqrt = np.sqrt(w_s)[:, None]
                if np.sum(w_s) > 1e-6:
                    b_s, _, _, _ = np.linalg.lstsq(X_design * w_sqrt, Y_target * w_sqrt.ravel(), rcond=None)
                    betas[s] = b_s
                    res_s = Y_target - X_design @ b_s
                    variances[s] = max(1e-6, float(np.sum(w_s * (res_s ** 2)) / np.sum(w_s)))
                else:
                    variances[s] = 1.0

            # E-step: Compute density and update posteriors
            densities = np.zeros((N, S), dtype=float)
            for s in range(S):
                mu_s = X_design @ betas[s]
                sd_s = math.sqrt(variances[s])
                densities[:, s] = stats.norm.pdf(Y_target, loc=mu_s, scale=sd_s)

            weighted_dens = densities * pi
            denom = np.sum(weighted_dens, axis=1, keepdims=True)
            denom[denom == 0] = 1e-12

            post = weighted_dens / denom

            # Log-likelihood
            ll = float(np.sum(np.log(np.maximum(1e-12, np.sum(weighted_dens, axis=1)))))
            if abs(ll - prev_ll) < tol:
                converged = True
                break
            prev_ll = ll

        if prev_ll > best_ll:
            best_ll = prev_ll
            best_res = {
                "log_likelihood": float(best_ll),
                "proportions": [round(float(p), 4) for p in pi],
                "coefficients": [b.tolist() for b in betas],
                "variances": [round(float(v), 4) for v in variances],
                "posteriors": post,
                "converged": converged,
                "iterations": it + 1,
            }

    return best_res if best_res is not None else {
        "log_likelihood": -1e6,
        "proportions": [1.0 / S] * S,
        "coefficients": [],
        "variances": [],
        "posteriors": np.ones((N, S)) / S,
        "converged": False,
        "iterations": max_iter,
    }


def analyze_fimix(
    df: pd.DataFrame,
    spec: Union[Dict[str, Any], Any],
    min_segments: int = 1,
    max_segments: int = 4,
    seed: Optional[int] = 42,
    settings: Optional[PipelineSettings] = None,
    progress_callback: Optional[Any] = None,
    cancel_event: Optional[Any] = None,
) -> Dict[str, Any]:
    """
    Main entry point for FIMIX-PLS unobserved heterogeneity analysis (LAT-01 to LAT-05).
    """
    spec_dict = spec.model_dump(mode="json", by_alias=True) if hasattr(spec, "model_dump") else (spec if isinstance(spec, dict) else {})
    cfg = settings or PipelineSettings()

    # Step 1: Global PLS estimation to obtain latent construct scores
    res_global = run_pipeline(df, spec_dict, cfg)
    scores = res_global.get("construct_scores", {})
    N = len(df)

    paths = spec_dict.get("paths", [])
    # Find all endogenous constructs
    preds_per_target: Dict[str, List[str]] = {}
    for p in paths:
        fc = p.get("from") or p.get("from_node")
        tc = p.get("to") or p.get("to_node")
        if tc not in preds_per_target:
            preds_per_target[tc] = []
        preds_per_target[tc].append(fc)

    if not preds_per_target:
        raise ValueError("Model contains no structural paths into endogenous constructs.")

    # Target construct for mixture regression (choose construct with most predictors or first)
    target_c = max(preds_per_target.keys(), key=lambda k: len(preds_per_target[k]))
    pred_cids = preds_per_target[target_c]

    Y_target = np.asarray(scores.get(target_c, np.zeros(N)), dtype=float)
    X_preds = np.column_stack([np.asarray(scores.get(p, np.zeros(N)), dtype=float) for p in pred_cids])
    P_paths = len(pred_cids)

    # Step 2: Fit FIMIX for S = min_segments .. max_segments
    segment_evals: List[Dict[str, Any]] = []
    best_results_map: Dict[int, Dict[str, Any]] = {}

    total_steps = max_segments - min_segments + 1
    for step_i, S in enumerate(range(min_segments, max_segments + 1)):
        if cancel_event and cancel_event.is_set():
            raise RuntimeError("FIMIX-PLS cancelled by user.")

        fit_res = _fit_single_fimix_em(
            X_preds=X_preds,
            Y_target=Y_target,
            n_segments=S,
            seed=(seed + S) if seed is not None else None,
        )
        best_results_map[S] = fit_res

        lnL = fit_res["log_likelihood"]
        # Number of free parameters K = (S - 1) + S * (P_paths + 1 intercept + 1 variance)
        K = (S - 1) + S * (P_paths + 2)

        # Information criteria (LAT-02)
        aic = -2.0 * lnL + 2.0 * K
        aic3 = -2.0 * lnL + 3.0 * K
        aic4 = -2.0 * lnL + 4.0 * K
        bic = -2.0 * lnL + K * math.log(N)
        caic = -2.0 * lnL + K * (math.log(N) + 1.0)
        mdl5 = -2.0 * lnL + 5.0 * K * math.log(N)

        # Normalized Entropy EN (classification quality, 0 to 1)
        post = fit_res["posteriors"]
        if S > 1:
            safe_post = np.maximum(1e-12, post)
            entropy = -float(np.sum(post * np.log(safe_post)))
            en_norm = 1.0 - (entropy / (N * math.log(S)))
            en_norm = max(0.0, min(1.0, float(en_norm)))
        else:
            en_norm = 1.0

        # Hard segment assignment
        hard_assignments = np.argmax(post, axis=1)
        seg_counts = [int(np.sum(hard_assignments == s)) for s in range(S)]

        segment_evals.append({
            "segments": S,
            "log_likelihood": round(lnL, 4),
            "free_parameters": K,
            "aic": round(aic, 2),
            "aic3": round(aic3, 2),
            "aic4": round(aic4, 2),
            "bic": round(bic, 2),
            "caic": round(caic, 2),
            "mdl5": round(mdl5, 2),
            "entropy_normalized": round(en_norm, 4),
            "segment_proportions": fit_res["proportions"],
            "segment_sizes": seg_counts,
        })

        if progress_callback:
            progress_callback(int(((step_i + 1) / total_steps) * 100))

    # Determine recommended segment solution (joint AIC3 & CAIC; Sarstedt et al. 2011)
    best_aic3_seg = min(segment_evals, key=lambda s: s["aic3"])["segments"]
    best_caic_seg = min(segment_evals, key=lambda s: s["caic"])["segments"]

    if best_aic3_seg == best_caic_seg:
        recommendation = f"Segment solution S={best_aic3_seg} is consistently recommended by both AIC3 and CAIC."
        recommended_S = best_aic3_seg
    else:
        recommendation = (
            f"AIC3 points to S={best_aic3_seg} while CAIC points to S={best_caic_seg}. "
            f"AIC3 tends to slightly overestimate while CAIC tends to underestimate. "
            f"Inspect segment sizes and normalized entropy to make a domain-specific decision (Sarstedt et al. 2011)."
        )
        recommended_S = best_caic_seg if best_caic_seg > 1 else best_aic3_seg

    # Partition for recommended S
    rec_post = best_results_map[recommended_S]["posteriors"]
    rec_assignments = [int(s) + 1 for s in np.argmax(rec_post, axis=1)]

    return {
        "target_construct": target_c,
        "predictor_constructs": pred_cids,
        "n_samples": N,
        "segment_retention_table": segment_evals,
        "recommended_segments": recommended_S,
        "recommendation": recommendation,
        "case_assignments": rec_assignments,
        "note": "FIMIX-PLS reveals unobserved heterogeneity in the structural model. Joint evaluation of AIC3 and CAIC is recommended (Hair et al. 2017; Sarstedt et al. 2011).",
    }
