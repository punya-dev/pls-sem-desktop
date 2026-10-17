"""
Data Screening Module (Stage 3: SCR-01 to SCR-10).
Provides data screening, diagnostic evaluations, and quality checks:
- SCR-01..04: Missing-data reports (indicators, cases, constructs), thresholds (>15% case, >5% indicator)
- SCR-05: Suspicious response patterns (straight-lining, diagonal-lining, attention checks)
- SCR-06: Outlier detection using Tukey fences (extreme beyond 3*IQR, mild 1.5*IQR)
- SCR-07: Skewness/Kurtosis evaluation (textbook +/-1 vs Kline) & normality tests (Shapiro-Wilk, KS, Mardia)
- SCR-08: Histogram and discrete distribution endpoint with normal overlay
- SCR-09: Reverse-coding transformation (x' = min + max - x)
- SCR-10: Directionality check for reflective construct indicators
"""

from typing import List, Dict, Any, Optional, Tuple, Union
import numpy as np
import pandas as pd
from scipy import stats
from core.issues import Issue, IssueTarget
from core.stats_utils import fisher_pearson_skewness, fisher_pearson_kurtosis
from core.thresholds import THRESHOLDS
from model_spec import ModelSpec


def analyze_missing_data(
    df: pd.DataFrame,
    columns: Optional[List[str]] = None,
    model_spec: Optional[ModelSpec] = None,
    case_threshold_pct: float = 15.0,
    indicator_threshold_pct: float = 5.0,
) -> Dict[str, Any]:
    """
    Comprehensive missing data analysis (SCR-01 to SCR-04).
    Flags indicators with > indicator_threshold_pct (default 5%) missing.
    Flags cases with > case_threshold_pct (default 15%) missing.
    """
    cols = [c for c in (columns or list(df.columns)) if c in df.columns]
    sub_df = df[cols]
    n_cases, n_cols = sub_df.shape

    # Per-indicator statistics
    indicator_stats = []
    flagged_indicators = []
    issues: List[Dict[str, Any]] = []

    for c in cols:
        s = sub_df[c]
        n_miss = int(s.isna().sum())
        pct_miss = round(n_miss / n_cases * 100, 2) if n_cases > 0 else 0.0
        flagged = pct_miss > indicator_threshold_pct
        indicator_stats.append({
            "column": c,
            "n_missing": n_miss,
            "pct_missing": pct_miss,
            "flagged": flagged,
        })
        if flagged:
            flagged_indicators.append(c)
            issues.append(
                Issue(
                    code="INDICATOR_HIGH_MISSING",
                    severity="warning",
                    target=IssueTarget(type="indicator", id=c),
                    message=f"Indicator '{c}' has {pct_miss}% missing values (exceeds {indicator_threshold_pct}% threshold).",
                    advice="Indicators with more than 5% missing values should typically be removed or imputed unless sample size is very large.",
                ).model_dump()
            )

    # Per-case statistics
    case_missing = sub_df.isna().sum(axis=1)
    case_stats = []
    flagged_cases = []

    for idx, count in case_missing.items():
        n_miss = int(count)
        pct_miss = round(n_miss / n_cols * 100, 2) if n_cols > 0 else 0.0
        flagged = pct_miss > case_threshold_pct
        if n_miss > 0:
            case_stats.append({
                "row_index": int(idx),
                "case_id": int(idx) + 1,
                "n_missing": n_miss,
                "pct_missing": pct_miss,
                "flagged": flagged,
            })
        if flagged:
            flagged_cases.append(int(idx))

    if flagged_cases:
        issues.append(
            Issue(
                code="CASES_HIGH_MISSING",
                severity="warning",
                target=IssueTarget(type="dataset", id="cases"),
                message=f"{len(flagged_cases)} case(s) have more than {case_threshold_pct}% missing data across indicators.",
                advice="Hair et al. (2017) recommend removing cases with more than 15% missing values via casewise deletion.",
            ).model_dump()
        )

    # Per-construct statistics if model_spec is provided
    construct_stats = []
    if model_spec:
        for c in model_spec.constructs:
            c_indicators = [ind.name for ind in model_spec.indicators if ind.construct_id == c.id and ind.name in df.columns]
            if not c_indicators:
                continue
            c_sub = df[c_indicators]
            any_miss = int(c_sub.isna().any(axis=1).sum())
            all_miss = int(c_sub.isna().all(axis=1).sum())
            pct_any = round(any_miss / n_cases * 100, 2) if n_cases > 0 else 0.0
            pct_all = round(all_miss / n_cases * 100, 2) if n_cases > 0 else 0.0
            construct_stats.append({
                "construct_id": c.id,
                "construct_name": c.name,
                "indicators": c_indicators,
                "n_cases_any_missing": any_miss,
                "pct_cases_any_missing": pct_any,
                "n_cases_all_missing": all_miss,
                "pct_cases_all_missing": pct_all,
            })

    total_cells = n_cases * n_cols
    total_missing_cells = int(sub_df.isna().sum().sum())
    cases_with_any = int((sub_df.isna().sum(axis=1) > 0).sum())

    return {
        "n_cases": n_cases,
        "n_columns": n_cols,
        "total_missing_cells": total_missing_cells,
        "pct_cells_missing": round(total_missing_cells / total_cells * 100, 2) if total_cells > 0 else 0.0,
        "n_cases_with_any_missing": cases_with_any,
        "pct_cases_with_any_missing": round(cases_with_any / n_cases * 100, 2) if n_cases > 0 else 0.0,
        "indicator_stats": indicator_stats,
        "case_stats": case_stats,
        "flagged_cases": flagged_cases,
        "flagged_indicators": flagged_indicators,
        "construct_stats": construct_stats,
        "issues": issues,
    }


def detect_suspicious_patterns(
    df: pd.DataFrame,
    model_spec: Optional[ModelSpec] = None,
    attention_checks: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Detects unengaged respondents (SCR-05):
    - Straight-lining: Standard deviation across a construct block is 0 (block size >= 3).
    - Diagonal-lining: Monotone staircase (+1 or -1 steps) across consecutive indicators.
    - Attention checks: Value mismatch for known test questions.
    """
    flagged: List[Dict[str, Any]] = []

    # Identify blocks to evaluate
    blocks: List[Tuple[str, List[str]]] = []
    if model_spec:
        for c in model_spec.constructs:
            inds = [ind.name for ind in model_spec.indicators if ind.construct_id == c.id and ind.name in df.columns]
            if len(inds) >= 3:
                blocks.append((c.name, inds))
    else:
        # Default numeric columns chunked in blocks of 4
        num_cols = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
        if len(num_cols) >= 3:
            blocks.append(("All_Indicators", num_cols))

    straight_line_count = 0
    diagonal_line_count = 0
    attention_fail_count = 0

    for block_name, cols in blocks:
        sub = df[cols].dropna()
        for idx, row in sub.iterrows():
            vals = row.values.astype(float)
            # 1. Straight-lining check
            if np.std(vals, ddof=0) < 1e-9:
                flagged.append({
                    "row_index": int(idx),
                    "case_id": int(idx) + 1,
                    "pattern": "straight_lining",
                    "block": block_name,
                    "details": f"Zero variance (all values = {vals[0]}) across {len(vals)} items.",
                })
                straight_line_count += 1

            # 2. Diagonal-lining check
            if len(vals) >= 4:
                diffs = np.diff(vals)
                if np.all(diffs == 1.0) or np.all(diffs == -1.0):
                    flagged.append({
                        "row_index": int(idx),
                        "case_id": int(idx) + 1,
                        "pattern": "diagonal_lining",
                        "block": block_name,
                        "details": f"Monotone stepping pattern ({'increasing' if diffs[0] == 1 else 'decreasing'}) across {len(vals)} items.",
                    })
                    diagonal_line_count += 1

    # 3. Attention checks
    if attention_checks:
        for col, expected in attention_checks.items():
            if col in df.columns:
                s = df[col]
                fails = s[s != expected].dropna()
                for idx, val in fails.items():
                    flagged.append({
                        "row_index": int(idx),
                        "case_id": int(idx) + 1,
                        "pattern": "attention_check_failed",
                        "block": col,
                        "details": f"Expected value '{expected}', got '{val}'.",
                    })
                    attention_fail_count += 1

    return {
        "flagged_cases": flagged,
        "total_flagged_instances": len(flagged),
        "straight_line_count": straight_line_count,
        "diagonal_line_count": diagonal_line_count,
        "attention_fail_count": attention_fail_count,
    }


def detect_outliers(
    df: pd.DataFrame,
    columns: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Detects mild (1.5*IQR) and extreme (3.0*IQR) univariate outliers (SCR-06).
    """
    cols = [c for c in (columns or list(df.columns)) if c in df.columns and pd.api.types.is_numeric_dtype(df[c])]
    outlier_results = {}

    for c in cols:
        valid = df[c].dropna().values.astype(float)
        if len(valid) < 4:
            continue

        q1 = float(np.percentile(valid, 25))
        q3 = float(np.percentile(valid, 75))
        iqr = q3 - q1
        median = float(np.median(valid))
        min_val = float(np.min(valid))
        max_val = float(np.max(valid))

        mild_lower = q1 - 1.5 * iqr
        mild_upper = q3 + 1.5 * iqr
        extreme_lower = q1 - 3.0 * iqr
        extreme_upper = q3 + 3.0 * iqr

        mild_outliers = []
        extreme_outliers = []

        s = df[c]
        for idx, val in s.dropna().items():
            v = float(val)
            if v < extreme_lower or v > extreme_upper:
                extreme_outliers.append({"row_index": int(idx), "case_id": int(idx) + 1, "value": v})
            elif v < mild_lower or v > mild_upper:
                mild_outliers.append({"row_index": int(idx), "case_id": int(idx) + 1, "value": v})

        # Whisker calculations
        non_outliers = valid[(valid >= mild_lower) & (valid <= mild_upper)]
        whisker_lower = float(np.min(non_outliers)) if len(non_outliers) > 0 else min_val
        whisker_upper = float(np.max(non_outliers)) if len(non_outliers) > 0 else max_val

        outlier_results[c] = {
            "min": min_val,
            "q1": q1,
            "median": median,
            "q3": q3,
            "max": max_val,
            "iqr": iqr,
            "whisker_lower": whisker_lower,
            "whisker_upper": whisker_upper,
            "mild_fence": [mild_lower, mild_upper],
            "extreme_fence": [extreme_lower, extreme_upper],
            "n_mild_outliers": len(mild_outliers),
            "n_extreme_outliers": len(extreme_outliers),
            "mild_outliers": mild_outliers[:50],
            "extreme_outliers": extreme_outliers[:50],
        }

    return outlier_results


def assess_distributions(
    df: pd.DataFrame,
    columns: Optional[List[str]] = None,
    rule_set: str = "textbook",
) -> Dict[str, Any]:
    """
    Calculates skewness, excess kurtosis, and tests for normality (SCR-07).
    rule_set:
      - 'textbook': flag |skew| > 1.0 or |excess_kurtosis| > 1.0 (Hair et al.)
      - 'kline': flag |skew| > 2.0 or |excess_kurtosis| > 7.0
    """
    cols = [c for c in (columns or list(df.columns)) if c in df.columns and pd.api.types.is_numeric_dtype(df[c])]
    skew_thresh = 1.0 if rule_set == "textbook" else 2.0
    kurt_thresh = 1.0 if rule_set == "textbook" else 7.0

    column_stats = []
    matrix_data = []

    for c in cols:
        vals = df[c].dropna().values.astype(float)
        n = len(vals)
        if n < 4:
            continue

        skew = float(fisher_pearson_skewness(vals))
        kurt = float(fisher_pearson_kurtosis(vals))

        flag_skew = abs(skew) > skew_thresh
        flag_kurt = abs(kurt) > kurt_thresh

        # Shapiro-Wilk (only valid for N <= 5000)
        shapiro_stat, shapiro_p = (None, None)
        if 3 <= n <= 5000:
            try:
                res = stats.shapiro(vals)
                shapiro_stat = float(res.statistic)
                shapiro_p = float(res.pvalue)
            except Exception:
                pass

        # Kolmogorov-Smirnov test against fitted normal
        ks_stat, ks_p = (None, None)
        try:
            mean_v, std_v = float(np.mean(vals)), float(np.std(vals, ddof=1))
            if std_v > 1e-9:
                res_ks = stats.kstest(vals, "norm", args=(mean_v, std_v))
                ks_stat = float(res_ks.statistic)
                ks_p = float(res_ks.pvalue)
        except Exception:
            pass

        column_stats.append({
            "column": c,
            "n_valid": n,
            "mean": float(np.mean(vals)),
            "std": float(np.std(vals, ddof=1)),
            "skewness": round(skew, 4),
            "excess_kurtosis": round(kurt, 4),
            "skew_flagged": flag_skew,
            "kurtosis_flagged": flag_kurt,
            "shapiro_wilk": {"statistic": shapiro_stat, "p_value": shapiro_p} if shapiro_stat is not None else None,
            "kolmogorov_smirnov": {"statistic": ks_stat, "p_value": ks_p} if ks_stat is not None else None,
        })

    # Mardia's multivariate skewness and kurtosis
    complete_sub = df[cols].dropna()
    mardia_results = None
    if complete_sub.shape[0] > complete_sub.shape[1] > 1:
        try:
            X = complete_sub.values.astype(float)
            N, p = X.shape
            X_center = X - np.mean(X, axis=0)
            S = np.cov(X_center, rowvar=False)
            S_inv = np.linalg.pinv(S)
            D = X_center @ S_inv @ X_center.T  # Mahalanobis distance matrix N x N

            mardia_skew = float(np.sum(D ** 3) / (N ** 2))
            mardia_kurt = float(np.trace(D ** 2) / N)

            # Chi-square test for multivariate skewness
            df_skew = p * (p + 1) * (p + 2) / 6
            chi_skew = N * mardia_skew / 6
            p_skew = float(1 - stats.chi2.cdf(chi_skew, df_skew))

            # Normal test for multivariate kurtosis
            expected_kurt = p * (p + 2)
            se_kurt = np.sqrt(8 * p * (p + 2) / N)
            z_kurt = (mardia_kurt - expected_kurt) / se_kurt
            p_kurt = float(2 * (1 - stats.norm.cdf(abs(z_kurt))))

            mardia_results = {
                "multivariate_skewness": round(mardia_skew, 4),
                "skewness_chi2": round(chi_skew, 4),
                "skewness_p": p_skew,
                "multivariate_kurtosis": round(mardia_kurt, 4),
                "kurtosis_z": round(z_kurt, 4),
                "kurtosis_p": p_kurt,
                "is_multivariate_normal": (p_skew > 0.05 and p_kurt > 0.05),
            }
        except Exception:
            pass

    return {
        "rule_set": rule_set,
        "skewness_threshold": skew_thresh,
        "kurtosis_threshold": kurt_thresh,
        "columns": column_stats,
        "mardia": mardia_results,
        "advice": "PLS-SEM is non-parametric and robust to non-normal data; extreme non-normality can attenuate bootstrap standard errors, so BCa bootstrap intervals are recommended.",
    }


def calculate_histogram(
    df: pd.DataFrame,
    column: str,
    bins: Union[int, str] = "auto",
) -> Dict[str, Any]:
    """
    Computes histogram binning, counts, and normal distribution curve overlay (SCR-08).
    """
    if column not in df.columns:
        raise ValueError(f"Column '{column}' not found in dataset.")

    s = df[column].dropna().values.astype(float)
    if len(s) == 0:
        return {"column": column, "n": 0, "counts": [], "edges": []}

    mean_v = float(np.mean(s))
    std_v = float(np.std(s, ddof=1)) if len(s) > 1 else 0.0

    counts, bin_edges = np.histogram(s, bins=bins)
    counts_list = [int(c) for c in counts]
    edges_list = [float(e) for e in bin_edges]

    # Generate smooth normal curve points across range
    normal_curve = []
    if std_v > 1e-9:
        x_grid = np.linspace(edges_list[0], edges_list[-1], 60)
        bin_width = edges_list[1] - edges_list[0] if len(edges_list) > 1 else 1.0
        y_pdf = stats.norm.pdf(x_grid, mean_v, std_v) * len(s) * bin_width
        normal_curve = [{"x": float(x), "y": float(y)} for x, y in zip(x_grid, y_pdf)]

    # Discrete distribution for small cardinality variables
    discrete_values = None
    unique_vals = np.unique(s)
    if len(unique_vals) <= 15:
        discrete_values = {float(v): int((s == v).sum()) for v in unique_vals}

    return {
        "column": column,
        "n_valid": len(s),
        "mean": mean_v,
        "std": std_v,
        "edges": edges_list,
        "counts": counts_list,
        "normal_curve": normal_curve,
        "discrete_values": discrete_values,
    }


def reverse_code_column(
    series: pd.Series,
    scale_min: Optional[float] = None,
    scale_max: Optional[float] = None,
) -> Tuple[pd.Series, float, float]:
    """
    Applies reverse coding: x' = min + max - x (SCR-09).
    Preserves NaN values.
    """
    valid = series.dropna().values.astype(float)
    s_min = float(scale_min if scale_min is not None else np.min(valid))
    s_max = float(scale_max if scale_max is not None else np.max(valid))

    reversed_series = s_min + s_max - series
    return reversed_series, s_min, s_max


def assess_directionality(
    df: pd.DataFrame,
    model_spec: ModelSpec,
) -> Dict[str, Any]:
    """
    Directionality analysis (SCR-10):
    For each reflective construct, verifies that indicators are positively correlated.
    Flags items whose average correlation with peer items is negative.
    """
    construct_checks = []

    for c in model_spec.constructs:
        if c.type != "reflective":
            continue
        inds = [ind.name for ind in model_spec.indicators if ind.construct_id == c.id and ind.name in df.columns]
        if len(inds) < 2:
            continue

        corr_matrix = df[inds].corr().values
        item_reports = []

        for i, item_name in enumerate(inds):
            peer_corrs = [corr_matrix[i, j] for j in range(len(inds)) if i != j and not np.isnan(corr_matrix[i, j])]
            avg_corr = float(np.mean(peer_corrs)) if peer_corrs else 0.0
            negative_share = float(np.mean([r < 0 for r in peer_corrs])) if peer_corrs else 0.0
            flagged = avg_corr < 0 or negative_share >= 0.50

            item_reports.append({
                "indicator": item_name,
                "average_peer_correlation": round(avg_corr, 4),
                "negative_correlation_share": round(negative_share, 4),
                "potential_reverse_coded": flagged,
            })

        construct_checks.append({
            "construct_id": c.id,
            "construct_name": c.name,
            "indicators": inds,
            "items": item_reports,
            "has_potential_reverse_coded_items": any(r["potential_reverse_coded"] for r in item_reports),
        })

    return {"constructs": construct_checks}
