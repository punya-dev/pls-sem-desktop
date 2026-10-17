"""
Bootstrap Contrasts and Difference Tests Module (STR-04).
Implements linear parameter contrasts:
- General contrast: theta_c = sum c_p * theta_p
- Path difference test: beta_1 - beta_2
- Specific indirect effect difference tests
- Paired R2 model comparison tests
"""

from typing import List, Dict, Any, Optional, Tuple
import numpy as np
from scipy import stats
from engine.pls.ci import compute_all_confidence_intervals


def compute_contrast(
    original_parameters: Dict[str, float],
    samples_matrix: Any,
    contrast_coefficients: Dict[str, float],
    parameter_names: Optional[List[str]] = None,
    alpha: float = 0.05,
    tails: str = "two",
    ci_method: str = "percentile",
) -> Dict[str, Any]:
    """
    Computes a linear contrast theta_c = sum c_p * theta_p across stored bootstrap samples.
    """
    # If samples_matrix is a numpy 2D array, convert to dictionary by parameter name
    if isinstance(samples_matrix, np.ndarray):
        if parameter_names is None:
            if len(original_parameters) == samples_matrix.shape[1]:
                parameter_names = list(original_parameters.keys())
            else:
                raise ValueError("parameter_names must be provided when samples_matrix is a numpy array.")
        samples_dict = {
            name: samples_matrix[:, i].tolist() for i, name in enumerate(parameter_names)
        }
        samples_matrix = samples_dict

    # 1. Original contrast value
    orig_c = 0.0
    for p_name, weight in contrast_coefficients.items():
        val = original_parameters.get(p_name, 0.0)
        orig_c += weight * val

    # 2. Bootstrap contrast distribution
    # Determine sample count B
    param_keys = list(contrast_coefficients.keys())
    if not param_keys or any(k not in samples_matrix for k in param_keys):
        missing = [k for k in param_keys if k not in samples_matrix]
        raise ValueError(f"Parameters {missing} not found in bootstrap samples.")

    B = min(len(samples_matrix[k]) for k in param_keys)
    if B == 0:
        raise ValueError("No bootstrap samples available for contrast calculation.")

    contrast_samples = np.zeros(B, dtype=float)
    for p_name, weight in contrast_coefficients.items():
        arr = np.array(samples_matrix[p_name][:B], dtype=float)
        contrast_samples += weight * arr

    se = float(np.std(contrast_samples, ddof=1))
    mean_val = float(np.mean(contrast_samples))
    t_stat = float(orig_c / se) if se > 1e-9 else 0.0

    # Non-parametric percentile p-value: 2 * min(P(theta* <= 0), P(theta* >= 0))
    p_le_zero = np.mean(contrast_samples <= 0)
    p_ge_zero = np.mean(contrast_samples >= 0)
    if tails == "one":
        p_val = float(min(p_le_zero, p_ge_zero))
    else:
        p_val = float(min(1.0, 2.0 * min(p_le_zero, p_ge_zero)))

    # Compute confidence intervals
    cis = compute_all_confidence_intervals(
        original_val=orig_c,
        sample_dist=contrast_samples,
        alpha=alpha,
        tails=tails,
    )
    chosen_ci = cis.get(ci_method, cis["percentile"])

    sig = "***" if p_val < 0.001 else ("**" if p_val < 0.01 else ("*" if p_val < alpha else "ns"))

    return {
        "contrast_coefficients": contrast_coefficients,
        "original": orig_c,
        "mean": mean_val,
        "se": se,
        "t_stat": t_stat,
        "p_value": p_val,
        "ci_low": chosen_ci[0],
        "ci_high": chosen_ci[1],
        "confidence_intervals": cis,
        "significance": sig,
        "n_samples": B,
    }


def path_difference_test(
    original_parameters: Dict[str, float],
    samples_matrix: Dict[str, List[float]],
    path1: str,
    path2: str,
    alpha: float = 0.05,
) -> Dict[str, Any]:
    """
    Tests the null hypothesis that beta_1 = beta_2 (beta_1 - beta_2 = 0).
    Note: Both paths should ideally share the same target construct or metric scale.
    """
    p1_key = path1 if path1.startswith("path:") else f"path:{path1}"
    p2_key = path2 if path2.startswith("path:") else f"path:{path2}"

    contrast_weights = {p1_key: 1.0, p2_key: -1.0}
    res = compute_contrast(
        original_parameters=original_parameters,
        samples_matrix=samples_matrix,
        contrast_coefficients=contrast_weights,
        alpha=alpha,
    )
    res["path_1"] = path1
    res["path_2"] = path2
    return res
