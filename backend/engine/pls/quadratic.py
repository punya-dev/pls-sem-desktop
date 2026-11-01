"""
SmartPLS-4 Style Nonlinear (Quadratic) Effects Engine.
Implements:
1. Two-stage approach (Hair et al. 2024; Basco et al. 2021) as default.
   - Stage 1: Main effects model without quadratic terms, yielding standardized LV scores.
   - Term construction: q = score², standardized as q* = (q - mean(q)) / sd(q).
   - Stage 2: Full PLS-SEM on original model plus single-item "{P} x {P}" construct.
   - Unscaling: beta_unstd = beta_std / sd(q), exactly reproducing SmartPLS 4 path coefficients.
2. Product indicator and orthogonalizing generation methods.
3. Kenny (2015) f² effect sizes (0.005 small, 0.010 medium, 0.025 large).
4. Turning point: x* = -b1 * s / (2 * b2_std) = -b1 / (2 * b2_unstd) in SD units.
5. Marginal effect table: dy/dx = b1 + 2 * b2_unstd * x at min, -1 SD, 0, +1 SD, max.
6. Interactive effect curve coordinates: y_hat(x) = b1 * x + b2_unstd * (x² - m).
7. Bootstrap re-estimation per resample (Stage 1 + term generation + Stage 2).
"""

from typing import List, Dict, Any, Optional, Tuple, Union
import copy
import numpy as np
import pandas as pd
from scipy import stats

from core.settings_schema import PipelineSettings


def standardize_series(s: Union[np.ndarray, pd.Series, List[float]], ddof: int = 1) -> np.ndarray:
    """Standardizes a series to mean 0 and unit variance (sample SD by default, ddof=1)."""
    arr = np.asarray(s, dtype=float)
    m = np.nanmean(arr)
    sd = np.nanstd(arr, ddof=ddof)
    if sd == 0 or np.isnan(sd):
        sd = 1.0
    return (arr - m) / sd


def normalize_quadratic_spec(
    model_spec: Union[Dict[str, Any], Any]
) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """
    Extracts and standardizes quadratic effects from a ModelSpec or dictionary.
    Returns (spec_dict, list_of_quadratic_effects).
    """
    if hasattr(model_spec, "model_dump"):
        spec_dict = model_spec.model_dump(mode="json", by_alias=True)
    elif isinstance(model_spec, dict):
        spec_dict = copy.deepcopy(model_spec)
    else:
        raise TypeError("model_spec must be a ModelSpec instance or dictionary")

    raw_quads = spec_dict.get("quadratic_effects") or spec_dict.get("quadraticEffects") or []
    c_list = spec_dict.get("constructs", [])
    name_to_cid = {}
    id_to_cname = {}
    for c in c_list:
        if isinstance(c, dict):
            cid = str(c.get("id") or "")
            cname = str(c.get("name") or "")
            if cid:
                id_to_cname[cid] = cname or cid
                if cname:
                    name_to_cid[cname] = cid

    quadratics: List[Dict[str, Any]] = []
    seen = set()

    for idx, qe in enumerate(raw_quads):
        if hasattr(qe, "model_dump"):
            d = qe.model_dump(mode="json", by_alias=True)
        elif isinstance(qe, dict):
            d = dict(qe)
        else:
            continue

        pred = str(
            d.get("predictor_construct")
            or d.get("predictorConstruct")
            or d.get("construct_id")
            or d.get("construct")
            or d.get("predictor")
            or d.get("source")
            or d.get("source_construct")
            or ""
        ).strip()
        tgt = str(
            d.get("target_construct")
            or d.get("targetConstruct")
            or d.get("target")
            or d.get("outcome")
            or ""
        ).strip()

        if pred not in id_to_cname and pred in name_to_cid:
            pred = name_to_cid[pred]
        if tgt not in id_to_cname and tgt in name_to_cid:
            tgt = name_to_cid[tgt]

        if not pred or not tgt:
            continue

        key = (pred, tgt)
        if key in seen:
            continue
        seen.add(key)

        pred_name = id_to_cname.get(pred, pred)
        tgt_name = id_to_cname.get(tgt, tgt)
        quad_construct_name = f"{pred_name} x {pred_name}"
        quad_id = str(d.get("id") or f"quad_{pred}_{tgt}_{idx}")
        indicator_name = f"q_{pred}_{tgt}"

        quadratics.append({
            "id": quad_id,
            "predictor": pred,
            "target": tgt,
            "predictor_name": pred_name,
            "target_name": tgt_name,
            "quad_construct_name": quad_construct_name,
            "indicator_name": indicator_name,
            "method": str(d.get("method") or "two_stage").lower(),
            "node_x": d.get("node_x") or d.get("nodeX"),
            "node_y": d.get("node_y") or d.get("nodeY"),
        })

    return spec_dict, quadratics


def calculate_kenny_f2(r2_included: float, r2_excluded: float) -> Dict[str, Any]:
    """
    Computes Kenny (2015) effect size f^2 = (R2_incl - R2_excl) / (1 - R2_incl).
    Thresholds: 0.005 (small), 0.010 (medium), 0.025 (large).
    """
    denom = max(1e-12, 1.0 - r2_included)
    f2_val = max(0.0, (r2_included - r2_excluded) / denom)

    if f2_val < 0.005:
        rating = "None (< 0.005)"
    elif f2_val < 0.010:
        rating = "Small (0.005 - 0.010)"
    elif f2_val < 0.025:
        rating = "Medium (0.010 - 0.025)"
    else:
        rating = "Large (>= 0.025)"

    return {
        "f_squared": round(float(f2_val), 4),
        "f_squared_raw": float(f2_val),
        "rating": rating,
        "r2_included": round(float(r2_included), 4),
        "r2_excluded": round(float(r2_excluded), 4),
    }


def compute_quadratic_diagnostics(
    b1_linear: float,
    b2_quad_unstd: float,
    scale: float,
    mean_sq: float,
    predictor_scores: np.ndarray,
    target_scores: Optional[np.ndarray] = None,
    b_linear_stage1: Optional[float] = None,
    f2_info: Optional[Dict[str, Any]] = None,
    p_value: Optional[float] = None,
    ci_lower: Optional[float] = None,
    ci_upper: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Computes marginal effects, turning point, effect plot coordinates,
    and interpretation text for a quadratic effect term.
    """
    sc = np.asarray(predictor_scores, dtype=float)
    min_x = float(np.nanmin(sc)) if len(sc) > 0 else -2.5
    max_x = float(np.nanmax(sc)) if len(sc) > 0 else 2.5

    b2_quad_std = float(b2_quad_unstd * scale)
    b_lin_ref = b_linear_stage1 if b_linear_stage1 is not None else b1_linear

    # Turning point: x* = -b1 / (2 * b2_unstd) = -b1 * s / (2 * b2_std)
    if abs(b2_quad_unstd) > 1e-9:
        turning_point = float(-b1_linear / (2.0 * b2_quad_unstd))
        turning_in_range = bool(min_x <= turning_point <= max_x)
    else:
        turning_point = None
        turning_in_range = False

    # Marginal effect table at [min, -1 SD, 0, +1 SD, max]
    levels = [
        ("Min (Observed)", min_x),
        ("-1 SD (Low)", -1.0),
        ("Mean (0 SD)", 0.0),
        ("+1 SD (High)", 1.0),
        ("Max (Observed)", max_x),
    ]

    marginal_effects = []
    for label, x_val in levels:
        # dy/dx = b1 + 2 * b2_unstd * x
        slope = float(b1_linear + 2.0 * b2_quad_unstd * x_val)
        # y_hat(x) = b1 * x + b2_unstd * (x^2 - mean_sq)
        y_hat = float(b1_linear * x_val + b2_quad_unstd * (x_val ** 2 - mean_sq))
        marginal_effects.append({
            "level": label,
            "x": round(float(x_val), 4),
            "slope": round(float(slope), 4),
            "predicted_y": round(float(y_hat), 4),
        })

    # Effect plot points across observed range (or [-3, +3])
    x_plot_min = max(min_x, -3.0)
    x_plot_max = min(max_x, 3.0)
    x_grid = np.linspace(x_plot_min, x_plot_max, 51)
    curve_points = []
    for x in x_grid:
        y_q = float(b1_linear * x + b2_quad_unstd * (x ** 2 - mean_sq))
        y_lin = float(b_lin_ref * x)
        curve_points.append({
            "x": round(float(x), 4),
            "y_nonlinear": round(float(y_q), 4),
            "y_linear": round(float(y_lin), 4),
        })

    # Shape classification
    is_sig = (p_value is not None and p_value < 0.05) or (ci_lower is not None and ci_upper is not None and (ci_lower > 0 or ci_upper < 0))
    if not is_sig and p_value is not None:
        shape = "Linear (no significant curvature)"
    elif b2_quad_unstd < 0:
        shape = "Inverted U-shape (diminishing returns)"
    else:
        shape = "U-shape (accelerating returns)"

    # Short interpretation text
    if not is_sig and p_value is not None:
        interpretation = (
            "The quadratic term is not statistically significant. "
            "A linear relationship is supported; the nonlinear term can be disregarded."
        )
    else:
        tp_text = (
            f"The turning point x* = {round(turning_point, 3)} SD lies within the observed range ({round(min_x, 2)} to {round(max_x, 2)})."
            if (turning_point is not None and turning_in_range)
            else "The turning point lies outside the observed range; the observed relationship is monotonic within the data."
        )
        interpretation = (
            f"A significant quadratic effect ({shape}) is observed. {tp_text} "
            f"Direction and strength of the effect vary depending on the level of the predictor."
        )

    return {
        "linear_effect": round(float(b1_linear), 4),
        "quadratic_effect": round(float(b2_quad_unstd), 4),
        "quadratic_effect_std": round(float(b2_quad_std), 4),
        "scale": round(float(scale), 4),
        "mean_sq": round(float(mean_sq), 4),
        "turning_point": round(float(turning_point), 4) if turning_point is not None else None,
        "turning_point_in_range": turning_in_range,
        "shape": shape,
        "interpretation": interpretation,
        "marginal_effects": marginal_effects,
        "curve_points": curve_points,
        "f_squared": f2_info.get("f_squared") if f2_info else None,
        "f_squared_rating": f2_info.get("rating") if f2_info else None,
        "p_value": round(float(p_value), 4) if p_value is not None else None,
        "ci_lower": round(float(ci_lower), 4) if ci_lower is not None else None,
        "ci_upper": round(float(ci_upper), 4) if ci_upper is not None else None,
        "is_significant": is_sig,
    }


def attach_bootstrap_to_quadratic(
    res: Dict[str, Any],
    boot_res: Dict[str, Any],
    alpha: float = 0.05,
) -> None:
    """
    Attaches bootstrap inference (SE, t, p-value, CI) to the nonlinear effects
    section of the results dictionary.
    """
    nl_block = res.get("nonlinear_effects")
    if not nl_block or not isinstance(nl_block, list):
        return

    p_summary = boot_res.get("parameter_summary") or boot_res.get("parameters") or {}
    coef_reps = boot_res.get("replicates") or boot_res.get("samples") or {}

    for item in nl_block:
        term_name = item.get("quad_construct_name")
        tgt = item.get("target")
        pkey = f"path:{term_name}->{tgt}"
        lin_key = f"path:{item.get('predictor')}->{tgt}"

        stat = p_summary.get(pkey, {})
        if stat:
            item["standard_error"] = round(float(stat.get("standard_error", 0.0)), 4)
            item["t_statistic"] = round(float(stat.get("t_statistic", 0.0)), 4)
            item["p_value"] = round(float(stat.get("p_value", 1.0)), 4)
            item["ci_lower"] = round(float(stat.get("ci_lower", 0.0)), 4)
            item["ci_upper"] = round(float(stat.get("ci_upper", 0.0)), 4)
            item["is_significant"] = bool(item["p_value"] < alpha)

        # Turning point bootstrap CI if replicates are available
        reps_b2 = coef_reps.get(pkey)
        reps_b1 = coef_reps.get(lin_key)
        if reps_b2 is not None and reps_b1 is not None and len(reps_b2) > 0:
            scale = float(item.get("scale", 1.0))
            # x* = -b1 / (2 * b2)
            valid_mask = np.abs(reps_b2) > 1e-6
            if np.sum(valid_mask) > len(reps_b2) * 0.8:
                tp_reps = -reps_b1[valid_mask] / (2.0 * reps_b2[valid_mask])
                tp_low = float(np.percentile(tp_reps, 100 * (alpha / 2)))
                tp_high = float(np.percentile(tp_reps, 100 * (1.0 - alpha / 2)))
                item["turning_point_ci_lower"] = round(tp_low, 4)
                item["turning_point_ci_upper"] = round(tp_high, 4)

        # Re-evaluate shape and interpretation with bootstrap inference
        if item.get("p_value") is not None:
            is_sig = item["is_significant"]
            b2 = item.get("quadratic_effect", 0.0)
            if not is_sig:
                item["shape"] = "Linear (no significant curvature)"
                item["interpretation"] = (
                    "The quadratic term is not statistically significant. "
                    "A linear relationship is supported; the nonlinear term can be disregarded."
                )
            else:
                shape = "Inverted U-shape (diminishing returns)" if b2 < 0 else "U-shape (accelerating returns)"
                item["shape"] = shape
                tp = item.get("turning_point")
                in_rng = item.get("turning_point_in_range", False)
                tp_text = f"The turning point x* = {round(tp, 3)} SD lies within the observed range." if (tp is not None and in_rng) else "The turning point lies outside the observed range; the relationship is monotonic within the data."
                item["interpretation"] = (
                    f"A significant quadratic effect ({shape}) is observed (p = {item['p_value']}). {tp_text}"
                )


def analyze_quadratic_effect(
    df: pd.DataFrame,
    spec: Union[Dict[str, Any], Any],
    source: str,
    target: str,
    approach: str = "two_stage",
    degree: int = 2,
    n_boot: int = 500,
    seed: Optional[int] = 42,
    alpha: float = 0.05,
    settings: Optional[PipelineSettings] = None,
    progress_callback: Optional[Any] = None,
    cancel_event: Optional[Any] = None,
) -> Dict[str, Any]:
    """
    Stand-alone helper to analyze a quadratic effect on a path (backward-compatible API).
    """
    from engine.pls.algorithm import run_pipeline

    spec_dict = spec.model_dump(mode="json", by_alias=True) if hasattr(spec, "model_dump") else copy.deepcopy(spec)
    cfg = settings or PipelineSettings()

    # Add quadratic effect to spec
    spec_with_quad = copy.deepcopy(spec_dict)
    quads = list(spec_with_quad.get("quadratic_effects", []))
    quads.append({
        "id": f"quad_{source}_{target}",
        "predictor_construct": source,
        "target_construct": target,
        "method": approach,
    })
    spec_with_quad["quadratic_effects"] = quads

    res = run_pipeline(df, spec_with_quad, cfg)

    # Bootstrapping
    if n_boot and n_boot > 0:
        from engine.pls.bootstrap import ParallelBootstrapper
        booter = ParallelBootstrapper()
        boot_res = booter.run(
            data=df,
            model_spec=spec_with_quad,
            n_boot=n_boot,
            seed=seed,
            scheme=cfg.inner_weighting,
            alpha=alpha,
            progress_callback=progress_callback,
            cancel_event=cancel_event,
        )
        res["significance"] = boot_res
        attach_bootstrap_to_quadratic(res, boot_res, alpha=alpha)

    # Return summary dict
    nl_list = res.get("nonlinear_effects", [])
    quad_info = next((item for item in nl_list if item.get("predictor") == source and item.get("target") == target), (nl_list[0] if nl_list else {}))
    return quad_info
