"""
Unit and Integration Tests for Phase 5:
Confirmatory Tetrad Analysis (CTA-PLS) (CTA-01..06),
Measurement Invariance of Composite Models (MICOM) (MIC-01..05),
Multigroup Analysis (MGA) (MGA-01..09),
Finite Mixture PLS (FIMIX-PLS) (LAT-01..05),
and Prediction-Oriented Segmentation (PLS-POS) (LAT-06..07).
"""

import numpy as np
import pandas as pd
import pytest

from engine.pls.cta import run_cta_pls, generate_all_tetrads_for_block, select_nonredundant_tetrads
from engine.pls.micom import run_micom, check_configural_invariance
from engine.pls.mga import (
    analyze_mga,
    compute_parametric_test,
    compute_welch_satterthwaite_test,
    compute_henseler_pls_mga,
)
from engine.pls.fimix import analyze_fimix
from engine.pls.pos import analyze_pos


@pytest.fixture
def synthetic_multigroup_data():
    np.random.seed(42)
    N_per_group = 100

    # Group 1 (Strong path X -> Y: beta = 0.7)
    c_x1 = np.random.normal(0, 1, N_per_group)
    c_y1 = 0.7 * c_x1 + np.random.normal(0, 0.4, N_per_group)

    df_g1 = pd.DataFrame({
        "x_1": 0.8 * c_x1 + np.random.normal(0, 0.3, N_per_group),
        "x_2": 0.85 * c_x1 + np.random.normal(0, 0.3, N_per_group),
        "x_3": 0.8 * c_x1 + np.random.normal(0, 0.3, N_per_group),
        "x_4": 0.75 * c_x1 + np.random.normal(0, 0.3, N_per_group),
        "y_1": 0.8 * c_y1 + np.random.normal(0, 0.3, N_per_group),
        "y_2": 0.85 * c_y1 + np.random.normal(0, 0.3, N_per_group),
        "group": ["G1"] * N_per_group,
    })

    # Group 2 (Weak path X -> Y: beta = 0.2)
    c_x2 = np.random.normal(0, 1, N_per_group)
    c_y2 = 0.2 * c_x2 + np.random.normal(0, 0.5, N_per_group)

    df_g2 = pd.DataFrame({
        "x_1": 0.8 * c_x2 + np.random.normal(0, 0.3, N_per_group),
        "x_2": 0.85 * c_x2 + np.random.normal(0, 0.3, N_per_group),
        "x_3": 0.8 * c_x2 + np.random.normal(0, 0.3, N_per_group),
        "x_4": 0.75 * c_x2 + np.random.normal(0, 0.3, N_per_group),
        "y_1": 0.8 * c_y2 + np.random.normal(0, 0.3, N_per_group),
        "y_2": 0.85 * c_y2 + np.random.normal(0, 0.3, N_per_group),
        "group": ["G2"] * N_per_group,
    })

    df = pd.concat([df_g1, df_g2], axis=0).reset_index(drop=True)

    spec = {
        "constructs": [
            {"id": "X", "name": "X", "type": "reflective", "indicators": ["x_1", "x_2", "x_3", "x_4"]},
            {"id": "Y", "name": "Y", "type": "reflective", "indicators": ["y_1", "y_2"]},
        ],
        "indicators": [
            {"name": "x_1", "construct_id": "X"},
            {"name": "x_2", "construct_id": "X"},
            {"name": "x_3", "construct_id": "X"},
            {"name": "x_4", "construct_id": "X"},
            {"name": "y_1", "construct_id": "Y"},
            {"name": "y_2", "construct_id": "Y"},
        ],
        "paths": [
            {"from": "X", "to": "Y"},
        ],
    }

    return df, spec


def test_cta_pls_tetrad_analysis(synthetic_multigroup_data):
    df, spec = synthetic_multigroup_data

    # For p = 4 indicators, nonredundant tetrads r = 4*(4-3)/2 = 2
    inds = ["x_1", "x_2", "x_3", "x_4"]
    all_tetrads = generate_all_tetrads_for_block(inds)
    # (4 choose 4) * 2 = 2 definitions
    assert len(all_tetrads) == 2

    # Run full CTA-PLS
    cta_res = run_cta_pls(df, spec, n_boot=100, seed=42)

    assert "constructs" in cta_res
    c_x = next(c for c in cta_res["constructs"] if c["construct_id"] == "X")
    assert c_x["applicable"] is True
    assert c_x["n_indicators"] == 4
    assert c_x["n_nonredundant_tetrads"] == 2
    assert "tetrads" in c_x
    assert len(c_x["tetrads"]) == 2
    # Reflective synthetic data should support reflective specification
    assert "supported" in c_x["verdict"].lower()

    # Construct Y has only 2 indicators -> must report applicable=False with na_reason
    c_y = next(c for c in cta_res["constructs"] if c["construct_id"] == "Y")
    assert c_y["applicable"] is False
    assert "fewer_than_4_indicators" in c_y["na_reason"].lower() or "requires at least 4" in c_y["na_reason"].lower()


def test_micom_invariance(synthetic_multigroup_data):
    df, spec = synthetic_multigroup_data

    # Test Step 1 configural check
    cfg_res = check_configural_invariance(spec, spec, attestation=True)
    assert cfg_res["passed"] is True
    assert cfg_res["auto_verified"]["same_constructs"] is True

    # Run full 3-step MICOM
    micom_res = run_micom(
        df=df,
        spec=spec,
        group_col="group",
        n_permutations=100,
        seed=42,
    )

    assert "constructs" in micom_res
    assert micom_res["configural_invariance"]["passed"] is True

    for c in micom_res["constructs"]:
        assert "step2_compositional" in c
        assert "step3_equal_means" in c
        assert "step3_equal_variances" in c
        assert c["invariance_status"] in (
            "Full measurement invariance",
            "Partial measurement invariance",
            "No invariance",
        )


def test_mga_statistical_tests(synthetic_multigroup_data):
    df, spec = synthetic_multigroup_data

    # 1. Test unit functions
    param_t = compute_parametric_test(beta1=0.7, beta2=0.2, se1=0.08, se2=0.08, n1=100, n2=100)
    assert param_t["is_significant"] is True
    assert param_t["t_statistic"] > 3.0

    welch_t = compute_welch_satterthwaite_test(beta1=0.7, beta2=0.2, se1=0.06, se2=0.12, n1=100, n2=100)
    assert welch_t["is_significant"] is True

    henseler_t = compute_henseler_pls_mga(
        samples_g1=np.random.normal(0.7, 0.05, 500),
        samples_g2=np.random.normal(0.2, 0.05, 500),
    )
    assert henseler_t["is_significant"] is True

    # 2. Run full MGA
    mga_res = analyze_mga(
        df=df,
        spec=spec,
        group_col="group",
        n_boot=100,
        n_permutations=100,
        seed=42,
    )

    assert "path_comparisons" in mga_res
    assert len(mga_res["path_comparisons"]) == 1

    comp = mga_res["path_comparisons"][0]
    assert comp["path"] == "X -> Y"
    assert comp["beta_group_1"] > comp["beta_group_2"]
    # All multigroup tests should detect the true difference (0.7 vs 0.2)
    assert comp["parametric_test"]["is_significant"] is True
    assert comp["welch_test"]["is_significant"] is True
    assert comp["permutation_test"]["is_significant"] is True
    assert comp["henseler_pls_mga"]["is_significant"] is True


def test_fimix_latent_class(synthetic_multigroup_data):
    df, spec = synthetic_multigroup_data

    fimix_res = analyze_fimix(
        df=df,
        spec=spec,
        min_segments=1,
        max_segments=3,
        seed=42,
    )

    assert "segment_retention_table" in fimix_res
    table = fimix_res["segment_retention_table"]
    assert len(table) == 3

    # Check that all textbook metrics exist (AIC, AIC3, AIC4, BIC, CAIC, MDL5, EN)
    s1 = table[0]
    assert s1["segments"] == 1
    assert "aic3" in s1
    assert "caic" in s1
    assert "entropy_normalized" in s1

    # Check segment assignment output
    assert len(fimix_res["case_assignments"]) == len(df)
    assert 1 <= fimix_res["recommended_segments"] <= 3


def test_pos_segmentation(synthetic_multigroup_data):
    df, spec = synthetic_multigroup_data

    pos_res = analyze_pos(
        df=df,
        spec=spec,
        n_segments=2,
        max_iter=10,
        min_segment_size=15,
        seed=42,
    )

    assert pos_res["n_segments"] == 2
    assert "segments" in pos_res
    assert len(pos_res["segments"]) == 2
    assert len(pos_res["case_assignments"]) == len(df)
    for seg in pos_res["segments"]:
        assert seg["sample_size"] >= 15
        assert "path_coefficients" in seg
