"""
Multigroup Analysis (PLS-MGA) (Section 20: MGA-01 to MGA-09).
Source of truth: Hair et al. (2017) Ch. 8.
Implements:
1. Parametric test (Keil et al. 2000)
2. Welch-Satterthwaite test (unequal variances)
3. Permutation test (Chin & Dibbern 2010)
4. Henseler's PLS-MGA test (Henseler et al. 2009)
"""

from typing import List, Dict, Any, Optional, Tuple, Union
import math
import numpy as np
import pandas as pd
from scipy import stats

from core.settings_schema import PipelineSettings
from core.rng import spawn_seeds
from engine.pls.algorithm import run_pipeline
from engine.pls.bootstrap import ParallelBootstrapper


def compute_parametric_test(
    beta1: float,
    beta2: float,
    se1: float,
    se2: float,
    n1: int,
    n2: int,
) -> Dict[str, Any]:
    """
    Parametric test for group differences assuming equal variances (Keil et al. 2000) (MGA-05).
    """
    diff = beta1 - beta2
    df = n1 + n2 - 2
    pooled_var = (((n1 - 1) ** 2 / df) * (se1 ** 2)) + (((n2 - 1) ** 2 / df) * (se2 ** 2))
    se_diff = math.sqrt(max(1e-12, pooled_var * (1.0 / n1 + 1.0 / n2)))

    t_stat = diff / se_diff if se_diff > 1e-12 else 0.0
    p_val = 2.0 * (1.0 - stats.t.cdf(abs(t_stat), df=df))

    return {
        "t_statistic": round(float(t_stat), 4),
        "degrees_of_freedom": int(df),
        "p_value": round(float(p_val), 4),
        "is_significant": bool(p_val < 0.05),
    }


def compute_welch_satterthwaite_test(
    beta1: float,
    beta2: float,
    se1: float,
    se2: float,
    n1: int,
    n2: int,
) -> Dict[str, Any]:
    """
    Welch-Satterthwaite test for group differences assuming unequal variances (MGA-06).
    """
    diff = beta1 - beta2
    term1 = ((n1 - 1.0) / n1) * (se1 ** 2)
    term2 = ((n2 - 1.0) / n2) * (se2 ** 2)
    denom_var = term1 + term2

    t_stat = diff / math.sqrt(max(1e-12, denom_var))

    # Degrees of freedom approximation
    df_denom = (((n1 - 1.0) / (n1 ** 2)) * (se1 ** 4)) + (((n2 - 1.0) / (n2 ** 2)) * (se2 ** 4))
    if df_denom > 1e-12:
        df = max(1.0, (denom_var ** 2) / df_denom - 2.0)
    else:
        df = float(n1 + n2 - 2)

    p_val = 2.0 * (1.0 - stats.t.cdf(abs(t_stat), df=df))

    return {
        "t_statistic": round(float(t_stat), 4),
        "degrees_of_freedom": round(float(df), 2),
        "p_value": round(float(p_val), 4),
        "is_significant": bool(p_val < 0.05),
    }


def compute_henseler_pls_mga(
    samples_g1: np.ndarray,
    samples_g2: np.ndarray,
) -> Dict[str, Any]:
    """
    Henseler's non-parametric PLS-MGA test (Henseler et al. 2009) (MGA-08).
    Evaluates P(theta_1* <= theta_2*).
    Significant at alpha=0.05 if p < 0.05 or p > 0.95.
    """
    # Sort samples for fast rank-based comparison
    B1 = len(samples_g1)
    B2 = len(samples_g2)

    # Vectorized count: how many (theta_1 <= theta_2)
    # Using searchsorted on sorted arrays
    s1 = np.sort(samples_g1)
    s2 = np.sort(samples_g2)

    # For each element in s2, count how many elements in s1 are <= s2
    counts = np.searchsorted(s1, s2, side='right')
    total_le = np.sum(counts)

    p_one_tailed = float(total_le) / float(B1 * B2)
    # Two-sided p-value
    p_two_tailed = 2.0 * min(p_one_tailed, 1.0 - p_one_tailed)

    return {
        "p_value_one_tailed": round(float(p_one_tailed), 4),
        "p_value_two_tailed": round(float(p_two_tailed), 4),
        "is_significant": bool(p_two_tailed < 0.05),
    }


def analyze_mga(
    df: pd.DataFrame,
    spec: Union[Dict[str, Any], Any],
    group_col: str,
    group_values: Optional[Tuple[Any, Any]] = None,
    n_boot: int = 500,
    n_permutations: int = 500,
    seed: Optional[int] = 42,
    alpha: float = 0.05,
    settings: Optional[PipelineSettings] = None,
    progress_callback: Optional[Any] = None,
    cancel_event: Optional[Any] = None,
) -> Dict[str, Any]:
    """
    Executes comprehensive Multigroup Analysis (MGA-01 to MGA-09).
    """
    spec_dict = spec.model_dump(by_alias=True) if hasattr(spec, "model_dump") else (spec if isinstance(spec, dict) else {})
    cfg = settings or PipelineSettings()

    # 1. Group definition & sample size checks (MGA-01, MGA-02)
    if group_values is None:
        unique_groups = df[group_col].dropna().unique()
        if len(unique_groups) < 2:
            raise ValueError(f"Group column '{group_col}' must have at least 2 distinct categories.")
        g1_val, g2_val = unique_groups[0], unique_groups[1]
    else:
        g1_val, g2_val = group_values

    df_g1 = df[df[group_col] == g1_val].copy()
    df_g2 = df[df[group_col] == g2_val].copy()

    n1 = len(df_g1)
    n2 = len(df_g2)

    warnings: List[str] = []
    ratio = max(n1, n2) / max(1, min(n1, n2))
    if ratio > 3.0:
        warnings.append(f"Group sample size ratio is {round(ratio, 1)}:1 (> 3:1). Extreme imbalance reduces statistical power.")

    if n1 < 10 or n2 < 10:
        warnings.append("One or both groups have N < 10, violating minimum sample size requirements for reliable PLS-SEM estimation.")

    # 2. Estimate base models for Group 1 and Group 2
    res_g1 = run_pipeline(df_g1, spec_dict, cfg)
    res_g2 = run_pipeline(df_g2, spec_dict, cfg)

    paths_g1 = res_g1.get("structural", {}).get("path_coefficients", {})
    paths_g2 = res_g2.get("structural", {}).get("path_coefficients", {})

    # 3. Bootstrapping Group 1 and Group 2
    booter = ParallelBootstrapper()
    boot_g1 = booter.run(
        data=df_g1,
        model_spec=spec_dict,
        n_boot=n_boot,
        seed=seed,
        scheme=cfg.inner_weighting,
        mode="basic",
        sign_change="none",
        alpha=alpha,
        cancel_event=cancel_event,
    )

    boot_g2 = booter.run(
        data=df_g2,
        model_spec=spec_dict,
        n_boot=n_boot,
        seed=(seed + 1000) if seed is not None else None,
        scheme=cfg.inner_weighting,
        mode="basic",
        sign_change="none",
        alpha=alpha,
        cancel_event=cancel_event,
    )

    p_summary_g1 = boot_g1.get("parameter_summary", {})
    p_summary_g2 = boot_g2.get("parameter_summary", {})
    samples_mat_g1 = boot_g1.get("samples_matrix")
    samples_mat_g2 = boot_g2.get("samples_matrix")
    p_names = boot_g1.get("parameter_names", [])

    # 4. Permutation test for all structural paths (MGA-07)
    df_pooled = pd.concat([df_g1, df_g2], axis=0).reset_index(drop=True)
    N_tot = len(df_pooled)

    paths_list = spec_dict.get("paths", [])
    path_keys = []
    for p in paths_list:
        fc = p.get("from") or p.get("from_node")
        tc = p.get("to") or p.get("to_node")
        path_keys.append((fc, tc, f"path:{fc}->{tc}"))

    perm_diffs: Dict[str, np.ndarray] = {pk: np.zeros(n_permutations, dtype=float) for _, _, pk in path_keys}
    p_seeds = spawn_seeds((seed or 42) + 2000, n_permutations)

    for p_idx in range(n_permutations):
        if cancel_event and cancel_event.is_set():
            raise RuntimeError("MGA permutation test cancelled by user.")
        p_rng = np.random.default_rng(p_seeds[p_idx])
        perm_idx = p_rng.permutation(N_tot)

        ps_g1 = df_pooled.iloc[perm_idx[:n1]]
        ps_g2 = df_pooled.iloc[perm_idx[n1:]]

        r_pg1 = run_pipeline(ps_g1, spec_dict, cfg)
        r_pg2 = run_pipeline(ps_g2, spec_dict, cfg)

        pp1 = r_pg1.get("structural", {}).get("path_coefficients", {})
        pp2 = r_pg2.get("structural", {}).get("path_coefficients", {})

        for fc, tc, pk in path_keys:
            b1_star = float(pp1.get(tc, {}).get(fc, 0.0))
            b2_star = float(pp2.get(tc, {}).get(fc, 0.0))
            perm_diffs[pk][p_idx] = (b1_star - b2_star)

        if progress_callback and p_idx % 50 == 0:
            progress_callback(int((p_idx / n_permutations) * 100))

    # 5. Compile multigroup test comparisons for each path (MGA-09)
    comparisons = []
    for fc, tc, pk in path_keys:
        b1 = float(paths_g1.get(tc, {}).get(fc, 0.0))
        b2 = float(paths_g2.get(tc, {}).get(fc, 0.0))
        diff = b1 - b2

        stat1 = p_summary_g1.get(pk, {})
        stat2 = p_summary_g2.get(pk, {})
        se1 = float(stat1.get("standard_error", 0.0))
        se2 = float(stat2.get("standard_error", 0.0))

        # Test 1: Parametric test (Keil et al. 2000)
        param_res = compute_parametric_test(b1, b2, se1, se2, n1, n2)

        # Test 2: Welch-Satterthwaite test
        welch_res = compute_welch_satterthwaite_test(b1, b2, se1, se2, n1, n2)

        # Test 3: Permutation test (Chin & Dibbern 2010)
        dist_perm = perm_diffs[pk]
        p_perm = float((np.sum(np.abs(dist_perm) >= abs(diff)) + 1.0) / (n_permutations + 1.0))
        perm_sig = p_perm < alpha

        # Test 4: Henseler PLS-MGA test (2009)
        p_names_1 = boot_g1.get("parameter_names", [])
        p_names_2 = boot_g2.get("parameter_names", [])
        if pk in p_names_1 and pk in p_names_2 and samples_mat_g1 is not None and samples_mat_g2 is not None:
            col_idx_1 = p_names_1.index(pk)
            col_idx_2 = p_names_2.index(pk)
            s_g1 = samples_mat_g1[:, col_idx_1]
            s_g2 = samples_mat_g2[:, col_idx_2]
            henseler_res = compute_henseler_pls_mga(s_g1, s_g2)
        else:
            henseler_res = {"p_value_one_tailed": None, "p_value_two_tailed": None, "is_significant": False}

        comparisons.append({
            "path": f"{fc} -> {tc}",
            "from": fc,
            "to": tc,
            "beta_group_1": round(b1, 4),
            "beta_group_2": round(b2, 4),
            "difference": round(diff, 4),
            "parametric_test": param_res,
            "welch_test": welch_res,
            "permutation_test": {
                "p_value": round(p_perm, 4),
                "is_significant": perm_sig,
            },
            "henseler_pls_mga": henseler_res,
            "consensus_significant": bool(perm_sig or henseler_res["is_significant"]),
        })

    return {
        "group_column": group_col,
        "group_1": str(g1_val),
        "group_2": str(g2_val),
        "n_group_1": n1,
        "n_group_2": n2,
        "n_boot": n_boot,
        "n_permutations": n_permutations,
        "warnings": warnings,
        "path_comparisons": comparisons,
        "recommendation": (
            "The Permutation test (Chin & Dibbern 2010) and Henseler's PLS-MGA (Henseler et al. 2009) "
            "are non-parametric and represent the recommended tests for PLS-SEM multigroup comparisons (Hair et al. 2017)."
        ),
    }
