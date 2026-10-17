"""
End-to-End Smoke Test on Corporate Reputation Reference Dataset:
1. Ingest dataset and screen data
2. Validate model specification
3. Estimate base PLS-SEM model via run_pipeline
4. Complete Bootstrapping (with BCa confidence intervals)
5. Blindfolding Q^2 analysis
6. Mediation analysis (LIKE -> CUSA -> CUSL)
7. Moderation analysis (CUSA -> CUSL moderated by COMP)
8. IPMA analysis
9. Model fit evaluation
10. PLSpredict evaluation
11. Generate PDF report
12. Export table formats
"""

import os
import sys
import pandas as pd
import numpy as np

from data.screening import analyze_missing_data, assess_distributions
from model_spec import ModelSpec
from model_validator import validate_model_spec
from engine.pls.algorithm import run_pipeline
from core.settings_schema import PipelineSettings
from engine.pls.bootstrap import ParallelBootstrapper
from engine.pls.blindfolding import run_blindfolding
from engine.pls.mediation import analyze_mediation
from engine.pls.moderation import analyze_moderation
from engine.pls.ipma import analyze_ipma
from engine.pls.fit import evaluate_model_fit
from engine.pls.predict import run_pls_predict
from reporting.tables import TABLE_EXTRACTORS, export_table_to_format
from reporting.pdf_export import generate_pdf_report


def run_e2e_smoke():
    data_path = os.path.join(os.path.dirname(__file__), "data", "Corporate reputation data.csv")
    if not os.path.exists(data_path):
        print(f"Skipping smoke test: {data_path} not found.")
        return

    print("1. Ingesting and screening reference dataset...")
    df = pd.read_csv(data_path, sep=";")
    assert df.shape == (344, 41)
    df_miss = df.replace([-99, "-99", -99.0], np.nan)
    scr_miss = analyze_missing_data(df_miss)
    assert scr_miss["total_missing_cells"] == 11
    print("   Screening verified 11 missing cells.")

    spec = {
        "constructs": [
            {"id": "COMP", "name": "Competence", "type": "reflective", "indicators": ["comp_1", "comp_2", "comp_3"]},
            {"id": "LIKE", "name": "Likeability", "type": "reflective", "indicators": ["like_1", "like_2", "like_3"]},
            {"id": "CUSA", "name": "Customer Satisfaction", "type": "reflective", "indicators": ["cusa"]},
            {"id": "CUSL", "name": "Customer Loyalty", "type": "reflective", "indicators": ["cusl_1", "cusl_2", "cusl_3"]},
        ],
        "indicators": [
            {"id": "comp_1", "name": "comp_1", "construct_id": "COMP", "column": "comp_1"},
            {"id": "comp_2", "name": "comp_2", "construct_id": "COMP", "column": "comp_2"},
            {"id": "comp_3", "name": "comp_3", "construct_id": "COMP", "column": "comp_3"},
            {"id": "like_1", "name": "like_1", "construct_id": "LIKE", "column": "like_1"},
            {"id": "like_2", "name": "like_2", "construct_id": "LIKE", "column": "like_2"},
            {"id": "like_3", "name": "like_3", "construct_id": "LIKE", "column": "like_3"},
            {"id": "cusa", "name": "cusa", "construct_id": "CUSA", "column": "cusa"},
            {"id": "cusl_1", "name": "cusl_1", "construct_id": "CUSL", "column": "cusl_1"},
            {"id": "cusl_2", "name": "cusl_2", "construct_id": "CUSL", "column": "cusl_2"},
            {"id": "cusl_3", "name": "cusl_3", "construct_id": "CUSL", "column": "cusl_3"},
        ],
        "paths": [
            {"from": "COMP", "to": "CUSA"},
            {"from": "LIKE", "to": "CUSA"},
            {"from": "COMP", "to": "CUSL"},
            {"from": "LIKE", "to": "CUSL"},
            {"from": "CUSA", "to": "CUSL"},
        ],
    }

    print("2. Validating model specification...")
    spec_model = ModelSpec.model_validate(spec)
    v_res = validate_model_spec(spec_model, dataset_columns=list(df.columns))
    assert v_res.is_valid is True
    print("   Model specification is valid.")

    print("3. Estimating base PLS model...")
    cfg = PipelineSettings(
        inner_weighting="path",
        missing_treatment="mean",
        missing_codes=[-99, "-99"],
        sign_convention="dominant",
    )
    res_base = run_pipeline(df, spec, cfg)
    assert res_base["converged"] is True
    assert res_base["iterations"] == 5
    print("   Base model converged in 5 iterations. R2(CUSL) = {:.3f}".format(res_base["structural"]["r_squared"]["CUSL"]))

    print("4. Executing complete bootstrap with BCa intervals...")
    booter = ParallelBootstrapper(n_workers=2, chunk_size=25)
    boot_res = booter.run(df, spec, n_boot=50, seed=42, mode="complete", ci_method="bca")
    res_base["significance"] = boot_res
    assert len(boot_res["parameters"]) > 10
    print("   Bootstrap completed with {} parameters.".format(len(boot_res["parameters"])))

    print("5. Running blindfolding Q2 analysis...")
    b_res = run_blindfolding(df, spec, omission_distance=7, settings=cfg, compute_q2_effects=False)
    c_map = {c["construct_id"]: c for c in b_res["constructs"]}
    assert c_map["CUSL"]["q2_redundancy"] > 0.35
    print("   Blindfolding Q2(CUSL) = {:.3f}".format(c_map["CUSL"]["q2_redundancy"]))

    print("6. Running mediation analysis (LIKE -> CUSA -> CUSL)...")
    med_res = analyze_mediation(df, spec, source="LIKE", target="CUSL", n_boot=30, seed=42, settings=cfg)
    assert med_res["overall_classification"] == "Complementary (partial mediation)"
    print("   Mediation classification: {}".format(med_res["overall_classification"]))

    print("7. Running moderation analysis (CUSA -> CUSL moderated by COMP)...")
    mod_res = analyze_moderation(df, spec, source="CUSA", target="CUSL", moderator="COMP", method="two_stage", n_boot=25, seed=42, settings=cfg)
    assert "simple_slopes" in mod_res
    print("   Moderation simple slopes evaluated successfully.")

    print("8. Running IPMA analysis...")
    ipma_res = analyze_ipma(df, spec, target_construct="CUSL", settings=cfg)
    assert "constructs" in ipma_res
    assert len(ipma_res["constructs"]) > 0
    print("   IPMA evaluated for target CUSL.")

    print("9. Running model fit evaluation...")
    fit_res = evaluate_model_fit(df, spec, res_base)
    assert "saturated_model" in fit_res
    print("   SRMR saturated = {:.3f}".format(fit_res["saturated_model"]["srmr"]))

    print("10. Running PLSpredict evaluation...")
    pred_res = run_pls_predict(df, spec, k_folds=5, repetitions=2, seed=42, settings=cfg)
    assert len(pred_res["indicator_metrics"]) >= 4
    print("   PLSpredict overall predictive power: {}".format(pred_res["overall_predictive_power"]))

    print("11. Generating PDF report...")
    pdf_bytes = generate_pdf_report(res_base, project_name="Corporate Reputation Study", dataset_name="Corporate reputation data.csv", model_name="Simple Model")
    assert pdf_bytes.startswith(b"%PDF-")
    print("   PDF report generated successfully ({} bytes).".format(len(pdf_bytes)))

    print("12. Testing table export to CSV and XLSX...")
    t_paths = TABLE_EXTRACTORS["path_coefficients"](res_base)
    csv_bytes, _, _ = export_table_to_format(t_paths, "csv")
    xlsx_bytes, _, _ = export_table_to_format(t_paths, "xlsx")
    assert len(csv_bytes) > 0 and len(xlsx_bytes) > 0
    print("   Table exports validated.")

    print("\nALL 12 END-TO-END SMOKE TEST PHASES PASSED WITH ZERO ERRORS!")


if __name__ == "__main__":
    run_e2e_smoke()
