"""
CSPLS SmartPLS-4 Style Moderation & Moderated Mediation Engine.
Implements:
- Multiple moderators on multiple paths (including shared paths and shared moderators)
- Automatic inclusion of direct paths (moderator -> outcome) without duplicates
- Three interaction term methods:
  1. Two-Stage (Hair et al. 2022; stage 1 main effects, stage 2 single-item products)
  2. Product-Indicator (all pairs of standardized indicators)
  3. Orthogonalizing (regressing product indicators on main-effect indicators, using residuals)
- Support for endogenous predictors (constructs that are both outcomes and predictors)
- Simple slope analysis (-1 SD, Mean, +1 SD) per moderation, line plot points, bootstrap inference
- Kenny (2016) moderation effect sizes f^2 per interaction (0.005 small, 0.010 medium, 0.025 large)
- Moderated Mediation (PROCESS-style conditional indirect effects & index of moderated mediation)
- Bootstrap inference with full-pipeline re-estimation per resample
"""

from typing import List, Dict, Any, Optional, Tuple, Union
import copy
import math
import time
import numpy as np
import pandas as pd
from scipy import stats

from core.settings_schema import PipelineSettings
from engine.pls.ci import percentile_ci, bca_ci


def standardize_series(s: Union[np.ndarray, pd.Series, List[float]], ddof: int = 1) -> np.ndarray:
    """Standardizes a series to mean 0 and unit variance (sample SD by default, ddof=1)."""
    arr = np.asarray(s, dtype=float)
    m = np.nanmean(arr)
    sd = np.nanstd(arr, ddof=ddof)
    if sd == 0 or np.isnan(sd):
        sd = 1.0
    return (arr - m) / sd


def compute_simple_slopes(
    beta_source: float,
    beta_moderator: float,
    beta_interaction: float,
    boot_samples: Optional[np.ndarray] = None,
    source_idx: Optional[int] = None,
    int_idx: Optional[int] = None,
    boot_source_reps: Optional[np.ndarray] = None,
    boot_int_reps: Optional[np.ndarray] = None,
    alpha: float = 0.05,
) -> Dict[str, Any]:
    """
    Computes simple slopes of target on source at 3 moderator levels:
    - 1 SD below mean (m = -1.0)
    - At mean (m = 0.0)
    - 1 SD above mean (m = +1.0)
    Includes line data for plotting x in [-2, 2] SD and bootstrap CIs.
    Guarantees slope(+1) - slope(-1) == 2 * beta_interaction.
    """
    levels = [-1.0, 0.0, 1.0]
    level_names = ["-1 SD (Low)", "Mean (Average)", "+1 SD (High)"]
    x_grid = np.linspace(-2.0, 2.0, 21).tolist()

    # Resolve bootstrap replicate vectors if provided
    rep_source = None
    rep_int = None
    if boot_source_reps is not None and boot_int_reps is not None:
        rep_source = np.asarray(boot_source_reps, dtype=float)
        rep_int = np.asarray(boot_int_reps, dtype=float)
    elif boot_samples is not None and source_idx is not None and int_idx is not None:
        boot_samples_arr = np.asarray(boot_samples)
        if boot_samples_arr.ndim == 2 and boot_samples_arr.shape[0] > 0:
            rep_source = boot_samples_arr[:, source_idx]
            rep_int = boot_samples_arr[:, int_idx]

    slopes_data = []
    for m_val, m_name in zip(levels, level_names):
        slope = float(beta_source + beta_interaction * m_val)
        # Prediction line: y = (beta_source + beta_interaction * m) * x + beta_moderator * m
        y_vals = [(slope * x + beta_moderator * m_val) for x in x_grid]

        se_slope = None
        t_slope = None
        p_slope = None
        ci_lower = None
        ci_upper = None

        if rep_source is not None and rep_int is not None and len(rep_source) > 0:
            rep_slopes = rep_source + rep_int * m_val
            se_slope = float(np.std(rep_slopes, ddof=1))
            t_slope = (slope / se_slope) if se_slope > 1e-12 else 0.0
            p_slope = float(2.0 * (1.0 - stats.norm.cdf(abs(t_slope))))
            ci_lower = float(np.percentile(rep_slopes, 100 * (alpha / 2)))
            ci_upper = float(np.percentile(rep_slopes, 100 * (1.0 - alpha / 2)))

        slopes_data.append({
            "moderator_level": m_name,
            "moderator_value": m_val,
            "slope": round(float(slope), 6),
            "standard_error": round(float(se_slope), 6) if se_slope is not None else None,
            "t_statistic": round(float(t_slope), 4) if t_slope is not None else None,
            "p_value": round(float(p_slope), 6) if p_slope is not None else None,
            "ci_lower": round(float(ci_lower), 6) if ci_lower is not None else None,
            "ci_upper": round(float(ci_upper), 6) if ci_upper is not None else None,
            "line_points": [{"x": round(x, 2), "y": round(y, 6)} for x, y in zip(x_grid, y_vals)],
        })

    return {
        "x_range": [-2.0, 2.0],
        "simple_slopes": slopes_data,
    }


def calculate_moderation_f2(
    r2_with_interaction: float,
    r2_without_interaction: float,
) -> Dict[str, Any]:
    """
    Calculates moderation effect size f^2 = (R2_incl - R2_excl) / (1 - R2_incl).
    Evaluated using Kenny (2016) thresholds: 0.005 (small), 0.010 (medium), 0.025 (large).
    """
    denom = max(1e-12, 1.0 - float(r2_with_interaction))
    f2_val = max(0.0, (float(r2_with_interaction) - float(r2_without_interaction)) / denom)

    if f2_val >= 0.025:
        magnitude = "large"
    elif f2_val >= 0.010:
        magnitude = "medium"
    elif f2_val >= 0.005:
        magnitude = "small"
    else:
        magnitude = "none"

    return {
        "f_squared": round(float(f2_val), 4),
        "magnitude": magnitude,
        "r_squared_included": round(float(r2_with_interaction), 4),
        "r_squared_excluded": round(float(r2_without_interaction), 4),
        "thresholds": {"small": 0.005, "medium": 0.010, "large": 0.025},
        "note": "Kenny (2016) thresholds for moderation: 0.005 (small), 0.010 (medium), 0.025 (large).",
    }


def normalize_moderation_spec(
    model_spec: Union[Dict[str, Any], Any]
) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """
    Extracts and standardizes the moderation list from a ModelSpec or dictionary.
    Returns (spec_dict, list_of_moderations).
    """
    if hasattr(model_spec, "model_dump"):
        spec_dict = model_spec.model_dump(mode="json", by_alias=True)
    elif isinstance(model_spec, dict):
        spec_dict = copy.deepcopy(model_spec)
    else:
        raise TypeError("model_spec must be a ModelSpec instance or dictionary")

    raw_mods = spec_dict.get("moderating_effects", [])
    moderations = []
    seen = set()

    for idx, m in enumerate(raw_mods):
        if hasattr(m, "model_dump"):
            m_dict = m.model_dump(mode="json", by_alias=True)
        elif isinstance(m, dict):
            m_dict = dict(m)
        else:
            m_dict = {
                "moderator": getattr(m, "moderator", getattr(m, "moderator_lv", "")),
                "source": getattr(m, "source", getattr(m, "predictor", getattr(m, "predictor_lv", ""))),
                "target": getattr(m, "target", getattr(m, "outcome", getattr(m, "outcome_lv", ""))),
                "method": getattr(m, "method", "two_stage"),
                "standardize": getattr(m, "standardize", True),
                "id": getattr(m, "id", f"mod_{idx}"),
            }

        mod_lv = str(m_dict.get("moderator") or m_dict.get("moderator_lv") or "").strip()
        pred_lv = str(m_dict.get("source") or m_dict.get("predictor") or m_dict.get("predictor_lv") or "").strip()
        out_lv = str(m_dict.get("target") or m_dict.get("outcome") or m_dict.get("outcome_lv") or "").strip()
        method = str(m_dict.get("method") or "two_stage").lower()
        standardize = bool(m_dict.get("standardize", True))
        mod_id = str(m_dict.get("id") or f"mod_{pred_lv}_{mod_lv}_{out_lv}")

        triple = (mod_lv, pred_lv, out_lv)
        if not mod_lv or not pred_lv or not out_lv:
            continue
        if triple in seen:
            continue
        seen.add(triple)

        int_name = f"{mod_lv} x {pred_lv}"
        moderations.append({
            "id": mod_id,
            "moderator": mod_lv,
            "source": pred_lv,
            "target": out_lv,
            "method": method,
            "standardize": standardize,
            "interaction_term": int_name,
        })

    return spec_dict, moderations


def build_interaction_indicators_for_df(
    df: pd.DataFrame,
    spec_dict: Dict[str, Any],
    moderation: Dict[str, Any],
) -> Tuple[pd.DataFrame, List[str]]:
    """
    Generates interaction indicators for Product Indicator or Orthogonalizing methods.
    Returns (df_with_new_cols, list_of_indicator_col_names).
    """
    df_out = df.copy()
    pred_lv = moderation["source"]
    mod_lv = moderation["moderator"]
    method = moderation["method"]
    standardize = moderation["standardize"]

    # Resolve indicators for predictor and moderator
    constructs = {c["id"]: c for c in spec_dict.get("constructs", [])}
    indicators_meta = spec_dict.get("indicators", [])
    ind_to_col = {}
    for ind in indicators_meta:
        iid = ind.get("id") or ind.get("name") or ind.get("column")
        col = ind.get("column") or ind.get("name") or iid
        ind_to_col[iid] = col

    pred_c = constructs.get(pred_lv, {})
    mod_c = constructs.get(mod_lv, {})

    pred_inds = [ind_to_col.get(i, i) for i in pred_c.get("indicators", []) if ind_to_col.get(i, i) in df_out.columns]
    mod_inds = [ind_to_col.get(i, i) for i in mod_c.get("indicators", []) if ind_to_col.get(i, i) in df_out.columns]

    if not pred_inds or not mod_inds:
        raise ValueError(f"Cannot generate interaction indicators: Missing indicators for {pred_lv} or {mod_lv}.")

    # Pre-standardize all main effect indicators
    pred_data = {}
    for pi in pred_inds:
        val = pd.to_numeric(df_out[pi], errors="coerce").to_numpy(dtype=float)
        pred_data[pi] = standardize_series(val, ddof=1) if standardize else val

    mod_data = {}
    for mi in mod_inds:
        val = pd.to_numeric(df_out[mi], errors="coerce").to_numpy(dtype=float)
        mod_data[mi] = standardize_series(val, ddof=1) if standardize else val

    # Build basis matrix if orthogonalizing
    X_basis = None
    if method == "orthogonalizing":
        basis_cols = []
        for pi in pred_inds:
            basis_cols.append(pred_data[pi])
        for mi in mod_inds:
            basis_cols.append(mod_data[mi])
        X_mat = np.column_stack(basis_cols)
        # Add intercept column
        X_basis = np.column_stack([np.ones(len(df_out)), X_mat])

    product_cols = []
    for pi in pred_inds:
        for mi in mod_inds:
            col_name = f"prod_{pred_lv}_{mod_lv}_{pi}_{mi}"
            raw_prod = pred_data[pi] * mod_data[mi]

            if method == "orthogonalizing" and X_basis is not None:
                # Regress raw_prod on all predictor & moderator indicators with intercept
                try:
                    coef, _, _, _ = np.linalg.lstsq(X_basis, raw_prod, rcond=None)
                    raw_prod = raw_prod - (X_basis @ coef)
                except Exception:
                    pass

            prod_val = standardize_series(raw_prod, ddof=1) if standardize else raw_prod
            df_out[col_name] = prod_val
            product_cols.append(col_name)

    return df_out, product_cols


def detect_moderated_mediation_chains(
    paths: List[Tuple[str, str]],
    moderations: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Automatically detects all mediation chains A -> B -> C where at least one of
    (A -> B) or (B -> C) is moderated.
    """
    path_set = set(paths)
    chains = []

    # Map (source, target) -> list of moderations
    mod_map: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}
    for m in moderations:
        pair = (m["source"], m["target"])
        mod_map.setdefault(pair, []).append(m)

    # Find 2-step paths A -> B -> C
    all_sources = {p[0] for p in paths}
    for a, b in paths:
        for b_cand, c in paths:
            if b_cand == b and c != a and c != b and a != b:
                # Chain A -> B -> C found
                mods_a = mod_map.get((a, b), [])
                mods_b = mod_map.get((b, c), [])
                if not mods_a and not mods_b:
                    continue

                # Collect all distinct moderators involved in this chain
                moderators_involved = set([m["moderator"] for m in mods_a] + [m["moderator"] for m in mods_b])
                for w in moderators_involved:
                    a_mod = any(m["moderator"] == w for m in mods_a)
                    b_mod = any(m["moderator"] == w for m in mods_b)
                    direct_mods = mod_map.get((a, c), [])
                    dir_mod = any(m["moderator"] == w for m in direct_mods)
                    has_direct = (a, c) in path_set

                    chain_key = f"{a}->{b}->{c}(mod:{w})"
                    chains.append({
                        "key": chain_key,
                        "antecedent": a,
                        "mediator": b,
                        "target": c,
                        "moderator": w,
                        "a_path_moderated": a_mod,
                        "b_path_moderated": b_mod,
                        "has_direct_path": has_direct,
                        "direct_moderated": dir_mod,
                        "interaction_a": f"{w} x {a}" if a_mod else None,
                        "interaction_b": f"{w} x {b}" if b_mod else None,
                        "interaction_direct": f"{w} x {a}" if dir_mod else None,
                    })

    return chains


def compute_conditional_indirect_effects(
    chains: List[Dict[str, Any]],
    path_matrix: Dict[str, Dict[str, float]],
    boot_coef_reps: Optional[Dict[str, np.ndarray]] = None,
    alpha: float = 0.05,
) -> List[Dict[str, Any]]:
    """
    Computes conditional indirect effects and index of moderated mediation for detected chains.
    Formulas:
      a-path moderated: indirect(w) = (a1 + a3*w) * b, index = a3 * b
      b-path moderated: indirect(w) = a * (b1 + b3*w), index = a * b3
      both moderated:   indirect(w) = (a1 + a3*w) * (b1 + b3*w), index(w) = a3*b1 + a1*b3 + 2*a3*b3*w, curvature = a3*b3
    """
    results = []
    w_levels = [-1.0, 0.0, 1.0]
    w_names = ["-1 SD (Low)", "Mean (Average)", "+1 SD (High)"]

    for ch in chains:
        a = ch["antecedent"]
        b = ch["mediator"]
        c = ch["target"]
        w = ch["moderator"]
        a_mod = ch["a_path_moderated"]
        b_mod = ch["b_path_moderated"]
        dir_mod = ch["direct_moderated"]
        has_dir = ch["has_direct_path"]

        # Extract point estimates
        a1 = float(path_matrix.get(b, {}).get(a, 0.0))
        a3 = float(path_matrix.get(b, {}).get(ch["interaction_a"], 0.0)) if a_mod else 0.0
        b1 = float(path_matrix.get(c, {}).get(b, 0.0))
        b3 = float(path_matrix.get(c, {}).get(ch["interaction_b"], 0.0)) if b_mod else 0.0
        c1 = float(path_matrix.get(c, {}).get(a, 0.0)) if has_dir else 0.0
        c3 = float(path_matrix.get(c, {}).get(ch["interaction_direct"], 0.0)) if dir_mod else 0.0

        # Conditional indirect effects at w
        cond_effects = []
        for w_val, w_label in zip(w_levels, w_names):
            eff_a = a1 + a3 * w_val
            eff_b = b1 + b3 * w_val
            ind_val = eff_a * eff_b
            dir_val = (c1 + c3 * w_val) if has_dir else 0.0
            tot_val = ind_val + dir_val
            cond_effects.append({
                "w_value": w_val,
                "w_label": w_label,
                "indirect_effect": float(ind_val),
                "direct_effect": float(dir_val),
                "total_effect": float(tot_val),
            })

        # Index of moderated mediation
        if a_mod and not b_mod:
            index_type = "linear"
            index_point = a3 * b1
            index_w = {"-1 SD": index_point, "Mean": index_point, "+1 SD": index_point}
            curvature = 0.0
        elif b_mod and not a_mod:
            index_type = "linear"
            index_point = a1 * b3
            index_w = {"-1 SD": index_point, "Mean": index_point, "+1 SD": index_point}
            curvature = 0.0
        else:
            # Both paths moderated
            index_type = "quadratic"
            curvature = a3 * b3
            index_point = a3 * b1 + a1 * b3  # at mean w=0
            index_w = {
                "-1 SD": (a3 * b1 + a1 * b3 - 2 * curvature),
                "Mean": (a3 * b1 + a1 * b3),
                "+1 SD": (a3 * b1 + a1 * b3 + 2 * curvature),
            }

        # Bootstrap statistics if replicate arrays available
        boot_stats: Dict[str, Any] = {}
        if boot_coef_reps is not None:
            n_reps = len(next(iter(boot_coef_reps.values())))
            rep_a1 = boot_coef_reps.get(f"path:{a}->{b}", np.zeros(n_reps))
            rep_a3 = boot_coef_reps.get(f"path:{ch['interaction_a']}->{b}", np.zeros(n_reps)) if a_mod else np.zeros(n_reps)
            rep_b1 = boot_coef_reps.get(f"path:{c}->{b}" if f"path:{c}->{b}" in boot_coef_reps else f"path:{b}->{c}", np.zeros(n_reps))
            if f"path:{b}->{c}" in boot_coef_reps:
                rep_b1 = boot_coef_reps[f"path:{b}->{c}"]
            rep_b3 = boot_coef_reps.get(f"path:{ch['interaction_b']}->{c}", np.zeros(n_reps)) if b_mod else np.zeros(n_reps)

            # Replicate index
            if a_mod and not b_mod:
                rep_index = rep_a3 * rep_b1
            elif b_mod and not a_mod:
                rep_index = rep_a1 * rep_b3
            else:
                rep_index = rep_a3 * rep_b1 + rep_a1 * rep_b3

            se_idx = float(np.std(rep_index, ddof=1))
            t_idx = (index_point / se_idx) if se_idx > 1e-12 else 0.0
            p_idx = float(2.0 * (1.0 - stats.norm.cdf(abs(t_idx))))
            ci_low = float(np.percentile(rep_index, 100 * (alpha / 2)))
            ci_high = float(np.percentile(rep_index, 100 * (1.0 - alpha / 2)))

            boot_stats = {
                "index_point": round(float(index_point), 6),
                "index_se": round(float(se_idx), 6),
                "index_t": round(float(t_idx), 4),
                "index_p_value": round(float(p_idx), 6),
                "index_ci_lower": round(float(ci_low), 6),
                "index_ci_upper": round(float(ci_high), 6),
                "index_significant": bool(ci_low > 0 or ci_high < 0),
            }

            # Also compute bootstrap CI for indirect effects at each level
            for item in cond_effects:
                w_val = item["w_value"]
                rep_ind_w = (rep_a1 + rep_a3 * w_val) * (rep_b1 + rep_b3 * w_val)
                se_w = float(np.std(rep_ind_w, ddof=1))
                t_w = (item["indirect_effect"] / se_w) if se_w > 1e-12 else 0.0
                p_w = float(2.0 * (1.0 - stats.norm.cdf(abs(t_w))))
                ci_l_w = float(np.percentile(rep_ind_w, 100 * (alpha / 2)))
                ci_u_w = float(np.percentile(rep_ind_w, 100 * (1.0 - alpha / 2)))
                item.update({
                    "se": round(se_w, 6),
                    "t_statistic": round(t_w, 4),
                    "p_value": round(p_w, 6),
                    "ci_lower": round(ci_l_w, 6),
                    "ci_upper": round(ci_u_w, 6),
                    "is_significant": bool(ci_l_w > 0 or ci_u_w < 0),
                })

        results.append({
            "chain": f"{a} -> {b} -> {c}",
            "moderator": w,
            "a_path_moderated": a_mod,
            "b_path_moderated": b_mod,
            "direct_path_moderated": dir_mod,
            "index_type": index_type,
            "index_of_moderated_mediation": float(index_point),
            "index_at_w": {k: float(v) for k, v in index_w.items()},
            "curvature": float(curvature),
            "conditional_effects": cond_effects,
            "bootstrap_inference": boot_stats if boot_stats else None,
        })

    return results


def run_expanded_pls_estimation(
    df: pd.DataFrame,
    spec_dict: Dict[str, Any],
    moderations: List[Dict[str, Any]],
    settings: Optional[PipelineSettings] = None,
    save_stage1_meas: bool = True,
) -> Dict[str, Any]:
    """
    Executes model expansion and estimation for single or multiple moderations.
    Supports Two-Stage, Product-Indicator, and Orthogonalizing methods.
    """
    from engine.pls.algorithm import run_pipeline, parse_model_spec

    cfg = settings or PipelineSettings()

    if not moderations:
        # Standard estimation without moderation
        return run_pipeline(df, spec_dict, cfg)

    # Determine predominant method across moderations (or per-moderation)
    has_two_stage = any(m.get("method") == "two_stage" for m in moderations)

    if has_two_stage:
        # --- TWO-STAGE APPROACH ---
        # Stage 1: Main effects model (including all implied moderator -> outcome paths)
        stage1_spec = copy.deepcopy(spec_dict)
        stage1_paths = list(stage1_spec.get("paths", []))
        existing_path_pairs = set(
            ((p.get("from") or p.get("from_node")), (p.get("to") or p.get("to_node")))
            for p in stage1_paths
        )

        # Silently add all moderator -> outcome direct paths
        for m in moderations:
            pair = (m["moderator"], m["target"])
            if pair not in existing_path_pairs:
                stage1_paths.append({"from": m["moderator"], "to": m["target"]})
                existing_path_pairs.add(pair)
        stage1_spec["paths"] = stage1_paths

        # Estimate Stage 1
        res_stage1 = run_pipeline(df, stage1_spec, cfg)
        scores_stage1 = res_stage1.get("construct_scores", {})
        n_obs = len(df)

        # Stage 2: Build single-item data & specification from Stage 1 latent scores
        df_stage2 = pd.DataFrame(index=df.index)
        stage2_constructs = []
        stage2_indicators = []

        # All stage 1 constructs become single-item constructs measured by their stage-1 score
        for c in stage1_spec.get("constructs", []):
            cid = c["id"]
            c_score = np.asarray(scores_stage1.get(cid, np.zeros(n_obs)), dtype=float)
            col_name = f"lv_{cid}"
            df_stage2[col_name] = c_score
            stage2_constructs.append({
                "id": cid,
                "name": c.get("name", cid),
                "type": "reflective",
                "indicators": [col_name],
                "outer_mode": "A",
            })
            stage2_indicators.append({
                "id": col_name,
                "column": col_name,
                "construct_id": cid,
            })

        # Build interaction constructs from stage-1 scores
        stage2_paths = list(stage1_paths)
        existing_stage2_pairs = set(existing_path_pairs)

        int_std_scales = {}
        for m in moderations:
            int_name = m["interaction_term"]
            p_score = np.asarray(scores_stage1.get(m["source"], np.zeros(n_obs)), dtype=float)
            m_score = np.asarray(scores_stage1.get(m["moderator"], np.zeros(n_obs)), dtype=float)
            int_raw = p_score * m_score
            int_std = standardize_series(int_raw, ddof=1) if m.get("standardize", True) else int_raw
            col_int = f"int_{m['source']}_{m['moderator']}"
            df_stage2[col_int] = int_std

            # Compute standard deviation of the interaction term to scale coefficients to unstandardized interaction scale
            # (Hair et al., SmartPLS 4 standard: latent variables are standardized Z-scores, but the product term
            # is not divided by its own standard deviation).
            int_sd = float(np.std(int_raw, ddof=1))
            int_std_scales[int_name] = int_sd if int_sd > 1e-12 else 1.0

            stage2_constructs.append({
                "id": int_name,
                "name": int_name,
                "type": "reflective",
                "indicators": [col_int],
                "outer_mode": "A",
                "is_interaction": True,
                "metadata": {
                    "moderator": m["moderator"],
                    "predictor": m["source"],
                    "outcome": m["target"],
                    "method": m["method"],
                },
            })
            stage2_indicators.append({
                "id": col_int,
                "column": col_int,
                "construct_id": int_name,
            })

            int_path_pair = (int_name, m["target"])
            if int_path_pair not in existing_stage2_pairs:
                stage2_paths.append({"from": int_name, "to": m["target"]})
                existing_stage2_pairs.add(int_path_pair)

        stage2_spec = {
            "constructs": stage2_constructs,
            "indicators": stage2_indicators,
            "paths": stage2_paths,
        }

        # Estimate Stage 2
        res_stage2 = run_pipeline(df_stage2, stage2_spec, cfg)

        # Rescale interaction path coefficients back to unstandardized interaction scale
        # (Hair et al., SmartPLS 4 standard: beta_unstd = beta_std / std(INT))
        if "structural" in res_stage2 and "path_coefficients" in res_stage2["structural"]:
            for m in moderations:
                int_name = m["interaction_term"]
                tgt = m["target"]
                scale = int_std_scales.get(int_name, 1.0)
                if scale > 1e-12:
                    tgt_paths = res_stage2["structural"]["path_coefficients"].get(tgt, {})
                    if int_name in tgt_paths:
                        tgt_paths[int_name] = float(tgt_paths[int_name]) / scale
                    if "original_coefficients" in res_stage2["structural"]:
                        orig_paths = res_stage2["structural"]["original_coefficients"].get(tgt, {})
                        if int_name in orig_paths:
                            orig_paths[int_name] = float(orig_paths[int_name]) / scale
                    if "paths" in res_stage2 and isinstance(res_stage2["paths"], list):
                        for p in res_stage2["paths"]:
                            if p.get("from") == int_name and p.get("to") == tgt:
                                p["beta"] = float(p.get("beta", 0.0)) / scale

        # Merge results: measurement results from Stage 1, structural results from Stage 2
        final_res = copy.deepcopy(res_stage2)
        if save_stage1_meas:
            final_res["measurement"] = copy.deepcopy(res_stage1.get("measurement", {}))
            final_res["reliability_and_validity"] = copy.deepcopy(res_stage1.get("reliability_and_validity", {}))
            # Preserve measurement entries (outer loadings and weights) for interaction constructs from Stage 2
            for m in moderations:
                int_name = m["interaction_term"]
                if int_name in res_stage2.get("measurement", {}).get("outer_loadings", {}):
                    final_res["measurement"].setdefault("outer_loadings", {})[int_name] = res_stage2["measurement"]["outer_loadings"][int_name]
                    final_res["measurement"].setdefault("outer_weights", {})[int_name] = res_stage2["measurement"]["outer_weights"][int_name]
                    final_res["measurement"].setdefault("indicator_reliability", {})[int_name] = res_stage2["measurement"]["indicator_reliability"].get(int_name, {})

        final_res["_stage1_results"] = res_stage1
        final_res["_expanded_spec"] = stage2_spec
        final_res["_expanded_df"] = df_stage2
        return final_res

    else:
        # --- PRODUCT-INDICATOR & ORTHOGONALIZING APPROACH ---
        df_mod = df.copy()
        expanded_constructs = list(spec_dict.get("constructs", []))
        expanded_indicators = list(spec_dict.get("indicators", []))
        expanded_paths = list(spec_dict.get("paths", []))
        existing_path_pairs = set(
            ((p.get("from") or p.get("from_node")), (p.get("to") or p.get("to_node")))
            for p in expanded_paths
        )

        for m in moderations:
            int_name = m["interaction_term"]
            # Auto-include direct path moderator -> outcome
            dir_pair = (m["moderator"], m["target"])
            if dir_pair not in existing_path_pairs:
                expanded_paths.append({"from": m["moderator"], "to": m["target"]})
                existing_path_pairs.add(dir_pair)

            # Generate indicators for this interaction
            df_mod, int_ind_cols = build_interaction_indicators_for_df(df_mod, spec_dict, m)

            expanded_constructs.append({
                "id": int_name,
                "name": int_name,
                "type": "reflective",
                "indicators": int_ind_cols,
                "outer_mode": "A",
                "is_interaction": True,
                "metadata": {
                    "moderator": m["moderator"],
                    "predictor": m["source"],
                    "outcome": m["target"],
                    "method": m["method"],
                },
            })
            for col in int_ind_cols:
                expanded_indicators.append({
                    "id": col,
                    "column": col,
                    "construct_id": int_name,
                })

            int_pair = (int_name, m["target"])
            if int_pair not in existing_path_pairs:
                expanded_paths.append({"from": int_name, "to": m["target"]})
                existing_path_pairs.add(int_pair)

        expanded_spec = {
            "constructs": expanded_constructs,
            "indicators": expanded_indicators,
            "paths": expanded_paths,
        }

        res_mod = run_pipeline(df_mod, expanded_spec, cfg)
        res_mod["_expanded_spec"] = expanded_spec
        res_mod["_expanded_df"] = df_mod
        return res_mod


def analyze_multiple_moderation(
    df: pd.DataFrame,
    spec: Union[Dict[str, Any], Any],
    n_boot: int = 500,
    seed: Optional[int] = 42,
    alpha: float = 0.05,
    settings: Optional[PipelineSettings] = None,
    progress_callback: Optional[Any] = None,
    cancel_event: Optional[Any] = None,
) -> Dict[str, Any]:
    """
    Complete analysis pipeline for multiple moderations, simple slopes, Kenny f^2,
    moderated mediation (conditional indirect effects), and bootstrap inference.
    """
    spec_dict, moderations = normalize_moderation_spec(spec)
    cfg = settings or PipelineSettings()
    start_time = time.time()

    # Step 1: Full Model Estimation with all interactions
    res_full = run_expanded_pls_estimation(df, spec_dict, moderations, cfg)
    path_matrix = res_full.get("structural", {}).get("path_coefficients", {})
    r2_full_map = res_full.get("structural", {}).get("r_squared", {})

    # Step 2: Kenny f^2 for each interaction
    f2_results = {}
    for m in moderations:
        int_name = m["interaction_term"]
        tgt = m["target"]
        r2_incl = float(r2_full_map.get(tgt, 0.0))

        # Re-estimate model excluding this specific interaction
        other_mods = [om for om in moderations if om["id"] != m["id"]]
        res_excl = run_expanded_pls_estimation(df, spec_dict, other_mods, cfg)
        r2_excl = float(res_excl.get("structural", {}).get("r_squared", {}).get(tgt, 0.0))

        f2_data = calculate_moderation_f2(r2_incl, r2_excl)
        f2_results[int_name] = f2_data

    # Step 3: Bootstrapping the full pipeline per resample
    boot_coef_reps: Dict[str, List[float]] = {}
    all_chains = detect_moderated_mediation_chains(
        [(p.get("from") or p.get("source"), p.get("to") or p.get("target")) for p in res_full.get("_expanded_spec", {}).get("paths", [])],
        moderations
    )

    if n_boot > 0:
        rng = np.random.default_rng(seed)
        n_samples = len(df)

        for b_idx in range(n_boot):
            if cancel_event and cancel_event.is_set():
                break

            boot_idx = rng.integers(0, n_samples, size=n_samples)
            df_b = df.iloc[boot_idx].reset_index(drop=True)

            try:
                res_b = run_expanded_pls_estimation(df_b, spec_dict, moderations, cfg, save_stage1_meas=False)
                b_paths = res_b.get("structural", {}).get("path_coefficients", {})

                for to_c, from_map in b_paths.items():
                    for from_c, val in from_map.items():
                        pkey = f"path:{from_c}->{to_c}"
                        boot_coef_reps.setdefault(pkey, []).append(float(val))
            except Exception:
                continue

            if progress_callback and (b_idx % 25 == 0 or b_idx == n_boot - 1):
                progress_callback(b_idx + 1, n_boot)

    boot_arrays = {k: np.asarray(v, dtype=float) for k, v in boot_coef_reps.items()}
    boot_time = round(time.time() - start_time, 2)

    # Step 4: Simple slope analysis per moderation
    simple_slopes_by_mod = {}
    mod_details = []
    for m in moderations:
        src = m["source"]
        mod = m["moderator"]
        tgt = m["target"]
        int_name = m["interaction_term"]

        b_src = float(path_matrix.get(tgt, {}).get(src, 0.0))
        b_mod = float(path_matrix.get(tgt, {}).get(mod, 0.0))
        b_int = float(path_matrix.get(tgt, {}).get(int_name, 0.0))

        src_reps = boot_arrays.get(f"path:{src}->{tgt}")
        int_reps = boot_arrays.get(f"path:{int_name}->{tgt}")

        slopes_res = compute_simple_slopes(
            beta_source=b_src,
            beta_moderator=b_mod,
            beta_interaction=b_int,
            boot_source_reps=src_reps,
            boot_int_reps=int_reps,
            alpha=alpha,
        )
        simple_slopes_by_mod[m["id"]] = slopes_res

        # Interaction bootstrap statistics
        int_se = float(np.std(int_reps, ddof=1)) if int_reps is not None and len(int_reps) > 0 else 0.0
        int_t = (b_int / int_se) if int_se > 1e-12 else 0.0
        int_p = float(2.0 * (1.0 - stats.norm.cdf(abs(int_t)))) if int_se > 1e-12 else 1.0
        int_ci_low = float(np.percentile(int_reps, 100 * (alpha / 2))) if int_reps is not None and len(int_reps) > 0 else 0.0
        int_ci_high = float(np.percentile(int_reps, 100 * (1.0 - alpha / 2))) if int_reps is not None and len(int_reps) > 0 else 0.0

        mod_details.append({
            "id": m["id"],
            "source": src,
            "moderator": mod,
            "target": tgt,
            "interaction_term": int_name,
            "method": m["method"],
            "estimates": {
                "beta_source": round(b_src, 4),
                "beta_moderator": round(b_mod, 4),
                "beta_interaction": round(b_int, 4),
                "interaction_se": round(int_se, 4),
                "interaction_t": round(int_t, 4),
                "interaction_p_value": round(int_p, 4),
                "interaction_ci_lower": round(int_ci_low, 4),
                "interaction_ci_upper": round(int_ci_high, 4),
                "is_significant": bool(int_p < alpha),
            },
            "f_squared": f2_results.get(int_name, {}),
            "simple_slopes": slopes_res["simple_slopes"],
            "plot_data": {
                "x_range": slopes_res["x_range"],
                "lines": slopes_res["simple_slopes"],
            },
        })

    # Step 5: Moderated Mediation (Conditional Indirect Effects)
    cond_indirect_effects = compute_conditional_indirect_effects(
        chains=all_chains,
        path_matrix=path_matrix,
        boot_coef_reps=boot_arrays if boot_arrays else None,
        alpha=alpha,
    )

    # Attach moderation results to full result dict
    moderation_summary = {
        "moderating_effects": mod_details,
        "f2_effect_sizes": f2_results,
        "simple_slopes": simple_slopes_by_mod,
        "conditional_indirect_effects": cond_indirect_effects,
        "n_boot": n_boot,
        "bootstrap_time_sec": boot_time,
    }

    res_full["moderation"] = moderation_summary

    # Ensure backend contract fields and complete metadata
    mod_by_term = {m["interaction_term"]: m for m in moderations}
    if "latent_variables" in res_full:
        for lv in res_full["latent_variables"]:
            cid = lv.get("id")
            if cid in mod_by_term:
                m_info = mod_by_term[cid]
                lv["is_interaction"] = True
                lv["metadata"] = {
                    "moderator": m_info["moderator"],
                    "predictor": m_info["source"],
                    "outcome": m_info["target"],
                    "method": m_info["method"],
                }
            elif " x " in str(cid):
                lv["is_interaction"] = True
                if not lv.get("metadata"):
                    parts = str(cid).split(" x ")
                    lv["metadata"] = {
                        "moderator": parts[0].strip(),
                        "predictor": parts[1].strip(),
                        "outcome": "",
                        "method": "two_stage",
                    }
    res_full["scores"] = res_full.get("construct_scores", {})
    res_full["r2"] = res_full.get("structural", {}).get("r_squared", {})
    res_full["f2"] = res_full.get("structural", {}).get("f_squared", {})
    res_full["vif"] = res_full.get("structural", {}).get("inner_vif", {})

    # Attach bootstrap significance summary
    if n_boot > 0 and boot_arrays:
        param_summary = {}
        for k, dist in boot_arrays.items():
            if len(dist) == 0:
                continue
            orig_val = 0.0
            if k.startswith("path:"):
                pts = k.split(":")[1].split("->")
                orig_val = float(path_matrix.get(pts[1], {}).get(pts[0], 0.0))
            se = float(np.std(dist, ddof=1)) if len(dist) > 1 else 0.0
            t_stat = float(orig_val / se) if se > 1e-9 else 0.0
            p_val = float(2.0 * (1.0 - stats.norm.cdf(abs(t_stat)))) if se > 1e-9 else 1.0
            ci_low = float(np.percentile(dist, 100 * (alpha / 2)))
            ci_high = float(np.percentile(dist, 100 * (1.0 - alpha / 2)))
            sig = "***" if p_val < 0.001 else ("**" if p_val < 0.01 else ("*" if p_val < alpha else "ns"))
            param_summary[k] = {
                "original": orig_val,
                "mean": float(np.mean(dist)),
                "se": se,
                "t_stat": t_stat,
                "p_value": p_val,
                "ci_low": ci_low,
                "ci_high": ci_high,
                "significance": sig,
            }
        path_significance = []
        for k, v in param_summary.items():
            if k.startswith("path:"):
                pts = k.split(":")[1].split("->")
                p_entry = dict(v)
                p_entry["from"] = pts[0]
                p_entry["to"] = pts[1]
                path_significance.append(p_entry)

        sig_obj = {
            "n_boot": n_boot,
            "actual_samples": n_boot,
            "parameters": param_summary,
            "parameter_summary": param_summary,
            "paths": path_significance,
        }
        res_full["significance"] = sig_obj
        res_full["bootstrap"] = sig_obj

    return res_full


def analyze_moderation(
    df: pd.DataFrame,
    spec: Union[Dict[str, Any], Any],
    source: str,
    moderator: str,
    target: str,
    method: str = "two_stage",
    n_boot: int = 500,
    seed: Optional[int] = 42,
    alpha: float = 0.05,
    settings: Optional[PipelineSettings] = None,
    progress_callback: Optional[Any] = None,
    cancel_event: Optional[Any] = None,
) -> Dict[str, Any]:
    """
    Backward-compatible single-moderation function wrapper over analyze_multiple_moderation.
    """
    spec_dict = spec.model_dump(mode="json", by_alias=True) if hasattr(spec, "model_dump") else (copy.deepcopy(spec) if isinstance(spec, dict) else {})
    single_mod = {
        "id": f"mod_{source}_{moderator}_{target}",
        "moderator": moderator,
        "source": source,
        "target": target,
        "method": method,
        "standardize": True,
    }
    spec_dict["moderating_effects"] = [single_mod]

    res = analyze_multiple_moderation(
        df=df,
        spec=spec_dict,
        n_boot=n_boot,
        seed=seed,
        alpha=alpha,
        settings=settings,
        progress_callback=progress_callback,
        cancel_event=cancel_event,
    )

    mod_meta = res.get("moderation", {}).get("moderating_effects", [{}])[0]
    return {
        "source": source,
        "moderator": moderator,
        "target": target,
        "method": method,
        "interaction_term": f"{moderator} x {source}",
        "estimates": mod_meta.get("estimates", {}),
        "effect_size": mod_meta.get("f_squared", {}),
        "simple_slopes": mod_meta.get("simple_slopes", []),
        "plot_data": mod_meta.get("plot_data", {}),
        "conditional_indirect_effects": res.get("moderation", {}).get("conditional_indirect_effects", []),
        "full_results": res,
    }


def attach_bootstrap_to_moderation(res: Dict[str, Any], boot_res: Dict[str, Any]) -> None:
    """
    Merges bootstrap statistics from ParallelBootstrapper output into the moderation results block.
    """
    if not res or "moderation" not in res or not boot_res:
        return
    param_summary = boot_res.get("parameter_summary") or boot_res.get("parameters") or {}
    mod_block = res.get("moderation", {})

    for me in mod_block.get("moderating_effects", []):
        src = me["source"]
        mod = me["moderator"]
        tgt = me["target"]
        int_name = me.get("interaction_term", f"{mod} x {src}")

        # Update interaction path estimates
        p_key = f"path:{int_name}->{tgt}"
        if p_key in param_summary:
            st = param_summary[p_key]
            me["estimates"].update({
                "interaction_se": round(float(st.get("se", 0.0)), 4),
                "interaction_t": round(float(st.get("t_stat", 0.0)), 4),
                "interaction_p_value": round(float(st.get("p_value", 1.0)), 4),
                "interaction_ci_lower": round(float(st.get("ci_low", 0.0)), 4),
                "interaction_ci_upper": round(float(st.get("ci_high", 0.0)), 4),
                "is_significant": bool(float(st.get("p_value", 1.0)) < 0.05),
            })

        # Update simple slopes
        for sl in me.get("simple_slopes", []):
            lvl_key = str(sl.get("moderator_level", "")).split(" ")[0]
            s_key = f"simple_slope:{int_name}->{tgt}:{lvl_key}"
            if s_key in param_summary:
                st = param_summary[s_key]
                sl.update({
                    "standard_error": round(float(st.get("se", 0.0)), 4),
                    "t_statistic": round(float(st.get("t_stat", 0.0)), 4),
                    "p_value": round(float(st.get("p_value", 1.0)), 4),
                    "ci_lower": round(float(st.get("ci_low", 0.0)), 4),
                    "ci_upper": round(float(st.get("ci_high", 0.0)), 4),
                })

    for cie in mod_block.get("conditional_indirect_effects", []):
        chain_str = cie.get("chain", "")
        mod_str = cie.get("moderator", "")
        idx_key = f"index_of_moderated_mediation:{chain_str}({mod_str})"
        if idx_key in param_summary:
            st = param_summary[idx_key]
            cie["bootstrap_inference"] = {
                "index_point": round(float(st.get("original", 0.0)), 6),
                "index_se": round(float(st.get("se", 0.0)), 6),
                "index_t": round(float(st.get("t_stat", 0.0)), 4),
                "index_p_value": round(float(st.get("p_value", 1.0)), 6),
                "index_ci_lower": round(float(st.get("ci_low", 0.0)), 6),
                "index_ci_upper": round(float(st.get("ci_high", 0.0)), 6),
                "index_significant": bool(float(st.get("ci_low", 0.0)) > 0 or float(st.get("ci_high", 0.0)) < 0),
            }

        for ce in cie.get("conditional_effects", []):
            lvl_key = str(ce.get("w_label", "")).split(" ")[0]
            c_key = f"cond_indirect:{chain_str}({mod_str}):{lvl_key}"
            if c_key in param_summary:
                st = param_summary[c_key]
                ce.update({
                    "se": round(float(st.get("se", 0.0)), 6),
                    "t_statistic": round(float(st.get("t_stat", 0.0)), 4),
                    "p_value": round(float(st.get("p_value", 1.0)), 6),
                    "ci_lower": round(float(st.get("ci_low", 0.0)), 6),
                    "ci_upper": round(float(st.get("ci_high", 0.0)), 6),
                    "is_significant": bool(float(st.get("ci_low", 0.0)) > 0 or float(st.get("ci_high", 0.0)) < 0),
                })
