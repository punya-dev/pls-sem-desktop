"""
Phase 6 Unit and Integration Tests:
- Statistical Power and Sample Size (Section 24: SAM-01 to SAM-05)
- Gaussian Copula Endogeneity (Section 25: X-A, X-01)
- Necessary Condition Analysis (Section 25: X-B, X-02)
- PLSpredict (Section 25: X-C, X-03)
- Table Exports (Section 26: REP-01)
- Summary Templates (Section 26: REP-02)
- Narrative Generator (Section 26: REP-04)
- PDF Report Generator (Section 26: REP-05)
"""

import pytest
import numpy as np
import pandas as pd

from engine.pls.algorithm import run_pipeline
from engine.pls.power import (
    calculate_ten_times_rule,
    compute_statistical_power,
    solve_minimum_sample_size,
    get_cohen_appendix_c_table,
    evaluate_model_power,
)
from engine.pls.copula import analyze_gaussian_copula, test_non_normality as assess_non_normality, compute_copula_term
from engine.pls.nca import analyze_nca, compute_ce_fdh, compute_cr_fdh
from engine.pls.predict import run_pls_predict
from reporting.tables import (
    TABLE_EXTRACTORS,
    export_table_to_format,
    extract_path_coefficients_table,
    extract_outer_loadings_table,
    extract_reliability_table,
)
from reporting.templates import (
    build_reflective_summary,
    build_discriminant_validity_summary,
    build_structural_summary,
    build_fit_summary,
)
from reporting.narrative import generate_narrative_report
from reporting.pdf_export import generate_pdf_report


@pytest.fixture
def synthetic_predict_data():
    np.random.seed(42)
    n = 120
    # True latent scores
    x1 = np.random.normal(0, 1, n)
    x2 = np.random.normal(0, 1, n)
    y1 = 0.5 * x1 + 0.3 * x2 + np.random.normal(0, 0.4, n)

    df = pd.DataFrame({
        "x1_1": x1 + np.random.normal(0, 0.2, n),
        "x1_2": x1 + np.random.normal(0, 0.2, n),
        "x2_1": x2 + np.random.normal(0, 0.2, n),
        "x2_2": x2 + np.random.normal(0, 0.2, n),
        "y1_1": y1 + np.random.normal(0, 0.2, n),
        "y1_2": y1 + np.random.normal(0, 0.2, n),
    })

    spec = {
        "constructs": [
            {"id": "X1", "name": "Exogenous 1", "type": "reflective", "indicators": ["x1_1", "x1_2"]},
            {"id": "X2", "name": "Exogenous 2", "type": "reflective", "indicators": ["x2_1", "x2_2"]},
            {"id": "Y1", "name": "Endogenous 1", "type": "reflective", "indicators": ["y1_1", "y1_2"]},
        ],
        "paths": [
            {"from": "X1", "to": "Y1"},
            {"from": "X2", "to": "Y1"},
        ],
    }
    return df, spec


def test_power_calculations():
    # 1. 10-times rule
    tt = calculate_ten_times_rule(max_formative_indicators=3, max_paths_into_construct=4)
    assert tt["ten_times_rule_min_n"] == 40
    assert tt["inverse_square_root_method"]["min_path_0_10"] > 600

    # 2. Power computation (Cohen benchmark)
    # 2 predictors, R2 = 0.25 (f2 = 0.333), N = 100
    pwr = compute_statistical_power(n_samples=100, n_predictors=2, r_squared=0.25, alpha=0.05)
    assert pwr > 0.95

    # 3. Solve minimum sample size for 80% power
    min_n = solve_minimum_sample_size(n_predictors=2, r_squared=0.25, target_power=0.80, alpha=0.05)
    assert 30 <= min_n <= 50  # Cohen Appendix C table value is around 33-39

    # 4. Cohen Appendix C Table
    app_c = get_cohen_appendix_c_table(target_power=0.80, alpha=0.05)
    assert len(app_c["table"]) == 10
    row_2 = [r for r in app_c["table"] if r["predictors"] == 2][0]
    assert "r2_25" in row_2
    assert row_2["r2_25"] > 20


def test_copula_endogeneity(synthetic_predict_data):
    df, spec = synthetic_predict_data

    # Direct unit test of copula term computation
    arr = np.array([0.1, 0.5, 1.2, 3.4, 8.9, 15.0])
    cop_t = compute_copula_term(arr)
    assert len(cop_t) == len(arr)
    assert not np.isnan(cop_t).any()

    # Test non-normality assessment function
    n_res = assess_non_normality(arr)
    assert "is_non_normal" in n_res

    # Endogeneity analysis
    res = analyze_gaussian_copula(
        df=df,
        spec=spec,
        candidate_predictor="X1",
        target_construct="Y1",
        n_boot=20,
        seed=42,
    )
    assert "candidate_predictor" in res
    assert "target_construct" in res
    if res.get("applicable"):
        assert "copula_coefficient" in res
        assert "p_value" in res
        assert "endogeneity_detected" in res
    else:
        assert "na_reason" in res


def test_nca_analysis(synthetic_predict_data):
    df, spec = synthetic_predict_data

    res = analyze_nca(
        df=df,
        spec=spec,
        predictor="X1",
        outcome="Y1",
        n_permutations=50,
        seed=42,
    )
    assert "effect_size_d_ce" in res
    assert "effect_size_d_cr" in res
    assert "p_value" in res
    assert "bottleneck_table" in res
    assert len(res["bottleneck_table"]) == 11


def test_pls_predict(synthetic_predict_data):
    df, spec = synthetic_predict_data

    res = run_pls_predict(
        df=df,
        model_spec=spec,
        k_folds=5,
        repetitions=2,
        seed=42,
    )
    assert "indicator_metrics" in res
    assert "construct_summary" in res
    assert "overall_predictive_power" in res
    assert len(res["indicator_metrics"]) >= 2

    # Check metric fields
    m1 = res["indicator_metrics"][0]
    assert "q2_predict" in m1
    assert "rmse_pls" in m1
    assert "rmse_lm" in m1
    assert "pls_beats_lm" in m1


def test_reporting_tables_and_export(synthetic_predict_data):
    df, spec = synthetic_predict_data
    results = run_pipeline(df, spec)

    # Path coefficients table
    t_paths = extract_path_coefficients_table(results)
    assert t_paths["title"] == "Path Coefficients"
    assert len(t_paths["columns"]) >= 2
    assert len(t_paths["rows"]) >= 1

    # Reliability table
    t_rel = extract_reliability_table(results)
    assert t_rel["title"] == "Construct Reliability and Validity"
    assert len(t_rel["rows"]) == 3

    # Export formats
    csv_bytes, media_csv, fn_csv = export_table_to_format(t_paths, "csv")
    assert media_csv == "text/csv"
    assert b"From / To" in csv_bytes

    tsv_bytes, media_tsv, fn_tsv = export_table_to_format(t_paths, "tsv")
    assert media_tsv == "text/tab-separated-values"
    assert b"\t" in tsv_bytes

    xlsx_bytes, media_xlsx, fn_xlsx = export_table_to_format(t_paths, "xlsx")
    assert media_xlsx.startswith("application/vnd.openxmlformats")
    assert len(xlsx_bytes) > 100

    clip_bytes, media_txt, _ = export_table_to_format(t_paths, "clipboard_text")
    assert media_txt == "text/plain"

    json_bytes, media_json, _ = export_table_to_format(t_paths, "json")
    assert media_json == "application/json"


def test_reporting_narrative_and_pdf(synthetic_predict_data):
    df, spec = synthetic_predict_data
    results = run_pipeline(df, spec)

    # Narrative
    narrative = generate_narrative_report(results, style="apa")
    assert "# PLS-SEM Empirical Results" in narrative
    assert "Reflective Measurement Model Assessment" in narrative
    assert "Discriminant Validity" in narrative
    assert "Structural Model Evaluation" in narrative

    # Summary templates
    t_ref = build_reflective_summary(results)
    assert len(t_ref["columns"]) == 9
    t_disc = build_discriminant_validity_summary(results)
    assert len(t_disc["rows"]) >= 1
    t_struct = build_structural_summary(results)
    assert len(t_struct["rows"]) >= 2
    t_fit = build_fit_summary(results)
    assert len(t_fit["rows"]) >= 4

    # PDF generation
    pdf_bytes = generate_pdf_report(
        results=results,
        project_name="Test Project",
        dataset_name="Test Dataset",
        model_name="Test Model",
    )
    assert isinstance(pdf_bytes, bytes)
    assert pdf_bytes.startswith(b"%PDF-")
    assert len(pdf_bytes) > 1000
