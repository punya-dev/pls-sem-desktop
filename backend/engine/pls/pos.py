"""
Prediction-Oriented Segmentation in PLS-SEM (PLS-POS) (A18-POS-01 to A18-POS-13).
Source of truth: Hair et al. (2018) Ch. 5, Becker et al. (2013), and Squillacciotti (2005, 2010).

Implements:
1. Sequential hill-climbing reallocation algorithm based on structural prediction errors.
2. Distance measure: sum of squared residuals across endogenous constructs.
3. Starting partition options: Random assignment (10 repetitions, keep best) or FIMIX-PLS partition.
4. Pre-segmentation option for random starts.
5. User-selectable optimization criteria:
   - Sum of all construct weighted R^2 (default)
   - Sum of all construct R^2
   - R^2 of a selected target endogenous construct
6. Search depth D and maximum iterations max(1000, 2N).
7. Segment-specific estimates, signed path differences (segment 1 - segment 2), and quality judgement.
"""

from typing import List, Dict, Any, Optional, Tuple, Union
import math
import numpy as np
import pandas as pd

from core.settings_schema import PipelineSettings
from engine.pls.algorithm import run_pipeline


def _evaluate_partition_objective(
    df: pd.DataFrame,
    spec_dict: Dict[str, Any],
    assignments: np.ndarray,
    n_segments: int,
    criterion: str = "weighted_r2",
    target_construct: Optional[str] = None,
    settings: Optional[PipelineSettings] = None,
) -> Tuple[float, List[Dict[str, Any]], Dict[str, float]]:
    """
    Estimates segment-specific PLS models and computes the optimization criterion.
    Returns: (objective_value, segment_results, weighted_r2_map)
    """
    cfg = settings or PipelineSettings()
    N = len(df)
    S = n_segments
    segment_results: List[Dict[str, Any]] = []

    # Get endogenous constructs
    paths = spec_dict.get("paths", [])
    endo_constructs = sorted(list(set(p.get("to") or p.get("to_node") for p in paths)))

    r2_by_seg_endo: Dict[int, Dict[str, float]] = {s: {} for s in range(S)}
    seg_sizes = [int(np.sum(assignments == s)) for s in range(S)]

    for s in range(S):
        seg_mask = (assignments == s)
        n_s = seg_sizes[s]
        if n_s < 3:
            return -np.inf, [], {}

        df_s = df.iloc[seg_mask].copy()
        try:
            res_s = run_pipeline(df_s, spec_dict, cfg)
        except Exception:
            return -np.inf, [], {}

        segment_results.append(res_s)
        r2_map = res_s.get("structural", {}).get("r_squared", {})
        for endo_c in endo_constructs:
            r2_by_seg_endo[s][endo_c] = float(r2_map.get(endo_c, 0.0))

    # Compute weighted R^2 per construct
    weighted_r2: Dict[str, float] = {}
    for endo_c in endo_constructs:
        w_sum = sum((seg_sizes[s] / N) * r2_by_seg_endo[s].get(endo_c, 0.0) for s in range(S))
        weighted_r2[endo_c] = round(float(w_sum), 4)

    # Compute objective
    if criterion == "weighted_r2":
        # Sum of all construct weighted R^2 (A18-POS-05 default)
        obj_val = float(sum(weighted_r2.values()))
    elif criterion == "sum_r2":
        # Sum of all construct R^2 across segments (unweighted)
        obj_val = float(sum(sum(r2_by_seg_endo[s].values()) for s in range(S)))
    elif criterion == "target_r2" and target_construct:
        obj_val = float(weighted_r2.get(target_construct, 0.0))
    else:
        obj_val = float(sum(weighted_r2.values()))

    return obj_val, segment_results, weighted_r2


def _compute_prediction_distances(
    df: pd.DataFrame,
    spec_dict: Dict[str, Any],
    assignments: np.ndarray,
    segment_models: List[Dict[str, Any]],
    n_segments: int,
    settings: Optional[PipelineSettings] = None,
) -> np.ndarray:
    """
    Computes distance matrix D of shape (N, S) based on structural model residuals (A18-POS-08).
    For each observation and segment: Error_is = sum over endogenous constructs of (y_ij - y_hat_ij)^2.
    """
    cfg = settings or PipelineSettings()
    N = len(df)
    S = n_segments
    paths = spec_dict.get("paths", [])
    endo_constructs = sorted(list(set(p.get("to") or p.get("to_node") for p in paths)))

    preds_per_endo: Dict[str, List[str]] = {}
    for p in paths:
        fc = p.get("from") or p.get("from_node")
        tc = p.get("to") or p.get("to_node")
        if tc not in preds_per_endo:
            preds_per_endo[tc] = []
        if fc not in preds_per_endo[tc]:
            preds_per_endo[tc].append(fc)

    dist_matrix = np.zeros((N, S), dtype=float)

    for s, model_s in enumerate(segment_models):
        # Evaluate whole dataset with segment s parameters
        try:
            eval_s = run_pipeline(df, spec_dict, cfg)
            scores_s = eval_s.get("construct_scores", {})
            paths_s = model_s.get("structural", {}).get("path_coefficients", {})

            for endo_c in endo_constructs:
                y_act = np.asarray(scores_s.get(endo_c, np.zeros(N)), dtype=float)
                pred_cids = preds_per_endo.get(endo_c, [])

                y_pred = np.zeros(N, dtype=float)
                for p_c in pred_cids:
                    beta_val = float(paths_s.get(endo_c, {}).get(p_c, 0.0))
                    p_score = np.asarray(scores_s.get(p_c, np.zeros(N)), dtype=float)
                    y_pred += beta_val * p_score

                res_sq = (y_act - y_pred) ** 2
                dist_matrix[:, s] += res_sq
        except Exception:
            dist_matrix[:, s] = 1e6

    return dist_matrix


def _run_single_pos(
    df: pd.DataFrame,
    spec_dict: Dict[str, Any],
    initial_assignments: np.ndarray,
    n_segments: int,
    criterion: str = "weighted_r2",
    target_construct: Optional[str] = None,
    pre_segmentation: bool = False,
    search_depth: Optional[int] = None,
    max_iter: int = 1000,
    min_segment_size: int = 15,
    settings: Optional[PipelineSettings] = None,
    cancel_event: Optional[Any] = None,
) -> Dict[str, Any]:
    """
    Executes a single run of the sequential hill-climbing PLS-POS algorithm.
    """
    N = len(df)
    S = n_segments
    assignments = initial_assignments.copy()
    depth = min(N, search_depth if search_depth is not None else N)

    # Initial evaluation
    curr_obj, segment_models, weighted_r2 = _evaluate_partition_objective(
        df=df,
        spec_dict=spec_dict,
        assignments=assignments,
        n_segments=S,
        criterion=criterion,
        target_construct=target_construct,
        settings=settings,
    )

    if not segment_models or curr_obj == -np.inf:
        return {"objective": -np.inf, "converged": False, "iterations": 0}

    objective_history = [round(curr_obj, 4)]
    converged = False

    # Optional Pre-segmentation (A18-POS-03)
    if pre_segmentation:
        dist_mat = _compute_prediction_distances(df, spec_dict, assignments, segment_models, S, settings)
        pre_assign = np.argmin(dist_mat, axis=1)
        # Check minimum segment sizes
        if all(np.sum(pre_assign == s) >= min_segment_size for s in range(S)):
            pre_obj, pre_models, pre_wr2 = _evaluate_partition_objective(
                df, spec_dict, pre_assign, S, criterion, target_construct, settings
            )
            if pre_obj > curr_obj:
                assignments = pre_assign
                curr_obj = pre_obj
                segment_models = pre_models
                weighted_r2 = pre_wr2
                objective_history.append(round(curr_obj, 4))

    for iteration in range(max_iter):
        if cancel_event and cancel_event.is_set():
            raise RuntimeError("PLS-POS cancelled by user.")

        # Step 4: Compute distances of each case to every segment
        dist_mat = _compute_prediction_distances(df, spec_dict, assignments, segment_models, S, settings)

        # Step 5: Build candidate list of observations closer to another segment (A18-POS-07)
        candidates = []
        for i in range(N):
            curr_s = assignments[i]
            d_own = dist_mat[i, curr_s]

            # Find closest alternative segment
            alt_segments = [s for s in range(S) if s != curr_s]
            alt_dists = [dist_mat[i, s] for s in alt_segments]
            best_alt_idx = int(np.argmin(alt_dists))
            best_alt_s = alt_segments[best_alt_idx]
            d_alt = alt_dists[best_alt_idx]

            diff = d_own - d_alt
            if diff > 1e-6:
                candidates.append({
                    "case_idx": i,
                    "from_seg": curr_s,
                    "to_seg": best_alt_s,
                    "improvement": diff,
                })

        if not candidates:
            converged = True
            break

        # Sort candidates in descending order of distance improvement
        candidates.sort(key=lambda c: c["improvement"], reverse=True)
        candidates = candidates[:depth]

        move_made = False

        # Step 6: Test moving candidates ONE BY ONE
        for cand in candidates:
            c_idx = cand["case_idx"]
            f_seg = cand["from_seg"]
            t_seg = cand["to_seg"]

            # Guard minimum segment size
            if np.sum(assignments == f_seg) <= min_segment_size:
                continue

            # Tentatively apply move
            assignments[c_idx] = t_seg

            new_obj, new_models, new_wr2 = _evaluate_partition_objective(
                df=df,
                spec_dict=spec_dict,
                assignments=assignments,
                n_segments=S,
                criterion=criterion,
                target_construct=target_construct,
                settings=settings,
            )

            if new_obj > curr_obj + 1e-7:
                # Keep move!
                curr_obj = new_obj
                segment_models = new_models
                weighted_r2 = new_wr2
                objective_history.append(round(curr_obj, 4))
                move_made = True
                break
            else:
                # Revert move
                assignments[c_idx] = f_seg

        if not move_made:
            converged = True
            break

    # Extract final segment summaries
    final_segments = []
    for s in range(S):
        seg_mask = (assignments == s)
        n_s = int(np.sum(seg_mask))
        model_s = segment_models[s]

        final_segments.append({
            "segment": s + 1,
            "sample_size": n_s,
            "relative_size": round(float(n_s) / N, 4),
            "r_squared": {k: round(float(v), 4) for k, v in model_s.get("structural", {}).get("r_squared", {}).items()},
            "path_coefficients": model_s.get("structural", {}).get("path_coefficients", {}),
        })

    # Signed path differences (Segment 1 - Segment 2) if S == 2 (A18-POS-10)
    signed_path_diffs: Dict[str, Dict[str, float]] = {}
    if S >= 2:
        paths_s1 = segment_models[0].get("structural", {}).get("path_coefficients", {})
        paths_s2 = segment_models[1].get("structural", {}).get("path_coefficients", {})
        for tc, preds_map in paths_s1.items():
            signed_path_diffs[tc] = {}
            for fc, b1 in preds_map.items():
                b2 = float(paths_s2.get(tc, {}).get(fc, 0.0))
                signed_path_diffs[tc][fc] = round(float(b1) - b2, 4)

    return {
        "objective": curr_obj,
        "objective_history": objective_history,
        "converged": converged,
        "iterations": len(objective_history) - 1,
        "assignments": assignments,
        "segments": final_segments,
        "signed_path_differences": signed_path_diffs,
        "weighted_r_squared": weighted_r2,
    }


def analyze_pos(
    df: pd.DataFrame,
    spec: Union[Dict[str, Any], Any],
    n_segments: int = 2,
    initial_separation: str = "random",  # "random" or "fimix"
    fimix_assignments: Optional[List[int]] = None,
    criterion: str = "weighted_r2",  # "weighted_r2", "sum_r2", "target_r2"
    optimization_criterion: Optional[str] = None,
    target_construct: Optional[str] = None,
    pre_segmentation: bool = False,
    search_depth: Optional[int] = None,
    max_iter: Optional[int] = None,
    min_segment_size: int = 15,
    n_repetitions: int = 10,
    seed: Optional[int] = 42,
    settings: Optional[PipelineSettings] = None,
    progress_callback: Optional[Any] = None,
    cancel_event: Optional[Any] = None,
) -> Dict[str, Any]:
    """
    Main entry point for Prediction-Oriented Segmentation (PLS-POS) (A18-POS-01 to A18-POS-13).
    """
    spec_dict = spec.model_dump(mode="json", by_alias=True) if hasattr(spec, "model_dump") else (spec if isinstance(spec, dict) else {})
    cfg = settings or PipelineSettings()
    S = n_segments
    N = len(df)

    if optimization_criterion is not None:
        if "weight" in optimization_criterion.lower():
            criterion = "weighted_r2"
        elif "sum" in optimization_criterion.lower():
            criterion = "sum_r2"
        elif "target" in optimization_criterion.lower():
            criterion = "target_r2"
        else:
            criterion = optimization_criterion

    if S < 2:
        raise ValueError("PLS-POS requires at least 2 segments.")

    # A18-POS-06: Max iterations default = max(1000, 2N)
    effective_max_iter = max_iter if max_iter is not None else max(1000, 2 * N)
    depth = search_depth if search_depth is not None else N

    # Baseline global model R^2
    res_global = run_pipeline(df, spec_dict, cfg)
    global_r2 = {
        k: round(float(v), 4)
        for k, v in res_global.get("structural", {}).get("r_squared", {}).items()
    }

    best_result: Optional[Dict[str, Any]] = None
    best_obj = -np.inf

    # Execution branches: FIMIX vs Random
    if initial_separation == "fimix":
        if fimix_assignments is None or len(fimix_assignments) != N:
            # Run FIMIX-PLS to extract initial partition
            from engine.pls.fimix import analyze_fimix
            fim_res = analyze_fimix(df, spec_dict, min_segments=S, max_segments=S, seed=seed, settings=cfg)
            fimix_assignments = fim_res["case_assignments"]

        init_assign = np.array([int(a) - 1 for a in fimix_assignments], dtype=int)
        # Pre-segmentation is not allowed with FIMIX start (A18-POS-03)
        res = _run_single_pos(
            df=df,
            spec_dict=spec_dict,
            initial_assignments=init_assign,
            n_segments=S,
            criterion=criterion,
            target_construct=target_construct,
            pre_segmentation=False,
            search_depth=depth,
            max_iter=effective_max_iter,
            min_segment_size=min_segment_size,
            settings=cfg,
            cancel_event=cancel_event,
        )
        best_result = res
        best_obj = res["objective"]

    else:
        # Random start with n_repetitions (A18-POS-02, A18-POS-11)
        reps = max(1, n_repetitions)
        rng = np.random.default_rng(seed)

        for rep in range(reps):
            if cancel_event and cancel_event.is_set():
                raise RuntimeError("PLS-POS cancelled by user.")

            # Random partition ensuring min segment size
            valid_part = False
            for _ in range(50):
                init_assign = rng.integers(0, S, size=N)
                if all(np.sum(init_assign == s) >= min_segment_size for s in range(S)):
                    valid_part = True
                    break

            if not valid_part:
                init_assign = np.array([i % S for i in range(N)])

            res = _run_single_pos(
                df=df,
                spec_dict=spec_dict,
                initial_assignments=init_assign,
                n_segments=S,
                criterion=criterion,
                target_construct=target_construct,
                pre_segmentation=pre_segmentation,
                search_depth=depth,
                max_iter=effective_max_iter,
                min_segment_size=min_segment_size,
                settings=cfg,
                cancel_event=cancel_event,
            )

            if res["objective"] > best_obj:
                best_obj = res["objective"]
                best_result = res

            if progress_callback:
                progress_callback(int(((rep + 1) / reps) * 100))

    if not best_result or best_obj == -np.inf:
        raise RuntimeError("PLS-POS failed to establish a valid segment solution.")

    # Quality judgement (A18-POS-12): Compare weighted average R^2 with global R^2
    weighted_r2 = best_result["weighted_r_squared"]
    substantially_higher = all(
        weighted_r2.get(k, 0.0) >= global_r2.get(k, 0.0)
        for k in global_r2.keys()
    )
    quality_verdict = (
        "PLS-POS segmentation substantially improves variance explained (weighted R^2 exceeds global sample R^2)."
        if substantially_higher else
        "Heterogeneity appears modest; segment-specific R^2 values are comparable to the full sample."
    )

    return {
        "n_segments": S,
        "n_samples": N,
        "initial_separation": initial_separation,
        "optimization_criterion": criterion,
        "converged": best_result["converged"],
        "iterations": best_result["iterations"],
        "final_objective": round(best_obj, 4),
        "objective_history": best_result["objective_history"],
        "segments": best_result["segments"],
        "segment_sample_sizes": [seg["sample_size"] for seg in best_result["segments"]],
        "signed_path_differences": best_result.get("signed_path_differences", {}),
        "weighted_r_squared": weighted_r2,
        "full_sample_r_squared": global_r2,
        "quality_judgement": quality_verdict,
        "case_assignments": [int(s) + 1 for s in best_result["assignments"]],
        "segment_assignments": [int(s) + 1 for s in best_result["assignments"]],
        "note": "PLS-POS reallocates cases using distance measures to maximize overall predictive power (Hair et al. 2018; Squillacciotti 2005).",
    }
