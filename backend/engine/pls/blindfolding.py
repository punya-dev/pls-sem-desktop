"""
Blindfolding, Predictive Relevance Q^2, and q^2 Effect Sizes (Section 13: BLI-01 to BLI-10).
Source of truth: Hair et al. (2017) Ch. 6.
Evaluates cross-validated redundancy and cross-validated communality for endogenous reflective constructs.
"""

from typing import List, Dict, Any, Optional, Tuple, Union
import math
import numpy as np
import pandas as pd

from core.settings_schema import PipelineSettings
from core.thresholds import THRESHOLDS
from engine.pls.algorithm import run_pipeline, parse_model_spec


def validate_omission_distance(n_samples: int, omission_distance: int = 7) -> int:
    """
    Validates omission distance D (BLI-01).
    Rules:
    - Must be between 5 and 10.
    - N / D must NOT be an integer (N % D != 0).
    """
    if omission_distance < 5 or omission_distance > 10:
        raise ValueError(f"Omission distance D must be between 5 and 10 (got {omission_distance}).")

    if n_samples % omission_distance == 0:
        valid_ds = [d for d in range(5, 11) if n_samples % d != 0]
        valid_str = ", ".join(map(str, valid_ds))
        raise ValueError(
            f"Omission distance D={omission_distance} is invalid because N/D is an integer ({n_samples}/{omission_distance} = {n_samples//omission_distance}). "
            f"Suggested valid omission distances for N={n_samples}: {valid_str}"
        )

    return omission_distance


def _run_single_blindfold_pass(
    df: pd.DataFrame,
    spec_dict: Dict[str, Any],
    all_indicators: List[str],
    endogenous_constructs: List[str],
    construct_indicator_map: Dict[str, List[str]],
    omission_distance: int,
    settings: PipelineSettings,
    progress_callback: Optional[Any] = None,
    cancel_event: Optional[Any] = None,
) -> Dict[str, Any]:
    """
    Runs the D rounds of blindfolding and computes SSE and SSO for redundancy and communality.
    """
    N = len(df)
    K = len(all_indicators)
    D = omission_distance

    # Track SSE and SSO per indicator
    sse_red = {ind: 0.0 for ind in all_indicators}
    sso_red = {ind: 0.0 for ind in all_indicators}
    sse_comm = {ind: 0.0 for ind in all_indicators}
    sso_comm = {ind: 0.0 for ind in all_indicators}

    raw_data = df[all_indicators].values.astype(float)
    # Exclude cells that are originally NaN
    valid_mask = ~np.isnan(raw_data)

    c_to_inds = construct_indicator_map
    ind_to_c = {}
    for cid, inds in c_to_inds.items():
        for iid in inds:
            ind_to_c[iid] = cid

    # Predecessors map
    preds_map: Dict[str, List[str]] = {c["id"]: [] for c in spec_dict.get("constructs", [])}
    for p in spec_dict.get("paths", []):
        fc = p.get("from") or p.get("from_node")
        tc = p.get("to") or p.get("to_node")
        if tc in preds_map and fc not in preds_map[tc]:
            preds_map[tc].append(fc)

    for d in range(D):
        if cancel_event and cancel_event.is_set():
            raise RuntimeError("Blindfolding calculation cancelled by user.")

        if progress_callback:
            progress_callback(int((d / D) * 100))

        # Copy data for this round as float to allow float mean replacements
        df_round = df.copy()
        for c in all_indicators:
            if c in df_round.columns:
                df_round[c] = df_round[c].astype(float)
        round_data = raw_data.copy()

        # Omission mask for round d: cell index (i * K + k) % D == d
        cell_indices = np.arange(N * K).reshape(N, K)
        omit_mask = ((cell_indices % D) == d) & valid_mask

        # Impute omitted cells with column mean of remaining non-omitted values
        for k_idx, ind_col in enumerate(all_indicators):
            col_valid_retained = valid_mask[:, k_idx] & (~omit_mask[:, k_idx])
            if np.any(col_valid_retained):
                col_mean = float(np.mean(raw_data[col_valid_retained, k_idx]))
            else:
                col_mean = 0.0

            # Replace omitted cells in df_round
            df_round.loc[omit_mask[:, k_idx], ind_col] = col_mean
            round_data[omit_mask[:, k_idx], k_idx] = col_mean

        # Estimate PLS model on round data
        round_settings = settings.model_copy(update={"missing_treatment": "mean"})
        res_round = run_pipeline(df_round, spec_dict, round_settings)

        loadings = res_round.get("measurement", {}).get("outer_loadings", {})
        scores = res_round.get("construct_scores", {})
        paths = res_round.get("structural", {}).get("path_coefficients", {})

        # Predict omitted values
        for k_idx, ind_col in enumerate(all_indicators):
            cid = ind_to_c.get(ind_col)
            if not cid:
                continue

            omitted_rows = np.where(omit_mask[:, k_idx])[0]
            if len(omitted_rows) == 0:
                continue

            # Retained data mean and std in round d
            col_retained = raw_data[valid_mask[:, k_idx] & (~omit_mask[:, k_idx]), k_idx]
            mu_k = float(np.mean(col_retained)) if len(col_retained) > 0 else 0.0
            sigma_k = float(np.std(col_retained, ddof=0)) if len(col_retained) > 0 else 1.0
            sigma_k = max(1e-6, sigma_k)

            lam_k = float(loadings.get(cid, {}).get(ind_col, 0.0))
            y_scores = np.asarray(scores.get(cid, np.zeros(N)), dtype=float)

            # Predecessor constructs for redundancy prediction
            preds = preds_map.get(cid, [])

            for row_i in omitted_rows:
                actual_val = raw_data[row_i, k_idx]

                # 1. Communality prediction: x_hat = mu_k + sigma_k * lam_k * Y_i
                y_i = float(y_scores[row_i])
                x_hat_comm = mu_k + sigma_k * lam_k * y_i

                sse_comm[ind_col] += (actual_val - x_hat_comm) ** 2
                sso_comm[ind_col] += (actual_val - mu_k) ** 2

                # 2. Redundancy prediction: Y_hat_i = sum_p beta_p * Y_pi
                if preds and cid in endogenous_constructs:
                    y_hat_i = sum(
                        float(paths.get(cid, {}).get(p_cid, 0.0)) * float(np.asarray(scores.get(p_cid, np.zeros(N)))[row_i])
                        for p_cid in preds
                    )
                    x_hat_red = mu_k + sigma_k * lam_k * y_hat_i
                    sse_red[ind_col] += (actual_val - x_hat_red) ** 2
                    sso_red[ind_col] += (actual_val - mu_k) ** 2

    # Compute Q^2 per indicator and construct
    ind_results: List[Dict[str, Any]] = []
    construct_results: Dict[str, Dict[str, Any]] = {}

    for cid, inds in c_to_inds.items():
        is_endo = cid in endogenous_constructs
        c_sse_red = sum(sse_red[i] for i in inds)
        c_sso_red = sum(sso_red[i] for i in inds)
        c_sse_comm = sum(sse_comm[i] for i in inds)
        c_sso_comm = sum(sso_comm[i] for i in inds)

        q2_red = (1.0 - (c_sse_red / c_sso_red)) if c_sso_red > 1e-12 and is_endo else None
        q2_comm = (1.0 - (c_sse_comm / c_sso_comm)) if c_sso_comm > 1e-12 else None

        construct_results[cid] = {
            "construct_id": cid,
            "is_endogenous": is_endo,
            "sso_redundancy": round(float(c_sso_red), 4) if is_endo else None,
            "sse_redundancy": round(float(c_sse_red), 4) if is_endo else None,
            "q2_redundancy": round(float(q2_red), 4) if q2_red is not None else None,
            "predictive_relevance": bool(q2_red > 0) if q2_red is not None else None,
            "sso_communality": round(float(c_sso_comm), 4),
            "sse_communality": round(float(c_sse_comm), 4),
            "q2_communality": round(float(q2_comm), 4) if q2_comm is not None else None,
        }

        for iid in inds:
            i_sso_r = sso_red[iid]
            i_sse_r = sse_red[iid]
            i_sso_c = sso_comm[iid]
            i_sse_c = sse_comm[iid]

            iq2_red = (1.0 - (i_sse_r / i_sso_r)) if i_sso_r > 1e-12 and is_endo else None
            iq2_comm = (1.0 - (i_sse_c / i_sso_c)) if i_sso_c > 1e-12 else None

            ind_results.append({
                "indicator": iid,
                "construct_id": cid,
                "sso_redundancy": round(float(i_sso_r), 4) if is_endo else None,
                "sse_redundancy": round(float(i_sse_r), 4) if is_endo else None,
                "q2_redundancy": round(float(iq2_red), 4) if iq2_red is not None else None,
                "sso_communality": round(float(i_sso_c), 4),
                "sse_communality": round(float(i_sse_c), 4),
                "q2_communality": round(float(iq2_comm), 4) if iq2_comm is not None else None,
            })

    return {
        "constructs": construct_results,
        "indicators": ind_results,
    }


def run_blindfolding(
    df: pd.DataFrame,
    spec: Union[Dict[str, Any], Any],
    omission_distance: int = 7,
    settings: Optional[PipelineSettings] = None,
    compute_q2_effects: bool = True,
    progress_callback: Optional[Any] = None,
    cancel_event: Optional[Any] = None,
) -> Dict[str, Any]:
    """
    Main entry point for Blindfolding analysis (BLI-01 to BLI-10).
    Computes Q^2 redundancy & communality, and q^2 effect sizes.
    """
    spec_dict = spec.model_dump(mode="json", by_alias=True) if hasattr(spec, "model_dump") else (spec if isinstance(spec, dict) else {})
    cfg = settings or PipelineSettings()

    # Identify reflective constructs & indicators
    constructs = spec_dict.get("constructs", [])
    paths = spec_dict.get("paths", [])

    construct_indicator_map: Dict[str, List[str]] = {}
    for c in constructs:
        cid = c["id"]
        c_type = c.get("type", "reflective")
        if c_type == "reflective":
            if "indicators" in c and c["indicators"]:
                inds = [i for i in c["indicators"] if i in df.columns]
            else:
                inds = [
                    (ind.get("name") or ind.get("column") or ind.get("id"))
                    for ind in spec_dict.get("indicators", [])
                    if (ind.get("construct_id") or ind.get("construct")) == cid and (ind.get("name") or ind.get("column") or ind.get("id")) in df.columns
                ]
            if inds:
                construct_indicator_map[cid] = inds

    all_indicators = []
    for inds in construct_indicator_map.values():
        all_indicators.extend(inds)

    # Clean and treat missing data
    clean_df = df.copy()
    missing_codes = cfg.missing_codes if cfg.missing_codes is not None else [-99, "-99"]
    for col in all_indicators:
        if col in clean_df.columns:
            clean_df[col] = pd.to_numeric(clean_df[col], errors="coerce")
            for m in missing_codes:
                try:
                    clean_df[col] = clean_df[col].replace(float(m), np.nan)
                except (ValueError, TypeError):
                    clean_df[col] = clean_df[col].replace(m, np.nan)

    if cfg.missing_treatment == "mean":
        for col in all_indicators:
            if col in clean_df.columns:
                m_val = clean_df[col].mean()
                clean_df[col] = clean_df[col].fillna(m_val)
    else:
        clean_df = clean_df.dropna(subset=all_indicators).reset_index(drop=True)

    sub_df = clean_df[all_indicators]
    N = len(sub_df)
    D = validate_omission_distance(N, omission_distance)

    # Identify endogenous constructs
    targets = set(p.get("to") or p.get("to_node") for p in paths)
    endogenous_constructs = [c for c in construct_indicator_map.keys() if c in targets]

    # Baseline blindfold pass
    base_res = _run_single_blindfold_pass(
        df=sub_df,
        spec_dict=spec_dict,
        all_indicators=all_indicators,
        endogenous_constructs=endogenous_constructs,
        construct_indicator_map=construct_indicator_map,
        omission_distance=D,
        settings=cfg,
        progress_callback=progress_callback,
        cancel_event=cancel_event,
    )

    q2_effects: List[Dict[str, Any]] = []

    # Calculate q^2 effect sizes: q^2 = (Q^2_incl - Q^2_excl) / (1 - Q^2_incl)
    if compute_q2_effects:
        preds_per_target: Dict[str, List[str]] = {}
        for p in paths:
            fc = p.get("from") or p.get("from_node")
            tc = p.get("to") or p.get("to_node")
            if tc in endogenous_constructs:
                if tc not in preds_per_target:
                    preds_per_target[tc] = []
                preds_per_target[tc].append(fc)

        for target_cid, preds in preds_per_target.items():
            if len(preds) < 1:
                continue

            q2_incl = base_res["constructs"].get(target_cid, {}).get("q2_redundancy")
            if q2_incl is None or q2_incl >= 1.0:
                continue

            for pred_cid in preds:
                # Build reduced model with pred_cid -> target_cid path excluded
                red_paths = [
                    p for p in paths
                    if not ((p.get("from") or p.get("from_node")) == pred_cid and (p.get("to") or p.get("to_node")) == target_cid)
                ]
                red_spec = dict(spec_dict)
                red_spec["paths"] = red_paths

                red_res = _run_single_blindfold_pass(
                    df=sub_df,
                    spec_dict=red_spec,
                    all_indicators=all_indicators,
                    endogenous_constructs=endogenous_constructs,
                    construct_indicator_map=construct_indicator_map,
                    omission_distance=D,
                    settings=cfg,
                    cancel_event=cancel_event,
                )

                q2_excl = red_res["constructs"].get(target_cid, {}).get("q2_redundancy", 0.0) or 0.0
                q2_val = (q2_incl - q2_excl) / (1.0 - q2_incl)
                q2_val = max(0.0, float(q2_val))

                # Classify effect size
                if q2_val >= 0.35:
                    label = "large"
                elif q2_val >= 0.15:
                    label = "medium"
                elif q2_val >= 0.02:
                    label = "small"
                else:
                    label = "none"

                q2_effects.append({
                    "target": target_cid,
                    "predictor": pred_cid,
                    "q2_included": round(float(q2_incl), 4),
                    "q2_excluded": round(float(q2_excl), 4),
                    "q2_effect_size": round(q2_val, 4),
                    "magnitude": label,
                })

    return {
        "omission_distance": D,
        "n_samples": N,
        "constructs": list(base_res["constructs"].values()),
        "indicators": base_res["indicators"],
        "q2_effect_sizes": q2_effects,
        "thresholds": THRESHOLDS.get("effect_size", {}),
        "notes": [
            "Q^2 > 0 indicates predictive relevance of the endogenous construct (Stone 1974; Geisser 1974; Hair et al. 2017).",
            "q^2 values of 0.02, 0.15, and 0.35 signify small, medium, and large effect sizes (Hair et al. 2017).",
        ],
    }
