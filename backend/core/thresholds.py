"""
Textbook thresholds and rules of thumb (Appendix B & Rule 7).
All values reference Hair, Hult, Ringle, Sarstedt (2017) 2nd Edition.
"""

from typing import Dict, Any

THRESHOLDS: Dict[str, Dict[str, Any]] = {
    # Ch. 4: Reflective measurement model evaluation
    "outer_loading": {
        "retain": 0.708,  # Ch. 4: 0.70 acceptable, 0.708 gives indicator reliability >= 0.50
        "evaluate_min": 0.40,  # 0.40 to 0.70: consider deletion only if it increases CR or AVE
        "remove_below": 0.40,  # < 0.40: delete indicator unless content validity demands retention
    },
    # Ch. 4: Internal consistency reliability
    "internal_consistency": {
        "satisfactory_min": 0.70,  # 0.70 to 0.90 is satisfactory
        "satisfactory_max": 0.90,
        "exploratory_min": 0.60,   # 0.60 to 0.70 acceptable in exploratory research
        "redundant_threshold": 0.95, # > 0.95 indicates redundant items (undesirable)
        "poor_threshold": 0.60,      # < 0.60 lacks internal consistency
    },
    # Ch. 4: Convergent validity
    "ave": {
        "acceptable_min": 0.50,  # Average Variance Extracted >= 0.50 (communality >= 50%)
    },
    # Ch. 4: Discriminant validity (HTMT)
    "htmt": {
        "conservative": 0.85,  # For conceptually distinct constructs (e.g. attitude vs behavior)
        "liberal": 0.90,       # For conceptually very similar constructs
        "ci_upper_limit": 1.0, # 95% bootstrap CI must not include 1.0
    },
    # Ch. 5: Formative measurement model evaluation
    "formative_collinearity": {
        "vif_ideal": 3.0,      # VIF < 3 ideal
        "vif_critical": 5.0,   # VIF >= 5.0 (tolerance <= 0.20) indicates critical collinearity
        "bivariate_r_flag": 0.60, # Bivariate correlation > 0.60 flags potential collinearity
        "condition_index_flag": 30.0, # Condition index > 30 flags collinearity
    },
    # Ch. 5: Redundancy analysis
    "redundancy_analysis": {
        "path_min": 0.708,     # Formative -> Global reflective path >= 0.70 (ideally >= 0.80)
        "r2_min": 0.50,        # Equivalent R^2 >= 0.50
    },
    # Ch. 5: Formative indicator relevance
    "formative_relevance": {
        "loading_relevance": 0.50, # If weight is not sig, loading >= 0.50 warrants retention
    },
    # Ch. 6: Structural model collinearity
    "inner_vif": {
        "vif_critical": 5.0,   # Predictor inner VIF >= 5 indicates critical collinearity
        "tolerance_critical": 0.20,
    },
    # Ch. 6: Coefficient of determination R^2
    "r_squared": {
        "weak": 0.25,          # R^2 = 0.25 weak (marketing research benchmark)
        "moderate": 0.50,      # R^2 = 0.50 moderate
        "substantial": 0.75,   # R^2 = 0.75 substantial
    },
    # Ch. 6: f^2 and q^2 effect sizes
    "f_squared": {
        "small": 0.02,
        "medium": 0.15,
        "large": 0.35,
    },
    "q_squared_effect": {
        "small": 0.02,
        "medium": 0.15,
        "large": 0.35,
    },
    # Ch. 6: Q^2 predictive relevance (Blindfolding)
    "q_squared": {
        "relevant_min": 0.0,   # Q^2 > 0 indicates predictive relevance
    },
    # Ch. 7: Moderation effect size (Kenny 2016 / Aguinis et al.)
    "moderation_f2": {
        "small": 0.005,
        "medium": 0.010,
        "large": 0.025,
    },
    # Ch. 6: Model fit measures
    "model_fit": {
        "srmr_max": 0.08,      # Standardized Root Mean Square Residual < 0.08
        "rms_theta_max": 0.12, # RMS_theta < 0.12 for reflective models
    },
    # Ch. 2: Data screening
    "data_screening": {
        "missing_case_max_pct": 15.0,     # Remove cases with > 15% missing values
        "missing_indicator_max_pct": 5.0, # Flag indicators with > 5% missing values
        "skewness_textbook_max": 1.0,     # |skewness| > 1 indicates non-normality
        "kurtosis_textbook_max": 1.0,     # |excess kurtosis| > 1 indicates non-normality
        "outlier_iqr_multiplier": 3.0,    # Values beyond 3 * IQR from Q1/Q3 are extreme outliers
    },
    # Ch. 1: Sample size rules
    "sample_size": {
        "ten_times_rule_multiplier": 10,  # 10 times max arrowheads pointing at a construct
    },
    # Dul (2016): Necessary Condition Analysis
    "nca": {
        "small": 0.10,
        "medium": 0.30,
        "large": 0.50,
    },
}
