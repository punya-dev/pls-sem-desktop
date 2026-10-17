"""
Statistical Power and Minimum Sample Size Analysis (Section 24: SAM-01 to SAM-05).
Source of truth: Hair et al. (2017) Ch. 1 & Appendix C (Cohen 1992).
Implements:
- SAM-01: 10-times rule and inverse square root method
- SAM-02: Cohen (1992) Appendix C power table lookup and noncentral F power calculation
- SAM-03: G*Power multiple regression equivalence solver (solving for N, power, or detectable f^2)
- SAM-04/05: Pre-flight and post-hoc statistical power evaluation per endogenous construct
"""

from typing import List, Dict, Any, Optional, Tuple, Union
import math
import numpy as np
from scipy import stats
from scipy.optimize import brentq


def calculate_ten_times_rule(
    max_formative_indicators: int = 1,
    max_paths_into_construct: int = 1,
) -> Dict[str, Any]:
    """
    Computes minimum sample size according to the 10-times rule (SAM-01).
    n_min = 10 * max(max formative indicators in any construct, max paths into any construct).
    Also reports the inverse square root method for minimum path coefficient 0.10 and 0.20 (Kock & Hadaya 2018).
    """
    max_formative = max(1, max_formative_indicators)
    max_paths = max(1, max_paths_into_construct)
    n_ten_times = 10 * max(max_formative, max_paths)

    # Inverse square root method: N_min = (2.486 / |p_min|)^2 for power=0.80, alpha=0.05
    n_inv_sqrt_010 = int(math.ceil((2.486 / 0.10) ** 2))  # ~ 619
    n_inv_sqrt_020 = int(math.ceil((2.486 / 0.20) ** 2))  # ~ 155

    return {
        "ten_times_rule_min_n": n_ten_times,
        "max_formative_indicators": max_formative,
        "max_paths_into_construct": max_paths,
        "inverse_square_root_method": {
            "min_path_0_10": n_inv_sqrt_010,
            "min_path_0_20": n_inv_sqrt_020,
        },
        "note": (
            "The 10-times rule is a rough rule of thumb. Modern recommendations favor power analyses "
            "based on noncentral F distributions or the inverse square root method (Hair et al. 2017; Kock & Hadaya 2018)."
        ),
    }


def compute_statistical_power(
    n_samples: int,
    n_predictors: int,
    r_squared: Optional[float] = None,
    effect_size_f2: Optional[float] = None,
    alpha: float = 0.05,
) -> float:
    """
    Computes statistical power for linear multiple regression R^2 deviation using noncentral F distribution (SAM-02, SAM-03).
    lambda = f^2 * N
    """
    if effect_size_f2 is None:
        if r_squared is None or r_squared <= 0.0:
            return 0.0
        r2 = min(0.999, max(0.001, r_squared))
        f2 = r2 / (1.0 - r2)
    else:
        f2 = max(1e-4, effect_size_f2)

    u = max(1, n_predictors)
    v = max(1, n_samples - u - 1)
    ncp = f2 * n_samples  # noncentrality parameter lambda

    # Critical F value from central F distribution at alpha
    f_crit = stats.f.ppf(1.0 - alpha, dfn=u, dfd=v)
    # Power = 1 - CDF of noncentral F at critical value
    power = 1.0 - stats.ncf.cdf(f_crit, dfn=u, dfd=v, nc=ncp)
    return float(max(0.0, min(1.0, power)))


def solve_minimum_sample_size(
    n_predictors: int,
    r_squared: Optional[float] = None,
    effect_size_f2: Optional[float] = None,
    target_power: float = 0.80,
    alpha: float = 0.05,
) -> int:
    """
    Finds minimum N needed to achieve target statistical power using root-finding on noncentral F (SAM-02, SAM-03).
    """
    if effect_size_f2 is None:
        r2 = min(0.999, max(0.001, r_squared or 0.25))
        f2 = r2 / (1.0 - r2)
    else:
        f2 = max(1e-4, effect_size_f2)

    u = max(1, n_predictors)

    # Search range for N: from u + 2 to 10000
    low_n = u + 5
    high_n = 5000

    def obj(n_val):
        return compute_statistical_power(int(n_val), u, effect_size_f2=f2, alpha=alpha) - target_power

    if obj(high_n) < 0:
        return high_n

    try:
        sol = brentq(obj, low_n, high_n, xtol=1.0)
        return int(math.ceil(sol))
    except Exception:
        # Step search
        for n in range(low_n, high_n, 2):
            if compute_statistical_power(n, u, effect_size_f2=f2, alpha=alpha) >= target_power:
                return n
        return high_n


def get_cohen_appendix_c_table(
    target_power: float = 0.80,
    alpha: float = 0.05,
) -> Dict[str, Any]:
    """
    Reproduces textbook Appendix C (Cohen 1992):
    Minimum sample sizes needed for detecting minimum R^2 values of 0.10, 0.25, 0.50, and 0.75
    across 1 to 10 predictors for statistical power = 0.80 at alpha = 0.05 (SAM-02).
    """
    r2_values = [0.10, 0.25, 0.50, 0.75]
    table_rows = []

    for k in range(1, 11):
        row = {"predictors": k}
        for r2 in r2_values:
            n_req = solve_minimum_sample_size(
                n_predictors=k,
                r_squared=r2,
                target_power=target_power,
                alpha=alpha,
            )
            row[f"r2_{int(r2*100)}"] = n_req
        table_rows.append(row)

    return {
        "target_power": target_power,
        "significance_level": alpha,
        "table": table_rows,
        "reference": "Hair, Hult, Ringle, Sarstedt (2017) Appendix C & Cohen (1992).",
    }


def evaluate_model_power(
    n_samples: int,
    spec_dict: Dict[str, Any],
    r_squared_results: Optional[Dict[str, float]] = None,
    alpha: float = 0.05,
) -> Dict[str, Any]:
    """
    Evaluates achieved power per endogenous construct (SAM-04, SAM-05).
    """
    paths = spec_dict.get("paths", [])
    preds_per_target: Dict[str, List[str]] = {}
    for p in paths:
        fc = p.get("from") or p.get("from_node")
        tc = p.get("to") or p.get("to_node")
        if tc not in preds_per_target:
            preds_per_target[tc] = []
        preds_per_target[tc].append(fc)

    evaluations = []
    r2_map = r_squared_results or {}

    for target_c, preds in preds_per_target.items():
        k = len(preds)
        obs_r2 = r2_map.get(target_c)

        # Baseline check at benchmark R2 = 0.25 (medium effect)
        power_benchmark = compute_statistical_power(n_samples, k, r_squared=0.25, alpha=alpha)
        n_req_benchmark = solve_minimum_sample_size(k, r_squared=0.25, target_power=0.80, alpha=alpha)

        obs_power = None
        if obs_r2 is not None and obs_r2 > 0:
            obs_power = compute_statistical_power(n_samples, k, r_squared=obs_r2, alpha=alpha)

        adequate_power = (obs_power >= 0.80) if obs_power is not None else (power_benchmark >= 0.80)

        evaluations.append({
            "endogenous_construct": target_c,
            "n_predictors": k,
            "predictors": preds,
            "observed_r_squared": round(float(obs_r2), 4) if obs_r2 is not None else None,
            "observed_power": round(float(obs_power), 4) if obs_power is not None else None,
            "power_at_benchmark_r2_0_25": round(float(power_benchmark), 4),
            "n_required_for_power_80_percent": n_req_benchmark,
            "has_adequate_power": adequate_power,
        })

    return {
        "n_samples": n_samples,
        "alpha": alpha,
        "construct_evaluations": evaluations,
        "general_adequate": all(e["has_adequate_power"] for e in evaluations),
    }
