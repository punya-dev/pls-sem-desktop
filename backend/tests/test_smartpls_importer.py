import os
import sys
import shutil
import tempfile
import unittest
import json
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from smartpls_importer import (
    decrypt_smartpls_content,
    parse_smartpls_dataset,
    convert_smartpls_model,
    detect_smartpls_folder,
    import_smartpls_folder,
)
from engine.pls.algorithm import PLSAlgorithm


class TestSmartPLSImporter(unittest.TestCase):
    def setUp(self):
        self.sample_dir = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..", "Example - Corporate reputation (primer)")
        )

    def test_detection(self):
        result = detect_smartpls_folder(self.sample_dir)
        self.assertTrue(result["valid"])
        self.assertEqual(result["models_count"], 8)
        self.assertEqual(result["datasets_count"], 3)
        self.assertIn("1 Simple model.splsm", [m["file"] for m in result["models"]])

    def test_decryption_and_conversion(self):
        model_file = os.path.join(self.sample_dir, "1 Simple model.splsm")
        with open(model_file, "r") as f:
            encrypted = f.read()

        raw_json = decrypt_smartpls_content(encrypted)
        self.assertIn("LATENT_VARIABLE", raw_json)

        import json
        model_data = json.loads(raw_json)
        spec, layout = convert_smartpls_model(model_data)

        self.assertEqual(len(spec["constructs"]), 4)  # COMP, CUSA, CUSL, LIKE
        self.assertEqual(len(spec["paths"]), 5)
        self.assertGreater(len(layout["nodes"]), 0)

    def test_dataset_parsing(self):
        data_file = os.path.join(self.sample_dir, "Complete data.txt")
        df, dataset_name = parse_smartpls_dataset(data_file)
        self.assertEqual(len(df), 344)
        self.assertEqual(dataset_name, "Complete data")
        self.assertIn("cusa", df.columns)
        self.assertIn("cusl_1", df.columns)

    def test_end_to_end_import_and_calculation(self):
        temp_ws = tempfile.mkdtemp(prefix="pls_smartpls_test_")
        try:
            res = import_smartpls_folder(self.sample_dir, target_workspace_folder=temp_ws, workspace_name="Test Import")
            self.assertEqual(res["status"], "success")
            self.assertEqual(len(res["studies"]), 3)
            self.assertEqual(len(res["models"]), 8)

            # Find Complete data study
            comp_study = next((s for s in res["studies"] if "Complete_data.pls" in s["path"]), None)
            self.assertIsNotNone(comp_study)

            import sqlite3
            conn = sqlite3.connect(comp_study["path"])
            df = pd.read_sql_query("SELECT * FROM raw_data", conn)
            self.assertEqual(len(df), 344)

            # Load the first model spec and fit
            cur = conn.cursor()
            cur.execute("SELECT spec_json FROM model_spec WHERE model_key = ?", (res["models"][0]["id"],))
            row = cur.fetchone()
            self.assertIsNotNone(row)
            spec_dict = json.loads(row[0])

            algo = PLSAlgorithm()
            fit_res = algo.fit(df, spec_dict)
            self.assertTrue(fit_res["converged"])
            self.assertEqual(fit_res["iterations"], 5)
        finally:
            shutil.rmtree(temp_ws, ignore_errors=True)

    def test_zip_detection_and_import(self):
        import zipfile
        temp_zip = os.path.join(tempfile.gettempdir(), f"smartpls_test_{os.getpid()}.zip")
        temp_ws = tempfile.mkdtemp(prefix="pls_zip_test_")
        try:
            with zipfile.ZipFile(temp_zip, "w") as zf:
                for root, dirs, files in os.walk(self.sample_dir):
                    for f in files:
                        full = os.path.join(root, f)
                        rel = os.path.relpath(full, self.sample_dir)
                        zf.write(full, rel)

            det = detect_smartpls_folder(temp_zip)
            self.assertTrue(det["valid"])
            self.assertTrue(det["is_zip"])
            self.assertEqual(det["models_count"], 8)
            self.assertEqual(det["datasets_count"], 3)

            res = import_smartpls_folder(temp_zip, target_workspace_folder=temp_ws, workspace_name="Zip Test WS")
            self.assertEqual(res["status"], "success")
            self.assertEqual(len(res["studies"]), 3)
            self.assertEqual(len(res["models"]), 8)
        finally:
            if os.path.exists(temp_zip):
                os.remove(temp_zip)
            shutil.rmtree(temp_ws, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
