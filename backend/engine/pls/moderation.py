"""
Moderation Analysis (Section 16: MOD-M01 to MOD-M22).
Source of truth: Hair et al. (2017) Ch. 7 & Kenny (2016).
Implements Two-Stage, Product-Indicator, and Orthogonalizing interaction approaches,
simple slope analysis (-1 SD, Mean, +1 SD), moderation f^2, and moderated mediation.
"""

from typing import List, Dict, Any, Optional, Tuple, Union
import numpy as np
import pandas as pd
from scipy import stats

from core.settings_schema import PipelineSettings
from core.thresholds import THRESHOLDS
from engine.pls.algorithm import run_pipeline
from engine.pls.bootstrap import ParallelBootstrapper


def compute_simple_slopes(
    beta_source: float,
    beta_moderator: float,
    beta_interaction: float,
    boot_samples: Optional[np.ndarray] = None,
    source_idx: Optional[int] = None,
    int_idx: Optional[int] = None,
    alpha: float = 0.05,
) -> Dict[str, Any]:
    """
    Computes simple slopes of target on source at 3 moderator levels:
    - 1 SD below mean (m = -1.0)
    - At mean (m = 0.0)
    - 1 SD above mean (m = +1.0)
    Includes line data for plotting x in [-2, 2] SD and bootstrap CIs.
    """
    levels = [-1.0, 0.0, 1.0]
    level_names = ["-1 SD (Low)", "Mean (Average)", "+1 SD (High)"]
    x_grid = np.linspace(-2.0, 2.0, 9).tolist()

    slopes_data = []

    for m_val, m_name in zip(levels, level_names):
        slope = beta_source + beta_interaction * m_val
        # Prediction line: y = (beta_s + beta_int * m) * x + beta_m * m
        y_vals = [(slope * x + beta_moderator * m_val) for x in x_grid]

        se_slope = None
        t_slope = None
        p_slope = None
        ci_lower = None
        ci_upper = None

        if boot_samples is not None and source_idx is not None and int_idx is not None:
            boot_samples_arr = np.asarray(boot_samples)
            if boot_samples_arr.ndim == 2 and boot_samples_arr.shape[0] > 0:
                # Replicate slopes
                rep_source = boot_samples_arr[:, source_idx]
                rep_int = boot_samples_arr[:, int_idx]
                rep_slopes = rep_source + rep_int * m_val
                se_slope = float(np.std(rep_slopes, ddof=1))
            t_slope = (slope / se_slope) if se_slope > 1e-12 else 0.0
            p_slope = 2.0 * (1.0 - stats.norm.cdf(abs(t_slope)))
            ci_lower = float(np.percentile(rep_slopes, 100 * (alpha / 2)))
            ci_upper = float(np.percentile(rep_slopes, 100 * (1.0 - alpha / 2)))

        slopes_data.append({
            "moderator_level": m_name,
            "moderator_value": m_val,
            "slope": round(float(slope), 4),
            "standard_error": round(float(se_slope), 4) if se_slope is not None else None,
            "t_statistic": round(float(t_slope), 4) if t_slope is not None else None,
            "p_value": round(float(p_slope), 4) if p_slope is not None else None,
            "ci_lower": round(float(ci_lower), 4) if ci_lower is not None else None,
            "ci_upper": round(float(ci_upper), 4) if ci_upper is not None else None,
            "line_points": [{"x": round(x, 2), "y": round(y, 4)} for x, y in zip(x_grid, y_vals)],
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
    Evaluated using Kenny (2016) thresholds: 0.005 (small), 0.01 (medium), 0.025 (large).
    """
    denom = max(1e-12, 1.0 - r2_with_interaction)
    f2_val = max(0.0, (r2_with_interaction - r2_without_interaction) / denom)

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
        "note": "Moderation effect sizes use Kenny (2016) thresholds (0.005 small, 0.010 medium, 0.025 large) rather than general Cohen f^2 cutoffs (Hair et al. 2017).",
    }


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
    Executes complete moderation analysis:
    1. Stage 1 / Main model (without interaction)
    2. Builds interaction construct and estimates moderated model
    3. Bootstraps interaction significance and simple slopes
    4. Computes Kenny (2016) moderation effect size f^2
    """
    spec_dict = spec.model_dump(mode="json", by_alias=True) if hasattr(spec, "model_dump") else (spec if isinstance(spec, dict) else {})
    cfg = settings or PipelineSettings()

    # Step 1: Main effects model (without interaction term)
    res_main = run_pipeline(df, spec_dict, cfg)
    paths_main = res_main.get("structural", {}).get("path_coefficients", {})
    r2_without_int = float(res_main.get("structural", {}).get("r_squared", {}).get(target, 0.0))
    scores_main = res_main.get("construct_scores", {})

    int_name = f"{source}_x_{moderator}"

    # Step 2: Build moderated model specification and data
    if method == "two_stage":
        # Two-stage: Use standardized latent scores from Stage 1 as single-item indicators
        df_mod = df.copy()
        s_score = np.asarray(scores_main.get(source, np.zeros(len(df))), dtype=float)
        m_score = np.asarray(scores_main.get(moderator, np.zeros(len(df))), dtype=float)
        int_score = (s_score * m_score)
        # Standardize interaction score
        int_score_std = (int_score - np.mean(int_score)) / (np.std(int_score, ddof=0) or 1.0)
        df_mod[f"{int_name}_ind"] = int_score_std

        # Add interaction construct to spec
        mod_constructs = list(spec_dict.get("constructs", [])) + [{
            "id": int_name,
            "name": f"{source} * {moderator}",
            "type": "reflective",
            "indicators": [f"{int_name}_ind"],
        }]
        mod_indicators = list(spec_dict.get("indicators", [])) + [{
            "name": f"{int_name}_ind",
            "construct_id": int_name,
        }]
        mod_paths = list(spec_dict.get("paths", [])) + [{
            "from": int_name,
            "to": target,
        }]

        # Ensure main effect moderator -> target exists if not already present
        has_mod_path = any((p.get("from") or p.get("from_node")) == moderator and (p.get("to") or p.get("to_node")) == target for p in mod_paths)
        if not has_mod_path:
            mod_paths.append({"from": moderator, "to": target})

        mod_spec = {
            "constructs": mod_constructs,
            "indicators": mod_indicators,
            "paths": mod_paths,
        }

    else:
        # Product-indicator approach (or orthogonalizing)
        df_mod = df.copy()
        # Find indicators for source and moderator
        source_inds = [
            (ind.get("name") or ind.get("column") or ind.get("id"))
            for ind in spec_dict.get("indicators", [])
            if (ind.get("construct_id") or ind.get("construct")) == source and (ind.get("name") or ind.get("column") or ind.get("id")) in df.columns
        ]
        mod_inds = [
            (ind.get("name") or ind.get("column") or ind.get("id"))
            for ind in spec_dict.get("indicators", [])
            if (ind.get("construct_id") or ind.get("construct")) == moderator and (ind.get("name") or ind.get("column") or ind.get("id")) in df.columns
        ]

        product_ind_names = []
        for si in source_inds:
            s_val = df[si].values.astype(float)
            s_std = (s_val - np.mean(s_val)) / (np.std(s_val, ddof=0) or 1.0)
            for mi in mod_inds:
                m_val = df[mi].values.astype(float)
                m_std = (m_val - np.mean(m_val)) / (np.std(m_val, ddof=0) or 1.0)
                prod_val = s_std * m_std

                if method == "orthogonalizing":
                    # Regress prod_val on all source & moderator indicators, take residuals
                    X_basis = np.column_stack([
                        (df[col].values - np.mean(df[col].values)) / (np.std(df[col].values, ddof=0) or 1.0)
                        for col in (source_inds + mod_inds)
                    ])
                    coef, _, _, _ = np.linalg.lstsq(X_basis, prod_val, rcond=None)
                    prod_val = prod_val - X_basis @ coef

                prod_std = (prod_val - np.mean(prod_val)) / (np.std(prod_val, ddof=0) or 1.0)
                p_col = f"prod_{si}_{mi}"
                df_mod[p_col] = prod_std
                product_ind_names.append(p_col)

        mod_constructs = list(spec_dict.get("constructs", [])) + [{
            "id": int_name,
            "name": f"{source} * {moderator}",
            "type": "reflective",
            "indicators": product_ind_names,
        }]
        mod_indicators = list(spec_dict.get("indicators", [])) + [
            {"name": p_col, "construct_id": int_name} for p_col in product_ind_names
        ]
        mod_paths = list(spec_dict.get("paths", [])) + [{
            "from": int_name,
            "to": target,
        }]
        has_mod_path = any((p.get("from") or p.get("from_node")) == moderator and (p.get("to") or p.get("to_node")) == target for p in mod_paths)
        if not has_mod_path:
            mod_paths.append({"from": moderator, "to": target})

        mod_spec = {
            "constructs": mod_constructs,
            "indicators": mod_indicators,
            "paths": mod_paths,
        }

    # Step 3: Estimate Moderated Model
    res_mod = run_pipeline(df_mod, mod_spec, cfg)
    paths_mod = res_mod.get("structural", {}).get("path_coefficients", {})
    r2_with_int = float(res_mod.get("structural", {}).get("r_squared", {}).get(target, 0.0))

    b_source = float(paths_mod.get(target, {}).get(source, 0.0))
    b_mod = float(paths_mod.get(target, {}).get(moderator, 0.0))
    b_int = float(paths_mod.get(target, {}).get(int_name, 0.0))

    # Step 4: Bootstrapping the Moderated Model
    booter = ParallelBootstrapper()
    boot_res = booter.run(
        data=df_mod,
        model_spec=mod_spec,
        n_boot=n_boot,
        seed=seed,
        scheme=cfg.inner_weighting,
        mode="basic",
        sign_change="none",
        alpha=alpha,
        progress_callback=progress_callback,
        cancel_event=cancel_event,
    )

    p_summary = boot_res.get("parameter_summary", {})
    int_stat = p_summary.get(f"path:{int_name}->{target}", {})
    int_p = float(int_stat.get("p_value", 1.0))
    int_sig = int_p < alpha

    # Extract bootstrap samples for simple slope CI
    samples_mat = boot_res.get("samples_matrix")
    param_names = boot_res.get("parameter_names", [])

    src_idx = param_names.index(f"path:{source}->{target}") if f"path:{source}->{target}" in param_names else None
    int_idx = param_names.index(f"path:{int_name}->{target}") if f"path:{int_name}->{target}" in param_names else None

    # Compute Simple Slopes
    slopes_res = compute_simple_slopes(
        beta_source=b_source,
        beta_moderator=b_mod,
        beta_interaction=b_int,
        boot_samples=samples_mat,
        source_idx=src_idx,
        int_idx=int_idx,
        alpha=alpha,
    )

    # Compute Moderation f^2
    f2_res = calculate_moderation_f2(
        r2_with_interaction=r2_with_int,
        r2_without_interaction=r2_without_int,
    )

    return {
        "source": source,
        "moderator": moderator,
        "target": target,
        "method": method,
        "interaction_term": int_name,
        "estimates": {
            "beta_source": round(b_source, 4),
            "beta_moderator": round(b_mod, 4),
            "beta_interaction": round(b_int, 4),
            "interaction_se": round(float(int_stat.get("standard_error", 0.0)), 4),
            "interaction_t": round(float(int_stat.get("t_statistic", 0.0)), 4),
            "interaction_p_value": round(int_p, 4),
            "interaction_ci_lower": round(float(int_stat.get("ci_lower", 0.0)), 4),
            "interaction_ci_upper": round(float(int_stat.get("ci_upper", 0.0)), 4),
            "is_significant": int_sig,
        },
        "effect_size": f2_res,
        "simple_slopes": slopes_res["simple_slopes"],
        "plot_data": {
            "x_range": slopes_res["x_range"],
            "lines": slopes_res["simple_slopes"],
        },
        "interpretation": (
            f"The interaction effect of {moderator} on the relationship between {source} and {target} "
            f"is {'statistically significant' if int_sig else 'not statistically significant'} "
            f"(beta = {round(b_int, 4)}, p = {round(int_p, 4)}) with a {f2_res['magnitude']} effect size (f^2 = {f2_res['f_squared']})."
        ),
    }
