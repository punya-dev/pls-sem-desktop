"""
CB-SEM Algorithm Implementation (Phase 6)
Covariance-Based Structural Equation Modeling:
- Reticular Action Model (RAM) formulation: A (asymmetric paths), S (symmetric covariances), F (filter)
- Maximum Likelihood (ML) discrepancy function F_ML
- Optimization with parameter bounds via scipy.optimize (L-BFGS-B / SLSQP)
- Identification checks & degrees of freedom (df)
- Asymptotic standard errors, z-scores, p-values via numerical Fisher information matrix
- Complete fit indices:
  - Chi-Square, df, p-value
  - Baseline (Independence) Chi-Square and df
  - CFI (Comparative Fit Index)
  - TLI (Tucker-Lewis Index / NNFI)
  - RMSEA (with 90% confidence interval)
  - SRMR (Standardized Root Mean Square Residual)
  - AIC, BIC
- Standardized parameter estimates
- Heywood case detection (negative error variances or standardized loadings > 1)
"""

import math
from typing import Dict, List, Optional, Tuple, Any, Union
import numpy as np
import pandas as pd
from scipy import stats, optimize


class CBSEMAlgorithm:
    """
    Covariance-Based Structural Equation Modeling (CB-SEM) Engine.
    Uses Reticular Action Model (RAM) parameterization and ML estimation.
    """

    def __init__(
        self,
        optimizer_method: str = "L-BFGS-B",
        max_iter: int = 500,
        tol: float = 1e-8,
        min_variance: float = 1e-5,
    ):
        """
        Args:
            optimizer_method: Optimization algorithm ('L-BFGS-B' or 'SLSQP').
            max_iter: Maximum iterations for optimizer.
            tol: Optimization convergence tolerance.
            min_variance: Lower bound for error and latent variances to prevent Heywood cases.
        """
        self.optimizer_method = optimizer_method
        self.max_iter = max_iter
        self.tol = tol
        self.min_variance = min_variance

    def _parse_spec(self, model_spec: Any) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, str], List[Tuple[str, str]]]:
        """Parses model_spec into constructs, indicator mappings, and structural paths."""
        if hasattr(model_spec, "model_dump"):
            spec_dict = model_spec.model_dump(by_alias=True)
        elif isinstance(model_spec, dict):
            spec_dict = model_spec
        else:
            raise TypeError("model_spec must be a ModelSpec instance or dictionary")

        constructs = {}
        for c in spec_dict.get("constructs", []):
            cid = c["id"]
            constructs[cid] = {
                "id": cid,
                "name": c.get("name", cid),
                "type": c.get("type", "reflective").lower(),
                "indicators": list(c.get("indicators", [])),
            }

        indicator_col_map = {}
        for ind in spec_dict.get("indicators", []):
            iid = ind["id"]
            col = ind.get("column", iid)
            indicator_col_map[iid] = col

        paths = []
        for p in spec_dict.get("paths", []):
            from_c = p.get("from") or p.get("from_node")
            to_c = p.get("to") or p.get("to_node")
            if from_c and to_c:
                paths.append((from_c, to_c))

        return constructs, indicator_col_map, paths

    def _rmsea_ci(self, chi2: float, df: int, n: int) -> Tuple[float, float]:
        """Calculates 90% confidence interval for RMSEA using non-central chi-square."""
        if df <= 0 or n <= 1:
            return 0.0, 0.0

        # Find delta_lower where cdf(chi2, df, delta) = 0.95
        # Find delta_upper where cdf(chi2, df, delta) = 0.05
        def f_low(delta):
            return stats.ncx2.cdf(chi2, df, delta) - 0.95

        def f_up(delta):
            return stats.ncx2.cdf(chi2, df, delta) - 0.05

        # Lower bound
        if stats.chi2.cdf(chi2, df) < 0.95:
            delta_low = 0.0
        else:
            try:
                res_low = optimize.root_scalar(f_low, bracket=[0.0, max(1000.0, chi2 * 5)], method="brentq")
                delta_low = max(0.0, float(res_low.root))
            except Exception:
                delta_low = 0.0

        # Upper bound
        if stats.chi2.cdf(chi2, df) < 0.05:
            delta_up = 0.0
        else:
            try:
                res_up = optimize.root_scalar(f_up, bracket=[0.0, max(2000.0, chi2 * 10)], method="brentq")
                delta_up = max(0.0, float(res_up.root))
            except Exception:
                delta_up = max(0.0, chi2 - df)

        rmsea_low = math.sqrt(delta_low / ((n - 1) * df))
        rmsea_high = math.sqrt(delta_up / ((n - 1) * df))
        return rmsea_low, rmsea_high

    def fit(self, data: pd.DataFrame, model_spec: Any) -> Dict[str, Any]:
        """
        Fits a CB-SEM model using Maximum Likelihood.

        Args:
            data: pandas DataFrame of observations.
            model_spec: ModelSpec instance or dictionary.

        Returns:
            Dictionary containing model fit indices, parameter estimates with SE, z, p-values,
            standardized estimates, implied covariance matrix, and Heywood case flags.
        """
        constructs, ind_col_map, paths = self._parse_spec(model_spec)
        construct_ids = list(constructs.keys())
        n_constructs = len(construct_ids)

        # Collect all indicator IDs and map to columns in order
        observed_indicators: List[str] = []
        observed_cols: List[str] = []
        indicator_to_construct: Dict[str, str] = {}

        for cid in construct_ids:
            for iid in constructs[cid]["indicators"]:
                if iid not in observed_indicators:
                    col = ind_col_map.get(iid, iid)
                    if col not in data.columns:
                        raise KeyError(f"Indicator '{iid}' mapped to column '{col}' not in dataset.")
                    observed_indicators.append(iid)
                    observed_cols.append(col)
                    indicator_to_construct[iid] = cid

        p = len(observed_indicators)
        m = n_constructs
        total_vars = p + m
        n_sample_moments = p * (p + 1) // 2

        # Variable index mapping in RAM matrix:
        # [0 ... p-1]: observed indicators
        # [p ... p+m-1]: latent constructs
        obs_idx = {iid: idx for idx, iid in enumerate(observed_indicators)}
        latent_idx = {cid: p + idx for idx, cid in enumerate(construct_ids)}

        # Extract numeric data and sample covariance matrix S
        sub_data = data[observed_cols].copy().dropna()
        n_samples = len(sub_data)
        if n_samples <= p:
            raise ValueError(f"Sample size N={n_samples} must be greater than number of indicators p={p}.")

        X_obs = sub_data.to_numpy(dtype=float)
        # Sample covariance matrix S with divisor (N - 1)
        S_sample = np.cov(X_obs, rowvar=False, ddof=1)
        if p == 1:
            S_sample = np.array([[S_sample]])

        # Symmetrize S
        S_sample = 0.5 * (S_sample + S_sample.T)

        # Log determinant of S
        try:
            L_S = np.linalg.cholesky(S_sample)
            log_det_S = 2.0 * np.sum(np.log(np.diag(L_S)))
        except np.linalg.LinAlgError:
            # Fallback if S has minor singularity issues
            sign, log_det_S = np.linalg.slogdet(S_sample)
            if sign <= 0:
                raise ValueError("Sample covariance matrix S is not positive definite.")

        # Identify exogenous vs endogenous latent constructs
        endogenous_constructs = set(to_c for _, to_c in paths)
        exogenous_constructs = [cid for cid in construct_ids if cid not in endogenous_constructs]

        # -----------------------------------------------------------------
        # Build Parameter Layout:
        # Free parameters theta will contain:
        # 1. Free factor loadings (first indicator per construct is marker with loading = 1.0)
        # 2. Free structural paths
        # 3. Indicator measurement error variances (p parameters, lower bound > 0)
        # 4. Latent variances / residual variances (m parameters, lower bound > 0)
        # 5. Exogenous latent covariances (if >= 2 exogenous constructs)
        # -----------------------------------------------------------------
        params_info = []  # list of dicts describing each parameter

        # 1. Loadings
        # For each construct, first indicator is marker (fixed = 1.0)
        for cid in construct_ids:
            inds = constructs[cid]["indicators"]
            for i, iid in enumerate(inds):
                if i == 0:
                    # Marker variable: fixed loading = 1.0
                    continue
                params_info.append({
                    "type": "loading",
                    "construct": cid,
                    "indicator": iid,
                    "row": obs_idx[iid],
                    "col": latent_idx[cid],
                    "matrix": "A",
                    "lower_bound": None,
                    "upper_bound": None,
                })

        # 2. Structural paths
        for from_c, to_c in paths:
            params_info.append({
                "type": "path",
                "from": from_c,
                "to": to_c,
                "row": latent_idx[to_c],
                "col": latent_idx[from_c],
                "matrix": "A",
                "lower_bound": None,
                "upper_bound": None,
            })

        # 3. Indicator residual variances
        for iid in observed_indicators:
            params_info.append({
                "type": "error_variance",
                "indicator": iid,
                "row": obs_idx[iid],
                "col": obs_idx[iid],
                "matrix": "S",
                "lower_bound": self.min_variance,
                "upper_bound": None,
            })

        # 4. Latent variances / disturbances
        for cid in construct_ids:
            params_info.append({
                "type": "latent_variance",
                "construct": cid,
                "row": latent_idx[cid],
                "col": latent_idx[cid],
                "matrix": "S",
                "lower_bound": self.min_variance,
                "upper_bound": None,
            })

        # 5. Exogenous latent covariances
        if len(exogenous_constructs) >= 2:
            for i in range(len(exogenous_constructs)):
                for j in range(i + 1, len(exogenous_constructs)):
                    c1 = exogenous_constructs[i]
                    c2 = exogenous_constructs[j]
                    params_info.append({
                        "type": "latent_covariance",
                        "construct1": c1,
                        "construct2": c2,
                        "row": latent_idx[c1],
                        "col": latent_idx[c2],
                        "matrix": "S",
                        "lower_bound": None,
                        "upper_bound": None,
                    })

        q = len(params_info)
        df = n_sample_moments - q

        # Identification check:
        if df < 0:
            return {
                "algorithm": "cbsem",
                "converged": False,
                "error": f"Model is under-identified: degrees of freedom df={df} < 0 (moments={n_sample_moments}, parameters={q}).",
                "df": df,
                "n_sample_moments": n_sample_moments,
                "n_parameters": q,
            }

        # -----------------------------------------------------------------
        # Initial Parameter Values:
        # -----------------------------------------------------------------
        theta0 = np.zeros(q, dtype=float)
        bounds = []

        # Fixed entries in A matrix
        # A_fixed contains marker variable loadings
        A_fixed = np.zeros((total_vars, total_vars), dtype=float)
        for cid in construct_ids:
            marker_iid = constructs[cid]["indicators"][0]
            A_fixed[obs_idx[marker_iid], latent_idx[cid]] = 1.0

        for idx, pinfo in enumerate(params_info):
            ptype = pinfo["type"]
            lb = pinfo["lower_bound"]
            ub = pinfo["upper_bound"]
            bounds.append((lb, ub))

            if ptype == "loading":
                iid = pinfo["indicator"]
                cid = pinfo["construct"]
                marker_iid = constructs[cid]["indicators"][0]
                i_idx = obs_idx[iid]
                m_idx = obs_idx[marker_iid]
                # Ratio of stds or covariance ratio
                cov_im = S_sample[i_idx, m_idx]
                var_m = S_sample[m_idx, m_idx]
                init_val = cov_im / var_m if var_m > 0 else 1.0
                theta0[idx] = float(np.clip(init_val, -10.0, 10.0))

            elif ptype == "path":
                # Structural regression initial guess
                theta0[idx] = 0.1

            elif ptype == "error_variance":
                iid = pinfo["indicator"]
                i_idx = obs_idx[iid]
                # Half of sample variance
                theta0[idx] = float(max(self.min_variance * 10, 0.5 * S_sample[i_idx, i_idx]))

            elif ptype == "latent_variance":
                cid = pinfo["construct"]
                marker_iid = constructs[cid]["indicators"][0]
                m_idx = obs_idx[marker_iid]
                # Half of marker variance
                theta0[idx] = float(max(self.min_variance * 10, 0.5 * S_sample[m_idx, m_idx]))

            elif ptype == "latent_covariance":
                theta0[idx] = 0.0

        # Helper to construct RAM matrices A and S from theta
        eye_total = np.eye(total_vars)

        def _compute_sigma(theta: np.ndarray) -> Tuple[Optional[np.ndarray], Optional[np.ndarray], Optional[np.ndarray]]:
            """Returns (Sigma_obs, Sigma_all, invIminusA) or (None, None, None) if singular."""
            A = A_fixed.copy()
            S_mat = np.zeros((total_vars, total_vars), dtype=float)

            for val, pinfo in zip(theta, params_info):
                r = pinfo["row"]
                c = pinfo["col"]
                if pinfo["matrix"] == "A":
                    A[r, c] = val
                else:  # 'S'
                    S_mat[r, c] = val
                    S_mat[c, r] = val

            try:
                invIminusA = np.linalg.inv(eye_total - A)
            except np.linalg.LinAlgError:
                return None, None, None

            Sigma_all = invIminusA @ S_mat @ invIminusA.T
            Sigma_obs = Sigma_all[:p, :p]
            Sigma_obs = 0.5 * (Sigma_obs + Sigma_obs.T)
            return Sigma_obs, Sigma_all, invIminusA

        # ML Discrepancy Objective Function
        def _objective(theta: np.ndarray) -> float:
            # Enforce variance bounds penalty
            pen = 0.0
            for val, pinfo in zip(theta, params_info):
                if pinfo["lower_bound"] is not None and val < pinfo["lower_bound"]:
                    pen += 1e5 * (pinfo["lower_bound"] - val) ** 2

            Sigma_obs, _, _ = _compute_sigma(theta)
            if Sigma_obs is None:
                return 1e10 + pen

            try:
                L = np.linalg.cholesky(Sigma_obs)
                log_det_sigma = 2.0 * np.sum(np.log(np.diag(L)))
                # trace(S * Sigma^{-1})
                # solve L * Y = S => solve L.T * X = Y
                Y = np.linalg.solve(L, S_sample)
                X = np.linalg.solve(L.T, Y)
                tr_s_inv_sigma = np.trace(X)
                f_ml = log_det_sigma + tr_s_inv_sigma - log_det_S - p
                if math.isnan(f_ml) or math.isinf(f_ml):
                    return 1e10 + pen
                return float(f_ml + pen)
            except np.linalg.LinAlgError:
                # Eigenvalue penalty if not positive definite
                eigvals = np.linalg.eigvalsh(Sigma_obs)
                min_eig = np.min(eigvals)
                return float(1e8 + 1e4 * max(0.0, -min_eig) + pen)

        # Optimization
        res = optimize.minimize(
            _objective,
            theta0,
            method=self.optimizer_method,
            bounds=bounds if self.optimizer_method == "L-BFGS-B" else None,
            options={"maxiter": self.max_iter, "ftol": self.tol},
        )

        converged = bool(res.success)
        theta_hat = res.x
        f_min = float(res.fun)

        # Implied covariances at minimum
        Sigma_obs, Sigma_all, _ = _compute_sigma(theta_hat)
        if Sigma_obs is None:
            Sigma_obs = S_sample.copy()
            Sigma_all = np.eye(total_vars)

        # -----------------------------------------------------------------
        # Standard Errors via Numerical Hessian & Fisher Information Matrix
        # -----------------------------------------------------------------
        se_estimates = np.zeros(q, dtype=float)
        z_scores = np.zeros(q, dtype=float)
        p_values = np.zeros(q, dtype=float)

        try:
            # Central difference step size
            h = np.maximum(1e-4 * np.abs(theta_hat), 1e-5)
            H = np.zeros((q, q), dtype=float)

            # Diagonal elements
            f_center = _objective(theta_hat)
            for i in range(q):
                th_plus = theta_hat.copy()
                th_plus[i] += h[i]
                th_minus = theta_hat.copy()
                th_minus[i] -= h[i]
                f_plus = _objective(th_plus)
                f_minus = _objective(th_minus)
                H[i, i] = (f_plus - 2.0 * f_center + f_minus) / (h[i] ** 2)

            # Off-diagonal elements
            for i in range(q):
                for j in range(i + 1, q):
                    th_pp = theta_hat.copy()
                    th_pp[i] += h[i]
                    th_pp[j] += h[j]

                    th_pm = theta_hat.copy()
                    th_pm[i] += h[i]
                    th_pm[j] -= h[j]

                    th_mp = theta_hat.copy()
                    th_mp[i] -= h[i]
                    th_mp[j] += h[j]

                    th_mm = theta_hat.copy()
                    th_mm[i] -= h[i]
                    th_mm[j] -= h[j]

                    hij = (
                        _objective(th_pp)
                        - _objective(th_pm)
                        - _objective(th_mp)
                        + _objective(th_mm)
                    ) / (4.0 * h[i] * h[j])
                    H[i, j] = hij
                    H[j, i] = hij

            # Fisher information matrix: I = 0.5 * (N - 1) * H
            # Asymptotic covariance of estimates: V = (2 / (N - 1)) * H^{-1}
            info_mat = 0.5 * (n_samples - 1) * H
            acov = np.linalg.pinv(info_mat)

            for i in range(q):
                var_est = acov[i, i]
                if var_est > 0:
                    se = math.sqrt(var_est)
                    z = theta_hat[i] / se
                    p_val = 2.0 * (1.0 - stats.norm.cdf(abs(z)))
                    se_estimates[i] = float(se)
                    z_scores[i] = float(z)
                    p_values[i] = float(p_val)
                else:
                    se_estimates[i] = 0.0
                    z_scores[i] = 0.0
                    p_values[i] = 1.0
        except Exception:
            # Fallback if Hessian inversion fails
            pass

        # -----------------------------------------------------------------
        # Standardized Parameter Estimates & Parameter Table
        # -----------------------------------------------------------------
        parameter_estimates = []
        heywood_cases = []

        for i, pinfo in enumerate(params_info):
            raw_val = float(theta_hat[i])
            se = float(se_estimates[i])
            z = float(z_scores[i])
            pval = float(p_values[i])
            ptype = pinfo["type"]

            # Standardized coefficient
            std_val = raw_val
            if ptype == "loading":
                iid = pinfo["indicator"]
                cid = pinfo["construct"]
                var_lat = Sigma_all[latent_idx[cid], latent_idx[cid]]
                var_ind = Sigma_obs[obs_idx[iid], obs_idx[iid]]
                if var_lat > 0 and var_ind > 0:
                    std_val = raw_val * math.sqrt(var_lat / var_ind)
                if abs(std_val) > 1.0:
                    heywood_cases.append(f"Standardized loading of '{iid}' on '{cid}' exceeds 1.0 ({std_val:.3f})")

            elif ptype == "path":
                from_c = pinfo["from"]
                to_c = pinfo["to"]
                var_from = Sigma_all[latent_idx[from_c], latent_idx[from_c]]
                var_to = Sigma_all[latent_idx[to_c], latent_idx[to_c]]
                if var_from > 0 and var_to > 0:
                    std_val = raw_val * math.sqrt(var_from / var_to)

            elif ptype == "error_variance":
                iid = pinfo["indicator"]
                var_ind = Sigma_obs[obs_idx[iid], obs_idx[iid]]
                if var_ind > 0:
                    std_val = raw_val / var_ind
                if raw_val <= self.min_variance * 1.5:
                    heywood_cases.append(f"Near-zero/boundary error variance for indicator '{iid}' ({raw_val:.5f})")

            elif ptype == "latent_variance":
                cid = pinfo["construct"]
                var_lat = Sigma_all[latent_idx[cid], latent_idx[cid]]
                if var_lat > 0:
                    std_val = raw_val / var_lat
                if raw_val <= self.min_variance * 1.5:
                    heywood_cases.append(f"Near-zero/boundary latent variance for construct '{cid}' ({raw_val:.5f})")

            elif ptype == "latent_covariance":
                c1 = pinfo["construct1"]
                c2 = pinfo["construct2"]
                v1 = Sigma_all[latent_idx[c1], latent_idx[c1]]
                v2 = Sigma_all[latent_idx[c2], latent_idx[c2]]
                if v1 > 0 and v2 > 0:
                    std_val = raw_val / math.sqrt(v1 * v2)

            rec = {
                "type": ptype,
                "estimate": raw_val,
                "std_estimate": float(std_val),
                "std_error": se,
                "z_score": z,
                "p_value": pval,
            }
            # Add metadata keys
            for k in ["indicator", "construct", "from", "to", "construct1", "construct2"]:
                if k in pinfo:
                    rec[k] = pinfo[k]

            parameter_estimates.append(rec)

        # Include marker variables (fixed loading = 1.0) in loadings report
        for cid in construct_ids:
            marker_iid = constructs[cid]["indicators"][0]
            var_lat = Sigma_all[latent_idx[cid], latent_idx[cid]]
            var_ind = Sigma_obs[obs_idx[marker_iid], obs_idx[marker_iid]]
            std_marker = math.sqrt(var_lat / var_ind) if var_lat > 0 and var_ind > 0 else 1.0
            parameter_estimates.insert(0, {
                "type": "loading",
                "construct": cid,
                "indicator": marker_iid,
                "estimate": 1.0,
                "std_estimate": float(std_marker),
                "std_error": 0.0,
                "z_score": 0.0,
                "p_value": 0.0,
                "fixed": True,
            })

        # -----------------------------------------------------------------
        # Model Fit Indices Calculation
        # -----------------------------------------------------------------
        # 1. Chi-Square & p-value
        chi2 = max(0.0, float((n_samples - 1) * f_min))
        p_value_chi2 = float(1.0 - stats.chi2.cdf(chi2, df)) if df > 0 else 1.0

        # 2. Baseline (Null) Model: Independent observed indicators
        # Sigma_null = diag(S_sample)
        # F_null = sum(log(s_ii)) - log|S|
        diag_s = np.diag(S_sample)
        log_det_null = np.sum(np.log(diag_s))
        f_null = float(log_det_null - log_det_S)
        df_null = p * (p - 1) // 2
        chi2_null = max(0.0, float((n_samples - 1) * f_null))
        p_value_null = float(1.0 - stats.chi2.cdf(chi2_null, df_null)) if df_null > 0 else 1.0

        # 3. Incremental Fit: CFI and TLI
        d_model = max(0.0, chi2 - df)
        d_null = max(0.0, max(chi2_null - df_null, d_model))
        cfi = float(1.0 - (d_model / d_null)) if d_null > 0 else 1.0
        cfi = max(0.0, min(cfi, 1.0))

        if df > 0 and df_null > 0 and (chi2_null / df_null - 1.0) > 0:
            tli = float(((chi2_null / df_null) - (chi2 / df)) / ((chi2_null / df_null) - 1.0))
            tli = max(0.0, min(tli, 1.0))
        else:
            tli = 1.0

        # 4. Absolute Fit: RMSEA (+ 90% CI) & SRMR
        if df > 0:
            rmsea_val = math.sqrt(max(0.0, (chi2 - df) / ((n_samples - 1) * df)))
            rmsea_low, rmsea_high = self._rmsea_ci(chi2, df, n_samples)
        else:
            rmsea_val = 0.0
            rmsea_low, rmsea_high = 0.0, 0.0

        # SRMR (Standardized Root Mean Square Residual)
        std_diag = np.sqrt(diag_s)
        std_diag[std_diag == 0] = 1.0
        R_S = S_sample / np.outer(std_diag, std_diag)

        diag_sigma = np.sqrt(np.diag(Sigma_obs))
        diag_sigma[diag_sigma == 0] = 1.0
        R_Sigma = Sigma_obs / np.outer(diag_sigma, diag_sigma)

        R_res = R_S - R_Sigma
        # Sum of squared lower-triangle elements
        tril_indices = np.tril_indices(p)
        srmr_val = float(math.sqrt(np.mean(R_res[tril_indices] ** 2)))

        # 5. Information Criteria: AIC & BIC
        aic = float(chi2 + 2.0 * q)
        bic = float(chi2 + q * math.log(n_samples))

        fit_indices = {
            "chi2": chi2,
            "df": df,
            "p_value": p_value_chi2,
            "chi2_null": chi2_null,
            "df_null": df_null,
            "p_value_null": p_value_null,
            "cfi": cfi,
            "tli": tli,
            "rmsea": float(rmsea_val),
            "rmsea_ci_90": [rmsea_low, rmsea_high],
            "srmr": srmr_val,
            "aic": aic,
            "bic": bic,
        }

        # Structure parameters by category for frontend/user convenience
        loadings_dict = {}
        paths_dict = {}
        variances_dict = {}

        for p_est in parameter_estimates:
            ptype = p_est["type"]
            if ptype == "loading":
                c = p_est["construct"]
                ind = p_est["indicator"]
                if c not in loadings_dict:
                    loadings_dict[c] = {}
                loadings_dict[c][ind] = p_est
            elif ptype == "path":
                t = p_est["to"]
                f = p_est["from"]
                if t not in paths_dict:
                    paths_dict[t] = {}
                paths_dict[t][f] = p_est
            else:
                variances_dict[f"{ptype}_{p_est.get('indicator', p_est.get('construct', ''))}"] = p_est

        return {
            "algorithm": "cbsem",
            "converged": converged,
            "iterations": int(res.nit) if hasattr(res, "nit") else 0,
            "n_samples": n_samples,
            "n_parameters": q,
            "degrees_of_freedom": df,
            "fit_indices": fit_indices,
            "parameters": parameter_estimates,
            "structural_paths": paths_dict,
            "measurement_loadings": loadings_dict,
            "variances_and_covariances": variances_dict,
            "implied_covariance": pd.DataFrame(Sigma_obs, index=observed_indicators, columns=observed_indicators),
            "sample_covariance": pd.DataFrame(S_sample, index=observed_indicators, columns=observed_indicators),
            "heywood_cases": heywood_cases,
        }


def run_cbsem(data: pd.DataFrame, model_spec: Any) -> Dict[str, Any]:
    """Convenience entry point for CB-SEM."""
    algo = CBSEMAlgorithm()
    return algo.fit(data, model_spec)
