"""
Advanced Parallel Bootstrapping Engine for PLS-SEM (Section 11).
Implements complete textbook resampling and statistical inference:
- BOO-01..04: N-sample warning, cancellation, deterministic RNG spawning
- BOO-05: Basic vs Complete bootstrapping modes
- BOO-06/07: Sign indeterminacy correction (none, individual, construct-level)
- BOO-09/10: Student's t distribution with exact degrees of freedom (N - k - 1 / N - 1)
- BOO-11: Full parameter extraction (paths, loadings, weights, specific indirect, total indirect, total, HTMT, R2, f2, alpha, rho_A, CR, AVE)
- BOO-13: Percentile, Bias-Corrected, and BCa confidence intervals (jackknife accelerated)
- BOO-17/18: Raw samples matrix export and parameter histogram support
"""

import math
import os
import threading
from concurrent.futures import ProcessPoolExecutor, as_completed
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

import numpy as np
import pandas as pd
from scipy import stats

from core.rng import spawn_seeds
from engine.pls.ci import compute_all_confidence_intervals, bca_ci, percentile_ci, bias_corrected_ci
from engine.pls.effects import calculate_effects


def _extract_model_parameters(
    res: Dict[str, Any],
    spec_dict: Dict[str, Any],
    mode: str = "complete",
) -> Dict[str, float]:
    """
    Extracts a flat dictionary of parameter values from an estimation result.
    """
    params: Dict[str, float] = {}

    # 1. Path coefficients
    path_matrix = res.get("structural", {}).get("path_coefficients", {})
    paths = spec_dict.get("paths", [])
    for p in paths:
        from_c = p.get("from") or p.get("from_node")
        to_c = p.get("to") or p.get("to_node")
        val = path_matrix.get(to_c, {}).get(from_c, 0.0)
        params[f"path:{from_c}->{to_c}"] = float(val)

    # Capture all paths present in path_matrix (including interaction paths and auto-included moderator paths)
    for to_c, from_map in path_matrix.items():
        if isinstance(from_map, dict):
            for from_c, val in from_map.items():
                pkey = f"path:{from_c}->{to_c}"
                if pkey not in params:
                    params[pkey] = float(val)

    # Capture moderation simple slopes and conditional indirect effects
    mod_block = res.get("moderation", {})
    if isinstance(mod_block, dict):
        for me in mod_block.get("moderating_effects", []):
            s_name = me.get("source")
            m_name = me.get("moderator")
            t_name = me.get("target")
            int_name = me.get("interaction_term", f"{m_name} x {s_name}")
            for sl in me.get("simple_slopes", []):
                lvl_key = str(sl.get("moderator_level", "")).split(" ")[0]
                params[f"simple_slope:{int_name}->{t_name}:{lvl_key}"] = float(sl.get("slope", 0.0))
        for cie in mod_block.get("conditional_indirect_effects", []):
            chain_str = cie.get("chain", "")
            mod_str = cie.get("moderator", "")
            idx_val = cie.get("index_of_moderated_mediation", 0.0)
            params[f"index_of_moderated_mediation:{chain_str}({mod_str})"] = float(idx_val)
            for ce in cie.get("conditional_effects", []):
                lvl_key = str(ce.get("w_label", "")).split(" ")[0]
                params[f"cond_indirect:{chain_str}({mod_str}):{lvl_key}"] = float(ce.get("indirect_effect", 0.0))
                params[f"cond_direct:{chain_str}({mod_str}):{lvl_key}"] = float(ce.get("direct_effect", 0.0))
                params[f"cond_total:{chain_str}({mod_str}):{lvl_key}"] = float(ce.get("total_effect", 0.0))

    # 2. Outer loadings & weights
    meas = res.get("measurement", {})
    loadings = meas.get("outer_loadings", {})
    weights = meas.get("outer_weights", {})
    for cid, ind_map in loadings.items():
        for iid, l_val in ind_map.items():
            params[f"loading:{cid}->{iid}"] = float(l_val)
            w_val = weights.get(cid, {}).get(iid, 0.0)
            params[f"weight:{cid}->{iid}"] = float(w_val)

    # 3. Total effects & Indirect effects
    tot_effects = res.get("structural", {}).get("total_effects", {})
    if isinstance(tot_effects, dict):
        for to_c, from_map in tot_effects.items():
            if isinstance(from_map, dict):
                for from_c, val in from_map.items():
                    params[f"total_effect:{from_c}->{to_c}"] = float(val)

    effects_decomp = res.get("effects_decomposition", {})
    effects_summary = effects_decomp.get("effects_summary") or res.get("structural", {}).get("effects", [])
    for eff in effects_summary:
        if isinstance(eff, dict):
            fc = eff.get("from")
            tc = eff.get("to")
            if fc and tc:
                params[f"total_effect:{fc}->{tc}"] = float(eff.get("total", 0.0))
                params[f"total_indirect:{fc}->{tc}"] = float(eff.get("indirect", 0.0))
                params[f"direct_effect:{fc}->{tc}"] = float(eff.get("direct", 0.0))

    if mode == "basic":
        return params

    # 4. Total and specific indirect effects (Complete mode)
    ind_effects = res.get("structural", {}).get("indirect_effects", {})
    if isinstance(ind_effects, dict):
        for to_c, from_map in ind_effects.items():
            if isinstance(from_map, dict):
                for from_c, val in from_map.items():
                    params[f"total_indirect:{from_c}->{to_c}"] = float(val)

    for item in effects_decomp.get("specific_indirect", []):
        path_str = item.get("path")
        eff_val = item.get("effect", 0.0)
        params[f"specific_indirect:{path_str}"] = float(eff_val)

    # 5. R2 and Adjusted R2
    r2_map = res.get("structural", {}).get("r_squared", {})
    r2_adj_map = res.get("structural", {}).get("r_squared_adj", {})
    for cid, r2_val in r2_map.items():
        params[f"r2:{cid}"] = float(r2_val)
        if cid in r2_adj_map:
            params[f"r2_adj:{cid}"] = float(r2_adj_map[cid])

    # 6. f2 effect sizes
    f2_map = res.get("structural", {}).get("f_squared", {})
    for to_c, from_map in f2_map.items():
        for from_c, val in from_map.items():
            params[f"f2:{from_c}->{to_c}"] = float(val)

    # 7. Construct reliability (Cronbach alpha, rho_A, CR, AVE)
    rel = res.get("reliability_and_validity") or meas.get("reliability", {})
    alpha_map = rel.get("cronbachs_alpha") or rel.get("cronbach_alpha") or {}
    for cid, alpha_val in alpha_map.items():
        if alpha_val is not None:
            params[f"alpha:{cid}"] = float(alpha_val)
    for cid, rho_a_val in rel.get("rho_a", {}).items():
        if rho_a_val is not None:
            params[f"rho_a:{cid}"] = float(rho_a_val)
    for cid, cr_val in rel.get("composite_reliability", {}).items():
        if cr_val is not None:
            params[f"cr:{cid}"] = float(cr_val)
    for cid, ave_val in rel.get("ave", {}).items():
        if ave_val is not None:
            params[f"ave:{cid}"] = float(ave_val)

    # 8. HTMT matrix
    htmt_map = rel.get("htmt") or meas.get("htmt", {})
    for c1, c2_map in htmt_map.items():
        for c2, h_val in c2_map.items():
            if c1 != c2 and h_val is not None:
                pair_key = f"htmt:{sorted([c1, c2])[0]}<->{sorted([c1, c2])[1]}"
                params[pair_key] = float(h_val)

    return params


def _run_bootstrap_worker_chunk(
    seeds: List[int],
    data_matrix: np.ndarray,
    col_names: List[str],
    spec_dict: Dict[str, Any],
    scheme: str,
    max_iter: int,
    tol: float,
    mode: str,
    orig_params: Dict[str, float],
    sign_change: str,
) -> List[Dict[str, float]]:
    """
    Worker function executed across parallel processes.
    Generates bootstrap resamples and extracts parameter vectors.
    """
    from engine.pls.algorithm import PLSAlgorithm, run_pipeline

    algo = PLSAlgorithm(
        scheme=scheme,
        max_iter=max_iter,
        tol=tol,
        sign_alignment=(sign_change != "none"),
        missing_treatment="mean",
    )

    n_samples = data_matrix.shape[0]
    df_template = pd.DataFrame(data_matrix, columns=col_names)
    chunk_samples: List[Dict[str, float]] = []

    for s in seeds:
        rng = np.random.default_rng(s)
        indices = rng.choice(n_samples, size=n_samples, replace=True)
        resampled_df = df_template.iloc[indices].reset_index(drop=True)

        try:
            res = algo.fit(resampled_df, spec_dict)
            params = _extract_model_parameters(res, spec_dict, mode=mode)

            # Sign-change corrections
            if sign_change == "individual":
                # Flip each parameter's sign if opposite to original estimate
                for p_k, p_v in params.items():
                    orig_v = orig_params.get(p_k, 0.0)
                    if (orig_v > 0 and p_v < 0) or (orig_v < 0 and p_v > 0):
                        params[p_k] = -p_v

            elif sign_change == "construct":
                # Construct-level sign alignment based on sum of squared differences
                # S+ = sum (lambda_boot - lambda_orig)^2 vs S- = sum (-lambda_boot - lambda_orig)^2
                construct_signs: Dict[str, float] = {}
                constructs = spec_dict.get("constructs", [])
                for c in constructs:
                    cid = c.get("id")
                    s_plus = 0.0
                    s_minus = 0.0
                    for p_k, p_v in params.items():
                        if p_k.startswith(f"loading:{cid}->"):
                            orig_v = orig_params.get(p_k, 0.0)
                            s_plus += (p_v - orig_v) ** 2
                            s_minus += (-p_v - orig_v) ** 2
                    construct_signs[cid] = -1.0 if s_minus < s_plus else 1.0

                # Apply construct sign flips to loadings, weights, and paths
                for p_k in list(params.keys()):
                    if p_k.startswith("loading:") or p_k.startswith("weight:"):
                        cid = p_k.split(":")[1].split("->")[0]
                        params[p_k] *= construct_signs.get(cid, 1.0)
                    elif p_k.startswith("path:") or p_k.startswith("total_effect:") or p_k.startswith("total_indirect:"):
                        parts = p_k.split(":")[1].split("->")
                        from_c, to_c = parts[0], parts[1]
                        s_from = construct_signs.get(from_c, 1.0)
                        s_to = construct_signs.get(to_c, 1.0)
                        params[p_k] *= (s_from * s_to)

            chunk_samples.append(params)
        except Exception:
            continue

    return chunk_samples


def compute_jackknife_parameters(
    df: pd.DataFrame,
    spec_dict: Dict[str, Any],
    scheme: str = "path",
    max_iter: int = 300,
    tol: float = 1e-7,
    mode: str = "complete",
) -> Dict[str, np.ndarray]:
    """
    Computes leave-one-out Jackknife estimates for each parameter (BOO-13 BCa acceleration).
    """
    from engine.pls.algorithm import PLSAlgorithm

    algo = PLSAlgorithm(scheme=scheme, max_iter=max_iter, tol=tol, missing_treatment="mean")
    df_clean = df.reset_index(drop=True)
    n = len(df_clean)
    param_collect: Dict[str, List[float]] = {}

    for i in range(n):
        df_jack = df_clean.drop(index=i).reset_index(drop=True)
        try:
            res_jack = algo.fit(df_jack, spec_dict)
            params = _extract_model_parameters(res_jack, spec_dict, mode=mode)
            for k, v in params.items():
                if k not in param_collect:
                    param_collect[k] = []
                param_collect[k].append(v)
        except Exception:
            continue

    return {k: np.array(v, dtype=float) for k, v in param_collect.items()}


class ParallelBootstrapper:
    """
    Upgraded Parallel Bootstrapping Engine (Section 11).
    Supports basic/complete modes, BCa confidence intervals, sign corrections,
    exact t-test degrees of freedom, and sample exports.
    """

    def __init__(
        self,
        n_workers: Optional[int] = None,
        chunk_size: int = 25,
    ):
        self.n_workers = n_workers or max(1, (os.cpu_count() or 4) - 1)
        self.chunk_size = chunk_size

    def run(
        self,
        data: pd.DataFrame,
        model_spec: Any,
        n_boot: int = 5000,
        seed: Optional[int] = 42,
        scheme: str = "path",
        max_iter: int = 300,
        tol: float = 1e-7,
        mode: str = "complete",  # "basic" or "complete"
        sign_change: str = "none",  # "none", "individual", "construct"
        test_distribution: str = "t",  # "t" or "normal"
        significance_level: float = 0.05,
        tails: str = "two",  # "two" or "one"
        ci_method: str = "bca",  # "percentile", "bias_corrected", "bca"
        progress_callback: Optional[Callable[[int, int], None]] = None,
        cancel_event: Optional[threading.Event] = None,
        sign_alignment: Optional[bool] = None,
        alpha: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Executes bootstrapping pipeline across worker processes.
        """
        if alpha is not None:
            significance_level = alpha
        if sign_alignment is not None and sign_change == "none":
            sign_change = "construct" if sign_alignment else "none"
        from engine.pls.algorithm import PLSAlgorithm

        spec_dict = model_spec.model_dump(mode="json", by_alias=True) if hasattr(model_spec, "model_dump") else (model_spec if isinstance(model_spec, dict) else {})

        base_algo = PLSAlgorithm(
            scheme=scheme,
            max_iter=max_iter,
            tol=tol,
            sign_alignment=(sign_change != "none"),
            missing_treatment="mean",
        )
        base_res = base_algo.fit(data, model_spec)
        orig_params = _extract_model_parameters(base_res, spec_dict, mode=mode)

        # Parse constructs and clean indicators
        constructs, ind_col_map, paths = base_algo._parse_spec(model_spec)
        all_required_cols = []
        for c in constructs.values():
            for iid in c["indicators"]:
                col = ind_col_map.get(iid, iid)
                all_required_cols.append(col)

        sub_df = data[all_required_cols].copy()
        for col in all_required_cols:
            sub_df[col] = pd.to_numeric(sub_df[col], errors="coerce")
            sub_df[col] = sub_df[col].replace([-99, "-99"], np.nan)
            col_mean = sub_df[col].mean()
            if pd.notna(col_mean):
                sub_df[col] = sub_df[col].fillna(col_mean)
        sub_df = sub_df.dropna()

        N = len(sub_df)
        data_matrix = sub_df.to_numpy(dtype=float)
        col_names = list(sub_df.columns)

        # 1. Deterministic seeds across workers (core/rng.py)
        all_seeds = spawn_seeds(seed, n_boot)

        chunk_size = max(5, min(self.chunk_size, math.ceil(n_boot / (self.n_workers * 4))))
        seed_chunks = [all_seeds[i : i + chunk_size] for i in range(0, n_boot, chunk_size)]

        all_sample_dicts: List[Dict[str, float]] = []
        completed_count = 0

        # 2. Parallel execution
        with ProcessPoolExecutor(max_workers=self.n_workers) as executor:
            future_to_chunk = {
                executor.submit(
                    _run_bootstrap_worker_chunk,
                    chunk,
                    data_matrix,
                    col_names,
                    spec_dict,
                    scheme,
                    max_iter,
                    tol,
                    mode,
                    orig_params,
                    sign_change,
                ): len(chunk)
                for chunk in seed_chunks
            }

            for future in as_completed(future_to_chunk):
                if cancel_event is not None and cancel_event.is_set():
                    executor.shutdown(wait=False, cancel_futures=True)
                    raise InterruptedError("Bootstrapping was cancelled by the user.")

                chunk_len = future_to_chunk[future]
                try:
                    resample_results = future.result()
                    all_sample_dicts.extend(resample_results)
                except Exception as exc:
                    print(f"Bootstrap chunk failed: {exc}")

                completed_count += chunk_len
                if progress_callback:
                    progress_callback(min(completed_count, n_boot), n_boot)

        # 3. Calculate Jackknife estimates if BCa is requested
        jackknife_dict: Dict[str, np.ndarray] = {}
        if ci_method == "bca" and N <= 500:
            jackknife_dict = compute_jackknife_parameters(
                sub_df, spec_dict, scheme=scheme, max_iter=max_iter, tol=tol, mode=mode
            )

        # 4. Count predictors for degrees of freedom calculation (BOO-09)
        # For paths into target: df = N - k - 1
        predictor_counts: Dict[str, int] = {}
        for p in paths:
            to_c = p.get("to") or p.get("to_node") if isinstance(p, dict) else p[1]
            predictor_counts[to_c] = predictor_counts.get(to_c, 0) + 1

        # 5. Summarize statistical metrics per parameter
        param_keys = list(orig_params.keys())
        summarized_parameters: Dict[str, Dict[str, Any]] = {}
        samples_matrix: Dict[str, List[float]] = {k: [] for k in param_keys}

        for s_dict in all_sample_dicts:
            for k in param_keys:
                if k in s_dict:
                    samples_matrix[k].append(s_dict[k])

        for k in param_keys:
            dist = np.array(samples_matrix[k], dtype=float)
            orig_val = float(orig_params.get(k, 0.0))

            if len(dist) == 0:
                summarized_parameters[k] = {
                    "original": orig_val,
                    "mean": orig_val,
                    "se": 0.0,
                    "t_stat": 0.0,
                    "p_value": 1.0,
                    "ci_low": orig_val,
                    "ci_high": orig_val,
                    "significance": "ns",
                    "df": N - 1,
                }
                continue

            se = float(np.std(dist, ddof=1))
            t_stat = float(orig_val / se) if se > 1e-9 else 0.0

            # Determine degrees of freedom (BOO-09)
            if k.startswith("path:"):
                target_c = k.split(":")[1].split("->")[1]
                k_pred = predictor_counts.get(target_c, 1)
                df_val = max(1, N - k_pred - 1)
            else:
                df_val = max(1, N - 1)

            # Compute p-value
            if test_distribution == "t":
                if tails == "one":
                    p_val = float(1.0 - stats.t.cdf(t_stat, df=df_val))
                else:
                    p_val = float(2.0 * (1.0 - stats.t.cdf(abs(t_stat), df=df_val)))
            else:
                if tails == "one":
                    p_val = float(1.0 - stats.norm.cdf(t_stat))
                else:
                    p_val = float(2.0 * (1.0 - stats.norm.cdf(abs(t_stat))))

            # Confidence intervals
            all_cis = compute_all_confidence_intervals(
                original_val=orig_val,
                sample_dist=dist,
                jackknife_vals=jackknife_dict.get(k),
                alpha=significance_level,
                tails=tails,
            )
            chosen_ci = all_cis.get(ci_method, all_cis["percentile"])

            sig = "***" if p_val < 0.001 else ("**" if p_val < 0.01 else ("*" if p_val < significance_level else "ns"))

            summarized_parameters[k] = {
                "original": orig_val,
                "mean": float(np.mean(dist)),
                "se": se,
                "t_stat": t_stat,
                "p_value": p_val,
                "ci_low": chosen_ci[0],
                "ci_high": chosen_ci[1],
                "confidence_intervals": all_cis,
                "significance": sig,
                "df": df_val,
            }

        # 6. Organize categorized output tables
        construct_names = base_res.get("construct_names", {})
        indicator_names = base_res.get("indicator_names", {})

        path_significance = []
        seen_path_keys = set()
        for p in paths:
            from_c = p.get("from") or p.get("from_node") if isinstance(p, dict) else p[0]
            to_c = p.get("to") or p.get("to_node") if isinstance(p, dict) else p[1]
            k = f"path:{from_c}->{to_c}"
            seen_path_keys.add(k)
            st = summarized_parameters.get(k, {})
            st_copy = dict(st)
            st_copy["from"] = from_c
            st_copy["to"] = to_c
            st_copy["from_name"] = construct_names.get(from_c, from_c)
            st_copy["to_name"] = construct_names.get(to_c, to_c)
            path_significance.append(st_copy)

        # Include any additional paths (e.g. interaction paths and implied direct paths)
        for k, st in summarized_parameters.items():
            if k.startswith("path:") and k not in seen_path_keys:
                seen_path_keys.add(k)
                parts = k[5:].split("->")
                if len(parts) == 2:
                    from_c, to_c = parts[0], parts[1]
                    st_copy = dict(st)
                    st_copy["from"] = from_c
                    st_copy["to"] = to_c
                    st_copy["from_name"] = construct_names.get(from_c, from_c)
                    st_copy["to_name"] = construct_names.get(to_c, to_c)
                    path_significance.append(st_copy)

        loading_significance = []
        weight_significance = []
        for cid, cinfo in constructs.items():
            for iid in cinfo["indicators"]:
                l_k = f"loading:{cid}->{iid}"
                if l_k in summarized_parameters:
                    l_st = dict(summarized_parameters[l_k])
                    l_st["construct"] = cid
                    l_st["construct_name"] = construct_names.get(cid, cid)
                    l_st["indicator"] = iid
                    l_st["indicator_name"] = indicator_names.get(iid, iid)
                    loading_significance.append(l_st)

                w_k = f"weight:{cid}->{iid}"
                if w_k in summarized_parameters:
                    w_st = dict(summarized_parameters[w_k])
                    w_st["construct"] = cid
                    w_st["construct_name"] = construct_names.get(cid, cid)
                    w_st["indicator"] = iid
                    w_st["indicator_name"] = indicator_names.get(iid, iid)
                    weight_significance.append(w_st)

        # Specific indirect effects
        indirect_significance = []
        for k, v in summarized_parameters.items():
            if k.startswith("specific_indirect:") or k.startswith("total_indirect:"):
                st_copy = dict(v)
                st_copy["parameter"] = k
                indirect_significance.append(st_copy)

        # 2D samples array [n_samples, n_params] for contrasts, MGA, histograms
        if param_keys and len(all_sample_dicts) > 0:
            samples_2d = np.column_stack([np.array(samples_matrix[k], dtype=float) for k in param_keys])
        else:
            samples_2d = np.empty((0, 0))

        return {
            "n_boot": n_boot,
            "actual_samples": len(all_sample_dicts),
            "settings": {
                "mode": mode,
                "sign_change": sign_change,
                "test_distribution": test_distribution,
                "significance_level": significance_level,
                "tails": tails,
                "ci_method": ci_method,
            },
            "parameters": summarized_parameters,
            "parameter_summary": summarized_parameters,
            "paths": path_significance,
            "loadings": loading_significance,
            "weights": weight_significance,
            "indirect_effects": indirect_significance,
            "samples_matrix": samples_2d,
            "samples_dict": samples_matrix,
            "parameter_names": param_keys,
        }
