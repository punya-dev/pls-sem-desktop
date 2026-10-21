"""
Unit and Integration Tests for Phase 1: Data, Import, Screening, Imputation, and Project Management.
(PRJ-01..09, DAT-01..12, SCR-01..10, MIS-01..07)
"""

import os
import io
import json
import tempfile
import numpy as np
import pandas as pd
import pytest

from data.importer import (
    ImportSettings,
    raw_file_preview,
    parse_dataframe,
    preview_import_data,
    clean_column_names,
)
from data.screening import (
    analyze_missing_data,
    detect_suspicious_patterns,
    detect_outliers,
    assess_distributions,
    calculate_histogram,
    reverse_code_column,
    assess_directionality,
)
from data.imputation import (
    mean_imputation,
    em_imputation,
    knn_imputation,
)
from data.derived import (
    apply_derivation,
    create_derived_dataset,
    split_by_group,
)
from data.datasets import (
    save_dataset,
    load_dataset,
    list_datasets,
)
import project_io
from model_spec import ModelSpec, Construct, Indicator


@pytest.fixture
def corp_rep_csv_path():
    p = os.path.join(os.path.dirname(__file__), "data", "Corporate reputation data.csv")
    if not os.path.exists(p):
        pytest.skip("Corporate reputation data.csv not found")
    return p


def test_clean_column_names():
    cols = ["col", "col", "  spaced name  ", "", "unnamed", "col"]
    cleaned = clean_column_names(cols)
    assert cleaned == ["col", "col_2", "spaced_name", "Col_4", "Col_5", "col_3"]


def test_raw_preview_and_importer():
    sample_csv = b"id;qual_1;qual_2;score\n1;4.5;3.2;10\n2;3.0;.;12\n3;-99;4.1;15\n"
    preview = raw_file_preview(sample_csv)
    assert preview["detected_delimiter"] == ";"
    assert len(preview["raw_lines"]) == 4

    settings = ImportSettings(delimiter=";", missing_codes=["-99", "."], treat_dot_as_missing=True)
    df, col_meta, issues, used = parse_dataframe(sample_csv, "test.csv", settings)
    assert df.shape == (3, 4)
    assert np.isnan(df.loc[1, "qual_2"])  # "." treated as missing
    assert np.isnan(df.loc[2, "qual_1"])  # "-99" treated as missing
    assert df.loc[0, "score"] == 10.0


def test_european_decimal_comma():
    sample_csv = b"item1;item2\n3,5;4,2\n2,1;1,8\n"
    settings = ImportSettings(delimiter=";", decimal=",")
    df, col_meta, issues, used = parse_dataframe(sample_csv, "test.csv", settings)
    assert df.loc[0, "item1"] == 3.5
    assert df.loc[1, "item2"] == 1.8


def test_corporate_reputation_import_and_missing_counts(corp_rep_csv_path):
    """
    Acceptance test 27.1 / MIS-07:
    Authentic Corporate reputation dataset (344 cases, missing codes -99).
    Verifies that cusa, cusl_1, cusl_2, cusl_3 have exact missing counts matching textbook.
    """
    with open(corp_rep_csv_path, "rb") as f:
        file_bytes = f.read()

    settings = ImportSettings(delimiter=";", missing_codes=["-99"])
    df, col_meta, issues, settings_used = parse_dataframe(file_bytes, "Corporate reputation data.csv", settings)

    assert df.shape[0] == 344
    assert df.shape[1] == 41

    # Book missing values check:
    # In corporate reputation data: cusa has 1 missing, cusl_1 has 3 missing, cusl_2 has 4 missing, cusl_3 has 3 missing
    assert int(df["cusa"].isna().sum()) == 1
    assert int(df["cusl_1"].isna().sum()) == 3
    assert int(df["cusl_2"].isna().sum()) == 4
    assert int(df["cusl_3"].isna().sum()) == 3

    # Total missing values across indicators in simple model
    simple_indicators = ["cusa", "cusl_1", "cusl_2", "cusl_3", "comp_1", "comp_2", "comp_3", "like_1", "like_2", "like_3"]
    total_missing = df[simple_indicators].isna().sum().sum()
    assert total_missing == 11


def test_data_screening_missing():
    df = pd.DataFrame({
        "x1": [1.0, 2.0, np.nan, 4.0, 5.0] * 10,  # 20% missing -> flagged (>5%)
        "x2": [1.0, 2.0, 3.0, 4.0, 5.0] * 10,     # 0% missing
        "x3": [np.nan] * 10 + [1.0] * 40,         # 20% missing -> flagged
    })
    res = analyze_missing_data(df, indicator_threshold_pct=5.0, case_threshold_pct=15.0)
    assert "x1" in res["flagged_indicators"]
    assert "x3" in res["flagged_indicators"]
    assert "x2" not in res["flagged_indicators"]
    assert res["n_cases"] == 50
    assert len(res["issues"]) > 0


def test_data_screening_suspicious_patterns():
    df = pd.DataFrame({
        "item1": [4.0, 1.0, 2.0],
        "item2": [4.0, 2.0, 3.0],
        "item3": [4.0, 3.0, 5.0],
        "item4": [4.0, 4.0, 1.0],
    })
    res = detect_suspicious_patterns(df)
    # Row 0 has straight lining (all 4.0)
    # Row 1 has diagonal lining (1, 2, 3, 4)
    patterns = {p["row_index"]: p["pattern"] for p in res["flagged_cases"]}
    assert patterns[0] == "straight_lining"
    assert patterns[1] == "diagonal_lining"


def test_data_screening_outliers():
    vals = [10.0, 10.2, 10.1, 9.9, 10.0, 10.3, 9.8, 10.1, 10.0, 50.0]  # 50.0 is an extreme outlier
    df = pd.DataFrame({"y": vals})
    res = detect_outliers(df)
    assert res["y"]["n_extreme_outliers"] >= 1
    assert res["y"]["extreme_outliers"][0]["value"] == 50.0


def test_data_screening_distributions():
    np.random.seed(42)
    normal_data = np.random.normal(loc=5.0, scale=1.0, size=200)
    skewed_data = np.random.exponential(scale=2.0, size=200)
    df = pd.DataFrame({"normal": normal_data, "skewed": skewed_data})

    res = assess_distributions(df, rule_set="textbook")
    col_dict = {c["column"]: c for c in res["columns"]}

    assert col_dict["skewed"]["skew_flagged"] is True
    assert col_dict["normal"]["skew_flagged"] is False


def test_histogram_and_reverse_coding():
    s = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0, np.nan])
    rev, s_min, s_max = reverse_code_column(s, scale_min=1.0, scale_max=5.0)
    # 1 -> 5, 2 -> 4, 3 -> 3, 4 -> 2, 5 -> 1
    assert rev.iloc[0] == 5.0
    assert rev.iloc[4] == 1.0
    assert np.isnan(rev.iloc[5])

    df = pd.DataFrame({"rating": [1, 2, 2, 3, 4, 5, 5, 5]})
    hist = calculate_histogram(df, "rating", bins=5)
    assert len(hist["counts"]) == 5
    assert len(hist["normal_curve"]) > 0


def test_imputation_algorithms():
    df = pd.DataFrame({
        "a": [1.0, 2.0, np.nan, 4.0, 5.0],
        "b": [2.0, 4.0, 6.0, np.nan, 10.0],
    })
    # Mean imputation
    df_mean, n_mean = mean_imputation(df)
    assert n_mean == 2
    assert df_mean.isna().sum().sum() == 0
    assert df_mean.loc[2, "a"] == 3.0  # mean of 1, 2, 4, 5 = 3.0

    # EM imputation
    df_em, n_em, iters = em_imputation(df, max_iter=20)
    assert n_em == 2
    assert df_em.isna().sum().sum() == 0

    # kNN imputation
    df_knn, n_knn = knn_imputation(df, k=2)
    assert n_knn == 2
    assert df_knn.isna().sum().sum() == 0


def test_derived_datasets_and_lineage():
    with tempfile.TemporaryDirectory() as tmp_dir:
        proj_path = os.path.join(tmp_dir, "test_proj.pls")
        project_io.create_project(proj_path, "Test Project")

        # Save initial dataset
        df = pd.DataFrame({
            "group": ["A", "A", "B", "B", "B"],
            "score": [10.0, 12.0, 20.0, 22.0, 25.0],
        })
        import sqlite3
        conn = sqlite3.connect(proj_path)
        save_dataset(conn, "1", "Main Data", df)

        # Create derived dataset with casewise / filter
        derived_meta = create_derived_dataset(
            conn,
            parent_id="1",
            name="Group B Only",
            operation="filter_rows",
            params={"filters": [{"column": "group", "op": "==", "value": "B"}]},
        )
        assert derived_meta["name"] == "Group B Only"
        assert derived_meta["parent_id"] == "1"
        assert derived_meta["n_rows"] == 3

        # List datasets
        datasets = list_datasets(conn)
        assert len(datasets) == 2
        conn.close()

        # Check project tree (PRJ-02)
        tree = project_io.get_project_tree(proj_path)
        assert len(tree["datasets"]) == 1  # Root dataset "Main Data"
        assert len(tree["datasets"][0]["children"]) == 1  # Child "Group B Only"
        assert tree["datasets"][0]["children"][0]["name"] == "Group B Only"


def test_project_zip_export_and_import():
    with tempfile.TemporaryDirectory() as tmp_dir:
        proj_path = os.path.join(tmp_dir, "archive_test.pls")
        project_io.create_project(proj_path, "Archive Test")

        # Add data
        df = pd.DataFrame({"x": [1, 2, 3], "y": [4, 5, 6]})
        import sqlite3
        conn = sqlite3.connect(proj_path)
        save_dataset(conn, "1", "Dataset_One", df)
        conn.close()

        # Export zip
        zip_path = os.path.join(tmp_dir, "archive.zip")
        project_io.export_project_zip(proj_path, zip_path)
        assert os.path.exists(zip_path)

        # Import into another workspace
        import_ws = os.path.join(tmp_dir, "new_workspace")
        imported_proj_path = project_io.import_project_zip(zip_path, import_ws)
        assert os.path.exists(imported_proj_path)

        # Verify dataset in imported project
        conn_imp = sqlite3.connect(imported_proj_path)
        imp_ds = load_dataset(conn_imp, "1")
        assert imp_ds is not None
        assert imp_ds["n_rows"] == 3
        conn_imp.close()
