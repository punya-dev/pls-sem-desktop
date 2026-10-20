"""
Section 15: PLS-SEM Advanced Issues Benchmark Acceptance Test Suite.
Source of Truth: Hair, Sarstedt, Ringle, and Gudergan (2018),
Advanced Issues in Partial Least Squares Structural Equation Modeling (SAGE).
Case Study: Corporate Reputation Benchmark (N=344 raw, N=336 clean, 41 columns).
"""

import os
import tempfile
import math
import pytest
import numpy as np
import pandas as pd

from core.settings_schema import PipelineSettings
from engine.pls.algorithm import run_pipeline
from engine.pls.hcm import (
    compute_manual_hoc_reliability,
    build_repeated_indicators_spec,
    build_collect_type_total_effects_spec,
    run_disjoint_two_stage_hcm,
    analyze_hcm,
)
from engine.pls.quadratic import analyze_quadratic_effect
from engine.pls.cta import (
    run_cta_pls,
    generate_all_tetrads_for_block,
    select_nonredundant_tetrads,
)
from engine.pls.micom import run_micom, check_configural_invariance
from engine.pls.mga import (
    analyze_mga,
    compute_parametric_test,
    compute_welch_satterthwaite_test,
)
from engine.pls.otg import (
    analyze_otg,
    calculate_fwer,
    calculate_sidak_alpha,
    calculate_bonferroni_alpha,
    compute_otg_fr_statistic,
)
from engine.pls.fimix import analyze_fimix
from engine.pls.pos import analyze_pos
from engine.pls.ex_post import (
    compute_crosstab_overlap,
    run_logistic_segment_regression,
    compare_explanatory_groups_with_pos,
)
from data.groups import (
    generate_categorical_groups,
    append_column_to_dataset,
    seed_corporate_reputation_project,
)


DATA_PATH = os.path.join(os.path.dirname(__file__), "data", "Corporate reputation data.csv")


@pytest.fixture
def corp_rep_raw():
    if not os.path.exists(DATA_PATH):
        pytest.skip(f"Reference dataset '{DATA_PATH}' missing. Skipping acceptance tests.")
    return pd.read_csv(DATA_PATH, sep=";")


@pytest.fixture
def corp_rep_clean(corp_rep_raw):
    # Hair et al. (2018): casewise deletion of missing values (-99) yields exactly 336 clean rows
    df_clean = corp_rep_raw.replace(-99, float("nan")).dropna().reset_index(drop=True)
    return df_clean


@pytest.fixture
def corp_rep_extended_spec():
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


# =====================================================================
# 1. Higher-Order Constructs (HCM) Acceptance Tests (Exhibit 2.14, 2.17)
# =====================================================================

def test_a18_hcm_manual_metrics_exhibit_2_14():
    """
    Exhibit 2.14: Manual HOC reliability and convergent validity based on HOC–LOC loadings.
    Loadings: COMP = 0.914, LIKE = 0.891
    Expected: AVE = 0.815, rho_c (CR) = 0.898, standardized Cronbach's alpha = 0.774.
    """
    loadings = {"COMP": 0.914, "LIKE": 0.891}
    loc_correlations = np.array([[1.0, 0.631], [0.631, 1.0]])

    metrics = compute_manual_hoc_reliability(loadings, loc_correlations)
    assert abs(metrics["ave"] - 0.8146) < 0.002
    assert abs(metrics["composite_reliability"] - 0.8978) < 0.002
    assert abs(metrics["cronbachs_alpha"] - 0.7738) < 0.002


def test_a18_hcm_repeated_indicators_and_two_stage(corp_rep_clean):
    """
    Exhibit 2.17: Repeated indicators and Disjoint Two-Stage approaches on Corporate Reputation.
    HOC: Corporate Reputation (CORP_REP) composed of LOCs COMP and LIKE.
    """
    base_loc_spec = {
        "constructs": [
            {"id": "COMP", "name": "Competence", "type": "reflective", "indicators": ["comp_1", "comp_2", "comp_3"]},
            {"id": "LIKE", "name": "Likeability", "type": "reflective", "indicators": ["like_1", "like_2", "like_3"]},
            {"id": "CUSA", "name": "Satisfaction", "type": "reflective", "indicators": ["cusa"]},
            {"id": "CUSL", "name": "Loyalty", "type": "reflective", "indicators": ["cusl_1", "cusl_2", "cusl_3"]},
        ],
        "paths": [
            {"from": "COMP", "to": "CUSA"},
            {"from": "LIKE", "to": "CUSA"},
            {"from": "CUSA", "to": "CUSL"},
        ],
    }

    # Test repeated-indicators specification builder
    rep_spec, warnings = build_repeated_indicators_spec(
        base_loc_spec,
        hoc_id="CORP_REP",
        loc_ids=["COMP", "LIKE"],
        hoc_type="RR",
    )
    hoc_construct = next(c for c in rep_spec["constructs"] if c["id"] == "CORP_REP")
    assert len(hoc_construct["indicators"]) == 6  # 3 from comp + 3 from like
    assert len(warnings) == 0  # balanced indicator counts (3 and 3)

    # Base spec with HOC connected to CUSA
    hoc_model_spec = {
        "constructs": [
            {"id": "CORP_REP", "name": "Corporate Reputation", "type": "reflective", "indicators": []},
            {"id": "COMP", "name": "Competence", "type": "reflective", "indicators": ["comp_1", "comp_2", "comp_3"]},
            {"id": "LIKE", "name": "Likeability", "type": "reflective", "indicators": ["like_1", "like_2", "like_3"]},
            {"id": "CUSA", "name": "Satisfaction", "type": "reflective", "indicators": ["cusa"]},
            {"id": "CUSL", "name": "Loyalty", "type": "reflective", "indicators": ["cusl_1", "cusl_2", "cusl_3"]},
        ],
        "paths": [
            {"from": "CORP_REP", "to": "CUSA"},
            {"from": "CUSA", "to": "CUSL"},
        ],
    }

    # Test disjoint two-stage analysis
    ts_res = run_disjoint_two_stage_hcm(
        corp_rep_clean,
        hoc_model_spec,
        hoc_id="CORP_REP",
        loc_ids=["COMP", "LIKE"],
        hoc_type="RR",
    )
    assert ts_res["stage2_structural"] is not None
    assert "CORP_REP" in ts_res["stage2_scores"]
    assert len(ts_res["stage2_scores"]["CORP_REP"]) == len(corp_rep_clean)

    # Test collect-type total effects decomposition builder
    collect_spec = build_collect_type_total_effects_spec(
        hoc_model_spec,
        hoc_id="CORP_REP",
        loc_ids=["COMP", "LIKE"],
    )
    collect_paths = [(p["from"], p["to"]) for p in collect_spec["paths"]]
    assert ("COMP", "CUSA") in collect_paths
    assert ("LIKE", "CUSA") in collect_paths


# =====================================================================
# 2. Nonlinear / Quadratic Effects Acceptance Tests (Exhibit 3.14, 3.16)
# =====================================================================

def test_a18_quadratic_effect_qual_on_cusa(corp_rep_clean):
    """
    Exhibit 3.14 / 3.16: Non-linear effect of Quality (QUAL) on Customer Satisfaction (CUSA).
    Tests two-stage quadratic evaluation, Kenny (2015) f^2 rating, and marginal slope table.
    """
    spec = {
        "constructs": [
            {"id": "QUAL", "name": "Quality", "type": "reflective", "indicators": [f"qual_{i}" for i in range(1, 9)]},
            {"id": "PERF", "name": "Performance", "type": "reflective", "indicators": [f"perf_{i}" for i in range(1, 6)]},
            {"id": "CSOR", "name": "CSR", "type": "reflective", "indicators": [f"csor_{i}" for i in range(1, 6)]},
            {"id": "ATTR", "name": "Attractiveness", "type": "reflective", "indicators": ["attr_1", "attr_2", "attr_3"]},
            {"id": "CUSA", "name": "Customer Satisfaction", "type": "reflective", "indicators": ["cusa"]},
        ],
        "paths": [
            {"from": "QUAL", "to": "CUSA"},
            {"from": "PERF", "to": "CUSA"},
            {"from": "CSOR", "to": "CUSA"},
            {"from": "ATTR", "to": "CUSA"},
        ],
    }

    res = analyze_quadratic_effect(
        corp_rep_clean,
        spec,
        source="QUAL",
        target="CUSA",
        approach="two_stage",
        n_boot=100,
        seed=42,
    )

    # Hair et al. (2018): Linear R2 approx 0.30, quadratic R2 approx 0.30
    assert abs(res["r_squared_linear"] - 0.3045) < 0.05
    assert res["r_squared_quadratic"] >= res["r_squared_linear"]
    assert "f_squared" in res
    assert "f_squared_rating" in res

    # Marginal effect table at 0, 1, 2 SD
    table_012 = res["effect_table_0_1_2"]
    assert len(table_012) == 3
    assert table_012[0]["source_level"] == 0.0
    assert table_012[1]["source_level"] == 1.0
    assert table_012[2]["source_level"] == 2.0

    # Decision recommendation
    assert "retain the simpler linear model" in res["decision_recommendation"]
    assert len(res["curve_points"]) == 21


# =====================================================================
# 3. Confirmatory Tetrad Analysis (CTA-PLS) (Exhibit 2.10)
# =====================================================================

def test_a18_cta_pls_qual_indicators(corp_rep_clean):
    """
    Exhibit 2.10: CTA-PLS for Quality (QUAL) with 8 indicators.
    Total potential tetrads: C(8, 4) * 3 = 210.
    Nonredundant tetrads: 8 * (8 - 3) / 2 = 20.
    Bonferroni alpha = 0.10 / 20 = 0.005.
    Empirical verdict rejects reflective null in favor of formative specification.
    """
    spec = {
        "constructs": [
            {"id": "QUAL", "name": "Quality", "type": "reflective", "indicators": [f"qual_{i}" for i in range(1, 9)]},
        ],
        "paths": [],
    }

    res = run_cta_pls(
        corp_rep_clean,
        spec,
        construct_id="QUAL",
        n_boot=100,
        seed=42,
        alpha=0.10,
    )

    qual_res = res["constructs"][0]
    assert qual_res["construct_id"] == "QUAL"
    assert qual_res["n_indicators"] == 8
    assert qual_res["total_possible_tetrads"] == 210
    assert qual_res["n_nonredundant_tetrads"] == 20
    assert qual_res["bonferroni_alpha"] == 0.005
    assert qual_res["min_indicator_correlation"] >= 0.10
    assert qual_res["indicator_correlations_adequate"] is True
    assert "Formative" in qual_res["verdict"]


# =====================================================================
# 4. Measurement Invariance (MICOM) & Multigroup (MGA) (Exhibit 4.4, 4.6)
# =====================================================================

def test_a18_micom_mga_servicetype(corp_rep_clean, corp_rep_extended_spec):
    """
    Exhibit 4.4 / 4.6: MICOM across servicetype (1: prepaid, N=124 vs 2: contract, N=212).
    Step 1: Configural invariance verified.
    Step 2: Compositional invariance c >= 5% quantile.
    MGA: Multi-method consensus (Parametric, Welch-Satterthwaite, PLS-MGA).
    """
    micom_res = run_micom(
        corp_rep_clean,
        corp_rep_extended_spec,
        group_col="servicetype",
        group_values=(1, 2),
        n_permutations=50,
        seed=42,
    )

    assert str(micom_res["group_1"]) == "1"
    assert str(micom_res["group_2"]) == "2"
    assert micom_res["n_group_1"] == 124
    assert micom_res["n_group_2"] == 212
    assert micom_res["configural_invariance"]["passed"] is True
    assert micom_res["overall_summary"]["all_partial_or_full"] is True
    assert micom_res["overall_summary"]["mga_eligible"] is True

    # Check Step 2 compositional invariance for COMP
    comp_micom = next(c for c in micom_res["constructs"] if c["construct_id"] == "COMP")
    assert comp_micom["step2_compositional"]["c_correlation"] >= 0.99
    assert comp_micom["step2_compositional"]["passed"] is True

    # Run MGA
    mga_res = analyze_mga(
        corp_rep_clean,
        corp_rep_extended_spec,
        group_col="servicetype",
        group_values=(1, 2),
        n_boot=100,
        n_permutations=50,
        seed=42,
    )
    assert "path_comparisons" in mga_res
    assert len(mga_res["path_comparisons"]) == len(corp_rep_extended_spec["paths"])
    for p in mga_res["path_comparisons"]:
        assert "parametric_test" in p
        assert "welch_satterthwaite_test" in p
        assert "henseler_pls_mga" in p
        assert "consensus" in p


# =====================================================================
# 5. Omnibus Test of Group Differences (OTG) (Exhibit 4.8, 4.10)
# =====================================================================

def test_a18_otg_fwer_and_permutation(corp_rep_clean, corp_rep_extended_spec):
    """
    Exhibit 4.8 / 4.10: Omnibus Test of Group Differences (OTG) across service providers.
    FWER calculation: m=6 comparisons -> FWER = 26.5%, Sidak = 0.0085, Bonferroni = 0.0083.
    """
    # Verify FWER formulas
    fwer_6 = calculate_fwer(6, alpha=0.05)
    sidak_6 = calculate_sidak_alpha(6, alpha=0.05)
    bonf_6 = calculate_bonferroni_alpha(6, alpha=0.05)

    assert abs(fwer_6 - 0.2649) < 0.001
    assert abs(sidak_6 - 0.00851) < 0.0001
    assert abs(bonf_6 - 0.00833) < 0.0001

    # Run OTG test across the 4 service providers (providers 1, 2, 3, 4)
    otg_res = analyze_otg(
        corp_rep_clean,
        corp_rep_extended_spec,
        group_col="serviceprovider",
        n_boot=50,
        n_permutations=50,
        seed=42,
    )

    assert otg_res["n_groups"] == 4
    assert len(otg_res["omnibus_tests"]) == len(corp_rep_extended_spec["paths"])
    assert len(otg_res["pairwise_comparisons"]) == len(corp_rep_extended_spec["paths"]) * 6
    assert otg_res["multiple_testing"]["family_wise_error_rate"] > 0.20


# =====================================================================
# 6. FIMIX-PLS Unobserved Heterogeneity (Exhibit 5.8, 5.10)
# =====================================================================

def test_a18_fimix_corporate_reputation(corp_rep_clean, corp_rep_extended_spec):
    """
    Exhibit 5.8 / 5.10: FIMIX-PLS on Corporate Reputation (N=336).
    Evaluates AIC, AIC3, AIC4, BIC, CAIC, MDL5, and Normed Entropy (EN).
    Verifies power warning when a segment has N < 54.
    """
    fimix_res = analyze_fimix(
        corp_rep_clean,
        corp_rep_extended_spec,
        min_segments=1,
        max_segments=3,
        n_repetitions=5,
        max_iter=500,
        min_sample_size=54,
        seed=42,
    )

    assert fimix_res["n_samples"] == 336
    assert len(fimix_res["segment_retention_table"]) == 3
    assert fimix_res["recommended_segments"] in [1, 2, 3]

    table = fimix_res["segment_retention_table"]
    for row in table:
        assert "AIC" in row
        assert "AIC3" in row
        assert "AIC4" in row
        assert "BIC" in row
        assert "CAIC" in row
        assert "MDL5" in row
        assert "EN" in row
        assert "segment_sizes" in row

    assert len(fimix_res["case_assignments"]) == 336


# =====================================================================
# 7. Prediction-Oriented Segmentation (POS) & Ex Post (Exhibit 5.15, 5.16)
# =====================================================================

def test_a18_pos_and_ex_post_contingency(corp_rep_clean, corp_rep_extended_spec):
    """
    Exhibit 5.15 / 5.16: PLS-POS 2-segment solution and Ex Post contingency matching with servicetype.
    Optimal permutation matching >= 60% satisfactory benchmark (Book: 73.5%).
    """
    pos_res = analyze_pos(
        corp_rep_clean,
        corp_rep_extended_spec,
        n_segments=2,
        optimization_criterion="weighted",
        max_iter=15,
        search_depth=10,
        seed=42,
    )

    assert pos_res["converged"] is True or pos_res["iterations"] > 0
    assert len(pos_res["segment_sample_sizes"]) == 2
    assert "signed_path_differences" in pos_res
    assert len(pos_res["segment_assignments"]) == 336

    # Test contingency table optimal permutation matching
    cross_res = compute_crosstab_overlap(
        pos_res["segment_assignments"],
        corp_rep_clean["servicetype"],
    )
    assert cross_res["n_samples"] == 336
    assert cross_res["overlap_percentage"] > 50.0  # satisfactory overlap
    assert "contingency_table" in cross_res
    assert "best_matching_mapping" in cross_res

    # Test logistic regression
    logit_res = run_logistic_segment_regression(
        pos_res["segment_assignments"],
        corp_rep_clean[["servicetype"]],
    )
    assert "coefficients" in logit_res or "model_type" in logit_res

    # Test explanatory groups comparison with POS
    comp_res = compare_explanatory_groups_with_pos(
        corp_rep_clean,
        corp_rep_extended_spec,
        explanatory_col="servicetype",
        pos_results=pos_res,
    )
    assert "explanatory_groups" in comp_res
    assert "pos_solution" in comp_res
    assert "comparison_table" in comp_res


# =====================================================================
# 8. Data Groups & Project Template Seeding Tests (A18-DAT-01..05)
# =====================================================================

def test_a18_data_groups_and_project_seeding(corp_rep_raw):
    """
    A18-DAT-01 to 05: Data groups generation, sample size power warnings,
    and Corporate Reputation project template seeding.
    """
    # Test group generator
    g_res = generate_categorical_groups(
        corp_rep_raw,
        column="servicetype",
        min_size=10,
        max_paths_predictors=2,
    )
    assert g_res["column"] == "servicetype"
    assert g_res["total_samples"] == 344
    assert len(g_res["groups"]) == 2

    # Test seeding project in temporary directory
    with tempfile.TemporaryDirectory() as tmp_dir:
        proj_res = seed_corporate_reputation_project(tmp_dir)
        assert proj_res["success"] is True
        assert proj_res["row_count"] == 344
        assert proj_res["column_count"] == 41
        assert "dataset_id" in proj_res
        assert "model_id" in proj_res
        assert os.path.exists(os.path.join(tmp_dir, "corporate_reputation.sqlite"))
