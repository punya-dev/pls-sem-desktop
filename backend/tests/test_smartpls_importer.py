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
    detect_folder_type,
    import_smartpls_workspace,
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
            self.assertEqual(len(res["studies"]), 1)
            self.assertEqual(len(res["models"]), 8)

            # Single unified study contains all datasets
            comp_study = res["studies"][0]
            self.assertIsNotNone(comp_study)
            self.assertEqual(comp_study["datasets_count"], 3)

            import sqlite3
            conn = sqlite3.connect(comp_study["path"])
            df = pd.read_sql_query("SELECT * FROM raw_data", conn)
            self.assertEqual(len(df), 344)

            # Check that datasets table contains all 3 datasets
            datasets_df = pd.read_sql_query("SELECT * FROM datasets", conn)
            self.assertEqual(len(datasets_df), 3)

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
            self.assertEqual(len(res["studies"]), 1)
            self.assertEqual(len(res["models"]), 8)
            self.assertEqual(res["studies"][0]["datasets_count"], 3)
        finally:
            if os.path.exists(temp_zip):
                os.remove(temp_zip)
            shutil.rmtree(temp_ws, ignore_errors=True)

    def test_detect_folder_type(self):
        # 1. Project folder
        res_proj = detect_folder_type(self.sample_dir)
        self.assertEqual(res_proj["kind"], "smartpls_project")
        self.assertEqual(res_proj["models_count"], 8)

        # 2. StatSEM Workspace
        temp_cspls_ws = tempfile.mkdtemp(prefix="cspls_ws_test_")
        try:
            with open(os.path.join(temp_cspls_ws, "workspace.json"), "w") as f:
                json.dump({"name": "Test StatSEM WS", "projects": []}, f)
            res_cspls = detect_folder_type(temp_cspls_ws)
            self.assertEqual(res_cspls["kind"], "cspls_workspace")
            self.assertEqual(res_cspls["name"], "Test StatSEM WS")
        finally:
            shutil.rmtree(temp_cspls_ws, ignore_errors=True)

        # 3. SmartPLS Workspace with subfolder
        temp_spls_ws = tempfile.mkdtemp(prefix="spls_ws_test_")
        try:
            sub_proj_dir = os.path.join(temp_spls_ws, "Sub Project")
            os.makedirs(sub_proj_dir, exist_ok=True)
            # Copy one model file into sub_proj_dir
            for f in os.listdir(self.sample_dir):
                if f.endswith(".splsm") or f.endswith(".txt"):
                    shutil.copy(os.path.join(self.sample_dir, f), os.path.join(sub_proj_dir, f))
                    break
            res_spls_ws = detect_folder_type(temp_spls_ws)
            self.assertEqual(res_spls_ws["kind"], "smartpls_workspace")
            self.assertEqual(res_spls_ws["projects_count"], 1)
        finally:
            shutil.rmtree(temp_spls_ws, ignore_errors=True)

    def test_formative_indicators_in_extended_model(self):
        model_file = os.path.join(self.sample_dir, "2 Extended model.splsm")
        with open(model_file, "r") as f:
            encrypted = f.read()

        raw_json = decrypt_smartpls_content(encrypted)
        model_data = json.loads(raw_json)
        spec, layout = convert_smartpls_model(model_data)

        # 8 constructs in 2 Extended model
        self.assertEqual(len(spec["constructs"]), 8)

        construct_map = {c["name"]: c for c in spec["constructs"]}
        # Formative constructs
        self.assertIn("ATTR", construct_map)
        self.assertEqual(construct_map["ATTR"]["type"], "formative")
        self.assertEqual(construct_map["ATTR"]["outer_mode"], "B")
        self.assertEqual(len(construct_map["ATTR"]["indicators"]), 3)

        self.assertIn("QUAL", construct_map)
        self.assertEqual(construct_map["QUAL"]["type"], "formative")
        self.assertEqual(construct_map["QUAL"]["outer_mode"], "B")
        self.assertEqual(len(construct_map["QUAL"]["indicators"]), 8)

        self.assertIn("PERF", construct_map)
        self.assertEqual(construct_map["PERF"]["type"], "formative")
        self.assertEqual(construct_map["PERF"]["outer_mode"], "B")
        self.assertEqual(len(construct_map["PERF"]["indicators"]), 5)

        self.assertIn("CSOR", construct_map)
        self.assertEqual(construct_map["CSOR"]["type"], "formative")
        self.assertEqual(construct_map["CSOR"]["outer_mode"], "B")
        self.assertEqual(len(construct_map["CSOR"]["indicators"]), 5)

        # Reflective constructs
        self.assertEqual(construct_map["COMP"]["type"], "reflective")
        self.assertEqual(construct_map["COMP"]["outer_mode"], "A")
        self.assertEqual(len(construct_map["COMP"]["indicators"]), 3)

        # Verify all manifest nodes in layout have parentId assigned (no orphaned floating indicators)
        manifest_nodes = [n for n in layout["nodes"] if n.get("isLatent") is False and not n.get("isCopula")]
        for mn in manifest_nodes:
            self.assertIsNotNone(mn.get("parentId"), f"Manifest node {mn.get('id')} ({mn.get('label')}) has no parentId")
        self.assertEqual(len(manifest_nodes), 31)

        # Run PLS algorithm on Complete data with this model spec
        data_file = os.path.join(self.sample_dir, "Complete data.txt")
        df, _ = parse_smartpls_dataset(data_file)
        algo = PLSAlgorithm()
        fit_res = algo.fit(df, spec)
        self.assertTrue(fit_res["converged"])
        cusl_id = construct_map["CUSL"]["id"]
        self.assertIn(cusl_id, fit_res["r2"])
        self.assertAlmostEqual(fit_res["r2"][cusl_id], 0.562, places=2)

    def test_import_smartpls_workspace(self):
        temp_spls_ws = tempfile.mkdtemp(prefix="spls_ws_import_test_")
        try:
            # Create a project subfolder
            sub_proj = os.path.join(temp_spls_ws, "Example - Corporate reputation (primer)")
            shutil.copytree(self.sample_dir, sub_proj)

            res = import_smartpls_workspace(temp_spls_ws)
            self.assertEqual(res["status"], "success")
            self.assertTrue(os.path.exists(os.path.join(temp_spls_ws, "workspace.json")))
            self.assertTrue(len(res["studies"]) >= 1)
            self.assertTrue(len(res["models"]) >= 1)
        finally:
            shutil.rmtree(temp_spls_ws, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()

