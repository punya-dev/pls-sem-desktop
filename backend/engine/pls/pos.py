"""
Prediction-Oriented Segmentation in PLS-SEM (PLS-POS) (Section 21: LAT-06 to LAT-07).
Source of truth: Becker et al. (2013) & Hair et al. (2017) Ch. 8.
Iterative reassignment algorithm optimizing prediction-oriented distance measures
to uncover unobserved heterogeneity.
"""

from typing import List, Dict, Any, Optional, Tuple, Union
import numpy as np
import pandas as pd

from core.settings_schema import PipelineSettings
from engine.pls.algorithm import run_pipeline


def analyze_pos(
    df: pd.DataFrame,
    spec: Union[Dict[str, Any], Any],
    n_segments: int = 2,
    max_iter: int = 50,
    min_segment_size: int = 15,
    seed: Optional[int] = 42,
    settings: Optional[PipelineSettings] = None,
    progress_callback: Optional[Any] = None,
    cancel_event: Optional[Any] = None,
) -> Dict[str, Any]:
    """
    Executes Prediction-Oriented Segmentation (PLS-POS) (LAT-06, LAT-07).
    """
    spec_dict = spec.model_dump(by_alias=True) if hasattr(spec, "model_dump") else (spec if isinstance(spec, dict) else {})
    cfg = settings or PipelineSettings()
    S = n_segments
    N = len(df)
    rng = np.random.default_rng(seed)

    if S < 2:
        raise ValueError("PLS-POS requires at least 2 segments.")

    # Initial partition using random or k-means on global scores
    res_global = run_pipeline(df, spec_dict, cfg)
    scores_dict = res_global.get("construct_scores", {})
    c_names = list(scores_dict.keys())

    X_scores = np.column_stack([np.asarray(scores_dict[c], dtype=float) for c in c_names])

    # K-means style initial partition
    # Pick S random initial centers
    center_indices = rng.choice(N, size=S, replace=False)
    centers = X_scores[center_indices]
    dists = np.linalg.norm(X_scores[:, None, :] - centers[None, :, :], axis=2)
    assignments = np.argmin(dists, axis=1)

    # Ensure min_segment_size
    for s in range(S):
        if np.sum(assignments == s) < min_segment_size:
            # Rebalance
            assignments = rng.integers(0, S, size=N)
            break

    # Identify endogenous constructs
    paths = spec_dict.get("paths", [])
    endo_constructs = list(set(p.get("to") or p.get("to_node") for p in paths))

    objective_history = []
    converged = False

    for iteration in range(max_iter):
        if cancel_event and cancel_event.is_set():
            raise RuntimeError("PLS-POS cancelled by user.")

        # Estimate segment-specific PLS models
        segment_models = []
        segment_r2 = {s: {} for s in range(S)}
        valid_segments = True

        for s in range(S):
            seg_mask = (assignments == s)
            if np.sum(seg_mask) < min_segment_size:
                valid_segments = False
                break
            df_s = df.iloc[seg_mask].copy()
            res_s = run_pipeline(df_s, spec_dict, cfg)
            segment_models.append(res_s)
            r2_map = res_s.get("structural", {}).get("r_squared", {})
            for endo_c, val in r2_map.items():
                segment_r2[s][endo_c] = float(val)

        if not valid_segments:
            # Stop if segment collapses
            break

        # Calculate Distance Measure DM for each case to each segment
        # DM_is = sum over endogenous constructs of (y_i - y_hat_i_s)^2
        distance_matrix = np.zeros((N, S), dtype=float)

        for s, model_s in enumerate(segment_models):
            paths_s = model_s.get("structural", {}).get("path_coefficients", {})
            # Predict scores of all cases using segment s weights
            # To do this cleanly, run evaluation on whole dataset with segment s settings
            eval_s = run_pipeline(df, spec_dict, cfg)
            scores_eval = eval_s.get("construct_scores", {})

            for endo_c in endo_constructs:
                y_act = np.asarray(scores_eval.get(endo_c, np.zeros(N)), dtype=float)
                # Predict from predecessors
                preds = [p.get("from") or p.get("from_node") for p in paths if (p.get("to") or p.get("to_node")) == endo_c]
                y_pred = sum(
                    float(paths_s.get(endo_c, {}).get(p_c, 0.0)) * np.asarray(scores_eval.get(p_c, np.zeros(N)), dtype=float)
                    for p_c in preds
                )
                residuals = (y_act - y_pred) ** 2
                distance_matrix[:, s] += residuals

        new_assignments = np.argmin(distance_matrix, axis=1)

        # Check constraint: each segment must have at least min_segment_size
        counts = [int(np.sum(new_assignments == s)) for s in range(S)]
        if any(c < min_segment_size for c in counts):
            # Keep previous assignments and terminate
            break

        total_distance = float(np.sum(np.min(distance_matrix, axis=1)))
        objective_history.append(total_distance)

        # Check convergence: no cases moved
        changes = int(np.sum(assignments != new_assignments))
        assignments = new_assignments

        if changes == 0:
            converged = True
            break

        if progress_callback:
            progress_callback(int(((iteration + 1) / max_iter) * 100))

    # Final summary per segment
    segment_summaries = []
    for s in range(S):
        seg_mask = (assignments == s)
        n_s = int(np.sum(seg_mask))
        df_s = df.iloc[seg_mask]
        res_s = run_pipeline(df_s, spec_dict, cfg)

        segment_summaries.append({
            "segment": s + 1,
            "sample_size": n_s,
            "relative_size": round(float(n_s) / N, 4),
            "r_squared": {k: round(float(v), 4) for k, v in res_s.get("structural", {}).get("r_squared", {}).items()},
            "path_coefficients": res_s.get("structural", {}).get("path_coefficients", {}),
        })

    return {
        "n_segments": S,
        "n_samples": N,
        "converged": converged,
        "iterations": len(objective_history),
        "objective_history": [round(val, 4) for val in objective_history],
        "segments": segment_summaries,
        "case_assignments": [int(s) + 1 for s in assignments],
        "note": "PLS-POS partitions data to maximize predictive accuracy and variance explained in endogenous constructs (Becker et al. 2013).",
    }
