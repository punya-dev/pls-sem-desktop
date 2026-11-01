"""
Gaussian Copula Endogeneity Analysis (Liengaard et al., 2025; Park & Gupta, 2012).
Tests for endogeneity and applies copula-based correction without instrumental variables.
Follows the SmartPLS 4 Gaussian Copula workflow and specifications.
"""

from typing import List, Dict, Any, Optional, Tuple, Union
import copy
import numpy as np
import pandas as pd
from scipy import stats

from core.settings_schema import PipelineSettings, GCSettings
from core.rng import spawn_seeds, resample_indices


class CopulaCollinearityError(ValueError):
    """Raised when copula regressors are singular or collinear (condition number > 1e8)."""
    pass


def f4_ecdf(p: np.ndarray, round_decimals: Optional[int] = 12) -> np.ndarray:
    """
    Adjusted ECDF F4 (Liengaard et al. 2025 Eq. 15):
    F4(x) = 1/(2n) + ((n-1)/n^2) * #{ i : P_i <= x }
    Properties:
    - Never 0 or 1: strictly inside (0, 1).
    - F4(max) == (n - 0.5) / n.
    - Handles ties using <= (right searchsorted).
    - Invariant to input ordering.
    - Pre-rounds scores to avoid false split ties from floating-point noise.
    """
    p_arr = np.asarray(p, dtype=float)
    n = len(p_arr)
    if n == 0:
        return np.array([], dtype=float)
    if round_decimals is not None:
        p_arr = np.round(p_arr, round_decimals)
    p_sorted = np.sort(p_arr)
    count_le = np.searchsorted(p_sorted, p_arr, side="right")
    return 1.0 / (2.0 * n) + ((n - 1.0) / (n ** 2.0)) * count_le


def f3_ecdf(p: np.ndarray, round_decimals: Optional[int] = 12) -> np.ndarray:
    """
    Endpoint-adjusted ECDF F3:
    F3(x) = #{ i : P_i <= x } / n, clipped to [1e-7, 1 - 1e-7].
    """
    p_arr = np.asarray(p, dtype=float)
    n = len(p_arr)
    if n == 0:
        return np.array([], dtype=float)
    if round_decimals is not None:
        p_arr = np.round(p_arr, round_decimals)
    p_sorted = np.sort(p_arr)
    count_le = np.searchsorted(p_sorted, p_arr, side="right")
    return np.clip(count_le / float(n), 1e-7, 1.0 - 1e-7)


def copula_term(p: np.ndarray, ecdf: str = "F4", round_decimals: Optional[int] = 12) -> np.ndarray:
    """
    Computes standard normal quantile of ECDF: C(P) = Phi^-1(F(P)).
    """
    f = f4_ecdf(p, round_decimals=round_decimals) if str(ecdf).upper() == "F4" else f3_ecdf(p, round_decimals=round_decimals)
    return stats.norm.ppf(f)


def copula_matrix(
    scores_dict: Dict[str, np.ndarray],
    P_names: List[str],
    W_names: List[str],
    transform: str = "raw",
    ecdf: str = "F4",
    round_decimals: Optional[int] = 12,
) -> np.ndarray:
    """
    Computes copula terms for target construct Y with endogenous regressors P
    and exogenous continuous regressors W (Liengaard et al. 2025 Eq. 17).
    Per Liengaard et al. (2025), if W is empty, copula terms are simply raw C(P).
    """
    dP = len(P_names)
    dW = len(W_names)
    if dP == 0:
        first_v = next(iter(scores_dict.values()))
        return np.empty((len(first_v), 0), dtype=float)

    all_names = P_names + W_names
    C_list = [copula_term(scores_dict[v], ecdf=ecdf, round_decimals=round_decimals) for v in all_names]
    C = np.column_stack(C_list)

    if transform.lower() == "raw":
        return C[:, :dP]

    # Eq. 17: Cmat(P, W) = [C(P) C(W)] @ inv(Sigma) @ [I_dP; 0]
    Sigma = np.cov(C, rowvar=False, ddof=1)
    if np.ndim(Sigma) == 0:
        Sigma = np.array([[float(Sigma)]], dtype=float)

    cond = np.linalg.cond(Sigma)
    if cond > 1e8 or np.isnan(cond):
        raise CopulaCollinearityError(
            "Copula term for regressor is collinear with the regressors; endogeneity correction not possible"
        )

    sel = np.vstack([np.eye(dP), np.zeros((dW, dP))])
    inv_sigma = np.linalg.inv(Sigma)
    return C @ inv_sigma @ sel


def cvm_mc_test(x: np.ndarray, n_mc: int = 2000, seed: int = 42) -> Tuple[float, float]:
    """
    Cramer-von Mises normality test with estimated parameters (mean and variance),
    p-value computed via Monte Carlo under normal null (2000 draws).
    """
    x_arr = np.asarray(x, dtype=float)
    n = len(x_arr)
    if n < 4:
        return 0.0, 1.0

    mu = float(np.mean(x_arr))
    s = float(np.std(x_arr, ddof=1))
    if s == 0 or np.isnan(s):
        return 0.0, 1.0

    x_sort = np.sort(x_arr)
    u = stats.norm.cdf(x_sort, loc=mu, scale=s)
    i = np.arange(1, n + 1)
    stat = float((1.0 / (12.0 * n)) + np.sum(((2.0 * i - 1.0) / (2.0 * n) - u) ** 2))

    rng = np.random.default_rng(seed)
    sims = rng.standard_normal((n_mc, n))
    sims.sort(axis=1)
    m_sim = np.mean(sims, axis=1, keepdims=True)
    s_sim = np.std(sims, axis=1, ddof=1, keepdims=True)
    s_sim = np.where(s_sim == 0, 1.0, s_sim)
    u_sim = stats.norm.cdf(sims, loc=m_sim, scale=s_sim)
    stats_mc = (1.0 / (12.0 * n)) + np.sum(((2.0 * i - 1.0) / (2.0 * n) - u_sim) ** 2, axis=1)
    p_val = float(np.mean(stats_mc >= stat))
    return stat, p_val


def anderson_darling_test(x: np.ndarray) -> Tuple[float, float]:
    """
    Anderson-Darling normality test for estimated mean and variance.
    Uses scipy.stats.anderson with interpolate method or Stephens formula.
    """
    x_arr = np.asarray(x, dtype=float)
    if len(x_arr) < 5:
        return 0.0, 1.0
    try:
        res = stats.anderson(x_arr, dist="norm", method="interpolate")
        return float(res.statistic), float(res.pvalue)
    except Exception:
        res = stats.anderson(x_arr, dist="norm")
        stat = float(res.statistic)
        n = len(x_arr)
        a_star = stat * (1.0 + 0.75 / n + 2.25 / (n ** 2))
        if a_star >= 0.600:
            p_val = np.exp(1.2937 - 5.709 * a_star + 0.0186 * (a_star ** 2))
        elif a_star >= 0.340:
            p_val = np.exp(0.9177 - 4.279 * a_star - 1.38 * (a_star ** 2))
        elif a_star >= 0.200:
            p_val = 1.0 - np.exp(-8.318 + 42.796 * a_star - 59.938 * (a_star ** 2))
        else:
            p_val = 1.0 - np.exp(-13.436 + 101.14 * a_star - 223.73 * (a_star ** 2))
        p_val = float(np.clip(p_val, 0.0, 1.0))
        return stat, p_val


def compute_regressor_diagnostics(
    scores_dict: Dict[str, np.ndarray],
    regressor_roles: Dict[str, str],
    distinct_counts: Optional[Dict[str, int]] = None,
    n_cases: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """
    Calculates non-normality diagnostics (skewness, kurtosis, AD, CvM, Corr(P, C(P)))
    for all regressors.
    """
    rows = []
    n = n_cases or (len(next(iter(scores_dict.values()))) if scores_dict else 0)

    for cname, role in regressor_roles.items():
        if cname not in scores_dict:
            continue
        sc = np.asarray(scores_dict[cname], dtype=float)
        skew = float(stats.skew(sc))
        kurt = float(stats.kurtosis(sc))
        ad_stat, ad_p = anderson_darling_test(sc)
        cvm_stat, cvm_p = cvm_mc_test(sc)

        c_term = copula_term(sc, ecdf="F4")
        corr_matrix = np.corrcoef(sc, c_term)
        corr_val = float(corr_matrix[0, 1]) if corr_matrix.shape == (2, 2) else 1.0

        is_normal = (ad_p >= 0.05) and (cvm_p >= 0.05)
        flags = []
        if is_normal:
            flags.append("Regressor appears normally distributed; the Gaussian copula approach needs sufficient non-normality.")
        if n < 200:
            flags.append(f"Small sample size (n = {n} < 200); copula estimates can be biased.")
        if distinct_counts and distinct_counts.get(cname, 999) < 10:
            flags.append(f"Construct has only {distinct_counts[cname]} distinct values; caution with ties.")

        rows.append({
            "construct": cname,
            "role": role,
            "skewness": round(skew, 4),
            "excess_kurtosis": round(kurt, 4),
            "ad_stat": round(ad_stat, 4),
            "ad_pvalue": round(ad_p, 4),
            "cvm_stat": round(cvm_stat, 4),
            "cvm_pvalue": round(cvm_p, 4),
            "corr_copula": round(corr_val, 4),
            "is_non_normal": bool(not is_normal),
            "flag": " | ".join(flags) if flags else "Adequate non-normality",
        })
    return rows


def compute_wald_test(
    orig_gc_coefs: Dict[str, float],
    boot_samples: Dict[str, np.ndarray],
    target_to_gc_names: Dict[str, List[str]],
) -> List[Dict[str, Any]]:
    """
    Computes Joint Significance (Wald) tests per target and overall:
    W = g' V^-1 g ~ Chi-square(k).
    """
    results = []

    # Per target tests
    for tgt, gc_list in target_to_gc_names.items():
        if not gc_list:
            continue
        k = len(gc_list)
        g = np.array([orig_gc_coefs.get(gcn, 0.0) for gcn in gc_list], dtype=float)
        boot_matrix = []
        for gcn in gc_list:
            pkey = f"path:{gcn}->{tgt}"
            boot_vals = boot_samples.get(pkey)
            if boot_vals is not None and len(boot_vals) > 0:
                boot_matrix.append(boot_vals)
            else:
                boot_matrix.append(np.zeros(10))

        boot_matrix = np.array(boot_matrix, dtype=float)
        if boot_matrix.shape[1] > 1:
            V = np.cov(boot_matrix, ddof=1)
            if np.ndim(V) == 0:
                V = np.array([[float(V)]])
            try:
                cond = np.linalg.cond(V)
                if cond > 1e12 or np.isnan(cond):
                    stat = None
                    p_val = None
                    note = "Covariance matrix singular; not computable"
                else:
                    inv_V = np.linalg.inv(V)
                    W_stat = float(g @ inv_V @ g)
                    p_val = float(1.0 - stats.chi2.cdf(W_stat, df=k))
                    stat = round(W_stat, 4)
                    p_val = round(p_val, 4)
                    note = "Significant result indicates endogeneity. Researchers should keep and interpret the copula model estimates even when GC terms are not significant due to low power."
            except Exception:
                stat = None
                p_val = None
                note = "Covariance matrix singular; not computable"
        else:
            stat = None
            p_val = None
            note = "Requires bootstrap to compute covariance matrix V"

        results.append({
            "target": tgt,
            "gc_terms": ", ".join(gc_list),
            "statistic": stat,
            "df": k,
            "p_value": p_val,
            "is_significant": bool(p_val < 0.05) if p_val is not None else False,
            "note": note,
        })

    # Overall test
    all_gc = []
    for tgt, gc_list in target_to_gc_names.items():
        for gcn in gc_list:
            all_gc.append((tgt, gcn))

    if len(all_gc) > 0:
        k_tot = len(all_gc)
        g_tot = np.array([orig_gc_coefs.get(gcn, 0.0) for tgt, gcn in all_gc], dtype=float)
        boot_matrix = []
        for tgt, gcn in all_gc:
            pkey = f"path:{gcn}->{tgt}"
            boot_vals = boot_samples.get(pkey)
            if boot_vals is not None and len(boot_vals) > 0:
                boot_matrix.append(boot_vals)
            else:
                boot_matrix.append(np.zeros(10))

        boot_matrix = np.array(boot_matrix, dtype=float)
        if boot_matrix.shape[1] > 1:
            V = np.cov(boot_matrix, ddof=1)
            if np.ndim(V) == 0:
                V = np.array([[float(V)]])
            try:
                cond = np.linalg.cond(V)
                if cond > 1e12 or np.isnan(cond):
                    stat = None
                    p_val = None
                    note = "Covariance matrix singular; not computable"
                else:
                    inv_V = np.linalg.inv(V)
                    W_stat = float(g_tot @ inv_V @ g_tot)
                    p_val = float(1.0 - stats.chi2.cdf(W_stat, df=k_tot))
                    stat = round(W_stat, 4)
                    p_val = round(p_val, 4)
                    note = "Significant result indicates endogeneity. Researchers should keep and interpret the copula model estimates even when GC terms are not significant due to low power."
            except Exception:
                stat = None
                p_val = None
                note = "Covariance matrix singular; not computable"
        else:
            stat = None
            p_val = None
            note = "Requires bootstrap to compute covariance matrix V"

        results.append({
            "target": "Overall",
            "gc_terms": ", ".join([f"{gcn}->{tgt}" for tgt, gcn in all_gc]),
            "statistic": stat,
            "df": k_tot,
            "p_value": p_val,
            "is_significant": bool(p_val < 0.05) if p_val is not None else False,
            "note": note,
        })

    return results


def normalize_gc_spec(spec_dict: Dict[str, Any]) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """
    Extracts and validates active Gaussian Copula definitions from model_spec dict.
    """
    raw_gc = spec_dict.get("gaussian_copulas") or spec_dict.get("gaussianCopulas") or []
    cleaned_gc: List[Dict[str, Any]] = []

    c_map = {c["id"]: c.get("name", c["id"]) for c in spec_dict.get("constructs", [])}
    name_to_cid = {c.get("name", c["id"]): c["id"] for c in spec_dict.get("constructs", [])}

    for item in raw_gc:
        if hasattr(item, "model_dump"):
            d = item.model_dump(by_alias=True)
        elif isinstance(item, dict):
            d = dict(item)
        else:
            continue

        gc_id = str(d.get("id") or "")
        src = str(d.get("source_construct") or d.get("sourceConstruct") or d.get("source") or "")
        tgt = str(d.get("target_construct") or d.get("targetConstruct") or d.get("target") or "")

        if src not in c_map and src in name_to_cid:
            src = name_to_cid[src]
        if tgt not in c_map and tgt in name_to_cid:
            tgt = name_to_cid[tgt]

        if not gc_id:
            gc_id = f"gc_{src}_{tgt}"

        src_name = c_map.get(src, src)
        tgt_name = c_map.get(tgt, tgt)
        gc_construct_name = f"GC ({src_name} -> {tgt_name})"

        cleaned_gc.append({
            "id": gc_id,
            "source": src,
            "target": tgt,
            "source_name": src_name,
            "target_name": tgt_name,
            "gc_construct_name": gc_construct_name,
            "indicator_name": f"gc_{src}_{tgt}",
            "node_x": d.get("node_x") or d.get("nodeX"),
            "node_y": d.get("node_y") or d.get("nodeY"),
        })

    return spec_dict, cleaned_gc


def run_expanded_copula_estimation(
    df: pd.DataFrame,
    spec_dict: Dict[str, Any],
    gcs: List[Dict[str, Any]],
    settings: PipelineSettings,
) -> Dict[str, Any]:
    """
    Executes the two-stage Gaussian copula estimation pipeline:
    Stage 1: Normal PLS-SEM on model without GC.
    Copulas: Computed from Stage 1 LV scores.
    Stage 2: Full PLS-SEM with single-indicator GC constructs.
    """
    from engine.pls.algorithm import run_pipeline, parse_model_spec

    # Build Stage 1 spec (remove GC)
    s1_spec = copy.deepcopy(spec_dict)
    s1_spec["gaussian_copulas"] = []
    s1_spec["gaussianCopulas"] = []

    cfg_s1 = copy.deepcopy(settings)
    cfg_s1._in_gaussian_copula = True

    # 1. Run Stage 1
    res_s1 = run_pipeline(df, s1_spec, cfg_s1)
    scores_s1 = res_s1.get("construct_scores", {})
    N = len(df)

    # Standardize Stage 1 construct scores (mean 0, SD 1, ddof=1)
    std_scores: Dict[str, np.ndarray] = {}
    for cid, sc in scores_s1.items():
        sc_arr = np.asarray(sc, dtype=float)
        std_dev = float(np.std(sc_arr, ddof=1))
        if std_dev > 1e-12:
            std_scores[cid] = (sc_arr - np.mean(sc_arr)) / std_dev
        else:
            std_scores[cid] = sc_arr - np.mean(sc_arr)

    # Resolve settings
    gc_settings = getattr(settings, "gc", None) or GCSettings()
    ecdf_choice = getattr(gc_settings, "ecdf", "F4")
    transform_choice = getattr(gc_settings, "copula_transform", "raw")
    stage2_method = getattr(gc_settings, "stage2_method", "pls")

    # Group GCs by target
    target_to_gcs: Dict[str, List[Dict[str, Any]]] = {}
    for gc in gcs:
        target_to_gcs.setdefault(gc["target"], []).append(gc)

    # Predecessors of each target from Stage 1 paths
    paths = s1_spec.get("paths", [])
    target_all_preds: Dict[str, List[str]] = {}
    for p in paths:
        fc = p.get("from") or p.get("from_node")
        tc = p.get("to") or p.get("to_node")
        if tc not in target_all_preds:
            target_all_preds[tc] = []
        if fc not in target_all_preds[tc]:
            target_all_preds[tc].append(fc)

    # If moderation exists, add interaction terms as predecessors in W
    mod_effects = s1_spec.get("moderating_effects") or s1_spec.get("moderatingEffects") or []
    for me in mod_effects:
        tgt = me.get("target") or me.get("outcome")
        int_term = me.get("interaction_term") or f"{me.get('moderator')} x {me.get('source')}"
        if tgt and int_term in std_scores:
            target_all_preds.setdefault(tgt, []).append(int_term)

    # 2. Compute copula matrices per target
    copula_columns: Dict[str, np.ndarray] = {}
    regressor_roles: Dict[str, str] = {}
    raw_copula_stds: Dict[str, float] = {}
    round_decimals = getattr(gc_settings, "round_decimals", 12)

    try:
        for tgt, target_gc_list in target_to_gcs.items():
            P_cids = [gc["source"] for gc in target_gc_list]
            for p_cid in P_cids:
                regressor_roles[p_cid] = "Endogenous (P)"

            all_preds = target_all_preds.get(tgt, [])
            W_cids = [pred for pred in all_preds if pred not in P_cids]
            for w_cid in W_cids:
                if w_cid not in regressor_roles:
                    regressor_roles[w_cid] = "Exogenous (W)"

            # Copula matrix for this target (per Liengaard et al. 2025: raw C(P) when W empty)
            eff_transform = "raw" if len(W_cids) == 0 else transform_choice
            Cmat = copula_matrix(
                scores_dict=std_scores,
                P_names=P_cids,
                W_names=W_cids,
                transform=eff_transform,
                ecdf=ecdf_choice,
                round_decimals=round_decimals,
            )

            for idx, gc in enumerate(target_gc_list):
                col_data = Cmat[:, idx]
                # Standardize copula column
                col_std = float(np.std(col_data, ddof=1))
                raw_copula_stds[gc["gc_construct_name"]] = col_std
                if col_std > 1e-12:
                    col_norm = (col_data - np.mean(col_data)) / col_std
                else:
                    col_norm = col_data - np.mean(col_data)
                copula_columns[gc["indicator_name"]] = col_norm

    except CopulaCollinearityError as err:
        # Collinear error: return partial stage 1 results with banner
        res_s1["gaussian_copula"] = {
            "error": str(err),
            "banner": str(err),
            "collinear": True,
        }
        return res_s1

    # Distinct values check on manifest variables
    distinct_counts: Dict[str, int] = {}
    for c in s1_spec.get("constructs", []):
        cid = c["id"]
        inds = c.get("indicators", [])
        if len(inds) == 1 and inds[0] in df.columns:
            distinct_counts[cid] = int(df[inds[0]].dropna().nunique())

    # Regressor diagnostics from Stage 1 (skip during bootstrap resamples for high performance)
    if not getattr(settings, "_is_bootstrap", False):
        diagnostics = compute_regressor_diagnostics(
            scores_dict=std_scores,
            regressor_roles=regressor_roles,
            distinct_counts=distinct_counts,
            n_cases=N,
        )
    else:
        diagnostics = []

    # 3. Build Stage 2 expanded model
    df_stage2 = df.copy()
    for col_name, col_data in copula_columns.items():
        df_stage2[col_name] = col_data

    s2_constructs = list(s1_spec.get("constructs", []))
    s2_indicators = list(s1_spec.get("indicators", []))
    s2_paths = list(s1_spec.get("paths", []))

    for gc in gcs:
        gc_cname = gc["gc_construct_name"]
        gc_ind = gc["indicator_name"]

        # Add single-indicator construct
        s2_constructs.append({
            "id": gc_cname,
            "name": gc_cname,
            "type": "reflective",
            "outer_mode": "A",
            "indicators": [gc_ind],
            "is_copula": True,
        })
        s2_indicators.append({
            "id": gc_ind,
            "name": gc_ind,
            "column": gc_ind,
        })
        # Add path into target
        s2_paths.append({
            "from": gc_cname,
            "to": gc["target"],
        })

    s2_spec = copy.deepcopy(s1_spec)
    s2_spec["constructs"] = s2_constructs
    s2_spec["indicators"] = s2_indicators
    s2_spec["paths"] = s2_paths
    s2_spec["gaussian_copulas"] = []
    s2_spec["gaussianCopulas"] = []

    cfg_s2 = copy.deepcopy(settings)
    cfg_s2._in_gaussian_copula = True

    # Run Stage 2
    res_s2 = run_pipeline(df_stage2, s2_spec, cfg_s2)

    # 4. Compile Endogeneity Tests and Effect of Correction
    s1_paths = res_s1.get("structural", {}).get("path_coefficients", {})
    s2_paths_map = res_s2.get("structural", {}).get("path_coefficients", {})

    # Apply copula scale normalization: in SmartPLS, Gaussian copulas are unscaled by std(C)
    scale_norm = getattr(gc_settings, "scale_normalization", "unscaled")
    if scale_norm == "unscaled":
        for gc in gcs:
            tgt = gc["target"]
            gc_cname = gc["gc_construct_name"]
            s_val = raw_copula_stds.get(gc_cname, 1.0)
            if s_val > 1e-12:
                if tgt in s2_paths_map and gc_cname in s2_paths_map[tgt]:
                    s2_paths_map[tgt][gc_cname] = float(s2_paths_map[tgt][gc_cname]) / s_val
                if "total_effects" in res_s2.get("structural", {}):
                    tot_map = res_s2["structural"]["total_effects"]
                    if tgt in tot_map and gc_cname in tot_map[tgt]:
                        tot_map[tgt][gc_cname] = float(tot_map[tgt][gc_cname]) / s_val

    endogeneity_tests = []
    effects_of_correction = []
    orig_gc_coefs: Dict[str, float] = {}
    target_to_gc_names: Dict[str, List[str]] = {}

    for gc in gcs:
        src = gc["source"]
        tgt = gc["target"]
        src_name = gc["source_name"]
        tgt_name = gc["target_name"]
        gc_cname = gc["gc_construct_name"]

        target_to_gc_names.setdefault(tgt, []).append(gc_cname)

        # Stage 2 copula coefficient (unscaled if unscaled mode)
        gc_coef = float(s2_paths_map.get(tgt, {}).get(gc_cname, 0.0))
        orig_gc_coefs[gc_cname] = gc_coef

        endogeneity_tests.append({
            "source": src_name,
            "target": tgt_name,
            "path": f"{src_name} -> {tgt_name}",
            "gc_construct": gc_cname,
            "original": round(gc_coef, 4),
            "mean": None,
            "se": None,
            "t_stat": None,
            "p_value": None,
            "ci_lower": None,
            "ci_upper": None,
            "is_significant": False,
        })

        # Effect of correction on the structural relationship
        b_s1 = float(s1_paths.get(tgt, {}).get(src, 0.0))
        b_s2 = float(s2_paths_map.get(tgt, {}).get(src, 0.0))
        diff = b_s2 - b_s1

        effects_of_correction.append({
            "source": src_name,
            "target": tgt_name,
            "path": f"{src_name} -> {tgt_name}",
            "beta_s1": round(b_s1, 4),
            "beta_s2": round(b_s2, 4),
            "difference": round(diff, 4),
            "diff_se": None,
            "diff_ci_lower": None,
            "diff_ci_upper": None,
            "diff_pvalue": None,
        })

    # Initial Wald test structure (populated with bootstrap)
    wald_tests = compute_wald_test(orig_gc_coefs, {}, target_to_gc_names)

    # Assemble Gaussian Copula results dictionary
    gc_results = {
        "endogeneity_tests": endogeneity_tests,
        "wald_tests": wald_tests,
        "regressor_diagnostics": diagnostics,
        "effects_of_correction": effects_of_correction,
        "settings": {
            "ecdf": ecdf_choice,
            "copula_transform": transform_choice,
            "stage2_method": stage2_method,
            "round_decimals": round_decimals,
            "scale_normalization": scale_norm,
        },
        "target_to_gc_names": target_to_gc_names,
        "orig_gc_coefs": orig_gc_coefs,
    }

    # Store in res_s2
    res_s2["gaussian_copula"] = gc_results
    res_s2["vif"] = res_s2.get("structural", {}).get("inner_vif", {})
    res_s2["stage1"] = {
        "r_squared": res_s1.get("structural", {}).get("r_squared", {}),
        "path_coefficients": res_s1.get("structural", {}).get("path_coefficients", {}),
    }

    # Clean up single-item GC constructs from reliability and validity tables
    gc_names_set = {gc["gc_construct_name"] for gc in gcs}
    for table_key in ["construct_reliability", "reliability", "discriminant_validity", "htmt", "fornell_larcker"]:
        if table_key in res_s2:
            tab = res_s2[table_key]
            if isinstance(tab, dict):
                res_s2[table_key] = {k: v for k, v in tab.items() if k not in gc_names_set}

    rv = res_s2.get("reliability_and_validity")
    if isinstance(rv, dict):
        for sub_k in ["cronbachs_alpha", "composite_reliability", "rho_a", "ave"]:
            if isinstance(rv.get(sub_k), dict):
                rv[sub_k] = {k: v for k, v in rv[sub_k].items() if k not in gc_names_set}
        for sub_k in ["fornell_larcker", "htmt"]:
            if isinstance(rv.get(sub_k), dict):
                rv[sub_k] = {
                    k1: {k2: val for k2, val in sub_map.items() if k2 not in gc_names_set}
                    for k1, sub_map in rv[sub_k].items()
                    if k1 not in gc_names_set and isinstance(sub_map, dict)
                }

    return res_s2


def attach_bootstrap_to_copula(res: Dict[str, Any], boot_res: Dict[str, Any]) -> None:
    """
    Enriches Gaussian Copula results with bootstrap standard errors, t-stats,
    p-values, confidence intervals, difference tests, and Wald tests.
    """
    gc_data = res.get("gaussian_copula")
    if not isinstance(gc_data, dict):
        return

    param_summary = dict(boot_res.get("parameter_summary") or boot_res.get("parameters") or {})
    paths_list = boot_res.get("paths", [])
    if isinstance(paths_list, list):
        for p_item in paths_list:
            fc = p_item.get("from")
            tc = p_item.get("to")
            if fc and tc:
                param_summary[f"path:{fc}->{tc}"] = p_item

    boot_samples = boot_res.get("samples_dict") or boot_res.get("samples") or {}
    orig_gc_coefs = gc_data.get("orig_gc_coefs", {})
    target_to_gc_names = gc_data.get("target_to_gc_names", {})

    # 1. Enrich Endogeneity Tests
    for row in gc_data.get("endogeneity_tests", []):
        gc_name = row["gc_construct"]
        tgt = row["target"]
        pkey = f"path:{gc_name}->{tgt}"
        sig = param_summary.get(pkey) or param_summary.get(f"{gc_name} -> {tgt}")
        if sig:
            row["mean"] = round(float(sig.get("mean", row["original"])), 4)
            row["se"] = round(float(sig.get("se", 0.0)), 4)
            row["t_stat"] = round(float(sig.get("t_stat", 0.0)), 4)
            row["p_value"] = round(float(sig.get("p_value", 1.0)), 4)
            row["ci_lower"] = round(float(sig.get("ci_lower", 0.0)), 4)
            row["ci_upper"] = round(float(sig.get("ci_upper", 0.0)), 4)
            row["is_significant"] = bool(row["p_value"] < 0.05)

    # 2. Enrich Effect of Correction (Difference tests)
    for row in gc_data.get("effects_of_correction", []):
        src = row["source"]
        tgt = row["target"]
        diff_key = f"gc_diff:{src}->{tgt}"
        diff_samples = boot_samples.get(diff_key)
        if diff_samples is not None and len(diff_samples) > 0:
            diff_arr = np.asarray(diff_samples, dtype=float)
            se = float(np.std(diff_arr, ddof=1))
            ci_l = float(np.percentile(diff_arr, 2.5))
            ci_u = float(np.percentile(diff_arr, 97.5))
            t_st = float(row["difference"] / (se or 1e-9))
            p_v = float(2.0 * (1.0 - stats.norm.cdf(abs(t_st))))
            row["diff_se"] = round(se, 4)
            row["diff_ci_lower"] = round(ci_l, 4)
            row["diff_ci_upper"] = round(ci_u, 4)
            row["diff_pvalue"] = round(p_v, 4)

    # 3. Recompute Joint Wald Tests using empirical covariance across bootstrap resamples
    gc_data["wald_tests"] = compute_wald_test(
        orig_gc_coefs=orig_gc_coefs,
        boot_samples=boot_samples,
        target_to_gc_names=target_to_gc_names,
    )


# ---------------------------------------------------------------------------
# Backward Compatibility & Legacy Endpoints
# ---------------------------------------------------------------------------

def test_non_normality(scores: np.ndarray) -> Dict[str, Any]:
    """
    Tests whether the construct score distribution is significantly non-normal.
    Gaussian copulas require non-normal regressors (Park & Gupta 2012).
    """
    N = len(scores)
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
    """
    return copula_term(scores, ecdf="F4")


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
    Executes Gaussian Copula Endogeneity Analysis for legacy API endpoints.
    """
    from engine.pls.algorithm import run_pipeline

    spec_dict = spec.model_dump(mode="json", by_alias=True) if hasattr(spec, "model_dump") else (spec if isinstance(spec, dict) else {})
    cfg = settings or PipelineSettings()

    res_base = run_pipeline(df, spec_dict, cfg)
    scores = res_base.get("construct_scores", {})
    N = len(df)

    p_scores = np.asarray(scores.get(candidate_predictor, np.zeros(N)), dtype=float)
    y_scores = np.asarray(scores.get(target_construct, np.zeros(N)), dtype=float)

    paths = spec_dict.get("paths", [])
    pred_cids = [p.get("from") or p.get("from_node") for p in paths if (p.get("to") or p.get("to_node")) == target_construct]

    if candidate_predictor not in pred_cids:
        raise ValueError(f"Candidate '{candidate_predictor}' is not a direct predictor of '{target_construct}'.")

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

    X_base = np.column_stack([np.asarray(scores[c], dtype=float) for c in pred_cids])
    c_idx = pred_cids.index(candidate_predictor)

    coef_base, _, _, _ = np.linalg.lstsq(X_base, y_scores, rcond=None)
    orig_beta = float(coef_base[c_idx])

    c_copula = compute_copula_term(p_scores)
    X_ext = np.column_stack([X_base, c_copula])

    coef_ext, _, _, _ = np.linalg.lstsq(X_ext, y_scores, rcond=None)
    beta_with_copula = float(coef_ext[c_idx])
    copula_coef = float(coef_ext[-1])

    seeds = spawn_seeds(seed or 42, n_boot)
    boot_copula_coefs = np.zeros(n_boot, dtype=float)
    boot_beta_with = np.zeros(n_boot, dtype=float)

    for b in range(n_boot):
        if cancel_event and cancel_event.is_set():
            raise RuntimeError("Gaussian copula analysis cancelled by user.")
        b_rng = np.random.default_rng(seeds[b])
        resamp_idx = resample_indices(N, b_rng)

        df_b = df.iloc[resamp_idx]
        res_b = run_pipeline(df_b, spec_dict, cfg, _is_bootstrap=True)
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

