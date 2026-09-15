import pytest
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import validate_model, save_project_model, load_project_model
from model_spec import ModelSpec, Construct, Indicator, Path, ConstructType, ValidateModelRequest, SaveModelRequest
from model_validator import validate_model_spec, detect_cycles
import project_io



def test_model_spec_pydantic_parsing():
    raw_spec = {
        "constructs": [
            {"id": "C1", "name": "Satisfaction", "type": "reflective", "indicators": ["Q1", "Q2", "Q3"]},
            {"id": "C2", "name": "Loyalty", "type": "formative", "indicators": ["Q4"]}
        ],
        "indicators": [
            {"id": "Q1", "column": "survey_q1"},
            {"id": "Q2", "column": "survey_q2"},
            {"id": "Q3", "column": "survey_q3"},
            {"id": "Q4", "column": "survey_q4"}
        ],
        "paths": [
            {"from": "C1", "to": "C2"}
        ]
    }
    spec = ModelSpec.model_validate(raw_spec)
    assert len(spec.constructs) == 2
    assert spec.constructs[0].type == ConstructType.REFLECTIVE
    assert spec.constructs[1].type == ConstructType.FORMATIVE
    assert len(spec.paths) == 1
    assert spec.paths[0].from_node == "C1"
    assert spec.paths[0].to_node == "C2"

    dumped = spec.model_dump(by_alias=True)
    assert dumped["paths"][0]["from"] == "C1"
    assert dumped["paths"][0]["to"] == "C2"


def test_validator_valid_spec():
    spec = ModelSpec(
        constructs=[
            Construct(id="C1", name="Satisfaction", indicators=["Q1", "Q2"]),
            Construct(id="C2", name="Loyalty", indicators=["Q3", "Q4"])
        ],
        indicators=[
            Indicator(id="Q1", column="col_q1"),
            Indicator(id="Q2", column="col_q2"),
            Indicator(id="Q3", column="col_q3"),
            Indicator(id="Q4", column="col_q4")
        ],
        paths=[
            Path(from_node="C1", to_node="C2")
        ]
    )
    dataset_cols = ["col_q1", "col_q2", "col_q3", "col_q4", "col_other"]
    result = validate_model_spec(spec, dataset_columns=dataset_cols)
    assert result.is_valid is True
    assert len(result.errors) == 0
    assert result.exogenous_constructs == ["C1"]
    assert result.endogenous_constructs == ["C2"]
    assert result.isolated_constructs == []


def test_validator_detects_cycles():
    # 2-node cycle: C1 -> C2 -> C1
    spec_2node = ModelSpec(
        constructs=[
            Construct(id="C1", name="Construct 1", indicators=["Q1"]),
            Construct(id="C2", name="Construct 2", indicators=["Q2"])
        ],
        indicators=[
            Indicator(id="Q1", column="q1"),
            Indicator(id="Q2", column="q2")
        ],
        paths=[
            Path(from_node="C1", to_node="C2"),
            Path(from_node="C2", to_node="C1")
        ]
    )
    res_2 = validate_model_spec(spec_2node)
    assert res_2.is_valid is False
    assert any("Cycle detected" in err for err in res_2.errors)

    # 3-node cycle: A -> B -> C -> A
    spec_3node = ModelSpec(
        constructs=[
            Construct(id="A", name="A", indicators=["Q1"]),
            Construct(id="B", name="B", indicators=["Q2"]),
            Construct(id="C", name="C", indicators=["Q3"])
        ],
        indicators=[
            Indicator(id="Q1", column="q1"),
            Indicator(id="Q2", column="q2"),
            Indicator(id="Q3", column="q3")
        ],
        paths=[
            Path(from_node="A", to_node="B"),
            Path(from_node="B", to_node="C"),
            Path(from_node="C", to_node="A")
        ]
    )
    res_3 = validate_model_spec(spec_3node)
    assert res_3.is_valid is False
    assert any("Cycle detected" in err for err in res_3.errors)


def test_validator_detects_self_loop():
    spec = ModelSpec(
        constructs=[Construct(id="C1", name="Construct 1", indicators=["Q1"])],
        indicators=[Indicator(id="Q1", column="q1")],
        paths=[Path(from_node="C1", to_node="C1")]
    )
    res = validate_model_spec(spec)
    assert res.is_valid is False
    assert any("Self-loop" in err for err in res.errors)


def test_validator_orphan_and_missing_indicators():
    spec = ModelSpec(
        constructs=[
            Construct(id="C1", name="Construct 1", indicators=["Q1"]),
            Construct(id="C2", name="Empty Construct", indicators=[])  # 0 indicators
        ],
        indicators=[
            Indicator(id="Q1", column="q1"),
            Indicator(id="Q2", column="q2")  # Orphan indicator
        ],
        paths=[]
    )
    res = validate_model_spec(spec)
    assert res.is_valid is False
    assert any("must have at least 1 indicator" in err for err in res.errors)
    assert any("Orphan indicator 'Q2'" in err for err in res.errors)


def test_validator_unknown_and_shared_indicators():
    spec = ModelSpec(
        constructs=[
            Construct(id="C1", name="Construct 1", indicators=["Q1", "Q_NONEXISTENT"]),
            Construct(id="C2", name="Construct 2", indicators=["Q1"])  # Q1 is shared!
        ],
        indicators=[
            Indicator(id="Q1", column="q1")
        ],
        paths=[]
    )
    res = validate_model_spec(spec)
    assert res.is_valid is False
    assert any("references unknown indicator 'Q_NONEXISTENT'" in err for err in res.errors)
    assert any("assigned to multiple constructs" in err for err in res.errors)


def test_validator_dataset_column_mismatch():
    spec = ModelSpec(
        constructs=[Construct(id="C1", name="Construct 1", indicators=["Q1"])],
        indicators=[Indicator(id="Q1", column="missing_col")],
        paths=[]
    )
    res = validate_model_spec(spec, dataset_columns=["col_a", "col_b"])
    assert res.is_valid is False
    assert any("does not exist in the dataset" in err for err in res.errors)


def test_project_io_save_and_load_model():
    with tempfile.TemporaryDirectory() as tmpdir:
        prj_path = os.path.join(tmpdir, "test.pls")
        project_io.create_project(prj_path, "Test Project")

        raw_spec = {
            "constructs": [{"id": "C1", "name": "Satisfaction", "type": "reflective", "indicators": ["Q1"]}],
            "indicators": [{"id": "Q1", "column": "survey_q1"}],
            "paths": []
        }
        diagram_layout = {
            "nodes": [{"id": "C1", "x": 100, "y": 200}],
            "zoom": 1.2
        }

        project_io.save_model_spec(prj_path, raw_spec, diagram_layout)

        loaded = project_io.load_model_spec(prj_path)
        assert loaded is not None
        assert loaded["spec"] == raw_spec
        assert loaded["diagram_layout"] == diagram_layout
        assert loaded["updated_at"] is not None


def test_api_endpoints():
    with tempfile.TemporaryDirectory() as tmpdir:
        prj_path = os.path.join(tmpdir, "api_test.pls")
        project_io.create_project(prj_path, "API Test Project")
        # Save sample data
        project_io.save_data(prj_path, [[1.0, 2.0], [3.0, 4.0]], ["q1", "q2"], ["float", "float"])

        # 1. Validate API with valid spec
        valid_payload = {
            "spec": {
                "constructs": [
                    {"id": "C1", "name": "Satisfaction", "type": "reflective", "indicators": ["Q1"]},
                    {"id": "C2", "name": "Loyalty", "type": "reflective", "indicators": ["Q2"]}
                ],
                "indicators": [
                    {"id": "Q1", "column": "q1"},
                    {"id": "Q2", "column": "q2"}
                ],
                "paths": [
                    {"from": "C1", "to": "C2"}
                ]
            },
            "project_path": prj_path
        }
        # 1. Validate API with valid spec
        spec_obj = ModelSpec.model_validate(valid_payload["spec"])
        req_validate = ValidateModelRequest(spec=spec_obj, project_path=prj_path)
        data = validate_model(req_validate)
        assert data["is_valid"] is True
        assert data["exogenous_constructs"] == ["C1"]
        assert data["endogenous_constructs"] == ["C2"]

        # 2. Save Model API
        req_save = SaveModelRequest(
            project_path=prj_path,
            spec=spec_obj,
            diagram_layout={"zoom": 1.0, "nodes": [{"id": "C1", "x": 50, "y": 50}]}
        )
        save_data = save_project_model(req_save)
        assert save_data["status"] == "saved"
        assert save_data["validation"]["is_valid"] is True

        # 3. Load Model API
        load_data = load_project_model(path=prj_path)
        assert load_data["spec"]["constructs"][0]["id"] == "C1"
        assert load_data["diagram_layout"]["zoom"] == 1.0

