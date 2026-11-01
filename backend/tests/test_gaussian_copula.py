"""
Unit, Simulation, and Calibration Tests for Gaussian Copula Endogeneity Analysis.
Tests Sections 9.1 through 9.10 of gaussian_copula_spec.md.
"""

import json
import os
import pytest
import numpy as np
import pandas as pd
from scipy import stats

from engine.pls.copula import (
    f4_ecdf,
    f3_ecdf,
    copula_term,
    copula_matrix,
    cvm_mc_test,
    anderson_darling_test,
    compute_regressor_diagnostics,
    compute_wald_test,
    run_expanded_copula_estimation,
    normalize_gc_spec,
    attach_bootstrap_to_copula,
    CopulaCollinearityError,
)
from engine.pls.algorithm import PLSAlgorithm, run_pipeline
from core.settings_schema import PipelineSettings, GCSettings
from model_spec import ModelSpec, Construct, Indicator, Path, GaussianCopula
from model_validator import validate_model_spec


# ==============================================================================
# Test 1: F4 unit test (Section 9.1)
# ==============================================================================
def test_f4_unit():
    # 1. n=4 example from paper/spec: P=[1, 2, 2, 3] -> F4 = [0.3125, 0.6875, 0.6875, 0.875]
    P = np.array([1, 2, 2, 3])
    expected = np.array([0.3125, 0.6875, 0.6875, 0.875])
    f4 = f4_ecdf(P)
    assert np.allclose(f4, expected, atol=1e-6), f"Expected {expected}, got {f4}"

    # 2. F4(max) == (n - 0.5) / n
    n = len(P)
    assert np.isclose(np.max(f4), (n - 0.5) / n)

    # 3. Strictly inside (0, 1) for various sample sizes
    for sz in [1, 5, 20, 100, 500]:
        x = np.random.randn(sz)
        res = f4_ecdf(x)
        assert np.all(res > 0.0)
        assert np.all(res < 1.0)
        assert np.isclose(np.max(res), (sz - 0.5) / sz)

    # 4. Ties handled as <=
    P_ties = np.array([5.0, 5.0, 5.0])
    res_ties = f4_ecdf(P_ties)
    assert len(set(res_ties)) == 1
    assert np.isclose(res_ties[0], (3 - 0.5) / 3)

    # 5. Invariance to input order
    P_shuffled = np.array([2, 3, 1, 2])
    res_shuffled = f4_ecdf(P_shuffled)
    assert np.isclose(res_shuffled[0], 0.6875)
    assert np.isclose(res_shuffled[1], 0.8750)
    assert np.isclose(res_shuffled[2], 0.3125)
    assert np.isclose(res_shuffled[3], 0.6875)


# ==============================================================================
# Test 2: Copula distribution (Section 9.2)
# ==============================================================================
def test_copula_distribution():
    rng = np.random.default_rng(42)

    # Uniform sample
    u = rng.uniform(0, 10, size=5000)
    c_u = copula_term(u, ecdf="F4")
    # KS test against standard normal N(0, 1)
    ks_u = stats.kstest(c_u, "norm")
    assert ks_u.pvalue > 0.01, f"Uniform copula term failed normality test: p={ks_u.pvalue}"

    # Chi-square sample (heavily skewed)
    chi = rng.chisquare(df=3, size=5000)
    c_chi = copula_term(chi, ecdf="F4")
    ks_chi = stats.kstest(c_chi, "norm")
    assert ks_chi.pvalue > 0.01, f"Chi-square copula term failed normality test: p={ks_chi.pvalue}"

    # Strictly monotone in p
    ranks_orig = stats.rankdata(u)
    ranks_cop = stats.rankdata(c_u)
    assert np.array_equal(ranks_orig, ranks_cop)


# ==============================================================================
# Test 3: Eq. 17 unit test (Section 9.3)
# ==============================================================================
def test_eq17_unit():
    rng = np.random.default_rng(123)
    n = 1000
    p = rng.exponential(scale=2.0, size=n)
    w = rng.gamma(shape=2.0, scale=1.5, size=n)

    scores = {"P": p, "W": w}
    c_p = copula_term(p, ecdf="F4")
    c_w = copula_term(w, ecdf="F4")

    # 1. Single P, single W closed form:
    # {C(P)*s2W - C(W)*sPW} / {s2P*s2W - sPW^2}
    s2P = np.var(c_p, ddof=1)
    s2W = np.var(c_w, ddof=1)
    sPW = np.cov(c_p, c_w, ddof=1)[0, 1]
    denom = s2P * s2W - sPW**2
    expected_1p1w = (c_p * s2W - c_w * sPW) / denom

    cmat_1p1w = copula_matrix(scores, P_names=["P"], W_names=["W"], transform="eq17", ecdf="F4")
    assert cmat_1p1w.shape == (n, 1)
    assert np.allclose(cmat_1p1w[:, 0], expected_1p1w, atol=1e-10)

    # 2. Single P, no W: C(P) / var(C(P))
    expected_1p0w = c_p / np.var(c_p, ddof=1)
    cmat_1p0w = copula_matrix(scores, P_names=["P"], W_names=[], transform="eq17", ecdf="F4")
    assert cmat_1p0w.shape == (n, 1)
    assert np.allclose(cmat_1p0w[:, 0], expected_1p0w, atol=1e-10)

    # 3. Multiple P's: exactly one column per GC-selected path
    scores["P2"] = rng.lognormal(mean=0, sigma=0.5, size=n)
    cmat_2p = copula_matrix(scores, P_names=["P", "P2"], W_names=["W"], transform="eq17", ecdf="F4")
    assert cmat_2p.shape == (n, 2)

    # 4. Singular Sigma raises CopulaCollinearityError
    scores["P_dup"] = p.copy()  # perfect collinearity
    with pytest.raises(CopulaCollinearityError):
        copula_matrix(scores, P_names=["P", "P_dup"], W_names=[], transform="eq17")


# ==============================================================================
# Test 4: Model expansion and validation (Section 9.4)
# ==============================================================================
def test_model_expansion_and_validation():
    base_spec = ModelSpec(
        constructs=[
            Construct(id="X", name="X", indicators=["x1"]),
            Construct(id="Y", name="Y", indicators=["y1"]),
        ],
        indicators=[
            Indicator(id="x1", column="x1"),
            Indicator(id="y1", column="y1"),
        ],
        paths=[
            Path(**{"from": "X", "to": "Y"}),
        ],
        gaussian_copulas=[
            GaussianCopula(id="gc1", source_construct="X", target_construct="Y"),
        ],
    )

    # Valid model passes validation
    val = validate_model_spec(base_spec)
    assert val.is_valid, f"Expected valid model, got errors: {val.errors}"

    # Duplicate GC rejected
    dup_spec = base_spec.model_copy(deep=True)
    dup_spec.gaussian_copulas.append(GaussianCopula(id="gc2", source_construct="X", target_construct="Y"))
    val_dup = validate_model_spec(dup_spec)
    assert not val_dup.is_valid
    assert any("Duplicate Gaussian copula" in e for e in val_dup.errors)

    # Non-existent path rejected
    invalid_path_spec = base_spec.model_copy(deep=True)
    invalid_path_spec.gaussian_copulas = [
        GaussianCopula(id="gc_bad", source_construct="Y", target_construct="X")
    ]
    val_bad = validate_model_spec(invalid_path_spec)
    assert not val_bad.is_valid
    assert any("must attach to an existing structural path" in e for e in val_bad.errors)

    # Serialization round-trip
    dumped = base_spec.model_dump()
    loaded = ModelSpec.model_validate(dumped)
    assert len(loaded.gaussian_copulas) == 1
    assert loaded.gaussian_copulas[0].source_construct == "X"
    assert loaded.gaussian_copulas[0].target_construct == "Y"

    # Backward compatibility: missing gaussian_copulas defaults to empty list
    old_data = {
        "constructs": [{"id": "X", "name": "X", "indicators": ["x1"]}],
        "indicators": [{"id": "x1", "column": "x1"}],
        "paths": [],
    }
    old_model = ModelSpec.model_validate(old_data)
    assert old_model.gaussian_copulas == []


# ==============================================================================
# Test 5: Exactness on single-indicator models (Section 9.5)
# ==============================================================================
def test_exactness_on_single_indicator_models():
    rng = np.random.default_rng(999)
    n = 500
    x = rng.exponential(scale=1.5, size=n)
    m = 0.5 * x + rng.exponential(scale=1.0, size=n)
    y = 0.3 * x + 0.4 * m + rng.normal(0, 1, size=n)

    df = pd.DataFrame({"x": x, "m": m, "y": y})

    spec = {
        "constructs": [
            {"id": "X", "name": "X", "indicators": ["x"]},
            {"id": "M", "name": "M", "indicators": ["m"]},
            {"id": "Y", "name": "Y", "indicators": ["y"]},
        ],
        "indicators": [
            {"id": "x", "column": "x"},
            {"id": "m", "column": "m"},
            {"id": "y", "column": "y"},
        ],
        "paths": [
            {"from": "X", "to": "M"},
            {"from": "X", "to": "Y"},
            {"from": "M", "to": "Y"},
        ],
        "gaussian_copulas": [
            {"id": "gc_xy", "source_construct": "X", "target_construct": "Y"},
            {"id": "gc_my", "source_construct": "M", "target_construct": "Y"},
        ],
    }

    for transform in ["raw", "eq17"]:
        cfg = PipelineSettings(
            inner_weighting="path",
            gc=GCSettings(ecdf="F4", copula_transform=transform, scale_normalization="standardized"),
        )
        res_pls = run_pipeline(df, spec, cfg)
        path_pls = res_pls["structural"]["path_coefficients"]["Y"]

        # Stage 1 scores (single-indicator standardized)
        x_std = (x - np.mean(x)) / np.std(x, ddof=1)
        m_std = (m - np.mean(m)) / np.std(m, ddof=1)
        y_std = (y - np.mean(y)) / np.std(y, ddof=1)

        scores_std = {"X": x_std, "M": m_std}
        eff_tf = "raw" if transform == "eq17" else transform
        cmat = copula_matrix(scores_std, P_names=["X", "M"], W_names=[], transform=eff_tf, ecdf="F4")
        cmat_std = (cmat - np.mean(cmat, axis=0)) / np.std(cmat, axis=0, ddof=1)

        X_mat = np.column_stack([x_std, m_std, cmat_std])
        b_ols, _, _, _ = np.linalg.lstsq(X_mat, y_std, rcond=None)

        assert np.isclose(path_pls["X"], b_ols[0], atol=1e-7)
        assert np.isclose(path_pls["M"], b_ols[1], atol=1e-7)
        assert np.isclose(path_pls["GC (X -> Y)"], b_ols[2], atol=1e-7)
        assert np.isclose(path_pls["GC (M -> Y)"], b_ols[3], atol=1e-7)


# ==============================================================================
# Test 6: Endogeneity recovery simulation (Section 9.6)
# ==============================================================================
def test_endogeneity_recovery_simulation():
    # DGP: y = 3 - 1*P + e, (e, P*) ~ N(0, [[1, .5], [.5, 1]]), P = Phi(P*)
    rng = np.random.default_rng(2025)
    n = 1000
    n_reps = 30
    true_beta = -1.0

    naive_slopes = []
    copula_slopes = []

    for _ in range(n_reps):
        mean = [0.0, 0.0]
        cov = [[1.0, 0.5], [0.5, 1.0]]
        samples = rng.multivariate_normal(mean, cov, size=n)
        e = samples[:, 0]
        p_star = samples[:, 1]
        p = stats.norm.cdf(p_star)  # uniform P
        y = 3.0 + true_beta * p + e

        # Naive OLS (unstandardized)
        slope_naive, _, _, _, _ = stats.linregress(p, y)
        naive_slopes.append(slope_naive)

        # Copula estimation
        c_p = copula_term(p, ecdf="F4")
        X_reg = np.column_stack([np.ones(n), p, c_p])
        b_cop, _, _, _ = np.linalg.lstsq(X_reg, y, rcond=None)
        copula_slopes.append(b_cop[1])

    mean_naive = float(np.mean(naive_slopes))
    mean_copula = float(np.mean(copula_slopes))

    naive_bias = abs(mean_naive - true_beta)
    copula_bias = abs(mean_copula - true_beta)

    # Copula slope must be closer to true beta than naive OLS
    assert copula_bias < naive_bias, f"Copula bias {copula_bias:.4f} not less than naive bias {naive_bias:.4f}"
    # Relative bias < 0.3
    rel_bias = abs((mean_copula - true_beta) / (mean_naive - true_beta))
    assert rel_bias < 0.3, f"Relative bias {rel_bias:.4f} exceeds 0.3"


# ==============================================================================
# Test 7: Bootstrap re-estimation (Section 9.7)
# ==============================================================================
def test_bootstrap_reestimation():
    rng = np.random.default_rng(777)
    n = 200
    x = rng.exponential(scale=1.5, size=n)
    y = 0.5 * x + rng.normal(0, 1, size=n)

    df = pd.DataFrame({"x": x, "y": y})
    spec = {
        "constructs": [
            {"id": "X", "name": "X", "indicators": ["x"]},
            {"id": "Y", "name": "Y", "indicators": ["y"]},
        ],
        "indicators": [
            {"id": "x", "column": "x"},
            {"id": "y", "column": "y"},
        ],
        "paths": [{"from": "X", "to": "Y"}],
        "gaussian_copulas": [{"id": "gc1", "source_construct": "X", "target_construct": "Y"}],
    }

    algo = PLSAlgorithm(scheme="path")
    res = algo.fit(df, spec)
    boot_res = algo.bootstrap(df, spec, n_boot=20, seed=123)
    attach_bootstrap_to_copula(res, boot_res)

    gc_test = res["gaussian_copula"]["endogeneity_tests"][0]
    # SE > 0
    assert gc_test["se"] > 0.0
    # Mean is finite
    assert np.isfinite(gc_test["mean"])

    # Reproducibility with fixed seed
    boot_res2 = algo.bootstrap(df, spec, n_boot=20, seed=123)
    p1 = boot_res["parameters"]["path:GC (X -> Y)->Y"]["mean"]
    p2 = boot_res2["parameters"]["path:GC (X -> Y)->Y"]["mean"]
    assert np.isclose(p1, p2, atol=1e-8)


# ==============================================================================
# Test 8: Wald test (Section 9.8)
# ==============================================================================
def test_wald_test():
    # Strong endogeneity test
    orig_gc = {"GC1": 0.5, "GC2": -0.4}
    # Realistic bootstrap draws with mean near 0.5 and -0.4
    rng = np.random.default_rng(42)
    b_draws = {
        "path:GC1->Y": rng.normal(loc=0.5, scale=0.1, size=100),
        "path:GC2->Y": rng.normal(loc=-0.4, scale=0.1, size=100),
    }
    targets = {"Y": ["GC1", "GC2"]}
    w_res = compute_wald_test(orig_gc, b_draws, targets)

    target_w = next(r for r in w_res if r["target"] == "Y")
    assert target_w["p_value"] < 0.05
    assert target_w["df"] == 2
    assert target_w["statistic"] > 0

    # No endogeneity test (coefficients near 0)
    orig_null = {"GC1": 0.01, "GC2": -0.01}
    b_draws_null = {
        "path:GC1->Y": rng.normal(loc=0.01, scale=0.1, size=100),
        "path:GC2->Y": rng.normal(loc=-0.01, scale=0.1, size=100),
    }
    w_res_null = compute_wald_test(orig_null, b_draws_null, targets)
    target_w_null = next(r for r in w_res_null if r["target"] == "Y")
    assert target_w_null["p_value"] > 0.05

    # Singular V reports not computable
    b_draws_singular = {
        "path:GC1->Y": np.ones(100),
        "path:GC2->Y": np.ones(100),
    }
    w_res_sing = compute_wald_test(orig_gc, b_draws_singular, targets)
    assert w_res_sing[0]["statistic"] is None
    assert "singular" in w_res_sing[0]["note"].lower()


# ==============================================================================
# Test 9: Regressor Diagnostics (Section 9.9)
# ==============================================================================
def test_diagnostics():
    rng = np.random.default_rng(555)

    # Normal sample
    norm_sc = rng.normal(0, 1, size=500)
    # Skewed sample
    skew_sc = rng.exponential(scale=1.0, size=500)

    scores = {"NORM": norm_sc, "SKEW": skew_sc}
    roles = {"NORM": "Endogenous (P)", "SKEW": "Endogenous (P)"}
    distinct = {"NORM": 500, "SKEW": 5}

    diag = compute_regressor_diagnostics(scores, roles, distinct_counts=distinct, n_cases=150)

    d_norm = next(d for d in diag if d["construct"] == "NORM")
    d_skew = next(d for d in diag if d["construct"] == "SKEW")

    assert d_norm["is_non_normal"] is False
    assert "appears normally distributed" in d_norm["flag"]

    assert d_skew["is_non_normal"] is True
    assert "caution with ties" in d_skew["flag"]
    assert "Small sample size" in d_skew["flag"]


# ==============================================================================
# Test 10: SmartPLS calibration (Section 9.10)
# ==============================================================================
def test_smartpls_calibration_corporate_reputation():
    # Load dataset
    data_path = "backend/tests/data/Corporate reputation data.csv"
    alt_data_path = "/Users/punyapratap/Desktop/smartpls_test/Example - Corporate reputation (advanced)/Complete data.txt"

    if os.path.exists(data_path):
        df = pd.read_csv(data_path, sep=None, engine="python")
    elif os.path.exists(alt_data_path):
        df = pd.read_csv(alt_data_path, sep=None, engine="python")
    else:
        pytest.skip("Corporate reputation data not found for calibration test.")

    ref_file = "backend/tests/reference/smartpls_gaussian_copula.json"
    with open(ref_file) as f:
        ref = json.load(f)

    # 4-construct model spec
    spec_4 = {
        "constructs": [
            {"id": "COMP", "name": "COMP", "indicators": ["comp_1", "comp_2", "comp_3"]},
            {"id": "LIKE", "name": "LIKE", "indicators": ["like_1", "like_2", "like_3"]},
            {"id": "CUSA", "name": "CUSA", "indicators": ["cusa"]},
            {"id": "CUSL", "name": "CUSL", "indicators": ["cusl_1", "cusl_2", "cusl_3"]},
        ],
        "indicators": [
            {"id": "comp_1", "column": "comp_1"},
            {"id": "comp_2", "column": "comp_2"},
            {"id": "comp_3", "column": "comp_3"},
            {"id": "like_1", "column": "like_1"},
            {"id": "like_2", "column": "like_2"},
            {"id": "like_3", "column": "like_3"},
            {"id": "cusa", "column": "cusa"},
            {"id": "cusl_1", "column": "cusl_1"},
            {"id": "cusl_2", "column": "cusl_2"},
            {"id": "cusl_3", "column": "cusl_3"},
        ],
        "paths": [
            {"from": "COMP", "to": "CUSA"},
            {"from": "COMP", "to": "CUSL"},
            {"from": "LIKE", "to": "CUSA"},
            {"from": "LIKE", "to": "CUSL"},
            {"from": "CUSA", "to": "CUSL"},
        ],
        "gaussian_copulas": [
            {"id": "gc1", "source_construct": "COMP", "target_construct": "CUSA"},
            {"id": "gc2", "source_construct": "COMP", "target_construct": "CUSL"},
            {"id": "gc3", "source_construct": "LIKE", "target_construct": "CUSA"},
            {"id": "gc4", "source_construct": "LIKE", "target_construct": "CUSL"},
            {"id": "gc5", "source_construct": "CUSA", "target_construct": "CUSL"},
        ],
    }

    results_grid = {}
    print("\n" + "=" * 70)
    print("CALIBRATION GRID EVALUATION: SmartPLS 4 Corporate Reputation")
    print("=" * 70)

    for ecdf in ["F4", "F3"]:
        for transform in ["raw", "eq17"]:
            cfg = PipelineSettings(
                inner_weighting="path",
                gc=GCSettings(ecdf=ecdf, copula_transform=transform),
            )
            res = run_pipeline(df, spec_4, cfg)

            r2_cusa = res["structural"]["r_squared"]["CUSA"]
            r2_cusl = res["structural"]["r_squared"]["CUSL"]
            diff_r2_cusa = abs(r2_cusa - ref["r_squared"]["CUSA"])
            diff_r2_cusl = abs(r2_cusl - ref["r_squared"]["CUSL"])

            p_map = res["structural"]["path_coefficients"]
            path_diffs = [
                abs(p_map["CUSA"]["COMP"] - ref["path_coefficients"]["COMP -> CUSA"]),
                abs(p_map["CUSL"]["COMP"] - ref["path_coefficients"]["COMP -> CUSL"]),
                abs(p_map["CUSA"]["LIKE"] - ref["path_coefficients"]["LIKE -> CUSA"]),
                abs(p_map["CUSL"]["LIKE"] - ref["path_coefficients"]["LIKE -> CUSL"]),
                abs(p_map["CUSL"]["CUSA"] - ref["path_coefficients"]["CUSA -> CUSL"]),
            ]
            max_path_diff = max(path_diffs)

            gc_diffs = [
                abs(p_map["CUSA"]["GC (COMP -> CUSA)"] - ref["gc_coefficients"]["GC (COMP -> CUSA)"]),
                abs(p_map["CUSL"]["GC (COMP -> CUSL)"] - ref["gc_coefficients"]["GC (COMP -> CUSL)"]),
                abs(p_map["CUSA"]["GC (LIKE -> CUSA)"] - ref["gc_coefficients"]["GC (LIKE -> CUSA)"]),
                abs(p_map["CUSL"]["GC (LIKE -> CUSL)"] - ref["gc_coefficients"]["GC (LIKE -> CUSL)"]),
                abs(p_map["CUSL"]["GC (CUSA -> CUSL)"] - ref["gc_coefficients"]["GC (CUSA -> CUSL)"]),
            ]
            max_gc_diff = max(gc_diffs)

            key = f"{ecdf} | {transform}"
            results_grid[key] = {
                "max_path_diff": max_path_diff,
                "max_gc_diff": max_gc_diff,
                "r2_cusa": r2_cusa,
                "r2_cusl": r2_cusl,
            }
            print(f"Option {key:<12}: Max Path Diff = {max_path_diff:.4f}, Max GC Diff = {max_gc_diff:.4f}, R2 CUSA = {r2_cusa:.3f}, R2 CUSL = {r2_cusl:.3f}")

    print("=" * 70)

    # Verify best match is F4 | raw
    best = results_grid["F4 | raw"]
    assert best["max_path_diff"] < 0.02, f"F4 raw path diff {best['max_path_diff']} exceeds 0.02 tolerance"
    assert np.isclose(best["r2_cusa"], ref["r_squared"]["CUSA"], atol=0.001)
    assert np.isclose(best["r2_cusl"], ref["r_squared"]["CUSL"], atol=0.001)

