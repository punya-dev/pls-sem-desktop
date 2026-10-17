"""
PLSpredict Module (Section 25: X-C, X-03).
Source of truth: Shmueli et al. (2016, 2019) & Hair et al. (2017).
Implements:
- k-fold cross-validation with multiple repetitions
- Holdout prediction using training weights and path coefficients
- Linear model (LM) benchmark comparisons
- Q^2_predict, RMSE, MAE metrics per indicator and construct
- Predictive power classification: High, Medium, Low, None
"""

from typing import List, Dict, Any, Optional, Tuple, Union
import numpy as np
import pandas as pd
from core.settings_schema import PipelineSettings
from core.rng import spawn_seeds
from engine.pls.algorithm import run_pipeline, parse_model_spec


def _fit_ols(X: np.ndarray, y: np.ndarray) -> np.ndarray:
    """Fits OLS linear regression with intercept using pure numpy."""
    X_ones = np.column_stack([np.ones(len(X)), X])
    coefs, _, _, _ = np.linalg.lstsq(X_ones, y, rcond=None)
    return coefs


def _predict_ols(coefs: np.ndarray, X: np.ndarray) -> np.ndarray:
    """Predicts from OLS linear regression with intercept using pure numpy."""
    X_ones = np.column_stack([np.ones(len(X)), X])
    return X_ones @ coefs



def run_pls_predict(
    df: pd.DataFrame,
    model_spec: Any,
    k_folds: int = 10,
    repetitions: int = 10,
    seed: Optional[int] = 42,
    antecedents: str = "direct",
    settings: Optional[Union[PipelineSettings, Dict[str, Any]]] = None,
    progress_callback: Optional[Any] = None,
    cancel_event: Optional[Any] = None,
) -> Dict[str, Any]:
    """
    Executes PLSpredict with k-fold cross-validation and LM benchmark comparison.
    """
    spec_dict = model_spec.model_dump(by_alias=True) if hasattr(model_spec, "model_dump") else (
        model_spec if isinstance(model_spec, dict) else {}
    )

    if settings is None:
        cfg = PipelineSettings()
    elif isinstance(settings, dict):
        cfg = PipelineSettings(**settings)
    else:
        cfg = settings

    constructs, ind_col_map, paths = parse_model_spec(spec_dict)
    construct_ids = list(constructs.keys())

    # Identify endogenous constructs and their direct/exogenous predictors
    preds_per_target: Dict[str, List[str]] = {}
    for from_c, to_c in paths:
        if to_c not in preds_per_target:
            preds_per_target[to_c] = []
        preds_per_target[to_c].append(from_c)

    endogenous_constructs = list(preds_per_target.keys())
    if not endogenous_constructs:
        raise ValueError("PLSpredict requires at least one endogenous construct with incoming paths.")

    # All exogenous constructs in the model
    exogenous_constructs = [c for c in construct_ids if c not in endogenous_constructs]

    # Map each endogenous construct to its indicators
    endog_indicators: Dict[str, List[str]] = {}
    for ec in endogenous_constructs:
        endog_indicators[ec] = [ind_col_map.get(iid, iid) for iid in constructs[ec]["indicators"] if ind_col_map.get(iid, iid) in df.columns]

    # Map exogenous predictors to their indicators for the LM benchmark
    exog_indicators_all: List[str] = []
    for xc in exogenous_constructs:
        for iid in constructs[xc]["indicators"]:
            col = ind_col_map.get(iid, iid)
            if col in df.columns and col not in exog_indicators_all:
                exog_indicators_all.append(col)

    # Clean data across needed indicators
    all_needed_cols = list(dict.fromkeys(
        [col for c_info in constructs.values() for iid in c_info["indicators"] for col in [ind_col_map.get(iid, iid)] if col in df.columns]
    ))
    clean_df = df[all_needed_cols].dropna().reset_index(drop=True)
    N = len(clean_df)

    if N < 30:
        raise ValueError(f"PLSpredict requires at least 30 complete cases (found {N}).")

    effective_k = min(k_folds, N // 5)
    effective_k = max(2, effective_k)

    # Check N/k ratio recommendation (Hair et al. recommend N/k >= 30 when possible)
    n_k_ratio_warning = None
    if N / effective_k < 30:
        n_k_ratio_warning = f"Sample size per fold ({N // effective_k}) is below recommended threshold of 30."

    rng = np.random.default_rng(seed)
    rep_seeds = rng.integers(0, 1000000, size=repetitions)

    # Accumulate predictions across all repetitions
    # Per indicator: lists of true, predicted_pls, predicted_lm, predicted_naive
    accum_true: Dict[str, List[float]] = {col: [] for ec in endogenous_constructs for col in endog_indicators[ec]}
    accum_pls: Dict[str, List[float]] = {col: [] for ec in endogenous_constructs for col in endog_indicators[ec]}
    accum_lm: Dict[str, List[float]] = {col: [] for ec in endogenous_constructs for col in endog_indicators[ec]}
    accum_naive: Dict[str, List[float]] = {col: [] for ec in endogenous_constructs for col in endog_indicators[ec]}

    total_steps = repetitions * effective_k
    step_count = 0

    for rep in range(repetitions):
        rep_rng = np.random.default_rng(int(rep_seeds[rep]))
        shuffled_indices = rep_rng.permutation(N)
        folds = np.array_split(shuffled_indices, effective_k)

        for f_idx in range(effective_k):
            if cancel_event and cancel_event.is_set():
                return {"status": "cancelled", "message": "PLSpredict cancelled by user."}

            holdout_idx = folds[f_idx]
            train_idx = np.setdiff1d(shuffled_indices, holdout_idx)

            train_df = clean_df.iloc[train_idx]
            holdout_df = clean_df.iloc[holdout_idx]

            # 1. Fit PLS on training split
            train_results = run_pipeline(train_df, model_spec, cfg)

            meas = train_results.get("measurement", {})
            struct = train_results.get("structural", {})
            train_weights = meas.get("outer_weights", {})
            train_loadings = meas.get("outer_loadings", {})
            train_paths = struct.get("path_coefficients", {})

            # Calculate training means and SDs per indicator
            train_means = train_df.mean()
            train_sds = train_df.std(ddof=0).replace(0.0, 1.0)

            # Compute standardized holdout scores
            holdout_scores: Dict[str, np.ndarray] = {}
            for cid, cinfo in constructs.items():
                c_cols = [ind_col_map.get(iid, iid) for iid in cinfo["indicators"] if ind_col_map.get(iid, iid) in train_df.columns]
                # Standardize holdout indicators using training parameters
                X_hold = holdout_df[c_cols].values
                mu_tr = train_means[c_cols].values
                sd_tr = train_sds[c_cols].values
                X_hold_std = (X_hold - mu_tr) / sd_tr

                w_vec = np.array([train_weights.get(cid, {}).get(iid, 1.0 / np.sqrt(len(c_cols))) for iid in cinfo["indicators"]])
                raw_score = X_hold_std @ w_vec
                score_sd = np.std(raw_score, ddof=0) or 1.0
                holdout_scores[cid] = raw_score / score_sd

            # Predict endogenous construct scores via training path coefficients
            predicted_construct_scores: Dict[str, np.ndarray] = {}
            for ec in endogenous_constructs:
                preds = preds_per_target[ec]
                pred_val = np.zeros(len(holdout_df))
                for pc in preds:
                    beta = train_paths.get(pc, {}).get(ec, 0.0)
                    pred_val += beta * holdout_scores[pc]
                predicted_construct_scores[ec] = pred_val

            # Fit LM Benchmark on training split
            # Regress each endogenous indicator on all exogenous indicators
            lm_coefs: Dict[str, np.ndarray] = {}
            exog_cols = [c for c in exog_indicators_all if c in train_df.columns]
            if not exog_cols:
                # Fallback: regress on all predecessor construct indicators
                exog_cols = [c for c in train_df.columns if c not in [ind for inds in endog_indicators.values() for ind in inds]]

            if exog_cols:
                X_train_lm = train_df[exog_cols].values
                X_hold_lm = holdout_df[exog_cols].values
                for ec in endogenous_constructs:
                    for iid in constructs[ec]["indicators"]:
                        col = ind_col_map.get(iid, iid)
                        if col in train_df.columns:
                            y_tr = train_df[col].values
                            lm_coefs[col] = _fit_ols(X_train_lm, y_tr)

            # 2. Predict indicators for holdout
            for ec in endogenous_constructs:
                for iid in constructs[ec]["indicators"]:
                    col = ind_col_map.get(iid, iid)
                    if col not in holdout_df.columns:
                        continue

                    y_true = holdout_df[col].values
                    mu = float(train_means[col])
                    sd = float(train_sds[col])
                    lam = float(train_loadings.get(ec, {}).get(iid, 0.70))

                    # PLS prediction: x_hat = mu + sd * lambda * Y_hat
                    y_pred_pls = mu + sd * lam * predicted_construct_scores[ec]

                    # LM prediction
                    if col in lm_coefs and exog_cols:
                        y_pred_lm = _predict_ols(lm_coefs[col], X_hold_lm)
                    else:
                        y_pred_lm = np.full_like(y_true, mu)

                    # Naive benchmark: training sample mean
                    y_pred_naive = np.full_like(y_true, mu)

                    accum_true[col].extend(y_true.tolist())
                    accum_pls[col].extend(y_pred_pls.tolist())
                    accum_lm[col].extend(y_pred_lm.tolist())
                    accum_naive[col].extend(y_pred_naive.tolist())

            step_count += 1
            if progress_callback:
                progress_callback(step_count, total_steps)

    # 3. Calculate summary metrics per indicator
    indicator_results = []
    construct_summary = {}

    for ec in endogenous_constructs:
        construct_indicators = []
        n_better_lm = 0
        total_ind_in_ec = 0

        for iid in constructs[ec]["indicators"]:
            col = ind_col_map.get(iid, iid)
            if col not in accum_true or len(accum_true[col]) == 0:
                continue

            y_t = np.array(accum_true[col])
            y_p = np.array(accum_pls[col])
            y_l = np.array(accum_lm[col])
            y_n = np.array(accum_naive[col])

            # SSE
            sse_pls = float(np.sum((y_t - y_p) ** 2))
            sse_lm = float(np.sum((y_t - y_l) ** 2))
            sse_naive = float(np.sum((y_t - y_n) ** 2))

            # RMSE
            rmse_pls = float(np.sqrt(np.mean((y_t - y_p) ** 2)))
            rmse_lm = float(np.sqrt(np.mean((y_t - y_l) ** 2)))
            rmse_diff = rmse_pls - rmse_lm

            # MAE
            mae_pls = float(np.mean(np.abs(y_t - y_p)))
            mae_lm = float(np.mean(np.abs(y_t - y_l)))
            mae_diff = mae_pls - mae_lm

            # Q^2_predict = 1 - SSE_pls / SSE_naive
            q2_predict = 1.0 - (sse_pls / sse_naive) if sse_naive > 1e-12 else 0.0

            pls_beats_lm = (rmse_pls < rmse_lm)
            if pls_beats_lm:
                n_better_lm += 1
            total_ind_in_ec += 1

            ind_res = {
                "indicator": col,
                "construct": ec,
                "q2_predict": round(q2_predict, 4),
                "q2_predict_positive": q2_predict > 0,
                "rmse_pls": round(rmse_pls, 4),
                "rmse_lm": round(rmse_lm, 4),
                "rmse_diff": round(rmse_diff, 4),
                "mae_pls": round(mae_pls, 4),
                "mae_lm": round(mae_lm, 4),
                "mae_diff": round(mae_diff, 4),
                "pls_beats_lm": bool(pls_beats_lm),
            }
            indicator_results.append(ind_res)
            construct_indicators.append(ind_res)

        # Classify predictive power per construct (Shmueli et al. 2019)
        if total_ind_in_ec > 0:
            if n_better_lm == total_ind_in_ec:
                verdict = "high"
                desc = "High predictive power: PLS-SEM outperforms LM for all indicators."
            elif n_better_lm >= total_ind_in_ec / 2.0:
                verdict = "medium"
                desc = "Medium predictive power: PLS-SEM outperforms LM for the majority of indicators."
            elif n_better_lm > 0:
                verdict = "low"
                desc = "Low predictive power: PLS-SEM outperforms LM for a minority of indicators."
            else:
                verdict = "none"
                desc = "No predictive power: LM outperforms PLS-SEM for all indicators."

            construct_summary[ec] = {
                "construct": ec,
                "n_indicators": total_ind_in_ec,
                "n_pls_beats_lm": n_better_lm,
                "predictive_power": verdict,
                "description": desc,
                "mean_q2_predict": round(float(np.mean([x["q2_predict"] for x in construct_indicators])), 4),
            }

    # Overall model predictive power
    total_all_ind = len(indicator_results)
    total_better = sum(1 for x in indicator_results if x["pls_beats_lm"])
    if total_all_ind > 0:
        if total_better == total_all_ind:
            overall_verdict = "high"
        elif total_better >= total_all_ind / 2.0:
            overall_verdict = "medium"
        elif total_better > 0:
            overall_verdict = "low"
        else:
            overall_verdict = "none"
    else:
        overall_verdict = "none"

    return {
        "k_folds": effective_k,
        "repetitions": repetitions,
        "n_samples": N,
        "antecedents": antecedents,
        "warning": n_k_ratio_warning,
        "indicator_metrics": indicator_results,
        "construct_summary": construct_summary,
        "overall_predictive_power": overall_verdict,
        "interpretation": {
            "high": "PLS-SEM has higher predictive power than LM on all indicator benchmarks.",
            "medium": "PLS-SEM outperforms LM on majority of indicator benchmarks.",
            "low": "PLS-SEM outperforms LM on minority of indicator benchmarks.",
            "none": "No predictive power: LM benchmark matches or exceeds PLS-SEM across indicators.",
        },
    }
