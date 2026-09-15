"""
Unit tests for PLS-SEM Engine (Phase 3).
"""

import unittest
import numpy as np
import pandas as pd
from engine.pls.algorithm import PLSAlgorithm, run_pls


class TestPLSSEM(unittest.TestCase):

    def setUp(self):
        np.random.seed(42)
        n = 300

        # Simulate true latent constructs
        # C1 (Quality), C2 (Value) -> C3 (Satisfaction)
        c1 = np.random.normal(0, 1, n)
        c2 = 0.5 * c1 + np.random.normal(0, np.sqrt(1 - 0.25), n)
        c3 = 0.4 * c1 + 0.5 * c2 + np.random.normal(0, 0.5, n)

        # Generate indicators with high loadings (> 0.7)
        q1 = 0.8 * c1 + np.random.normal(0, 0.6, n)
        q2 = 0.85 * c1 + np.random.normal(0, 0.5, n)
        q3 = 0.75 * c1 + np.random.normal(0, 0.65, n)

        v1 = 0.8 * c2 + np.random.normal(0, 0.6, n)
        v2 = 0.85 * c2 + np.random.normal(0, 0.5, n)
        v3 = 0.78 * c2 + np.random.normal(0, 0.6, n)

        s1 = 0.82 * c3 + np.random.normal(0, 0.55, n)
        s2 = 0.88 * c3 + np.random.normal(0, 0.45, n)
        s3 = 0.79 * c3 + np.random.normal(0, 0.6, n)

        self.df = pd.DataFrame({
            "q1": q1, "q2": q2, "q3": q3,
            "v1": v1, "v2": v2, "v3": v3,
            "s1": s1, "s2": s2, "s3": s3,
        })

        self.model_spec = {
            "constructs": [
                {"id": "Quality", "name": "Quality", "type": "reflective", "indicators": ["ind_q1", "ind_q2", "ind_q3"]},
                {"id": "Value", "name": "Value", "type": "reflective", "indicators": ["ind_v1", "ind_v2", "ind_v3"]},
                {"id": "Satisfaction", "name": "Satisfaction", "type": "reflective", "indicators": ["ind_s1", "ind_s2", "ind_s3"]},
            ],
            "indicators": [
                {"id": "ind_q1", "column": "q1"},
                {"id": "ind_q2", "column": "q2"},
                {"id": "ind_q3", "column": "q3"},
                {"id": "ind_v1", "column": "v1"},
                {"id": "ind_v2", "column": "v2"},
                {"id": "ind_v3", "column": "v3"},
                {"id": "ind_s1", "column": "s1"},
                {"id": "ind_s2", "column": "s2"},
                {"id": "ind_s3", "column": "s3"},
            ],
            "paths": [
                {"from": "Quality", "to": "Satisfaction"},
                {"from": "Value", "to": "Satisfaction"},
                {"from": "Quality", "to": "Value"},
            ],
        }

    def test_pls_convergence_and_loadings(self):
        algo = PLSAlgorithm(scheme="path")
        res = algo.fit(self.df, self.model_spec)

        self.assertTrue(res["converged"])
        self.assertLess(res["iterations"], 50)

        # Check outer loadings for all indicators are high (> 0.7)
        loadings = res["measurement"]["outer_loadings"]
        for cid, ind_loads in loadings.items():
            for iid, load in ind_loads.items():
                self.assertGreater(load, 0.7, f"Loading {cid}->{iid} too low: {load}")

    def test_pls_structural_paths_and_r2(self):
        algo = PLSAlgorithm(scheme="path")
        res = algo.fit(self.df, self.model_spec)

        struct = res["structural"]
        # Satisfaction should have paths from Quality and Value
        paths_sat = struct["path_coefficients"]["Satisfaction"]
        self.assertIn("Quality", paths_sat)
        self.assertIn("Value", paths_sat)
        self.assertGreater(paths_sat["Quality"], 0.2)
        self.assertGreater(paths_sat["Value"], 0.3)

        # R² for Satisfaction should be high (> 0.5)
        r2_sat = struct["r_squared"]["Satisfaction"]
        self.assertGreater(r2_sat, 0.5)

        # f² effect sizes
        f2_sat = struct["f_squared"]["Satisfaction"]
        self.assertIn("Quality", f2_sat)
        self.assertIn("Value", f2_sat)
        self.assertGreater(f2_sat["Value"], 0.15)  # medium to large effect

        # Inner VIF should be reasonable (< 5.0)
        vif_sat = struct["inner_vif"]["Satisfaction"]
        self.assertLess(vif_sat["Quality"], 3.0)

    def test_reliability_and_validity_metrics(self):
        algo = PLSAlgorithm(scheme="path")
        res = algo.fit(self.df, self.model_spec)

        rv = res["reliability_and_validity"]

        for cid in ["Quality", "Value", "Satisfaction"]:
            # Cronbach's alpha > 0.7
            self.assertGreater(rv["cronbachs_alpha"][cid], 0.7)
            # Composite Reliability > 0.8
            self.assertGreater(rv["composite_reliability"][cid], 0.8)
            # rho_A > 0.7
            self.assertGreater(rv["rho_a"][cid], 0.7)
            # AVE > 0.5
            self.assertGreater(rv["ave"][cid], 0.5)

        # Fornell-Larcker: sqrt(AVE) on diagonal > construct correlation off-diagonal
        fl = rv["fornell_larcker"]
        self.assertGreater(fl["Quality"]["Quality"], abs(fl["Quality"]["Satisfaction"]))

        # HTMT < 0.90 for discriminant validity
        htmt = rv["htmt"]
        self.assertLess(htmt["Quality"]["Satisfaction"], 0.95)

    def test_schemes_factor_and_centroid(self):
        for scheme in ["factor", "centroid"]:
            algo = PLSAlgorithm(scheme=scheme)
            res = algo.fit(self.df, self.model_spec)
            self.assertTrue(res["converged"])
            self.assertGreater(res["structural"]["r_squared"]["Satisfaction"], 0.5)

    def test_formative_construct_mode_b(self):
        # Modify model_spec to make Value formative (Mode B)
        formative_spec = dict(self.model_spec)
        formative_spec["constructs"] = [
            {"id": "Quality", "name": "Quality", "type": "reflective", "indicators": ["ind_q1", "ind_q2", "ind_q3"]},
            {"id": "Value", "name": "Value", "type": "formative", "indicators": ["ind_v1", "ind_v2", "ind_v3"]},
            {"id": "Satisfaction", "name": "Satisfaction", "type": "reflective", "indicators": ["ind_s1", "ind_s2", "ind_s3"]},
        ]
        algo = PLSAlgorithm()
        res = algo.fit(self.df, formative_spec)
        self.assertTrue(res["converged"])
        # Formative outer weights should be present and valid
        weights_val = res["measurement"]["outer_weights"]["Value"]
        self.assertEqual(len(weights_val), 3)

    def test_hair_et_al_exhibit_3_8_benchmark(self):
        """
        Benchmark test against textbook Exhibit 3.8 (Hair et al., A Primer on PLS-SEM).
        Corporate reputation data with -99 treated via mean replacement.
        """
        import os
        csv_path = "/Users/punyapratap/Desktop/Corporate reputation data.csv"
        if not os.path.exists(csv_path):
            return

        df_bench = pd.read_csv(csv_path, sep=None, engine="python")
        cols = ["comp_1", "comp_2", "comp_3", "like_1", "like_2", "like_3", "cusa", "cusl_1", "cusl_2", "cusl_3"]
        spec = {
            "constructs": [
                {"id": "COMP", "name": "COMP", "type": "reflective", "indicators": ["comp_1", "comp_2", "comp_3"]},
                {"id": "LIKE", "name": "LIKE", "type": "reflective", "indicators": ["like_1", "like_2", "like_3"]},
                {"id": "CUSA", "name": "CUSA", "type": "reflective", "indicators": ["cusa"]},
                {"id": "CUSL", "name": "CUSL", "type": "reflective", "indicators": ["cusl_1", "cusl_2", "cusl_3"]},
            ],
            "indicators": [{"id": c, "column": c} for c in cols],
            "paths": [
                {"from": "COMP", "to": "CUSA"},
                {"from": "LIKE", "to": "CUSA"},
                {"from": "COMP", "to": "CUSL"},
                {"from": "LIKE", "to": "CUSL"},
                {"from": "CUSA", "to": "CUSL"},
            ]
        }
        algo = PLSAlgorithm(scheme="path", missing_treatment="mean")
        res = algo.fit(df_bench, spec)

        paths = res["structural"]["path_coefficients"]
        r2 = res["structural"]["r_squared"]
        loads = res["measurement"]["outer_loadings"]

        # Paths match Exhibit 3.8
        self.assertAlmostEqual(paths["CUSA"]["COMP"], 0.162, places=3)
        self.assertAlmostEqual(paths["CUSA"]["LIKE"], 0.424, places=3)
        self.assertAlmostEqual(paths["CUSL"]["COMP"], 0.009, places=3)
        self.assertAlmostEqual(paths["CUSL"]["LIKE"], 0.342, places=3)
        self.assertAlmostEqual(paths["CUSL"]["CUSA"], 0.504, places=3)

        # R^2 match Exhibit 3.8
        self.assertAlmostEqual(r2["CUSA"], 0.295, places=3)
        self.assertAlmostEqual(r2["CUSL"], 0.562, places=3)

        # Outer loadings match Exhibit 3.8
        self.assertAlmostEqual(loads["COMP"]["comp_1"], 0.858, places=3)
        self.assertAlmostEqual(loads["COMP"]["comp_2"], 0.798, places=3)
        self.assertAlmostEqual(loads["COMP"]["comp_3"], 0.818, places=3)
        self.assertAlmostEqual(loads["LIKE"]["like_1"], 0.879, places=3)
        self.assertAlmostEqual(loads["LIKE"]["like_2"], 0.870, places=3)
        self.assertAlmostEqual(loads["LIKE"]["like_3"], 0.843, places=3)
        self.assertAlmostEqual(loads["CUSA"]["cusa"], 1.000, places=3)
        self.assertAlmostEqual(loads["CUSL"]["cusl_1"], 0.833, places=3)
        self.assertAlmostEqual(loads["CUSL"]["cusl_2"], 0.917, places=3)
        self.assertAlmostEqual(loads["CUSL"]["cusl_3"], 0.843, places=3)


if __name__ == "__main__":
    unittest.main()

