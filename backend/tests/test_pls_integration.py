"""
Integration tests for PLS-SEM endpoint with project database.
"""

import unittest
import os
import sys
import tempfile
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import run_project_pls, load_project_results
from model_spec import ModelSpec, Construct, Indicator, Path, RunPlsRequest
import project_io


class TestPLSIntegration(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.project_path = os.path.join(self.temp_dir.name, "test_study.pls")
        project_io.create_project(self.project_path, "Test Study")

        # Generate realistic dataset
        np.random.seed(42)
        n = 150
        c1 = np.random.normal(0, 1, n)
        c2 = 0.6 * c1 + np.random.normal(0, 0.5, n)

        q1 = 0.8 * c1 + np.random.normal(0, 0.4, n)
        q2 = 0.85 * c1 + np.random.normal(0, 0.35, n)
        s1 = 0.8 * c2 + np.random.normal(0, 0.4, n)
        s2 = 0.85 * c2 + np.random.normal(0, 0.35, n)

        df = pd.DataFrame({"q1": q1, "q2": q2, "s1": s1, "s2": s2})
        project_io.save_data(
            self.project_path,
            df.values.tolist(),
            list(df.columns),
            list(df.dtypes.astype(str)),
            dataset_name="sample.csv",
        )

        self.spec = ModelSpec(
            constructs=[
                Construct(id="Quality", name="Quality", indicators=["iq1", "iq2"]),
                Construct(id="Satisfaction", name="Satisfaction", indicators=["is1", "is2"]),
            ],
            indicators=[
                Indicator(id="iq1", column="q1"),
                Indicator(id="iq2", column="q2"),
                Indicator(id="is1", column="s1"),
                Indicator(id="is2", column="s2"),
            ],
            paths=[
                Path(from_node="Quality", to_node="Satisfaction"),
            ],
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_run_project_pls_success(self):
        req = RunPlsRequest(
            project_path=self.project_path,
            spec=self.spec,
            scheme="path",
        )
        res = run_project_pls(req)

        self.assertNotIn("error", res)
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["algorithm"], "pls")

        results = res["results"]
        self.assertTrue(results["converged"])
        self.assertIn("structural", results)
        self.assertIn("measurement", results)
        self.assertIn("reliability_and_validity", results)

        # Path coefficient Quality -> Satisfaction
        path_val = results["structural"]["path_coefficients"]["Satisfaction"]["Quality"]
        self.assertGreater(path_val, 0.5)

        # R² for Satisfaction
        r2 = results["structural"]["r_squared"]["Satisfaction"]
        self.assertGreater(r2, 0.3)

        # Loadings
        loadings = results["measurement"]["outer_loadings"]
        self.assertGreater(loadings["Quality"]["iq1"], 0.7)
        self.assertGreater(loadings["Satisfaction"]["is1"], 0.7)

        # Verify results were persisted in sqlite
        loaded = load_project_results(self.project_path, "pls")
        self.assertIsNotNone(loaded["results"])
        self.assertEqual(loaded["algorithm"], "pls")
        self.assertAlmostEqual(
            loaded["results"]["structural"]["path_coefficients"]["Satisfaction"]["Quality"],
            path_val,
            places=5,
        )

    def test_run_project_pls_with_saved_spec(self):
        # Save spec first
        project_io.save_model_spec(self.project_path, self.spec.model_dump(by_alias=True))

        # Call run without passing spec in request
        req = RunPlsRequest(project_path=self.project_path)
        res = run_project_pls(req)

        self.assertNotIn("error", res)
        self.assertEqual(res["status"], "success")
        self.assertTrue(res["results"]["converged"])

    def test_run_project_pls_with_provided_data_fallback(self):
        # Create fresh project with no data in database
        empty_project = os.path.join(self.temp_dir.name, "empty_study.pls")
        project_io.create_project(empty_project, "Empty Study")

        # Calling without data should fail
        req_fail = RunPlsRequest(project_path=empty_project, spec=self.spec)
        res_fail = run_project_pls(req_fail)
        self.assertIn("error", res_fail)
        self.assertIn("No dataset found", res_fail["error"])

        # Calling with columns and rows in request should auto-save and succeed
        np.random.seed(42)
        n = 50
        df = pd.DataFrame({
            "q1": np.random.normal(0, 1, n),
            "q2": np.random.normal(0, 1, n),
            "s1": np.random.normal(0, 1, n),
            "s2": np.random.normal(0, 1, n),
        })
        req_success = RunPlsRequest(
            project_path=empty_project,
            spec=self.spec,
            columns=list(df.columns),
            rows=df.values.tolist(),
            dataset_name="in_memory.csv",
        )
        res_success = run_project_pls(req_success)
        self.assertNotIn("error", res_success)
        self.assertEqual(res_success["status"], "success")
        self.assertTrue(res_success["results"]["converged"])


if __name__ == "__main__":
    unittest.main()
