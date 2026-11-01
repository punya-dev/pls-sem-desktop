import math
import numpy as np
import json
import pytest
from core.json_utils import sanitize_for_json
from engine.pls.algorithm import PLSAlgorithm
from engine.pls.fit import calculate_rms_theta
from model_spec import ModelSpec
import pandas as pd


def test_sanitize_primitives():
    assert sanitize_for_json(float("nan")) is None
    assert sanitize_for_json(float("inf")) is None
    assert sanitize_for_json(float("-inf")) is None
    assert sanitize_for_json(np.nan) is None
    assert sanitize_for_json(np.inf) is None
    assert sanitize_for_json(-np.inf) is None
    assert sanitize_for_json(1.23) == 1.23
    assert sanitize_for_json(42) == 42
    assert sanitize_for_json("text") == "text"
    assert sanitize_for_json(True) is True
    assert sanitize_for_json(None) is None


def test_sanitize_nested_structure():
    raw = {
        "a": float("nan"),
        "b": [1, 2, np.nan, np.inf, {"nested": float("-inf"), "valid": 3.14}],
        "c": np.array([1.0, np.nan, 3.0]),
        "d": np.float64(np.nan),
        "e": np.int64(10),
        "f": np.bool_(True),
    }
    clean = sanitize_for_json(raw)
    # Must succeed with strict allow_nan=False (Starlette default)
    serialized = json.dumps(clean, allow_nan=False)
    deserialized = json.loads(serialized)

    assert deserialized["a"] is None
    assert deserialized["b"][2] is None
    assert deserialized["b"][3] is None
    assert deserialized["b"][4]["nested"] is None
    assert deserialized["b"][4]["valid"] == 3.14
    assert deserialized["c"] == [1.0, None, 3.0]
    assert deserialized["d"] is None
    assert deserialized["e"] == 10
    assert deserialized["f"] is True


def test_rms_theta_single_item_no_nan():
    # Synthetic data with single-item construct
    np.random.seed(42)
    n = 100
    df = pd.DataFrame({
        "comp_1": np.random.normal(0, 1, n),
        "comp_2": np.random.normal(0, 1, n),
        "comp_3": np.random.normal(0, 1, n),
        "switch_1": np.random.normal(0, 1, n),
    })
    spec = {
        "constructs": [
            {"id": "COMP", "name": "COMP", "type": "reflective", "indicators": ["comp_1", "comp_2", "comp_3"]},
            {"id": "SWITCH", "name": "SWITCH", "type": "reflective", "indicators": ["switch_1"]},
        ],
        "indicators": [
            {"id": "comp_1", "column": "comp_1"},
            {"id": "comp_2", "column": "comp_2"},
            {"id": "comp_3", "column": "comp_3"},
            {"id": "switch_1", "column": "switch_1"},
        ],
        "paths": [{"from": "SWITCH", "to": "COMP"}],
        "moderating_effects": [],
    }

    model_spec = ModelSpec.model_validate(spec)
    algo = PLSAlgorithm()
    res = algo.fit(df, model_spec)

    fit = res.get("fit", {})
    rms = fit.get("rms_theta")
    # Must be either a finite float or None, NEVER float('nan')
    if rms is not None:
        assert not math.isnan(rms)
        assert not math.isinf(rms)

    # Must serialize cleanly with allow_nan=False
    json.dumps(res, allow_nan=False)

