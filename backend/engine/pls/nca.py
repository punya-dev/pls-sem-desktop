"""
Necessary Condition Analysis (NCA) (Section 25: X-B, X-02).
Source of truth: Dul (2016) & Richter et al. (2020).
Evaluates necessity relationships (in contrast to sufficiency in regression):
Computes CE-FDH and CR-FDH ceiling lines, effect size d = C / S, accuracy,
permutation significance test, and bottleneck capacity tables.
"""

from typing import List, Dict, Any, Optional, Tuple, Union
import numpy as np
import pandas as pd

from core.settings_schema import PipelineSettings
from core.rng import spawn_seeds
from engine.pls.algorithm import run_pipeline


def compute_ce_fdh(
    x: np.ndarray,
    y: np.ndarray,
) -> Tuple[np.ndarray, np.ndarray, float, float]:
    """
    Computes Ceiling Envelopment with Free Disposal Hull (CE-FDH) (Dul 2016).
    Step function along the upper-left border of the scatter plot.
    Returns (x_steps, y_steps, ceiling_area, effect_size_d).
    """
    N = len(x)
    x_min, x_max = float(np.min(x)), float(np.max(x))
    y_min, y_max = float(np.min(y)), float(np.max(y))
    scope = max(1e-12, (x_max - x_min) * (y_max - y_min))

    # Sort points by x ascending
    sort_idx = np.argsort(x)
    xs = x[sort_idx]
    ys = y[sort_idx]

    # Find upper-left corner peers: points (x_i, y_i) such that no other point has x <= x_i and y > y_i
    # Running maximum of y from left to right
    peer_x = []
    peer_y = []
    current_max_y = -np.inf

    for i in range(N):
        if ys[i] > current_max_y:
            peer_x.append(xs[i])
            peer_y.append(ys[i])
            current_max_y = ys[i]

    peer_x = np.array(peer_x)
    peer_y = np.array(peer_y)

    # Ceiling zone area above the step function within [x_min, x_max] x [y_min, y_max]
    # The area under the ceiling step function from x_min to x_max:
    # For x in [x_min, peer_x[0]], height is y_min (or peer_y[0] if left-extended)
    area_below = 0.0
    prev_x = x_min
    prev_y = y_min

    for px, py in zip(peer_x, peer_y):
        area_below += max(0.0, (px - prev_x) * (prev_y - y_min))
        prev_x = px
        prev_y = py

    area_below += max(0.0, (x_max - prev_x) * (prev_y - y_min))

    # Area above ceiling line (ceiling zone C)
    C = max(0.0, scope - area_below)
    d = float(C / scope)

    return peer_x, peer_y, float(C), float(d)


def compute_cr_fdh(
    peer_x: np.ndarray,
    peer_y: np.ndarray,
    x_min: float,
    x_max: float,
    y_min: float,
    y_max: float,
) -> Tuple[float, float, float]:
    """
    Computes Ceiling Regression with Free Disposal Hull (CR-FDH).
    Fits an OLS line through the CE-FDH peer points.
    Returns (slope, intercept, effect_size_d).
    """
    scope = max(1e-12, (x_max - x_min) * (y_max - y_min))
    if len(peer_x) >= 2:
        slope, intercept = np.polyfit(peer_x, peer_y, 1)
    else:
        slope = 0.0
        intercept = float(peer_y[0]) if len(peer_y) > 0 else y_min

    # Integrate area above line y = slope * x + intercept within scope
    # Clamp line values to [y_min, y_max]
    x_grid = np.linspace(x_min, x_max, 200)
    line_y = np.clip(slope * x_grid + intercept, y_min, y_max)
    area_below = float(np.trapezoid(line_y - y_min, x_grid))
    C = max(0.0, scope - area_below)
    d = float(C / scope)

    return float(slope), float(intercept), float(d)


def generate_bottleneck_table(
    peer_x: np.ndarray,
    peer_y: np.ndarray,
    x_min: float,
    x_max: float,
    y_min: float,
    y_max: float,
) -> List[Dict[str, Any]]:
    """
    Constructs NCA Bottleneck Table for outcome levels 0% to 100% (step 10%) (X-B).
    Reports minimum required predictor level.
    """
    levels = np.linspace(0.0, 100.0, 11)
    rows = []

    for pct in levels:
        target_y = y_min + (pct / 100.0) * (y_max - y_min)
        # Find minimum x peer that achieves target_y
        valid_peers = peer_x[peer_y >= target_y]
        if len(valid_peers) > 0:
            min_req_x = float(np.min(valid_peers))
            x_pct = max(0.0, min(100.0, ((min_req_x - x_min) / max(1e-12, x_max - x_min)) * 100.0))
            req_str = f"{round(x_pct, 1)}%"
        else:
            x_pct = 0.0
            req_str = "NN"  # Not Necessary

        rows.append({
            "outcome_level_pct": int(pct),
            "outcome_value": round(float(target_y), 4),
            "required_predictor_pct": req_str,
            "is_bottleneck": req_str != "NN" and x_pct > 0.0,
        })

    return rows


def analyze_nca(
    df: pd.DataFrame,
    spec: Union[Dict[str, Any], Any],
    predictor: str,
    outcome: str,
    n_permutations: int = 500,
    seed: Optional[int] = 42,
    alpha: float = 0.05,
    settings: Optional[PipelineSettings] = None,
    cancel_event: Optional[Any] = None,
) -> Dict[str, Any]:
    """
    Executes Necessary Condition Analysis (NCA) between predictor construct and outcome construct (X-B, X-02).
    """
    spec_dict = spec.model_dump(mode="json", by_alias=True) if hasattr(spec, "model_dump") else (spec if isinstance(spec, dict) else {})
    cfg = settings or PipelineSettings()

    # Get scores
    res_pls = run_pipeline(df, spec_dict, cfg)
    scores = res_pls.get("construct_scores", {})
    N = len(df)

    if predictor not in scores or outcome not in scores:
        raise ValueError(f"Constructs '{predictor}' and '{outcome}' must exist in the model.")

    x = np.asarray(scores[predictor], dtype=float)
    y = np.asarray(scores[outcome], dtype=float)

    x_min, x_max = float(np.min(x)), float(np.max(x))
    y_min, y_max = float(np.min(y)), float(np.max(y))
    scope = max(1e-12, (x_max - x_min) * (y_max - y_min))

    # CE-FDH
    peer_x, peer_y, c_ce, d_ce = compute_ce_fdh(x, y)

    # CR-FDH
    slope_cr, int_cr, d_cr = compute_cr_fdh(peer_x, peer_y, x_min, x_max, y_min, y_max)

    # Accuracy of CR-FDH ceiling (percentage of points on or below line)
    cr_pred_y = slope_cr * x + int_cr
    accuracy_cr = float(np.mean(y <= cr_pred_y + 1e-6) * 100.0)

    # Permutation test for effect size d_ce
    seeds = spawn_seeds(seed or 42, n_permutations)
    perm_d = np.zeros(n_permutations, dtype=float)

    for p in range(n_permutations):
        if cancel_event and cancel_event.is_set():
            raise RuntimeError("NCA cancelled by user.")
        p_rng = np.random.default_rng(seeds[p])
        y_perm = p_rng.permutation(y)
        _, _, _, d_p = compute_ce_fdh(x, y_perm)
        perm_d[p] = d_p

    p_value = float((np.sum(perm_d >= d_ce) + 1.0) / (n_permutations + 1.0))
    is_necessary = bool(d_ce >= 0.10 and p_value < alpha)

    # Effect size magnitude (Dul 2016)
    if d_ce >= 0.50:
        magnitude = "large"
    elif d_ce >= 0.30:
        magnitude = "medium"
    elif d_ce >= 0.10:
        magnitude = "small"
    else:
        magnitude = "negligible"

    # Bottleneck table
    bottleneck_table = generate_bottleneck_table(peer_x, peer_y, x_min, x_max, y_min, y_max)

    return {
        "predictor": predictor,
        "outcome": outcome,
        "n_samples": N,
        "scope": round(scope, 4),
        "effect_size_d_ce": round(d_ce, 4),
        "effect_size_d_cr": round(d_cr, 4),
        "p_value": round(p_value, 4),
        "is_necessary": is_necessary,
        "ce_fdh": {
            "ceiling_zone_area": round(c_ce, 4),
            "effect_size_d": round(d_ce, 4),
            "p_value": round(p_value, 4),
            "is_necessary": is_necessary,
            "magnitude": magnitude,
            "accuracy": 100.0,
        },
        "cr_fdh": {
            "slope": round(slope_cr, 4),
            "intercept": round(int_cr, 4),
            "effect_size_d": round(d_cr, 4),
            "accuracy_pct": round(accuracy_cr, 2),
        },
        "bottleneck_table": bottleneck_table,
        "interpretation": (
            f"Construct '{predictor}' {'is a necessary condition' if is_necessary else 'is not a necessary condition'} "
            f"for '{outcome}' (CE-FDH d = {round(d_ce, 4)}, p = {round(p_value, 4)}, {magnitude} effect). "
            f"{'Without sufficient levels of ' + predictor + ', high levels of ' + outcome + ' are impossible (Dul 2016).' if is_necessary else ''}"
        ),
    }
