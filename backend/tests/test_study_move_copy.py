import os
import tempfile
import shutil
import pytest
import workspace_io
import project_io

def test_move_and_duplicate_study_across_workspaces():
    temp_dir = tempfile.mkdtemp()
    try:
        ws_a_path = os.path.join(temp_dir, "WorkspaceA")
        ws_b_path = os.path.join(temp_dir, "WorkspaceB")
        
        workspace_io.create_workspace(ws_a_path, "Workspace A")
        workspace_io.create_workspace(ws_b_path, "Workspace B")
        
        # Create a study in Workspace A
        study_filename = "MyStudy.pls"
        study_path = os.path.join(ws_a_path, study_filename)
        project_io.create_project(study_path, "My Study")
        workspace_io.add_project_to_workspace(ws_a_path, study_filename, "My Study")
        
        ws_a_data = workspace_io.load_workspace(ws_a_path)
        assert len(ws_a_data["projects"]) == 1
        assert ws_a_data["projects"][0]["name"] == "My Study"
        
        # Test 1: Duplicate into Workspace B
        dup_res = project_io.duplicate_project(ws_b_path, study_path, "My Study Copy")
        assert dup_res["status"] == "duplicated"
        assert os.path.exists(dup_res["project_path"])
        assert os.path.dirname(dup_res["project_path"]) == ws_b_path
        
        ws_b_data = workspace_io.load_workspace(ws_b_path)
        assert len(ws_b_data["projects"]) == 1
        assert ws_b_data["projects"][0]["name"] == "My Study Copy"
        
        # Original study still exists in Workspace A
        assert os.path.exists(study_path)
        ws_a_data = workspace_io.load_workspace(ws_a_path)
        assert len(ws_a_data["projects"]) == 1
        
        # Test 2: Move original study from Workspace A to Workspace B
        move_res = project_io.move_project(ws_a_path, ws_b_path, study_path, "My Study")
        assert move_res["status"] == "moved"
        assert os.path.exists(move_res["project_path"])
        assert os.path.dirname(move_res["project_path"]) == ws_b_path
        
        # Original file removed from Workspace A
        assert not os.path.exists(study_path)
        
        # Workspace A workspace.json updated
        ws_a_data = workspace_io.load_workspace(ws_a_path)
        assert len(ws_a_data["projects"]) == 0
        
        # Workspace B workspace.json has both projects
        ws_b_data = workspace_io.load_workspace(ws_b_path)
        assert len(ws_b_data["projects"]) == 2
        names = [p["name"] for p in ws_b_data["projects"]]
        assert "My Study Copy" in names
        assert "My Study" in names
        
        # Test 3: Attempt to move to same workspace should fail
        with pytest.raises(ValueError):
            project_io.move_project(ws_b_path, ws_b_path, move_res["project_path"], "My Study")
            
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
