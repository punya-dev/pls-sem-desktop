"""
Unit and Integration Tests for Phase 4:
Blindfolding (BLI-01..10), Mediation (MED-01..09), Moderation (MOD-M01..22),
Quadratic Effects (X-04), IPMA (IPM-01..07), and HCM (HCM-01..08).
"""

import numpy as np
import pandas as pd
import pytest

from engine.pls.blindfolding import run_blindfolding, validate_omission_distance
from engine.pls.mediation import analyze_mediation, classify_mediation, compute_sobel_test
from engine.pls.moderation import analyze_moderation, compute_simple_slopes, calculate_moderation_f2
from engine.pls.quadratic import analyze_quadratic_effect
from engine.pls.ipma import analyze_ipma
from engine.pls.hcm import analyze_hcm, build_repeated_indicators_spec


@pytest.fixture
def synthetic_phase4_data():
    np.random.seed(123)
    N = 185  # N=185: 185 % 7 = 3 != 0 (valid for D=7)
    
    # Latent variables
    c_x = np.random.normal(0, 1, N)
    c_m = 0.6 * c_x + np.random.normal(0, 0.5, N)
    c_w = np.random.normal(0, 1, N)  # Moderator
    c_y = 0.3 * c_x + 0.5 * c_m + 0.25 * (c_x * c_w) + np.random.normal(0, 0.4, N)

    df = pd.DataFrame({
        "x_1": 0.8 * c_x + np.random.normal(0, 0.4, N),
        "x_2": 0.85 * c_x + np.random.normal(0, 0.4, N),
        "m_1": 0.8 * c_m + np.random.normal(0, 0.4, N),
        "m_2": 0.85 * c_m + np.random.normal(0, 0.4, N),
        "w_1": 0.8 * c_w + np.random.normal(0, 0.4, N),
        "w_2": 0.85 * c_w + np.random.normal(0, 0.4, N),
        "y_1": 0.8 * c_y + np.random.normal(0, 0.4, N),
        "y_2": 0.85 * c_y + np.random.normal(0, 0.4, N),
    })

    model_spec = {
        "constructs": [
            {"id": "X", "name": "X", "type": "reflective", "indicators": ["x_1", "x_2"]},
            {"id": "M", "name": "M", "type": "reflective", "indicators": ["m_1", "m_2"]},
            {"id": "W", "name": "W", "type": "reflective", "indicators": ["w_1", "w_2"]},
            {"id": "Y", "name": "Y", "type": "reflective", "indicators": ["y_1", "y_2"]},
        ],
        "indicators": [
            {"name": "x_1", "construct_id": "X"},
            {"name": "x_2", "construct_id": "X"},
            {"name": "m_1", "construct_id": "M"},
            {"name": "m_2", "construct_id": "M"},
            {"name": "w_1", "construct_id": "W"},
            {"name": "w_2", "construct_id": "W"},
            {"name": "y_1", "construct_id": "Y"},
            {"name": "y_2", "construct_id": "Y"},
        ],
        "paths": [
            {"from": "X", "to": "M"},
            {"from": "M", "to": "Y"},
            {"from": "X", "to": "Y"},
            {"from": "W", "to": "Y"},
        ],
    }

    return df, model_spec


def test_blindfolding_and_q2(synthetic_phase4_data):
    df, spec = synthetic_phase4_data

    # Test omission distance validation (BLI-01)
    with pytest.raises(ValueError, match="must be between 5 and 10"):
        validate_omission_distance(len(df), 4)

    # 182 is divisible by 7 (182 % 7 == 0)
    with pytest.raises(ValueError, match="N/D is an integer"):
        validate_omission_distance(182, 7)

    # Valid D for N=185
    d_valid = validate_omission_distance(len(df), 7)
    assert d_valid == 7

    # Run blindfolding
    res = run_blindfolding(df, spec, omission_distance=7, compute_q2_effects=True)

    assert "constructs" in res
    assert "q2_effect_sizes" in res
    assert res["n_samples"] == len(df)

    # Endogenous construct Y must have positive Q^2
    y_info = next(c for c in res["constructs"] if c["construct_id"] == "Y")
    assert y_info["is_endogenous"] is True
    assert y_info["q2_redundancy"] > 0
    assert y_info["predictive_relevance"] is True

    # q^2 effect sizes
    effects = res["q2_effect_sizes"]
    assert len(effects) > 0
    assert any(e["predictor"] == "M" and e["target"] == "Y" for e in effects)


def test_mediation_analysis(synthetic_phase4_data):
    df, spec = synthetic_phase4_data

    # Test Zhao et al. classification logic
    c1 = classify_mediation(True, True, 0.3, 0.4)
    assert "Complementary" in c1["classification"]

    c2 = classify_mediation(True, True, -0.3, 0.4)
    assert "Competitive" in c2["classification"]

    c3 = classify_mediation(True, False, 0.3, 0.0)
    assert "Indirect-only" in c3["classification"]

    # Test Sobel test
    sobel = compute_sobel_test(a_coef=0.5, b_coef=0.4, a_se=0.08, b_se=0.07)
    assert sobel["z_statistic"] > 0
    assert sobel["p_value"] < 0.05
    assert "Sobel test assumes" in sobel["warning"]

    # Full mediation run with bootstrap
    med_res = analyze_mediation(
        df=df,
        spec=spec,
        source_construct="X",
        target_construct="Y",
        n_boot=100,
        seed=42,
        include_sobel=True,
    )

    assert med_res["source"] == "X"
    assert med_res["target"] == "Y"
    assert "direct_effect" in med_res
    assert "total_indirect_effect" in med_res
    assert len(med_res["specific_indirect_effects"]) >= 1

    path_x_m_y = next(p for p in med_res["specific_indirect_effects"] if p["path"] == "X -> M -> Y")
    assert path_x_m_y["original_effect"] > 0
    assert "sobel_test" in path_x_m_y
    assert med_res["overall_classification"] in ("Complementary (partial mediation)", "Indirect-only (full mediation)")


def test_moderation_analysis(synthetic_phase4_data):
    df, spec = synthetic_phase4_data

    # Test Kenny f^2
    f2_res = calculate_moderation_f2(0.50, 0.48)
    assert f2_res["f_squared"] > 0
    assert "Kenny (2016)" in f2_res["note"]

    # Simple slopes test
    slopes = compute_simple_slopes(beta_source=0.4, beta_moderator=0.2, beta_interaction=0.25)
    assert len(slopes["simple_slopes"]) == 3
    # High moderator level should have higher slope than low moderator level
    s_low = slopes["simple_slopes"][0]["slope"]
    s_high = slopes["simple_slopes"][2]["slope"]
    assert s_high > s_low

    # Full moderation run
    mod_res = analyze_moderation(
        df=df,
        spec=spec,
        source="X",
        moderator="W",
        target="Y",
        method="two_stage",
        n_boot=100,
        seed=42,
    )

    assert mod_res["source"] == "X"
    assert mod_res["moderator"] == "W"
    assert mod_res["target"] == "Y"
    assert "estimates" in mod_res
    assert "simple_slopes" in mod_res
    assert len(mod_res["simple_slopes"]) == 3
    assert mod_res["effect_size"]["f_squared"] >= 0


def test_quadratic_effects(synthetic_phase4_data):
    df, spec = synthetic_phase4_data

    q_res = analyze_quadratic_effect(
        df=df,
        spec=spec,
        source="X",
        target="Y",
        n_boot=100,
        seed=42,
    )

    assert q_res["source"] == "X"
    assert q_res["target"] == "Y"
    assert "linear_path" in q_res
    assert "quadratic_path" in q_res
    assert "shape_classification" in q_res
    assert len(q_res["curve_points"]) == 21


def test_ipma_analysis(synthetic_phase4_data):
    df, spec = synthetic_phase4_data

    ipma_res = analyze_ipma(
        df=df,
        spec=spec,
        target_construct="Y",
        level="both",
    )

    assert ipma_res["target_construct"] == "Y"
    assert 0 <= ipma_res["target_performance"] <= 100
    assert len(ipma_res["constructs"]) >= 2
    assert len(ipma_res["indicators"]) >= 4

    # Check that quadrants are assigned correctly
    for c_info in ipma_res["constructs"]:
        assert c_info["quadrant"] in ("concentrate_here", "keep_up_good_work", "low_priority", "possible_overkill")
        assert 0 <= c_info["performance"] <= 100


def test_hcm_analysis(synthetic_phase4_data):
    df, _ = synthetic_phase4_data

    # Define a 2-LOC model: LOC1 (x_1, x_2), LOC2 (m_1, m_2) forming HOC "SUPER"
    hcm_spec = {
        "constructs": [
            {"id": "LOC1", "name": "LOC1", "type": "reflective", "indicators": ["x_1", "x_2"]},
            {"id": "LOC2", "name": "LOC2", "type": "reflective", "indicators": ["m_1", "m_2"]},
            {"id": "Y", "name": "Y", "type": "reflective", "indicators": ["y_1", "y_2"]},
        ],
        "indicators": [
            {"name": "x_1", "construct_id": "LOC1"},
            {"name": "x_2", "construct_id": "LOC1"},
            {"name": "m_1", "construct_id": "LOC2"},
            {"name": "m_2", "construct_id": "LOC2"},
            {"name": "y_1", "construct_id": "Y"},
            {"name": "y_2", "construct_id": "Y"},
        ],
        "paths": [
            {"from": "SUPER", "to": "Y"},
        ],
    }

    # 1. Repeated Indicators approach (RR)
    res_rep = analyze_hcm(
        df=df,
        spec=hcm_spec,
        hoc_id="SUPER",
        loc_ids=["LOC1", "LOC2"],
        hoc_type="RR",
        approach="repeated_indicators",
    )
    assert res_rep["hoc_id"] == "SUPER"
    assert res_rep["approach"] == "repeated_indicators"
    assert "hoc_assessment" in res_rep
    assert "outer_loadings" in res_rep["hoc_assessment"]

    # 2. Disjoint Two-Stage approach (RF)
    res_ts = analyze_hcm(
        df=df,
        spec=hcm_spec,
        hoc_id="SUPER",
        loc_ids=["LOC1", "LOC2"],
        hoc_type="RF",
        approach="two_stage",
    )
    assert res_ts["hoc_id"] == "SUPER"
    assert res_ts["approach"] == "two_stage"
    assert "stage1_results" in res_ts
    assert "stage2_results" in res_ts
    assert "collinearity_vif" in res_ts["hoc_assessment"]
