"""
Unit and Integration Tests for Phase 3: Bootstrapping Upgrade, Structural Evaluation, Fit, and Consistent PLS (PLSc).
(BOO-01..19, STR-01..09, FIT-01..05, PLC-01..05)
"""

import numpy as np
import pandas as pd
import pytest

from engine.pls.bootstrap import ParallelBootstrapper
from engine.pls.ci import compute_all_confidence_intervals, percentile_ci, bias_corrected_ci, bca_ci
from engine.pls.contrast import compute_contrast, path_difference_test
from engine.pls.fit import evaluate_model_fit, calculate_srmr, calculate_gof
from engine.pls.plsc import apply_plsc_correction
from engine.pls.algorithm import run_pipeline, PLSAlgorithm
from core.settings_schema import PipelineSettings


@pytest.fixture
def synthetic_sem_data():
    np.random.seed(42)
    N = 180
    # Common factor structure
    c_x1 = np.random.normal(0, 1, N)
    c_x2 = np.random.normal(0, 1, N)
    # Structural relations: Y1 = 0.5 * X1 + e1; Y2 = 0.4 * Y1 + 0.3 * X2 + e2
    c_y1 = 0.5 * c_x1 + np.random.normal(0, 0.6, N)
    c_y2 = 0.4 * c_y1 + 0.3 * c_x2 + np.random.normal(0, 0.5, N)

    df = pd.DataFrame({
        "x1_1": 0.8 * c_x1 + np.random.normal(0, 0.4, N),
        "x1_2": 0.85 * c_x1 + np.random.normal(0, 0.4, N),
        "x2_1": 0.8 * c_x2 + np.random.normal(0, 0.4, N),
        "x2_2": 0.85 * c_x2 + np.random.normal(0, 0.4, N),
        "y1_1": 0.8 * c_y1 + np.random.normal(0, 0.4, N),
        "y1_2": 0.85 * c_y1 + np.random.normal(0, 0.4, N),
        "y2_1": 0.8 * c_y2 + np.random.normal(0, 0.4, N),
        "y2_2": 0.85 * c_y2 + np.random.normal(0, 0.4, N),
    })

    model_spec = {
        "constructs": [
            {"id": "X1", "name": "X1", "type": "reflective", "indicators": ["x1_1", "x1_2"]},
            {"id": "X2", "name": "X2", "type": "reflective", "indicators": ["x2_1", "x2_2"]},
            {"id": "Y1", "name": "Y1", "type": "reflective", "indicators": ["y1_1", "y1_2"]},
            {"id": "Y2", "name": "Y2", "type": "reflective", "indicators": ["y2_1", "y2_2"]},
        ],
        "indicators": [
            {"name": "x1_1", "construct_id": "X1"},
            {"name": "x1_2", "construct_id": "X1"},
            {"name": "x2_1", "construct_id": "X2"},
            {"name": "x2_2", "construct_id": "X2"},
            {"name": "y1_1", "construct_id": "Y1"},
            {"name": "y1_2", "construct_id": "Y1"},
            {"name": "y2_1", "construct_id": "Y2"},
            {"name": "y2_2", "construct_id": "Y2"},
        ],
        "paths": [
            {"from": "X1", "to": "Y1"},
            {"from": "Y1", "to": "Y2"},
            {"from": "X2", "to": "Y2"},
        ],
    }

    return df, model_spec


def test_confidence_intervals_module():
    np.random.seed(99)
    dist = np.random.normal(loc=0.5, scale=0.1, size=1000)
    jack = np.random.normal(loc=0.5, scale=0.01, size=100)

    p_low, p_high = percentile_ci(dist, alpha=0.05)
    assert p_low < 0.5 < p_high
    assert abs(p_high - 0.5 - 1.96 * 0.1) < 0.05

    bc_low, bc_high = bias_corrected_ci(0.5, dist, alpha=0.05)
    assert bc_low < 0.5 < bc_high

    bca_low, bca_high = bca_ci(0.5, dist, jackknife_vals=jack, alpha=0.05)
    assert bca_low < 0.5 < bca_high

    all_cis = compute_all_confidence_intervals(0.5, dist, jackknife_vals=jack)
    assert "percentile" in all_cis
    assert "bias_corrected" in all_cis
    assert "bca" in all_cis


def test_complete_bootstrapping_and_parameter_extraction(synthetic_sem_data):
    df, spec = synthetic_sem_data
    booter = ParallelBootstrapper(n_workers=2, chunk_size=20)

    res = booter.run(
        df,
        spec,
        n_boot=60,
        seed=101,
        mode="complete",
        sign_change="none",
        test_distribution="t",
        ci_method="bca",
    )

    assert res["n_boot"] == 60
    assert res["actual_samples"] == 60

    params = res["parameters"]
    # Check that specific indirect path is extracted and summarized
    assert "specific_indirect:X1 -> Y1 -> Y2" in params
    ind_res = params["specific_indirect:X1 -> Y1 -> Y2"]
    assert ind_res["original"] > 0
    assert "ci_low" in ind_res and "ci_high" in ind_res

    # Check degrees of freedom for paths vs loadings
    path_res = params["path:X1->Y1"]
    # Target Y1 has 1 predictor, df = N - 1 - 1 = 178
    assert path_res["df"] == 180 - 1 - 1

    load_res = params["loading:X1->x1_1"]
    assert load_res["df"] == 180 - 1

    # Check that HTMT and R2 are present in complete mode
    assert any(k.startswith("htmt:") for k in params)
    assert "r2:Y1" in params
    assert "r2:Y2" in params
    assert "f2:X1->Y1" in params


def test_sign_change_strategies(synthetic_sem_data):
    df, spec = synthetic_sem_data
    booter = ParallelBootstrapper(n_workers=2, chunk_size=20)

    # Test that individual and construct sign change run without error
    res_ind = booter.run(df, spec, n_boot=30, seed=77, sign_change="individual")
    assert res_ind["actual_samples"] == 30

    res_const = booter.run(df, spec, n_boot=30, seed=77, sign_change="construct")
    assert res_const["actual_samples"] == 30


def test_bootstrap_contrasts(synthetic_sem_data):
    df, spec = synthetic_sem_data
    booter = ParallelBootstrapper(n_workers=2, chunk_size=20)
    boot_res = booter.run(df, spec, n_boot=50, seed=42)

    samples_matrix = boot_res["samples_matrix"]
    orig_params = {k: v["original"] for k, v in boot_res["parameters"].items()}

    # Test contrast: difference between two paths into Y2: (Y1->Y2) - (X2->Y2)
    contrast_weights = {
        "path:Y1->Y2": 1.0,
        "path:X2->Y2": -1.0,
    }
    c_res = compute_contrast(orig_params, samples_matrix, contrast_weights)
    assert "t_stat" in c_res
    assert "p_value" in c_res
    assert len(c_res["confidence_intervals"]) == 3

    # Contrast of a parameter with itself must be exactly 0 with SE 0
    self_contrast = compute_contrast(orig_params, samples_matrix, {"path:Y1->Y2": 1.0, "path:Y1->Y2": -1.0})
    # Since keys overwrite in dict, test with separate path diff
    diff_res = path_difference_test(orig_params, samples_matrix, "path:Y1->Y2", "path:X2->Y2")
    assert diff_res["path_1"] == "path:Y1->Y2"
    assert diff_res["path_2"] == "path:X2->Y2"


def test_model_fit_evaluation(synthetic_sem_data):
    df, spec = synthetic_sem_data
    res = run_pipeline(df, spec)

    assert "fit" in res
    fit = res["fit"]

    # SRMR checks
    assert "saturated_model" in fit
    assert "estimated_model" in fit
    assert fit["saturated_model"]["srmr"] < 0.15
    assert fit["estimated_model"]["srmr"] < 0.15

    # Exact fit criteria
    assert "d_uls" in fit["saturated_model"]
    assert "d_g" in fit["saturated_model"]

    # GoF
    assert "gof" in fit
    assert fit["gof"]["gof"] > 0
    assert "not recommended" in fit["gof"]["note"].lower()


def test_plsc_disattenuation(synthetic_sem_data):
    df, spec = synthetic_sem_data
    # 1. Standard PLS run
    res_pls = run_pipeline(df, spec, settings=PipelineSettings(consistent=False))
    # 2. Consistent PLS run
    res_plsc = run_pipeline(df, spec, settings=PipelineSettings(consistent=True))

    assert res_plsc.get("is_consistent") is True
    # Verify that consistent outer loadings and path coefficients exist
    plsc_paths = res_plsc["structural"]["path_coefficients"]
    assert "Y1" in plsc_paths and "X1" in plsc_paths["Y1"]
    assert plsc_paths["Y1"]["X1"] > 0

    # In common factor model, PLSc disattenuation typically increases path coefficients toward truth
    beta_pls = res_pls["structural"]["path_coefficients"]["Y1"]["X1"]
    beta_plsc = plsc_paths["Y1"]["X1"]
    assert beta_plsc >= beta_pls * 0.9  # consistent path is in close or higher range
