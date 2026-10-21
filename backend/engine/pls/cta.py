"""
Confirmatory Tetrad Analysis (CTA-PLS) (A18-CTA-01 to A18-CTA-14).
Source of truth: Hair et al. (2018) Ch. 3 & Gudergan et al. (2008).

Implements:
1. Evaluation of vanishing tetrads H0: tau = 0 to empirically test reflective vs formative specifications.
2. Applies to reflective and formative constructs alike (starts from reflective null).
3. Nonredundant tetrad selection via QR decomposition with column pivoting (r = p*(p-3)/2).
4. Bias-corrected Bonferroni adjusted bootstrap confidence intervals (default alpha = 0.10 / 90% adj. CI).
5. Minimum indicator correlation pre-check table.
6. Preservation of original tetrad numbering from full combinatorial enumeration.
"""

from typing import List, Dict, Any, Optional, Tuple, Union
import itertools
import math
import numpy as np
import pandas as pd
from scipy import stats

from core.rng import spawn_seeds, resample_indices


def generate_all_tetrads_for_block(
    indicators: List[str],
) -> List[Dict[str, Any]]:
    """
    Generates all candidate tetrad definitions for p indicators with original 1-based indexing (A18-CTA-03, A18-CTA-05).
    For each combination of 4 indicators (i < j < k < l):
      tau_1 = sigma_ij * sigma_kl - sigma_ik * sigma_jl
      tau_2 = sigma_ij * sigma_kl - sigma_il * sigma_jk
      tau_3 = sigma_ik * sigma_jl - sigma_il * sigma_jk
    """
    p = len(indicators)
    if p < 4:
        return []

    tetrad_defs = []
    tetrad_counter = 1

    # Loop over all combinations of 4 distinct indicators in order
    for combo in itertools.combinations(range(p), 4):
        i, j, k, l = combo
        name_i, name_j, name_k, name_l = indicators[i], indicators[j], indicators[k], indicators[l]
        idx_label = f"{i+1}{j+1}{k+1}{l+1}"

        # Tetrad 1: tau_ijkl = sigma_ij * sigma_kl - sigma_ik * sigma_jl
        tetrad_defs.append({
            "original_index": tetrad_counter,
            "indices": (i, j, k, l),
            "pair1": (i, j), "pair2": (k, l),
            "pair3": (i, k), "pair4": (j, l),
            "tetrad_name": f"τ_{idx_label}",
            "label": f"τ_{tetrad_counter} ({name_i},{name_j})({name_k},{name_l}) - ({name_i},{name_k})({name_j},{name_l})",
            "names": (name_i, name_j, name_k, name_l),
        })
        tetrad_counter += 1

        # Tetrad 2: tau_iklj = sigma_ij * sigma_kl - sigma_il * sigma_jk
        tetrad_defs.append({
            "original_index": tetrad_counter,
            "indices": (i, j, k, l),
            "pair1": (i, j), "pair2": (k, l),
            "pair3": (i, l), "pair4": (j, k),
            "tetrad_name": f"τ_{i+1}{j+1}{l+1}{k+1}",
            "label": f"τ_{tetrad_counter} ({name_i},{name_j})({name_k},{name_l}) - ({name_i},{name_l})({name_j},{name_k})",
            "names": (name_i, name_j, name_k, name_l),
        })
        tetrad_counter += 1

        # Tetrad 3: tau_iljk = sigma_ik * sigma_jl - sigma_il * sigma_jk
        tetrad_defs.append({
            "original_index": tetrad_counter,
            "indices": (i, j, k, l),
            "pair1": (i, k), "pair2": (j, l),
            "pair3": (i, l), "pair4": (j, k),
            "tetrad_name": f"τ_{i+1}{k+1}{l+1}{j+1}",
            "label": f"τ_{tetrad_counter} ({name_i},{name_k})({name_j},{name_l}) - ({name_i},{name_l})({name_j},{name_k})",
            "names": (name_i, name_j, name_k, name_l),
        })
        tetrad_counter += 1

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
    Selects a maximal linearly independent set of r = p*(p-3)/2 nonredundant tetrads (A18-CTA-04, A18-CTA-05).
    Constructs Jacobian matrix J and performs QR decomposition with column pivoting.
    """
    expected_r = (p_indicators * (p_indicators - 3)) // 2
    if len(all_tetrad_defs) <= expected_r:
        return all_tetrad_defs, np.arange(len(all_tetrad_defs))

    # Map unique off-diagonal pairs (u, v) with u < v
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

    from scipy.linalg import qr
    # Pivot QR on J^T to find independent rows of J
    _, _, p_indices = qr(J.T, pivoting=True)

    selected_indices = sorted(list(p_indices[:expected_r]))
    selected_tetrads = [all_tetrad_defs[idx] for idx in selected_indices]

    return selected_tetrads, np.array(selected_indices)


def run_cta_pls(
    df: pd.DataFrame,
    spec: Union[Dict[str, Any], Any],
    construct_id: Optional[str] = None,
    n_boot: int = 5000,
    seed: Optional[int] = 42,
    alpha: float = 0.10,  # A18-CTA-10: recommended alpha is 0.10 (90% adjusted CI)
    progress_callback: Optional[Any] = None,
    cancel_event: Optional[Any] = None,
) -> Dict[str, Any]:
    """
    Executes Confirmatory Tetrad Analysis (CTA-PLS) (A18-CTA-01 to A18-CTA-14).
    """
    spec_dict = spec.model_dump(mode="json", by_alias=True) if hasattr(spec, "model_dump") else (spec if isinstance(spec, dict) else {})
    from engine.pls.algorithm import parse_model_spec
    constructs_dict, ind_col_map, paths_list = parse_model_spec(spec_dict)

    # A18-CTA-13: Allow CTA on formative-drawn and reflective-drawn constructs alike
    target_constructs = []
    for cid, c in constructs_dict.items():
        if construct_id is not None and cid != construct_id:
            continue
        target_constructs.append(c)

    results_per_construct: List[Dict[str, Any]] = []

    for c in target_constructs:
        cid = c["id"]
        c_name = c.get("name", cid)
        c_drawn_type = c.get("type", "reflective")
        inds = []
        for iid in c.get("indicators", []):
            col = ind_col_map.get(iid, iid)
            if col in df.columns and col not in inds:
                inds.append(col)

        p = len(inds)

        # A18-CTA-08: Eligibility check (>= 4 indicators)
        if p < 4:
            results_per_construct.append({
                "construct_id": cid,
                "construct_name": c_name,
                "drawn_type": c_drawn_type,
                "applicable": False,
                "na_reason": f"Construct '{c_name}' has {p} indicators. CTA-PLS requires at least 4 indicators to form vanishing tetrads (Hair et al. 2018).",
            })
            continue

        sub_df = df[inds].dropna()
        N = len(sub_df)
        X = sub_df.values.astype(float)
        cov_S = np.cov(X, rowvar=False)

        # Compute indicator correlation matrix and minimum off-diagonal correlation (A18-CTA-08)
        std_devs = np.sqrt(np.diag(cov_S))
        std_outer = np.outer(std_devs, std_devs)
        corr_matrix = np.divide(cov_S, std_outer, out=np.zeros_like(cov_S), where=std_outer != 0)
        np.fill_diagonal(corr_matrix, 1.0)

        # Minimum off-diagonal correlation
        off_diag_corrs = []
        for u in range(p):
            for v in range(u + 1, p):
                off_diag_corrs.append(float(corr_matrix[u, v]))
        min_indicator_corr = min(off_diag_corrs) if off_diag_corrs else 0.0

        # Generate candidate tetrads and select r = p*(p-3)/2 nonredundant tetrads
        all_tetrads = generate_all_tetrads_for_block(inds)
        total_m_tetrads = len(all_tetrads)
        nonred_tetrads, _ = select_nonredundant_tetrads(cov_S, all_tetrads, p)
        r = len(nonred_tetrads)

        orig_values = compute_tetrad_values(cov_S, nonred_tetrads)

        # Bonferroni-adjusted alpha (A18-CTA-06)
        alpha_adj = alpha / max(1, r)

        # Bootstrapping (A18-CTA-04)
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

            if progress_callback and b % 100 == 0:
                progress_callback(int((b / n_boot) * 100))

        # Summarize tetrads with bias-corrected Bonferroni CIs
        tetrad_rows = []
        any_excludes_zero = False
        significant_tetrad_numbers = []

        for t_idx, tdef in enumerate(nonred_tetrads):
            val = float(orig_values[t_idx])
            rep_vals = boot_matrix[:, t_idx]
            se = float(np.std(rep_vals, ddof=1))
            t_stat = (val / se) if se > 1e-12 else 0.0
            p_val = 2.0 * (1.0 - stats.norm.cdf(abs(t_stat)))

            # Bias-corrected quantile calculation (A18-CTA-06)
            prop_below = float(np.mean(rep_vals < val))
            prop_below = max(1e-5, min(1.0 - 1e-5, prop_below))
            z0 = stats.norm.ppf(prop_below)

            z_lower = stats.norm.ppf(alpha_adj / 2.0)
            z_upper = stats.norm.ppf(1.0 - alpha_adj / 2.0)

            pct_lower = float(stats.norm.cdf(2.0 * z0 + z_lower) * 100.0)
            pct_upper = float(stats.norm.cdf(2.0 * z0 + z_upper) * 100.0)
            pct_lower = max(0.01, min(99.99, pct_lower))
            pct_upper = max(0.01, min(99.99, pct_upper))

            ci_low = float(np.percentile(rep_vals, pct_lower))
            ci_high = float(np.percentile(rep_vals, pct_upper))

            includes_zero = bool(ci_low <= 0.0 <= ci_high)
            if not includes_zero:
                any_excludes_zero = True
                significant_tetrad_numbers.append(tdef["original_index"])

            tetrad_rows.append({
                "tetrad_number": tdef["original_index"],
                "tetrad_name": tdef["tetrad_name"],
                "tetrad_label": tdef["label"],
                "indicators": list(tdef["names"]),
                "original_value": round(val, 4),
                "bootstrap_mean": round(float(np.mean(rep_vals)), 4),
                "standard_error": round(se, 4),
                "t_statistic": round(float(t_stat), 4),
                "p_value": round(float(p_val), 4),
                "ci_lower_adjusted": round(ci_low, 4),
                "ci_upper_adjusted": round(ci_high, 4),
                "includes_zero": includes_zero,
                "is_significant": not includes_zero,
            })

        # Decision rule (A18-CTA-07)
        if not any_excludes_zero:
            verdict = "Reflective specification supported"
            interpretation = (
                f"All {r} nonredundant vanishing tetrads hold (none of the Bonferroni-adjusted {int((1-alpha)*100)}% "
                f"CIs exclude zero). The empirical data support a reflective measurement model (Hair et al. 2018)."
            )
        else:
            verdict = "Formative specification supported (reflective rejected)"
            interpretation = (
                f"Significant vanishing tetrad(s) detected: {significant_tetrad_numbers}. "
                f"At least one nonredundant tetrad statistically differs from zero at the adjusted {int((1-alpha)*100)}% level. "
                f"The reflective null is rejected, supporting a formative specification (Hair et al. 2018; Gudergan et al. 2008)."
            )

        results_per_construct.append({
            "construct_id": cid,
            "construct_name": c_name,
            "drawn_type": c_drawn_type,
            "applicable": True,
            "n_indicators": p,
            "total_possible_tetrads": total_m_tetrads,
            "n_nonredundant_tetrads": r,
            "min_indicator_correlation": round(min_indicator_corr, 4),
            "indicator_correlations_adequate": bool(min_indicator_corr > 0.10),
            "bonferroni_alpha": round(alpha_adj, 6),
            "verdict": verdict,
            "interpretation": interpretation,
            "has_significant_tetrads": any_excludes_zero,
            "significant_tetrad_numbers": significant_tetrad_numbers,
            "tetrads": tetrad_rows,
        })

    return {
        "constructs": results_per_construct,
        "n_boot": n_boot,
        "nominal_alpha": alpha,
        "confidence_level": f"{int((1-alpha)*100)}%",
        "decision_rules_help": {
            "causality_direction": "Do indicators define the construct (formative) or are they consequences of the construct (reflective)?",
            "interchangeability": "Are indicators interchangeable with identical content (reflective) or each capturing a unique facet (formative)?",
            "covariation": "Are indicators expected to covary strongly (reflective) or can they vary independently (formative)?",
            "nomological_net": "Do indicators share the same antecedents and consequences (reflective) or distinct ones (formative)?",
            "source": "Jarvis, MacKenzie & Podsakoff (2003) & Bollen & Diamantopoulos (2017).",
        },
        "note": "CTA-PLS empirically evaluates vanishing tetrads. Any non-vanishing tetrad rejects reflective measurement in favor of formative, provided theory aligns (Hair et al. 2018).",
    }
