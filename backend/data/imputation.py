"""
Missing Value Imputation Module (MIS-03, MIS-05).
Implements imputation and missing data handlers:
- Mean replacement
- Expectation-Maximization (EM) imputation for multivariate normal data
- k-Nearest Neighbors (kNN) imputation based on normalized Euclidean distances
- Pairwise correlation matrix generation with nearest-PSD correction
"""

from typing import List, Dict, Any, Optional, Tuple
import numpy as np
import pandas as pd
from core.stats_utils import nearest_psd, pairwise_correlation_matrix


def mean_imputation(df: pd.DataFrame, columns: Optional[List[str]] = None) -> Tuple[pd.DataFrame, int]:
    """
    Replaces missing values in specified columns with the column mean.
    Returns (imputed_df, count_of_imputed_cells).
    """
    df_imputed = df.copy()
    cols = [c for c in (columns or list(df.columns)) if c in df.columns and pd.api.types.is_numeric_dtype(df[c])]
    imputed_count = 0

    for c in cols:
        s = df_imputed[c]
        n_miss = int(s.isna().sum())
        if n_miss > 0:
            mean_val = float(s.mean())
            df_imputed[c] = s.fillna(mean_val)
            imputed_count += n_miss

    return df_imputed, imputed_count


def em_imputation(
    df: pd.DataFrame,
    columns: Optional[List[str]] = None,
    max_iter: int = 100,
    tol: float = 1e-4,
) -> Tuple[pd.DataFrame, int, int]:
    """
    Multivariate Normal Expectation-Maximization (EM) Imputation (MIS-05).
    Iteratively computes conditional expectations of missing data given observed features.
    Returns: (imputed_df, imputed_cells_count, iterations_converged)
    """
    cols = [c for c in (columns or list(df.columns)) if c in df.columns and pd.api.types.is_numeric_dtype(df[c])]
    if not cols:
        return df.copy(), 0, 0

    X_orig = df[cols].values.astype(float)
    N, P = X_orig.shape
    nan_mask = np.isnan(X_orig)
    n_missing_cells = int(np.sum(nan_mask))

    if n_missing_cells == 0:
        return df.copy(), 0, 0

    # Bounds for clipping imputed values
    col_mins = np.nanmin(X_orig, axis=0)
    col_maxs = np.nanmax(X_orig, axis=0)

    # Initial imputation with column means
    col_means = np.nanmean(X_orig, axis=0)
    X = X_orig.copy()
    for j in range(P):
        X[nan_mask[:, j], j] = col_means[j]

    mu = np.mean(X, axis=0)
    Sigma = np.cov(X, rowvar=False)
    if P == 1:
        Sigma = np.array([[Sigma]])

    iters = 0
    for iters in range(1, max_iter + 1):
        mu_old = mu.copy()
        Sigma_old = Sigma.copy()

        # E-step: for each row, compute conditional expectation for missing features
        for i in range(N):
            missing_idx = np.where(nan_mask[i])[0]
            if len(missing_idx) == 0:
                continue
            observed_idx = np.where(~nan_mask[i])[0]

            if len(observed_idx) == 0:
                X[i, missing_idx] = mu[missing_idx]
                continue

            # Submatrices of Sigma
            mu_m = mu[missing_idx]
            mu_o = mu[observed_idx]
            x_o = X_orig[i, observed_idx]

            Sigma_mo = Sigma[np.ix_(missing_idx, observed_idx)]
            Sigma_oo = Sigma[np.ix_(observed_idx, observed_idx)]

            # Conditional expectation: E[X_m | X_o] = mu_m + Sigma_mo * Sigma_oo^-1 * (X_o - mu_o)
            try:
                cond_exp = mu_m + Sigma_mo @ np.linalg.pinv(Sigma_oo) @ (x_o - mu_o)
                # Clip to observed min and max
                cond_exp = np.clip(cond_exp, col_mins[missing_idx], col_maxs[missing_idx])
                X[i, missing_idx] = cond_exp
            except Exception:
                X[i, missing_idx] = mu[missing_idx]

        # M-step: update mu and Sigma
        mu = np.mean(X, axis=0)
        X_centered = X - mu
        Sigma = (X_centered.T @ X_centered) / N
        Sigma = nearest_psd(Sigma)

        # Check convergence
        diff_mu = np.max(np.abs(mu - mu_old))
        diff_sigma = np.max(np.abs(Sigma - Sigma_old))
        if max(diff_mu, diff_sigma) < tol:
            break

    df_imputed = df.copy()
    df_imputed[cols] = X
    return df_imputed, n_missing_cells, iters


def knn_imputation(
    df: pd.DataFrame,
    columns: Optional[List[str]] = None,
    k: int = 5,
) -> Tuple[pd.DataFrame, int]:
    """
    k-Nearest Neighbors (kNN) Imputation (MIS-05).
    Computes normalized Euclidean distance on standardized observed features.
    Imputes missing values with the mean of the k nearest donors.
    """
    cols = [c for c in (columns or list(df.columns)) if c in df.columns and pd.api.types.is_numeric_dtype(df[c])]
    if not cols:
        return df.copy(), 0

    X_orig = df[cols].values.astype(float)
    N, P = X_orig.shape
    nan_mask = np.isnan(X_orig)
    n_missing_cells = int(np.sum(nan_mask))

    if n_missing_cells == 0:
        return df.copy(), 0

    # Standardize data based on observed values
    col_means = np.nanmean(X_orig, axis=0)
    col_stds = np.nanstd(X_orig, axis=0)
    col_stds[col_stds == 0] = 1.0
    col_mins = np.nanmin(X_orig, axis=0)
    col_maxs = np.nanmax(X_orig, axis=0)

    X_norm = (X_orig - col_means) / col_stds
    X_imputed = X_orig.copy()

    for i in range(N):
        missing_idx = np.where(nan_mask[i])[0]
        if len(missing_idx) == 0:
            continue
        observed_idx = np.where(~nan_mask[i])[0]

        if len(observed_idx) == 0:
            X_imputed[i, missing_idx] = col_means[missing_idx]
            continue

        # Candidate donors must have the missing features observed
        for m in missing_idx:
            donor_candidates = np.where(~nan_mask[:, m])[0]
            donor_candidates = donor_candidates[donor_candidates != i]
            if len(donor_candidates) == 0:
                X_imputed[i, m] = col_means[m]
                continue

            # Compute distance to each candidate over mutually observed features
            distances = []
            for d in donor_candidates:
                mutual = np.intersect1d(observed_idx, np.where(~nan_mask[d])[0])
                if len(mutual) == 0:
                    dist = 1e6
                else:
                    diff = X_norm[i, mutual] - X_norm[d, mutual]
                    # Normalized Euclidean distance
                    dist = np.sqrt((P / len(mutual)) * np.sum(diff ** 2))
                distances.append(dist)

            distances = np.array(distances)
            k_eff = min(k, len(donor_candidates))
            nearest_donor_indices = donor_candidates[np.argsort(distances)[:k_eff]]

            # Impute with mean of the k nearest donors
            imputed_val = np.mean(X_orig[nearest_donor_indices, m])
            imputed_val = np.clip(imputed_val, col_mins[m], col_maxs[m])
            X_imputed[i, m] = imputed_val

    df_imputed = df.copy()
    df_imputed[cols] = X_imputed
    return df_imputed, n_missing_cells
