"""
PLS-SEM Algorithm Implementation (Phase 3)
Implements Wold's Lohmöller Partial Least Squares Path Modeling algorithm:
- Outer approximation & Inner approximation (path, factor, centroid weighting)
- Mode A (reflective) and Mode B (formative) outer updates
- Convergence & sign alignment
- Structural path estimation via OLS, R², adjusted R², f² effect sizes
- Measurement model metrics: outer loadings, outer weights, indicator reliability
- Internal consistency & validity: Cronbach's alpha, Composite Reliability (CR), rho_A, AVE
- Discriminant validity: Fornell-Larcker matrix, HTMT matrix
- Collinearity: Inner VIF and Outer VIF
- Direct, indirect, and total effects
- Bootstrapping procedure for standard errors and p-values
"""

import math
from typing import Dict, List, Optional, Tuple, Any, Union
import numpy as np
import pandas as pd
from scipy import stats


def _standardize_matrix(X: np.ndarray) -> np.ndarray:
    """Standardizes columns of X to zero mean and unit variance."""
    mean = np.mean(X, axis=0)
    std = np.std(X, axis=0, ddof=0)
    std[std == 0] = 1.0  # avoid division by zero for constant columns
    return (X - mean) / std


def _calculate_vif(X: np.ndarray) -> List[float]:
    """
    Calculates Variance Inflation Factor (VIF) for columns of matrix X.
    If 1 column, VIF is 1.0.
    """
    n_vars = X.shape[1]
    if n_vars <= 1:
        return [1.0] * n_vars

    vifs = []
    for i in range(n_vars):
        y = X[:, i]
        X_others = np.delete(X, i, axis=1)
        # Add intercept
        X_design = np.column_stack([np.ones(len(y)), X_others])
        try:
            beta, residuals, _, _ = np.linalg.lstsq(X_design, y, rcond=None)
            y_pred = X_design @ beta
            ss_tot = np.sum((y - np.mean(y)) ** 2)
            ss_res = np.sum((y - y_pred) ** 2)
            r2 = 1.0 - (ss_res / ss_tot) if ss_tot > 0 else 0.0
            r2 = max(0.0, min(r2, 0.999999))
            vif = 1.0 / (1.0 - r2)
        except Exception:
            vif = 1.0
        vifs.append(float(vif))
    return vifs


class PLSAlgorithm:
    """
    Partial Least Squares Structural Equation Modeling (PLS-SEM) Engine.
    """

    def __init__(
        self,
        scheme: str = "path",
        max_iter: int = 300,
        tol: float = 1e-7,
        sign_alignment: bool = True,
    ):
        """
        Args:
            scheme: Inner weighting scheme: 'path' (default), 'factor', or 'centroid'.
            max_iter: Maximum number of iterations for Wold algorithm.
            tol: Convergence tolerance for outer weights difference.
            sign_alignment: Whether to align signs of latent constructs with dominant indicator.
        """
        if scheme not in ["path", "factor", "centroid"]:
            raise ValueError(f"Unknown inner weighting scheme: {scheme}. Use 'path', 'factor', or 'centroid'.")
        self.scheme = scheme
        self.max_iter = max_iter
        self.tol = tol
        self.sign_alignment = sign_alignment

    def _parse_spec(self, model_spec: Any) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, str], List[Tuple[str, str]]]:
        """
        Extracts constructs, indicator-to-column mapping, and directed paths from model_spec.
        Supports ModelSpec Pydantic object or dict.
        """
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

    def fit(self, data: pd.DataFrame, model_spec: Any) -> Dict[str, Any]:
        """
        Runs the full PLS-SEM estimation.

        Args:
            data: pandas DataFrame of observations.
            model_spec: ModelSpec instance or dictionary specifying constructs, indicators, paths.

        Returns:
            Dictionary containing full structural, measurement, reliability, validity,
            collinearity, effect sizes, and construct scores.
        """
        constructs, ind_col_map, paths = self._parse_spec(model_spec)
        construct_ids = list(constructs.keys())
        n_constructs = len(construct_ids)
        c_idx_map = {cid: idx for idx, cid in enumerate(construct_ids)}

        # Validate that indicators exist in data
        all_required_cols = []
        for c in constructs.values():
            for iid in c["indicators"]:
                col = ind_col_map.get(iid, iid)
                if col not in data.columns:
                    raise KeyError(f"Indicator '{iid}' mapped to column '{col}' was not found in dataset columns.")
                all_required_cols.append(col)

        # Build clean numeric matrix of required columns
        sub_data = data[all_required_cols].copy().dropna()
        n_samples = len(sub_data)
        if n_samples < 5:
            raise ValueError(f"Insufficient valid data rows ({n_samples}) for PLS-SEM.")

        # Standardized indicator matrices per construct
        construct_indicators = {}
        construct_data_norm = {}
        construct_indicator_names = {}

        for cid, cinfo in constructs.items():
            inds = cinfo["indicators"]
            cols = [ind_col_map.get(iid, iid) for iid in inds]
            X_c = sub_data[cols].to_numpy(dtype=float)
            X_norm = _standardize_matrix(X_c)
            construct_indicators[cid] = inds
            construct_indicator_names[cid] = cols
            construct_data_norm[cid] = X_norm

        # Build adjacency matrix for inner paths
        # adj[i, j] == 1 means i -> j (i is predecessor of j, j is successor of i)
        adj = np.zeros((n_constructs, n_constructs), dtype=float)
        for from_c, to_c in paths:
            if from_c in c_idx_map and to_c in c_idx_map:
                i = c_idx_map[from_c]
                j = c_idx_map[to_c]
                adj[i, j] = 1.0

        # Step 1: Initialize outer weights
        weights = {}
        for cid in construct_ids:
            k = len(construct_indicators[cid])
            # Initial unit or equal weights: 1 / sqrt(k)
            w = np.ones(k, dtype=float) / np.sqrt(k)
            weights[cid] = w

        # Compute initial construct scores Y
        Y = np.zeros((n_samples, n_constructs), dtype=float)
        for cid, idx in c_idx_map.items():
            X_norm = construct_data_norm[cid]
            y_raw = X_norm @ weights[cid]
            std_y = np.std(y_raw, ddof=0)
            if std_y == 0:
                std_y = 1.0
            Y[:, idx] = (y_raw - np.mean(y_raw)) / std_y

        # Step 2: Iterative Wold Algorithm
        converged = False
        iteration = 0

        while iteration < self.max_iter and not converged:
            iteration += 1
            old_weights = {cid: weights[cid].copy() for cid in construct_ids}

            # 2a: Inner Approximation: Compute inner scores Y_tilde
            # Inner weight e_{j, i}: relation between construct j and construct i
            E = np.zeros((n_constructs, n_constructs), dtype=float)

            if self.scheme == "centroid":
                corr_Y = np.corrcoef(Y, rowvar=False)
                if n_constructs == 1:
                    corr_Y = np.array([[1.0]])
                for i in range(n_constructs):
                    for j in range(n_constructs):
                        if adj[i, j] == 1.0 or adj[j, i] == 1.0:
                            E[i, j] = np.sign(corr_Y[i, j])

            elif self.scheme == "factor":
                corr_Y = np.corrcoef(Y, rowvar=False)
                if n_constructs == 1:
                    corr_Y = np.array([[1.0]])
                for i in range(n_constructs):
                    for j in range(n_constructs):
                        if adj[i, j] == 1.0 or adj[j, i] == 1.0:
                            E[i, j] = corr_Y[i, j]

            else:  # 'path' scheme (Lohmöller standard)
                corr_Y = np.corrcoef(Y, rowvar=False)
                if n_constructs == 1:
                    corr_Y = np.array([[1.0]])

                for j in range(n_constructs):
                    # Predecessors of j: {i: adj[i, j] == 1}
                    preds = [i for i in range(n_constructs) if adj[i, j] == 1.0]
                    if preds:
                        if len(preds) == 1:
                            E[preds[0], j] = corr_Y[preds[0], j]
                        else:
                            # Multiple regression of Y_j on Y_preds
                            Y_preds = Y[:, preds]
                            try:
                                b, _, _, _ = np.linalg.lstsq(Y_preds, Y[:, j], rcond=None)
                                for p_idx, p in enumerate(preds):
                                    E[p, j] = b[p_idx]
                            except Exception:
                                for p in preds:
                                    E[p, j] = corr_Y[p, j]

                    # Successors of j: {k: adj[j, k] == 1}
                    succs = [k for k in range(n_constructs) if adj[j, k] == 1.0]
                    for k in succs:
                        E[k, j] = corr_Y[k, j]

            # Compute inner proxy scores Y_tilde
            Y_tilde = np.zeros_like(Y)
            for j in range(n_constructs):
                connected = [i for i in range(n_constructs) if E[i, j] != 0]
                if connected:
                    inner_score = np.zeros(n_samples)
                    for i in connected:
                        inner_score += E[i, j] * Y[:, i]
                else:
                    inner_score = Y[:, j]

                std_inner = np.std(inner_score, ddof=0)
                if std_inner > 0:
                    Y_tilde[:, j] = (inner_score - np.mean(inner_score)) / std_inner
                else:
                    Y_tilde[:, j] = Y[:, j]

            # 2b: Outer Weights Update
            for cid, j in c_idx_map.items():
                X_norm = construct_data_norm[cid]
                c_type = constructs[cid]["type"]
                y_inner = Y_tilde[:, j]

                if c_type == "reflective":
                    # Mode A: Bivariate regression of indicators on inner score
                    # Since both are standardized, cov(X_k, y_inner) = (1/N) * X_k.T @ y_inner
                    w_new = (X_norm.T @ y_inner) / n_samples
                else:
                    # Mode B (Formative): Multiple regression of inner score on indicators
                    try:
                        w_new, _, _, _ = np.linalg.lstsq(X_norm, y_inner, rcond=None)
                    except Exception:
                        w_new = (X_norm.T @ y_inner) / n_samples

                # Normalize outer weights so that Var(X w) = 1
                y_outer = X_norm @ w_new
                std_outer = np.std(y_outer, ddof=0)
                if std_outer > 0:
                    w_new = w_new / std_outer
                else:
                    w_new = np.ones_like(w_new) / np.sqrt(len(w_new))

                weights[cid] = w_new

            # 2c: Update construct scores Y
            for cid, j in c_idx_map.items():
                X_norm = construct_data_norm[cid]
                y_raw = X_norm @ weights[cid]
                std_y = np.std(y_raw, ddof=0)
                if std_y > 0:
                    Y[:, j] = (y_raw - np.mean(y_raw)) / std_y
                else:
                    Y[:, j] = y_raw

            # 2d: Convergence Check: max change in outer weights
            max_diff = max(
                np.max(np.abs(weights[cid] - old_weights[cid]))
                for cid in construct_ids
            )
            if max_diff < self.tol:
                converged = True

        # Step 3: Sign Alignment
        # Align latent variables so outer loadings have positive sum / dominant sign
        loadings = {}
        for cid, j in c_idx_map.items():
            X_norm = construct_data_norm[cid]
            y_j = Y[:, j]
            # Loadings are correlations between indicators and construct score
            c_loadings = (X_norm.T @ y_j) / n_samples

            if self.sign_alignment and np.sum(c_loadings) < 0:
                # Flip sign
                weights[cid] = -weights[cid]
                Y[:, j] = -Y[:, j]
                c_loadings = -c_loadings

            loadings[cid] = c_loadings

        # Step 4: Structural Model Estimation
        # Path coefficients via OLS regression of endogenous constructs on predecessors
        path_coefs: Dict[str, Dict[str, float]] = {cid: {} for cid in construct_ids}
        path_matrix = np.zeros((n_constructs, n_constructs), dtype=float)
        r_squared: Dict[str, float] = {}
        r_squared_adj: Dict[str, float] = {}
        f_squared: Dict[str, Dict[str, float]] = {cid: {} for cid in construct_ids}
        inner_vif: Dict[str, Dict[str, float]] = {cid: {} for cid in construct_ids}

        for j_idx, target_cid in enumerate(construct_ids):
            pred_indices = [i for i in range(n_constructs) if adj[i, j_idx] == 1.0]
            if not pred_indices:
                # Exogenous construct
                continue

            y_target = Y[:, j_idx]
            X_preds = Y[:, pred_indices]
            k_preds = len(pred_indices)

            # Multiple regression (no intercept since variables are standardized)
            beta, _, _, _ = np.linalg.lstsq(X_preds, y_target, rcond=None)
            y_hat = X_preds @ beta
            ss_tot = np.sum((y_target - np.mean(y_target)) ** 2)
            ss_res = np.sum((y_target - y_hat) ** 2)
            r2 = float(1.0 - (ss_res / ss_tot)) if ss_tot > 0 else 0.0
            r2 = max(0.0, min(r2, 1.0))
            r_squared[target_cid] = r2

            # Adjusted R²: 1 - (1 - R²) * (N - 1) / (N - k - 1)
            if n_samples - k_preds - 1 > 0:
                r2_adj = float(1.0 - (1.0 - r2) * (n_samples - 1) / (n_samples - k_preds - 1))
            else:
                r2_adj = r2
            r_squared_adj[target_cid] = max(0.0, r2_adj)

            # Store path coefficients
            for p_pos, p_idx in enumerate(pred_indices):
                source_cid = construct_ids[p_idx]
                val = float(beta[p_pos])
                path_coefs[target_cid][source_cid] = val
                path_matrix[p_idx, j_idx] = val

            # f² effect sizes: (R²_incl - R²_excl) / (1 - R²_incl)
            if k_preds > 1 and r2 < 1.0:
                for p_pos, p_idx in enumerate(pred_indices):
                    source_cid = construct_ids[p_idx]
                    other_preds = [idx for idx in pred_indices if idx != p_idx]
                    X_reduced = Y[:, other_preds]
                    b_red, _, _, _ = np.linalg.lstsq(X_reduced, y_target, rcond=None)
                    y_red_hat = X_reduced @ b_red
                    ss_red_res = np.sum((y_target - y_red_hat) ** 2)
                    r2_excl = max(0.0, float(1.0 - (ss_red_res / ss_tot)))
                    f2 = (r2 - r2_excl) / (1.0 - r2)
                    f_squared[target_cid][source_cid] = float(max(0.0, f2))
            elif k_preds == 1 and r2 < 1.0:
                # Single predictor: excluding it means R²_excl = 0
                source_cid = construct_ids[pred_indices[0]]
                f2 = r2 / (1.0 - r2)
                f_squared[target_cid][source_cid] = float(max(0.0, f2))

            # Inner VIF for predictors
            if k_preds > 1:
                vifs = _calculate_vif(X_preds)
                for p_pos, p_idx in enumerate(pred_indices):
                    source_cid = construct_ids[p_idx]
                    inner_vif[target_cid][source_cid] = float(vifs[p_pos])
            elif k_preds == 1:
                source_cid = construct_ids[pred_indices[0]]
                inner_vif[target_cid][source_cid] = 1.0

        # Step 5: Direct, Indirect, and Total Effects
        # In path_matrix, entry [i, j] is path i -> j
        # Total effects T = (I - B)^{-1} - I = B + B^2 + B^3 + ...
        ident = np.eye(n_constructs)
        try:
            total_effects_mat = np.linalg.inv(ident - path_matrix) - ident
        except np.linalg.LinAlgError:
            total_effects_mat = path_matrix.copy()

        indirect_effects_mat = total_effects_mat - path_matrix

        effects_summary = []
        for i in range(n_constructs):
            for j in range(n_constructs):
                from_id = construct_ids[i]
                to_id = construct_ids[j]
                direct = float(path_matrix[i, j])
                indirect = float(indirect_effects_mat[i, j])
                total = float(total_effects_mat[i, j])
                if abs(direct) > 1e-7 or abs(indirect) > 1e-7 or abs(total) > 1e-7:
                    effects_summary.append({
                        "from": from_id,
                        "to": to_id,
                        "direct": direct,
                        "indirect": indirect,
                        "total": total,
                    })

        # Step 6: Measurement Model Evaluation & Quality Metrics
        outer_weights_dict: Dict[str, Dict[str, float]] = {}
        outer_loadings_dict: Dict[str, Dict[str, float]] = {}
        indicator_reliability_dict: Dict[str, Dict[str, float]] = {}
        outer_vif_dict: Dict[str, Dict[str, float]] = {}

        cronbachs_alpha: Dict[str, float] = {}
        composite_reliability: Dict[str, float] = {}
        rho_a: Dict[str, float] = {}
        ave: Dict[str, float] = {}

        for cid in construct_ids:
            inds = construct_indicators[cid]
            w_c = weights[cid]
            l_c = loadings[cid]
            X_norm = construct_data_norm[cid]
            k_ind = len(inds)

            outer_weights_dict[cid] = {iid: float(w_c[pos]) for pos, iid in enumerate(inds)}
            outer_loadings_dict[cid] = {iid: float(l_c[pos]) for pos, iid in enumerate(inds)}
            indicator_reliability_dict[cid] = {iid: float(l_c[pos] ** 2) for pos, iid in enumerate(inds)}

            # Outer VIF
            if k_ind > 1:
                ovifs = _calculate_vif(X_norm)
                outer_vif_dict[cid] = {iid: float(ovifs[pos]) for pos, iid in enumerate(inds)}
            else:
                outer_vif_dict[cid] = {inds[0]: 1.0}

            # 1. Average Variance Extracted (AVE)
            ave_val = float(np.mean(l_c ** 2))
            ave[cid] = ave_val

            # 2. Composite Reliability (CR)
            sum_loadings = float(np.sum(l_c))
            sum_error_var = float(np.sum(1.0 - l_c ** 2))
            denom_cr = (sum_loadings ** 2) + sum_error_var
            cr_val = (sum_loadings ** 2) / denom_cr if denom_cr > 0 else 0.0
            composite_reliability[cid] = float(cr_val)

            # 3. Cronbach's Alpha
            if k_ind > 1:
                corr_m = np.corrcoef(X_norm, rowvar=False)
                sum_all_corr = float(np.sum(corr_m))
                if sum_all_corr > 0:
                    alpha_val = (k_ind / (k_ind - 1)) * (1.0 - (k_ind / sum_all_corr))
                else:
                    alpha_val = 0.0
            else:
                alpha_val = 1.0
            cronbachs_alpha[cid] = float(max(0.0, min(alpha_val, 1.0)))

            # 4. Dijkstra-Henseler's rho_A
            # Formula: (w.T @ w)**2 * (w.T @ (S - diag(S)) @ w) / (w.T @ (w @ w.T - diag(w @ w.T)) @ w)
            if k_ind > 1:
                S_mat = np.corrcoef(X_norm, rowvar=False)
                w_vec = w_c
                w_sq_sum = np.sum(w_vec ** 2)
                # w.T @ (S - diag(S)) @ w = w.T @ S @ w - sum(w_i^2 * S_ii)
                num = (w_sq_sum ** 2) * (w_vec @ S_mat @ w_vec - np.sum((w_vec ** 2) * np.diag(S_mat)))
                # denom = (w.T @ w)**2 - sum(w_i**4)
                denom = (w_sq_sum ** 2) - np.sum(w_vec ** 4)
                rho_a_val = float(num / denom) if denom > 1e-12 else cr_val
            else:
                rho_a_val = 1.0
            rho_a[cid] = float(max(0.0, min(rho_a_val, 1.0)))

        # Step 7: Discriminant Validity
        # 7a: Fornell-Larcker Criterion
        # Matrix with sqrt(AVE) on diagonal, latent construct correlations on off-diagonal
        construct_corr = np.corrcoef(Y, rowvar=False)
        if n_constructs == 1:
            construct_corr = np.array([[1.0]])

        fornell_larcker: Dict[str, Dict[str, float]] = {c1: {} for c1 in construct_ids}
        for i, c1 in enumerate(construct_ids):
            for j, c2 in enumerate(construct_ids):
                if i == j:
                    fornell_larcker[c1][c2] = float(math.sqrt(max(0.0, ave[c1])))
                else:
                    fornell_larcker[c1][c2] = float(construct_corr[i, j])

        # 7b: HTMT Ratio (Heterotrait-Monotrait Ratio)
        htmt: Dict[str, Dict[str, float]] = {c1: {} for c1 in construct_ids}
        for i, c1 in enumerate(construct_ids):
            for j, c2 in enumerate(construct_ids):
                if i == j:
                    htmt[c1][c2] = 1.0
                    continue

                X1 = construct_data_norm[c1]
                X2 = construct_data_norm[c2]
                k1 = X1.shape[1]
                k2 = X2.shape[1]

                # Numerator: Average absolute cross-correlations
                cross_corr = np.abs(np.corrcoef(X1, X2, rowvar=False)[:k1, k1:])
                mean_cross = float(np.mean(cross_corr))

                # Denominator: Geometric mean of average within-construct absolute correlations
                if k1 > 1:
                    within1 = np.abs(np.corrcoef(X1, rowvar=False))
                    # Take strictly lower triangle
                    tril_indices1 = np.tril_indices(k1, k=-1)
                    mean_within1 = float(np.mean(within1[tril_indices1]))
                else:
                    mean_within1 = 1.0

                if k2 > 1:
                    within2 = np.abs(np.corrcoef(X2, rowvar=False))
                    tril_indices2 = np.tril_indices(k2, k=-1)
                    mean_within2 = float(np.mean(within2[tril_indices2]))
                else:
                    mean_within2 = 1.0

                denom_htmt = math.sqrt(max(1e-12, mean_within1 * mean_within2))
                htmt_val = float(mean_cross / denom_htmt)
                htmt[c1][c2] = htmt_val

        # Construct scores DataFrame
        scores_df = pd.DataFrame(Y, columns=construct_ids, index=sub_data.index)

        return {
            "algorithm": "pls",
            "converged": converged,
            "iterations": iteration,
            "n_samples": n_samples,
            "construct_scores": scores_df,
            "structural": {
                "path_coefficients": path_coefs,
                "r_squared": r_squared,
                "r_squared_adj": r_squared_adj,
                "f_squared": f_squared,
                "inner_vif": inner_vif,
                "effects": effects_summary,
            },
            "measurement": {
                "outer_weights": outer_weights_dict,
                "outer_loadings": outer_loadings_dict,
                "indicator_reliability": indicator_reliability_dict,
                "outer_vif": outer_vif_dict,
            },
            "reliability_and_validity": {
                "cronbachs_alpha": cronbachs_alpha,
                "composite_reliability": composite_reliability,
                "rho_a": rho_a,
                "ave": ave,
                "fornell_larcker": fornell_larcker,
                "htmt": htmt,
            },
        }

    def bootstrap(
        self,
        data: pd.DataFrame,
        model_spec: Any,
        n_boot: int = 500,
        seed: Optional[int] = 42,
    ) -> Dict[str, Any]:
        """
        Runs non-parametric bootstrapping to compute standard errors, t-values, and p-values
        for path coefficients, outer loadings, and outer weights.
        """
        if seed is not None:
            np.random.seed(seed)

        base_res = self.fit(data, model_spec)
        constructs, _, paths = self._parse_spec(model_spec)
        construct_ids = list(constructs.keys())
        n_samples = len(data)

        # Collect distributions
        boot_paths: Dict[Tuple[str, str], List[float]] = {p: [] for p in paths}
        boot_loadings: Dict[Tuple[str, str], List[float]] = {}
        boot_weights: Dict[Tuple[str, str], List[float]] = {}

        for cid, cinfo in constructs.items():
            for iid in cinfo["indicators"]:
                boot_loadings[(cid, iid)] = []
                boot_weights[(cid, iid)] = []

        for b in range(n_boot):
            # Resample with replacement
            indices = np.random.choice(n_samples, size=n_samples, replace=True)
            resampled_data = data.iloc[indices].reset_index(drop=True)
            try:
                b_res = self.fit(resampled_data, model_spec)
                for (from_c, to_c) in paths:
                    val = b_res["structural"]["path_coefficients"].get(to_c, {}).get(from_c, 0.0)
                    boot_paths[(from_c, to_c)].append(val)

                for (cid, iid) in boot_loadings.keys():
                    l_val = b_res["measurement"]["outer_loadings"].get(cid, {}).get(iid, 0.0)
                    w_val = b_res["measurement"]["outer_weights"].get(cid, {}).get(iid, 0.0)
                    boot_loadings[(cid, iid)].append(l_val)
                    boot_weights[(cid, iid)].append(w_val)
            except Exception:
                continue

        def _stats(original_val: float, sample_dist: List[float]):
            if not sample_dist:
                return {"original": original_val, "mean": original_val, "se": 0.0, "t_stat": 0.0, "p_value": 1.0, "ci_low": original_val, "ci_high": original_val}
            se = float(np.std(sample_dist, ddof=1))
            t_stat = float(original_val / se) if se > 1e-9 else 0.0
            p_val = float(2.0 * (1.0 - stats.norm.cdf(abs(t_stat))))
            ci_low = float(np.percentile(sample_dist, 2.5))
            ci_high = float(np.percentile(sample_dist, 97.5))
            return {
                "original": original_val,
                "mean": float(np.mean(sample_dist)),
                "se": se,
                "t_stat": t_stat,
                "p_value": p_val,
                "ci_low": ci_low,
                "ci_high": ci_high,
            }

        path_significance = []
        for (from_c, to_c), dist in boot_paths.items():
            orig = base_res["structural"]["path_coefficients"].get(to_c, {}).get(from_c, 0.0)
            st = _stats(orig, dist)
            st["from"] = from_c
            st["to"] = to_c
            path_significance.append(st)

        loading_significance = []
        for (cid, iid), dist in boot_loadings.items():
            orig = base_res["measurement"]["outer_loadings"].get(cid, {}).get(iid, 0.0)
            st = _stats(orig, dist)
            st["construct"] = cid
            st["indicator"] = iid
            loading_significance.append(st)

        weight_significance = []
        for (cid, iid), dist in boot_weights.items():
            orig = base_res["measurement"]["outer_weights"].get(cid, {}).get(iid, 0.0)
            st = _stats(orig, dist)
            st["construct"] = cid
            st["indicator"] = iid
            weight_significance.append(st)

        return {
            "n_boot": n_boot,
            "paths": path_significance,
            "loadings": loading_significance,
            "weights": weight_significance,
        }


def run_pls(
    data: pd.DataFrame,
    model_spec: Any,
    scheme: str = "path",
    bootstrap: bool = False,
    n_boot: int = 500,
) -> Dict[str, Any]:
    """Convenience entry point for PLS-SEM."""
    algo = PLSAlgorithm(scheme=scheme)
    res = algo.fit(data, model_spec)
    if bootstrap:
        res["significance"] = algo.bootstrap(data, model_spec, n_boot=n_boot)
    return res
