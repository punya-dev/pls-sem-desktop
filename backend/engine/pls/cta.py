"""
Confirmatory Tetrad Analysis (CTA-PLS) (Section 19: CTA-01 to CTA-06).
Source of truth: Hair et al. (2017) Ch. 8 & Gudergan et al. (2008).
Evaluates whether vanishing tetrads hold for reflective constructs with >= 4 indicators.
Eliminates redundant tetrads using QR decomposition (keeping p*(p-3)/2 independent tetrads),
and uses Bonferroni-adjusted bootstrap confidence intervals.
"""

from typing import List, Dict, Any, Optional, Tuple, Union
import itertools
import numpy as np
import pandas as pd
from scipy import stats

from core.rng import spawn_seeds, resample_indices


def generate_all_tetrads_for_block(
    indicators: List[str],
) -> List[Dict[str, Any]]:
    """
    Generates all candidate tetrad definitions for p indicators.
    For each combination of 4 indicators (i, j, k, l):
      tau_1 = sigma_ij * sigma_kl - sigma_ik * sigma_jl
      tau_2 = sigma_ij * sigma_kl - sigma_il * sigma_jk
    """
    p = len(indicators)
    if p < 4:
        return []

    tetrad_defs = []
    # Loop over all combinations of 4 distinct indicators
    for combo in itertools.combinations(range(p), 4):
        i, j, k, l = combo
        name_i, name_j, name_k, name_l = indicators[i], indicators[j], indicators[k], indicators[l]
        # Tetrad 1
        tetrad_defs.append({
            "indices": (i, j, k, l),
            "pair1": (i, j), "pair2": (k, l),
            "pair3": (i, k), "pair4": (j, l),
            "label": f"({name_i},{name_j})({name_k},{name_l}) - ({name_i},{name_k})({name_j},{name_l})",
            "names": (name_i, name_j, name_k, name_l),
        })
        # Tetrad 2
        tetrad_defs.append({
            "indices": (i, j, k, l),
            "pair1": (i, j), "pair2": (k, l),
            "pair3": (i, l), "pair4": (j, k),
            "label": f"({name_i},{name_j})({name_k},{name_l}) - ({name_i},{name_l})({name_j},{name_k})",
            "names": (name_i, name_j, name_k, name_l),
        })

    return tetrad_defs


def compute_tetrad_values(
    cov_matrix: np.ndarray,
    tetrad_defs: List[Dict[str, Any]],
) -> np.ndarray:
    """
    Evaluates numeric tetrad values on a covariance matrix S.
    tau = sigma_1 * sigma_2 - sigma_3 * sigma_4
    """
    values = np.zeros(len(tetrad_defs), dtype=float)
    for idx, tdef in enumerate(tetrad_defs):
        i1, j1 = tdef["pair1"]
        i2, j2 = tdef["pair2"]
        i3, j3 = tdef["pair3"]
        i4, j4 = tdef["pair4"]

        t_val = (cov_matrix[i1, j1] * cov_matrix[i2, j2]) - (cov_matrix[i3, j3] * cov_matrix[i4, j4])
        values[idx] = t_val

    return values


def select_nonredundant_tetrads(
    cov_matrix: np.ndarray,
    all_tetrad_defs: List[Dict[str, Any]],
    p_indicators: int,
) -> Tuple[List[Dict[str, Any]], np.ndarray]:
    """
    Selects a maximal linearly independent set of r = p*(p-3)/2 tetrads (CTA-03).
    Constructs Jacobian matrix J (derivatives of tetrads wrt unique covariance elements vech(S))
    and uses QR decomposition with column pivoting.
    """
    expected_r = (p_indicators * (p_indicators - 3)) // 2
    if len(all_tetrad_defs) <= expected_r:
        return all_tetrad_defs, np.arange(len(all_tetrad_defs))

    # Compute Jacobians wrt unique off-diagonal covariance elements
    # Map off-diagonal pairs (u, v) with u < v to index
    pair_map = {}
    pair_count = 0
    for u in range(p_indicators):
        for v in range(u + 1, p_indicators):
            pair_map[(u, v)] = pair_count
            pair_map[(v, u)] = pair_count
            pair_count += 1

    M_tetrads = len(all_tetrad_defs)
    J = np.zeros((M_tetrads, pair_count), dtype=float)

    for t_idx, tdef in enumerate(all_tetrad_defs):
        p1 = tdef["pair1"]
        p2 = tdef["pair2"]
        p3 = tdef["pair3"]
        p4 = tdef["pair4"]

        s1 = cov_matrix[p1[0], p1[1]]
        s2 = cov_matrix[p2[0], p2[1]]
        s3 = cov_matrix[p3[0], p3[1]]
        s4 = cov_matrix[p4[0], p4[1]]

        # Derivative wrt cov(p1): s2
        if p1 in pair_map:
            J[t_idx, pair_map[p1]] += s2
        # Derivative wrt cov(p2): s1
        if p2 in pair_map:
            J[t_idx, pair_map[p2]] += s1
        # Derivative wrt cov(p3): -s4
        if p3 in pair_map:
            J[t_idx, pair_map[p3]] -= s4
        # Derivative wrt cov(p4): -s3
        if p4 in pair_map:
            J[t_idx, pair_map[p4]] -= s3

    # QR decomposition with pivoting on J^T to select linearly independent rows of J
    from scipy.linalg import qr
    # J is (M, N_vars). Transpose J.T is (N_vars, M)
    _, _, p_indices = qr(J.T, pivoting=True)

    selected_indices = sorted(list(p_indices[:expected_r]))
    selected_tetrads = [all_tetrad_defs[idx] for idx in selected_indices]

    return selected_tetrads, np.array(selected_indices)


def run_cta_pls(
    df: pd.DataFrame,
    spec: Union[Dict[str, Any], Any],
    construct_id: Optional[str] = None,
    n_boot: int = 500,
    seed: Optional[int] = 42,
    alpha: float = 0.05,
    progress_callback: Optional[Any] = None,
    cancel_event: Optional[Any] = None,
) -> Dict[str, Any]:
    """
    Executes Confirmatory Tetrad Analysis (CTA-PLS) (CTA-01 to CTA-06).
    """
    spec_dict = spec.model_dump(by_alias=True) if hasattr(spec, "model_dump") else (spec if isinstance(spec, dict) else {})
    constructs = spec_dict.get("constructs", [])

    # Filter constructs to analyze
    target_constructs = []
    for c in constructs:
        cid = c["id"]
        c_type = c.get("type", "reflective")
        if construct_id is not None and cid != construct_id:
            continue
        if c_type == "reflective":
            target_constructs.append(c)

    results_per_construct: List[Dict[str, Any]] = []

    for c in target_constructs:
        cid = c["id"]
        if "indicators" in c and c["indicators"]:
            inds = [i for i in c["indicators"] if i in df.columns]
        else:
            inds = [
                (ind.get("name") or ind.get("column") or ind.get("id"))
                for ind in spec_dict.get("indicators", [])
                if (ind.get("construct_id") or ind.get("construct")) == cid and (ind.get("name") or ind.get("column") or ind.get("id")) in df.columns
            ]

        p = len(inds)
        # CTA-01: Eligibility check (>= 4 indicators)
        if p < 4:
            results_per_construct.append({
                "construct_id": cid,
                "applicable": False,
                "na_reason": f"Construct '{cid}' has {p} indicators. CTA-PLS requires at least 4 indicators to form vanishing tetrads (Hair et al. 2017).",
            })
            continue

        sub_df = df[inds].dropna()
        N = len(sub_df)
        X = sub_df.values.astype(float)
        cov_S = np.cov(X, rowvar=False)

        # Generate candidate tetrads and select r = p*(p-3)/2 nonredundant tetrads
        all_tetrads = generate_all_tetrads_for_block(inds)
        nonred_tetrads, _ = select_nonredundant_tetrads(cov_S, all_tetrads, p)
        r = len(nonred_tetrads)

        orig_values = compute_tetrad_values(cov_S, nonred_tetrads)

        # CTA-05: Bonferroni-adjusted alpha
        alpha_adj = alpha / max(1, r)
        ci_lower_pct = 100.0 * (alpha_adj / 2.0)
        ci_upper_pct = 100.0 * (1.0 - alpha_adj / 2.0)

        # CTA-04: Bootstrapping
        rng = np.random.default_rng(seed)
        seeds = spawn_seeds(seed or 42, n_boot)

        boot_matrix = np.zeros((n_boot, r), dtype=float)
        for b in range(n_boot):
            if cancel_event and cancel_event.is_set():
                raise RuntimeError("CTA-PLS cancelled by user.")
            b_rng = np.random.default_rng(seeds[b])
            resample_idx = resample_indices(N, b_rng)
            X_b = X[resample_idx]
            cov_b = np.cov(X_b, rowvar=False)
            boot_matrix[b, :] = compute_tetrad_values(cov_b, nonred_tetrads)

            if progress_callback and b % 50 == 0:
                progress_callback(int((b / n_boot) * 100))

        # Summarize tetrads
        tetrad_rows = []
        any_excludes_zero = False

        for t_idx, tdef in enumerate(nonred_tetrads):
            val = float(orig_values[t_idx])
            rep_vals = boot_matrix[:, t_idx]
            se = float(np.std(rep_vals, ddof=1))
            t_stat = (val / se) if se > 1e-12 else 0.0
            p_val = 2.0 * (1.0 - stats.norm.cdf(abs(t_stat)))

            # Adjusted percentile CI
            ci_low = float(np.percentile(rep_vals, ci_lower_pct))
            ci_high = float(np.percentile(rep_vals, ci_upper_pct))

            includes_zero = (ci_low <= 0.0 <= ci_high)
            if not includes_zero:
                any_excludes_zero = True

            tetrad_rows.append({
                "tetrad_label": tdef["label"],
                "indicators": list(tdef["names"]),
                "value": round(val, 4),
                "bootstrap_mean": round(float(np.mean(rep_vals)), 4),
                "standard_error": round(se, 4),
                "t_statistic": round(float(t_stat), 4),
                "p_value": round(float(p_val), 4),
                "ci_lower_adjusted": round(ci_low, 4),
                "ci_upper_adjusted": round(ci_high, 4),
                "includes_zero": includes_zero,
            })

        # CTA-06: Decision rule
        if not any_excludes_zero:
            verdict = "Reflective specification supported"
            interpretation = (
                f"All {r} nonredundant vanishing tetrads hold (none of the Bonferroni-adjusted {int((1-alpha)*100)}% "
                f"CIs exclude zero). The empirical data support a reflective measurement model (Hair et al. 2017)."
            )
        else:
            verdict = "Reflective specification rejected (consider formative)"
            interpretation = (
                f"At least one vanishing tetrad is statistically different from zero (Bonferroni-adjusted CI excludes zero). "
                f"The assumption of a reflective unidimensional construct is rejected. "
                f"Consider a formative specification or multidimensional structure (Gudergan et al. 2008)."
            )

        results_per_construct.append({
            "construct_id": cid,
            "applicable": True,
            "n_indicators": p,
            "n_nonredundant_tetrads": r,
            "bonferroni_alpha": round(alpha_adj, 6),
            "verdict": verdict,
            "interpretation": interpretation,
            "tetrads": tetrad_rows,
        })

    return {
        "constructs": results_per_construct,
        "n_boot": n_boot,
        "alpha": alpha,
        "note": "CTA-PLS tests whether vanishing tetrads hold for reflective constructs. Non-vanishing tetrads signal formative or multidimensional structures (Hair et al. 2017; Gudergan et al. 2008).",
    }
