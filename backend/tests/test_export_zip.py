import os
import tempfile
import shutil
import zipfile
import json
import pytest
import workspace_io
import project_io
from main import app
from fastapi.testclient import TestClient

client = TestClient(app)


def test_export_project_and_workspace_zip():
    temp_dir = tempfile.mkdtemp()
    try:
        ws_path = os.path.join(temp_dir, "MyWorkspace")
        workspace_io.create_workspace(ws_path, "My Workspace")

        # Create a study inside workspace
        study_path = os.path.join(ws_path, "TestStudy.pls")
        project_io.create_project(study_path, "Test Study")
        workspace_io.add_project_to_workspace(ws_path, "TestStudy.pls", "Test Study")

        # Save some data in project
        project_io.save_data(
            study_path,
            rows=[[1, 2], [3, 4]],
            columns=["colA", "colB"],
            dtypes=["int", "int"],
            dataset_name="Survey Data",
            dataset_id="ds_1",
        )

        # 1. Test export project as zip
        proj_zip_out = os.path.join(temp_dir, "export_proj.zip")
        res_path = project_io.export_project_zip(study_path, proj_zip_out)
        assert os.path.exists(res_path)
        assert zipfile.is_zipfile(res_path)

        with zipfile.ZipFile(res_path, "r") as zf:
            names = zf.namelist()
            assert "manifest.json" in names
            assert "TestStudy.pls" in names
            assert any(n.startswith("datasets/") and n.endswith(".csv") for n in names)
            manifest = json.loads(zf.read("manifest.json").decode("utf-8"))
            assert manifest["project_name"] == "Test Study"

        # 2. Test export workspace as zip via workspace_io
        ws_zip_out = os.path.join(temp_dir, "export_ws.zip")
        ws_res_path = workspace_io.export_workspace_zip(ws_path, ws_zip_out)
        assert os.path.exists(ws_res_path)
        assert zipfile.is_zipfile(ws_res_path)

        with zipfile.ZipFile(ws_res_path, "r") as zf:
            ws_names = zf.namelist()
            assert "workspace.json" in ws_names
            assert "TestStudy.pls" in ws_names

        # 3. Test /workspace/export-zip endpoint
        api_ws_zip_out = os.path.join(temp_dir, "api_export_ws.zip")
        res = client.post("/workspace/export-zip", json={"workspace_path": ws_path, "out_path": api_ws_zip_out})
        assert res.status_code == 200
        data = res.json()
        assert data.get("status") == "exported"
        assert os.path.exists(api_ws_zip_out)
        assert zipfile.is_zipfile(api_ws_zip_out)

        # 4. Test detection and import of workspace zip
        from smartpls_importer import detect_folder_type, detect_smartpls_folder
        det_ws = detect_folder_type(ws_zip_out)
        assert det_ws["kind"] == "cspls_workspace_zip"
        assert det_ws["valid"] is True

        import_target_dir = os.path.join(temp_dir, "ImportedWorkspaces")
        ws_import_res = workspace_io.import_workspace_zip(ws_zip_out, target_parent_folder=import_target_dir)
        assert ws_import_res["status"] == "imported"
        assert os.path.exists(ws_import_res["path"])
        assert len(ws_import_res["studies"]) == 1
        assert ws_import_res["studies"][0]["name"] == "Test Study"

        # 5. Test detection and import of project zip
        det_proj = detect_folder_type(proj_zip_out)
        assert det_proj["kind"] == "cspls_project"
        assert det_proj["valid"] is True
        assert det_proj["project_name"] == "TestStudy"

        det_smartpls_proj = detect_smartpls_folder(proj_zip_out)
        assert det_smartpls_proj["valid"] is True
        assert det_smartpls_proj["kind"] == "cspls_project"

        import_proj_ws = os.path.join(temp_dir, "TargetWsForProject")
        workspace_io.create_workspace(import_proj_ws, "Target Workspace")
        proj_import_res = client.post("/project/import-zip", json={
            "zip_path": proj_zip_out,
            "workspace_dir": import_proj_ws,
            "on_conflict": "rename"
        })
        assert proj_import_res.status_code == 200
        proj_data = proj_import_res.json()
        assert proj_data["status"] == "imported"
        assert len(proj_data["studies"]) == 1
        assert os.path.exists(proj_data["project_path"])

        # 6. Test import of raw .pls file
        pls_file_import_res = client.post("/project/import-file", json={
            "file_path": study_path,
            "workspace_dir": import_proj_ws,
            "on_conflict": "rename"
        })
        assert pls_file_import_res.status_code == 200
        pls_data = pls_file_import_res.json()
        assert pls_data["status"] == "imported"
        assert len(pls_data["studies"]) == 1

        # 7. Test invalid zip returns 'No compatible files found' without mentioning SmartPLS
        dummy_zip = os.path.join(temp_dir, "random_files.zip")
        with zipfile.ZipFile(dummy_zip, "w") as zf:
            zf.writestr("notes.txt", "Hello world")
        
        dummy_det = detect_smartpls_folder(dummy_zip)
        assert dummy_det["valid"] is False
        assert dummy_det["error"] == "No compatible files found"
        assert "SmartPLS" not in dummy_det["error"]

        dummy_folder_det = detect_folder_type(dummy_zip)
        assert dummy_folder_det["valid"] is False
        assert dummy_folder_det["error"] == "No compatible files found"
        assert "SmartPLS" not in dummy_folder_det["error"]

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
