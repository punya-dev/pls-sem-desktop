"""
Unit tests for CB-SEM Engine (Phase 6).
"""

import unittest
import numpy as np
import pandas as pd
from engine.cbsem.algorithm import CBSEMAlgorithm, run_cbsem


class TestCBSEM(unittest.TestCase):

    def setUp(self):
        np.random.seed(123)
        n = 500

        # Simulate true latent constructs for CB-SEM:
        # F1 (Exogenous), F2 (Endogenous)
        # F2 = 0.6 * F1 + error
        f1 = np.random.normal(0, 1, n)
        f2 = 0.6 * f1 + np.random.normal(0, np.sqrt(1 - 0.36), n)

        # Indicators for F1:
        # x1: marker (loading 1.0)
        # x2: loading 0.8
        # x3: loading 0.9
        x1 = 1.0 * f1 + np.random.normal(0, 0.5, n)
        x2 = 0.8 * f1 + np.random.normal(0, 0.5, n)
        x3 = 0.9 * f1 + np.random.normal(0, 0.5, n)

        # Indicators for F2:
        # y1: marker (loading 1.0)
        # y2: loading 0.85
        # y3: loading 0.75
        y1 = 1.0 * f2 + np.random.normal(0, 0.5, n)
        y2 = 0.85 * f2 + np.random.normal(0, 0.5, n)
        y3 = 0.75 * f2 + np.random.normal(0, 0.5, n)

        self.df = pd.DataFrame({
            "x1": x1, "x2": x2, "x3": x3,
            "y1": y1, "y2": y2, "y3": y3,
        })

        self.model_spec = {
            "constructs": [
                {"id": "F1", "name": "Factor 1", "type": "reflective", "indicators": ["x1", "x2", "x3"]},
                {"id": "F2", "name": "Factor 2", "type": "reflective", "indicators": ["y1", "y2", "y3"]},
            ],
            "indicators": [
                {"id": "x1", "column": "x1"},
                {"id": "x2", "column": "x2"},
                {"id": "x3", "column": "x3"},
                {"id": "y1", "column": "y1"},
                {"id": "y2", "column": "y2"},
                {"id": "y3", "column": "y3"},
            ],
            "paths": [
                {"from": "F1", "to": "F2"},
            ],
        }

    def test_cbsem_fit_and_convergence(self):
        algo = CBSEMAlgorithm()
        res = algo.fit(self.df, self.model_spec)

        self.assertTrue(res["converged"], f"CB-SEM failed to converge: {res}")
        self.assertGreater(res["degrees_of_freedom"], 0)

        # 6 indicators => 6*7/2 = 21 sample moments
        # Parameters:
        # - Free loadings: 2 (x2, x3) + 2 (y2, y3) = 4
        # - Structural path: 1 (F1 -> F2)
        # - Indicator error variances: 6
        # - Latent variances: 2
        # Total parameters = 13
        # df = 21 - 13 = 8
        self.assertEqual(res["degrees_of_freedom"], 8)

    def test_cbsem_fit_indices(self):
        algo = CBSEMAlgorithm()
        res = algo.fit(self.df, self.model_spec)

        fits = res["fit_indices"]
        # Model was simulated from this exact structure, so fit should be very good:
        # CFI > 0.95, TLI > 0.95, RMSEA < 0.08, SRMR < 0.08
        self.assertGreater(fits["cfi"], 0.95, f"CFI too low: {fits['cfi']}")
        self.assertGreater(fits["tli"], 0.95, f"TLI too low: {fits['tli']}")
        self.assertLess(fits["rmsea"], 0.08, f"RMSEA too high: {fits['rmsea']}")
        self.assertLess(fits["srmr"], 0.08, f"SRMR too high: {fits['srmr']}")
        self.assertGreater(fits["aic"], 0)
        self.assertGreater(fits["bic"], 0)

    def test_cbsem_parameter_estimates(self):
        algo = CBSEMAlgorithm()
        res = algo.fit(self.df, self.model_spec)

        # Check structural path F1 -> F2 estimate is close to true 0.6
        paths = res["structural_paths"]
        path_f1_f2 = paths["F2"]["F1"]
        self.assertAlmostEqual(path_f1_f2["estimate"], 0.6, delta=0.15)
        self.assertGreater(path_f1_f2["z_score"], 3.0)
        self.assertLess(path_f1_f2["p_value"], 0.01)

        # Check loadings: x2 true is 0.8, x3 true is 0.9
        loadings = res["measurement_loadings"]
        load_x2 = loadings["F1"]["x2"]
        load_x3 = loadings["F1"]["x3"]
        self.assertAlmostEqual(load_x2["estimate"], 0.8, delta=0.15)
        self.assertAlmostEqual(load_x3["estimate"], 0.9, delta=0.15)

        # Standardized loadings should be reasonable (> 0.6)
        self.assertGreater(load_x2["std_estimate"], 0.6)
        self.assertGreater(load_x3["std_estimate"], 0.6)

    def test_under_identified_model_handling(self):
        # 1 factor with only 2 indicators and free loading, no constraints = under-identified (df < 0)
        bad_spec = {
            "constructs": [
                {"id": "F1", "name": "Factor 1", "type": "reflective", "indicators": ["x1"]},
            ],
            "indicators": [
                {"id": "x1", "column": "x1"},
            ],
            "paths": [],
        }
        algo = CBSEMAlgorithm()
        res = algo.fit(self.df, bad_spec)
        # 1 indicator -> 1 moment. Parameters: 1 error var + 1 latent var = 2 -> df = -1
        self.assertFalse(res["converged"])
        self.assertIn("error", res)
        self.assertLess(res["df"], 0)

    def test_implied_covariance_matrix(self):
        algo = CBSEMAlgorithm()
        res = algo.fit(self.df, self.model_spec)

        sigma = res["implied_covariance"].to_numpy()
        s = res["sample_covariance"].to_numpy()
        # Matrix norm difference should be small for a well-fitting model
        rel_diff = np.linalg.norm(sigma - s) / np.linalg.norm(s)
        self.assertLess(rel_diff, 0.15)


if __name__ == "__main__":
    unittest.main()
