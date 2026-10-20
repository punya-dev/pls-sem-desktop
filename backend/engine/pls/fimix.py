"""
Finite Mixture PLS (FIMIX-PLS) for Unobserved Heterogeneity (A18-FIM-01 to A18-FIM-12).
Source of truth: Hair et al. (2018) Ch. 5, Sarstedt et al. (2011), and Hahn et al. (2002).

Implements:
1. Two-step approach: global PLS-SEM estimation -> simultaneous multi-equation mixture regressions.
2. EM algorithm with multi-start (10 repetitions), relative log-likelihood stop criterion (1e-5), and max iterations.
3. Information criteria: lnL, AIC, AIC3, AIC4, BIC, CAIC, MDL5, and normalized entropy EN.
4. Segment-specific path coefficients, R-squared values, and weighted R-squared.
5. In-app criteria decision advisor and casewise-deletion enforcement.
"""

from typing import List, Dict, Any, Optional, Tuple, Union
import math
import numpy as np
import pandas as pd
from scipy import stats

from core.settings_schema import PipelineSettings
from engine.pls.algorithm import run_pipeline


def _fit_multi_equation_fimix_em(
    equations: List[Dict[str, Any]],
    n_segments: int,
    n_samples: int,
    n_repetitions: int = 10,
    max_iter: int = 2000,
    tol: float = 1e-5,
    seed: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Fits simultaneous multi-equation EM mixture regression across all endogenous constructs.
    equations: List of dicts with:
      - 'target': construct ID
      - 'y': array of shape (N,)
      - 'predictors': list of predictor construct IDs
      - 'X_design': array of shape (N, P + 1) with intercept in column 0
    """
    N = n_samples
    S = n_segments
    J = len(equations)
    rng = np.random.default_rng(seed)

    # Free parameters: (S - 1) proportions + S * sum(P_j + 1 intercept + 1 error variance)
    total_P_plus_2 = sum(eq["X_design"].shape[1] + 1 for eq in equations)
    K_params = (S - 1) + S * total_P_plus_2

    if S == 1:
        # Standard simultaneous OLS
        total_ll = 0.0
        eq_results: Dict[str, Any] = {}
        eq_r2: Dict[str, float] = {}

        for eq in equations:
            t_id = eq["target"]
            y = eq["y"]
            X_des = eq["X_design"]
            coefs, _, _, _ = np.linalg.lstsq(X_des, y, rcond=None)
            res = y - X_des @ coefs
            var_e = float(np.mean(res ** 2)) or 1e-6
            ll_j = float(np.sum(stats.norm.logpdf(y, loc=X_des @ coefs, scale=math.sqrt(var_e))))
            total_ll += ll_j

            y_var = float(np.var(y)) or 1.0
            r2_j = max(0.0, 1.0 - (var_e / y_var))
            eq_r2[t_id] = round(r2_j, 4)

            # Map coefficients
            coef_map: Dict[str, float] = {"_intercept": round(float(coefs[0]), 4)}
            for p_idx, p_name in enumerate(eq["predictors"]):
                coef_map[p_name] = round(float(coefs[p_idx + 1]), 4)

            eq_results[t_id] = {
                "coefficients": [coef_map],
                "variances": [round(var_e, 4)],
                "r_squared": [round(r2_j, 4)],
            }

        return {
            "log_likelihood": total_ll,
            "free_parameters": K_params,
            "proportions": [1.0],
            "segment_sizes": [N],
            "equation_results": eq_results,
            "r_squared_per_segment": [eq_r2],
            "weighted_r_squared": eq_r2,
            "posteriors": np.ones((N, 1), dtype=float),
            "converged": True,
            "iterations": 1,
            "local_optima_detected": False,
        }

    # S > 1: Run n_repetitions with Dirichlet starts and pick best log-likelihood
    best_ll = -np.inf
    best_solution: Optional[Dict[str, Any]] = None
    rep_lls: List[float] = []

    for rep in range(n_repetitions):
        rep_seed = (seed * 1000 + rep * 17) if seed is not None else None
        rep_rng = np.random.default_rng(rep_seed)

        post = rep_rng.dirichlet(np.ones(S), size=N)
        pi = np.ones(S, dtype=float) / S

        # Initialize parameters
        betas: Dict[int, List[np.ndarray]] = {s: [] for s in range(S)}
        variances: Dict[int, List[float]] = {s: [] for s in range(S)}

        for eq in equations:
            y = eq["y"]
            X_des = eq["X_design"]
            y_var = float(np.var(y)) or 1.0
            b_init, _, _, _ = np.linalg.lstsq(X_des, y, rcond=None)
            for s in range(S):
                # Add small perturbation for segments
                pert = rep_rng.normal(0, 0.05, size=b_init.shape) if s > 0 else np.zeros_like(b_init)
                betas[s].append(b_init + pert)
                variances[s].append(y_var)

        prev_ll = -np.inf
        converged = False
        final_it = max_iter

        for it in range(max_iter):
            # M-step: Update pi and equation parameters for each segment
            pi = np.mean(post, axis=0)
            pi = np.clip(pi, 1e-6, 1.0)
            pi = pi / np.sum(pi)

            for s in range(S):
                w_s = post[:, s]
                sum_w_s = np.sum(w_s)
                w_sqrt = np.sqrt(np.maximum(1e-12, w_s))[:, None]

                for j_idx, eq in enumerate(equations):
                    y = eq["y"]
                    X_des = eq["X_design"]

                    if sum_w_s > 1e-5:
                        b_s, _, _, _ = np.linalg.lstsq(X_des * w_sqrt, y * w_sqrt.ravel(), rcond=None)
                        betas[s][j_idx] = b_s
                        res_s = y - X_des @ b_s
                        var_s = max(1e-6, float(np.sum(w_s * (res_s ** 2)) / sum_w_s))
                        variances[s][j_idx] = var_s
                    else:
                        variances[s][j_idx] = 1.0

            # E-step: Joint log-density across all J structural equations for each case in segment s
            log_dens = np.zeros((N, S), dtype=float)
            for s in range(S):
                s_dens = np.zeros(N, dtype=float)
                for j_idx, eq in enumerate(equations):
                    y = eq["y"]
                    X_des = eq["X_design"]
                    mu_js = X_des @ betas[s][j_idx]
                    sd_js = math.sqrt(variances[s][j_idx])
                    s_dens += stats.norm.logpdf(y, loc=mu_js, scale=sd_js)
                log_dens[:, s] = s_dens + math.log(pi[s])

            # Numerically stable posterior using log-sum-exp
            max_log = np.max(log_dens, axis=1, keepdims=True)
            exp_shift = np.exp(log_dens - max_log)
            sum_exp = np.sum(exp_shift, axis=1, keepdims=True)
            sum_exp[sum_exp == 0] = 1e-12
            post = exp_shift / sum_exp

            # Total log-likelihood: sum_i (max_log_i + log(sum_s exp(log_dens_is - max_log_i)))
            current_ll = float(np.sum(max_log.ravel() + np.log(np.maximum(1e-12, sum_exp.ravel()))))

            if it > 0:
                rel_change = abs(current_ll - prev_ll) / (abs(prev_ll) + 1e-12)
                if rel_change < tol:
                    converged = True
                    final_it = it + 1
                    break

            prev_ll = current_ll

        rep_lls.append(prev_ll)

        if prev_ll > best_ll:
            best_ll = prev_ll
            # Check label switching: sort segments by proportion descending
            order = np.argsort(pi)[::-1]
            sorted_pi = pi[order]
            sorted_post = post[:, order]

            sorted_betas = {new_s: betas[old_s] for new_s, old_s in enumerate(order)}
            sorted_variances = {new_s: variances[old_s] for new_s, old_s in enumerate(order)}

            # Build final segment equation results
            eq_results: Dict[str, Any] = {}
            r2_per_segment: List[Dict[str, float]] = [{} for _ in range(S)]
            weighted_r2: Dict[str, float] = {}

            for j_idx, eq in enumerate(equations):
                t_id = eq["target"]
                y = eq["y"]
                X_des = eq["X_design"]
                y_var = float(np.var(y)) or 1.0

                coef_list = []
                var_list = []
                r2_list = []

                for s in range(S):
                    b_s = sorted_betas[s][j_idx]
                    var_s = sorted_variances[s][j_idx]

                    coef_map = {"_intercept": round(float(b_s[0]), 4)}
                    for p_idx, p_name in enumerate(eq["predictors"]):
                        coef_map[p_name] = round(float(b_s[p_idx + 1]), 4)
                    coef_list.append(coef_map)
                    var_list.append(round(var_s, 4))

                    r2_s = max(0.0, 1.0 - (var_s / y_var))
                    r2_list.append(round(r2_s, 4))
                    r2_per_segment[s][t_id] = round(r2_s, 4)

                w_r2 = sum(sorted_pi[s] * r2_list[s] for s in range(S))
                weighted_r2[t_id] = round(float(w_r2), 4)

                eq_results[t_id] = {
                    "coefficients": coef_list,
                    "variances": var_list,
                    "r_squared": r2_list,
                }

            hard_assignments = np.argmax(sorted_post, axis=1)
            seg_counts = [int(np.sum(hard_assignments == s)) for s in range(S)]

            best_solution = {
                "log_likelihood": float(best_ll),
                "free_parameters": K_params,
                "proportions": [round(float(p), 4) for p in sorted_pi],
                "segment_sizes": seg_counts,
                "equation_results": eq_results,
                "r_squared_per_segment": r2_per_segment,
                "weighted_r_squared": weighted_r2,
                "posteriors": sorted_post,
                "converged": converged,
                "iterations": final_it,
            }

    # Detect local optima: check variance in top repetition log-likelihoods
    valid_lls = [l for l in rep_lls if np.isfinite(l)]
    local_optima = (len(valid_lls) > 1 and (max(valid_lls) - min(valid_lls) > 2.0))
    if best_solution:
        best_solution["local_optima_detected"] = local_optima

    return best_solution or {
        "log_likelihood": -1e6,
        "free_parameters": K_params,
        "proportions": [1.0 / S] * S,
        "segment_sizes": [N // S] * S,
        "equation_results": {},
        "r_squared_per_segment": [],
        "weighted_r_squared": {},
        "posteriors": np.ones((N, S)) / S,
        "converged": False,
        "iterations": max_iter,
        "local_optima_detected": False,
    }


def analyze_fimix(
    df: pd.DataFrame,
    spec: Union[Dict[str, Any], Any],
    min_segments: int = 1,
    max_segments: int = 4,
    n_repetitions: int = 10,
    max_iter: int = 2000,
    tol: float = 1e-5,
    min_sample_size: int = 54,
    seed: Optional[int] = 42,
    settings: Optional[PipelineSettings] = None,
    progress_callback: Optional[Any] = None,
    cancel_event: Optional[Any] = None,
) -> Dict[str, Any]:
    """
    Main entry point for Finite Mixture PLS (FIMIX-PLS) analysis (A18-FIM-01 to A18-FIM-12).
    """
    spec_dict = spec.model_dump(mode="json", by_alias=True) if hasattr(spec, "model_dump") else (spec if isinstance(spec, dict) else {})
    cfg = settings or PipelineSettings()

    # A18-FIM-04: Casewise deletion check and warning
    has_missing = bool(df.isna().any().any())
    missing_warning = None
    if has_missing:
        if cfg.missing_treatment != "casewise":
            missing_warning = (
                "Missing values detected and non-casewise treatment selected. "
                "Hair et al. (2018) strongly advise using casewise deletion with FIMIX-PLS, "
                "as mean replacement can artificially create missing-value latent segments."
            )

    # Step 1: Global PLS estimation to obtain latent construct scores
    res_global = run_pipeline(df, spec_dict, cfg)
    scores = res_global.get("construct_scores", {})
    N = len(df)

    # Calculate theoretical upper bound K (A18-FIM-05): floor(N / min_sample_size)
    theoretical_max_k = max(1, math.floor(N / max(10, min_sample_size)))
    effective_max_segments = min(max_segments, theoretical_max_k)

    # Step 2: Build regression equation specs for ALL endogenous constructs
    paths = spec_dict.get("paths", [])
    preds_per_target: Dict[str, List[str]] = {}
    for p in paths:
        fc = p.get("from") or p.get("from_node")
        tc = p.get("to") or p.get("to_node")
        if tc not in preds_per_target:
            preds_per_target[tc] = []
        if fc not in preds_per_target[tc]:
            preds_per_target[tc].append(fc)

    if not preds_per_target:
        raise ValueError("Model contains no structural paths into endogenous constructs.")

    equations: List[Dict[str, Any]] = []
    for tc, preds in preds_per_target.items():
        y_target = np.asarray(scores.get(tc, np.zeros(N)), dtype=float)
        X_preds = np.column_stack([np.asarray(scores.get(p, np.zeros(N)), dtype=float) for p in preds])
        X_design = np.column_stack([np.ones(N), X_preds])

        equations.append({
            "target": tc,
            "predictors": preds,
            "y": y_target,
            "X_design": X_design,
        })

    # Step 3: Run simultaneous EM across S = min_segments .. effective_max_segments
    segment_evals: List[Dict[str, Any]] = []
    best_solutions_map: Dict[int, Dict[str, Any]] = {}
    total_steps = effective_max_segments - min_segments + 1

    for step_i, S in enumerate(range(min_segments, effective_max_segments + 1)):
        if cancel_event and cancel_event.is_set():
            raise RuntimeError("FIMIX-PLS cancelled by user.")

        sol = _fit_multi_equation_fimix_em(
            equations=equations,
            n_segments=S,
            n_samples=N,
            n_repetitions=n_repetitions,
            max_iter=max_iter,
            tol=tol,
            seed=(seed + S * 13) if seed is not None else None,
        )
        best_solutions_map[S] = sol

        lnL = sol["log_likelihood"]
        K = sol["free_parameters"]

        # Information criteria (A18-FIM-06)
        aic = -2.0 * lnL + 2.0 * K
        aic3 = -2.0 * lnL + 3.0 * K
        aic4 = -2.0 * lnL + 4.0 * K
        bic = -2.0 * lnL + K * math.log(N)
        caic = -2.0 * lnL + K * (math.log(N) + 1.0)
        mdl5 = -2.0 * lnL + 5.0 * K * math.log(N)

        # Normed Entropy EN
        post = sol["posteriors"]
        if S > 1:
            safe_post = np.maximum(1e-12, post)
            entropy = -float(np.sum(post * np.log(safe_post)))
            en_norm = 1.0 - (entropy / (N * math.log(S)))
            en_norm = max(0.0, min(1.0, float(en_norm)))
        else:
            en_norm = 1.0

        # Segment sample size checks
        seg_sizes = sol["segment_sizes"]
        has_small_segment = any(size < min_sample_size for size in seg_sizes)

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
            "AIC": round(aic, 2),
            "AIC3": round(aic3, 2),
            "AIC4": round(aic4, 2),
            "BIC": round(bic, 2),
            "CAIC": round(caic, 2),
            "MDL5": round(mdl5, 2),
            "EN": round(en_norm, 4),
            "segment_proportions": sol["proportions"],
            "segment_sizes": seg_sizes,
            "has_small_segment": has_small_segment,
            "converged": sol["converged"],
            "iterations": sol["iterations"],
            "local_optima_detected": sol.get("local_optima_detected", False),
        })

        if progress_callback:
            progress_callback(int(((step_i + 1) / total_steps) * 100))

    # Mark minimums for each criterion (A18-FIM-06)
    for crit in ["aic", "aic3", "aic4", "bic", "caic", "mdl5"]:
        min_val = min(s[crit] for s in segment_evals)
        for s in segment_evals:
            s[f"is_best_{crit}"] = bool(s[crit] == min_val)

    max_en = max(s["entropy_normalized"] for s in segment_evals if s["segments"] > 1) if any(s["segments"] > 1 for s in segment_evals) else 1.0
    for s in segment_evals:
        s["is_best_entropy"] = bool(s["entropy_normalized"] == max_en and s["segments"] > 1)

    # Segment retention recommendation (A18-FIM-07 Exhibit 5.3)
    best_aic3 = min(segment_evals, key=lambda s: s["aic3"])["segments"]
    best_caic = min(segment_evals, key=lambda s: s["caic"])["segments"]
    best_bic = min(segment_evals, key=lambda s: s["bic"])["segments"]

    if best_aic3 == best_caic:
        recommended_S = best_aic3
        decision_rationale = (
            f"Segment solution S={recommended_S} is consistently indicated by both AIC3 and CAIC. "
            f"This represents the optimal empirical trade-off between model fit and parsimony (Sarstedt et al. 2011)."
        )
    else:
        # Joint consideration of AIC3 and BIC
        recommended_S = best_caic if best_caic > 1 else best_bic
        decision_rationale = (
            f"AIC3 indicates S={best_aic3} (tendency to overestimate) while CAIC indicates S={best_caic} "
            f"and BIC indicates S={best_bic} (tendency to underestimate). "
            f"Following Exhibit 5.3 rules of thumb, consider S={recommended_S} jointly with segment sizes and entropy."
        )

    # Check entropy and segment size on recommended solution
    rec_eval = next(s for s in segment_evals if s["segments"] == recommended_S)
    if rec_eval["has_small_segment"]:
        decision_rationale += (
            f" WARNING: One or more segments in S={recommended_S} fall below the minimum statistical power sample size ({min_sample_size}). "
            f"A more parsimonious solution is strongly recommended."
        )

    rec_sol = best_solutions_map[recommended_S]
    rec_hard_assignments = [int(s) + 1 for s in np.argmax(rec_sol["posteriors"], axis=1)]

    # Aggregate R-squared for full sample
    full_sample_r2 = {
        tc: round(float(res_global.get("structural", {}).get("r_squared", {}).get(tc, 0.0)), 4)
        for tc in preds_per_target.keys()
    }

    return {
        "endogenous_constructs": list(preds_per_target.keys()),
        "n_samples": N,
        "min_sample_size_threshold": min_sample_size,
        "theoretical_max_segments": theoretical_max_k,
        "segment_retention_table": segment_evals,
        "recommended_segments": recommended_S,
        "recommendation": decision_rationale,
        "recommended_solution": {
            "segments": recommended_S,
            "proportions": rec_sol["proportions"],
            "segment_sizes": rec_sol["segment_sizes"],
            "equation_results": rec_sol["equation_results"],
            "r_squared_per_segment": rec_sol["r_squared_per_segment"],
            "weighted_r_squared": rec_sol["weighted_r_squared"],
            "full_sample_r_squared": full_sample_r2,
        },
        "case_assignments": rec_hard_assignments,
        "membership_probabilities": rec_sol["posteriors"].tolist(),
        "missing_warning": missing_warning,
        "criteria_performance_guide": {
            "AIC": "Weak; strong tendency to overestimate; use as upper limit",
            "AIC3": "Fair to good; works well in joint combination with CAIC and BIC",
            "AIC4": "Good; tends to both over- and underestimate",
            "BIC": "Good; tends to underestimate; evaluate jointly with AIC3",
            "CAIC": "Good; tends to underestimate; evaluate jointly with AIC3",
            "MDL5": "Weak; strong tendency to underestimate; use as lower limit",
            "EN": "Normed entropy (> 0.50 indicates clear-cut segmentation separation)",
        },
    }
