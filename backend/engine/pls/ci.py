"""
Bootstrap Confidence Interval Calculations (ci.py - BOO-13).
Implements:
- Percentile confidence intervals
- Bias-Corrected (BC) confidence intervals
- Bias-Corrected and Accelerated (BCa) confidence intervals using jackknife acceleration
"""

from typing import List, Dict, Any, Optional, Tuple, Union
import numpy as np
from scipy import stats


def percentile_ci(
    sample_dist: np.ndarray,
    alpha: float = 0.05,
    tails: str = "two",
) -> Tuple[float, float]:
    """Computes standard percentile bootstrap confidence interval."""
    if len(sample_dist) == 0:
        return 0.0, 0.0
    if tails == "one":
        # One-tailed 1 - alpha level (e.g., lower bound at alpha, or upper at 1 - alpha)
        low = float(np.percentile(sample_dist, alpha * 100))
        high = float(np.percentile(sample_dist, (1 - alpha) * 100))
    else:
        low = float(np.percentile(sample_dist, (alpha / 2.0) * 100))
        high = float(np.percentile(sample_dist, (1 - alpha / 2.0) * 100))
    return low, high


def bias_corrected_ci(
    original_val: float,
    sample_dist: np.ndarray,
    alpha: float = 0.05,
    tails: str = "two",
) -> Tuple[float, float]:
    """Computes Bias-Corrected (BC) bootstrap confidence interval."""
    B = len(sample_dist)
    if B == 0:
        return 0.0, 0.0

    prop_less = np.sum(sample_dist < original_val) / B
    # Clamp to avoid inf in norm.ppf
    prop_less = np.clip(prop_less, 1.0 / (2 * B), 1.0 - 1.0 / (2 * B))
    z0 = float(stats.norm.ppf(prop_less))

    if tails == "one":
        z_alpha_low = stats.norm.ppf(alpha)
        z_alpha_high = stats.norm.ppf(1.0 - alpha)
        pct_low = float(stats.norm.cdf(2 * z0 + z_alpha_low)) * 100
        pct_high = float(stats.norm.cdf(2 * z0 + z_alpha_high)) * 100
    else:
        z_alpha = stats.norm.ppf(alpha / 2.0)
        z_one_minus_alpha = stats.norm.ppf(1.0 - alpha / 2.0)
        pct_low = float(stats.norm.cdf(2 * z0 + z_alpha)) * 100
        pct_high = float(stats.norm.cdf(2 * z0 + z_one_minus_alpha)) * 100

    pct_low = np.clip(pct_low, 0.0, 100.0)
    pct_high = np.clip(pct_high, 0.0, 100.0)

    low = float(np.percentile(sample_dist, pct_low))
    high = float(np.percentile(sample_dist, pct_high))
    return low, high


def bca_ci(
    original_val: float,
    sample_dist: np.ndarray,
    jackknife_vals: Optional[np.ndarray] = None,
    alpha: float = 0.05,
    tails: str = "two",
) -> Tuple[float, float]:
    """
    Computes Bias-Corrected and Accelerated (BCa) bootstrap confidence interval.
    If jackknife_vals is None or degenerate, falls back to bias_corrected_ci.
    """
    B = len(sample_dist)
    if B == 0:
        return 0.0, 0.0

    prop_less = np.sum(sample_dist < original_val) / B
    prop_less = np.clip(prop_less, 1.0 / (2 * B), 1.0 - 1.0 / (2 * B))
    z0 = float(stats.norm.ppf(prop_less))

    # Calculate acceleration parameter a from jackknife estimates
    a = 0.0
    if jackknife_vals is not None and len(jackknife_vals) > 1:
        j_mean = np.mean(jackknife_vals)
        diff = j_mean - jackknife_vals
        num = np.sum(diff ** 3)
        denom = 6.0 * (np.sum(diff ** 2) ** 1.5)
        if abs(denom) > 1e-12:
            a = float(num / denom)

    # Adjust percentiles with both bias z0 and acceleration a
    def adjust_p(z_alpha_val: float) -> float:
        denom = 1.0 - a * (z0 + z_alpha_val)
        if abs(denom) < 1e-6:
            denom = 1e-6 if denom >= 0 else -1e-6
        arg = z0 + (z0 + z_alpha_val) / denom
        return float(stats.norm.cdf(arg)) * 100.0

    if tails == "one":
        pct_low = adjust_p(stats.norm.ppf(alpha))
        pct_high = adjust_p(stats.norm.ppf(1.0 - alpha))
    else:
        pct_low = adjust_p(stats.norm.ppf(alpha / 2.0))
        pct_high = adjust_p(stats.norm.ppf(1.0 - alpha / 2.0))

    pct_low = np.clip(pct_low, 0.0, 100.0)
    pct_high = np.clip(pct_high, 0.0, 100.0)

    low = float(np.percentile(sample_dist, pct_low))
    high = float(np.percentile(sample_dist, pct_high))
    return low, high


def compute_all_confidence_intervals(
    original_val: float,
    sample_dist: np.ndarray,
    jackknife_vals: Optional[np.ndarray] = None,
    alpha: float = 0.05,
    tails: str = "two",
) -> Dict[str, Tuple[float, float]]:
    """Returns percentile, bias_corrected, and bca intervals side-by-side."""
    p_low, p_high = percentile_ci(sample_dist, alpha=alpha, tails=tails)
    bc_low, bc_high = bias_corrected_ci(original_val, sample_dist, alpha=alpha, tails=tails)
    bca_low, bca_high = bca_ci(original_val, sample_dist, jackknife_vals=jackknife_vals, alpha=alpha, tails=tails)

    return {
        "percentile": (p_low, p_high),
        "bias_corrected": (bc_low, bc_high),
        "bca": (bca_low, bca_high),
    }
