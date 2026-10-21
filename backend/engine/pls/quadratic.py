"""
Non-linear (Quadratic and Cubic) Effects Analysis (A18-NL-01 to A18-NL-14).
Source of truth: Hair et al. (2018) Ch. 2 & Kenny (2015).

Implements:
1. Three polynomial term creation approaches:
   - Two-stage approach (most versatile; recommended default)
   - Product indicator approach (all unique cross-products x_u * x_v)
   - Orthogonalizing approach (standardized residuals regressed on original indicators)
2. Evaluation rules: Kenny (2015) f^2 effect size thresholds (0.005, 0.01, 0.025).
3. Turning points x* = -beta_1 / (2 * beta_2) and curve coordinates vs linear line.
4. Effect tables at Y1 = 0, 1, 2 and at +/- 1 SD.
5. Keep-linear decision recommendation and optional cubic term.
"""

from typing import List, Dict, Any, Optional, Tuple, Union
import itertools
import numpy as np
import pandas as pd
from scipy import stats

from core.settings_schema import PipelineSettings
from engine.pls.algorithm import run_pipeline
from engine.pls.bootstrap import ParallelBootstrapper


def analyze_quadratic_effect(
    df: pd.DataFrame,
    spec: Union[Dict[str, Any], Any],
    source: str,
    target: str,
    approach: str = "two_stage",  # "two_stage", "product_indicator", "orthogonalizing"
    degree: int = 2,  # 2 for quadratic, 3 for cubic
    n_boot: int = 500,
    seed: Optional[int] = 42,
    alpha: float = 0.05,
    settings: Optional[PipelineSettings] = None,
    progress_callback: Optional[Any] = None,
    cancel_event: Optional[Any] = None,
) -> Dict[str, Any]:
    """
    Evaluates polynomial non-linear effects: target ~ source + (source)^2 (+ (source)^3).
    """
    spec_dict = spec.model_dump(mode="json", by_alias=True) if hasattr(spec, "model_dump") else (spec if isinstance(spec, dict) else {})
    cfg = settings or PipelineSettings()

    # Step 1: Base linear model
    res_linear = run_pipeline(df, spec_dict, cfg)
    linear_r2 = float(res_linear.get("structural", {}).get("r_squared", {}).get(target, 0.0))
    linear_paths = res_linear.get("structural", {}).get("path_coefficients", {})
    beta_pure_linear = float(linear_paths.get(target, {}).get(source, 0.0))

    scores = res_linear.get("construct_scores", {})
    N = len(df)

    from engine.pls.algorithm import parse_model_spec
    constructs_dict, ind_col_map, paths_list = parse_model_spec(spec_dict)

    source_inds = []
    for iid in constructs_dict.get(source, {}).get("indicators", []):
        col = ind_col_map.get(iid, iid)
        if col in df.columns and col not in source_inds:
            source_inds.append(col)

    df_model = df.copy()
    quad_name = f"{source}_squared"
    quad_indicators = []

    # Step 2: Build quadratic indicators according to selected approach (A18-NL-05)
    if approach == "product_indicator":
        # Product indicator approach: x_u * x_v for all pairs
        if not source_inds:
            raise ValueError(f"Source construct '{source}' has no indicators in dataset.")

        # Standardize source indicators
        X_src = df_model[source_inds].values.astype(float)
        X_src_std = (X_src - np.mean(X_src, axis=0)) / (np.std(X_src, axis=0, ddof=0) or 1.0)

        p_idx = 0
        for u in range(len(source_inds)):
            for v in range(u, len(source_inds)):
                p_col = f"{quad_name}_p{p_idx}"
                prod_vals = X_src_std[:, u] * X_src_std[:, v]
                prod_std = (prod_vals - np.mean(prod_vals)) / (np.std(prod_vals, ddof=0) or 1.0)
                df_model[p_col] = prod_std
                quad_indicators.append(p_col)
                p_idx += 1

    elif approach == "orthogonalizing":
        # Orthogonalizing approach: regress product indicators on all linear indicators
        if not source_inds:
            raise ValueError(f"Source construct '{source}' has no indicators in dataset.")

        X_src = df_model[source_inds].values.astype(float)
        X_src_std = (X_src - np.mean(X_src, axis=0)) / (np.std(X_src, axis=0, ddof=0) or 1.0)
        X_des = np.column_stack([np.ones(N), X_src_std])

        p_idx = 0
        for u in range(len(source_inds)):
            for v in range(u, len(source_inds)):
                p_col = f"{quad_name}_ortho{p_idx}"
                prod_raw = X_src_std[:, u] * X_src_std[:, v]
                coefs, _, _, _ = np.linalg.lstsq(X_des, prod_raw, rcond=None)
                res = prod_raw - X_des @ coefs
                res_std = (res - np.mean(res)) / (np.std(res, ddof=0) or 1.0)
                df_model[p_col] = res_std
                quad_indicators.append(p_col)
                p_idx += 1

    else:
        # Two-stage approach (recommended default) (A18-NL-05)
        x_score = np.asarray(scores.get(source, np.zeros(N)), dtype=float)
        x_std = (x_score - np.mean(x_score)) / (np.std(x_score, ddof=0) or 1.0)
        x_sq = x_std ** 2
        x_sq_std = (x_sq - np.mean(x_sq)) / (np.std(x_sq, ddof=0) or 1.0)
        quad_col = f"{quad_name}_ind"
        df_model[quad_col] = x_sq_std
        quad_indicators.append(quad_col)

    # Build spec with quadratic construct
    new_constructs = list(spec_dict.get("constructs", [])) + [{
        "id": quad_name,
        "name": f"{source}²",
        "type": "reflective",
        "indicators": quad_indicators,
    }]
    new_indicators = list(spec_dict.get("indicators", [])) + [
        {"name": col, "construct_id": quad_name} for col in quad_indicators
    ]
    new_paths = list(spec_dict.get("paths", [])) + [{
        "from": quad_name,
        "to": target,
    }]

    # Optional cubic term (A18-NL-13)
    cubic_name = f"{source}_cubed"
    if degree == 3:
        x_score = np.asarray(scores.get(source, np.zeros(N)), dtype=float)
        x_std = (x_score - np.mean(x_score)) / (np.std(x_score, ddof=0) or 1.0)
        x_cub = x_std ** 3
        x_cub_std = (x_cub - np.mean(x_cub)) / (np.std(x_cub, ddof=0) or 1.0)
        cub_col = f"{cubic_name}_ind"
        df_model[cub_col] = x_cub_std
        new_constructs.append({
            "id": cubic_name,
            "name": f"{source}³",
            "type": "reflective",
            "indicators": [cub_col],
        })
        new_indicators.append({"name": cub_col, "construct_id": cubic_name})
        new_paths.append({"from": cubic_name, "to": target})

    quad_spec = {
        "constructs": new_constructs,
        "indicators": new_indicators,
        "paths": new_paths,
    }

    # Step 3: Estimate quadratic model
    res_quad = run_pipeline(df_model, quad_spec, cfg)
    paths_quad = res_quad.get("structural", {}).get("path_coefficients", {})
    quad_r2 = float(res_quad.get("structural", {}).get("r_squared", {}).get(target, 0.0))

    beta_linear_in_quad = float(paths_quad.get(target, {}).get(source, 0.0))
    beta_quad = float(paths_quad.get(target, {}).get(quad_name, 0.0))
    beta_cubic = float(paths_quad.get(target, {}).get(cubic_name, 0.0)) if degree == 3 else 0.0

    # Turning point for quadratic: x* = -beta_1 / (2 * beta_2) (A18-NL-01)
    turning_point = (-beta_linear_in_quad / (2.0 * beta_quad)) if abs(beta_quad) > 1e-6 else None

    # Step 4: Bootstrapping for quadratic significance
    booter = ParallelBootstrapper()
    boot_res = booter.run(
        data=df_model,
        model_spec=quad_spec,
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
    quad_stat = p_summary.get(f"path:{quad_name}->{target}", {})
    quad_p = float(quad_stat.get("p_value", 1.0))
    quad_sig = quad_p < alpha

    # Effect size f^2 = (R2_quad - R2_linear) / (1 - R2_quad) (A18-NL-10)
    denom = max(1e-12, 1.0 - quad_r2)
    f2_val = max(0.0, (quad_r2 - linear_r2) / denom)

    # Kenny (2015) classification
    if f2_val < 0.005:
        f2_rating = "None (< 0.005)"
    elif f2_val < 0.01:
        f2_rating = "Small (0.005 - 0.01)"
    elif f2_val < 0.025:
        f2_rating = "Medium (0.01 - 0.025)"
    else:
        f2_rating = "Large (>= 0.025)"

    # Shape classification (A18-NL-02)
    if not quad_sig:
        shape = "Linear (no significant curvature)"
    elif beta_quad < 0:
        shape = "Inverted U-shape (concave / diminishing returns)"
    else:
        shape = "U-shape (convex / accelerating returns)"

    # Effect table at Y1 = 0, 1, 2 (A18-NL-11)
    effect_table = [
        {"source_level": 0.0, "predicted_y": 0.0, "marginal_effect": round(beta_linear_in_quad, 4)},
        {"source_level": 1.0, "predicted_y": round(beta_linear_in_quad * 1.0 + beta_quad * 1.0, 4), "marginal_effect": round(beta_linear_in_quad + 2.0 * beta_quad, 4)},
        {"source_level": 2.0, "predicted_y": round(beta_linear_in_quad * 2.0 + beta_quad * 4.0, 4), "marginal_effect": round(beta_linear_in_quad + 4.0 * beta_quad, 4)},
    ]

    # Effect at +/- 1 SD of standardized Y1
    effect_plus_1sd = round(beta_linear_in_quad + beta_quad, 4)
    effect_minus_1sd = round(beta_linear_in_quad - beta_quad, 4)

    # Curve plotting data: x in [-2, 2] with 21 points
    x_grid = np.linspace(-2.0, 2.0, 21).tolist()
    curve_data = []
    for x in x_grid:
        y_q = beta_linear_in_quad * x + beta_quad * (x ** 2) + (beta_cubic * (x ** 3) if degree == 3 else 0.0)
        y_lin = beta_pure_linear * x
        curve_data.append({
            "x": round(x, 2),
            "y_nonlinear": round(y_q, 4),
            "y_linear": round(y_lin, 4),
        })

    # Keep-linear decision helper (A18-NL-12)
    if not quad_sig or f2_val < 0.005:
        decision_recommendation = (
            "The quadratic term is statistically non-significant or exhibits negligible effect size (f² < 0.005). "
            "In accordance with Hair et al. (2018), retain the simpler linear model for parsimony and straightforward interpretation."
        )
    else:
        decision_recommendation = (
            f"The quadratic effect is statistically significant (p = {round(quad_p, 4)}) with {f2_rating} effect size (f² = {round(f2_val, 4)}). "
            f"Retaining the non-linear relationship is empirically supported."
        )

    return {
        "source": source,
        "target": target,
        "approach": approach,
        "degree": degree,
        "linear_path": round(beta_linear_in_quad, 4),
        "linear_path_in_linear_model": round(beta_pure_linear, 4),
        "linear_path_in_quad_model": round(beta_linear_in_quad, 4),
        "quadratic_path": round(beta_quad, 4),
        "cubic_path": round(beta_cubic, 4) if degree == 3 else None,
        "quadratic_se": round(float(quad_stat.get("standard_error", 0.0)), 4),
        "quadratic_t": round(float(quad_stat.get("t_statistic", 0.0)), 4),
        "quadratic_p_value": round(quad_p, 4),
        "quadratic_ci_lower": round(float(quad_stat.get("ci_lower", 0.0)), 4),
        "quadratic_ci_upper": round(float(quad_stat.get("ci_upper", 0.0)), 4),
        "is_significant": quad_sig,
        "turning_point": round(float(turning_point), 4) if turning_point is not None else None,
        "turning_point_in_range": (abs(turning_point) <= 2.0) if turning_point is not None else False,
        "shape_classification": shape,
        "r_squared_linear": round(linear_r2, 4),
        "r_squared_quadratic": round(quad_r2, 4),
        "f_squared": round(float(f2_val), 4),
        "f_squared_rating": f2_rating,
        "effect_table_0_1_2": effect_table,
        "effect_plus_1sd": effect_plus_1sd,
        "effect_minus_1sd": effect_minus_1sd,
        "curve_points": curve_data,
        "decision_recommendation": decision_recommendation,
        "note": "Non-linear terms are created using standardized data. p1 in the quadratic model is not directly comparable to linear beta (Hair et al. 2018).",
    }
