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

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
