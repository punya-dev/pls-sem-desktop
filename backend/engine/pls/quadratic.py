"""
Quadratic (Non-linear) Effects Analysis (Section 25a: X-04).
Implements Two-Stage polynomial estimation for quadratic effects (Y ~ X + X^2).
Calculates turning points x* = -beta_1 / (2 * beta_2), curve plotting data, and shape classification.
"""

from typing import List, Dict, Any, Optional, Tuple, Union
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
    n_boot: int = 500,
    seed: Optional[int] = 42,
    alpha: float = 0.05,
    settings: Optional[PipelineSettings] = None,
    progress_callback: Optional[Any] = None,
    cancel_event: Optional[Any] = None,
) -> Dict[str, Any]:
    """
    Evaluates quadratic non-linear effect: target ~ source + (source)^2.
    """
    spec_dict = spec.model_dump(by_alias=True) if hasattr(spec, "model_dump") else (spec if isinstance(spec, dict) else {})
    cfg = settings or PipelineSettings()

    # Step 1: Main linear model
    res_linear = run_pipeline(df, spec_dict, cfg)
    linear_r2 = float(res_linear.get("structural", {}).get("r_squared", {}).get(target, 0.0))
    scores = res_linear.get("construct_scores", {})
    x_score = np.asarray(scores.get(source, np.zeros(len(df))), dtype=float)

    # Step 2: Generate quadratic term (x_score^2, standardized)
    quad_name = f"{source}_squared"
    x_sq = x_score ** 2
    x_sq_std = (x_sq - np.mean(x_sq)) / (np.std(x_sq, ddof=0) or 1.0)

    df_quad = df.copy()
    df_quad[f"{quad_name}_ind"] = x_sq_std

    quad_constructs = list(spec_dict.get("constructs", [])) + [{
        "id": quad_name,
        "name": f"{source}^2",
        "type": "reflective",
        "indicators": [f"{quad_name}_ind"],
    }]
    quad_indicators = list(spec_dict.get("indicators", [])) + [{
        "name": f"{quad_name}_ind",
        "construct_id": quad_name,
    }]
    quad_paths = list(spec_dict.get("paths", [])) + [{
        "from": quad_name,
        "to": target,
    }]

    quad_spec = {
        "constructs": quad_constructs,
        "indicators": quad_indicators,
        "paths": quad_paths,
    }

    # Step 3: Estimate quadratic model
    res_quad = run_pipeline(df_quad, quad_spec, cfg)
    paths_quad = res_quad.get("structural", {}).get("path_coefficients", {})
    quad_r2 = float(res_quad.get("structural", {}).get("r_squared", {}).get(target, 0.0))

    beta_linear = float(paths_quad.get(target, {}).get(source, 0.0))
    beta_quad = float(paths_quad.get(target, {}).get(quad_name, 0.0))

    # Turning point: x* = -beta_1 / (2 * beta_2)
    turning_point = (-beta_linear / (2.0 * beta_quad)) if abs(beta_quad) > 1e-6 else None

    # Step 4: Bootstrapping for quadratic term significance
    booter = ParallelBootstrapper()
    boot_res = booter.run(
        data=df_quad,
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

    # Effect size f^2 = (R2_quad - R2_linear) / (1 - R2_quad)
    denom = max(1e-12, 1.0 - quad_r2)
    f2_val = max(0.0, (quad_r2 - linear_r2) / denom)

    # Shape classification
    if not quad_sig:
        shape = "Linear (no significant curvature)"
    elif beta_quad < 0:
        shape = "Inverted U-shape (concave / diminishing returns)"
    else:
        shape = "U-shape (convex / accelerating returns)"

    # Curve plotting data: x in [-2, 2]
    x_grid = np.linspace(-2.0, 2.0, 21).tolist()
    y_curve = [(beta_linear * x + beta_quad * (x ** 2)) for x in x_grid]
    y_linear_baseline = [(beta_linear * x) for x in x_grid]

    return {
        "source": source,
        "target": target,
        "linear_path": round(beta_linear, 4),
        "quadratic_path": round(beta_quad, 4),
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
        "curve_points": [
            {"x": round(x, 2), "y_quadratic": round(yq, 4), "y_linear": round(yl, 4)}
            for x, yq, yl in zip(x_grid, y_curve, y_linear_baseline)
        ],
    }
