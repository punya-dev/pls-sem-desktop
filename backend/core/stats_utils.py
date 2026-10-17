"""
Shared Statistical Utilities for PLS-SEM.
Includes weighted moments, pairwise matrix calculations, skewness/kurtosis,
jackknife, empirical CDF, normal quantiles, non-central F distribution solver,
bootstrap interval helpers (Percentile, BC, BCa), and Mann-Whitney prob_greater.
"""

from typing import List, Tuple, Optional, Dict, Any, Union
import numpy as np
from scipy import stats, optimize


def weighted_mean(x: np.ndarray, w: Optional[np.ndarray] = None, axis: int = 0) -> np.ndarray:
    """Computes weighted mean. If w is None, returns standard arithmetic mean."""
    if w is None:
        return np.mean(x, axis=axis)
    w_sum = np.sum(w, axis=axis)
    if axis == 0:
        return np.sum(x * w[:, None] if x.ndim > 1 else x * w, axis=0) / w_sum
    return np.sum(x * w, axis=axis) / w_sum


def weighted_std(x: np.ndarray, w: Optional[np.ndarray] = None, ddof: int = 0, axis: int = 0) -> np.ndarray:
    """Computes weighted standard deviation."""
    if w is None:
        return np.std(x, ddof=ddof, axis=axis)
    w_norm = w / np.sum(w)
    mean = weighted_mean(x, w, axis=axis)
    diff = x - mean
    var = np.sum(w_norm[:, None] * (diff ** 2) if x.ndim > 1 else w_norm * (diff ** 2), axis=axis)
    if ddof > 0:
        # Effective N sample correction: N_eff = (sum w)^2 / sum(w^2)
        n_eff = (np.sum(w) ** 2) / np.sum(w ** 2)
        if n_eff > ddof:
            var = var * (n_eff / (n_eff - ddof))
    return np.sqrt(np.maximum(0.0, var))


def weighted_corr(x: np.ndarray, y: np.ndarray, w: Optional[np.ndarray] = None) -> float:
    """Computes weighted Pearson correlation between 1D vectors x and y."""
    if w is None:
        return float(np.corrcoef(x, y)[0, 1])
    w_norm = w / np.sum(w)
    mx = float(np.sum(w_norm * x))
    my = float(np.sum(w_norm * y))
    vx = float(np.sum(w_norm * ((x - mx) ** 2)))
    vy = float(np.sum(w_norm * ((y - my) ** 2)))
    if vx <= 1e-12 or vy <= 1e-12:
        return 0.0
    cov = float(np.sum(w_norm * (x - mx) * (y - my)))
    return float(cov / np.sqrt(vx * vy))


def pairwise_correlation_matrix(df: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """
    Computes pairwise Pearson correlation matrix and pairwise sample size matrix N.
    df: 2D array (N_samples x K_variables) with possible NaNs.
    """
    n_vars = df.shape[1]
    R = np.eye(n_vars, dtype=float)
    N = np.zeros((n_vars, n_vars), dtype=int)

    for i in range(n_vars):
        N[i, i] = int(np.sum(~np.isnan(df[:, i])))
        for j in range(i + 1, n_vars):
            mask = ~np.isnan(df[:, i]) & ~np.isnan(df[:, j])
            n_ij = int(np.sum(mask))
            N[i, j] = n_ij
            N[j, i] = n_ij
            if n_ij >= 3:
                r_val = float(np.corrcoef(df[mask, i], df[mask, j])[0, 1])
                if np.isnan(r_val):
                    r_val = 0.0
                R[i, j] = r_val
                R[j, i] = r_val
            else:
                R[i, j] = 0.0
                R[j, i] = 0.0
    return R, N


def nearest_psd(A: np.ndarray, epsilon: float = 1e-6) -> np.ndarray:
    """Project a symmetric matrix to the nearest positive semi-definite matrix."""
    B = (A + A.T) / 2.0
    eigval, eigvec = np.linalg.eigh(B)
    eigval = np.maximum(eigval, epsilon)
    D = np.diag(eigval)
    A_psd = eigvec @ D @ eigvec.T
    # Restore unit diagonal for correlation matrices
    d = np.sqrt(np.diag(A_psd))
    d[d == 0] = 1.0
    return A_psd / np.outer(d, d)


def fisher_pearson_skewness(x: np.ndarray) -> float:
    """Computes sample skewness with sample size correction (Fisher-Pearson)."""
    return float(stats.skew(x, bias=False)) if len(x) >= 3 else 0.0


def fisher_pearson_kurtosis(x: np.ndarray) -> float:
    """Computes excess sample kurtosis with sample size correction (Fisher-Pearson, normal=0)."""
    return float(stats.kurtosis(x, bias=False)) if len(x) >= 4 else 0.0


def jackknife_estimates(data: np.ndarray, estimator_fn: Any) -> np.ndarray:
    """
    Leave-one-out jackknife computation.
    Returns 2D array of estimates (N_samples x N_parameters).
    """
    n = data.shape[0]
    estimates = []
    for i in range(n):
        subset = np.delete(data, i, axis=0)
        est = estimator_fn(subset)
        estimates.append(est)
    return np.array(estimates)


def bca_confidence_interval(
    original_val: float,
    boot_dist: np.ndarray,
    jackknife_dist: Optional[np.ndarray] = None,
    alpha: float = 0.05,
) -> Tuple[float, float]:
    """
    Calculates Bias-Corrected and Accelerated (BCa) bootstrap confidence intervals.
    If jackknife_dist is None, falls back to plain bias-corrected interval (acceleration a = 0).
    """
    B = len(boot_dist)
    if B < 10:
        return float(np.percentile(boot_dist, 100 * (alpha / 2))), float(np.percentile(boot_dist, 100 * (1 - alpha / 2)))

    # 1. Bias correction z0
    p_below = np.mean(boot_dist < original_val)
    # Clip to avoid infinite z0
    p_below = max(1e-6, min(p_below, 1.0 - 1e-6))
    z0 = float(stats.norm.ppf(p_below))

    # 2. Acceleration parameter a
    a = 0.0
    if jackknife_dist is not None and len(jackknife_dist) >= 3:
        theta_bar = np.mean(jackknife_dist)
        diff = theta_bar - jackknife_dist
        sum_cube = np.sum(diff ** 3)
        sum_sq = np.sum(diff ** 2)
        if sum_sq > 1e-12:
            a = float(sum_cube / (6.0 * (sum_sq ** 1.5)))

    # 3. Adjusted percentiles
    z_alpha_low = stats.norm.ppf(alpha / 2.0)
    z_alpha_high = stats.norm.ppf(1.0 - alpha / 2.0)

    denom_low = 1.0 - a * (z0 + z_alpha_low)
    denom_high = 1.0 - a * (z0 + z_alpha_high)

    if abs(denom_low) < 1e-6 or abs(denom_high) < 1e-6:
        # Fall back to percentile
        return float(np.percentile(boot_dist, 100 * (alpha / 2))), float(np.percentile(boot_dist, 100 * (1 - alpha / 2)))

    alpha_low_adj = stats.norm.cdf(z0 + (z0 + z_alpha_low) / denom_low)
    alpha_high_adj = stats.norm.cdf(z0 + (z0 + z_alpha_high) / denom_high)

    alpha_low_adj = max(0.0001, min(0.9999, alpha_low_adj))
    alpha_high_adj = max(0.0001, min(0.9999, alpha_high_adj))

    ci_low = float(np.percentile(boot_dist, 100.0 * alpha_low_adj))
    ci_high = float(np.percentile(boot_dist, 100.0 * alpha_high_adj))

    if ci_low > ci_high:
        ci_low, ci_high = ci_high, ci_low

    return ci_low, ci_high


def prob_greater(sample1: np.ndarray, sample2: np.ndarray) -> float:
    """
    Computes P(sample1 <= sample2) for PLS-MGA (Henseler 2009).
    Uses efficient sorted search instead of B1 x B2 nested loops.
    """
    s1 = np.sort(sample1)
    s2 = np.sort(sample2)
    # For each element in s1, count how many elements in s2 are >= it
    indices = np.searchsorted(s2, s1, side='left')
    count = np.sum(len(s2) - indices)
    return float(count / (len(s1) * len(s2)))


def noncentral_f_power(k_predictors: int, n_samples: int, r2: float, alpha: float = 0.05) -> float:
    """
    Computes statistical power for linear regression R^2 using the non-central F distribution.
    Effect size f^2 = R^2 / (1 - R^2).
    Non-centrality parameter lambda = f^2 * N.
    """
    if r2 >= 1.0:
        return 1.0
    if r2 <= 0.0 or n_samples <= k_predictors + 1:
        return alpha

    df1 = k_predictors
    df2 = n_samples - k_predictors - 1
    f2 = r2 / (1.0 - r2)
    nc = f2 * n_samples

    f_crit = stats.f.ppf(1.0 - alpha, df1, df2)
    power = 1.0 - stats.ncf.cdf(f_crit, df1, df2, nc)
    return float(np.clip(power, 0.0, 1.0))


def solve_minimum_sample_size(k_predictors: int, min_r2: float, target_power: float = 0.80, alpha: float = 0.05) -> int:
    """
    Finds minimum N needed to achieve target_power given k_predictors and min_r2.
    """
    for n in range(k_predictors + 2, 5000):
        pwr = noncentral_f_power(k_predictors, n, min_r2, alpha=alpha)
        if pwr >= target_power:
            return n
    return 5000
