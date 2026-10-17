"""
Gaussian Copula Endogeneity Analysis (Section 25: X-A, X-01).
Source of truth: Park & Gupta (2012) & Hult et al. (2018).
Tests for endogeneity without instrumental variables by constructing Gaussian copula terms
from non-normal latent construct distributions.
"""

from typing import List, Dict, Any, Optional, Tuple, Union
import numpy as np
import pandas as pd
from scipy import stats

from core.settings_schema import PipelineSettings
from core.rng import spawn_seeds, resample_indices
from engine.pls.algorithm import run_pipeline


def test_non_normality(scores: np.ndarray) -> Dict[str, Any]:
    """
    Tests whether the construct score distribution is significantly non-normal.
    Gaussian copulas require non-normal regressors (Park & Gupta 2012).
    """
    N = len(scores)
    # Shapiro-Wilk test (N <= 5000)
    if N <= 5000:
        stat, p_val = stats.shapiro(scores)
        test_name = "Shapiro-Wilk"
    else:
        stat, p_val = stats.kstest(scores, 'norm', args=(np.mean(scores), np.std(scores, ddof=0) or 1.0))
        test_name = "Kolmogorov-Smirnov"

    skewness = float(stats.skew(scores))
    kurtosis = float(stats.kurtosis(scores))

    is_non_normal = (p_val < 0.05) or (abs(skewness) > 1.0) or (abs(kurtosis) > 1.0)

    return {
        "test": test_name,
        "statistic": round(float(stat), 4),
        "p_value": round(float(p_val), 4),
        "skewness": round(skewness, 4),
        "kurtosis": round(kurtosis, 4),
        "is_non_normal": bool(is_non_normal),
    }


def compute_copula_term(scores: np.ndarray) -> np.ndarray:
    """
    Constructs Gaussian copula term c_P = Phi^-1(F_hat_P(P)).
    F_hat_P is the empirical CDF: rank(P) / (N + 1).
    """
    N = len(scores)
    ranks = stats.rankdata(scores, method='average')
    empirical_cdf = ranks / (N + 1.0)
    # Clip to avoid infinite values at boundaries
    empirical_cdf = np.clip(empirical_cdf, 1e-6, 1.0 - 1e-6)
    copula_term = stats.norm.ppf(empirical_cdf)
    return copula_term


def analyze_gaussian_copula(
    df: pd.DataFrame,
    spec: Union[Dict[str, Any], Any],
    candidate_predictor: str,
    target_construct: str,
    n_boot: int = 500,
    seed: Optional[int] = 42,
    alpha: float = 0.05,
    settings: Optional[PipelineSettings] = None,
    cancel_event: Optional[Any] = None,
) -> Dict[str, Any]:
    """
    Executes Gaussian Copula Endogeneity Analysis (X-A, X-01).
    """
    spec_dict = spec.model_dump(by_alias=True) if hasattr(spec, "model_dump") else (spec if isinstance(spec, dict) else {})
    cfg = settings or PipelineSettings()

    # 1. Global PLS run to get scores
    res_base = run_pipeline(df, spec_dict, cfg)
    scores = res_base.get("construct_scores", {})
    N = len(df)

    p_scores = np.asarray(scores.get(candidate_predictor, np.zeros(N)), dtype=float)
    y_scores = np.asarray(scores.get(target_construct, np.zeros(N)), dtype=float)

    # Find all predictors of target
    paths = spec_dict.get("paths", [])
    pred_cids = [p.get("from") or p.get("from_node") for p in paths if (p.get("to") or p.get("to_node")) == target_construct]

    if candidate_predictor not in pred_cids:
        raise ValueError(f"Candidate '{candidate_predictor}' is not a direct predictor of '{target_construct}'.")

    # 2. Check non-normality prerequisite
    norm_res = test_non_normality(p_scores)
    if not norm_res["is_non_normal"]:
        return {
            "candidate_predictor": candidate_predictor,
            "target_construct": target_construct,
            "applicable": False,
            "na_reason": (
                f"Predictor '{candidate_predictor}' distribution is not significantly non-normal "
                f"(p = {norm_res['p_value']}). The Gaussian copula method strictly requires non-normal regressors (Park & Gupta 2012)."
            ),
            "normality_test": norm_res,
        }

    # 3. Base OLS regression of target on predictors
    X_base = np.column_stack([np.asarray(scores[c], dtype=float) for c in pred_cids])
    c_idx = pred_cids.index(candidate_predictor)

    coef_base, _, _, _ = np.linalg.lstsq(X_base, y_scores, rcond=None)
    orig_beta = float(coef_base[c_idx])

    # 4. Construct copula term and estimate extended model
    c_copula = compute_copula_term(p_scores)
    X_ext = np.column_stack([X_base, c_copula])

    coef_ext, _, _, _ = np.linalg.lstsq(X_ext, y_scores, rcond=None)
    beta_with_copula = float(coef_ext[c_idx])
    copula_coef = float(coef_ext[-1])

    # 5. Bootstrap copula model to assess copula significance
    seeds = spawn_seeds(seed or 42, n_boot)
    boot_copula_coefs = np.zeros(n_boot, dtype=float)
    boot_beta_with = np.zeros(n_boot, dtype=float)

    for b in range(n_boot):
        if cancel_event and cancel_event.is_set():
            raise RuntimeError("Gaussian copula analysis cancelled by user.")
        b_rng = np.random.default_rng(seeds[b])
        resamp_idx = resample_indices(N, b_rng)

        # In each replicate: re-estimate PLS, recompute copula, re-estimate regression
        df_b = df.iloc[resamp_idx]
        res_b = run_pipeline(df_b, spec_dict, cfg)
        scores_b = res_b.get("construct_scores", {})

        p_sc_b = np.asarray(scores_b.get(candidate_predictor, np.zeros(N)), dtype=float)
        y_sc_b = np.asarray(scores_b.get(target_construct, np.zeros(N)), dtype=float)
        X_b_base = np.column_stack([np.asarray(scores_b[c], dtype=float) for c in pred_cids])

        cop_b = compute_copula_term(p_sc_b)
        X_b_ext = np.column_stack([X_b_base, cop_b])

        try:
            b_coefs, _, _, _ = np.linalg.lstsq(X_b_ext, y_sc_b, rcond=None)
            boot_copula_coefs[b] = float(b_coefs[-1])
            boot_beta_with[b] = float(b_coefs[c_idx])
        except Exception:
            boot_copula_coefs[b] = copula_coef
            boot_beta_with[b] = beta_with_copula

    se_copula = float(np.std(boot_copula_coefs, ddof=1))
    t_copula = (copula_coef / se_copula) if se_copula > 1e-12 else 0.0
    p_copula = 2.0 * (1.0 - stats.norm.cdf(abs(t_copula)))

    ci_low = float(np.percentile(boot_copula_coefs, 100.0 * (alpha / 2.0)))
    ci_high = float(np.percentile(boot_copula_coefs, 100.0 * (1.0 - alpha / 2.0)))

    endogeneity_detected = bool(p_copula < alpha)

    if endogeneity_detected:
        interpretation = (
            f"Endogeneity detected: The Gaussian copula term is statistically significant "
            f"(gamma = {round(copula_coef, 4)}, p = {round(p_copula, 4)}). "
            f"The original path coefficient ({round(orig_beta, 4)}) is biased; "
            f"the copula-corrected path is {round(beta_with_copula, 4)} (Hult et al. 2018)."
        )
    else:
        interpretation = (
            f"No endogeneity detected: The Gaussian copula term is not statistically significant "
            f"(gamma = {round(copula_coef, 4)}, p = {round(p_copula, 4)}). "
            f"The original estimate ({round(orig_beta, 4)}) does not show evidence of endogeneity bias (Park & Gupta 2012)."
        )

    return {
        "candidate_predictor": candidate_predictor,
        "target_construct": target_construct,
        "applicable": True,
        "normality_test": norm_res,
        "original_path_coefficient": round(orig_beta, 4),
        "copula_corrected_path": round(beta_with_copula, 4),
        "copula_term": {
            "coefficient": round(copula_coef, 4),
            "standard_error": round(se_copula, 4),
            "t_statistic": round(float(t_copula), 4),
            "p_value": round(float(p_copula), 4),
            "ci_lower": round(ci_low, 4),
            "ci_upper": round(ci_high, 4),
            "is_significant": endogeneity_detected,
        },
        "endogeneity_detected": endogeneity_detected,
        "interpretation": interpretation,
    }
