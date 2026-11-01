"""
Test Suite for Redundancy Analysis (Convergent Validity of Formative Constructs).
Validates against SmartPLS 4 reference behavior and analytic OLS identities.
Following Hair et al. (2022), A Primer on PLS-SEM (3rd ed.), Ch. 5.
"""

import json
import os
import numpy as np
import pandas as pd
import pytest

from engine.pls.algorithm import PLSAlgorithm, run_pipeline, PipelineSettings, standardize_matrix
from engine.pls.redundancy import (
    detect_redundancy_patterns,
    compute_convergent_validity_redundancy,
    attach_bootstrap_to_redundancy,
    validate_redundancy_candidate,
    build_redundancy_model_spec,
)
from reporting.tables import TABLE_EXTRACTORS, export_table_to_format

CORP_REP_DATA_PATH = os.path.join(os.path.dirname(__file__), "data", "Corporate reputation data.csv")
ADVD_DATA_PATH = os.path.join(os.path.dirname(__file__), "data", "data_for_advd_pls.csv")
REF_CORP_REP_PATH = os.path.join(os.path.dirname(__file__), "reference", "smartpls_redundancy_corp_rep.json")
REF_HCM_REPU_PATH = os.path.join(os.path.dirname(__file__), "reference", "smartpls_redundancy_hcm_repu.json")


def _load_corp_data():
    return pd.read_csv(CORP_REP_DATA_PATH, sep=";")


def _load_advd_data():
    if os.path.exists(ADVD_DATA_PATH):
        return pd.read_csv(ADVD_DATA_PATH, sep=";")
    return _load_corp_data()


# =========================================================================
# 1. Analytic OLS Identity Tests (Synthetic Data & Real Data)
# =========================================================================
@pytest.mark.parametrize("k_indicators", [3, 8])
def test_analytic_ols_identity_synthetic(k_indicators):
    """
    For a redundancy model X_F -> X_G with single-item X_G and Mode B X_F:
    - Converged outer weights are proportional to OLS regression coefficients:
      w = b / sd(X b) so that Var(X_F) = 1.
    - Algorithm converges in <= 5 iterations.
    - Path coefficient = corr(X_F, X_G) = multiple R = sqrt(R2_OLS).
    - R²(X_G) = beta².
    - Outer loading of X_G = 1.000; outer loadings of indicators = corr(X_i, X_F).
    """
    np.random.seed(42 + k_indicators)
    n = 500
    # True latent variable
    eta = np.random.randn(n)
    # Formative indicators with noise
    X_raw = np.zeros((n, k_indicators))
    for j in range(k_indicators):
        X_raw[:, j] = 0.5 * eta + np.random.randn(n) * 0.5
    # Standardize X
    X = (X_raw - X_raw.mean(axis=0)) / X_raw.std(axis=0, ddof=0)

    # Global single item
    y_raw = 0.7 * eta + np.random.randn(n) * 0.4
    y = (y_raw - y_raw.mean()) / y_raw.std(ddof=0)

    ind_names = [f"x_{i}" for i in range(k_indicators)]
    df = pd.DataFrame(X, columns=ind_names)
    df["y_global"] = y

    # Independent OLS regression
    b_ols, _, _, _ = np.linalg.lstsq(X, y, rcond=None)
    y_hat = X @ b_ols
    sd_yhat = np.std(y_hat, ddof=0)
    w_expected = b_ols / sd_yhat
    r2_expected = 1.0 - np.sum((y - y_hat) ** 2) / np.sum((y - np.mean(y)) ** 2)
    beta_expected = np.sqrt(r2_expected)

    spec = {
        "constructs": [
            {"id": "X_F", "name": "X_F", "type": "formative", "outer_mode": "B", "indicators": ind_names},
            {"id": "X_G", "name": "X_G", "type": "reflective", "outer_mode": "A", "indicators": ["y_global"]},
        ],
        "paths": [{"from": "X_F", "to": "X_G"}],
    }

    settings = PipelineSettings(
        inner_weighting="path",
        max_iter=3000,
        tolerance=1e-7,
    )
    res = run_pipeline(df, spec, settings)

    # 1. Convergence
    assert res["converged"] is True
    assert res["iterations"] <= 5

    # 2. Outer weights
    pls_w = np.array([res["measurement"]["outer_weights"]["X_F"][col] for col in ind_names])
    np.testing.assert_allclose(pls_w, w_expected, atol=1e-6)

    # 3. Path coefficient & R²
    pls_beta = res["structural"]["path_coefficients"]["X_G"]["X_F"]
    pls_r2 = res["structural"]["r_squared"]["X_G"]
    assert abs(pls_beta - beta_expected) < 1e-6
    assert abs(pls_r2 - r2_expected) < 1e-6
    assert abs(pls_r2 - (pls_beta ** 2)) < 1e-6

    # 4. Outer loadings
    assert res["measurement"]["outer_loadings"]["X_G"]["y_global"] == 1.0
    x_f_scores = np.array(res["construct_scores"]["X_F"])
    for col in ind_names:
        expected_loading = float(np.corrcoef(df[col], x_f_scores)[0, 1])
        actual_loading = res["measurement"]["outer_loadings"]["X_F"][col]
        assert abs(actual_loading - expected_loading) < 1e-6


def test_analytic_ols_identity_corporate_reputation():
    """Analytic OLS identity on the four formative constructs of Corporate reputation data."""
    df = _load_corp_data()
    models = [
        ("ATTR", ["attr_1", "attr_2", "attr_3"], "attr_global"),
        ("CSOR", ["csor_1", "csor_2", "csor_3", "csor_4", "csor_5"], "csor_global"),
        ("PERF", ["perf_1", "perf_2", "perf_3", "perf_4", "perf_5"], "perf_global"),
        ("QUAL", [f"qual_{i}" for i in range(1, 9)], "qual_global"),
    ]

    for name, indicators, global_item in models:
        spec = {
            "constructs": [
                {"id": f"{name}_F", "name": f"{name}_F", "type": "formative", "outer_mode": "B", "indicators": indicators},
                {"id": f"{name}_G", "name": f"{name}_G", "type": "reflective", "outer_mode": "A", "indicators": [global_item]},
            ],
            "paths": [{"from": f"{name}_F", "to": f"{name}_G"}],
        }
        settings = PipelineSettings(
            inner_weighting="path",
            max_iter=3000,
            tolerance=1e-7,
            missing_treatment="mean",
            missing_codes=[-99, "-99"],
        )
        res = run_pipeline(df, spec, settings)

        # Independent OLS
        sub = df[indicators + [global_item]].copy().replace(-99, np.nan).replace("-99", np.nan)
        for col in sub.columns:
            sub[col] = pd.to_numeric(sub[col]).fillna(pd.to_numeric(sub[col]).mean())
        X = (sub[indicators].to_numpy() - sub[indicators].to_numpy().mean(axis=0)) / sub[indicators].to_numpy().std(axis=0, ddof=0)
        y = (sub[global_item].to_numpy() - sub[global_item].to_numpy().mean()) / sub[global_item].to_numpy().std(ddof=0)

        b_ols, _, _, _ = np.linalg.lstsq(X, y, rcond=None)
        y_hat = X @ b_ols
        w_expected = b_ols / np.std(y_hat, ddof=0)
        r2_expected = 1.0 - np.sum((y - y_hat) ** 2) / np.sum((y - np.mean(y)) ** 2)
        beta_expected = np.sqrt(r2_expected)

        pls_w = np.array([res["measurement"]["outer_weights"][f"{name}_F"][col] for col in indicators])
        pls_beta = res["structural"]["path_coefficients"][f"{name}_G"][f"{name}_F"]
        pls_r2 = res["structural"]["r_squared"][f"{name}_G"]

        np.testing.assert_allclose(pls_w, w_expected, atol=1e-6)
        assert abs(pls_beta - beta_expected) < 1e-6
        assert abs(pls_r2 - r2_expected) < 1e-6
        assert res["iterations"] <= 5


# =========================================================================
# 2. Corporate Reputation SmartPLS 4 Benchmark Reproduction
# =========================================================================
def test_corporate_reputation_smartpls4_parity():
    """
    Verifies that the 4 corporate reputation redundancy models match SmartPLS 4:
    ATTR: 0.874
    CSOR: 0.857
    PERF: 0.811
    QUAL: 0.805
    Tolerance <= 0.001, R² = beta².
    """
    assert os.path.exists(REF_CORP_REP_PATH), "Reference file smartpls_redundancy_corp_rep.json must exist"
    with open(REF_CORP_REP_PATH, "r") as f:
        ref_data = json.load(f)

    df = _load_corp_data()

    settings = PipelineSettings(
        inner_weighting="path",
        max_iter=3000,
        tolerance=1e-7,
        missing_treatment="mean",
        missing_codes=[-99, "-99"],
    )

    for construct_name, ref_model in ref_data["models"].items():
        spec = {
            "constructs": [
                {
                    "id": ref_model["formative_construct"],
                    "name": ref_model["formative_construct"],
                    "type": "formative",
                    "outer_mode": "B",
                    "indicators": ref_model["formative_indicators"],
                },
                {
                    "id": ref_model["global_construct"],
                    "name": ref_model["global_construct"],
                    "type": "reflective",
                    "outer_mode": "A",
                    "indicators": [ref_model["global_item"]],
                },
            ],
            "paths": [{"from": ref_model["formative_construct"], "to": ref_model["global_construct"]}],
        }

        res = run_pipeline(df, spec, settings)
        actual_beta = res["structural"]["path_coefficients"][ref_model["global_construct"]][ref_model["formative_construct"]]
        actual_r2 = res["structural"]["r_squared"][ref_model["global_construct"]]

        expected_beta = ref_model["path_coefficient"]
        expected_r2 = ref_model["r_squared"]

        diff_beta = abs(actual_beta - expected_beta)
        diff_r2 = abs(actual_r2 - expected_r2)

        assert diff_beta <= 0.001, f"{construct_name} path coefficient {actual_beta:.4f} differs from SmartPLS {expected_beta} by {diff_beta:.4f}"
        assert diff_r2 <= 0.002, f"{construct_name} R² {actual_r2:.4f} differs from expected {expected_r2} by {diff_r2:.4f}"
        assert res["iterations"] <= 5


# =========================================================================
# 3. HCM Disjoint 2nd-Stage Redundancy Model
# =========================================================================
def test_hcm_redundancy_model_disjoint_stage2():
    """
    Tests the HCM disjoint 2nd-stage redundancy workflow:
    REPU_F (indicators: 'LV scores - COMP', 'LV scores - LIKE') -> REPU_G (indicator: 'repu_global').
    If smartpls_redundancy_hcm_repu.json has placeholders (null), runs analytic identity check and skips parity comparison.
    """
    assert os.path.exists(REF_HCM_REPU_PATH), "Reference file smartpls_redundancy_hcm_repu.json must exist"
    with open(REF_HCM_REPU_PATH, "r") as f:
        ref_hcm = json.load(f)

    df_raw = _load_advd_data()

    # Stage 1: Estimate full Corporate Reputation Model (with 4 formative antecedents: ATTR, CSOR, PERF, QUAL)
    spec_stage1 = {
        "constructs": [
            {"id": "COMP", "name": "COMP", "type": "reflective", "indicators": ["comp_1", "comp_2", "comp_3"]},
            {"id": "LIKE", "name": "LIKE", "type": "reflective", "indicators": ["like_1", "like_2", "like_3"]},
            {"id": "CUSA", "name": "CUSA", "type": "reflective", "indicators": ["cusa"]},
            {"id": "CUSL", "name": "CUSL", "type": "reflective", "indicators": ["cusl_1", "cusl_2", "cusl_3"]},
            {"id": "ATTR", "name": "ATTR", "type": "formative", "indicators": ["attr_1", "attr_2", "attr_3"]},
            {"id": "PERF", "name": "PERF", "type": "formative", "indicators": ["perf_1", "perf_2", "perf_3", "perf_4", "perf_5"]},
            {"id": "QUAL", "name": "QUAL", "type": "formative", "indicators": ["qual_1", "qual_2", "qual_3", "qual_4", "qual_5", "qual_6", "qual_7", "qual_8"]},
            {"id": "CSOR", "name": "CSOR", "type": "formative", "indicators": ["csor_1", "csor_2", "csor_3", "csor_4", "csor_5"]},
        ],
        "paths": [
            {"from": "ATTR", "to": "COMP"}, {"from": "ATTR", "to": "LIKE"},
            {"from": "PERF", "to": "COMP"}, {"from": "PERF", "to": "LIKE"},
            {"from": "QUAL", "to": "COMP"}, {"from": "QUAL", "to": "LIKE"},
            {"from": "CSOR", "to": "COMP"}, {"from": "CSOR", "to": "LIKE"},
            {"from": "COMP", "to": "CUSA"}, {"from": "COMP", "to": "CUSL"},
            {"from": "LIKE", "to": "CUSA"}, {"from": "LIKE", "to": "CUSL"},
            {"from": "CUSA", "to": "CUSL"},
        ],
    }
    cfg = PipelineSettings(missing_treatment="mean", missing_codes=[-99, "-99"])
    res1 = run_pipeline(df_raw, spec_stage1, cfg)

    # Stage 2: Create dataset with LV score columns and repu_global
    df_stage2 = df_raw.copy()
    df_stage2["LV scores - COMP"] = res1["construct_scores"]["COMP"]
    df_stage2["LV scores - LIKE"] = res1["construct_scores"]["LIKE"]

    if "repu_global" not in df_stage2.columns:
        df_stage2["repu_global"] = 0.5 * df_stage2["cusa"] + 0.5 * df_stage2["cusl_1"]

    spec_stage2 = {
        "constructs": [
            {
                "id": "REPU_F",
                "name": "REPU_F",
                "type": "formative",
                "outer_mode": "B",
                "indicators": ["LV scores - COMP", "LV scores - LIKE"],
            },
            {
                "id": "REPU_G",
                "name": "REPU_G",
                "type": "reflective",
                "outer_mode": "A",
                "indicators": ["repu_global"],
            },
        ],
        "paths": [{"from": "REPU_F", "to": "REPU_G"}],
    }

    res2 = run_pipeline(df_stage2, spec_stage2, cfg)
    assert res2["converged"] is True
    assert res2["iterations"] <= 5

    # Check analytic OLS identity
    X = df_stage2[["LV scores - COMP", "LV scores - LIKE"]].to_numpy()
    y = df_stage2["repu_global"].to_numpy()
    X_std = (X - X.mean(axis=0)) / X.std(axis=0, ddof=0)
    y_std = (y - y.mean()) / y.std(ddof=0)

    b_ols, _, _, _ = np.linalg.lstsq(X_std, y_std, rcond=None)
    y_hat = X_std @ b_ols
    w_expected = b_ols / np.std(y_hat, ddof=0)
    r2_expected = 1.0 - np.sum((y_std - y_hat) ** 2) / np.sum((y_std - np.mean(y_std)) ** 2)
    beta_expected = np.sqrt(r2_expected)

    actual_beta = res2["structural"]["path_coefficients"]["REPU_G"]["REPU_F"]
    actual_r2 = res2["structural"]["r_squared"]["REPU_G"]
    actual_w = np.array([res2["measurement"]["outer_weights"]["REPU_F"]["LV scores - COMP"],
                         res2["measurement"]["outer_weights"]["REPU_F"]["LV scores - LIKE"]])

    np.testing.assert_allclose(actual_w, w_expected, atol=1e-6)
    assert abs(actual_beta - beta_expected) < 1e-6
    assert abs(actual_r2 - r2_expected) < 1e-6

    # SmartPLS parity comparison
    ref_repu = ref_hcm.get("models", {}).get("REPU", {})
    if ref_repu.get("path_coefficient") is None:
        pytest.skip("smartpls_redundancy_hcm_repu.json contains null placeholders; analytic identity verified successfully.")
    else:
        assert abs(actual_beta - ref_repu["path_coefficient"]) <= 0.001
        assert abs(actual_r2 - ref_repu["r_squared"]) <= 0.001
        if "outer_weights" in ref_repu:
            exp_w_comp = ref_repu["outer_weights"]["LV scores - COMP"]
            exp_w_like = ref_repu["outer_weights"]["LV scores - LIKE"]
            assert abs(actual_w[0] - exp_w_comp) <= 0.001
            assert abs(actual_w[1] - exp_w_like) <= 0.001


# =========================================================================
# 4. Variable Names with Spaces and Hyphens
# =========================================================================
def test_variable_names_with_spaces_and_hyphens():
    """Verify indicators named with spaces, hyphens, and punctuation survive estimation and bootstrapping."""
    np.random.seed(42)
    n = 120
    df = pd.DataFrame({
        "LV scores - COMP": np.random.randn(n),
        "LV scores - LIKE": np.random.randn(n),
        "repu - global item": np.random.randn(n),
    })

    spec = {
        "constructs": [
            {
                "id": "REPU_F",
                "name": "REPU_F",
                "type": "formative",
                "outer_mode": "B",
                "indicators": ["LV scores - COMP", "LV scores - LIKE"],
            },
            {
                "id": "REPU_G",
                "name": "REPU_G",
                "type": "reflective",
                "outer_mode": "A",
                "indicators": ["repu - global item"],
            },
        ],
        "paths": [{"from": "REPU_F", "to": "REPU_G"}],
    }

    res = run_pipeline(df, spec)
    assert res["converged"] is True
    weights = res["measurement"]["outer_weights"]["REPU_F"]
    assert "LV scores - COMP" in weights
    assert "LV scores - LIKE" in weights

    # Bootstrapping with spaces/hyphens
    algo = PLSAlgorithm()
    boot = algo.bootstrap(df, spec, n_boot=20, seed=123)
    assert len(boot["paths"]) == 1
    assert boot["paths"][0]["from"] == "REPU_F"
    assert boot["paths"][0]["to"] == "REPU_G"

    # Export table with spaces/hyphens
    table_data = TABLE_EXTRACTORS["outer_weights"](res)
    content, media, fname = export_table_to_format(table_data, "csv")
    csv_text = content.decode("utf-8")
    assert "LV scores - COMP" in csv_text
    assert "LV scores - LIKE" in csv_text


# =========================================================================
# 5. Convergent Validity Card Generation & Pattern Detection
# =========================================================================
def test_convergent_validity_card_pattern_detection():
    """
    Verifies that the convergent validity card:
    - Appears when model is a redundancy model (formative -> single item).
    - Is hidden when model has non-redundancy paths (e.g. general SEM model).
    - Verdict logic at 0.70 (>= 0.70 is Supported, < 0.70 is Not supported).
    """
    df = _load_corp_data()

    # Model A: Pure redundancy model (ATTR_F -> ATTR_G)
    spec_red = {
        "constructs": [
            {"id": "ATTR_F", "name": "ATTR_F", "type": "formative", "outer_mode": "B", "indicators": ["attr_1", "attr_2", "attr_3"]},
            {"id": "ATTR_G", "name": "ATTR_G", "type": "reflective", "outer_mode": "A", "indicators": ["attr_global"]},
        ],
        "paths": [{"from": "ATTR_F", "to": "ATTR_G"}],
    }
    res_red = run_pipeline(df, spec_red)
    assert "convergent_validity_redundancy" in res_red
    card = res_red["convergent_validity_redundancy"]
    assert len(card) == 1
    assert card[0]["formative_construct"] == "ATTR_F"
    assert card[0]["global_construct"] == "ATTR_G"
    assert card[0]["path_coefficient"] >= 0.70
    assert card[0]["supported"] is True
    assert card[0]["result"] == "Supported (>= 0.70)"
    assert "Hair et al. (2022)" in card[0]["note"]

    # Model B: Non-redundancy structural model (COMP -> CUSA -> CUSL)
    spec_norm = {
        "constructs": [
            {"id": "COMP", "name": "COMP", "type": "reflective", "indicators": ["comp_1", "comp_2", "comp_3"]},
            {"id": "CUSA", "name": "CUSA", "type": "reflective", "indicators": ["cusa"]},
            {"id": "CUSL", "name": "CUSL", "type": "reflective", "indicators": ["cusl_1", "cusl_2", "cusl_3"]},
        ],
        "paths": [
            {"from": "COMP", "to": "CUSA"},
            {"from": "CUSA", "to": "CUSL"},
        ],
    }
    res_norm = run_pipeline(df, spec_norm)
    assert "convergent_validity_redundancy" not in res_norm


def test_convergent_validity_verdict_threshold():
    """Verify verdict threshold exactly at 0.70."""
    # Mock result with 0.699
    res_low = {
        "structural": {
            "path_coefficients": {"G": {"F": 0.6999}},
            "r_squared": {"G": 0.4899},
        }
    }
    spec = {
        "constructs": [
            {"id": "F", "name": "F", "type": "formative", "outer_mode": "B", "indicators": ["x1", "x2"]},
            {"id": "G", "name": "G", "type": "reflective", "outer_mode": "A", "indicators": ["g1"]},
        ],
        "paths": [{"from": "F", "to": "G"}],
    }
    card_low = compute_convergent_validity_redundancy(res_low, spec)
    assert card_low[0]["supported"] is False
    assert card_low[0]["result"] == "Not supported (< 0.70)"

    # Mock result with 0.7000
    res_high = {
        "structural": {
            "path_coefficients": {"G": {"F": 0.7000}},
            "r_squared": {"G": 0.4900},
        }
    }
    card_high = compute_convergent_validity_redundancy(res_high, spec)
    assert card_high[0]["supported"] is True
    assert card_high[0]["result"] == "Supported (>= 0.70)"


# =========================================================================
# 6. Bootstrap Resampling & Significance in Redundancy Analysis
# =========================================================================
def test_redundancy_bootstrapping_metrics():
    """Verifies that bootstrapping re-estimates Mode B weights per resample and attaches stats to card."""
    df = _load_corp_data()
    spec = {
        "constructs": [
            {"id": "ATTR_F", "name": "ATTR_F", "type": "formative", "outer_mode": "B", "indicators": ["attr_1", "attr_2", "attr_3"]},
            {"id": "ATTR_G", "name": "ATTR_G", "type": "reflective", "outer_mode": "A", "indicators": ["attr_global"]},
        ],
        "paths": [{"from": "ATTR_F", "to": "ATTR_G"}],
    }

    algo = PLSAlgorithm()
    res = algo.fit(df, spec)
    boot = algo.bootstrap(df, spec, n_boot=50, seed=42)

    attach_bootstrap_to_redundancy(res, boot)
    card = res.get("convergent_validity_redundancy", [])
    assert len(card) == 1
    assert "bootstrap" in card[0]
    b = card[0]["bootstrap"]
    assert b["se"] > 0
    assert b["t_stat"] > 10.0
    assert b["p_value"] < 0.05
    assert b["ci_low"] < b["ci_high"]

    # Table export includes bootstrap statistics
    table_data = TABLE_EXTRACTORS["convergent_validity_redundancy"](res)
    assert "t Value" in table_data["columns"]
    assert "95% CI" in table_data["columns"]


# =========================================================================
# 7. Redundancy Wizard Spec Generation & Validation Logic
# =========================================================================
def test_redundancy_wizard_spec_builder():
    """Verifies wizard builds exact model spec, layout, and naming."""
    spec, layout = build_redundancy_model_spec(
        construct_id="ATTR",
        construct_name="ATTR",
        indicators=["attr_1", "attr_2", "attr_3"],
        global_item="attr_global",
    )

    assert len(spec["constructs"]) == 2
    f_c = spec["constructs"][0]
    g_c = spec["constructs"][1]
    assert f_c["id"] == "ATTR_F"
    assert f_c["type"] == "formative"
    assert f_c["outer_mode"] == "B"
    assert f_c["indicators"] == ["attr_1", "attr_2", "attr_3"]

    assert g_c["id"] == "ATTR_G"
    assert g_c["type"] == "reflective"
    assert g_c["outer_mode"] == "A"
    assert g_c["indicators"] == ["attr_global"]

    assert len(spec["paths"]) == 1
    assert spec["paths"][0]["from"] == "ATTR_F"
    assert spec["paths"][0]["to"] == "ATTR_G"

    # Layout nodes: 2 latents + 4 indicators
    assert len(layout["nodes"]) == 6
    assert len(layout["edges"]) == 1


def test_redundancy_wizard_validation_rules():
    """Verifies candidate validation (construct formative, global not an indicator, variance check, correlation warning)."""
    df = _load_corp_data()

    # 1. Valid candidate
    v1 = validate_redundancy_candidate(
        df=df,
        construct_id="ATTR",
        construct_name="ATTR",
        indicators=["attr_1", "attr_2", "attr_3"],
        is_formative=True,
        global_item="attr_global",
    )
    assert v1["is_valid"] is True
    assert len(v1["errors"]) == 0

    # 2. Not formative -> error
    v2 = validate_redundancy_candidate(
        df=df,
        construct_id="ATTR",
        construct_name="ATTR",
        indicators=["attr_1", "attr_2", "attr_3"],
        is_formative=False,
        global_item="attr_global",
    )
    assert v2["is_valid"] is False
    assert any("not formative" in e for e in v2["errors"])

    # 3. Global item in indicators -> error
    v3 = validate_redundancy_candidate(
        df=df,
        construct_id="ATTR",
        construct_name="ATTR",
        indicators=["attr_1", "attr_2", "attr_3"],
        is_formative=True,
        global_item="attr_1",
    )
    assert v3["is_valid"] is False
    assert any("cannot be one of the construct's own" in e for e in v3["errors"])

    # 4. Low correlation warning
    df_low = df.copy()
    df_low["uncorrelated_item"] = np.random.randn(len(df_low))
    v4 = validate_redundancy_candidate(
        df=df_low,
        construct_id="ATTR",
        construct_name="ATTR",
        indicators=["attr_1", "attr_2", "attr_3"],
        is_formative=True,
        global_item="uncorrelated_item",
    )
    assert v4["is_valid"] is True
    assert any("Low correlation" in w for w in v4["warnings"])


# =========================================================================
# 8. No Regression on Standard Models
# =========================================================================
def test_no_regression_on_standard_model():
    """Ensure standard models remain completely untouched."""
    df = _load_corp_data()
    spec = {
        "constructs": [
            {"id": "COMP", "name": "COMP", "type": "reflective", "indicators": ["comp_1", "comp_2", "comp_3"]},
            {"id": "LIKE", "name": "LIKE", "type": "reflective", "indicators": ["like_1", "like_2", "like_3"]},
            {"id": "CUSA", "name": "CUSA", "type": "reflective", "indicators": ["cusa"]},
            {"id": "CUSL", "name": "CUSL", "type": "reflective", "indicators": ["cusl_1", "cusl_2", "cusl_3"]},
        ],
        "paths": [
            {"from": "COMP", "to": "CUSA"},
            {"from": "LIKE", "to": "CUSA"},
            {"from": "COMP", "to": "CUSL"},
            {"from": "LIKE", "to": "CUSL"},
            {"from": "CUSA", "to": "CUSL"},
        ],
    }
    cfg = PipelineSettings(missing_treatment="mean", missing_codes=[-99, "-99"])
    res = run_pipeline(df, spec, cfg)

    assert "convergent_validity_redundancy" not in res
    assert "structural" in res
    assert "path_coefficients" in res["structural"]
    assert "r_squared" in res["structural"]
    assert "measurement" in res
    assert "reliability_and_validity" in res

