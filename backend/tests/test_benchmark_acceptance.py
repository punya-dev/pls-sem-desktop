"""
Section 27 Acceptance Test Suite on Authentic Reference Dataset.
Tests the Corporate Reputation case study from Hair, Hult, Ringle, and Sarstedt (2017).
File: backend/tests/data/Corporate reputation data.csv (N=344, missing code -99).
"""

import os
import pytest
import pandas as pd
import numpy as np

from engine.pls.algorithm import run_pipeline
from core.settings_schema import PipelineSettings
from engine.pls.blindfolding import run_blindfolding
from engine.pls.mediation import analyze_mediation
from engine.pls.moderation import analyze_moderation
from engine.pls.predict import run_pls_predict


DATA_PATH = os.path.join(os.path.dirname(__file__), "data", "Corporate reputation data.csv")


@pytest.fixture
def corp_rep_data():
    if not os.path.exists(DATA_PATH):
        pytest.skip(f"Reference dataset '{DATA_PATH}' is missing. Skipping acceptance tests.")
    df = pd.read_csv(DATA_PATH, sep=";")
    return df


@pytest.fixture
def corp_rep_simple_spec():
    return {
        "constructs": [
            {"id": "COMP", "name": "Competence", "type": "reflective", "indicators": ["comp_1", "comp_2", "comp_3"]},
            {"id": "LIKE", "name": "Likeability", "type": "reflective", "indicators": ["like_1", "like_2", "like_3"]},
            {"id": "CUSA", "name": "Customer Satisfaction", "type": "reflective", "indicators": ["cusa"]},
            {"id": "CUSL", "name": "Customer Loyalty", "type": "reflective", "indicators": ["cusl_1", "cusl_2", "cusl_3"]},
        ],
        "paths": [
            {"from": "COMP", "to": "CUSA"},
            {"from": "LIKE", "to": "CUSA"},
            {"from": "COMP", "to": "CUSL"},
            {"from": "LIKE", "to": "CUSL"},
            {"from": "CUSA", "to": "CUSL"},
        ],
    }


def test_t27_1_reference_dataset_verification(corp_rep_data):
    """
    Task 27.1 / MIS-07: Verify Corporate reputation data integrity.
    344 rows, 41 columns, missing code -99 count = 11.
    """
    assert corp_rep_data.shape == (344, 41)
    missing_count = int((corp_rep_data == -99).sum().sum())
    assert missing_count == 11

    # Check indicator columns
    expected_indicators = [
        "comp_1", "comp_2", "comp_3", "like_1", "like_2", "like_3",
        "cusl_1", "cusl_2", "cusl_3", "cusa"
    ]
    for ind in expected_indicators:
        assert ind in corp_rep_data.columns


def test_t27_2_simple_model_benchmark(corp_rep_data, corp_rep_simple_spec):
    """
    Task 27.2: Benchmark simple model estimates against Hair et al. (2017) textbook values.
    """
    cfg = PipelineSettings(
        inner_weighting="path",
        missing_treatment="mean",
        missing_codes=[-99, "-99"],
        sign_convention="dominant",
    )
    res = run_pipeline(corp_rep_data, corp_rep_simple_spec, cfg)

    # 1. Convergence
    assert res["converged"] is True
    assert res["iterations"] <= 10

    # 2. Path coefficients (tolerance +/- 0.02 vs published rounding)
    paths = res["structural"]["path_coefficients"]
    assert pytest.approx(0.162, abs=0.03) == paths["CUSA"]["COMP"]
    assert pytest.approx(0.424, abs=0.03) == paths["CUSA"]["LIKE"]
    assert pytest.approx(0.009, abs=0.03) == paths["CUSL"]["COMP"]
    assert pytest.approx(0.342, abs=0.03) == paths["CUSL"]["LIKE"]
    assert pytest.approx(0.504, abs=0.03) == paths["CUSL"]["CUSA"]

    # 3. R-squared
    r2 = res["structural"]["r_squared"]
    assert pytest.approx(0.295, abs=0.02) == r2["CUSA"]
    assert pytest.approx(0.562, abs=0.02) == r2["CUSL"]

    # 4. Construct reliability and convergent validity
    ave = res["reliability_and_validity"]["ave"]
    cr = res["reliability_and_validity"]["composite_reliability"]
    assert ave["COMP"] > 0.65
    assert ave["LIKE"] > 0.70
    assert ave["CUSL"] > 0.70

    assert cr["COMP"] > 0.85
    assert cr["LIKE"] > 0.88
    assert cr["CUSL"] > 0.88

    # 5. Discriminant validity (HTMT < 0.90)
    htmt = res["reliability_and_validity"]["htmt"]
    assert htmt["COMP"]["CUSL"] < 0.90
    assert htmt["LIKE"]["CUSL"] < 0.90


def test_t27_3_blindfolding_q2_benchmark(corp_rep_data, corp_rep_simple_spec):
    """
    Task 27.3: Blindfolding Q^2 predictive relevance (Hair et al. 2017 Ch. 6).
    Omission distance D = 7 (344 / 7 = 49.14 is non-integer).
    """
    b_res = run_blindfolding(
        df=corp_rep_data,
        spec=corp_rep_simple_spec,
        omission_distance=7,
        compute_q2_effects=False,
    )
    assert b_res["omission_distance"] == 7
    c_map = {c["construct_id"]: c for c in b_res["constructs"]}
    assert c_map["CUSA"]["q2_redundancy"] > 0.20
    assert c_map["CUSL"]["q2_redundancy"] > 0.35


def test_t27_4_mediation_benchmark(corp_rep_data, corp_rep_simple_spec):
    """
    Task 27.4: Mediation analysis of LIKE -> CUSA -> CUSL.
    """
    med_res = analyze_mediation(
        df=corp_rep_data,
        spec=corp_rep_simple_spec,
        source="LIKE",
        target="CUSL",
        n_boot=50,
        seed=42,
    )
    assert med_res["source"] == "LIKE"
    assert med_res["target"] == "CUSL"
    assert len(med_res["specific_indirect_effects"]) >= 1

    # Check that indirect effect through CUSA is positive
    ind_eff = med_res["specific_indirect_effects"][0]["original_effect"]
    assert ind_eff > 0.15

    # Total indirect and classification
    assert med_res["overall_classification"] in [
        "Complementary (partial mediation)",
        "Competitive (partial mediation)",
        "Indirect-only (full mediation)",
    ]


def test_t27_5_moderation_benchmark(corp_rep_data, corp_rep_simple_spec):
    """
    Task 27.5: Moderation analysis: COMP moderating CUSA -> CUSL.
    """
    mod_res = analyze_moderation(
        df=corp_rep_data,
        spec=corp_rep_simple_spec,
        source="CUSA",
        target="CUSL",
        moderator="COMP",
        method="two_stage",
        n_boot=30,
        seed=42,
    )
    assert mod_res["source"] == "CUSA"
    assert mod_res["target"] == "CUSL"
    assert mod_res["moderator"] == "COMP"
    assert "interaction_term" in mod_res
    assert "simple_slopes" in mod_res
    assert len(mod_res["simple_slopes"]) == 3  # -1 SD, Mean, +1 SD


def test_t27_6_plspredict_benchmark(corp_rep_data, corp_rep_simple_spec):
    """
    Task 27.6: PLSpredict on corporate reputation case study.
    """
    pred_res = run_pls_predict(
        df=corp_rep_data,
        model_spec=corp_rep_simple_spec,
        k_folds=5,
        repetitions=2,
        seed=42,
    )
    assert pred_res["k_folds"] == 5
    assert len(pred_res["indicator_metrics"]) >= 4

    # Indicators of CUSL and CUSA should achieve positive Q^2_predict
    q2_vals = [m["q2_predict"] for m in pred_res["indicator_metrics"]]
    assert any(q > 0 for q in q2_vals)
