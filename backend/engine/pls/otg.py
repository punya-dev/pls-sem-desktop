"""
Omnibus Test of Group Differences (OTG) and Post-Hoc Pairwise Testing (A18-OTG-01 to A18-OTG-05).
Source of truth: Hair et al. (2018) Ch. 4 & Sarstedt, Henseler & Ringle (2011).

Implements:
1. Family-Wise Error Rate (FWER) calculator: FWER = 1 - (1 - alpha)^m.
2. OTG Omnibus F-statistic variance ratio test across K > 2 groups via bootstrap + permutation.
3. Post-hoc pairwise permutation tests across all K*(K-1)/2 group pairs.
4. Multiple-testing corrections: Bonferroni and Šidák.
"""

from typing import List, Dict, Any, Optional, Tuple, Union
import math
import itertools
import numpy as np
import pandas as pd

from core.settings_schema import PipelineSettings
from core.rng import spawn_seeds
from engine.pls.algorithm import run_pipeline
from engine.pls.bootstrap import ParallelBootstrapper


def calculate_fwer(n_comparisons: int, alpha: float = 0.05) -> float:
    """
    Computes Family-Wise Error Rate (A18-OTG-01):
    FWER = 1 - (1 - alpha)^m
    """
    m = max(1, n_comparisons)
    return float(1.0 - (1.0 - alpha) ** m)


def calculate_sidak_alpha(n_comparisons: int, alpha: float = 0.05) -> float:
    """
    Computes Šidák corrected significance threshold (A18-OTG-04):
    alpha_sidak = 1 - (1 - alpha)^(1/m)
    """
    m = max(1, n_comparisons)
    return float(1.0 - (1.0 - alpha) ** (1.0 / m))


def calculate_bonferroni_alpha(n_comparisons: int, alpha: float = 0.05) -> float:
    """
    Computes Bonferroni corrected significance threshold (A18-OTG-04):
    alpha_bonf = alpha / m
    """
    m = max(1, n_comparisons)
    return float(alpha / m)


def compute_otg_fr_statistic(
    bootstrap_samples_by_group: List[np.ndarray],
) -> float:
    """
    Computes the OTG variance ratio statistic FR (Sarstedt et al. 2011) (A18-OTG-02):
    FR = [ K * B * (1/(K-1)) * sum_i (p_bar_i - p_bar)^2 ] / [ (1/(B-1)) * sum_i sum_j (p_ij - p_bar_i)^2 ]
    """
    K = len(bootstrap_samples_by_group)
    if K < 2:
        return 0.0

    # Ensure equal sample count B across groups
    B = min(len(s) for s in bootstrap_samples_by_group)
    p_mat = np.column_stack([bootstrap_samples_by_group[i][:B] for i in range(K)])  # shape (B, K)

    # Group means: p_bar_i
    p_bar_i = np.mean(p_mat, axis=0)  # shape (K,)
    # Grand mean: p_bar
    p_bar = np.mean(p_bar_i)

    # Numerator (Between-group variance)
    between_var = (1.0 / (K - 1.0)) * np.sum((p_bar_i - p_bar) ** 2)
    numerator = K * B * between_var

    # Denominator (Within-group variance)
    within_var = (1.0 / (B - 1.0)) * np.sum((p_mat - p_bar_i[None, :]) ** 2)
    denom = max(1e-12, within_var)

    return float(numerator / denom)


def run_otg_analysis(
    df: pd.DataFrame,
    spec: Union[Dict[str, Any], Any],
    group_col: str,
    group_values: Optional[List[Any]] = None,
    n_boot: int = 500,
    n_permutations: int = 1000,
    alpha: float = 0.05,
    seed: Optional[int] = 42,
    settings: Optional[PipelineSettings] = None,
    progress_callback: Optional[Any] = None,
    cancel_event: Optional[Any] = None,
) -> Dict[str, Any]:
    """
    Main entry point for Omnibus Test of Group Differences (OTG) across K > 2 groups (A18-OTG-01 to A18-OTG-05).
    """
    spec_dict = spec.model_dump(mode="json", by_alias=True) if hasattr(spec, "model_dump") else (spec if isinstance(spec, dict) else {})
    cfg = settings or PipelineSettings()

    # Identify groups
    if group_values is None:
        unique_vals = list(df[group_col].dropna().unique())
    else:
        unique_vals = list(group_values)

    K = len(unique_vals)
    if K < 2:
        raise ValueError(f"OTG requires at least 2 groups (found {K} in column '{group_col}').")

    group_dfs = {str(g): df[df[group_col] == g].copy() for g in unique_vals}
    group_sizes = {str(g): len(group_dfs[str(g)]) for g in unique_vals}

    # Minimum sample size check
    for g, n_g in group_sizes.items():
        if n_g < 10:
            raise ValueError(f"Group '{g}' has only {n_g} cases. Minimum 10 cases required for OTG.")

    # Step 1: Run PLS and Bootstrapping for each group
    booter = ParallelBootstrapper()
    group_path_estimates: Dict[str, Dict[str, Dict[str, float]]] = {}
    group_path_boot_samples: Dict[str, Dict[str, np.ndarray]] = {}

    for g_idx, g_val in enumerate(unique_vals):
        if cancel_event and cancel_event.is_set():
            raise RuntimeError("OTG analysis cancelled by user.")

        g_df = group_dfs[str(g_val)]
        res_g = run_pipeline(g_df, spec_dict, cfg)
        paths_g = res_g.get("structural", {}).get("path_coefficients", {})
        group_path_estimates[str(g_val)] = paths_g

        # Run bootstrap
        b_seed = (seed * 100 + g_idx * 31) if seed is not None else None
        boot_res = booter.run(
            data=g_df,
            model_spec=spec_dict,
            n_boot=n_boot,
            seed=b_seed,
            scheme=cfg.inner_weighting,
            mode="basic",
            sign_change="none",
            alpha=alpha,
        )

        # Extract 2D matrix of bootstrap estimates: shape (B, n_params)
        raw_boot = boot_res.get("raw_bootstrap_samples", {})
        group_path_boot_samples[str(g_val)] = {
            p_name: np.array(samples, dtype=float)
            for p_name, samples in raw_boot.items()
            if p_name.startswith("path:")
        }

    # Identify all structural paths
    paths = spec_dict.get("paths", [])
    path_names = [f"path:{p.get('from')}->{p.get('to')}" for p in paths]
    clean_path_names = [f"{p.get('from')} -> {p.get('to')}" for p in paths]

    # Step 2: Compute OTG FR-statistic and permutation test per path
    otg_results = []
    rng = np.random.default_rng(seed)
    seeds = spawn_seeds(seed or 42, n_permutations)

    for p_idx, p_key in enumerate(path_names):
        display_name = clean_path_names[p_idx]

        # Collect bootstrap samples across K groups
        boot_list = [group_path_boot_samples[str(g)].get(p_key, np.zeros(n_boot)) for g in unique_vals]

        # Observed FR statistic
        fr_obs = compute_otg_fr_statistic(boot_list)

        # Permutations: permute bootstrap estimates between groups within each bootstrap sample
        B = min(len(s) for s in boot_list)
        p_mat = np.column_stack([boot_list[i][:B] for i in range(K)])  # shape (B, K)

        perm_frs = np.zeros(n_permutations, dtype=float)
        for u in range(n_permutations):
            u_rng = np.random.default_rng(seeds[u])
            # Permute across columns for each row
            p_mat_perm = np.zeros_like(p_mat)
            for b in range(B):
                p_mat_perm[b, :] = u_rng.permutation(p_mat[b, :])

            perm_boot_list = [p_mat_perm[:, i] for i in range(K)]
            perm_frs[u] = compute_otg_fr_statistic(perm_boot_list)

        # p-value = fraction of permuted FR >= observed FR (A18-OTG-02)
        p_val = float((np.sum(perm_frs >= fr_obs) + 1.0) / (n_permutations + 1.0))

        otg_results.append({
            "path": display_name,
            "fr_statistic": round(float(fr_obs), 4),
            "p_value": round(float(p_val), 4),
            "is_significant": bool(p_val < alpha),
            "verdict": "Group differences exist" if p_val < alpha else "No omnibus difference",
        })

    # Step 3: Post-hoc Pairwise Comparisons across all K*(K-1)/2 group pairs (A18-OTG-03)
    pairs = list(itertools.combinations([str(g) for g in unique_vals], 2))
    n_pairs = len(pairs)
    total_comparisons = n_pairs * len(paths)

    # Multiple testing thresholds (A18-OTG-04)
    sidak_alpha = calculate_sidak_alpha(total_comparisons, alpha)
    bonf_alpha = calculate_bonferroni_alpha(total_comparisons, alpha)
    fwer = calculate_fwer(total_comparisons, alpha)

    pairwise_results = []
    for g1, g2 in pairs:
        df1 = group_dfs[g1]
        df2 = group_dfs[g2]
        n1 = len(df1)
        n2 = len(df2)
        df_pooled = pd.concat([df1, df2], axis=0).reset_index(drop=True)

        for p_idx, p_def in enumerate(paths):
            fc = p_def.get("from")
            tc = p_def.get("to")
            p_name = f"{fc} -> {tc}"

            b1 = float(group_path_estimates[g1].get(tc, {}).get(fc, 0.0))
            b2 = float(group_path_estimates[g2].get(tc, {}).get(fc, 0.0))
            diff_obs = b1 - b2

            # Permutation test of path difference
            perm_diffs = np.zeros(n_permutations, dtype=float)
            for u in range(n_permutations):
                u_rng = np.random.default_rng(seeds[u])
                perm_idx = u_rng.permutation(len(df_pooled))
                pdf1 = df_pooled.iloc[perm_idx[:n1]]
                pdf2 = df_pooled.iloc[perm_idx[n1:]]

                res_p1 = run_pipeline(pdf1, spec_dict, cfg)
                res_p2 = run_pipeline(pdf2, spec_dict, cfg)

                pb1 = float(res_p1.get("structural", {}).get("path_coefficients", {}).get(tc, {}).get(fc, 0.0))
                pb2 = float(res_p2.get("structural", {}).get("path_coefficients", {}).get(tc, {}).get(fc, 0.0))
                perm_diffs[u] = pb1 - pb2

            p_val_pair = float((np.sum(np.abs(perm_diffs) >= abs(diff_obs)) + 1.0) / (n_permutations + 1.0))

            pairwise_results.append({
                "group_pair": f"{g1} vs {g2}",
                "group_1": g1,
                "group_2": g2,
                "path": p_name,
                "beta_group_1": round(b1, 4),
                "beta_group_2": round(b2, 4),
                "difference": round(diff_obs, 4),
                "permutation_p_value": round(p_val_pair, 4),
                "sig_standard_05": bool(p_val_pair < 0.05),
                "sig_sidak": bool(p_val_pair < sidak_alpha),
                "sig_bonferroni": bool(p_val_pair < bonf_alpha),
            })

    return {
        "group_column": group_col,
        "groups": [str(g) for g in unique_vals],
        "n_groups": K,
        "group_sample_sizes": group_sizes,
        "n_boot": n_boot,
        "n_permutations": n_permutations,
        "omnibus_tests": otg_results,
        "pairwise_comparisons": pairwise_results,
        "multiple_testing": {
            "total_comparisons": total_comparisons,
            "nominal_alpha": alpha,
            "family_wise_error_rate": round(fwer, 4),
            "sidak_alpha": round(sidak_alpha, 6),
            "bonferroni_alpha": round(bonf_alpha, 6),
            "recommendation": "Šidák correction is preferred over Bonferroni due to superior statistical power (Hair et al. 2018).",
        },
        "note": "OTG is the non-parametric omnibus test of path differences across 3 or more groups (Sarstedt et al. 2011).",
    }


analyze_otg = run_otg_analysis

