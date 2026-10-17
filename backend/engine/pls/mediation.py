"""
Mediation Analysis (Section 15: MED-01 to MED-09).
Source of truth: Hair et al. (2017) Ch. 7 & Zhao, Lynch & Chen (2010).
Analyzes direct, specific indirect, total indirect, and total effects with bootstrapping,
Zhao et al. classification, and optional Sobel test.
"""

from typing import List, Dict, Any, Optional, Tuple, Union
import math
import numpy as np
import pandas as pd
from scipy import stats

from core.settings_schema import PipelineSettings
from engine.pls.algorithm import run_pipeline
from engine.pls.bootstrap import ParallelBootstrapper


def classify_mediation(
    indirect_sig: bool,
    direct_sig: bool,
    indirect_coef: float,
    direct_coef: float,
) -> Dict[str, str]:
    """
    Classifies mediation type according to Zhao, Lynch & Chen (2010) decision tree (MED-05).
    """
    if indirect_sig:
        if direct_sig:
            sign_product = direct_coef * indirect_coef
            if sign_product > 0:
                classification = "Complementary (partial mediation)"
                interpretation = (
                    "Both indirect and direct effects are significant and point in the same direction. "
                    "The mediator partially explains the relationship between source and target."
                )
            else:
                classification = "Competitive (partial mediation)"
                interpretation = (
                    "Both indirect and direct effects are significant but point in opposite directions. "
                    "The mediator acts as a suppressor variable."
                )
        else:
            classification = "Indirect-only (full mediation)"
            interpretation = (
                "The indirect effect is significant while the direct effect is not. "
                "The mediator fully accounts for the relationship between source and target."
            )
    else:
        if direct_sig:
            classification = "Direct-only (no mediation)"
            interpretation = (
                "The direct effect is significant while the indirect effect is not. "
                "There is no evidence of mediation via the proposed path."
            )
        else:
            classification = "No-effect (no mediation)"
            interpretation = (
                "Neither the direct effect nor the indirect effect is significant. "
                "There is no relationship between source and target."
            )

    return {
        "classification": classification,
        "interpretation": interpretation,
    }


def compute_sobel_test(
    a_coef: float,
    b_coef: float,
    a_se: float,
    b_se: float,
) -> Dict[str, Any]:
    """
    Calculates the classical Sobel test for a single-mediator link (MED-04).
    z = (a * b) / sqrt(b^2 * se_a^2 + a^2 * se_b^2)
    """
    denom = math.sqrt(max(1e-12, (b_coef ** 2) * (a_se ** 2) + (a_coef ** 2) * (b_se ** 2)))
    z_stat = (a_coef * b_coef) / denom
    p_val = 2.0 * (1.0 - stats.norm.cdf(abs(z_stat)))

    return {
        "z_statistic": round(float(z_stat), 4),
        "p_value": round(float(p_val), 4),
        "is_significant": p_val < 0.05,
        "warning": (
            "The Sobel test assumes a normal distribution for the indirect product term, "
            "which is frequently violated in finite samples. Non-parametric bootstrapping "
            "(BCa confidence interval) is strongly recommended as the primary basis for inference."
        ),
    }


def analyze_mediation(
    df: pd.DataFrame,
    spec: Union[Dict[str, Any], Any],
    source_construct: Optional[str] = None,
    target_construct: Optional[str] = None,
    source: Optional[str] = None,
    target: Optional[str] = None,
    n_boot: int = 500,
    seed: Optional[int] = 42,
    alpha: float = 0.05,
    include_sobel: bool = False,
    settings: Optional[PipelineSettings] = None,
    progress_callback: Optional[Any] = None,
    cancel_event: Optional[Any] = None,
) -> Dict[str, Any]:
    """
    Executes a complete mediation analysis between source_construct and target_construct.
    """
    src = source_construct or source
    tgt = target_construct or target
    if not src or not tgt:
        raise ValueError("Both source and target constructs must be specified.")
    source_construct = src
    target_construct = tgt

    spec_dict = spec.model_dump(by_alias=True) if hasattr(spec, "model_dump") else (spec if isinstance(spec, dict) else {})
    cfg = settings or PipelineSettings()

    # 1. Main model estimation
    res_main = run_pipeline(df, spec_dict, cfg)
    paths_main = res_main.get("structural", {}).get("path_coefficients", {})
    effects_decomp = res_main.get("effects_decomposition", {})

    # Direct effect in model with mediators
    direct_coef = float(paths_main.get(target_construct, {}).get(source_construct, 0.0))

    # Identify all specific indirect effects from source to target
    all_spec_ind = effects_decomp.get("specific_indirect", [])
    relevant_spec_ind = [
        p for p in all_spec_ind
        if p.get("source") == source_construct and p.get("target") == target_construct
    ]

    total_indirect_coef = sum(float(p.get("effect", 0.0)) for p in relevant_spec_ind)
    total_effect_coef = direct_coef + total_indirect_coef

    # 2. Run bootstrapping to obtain significance of direct, specific indirect, and total indirect
    booter = ParallelBootstrapper()
    boot_res = booter.run(
        data=df,
        model_spec=spec_dict,
        n_boot=n_boot,
        seed=seed,
        scheme=cfg.inner_weighting,
        mode="complete",
        sign_change="none",
        alpha=alpha,
        progress_callback=progress_callback,
        cancel_event=cancel_event,
    )

    param_summary = boot_res.get("parameter_summary", {})

    # Evaluate direct effect significance
    direct_key = f"path:{source_construct}->{target_construct}"
    direct_stat = param_summary.get(direct_key, {})
    direct_p = direct_stat.get("p_value", 1.0)
    direct_sig = direct_p < alpha

    # Evaluate total indirect significance
    tot_ind_key = f"total_indirect:{source_construct}->{target_construct}"
    tot_ind_stat = param_summary.get(tot_ind_key, {})
    tot_ind_p = tot_ind_stat.get("p_value", 1.0)
    tot_ind_sig = tot_ind_p < alpha

    # Specific indirect effects analysis
    specific_indirect_results: List[Dict[str, Any]] = []
    for item in relevant_spec_ind:
        path_str = item.get("path")
        eff_val = float(item.get("effect", 0.0))
        p_key = f"specific_indirect:{path_str}"
        p_stat = param_summary.get(p_key, {})

        p_val = p_stat.get("p_value", 1.0)
        p_sig = p_val < alpha
        se_val = p_stat.get("standard_error", 0.0)
        t_val = p_stat.get("t_statistic", 0.0)
        ci_lower = p_stat.get("ci_lower", 0.0)
        ci_upper = p_stat.get("ci_upper", 0.0)

        # Classification for this specific path
        classif = classify_mediation(
            indirect_sig=p_sig,
            direct_sig=direct_sig,
            indirect_coef=eff_val,
            direct_coef=direct_coef,
        )

        entry = {
            "path": path_str,
            "path_nodes": item.get("path_nodes", []),
            "original_effect": round(eff_val, 4),
            "bootstrap_mean": round(float(p_stat.get("bootstrap_mean", eff_val)), 4),
            "standard_error": round(float(se_val), 4),
            "t_statistic": round(float(t_val), 4),
            "p_value": round(float(p_val), 4),
            "ci_lower": round(float(ci_lower), 4),
            "ci_upper": round(float(ci_upper), 4),
            "is_significant": p_sig,
            "classification": classif["classification"],
            "interpretation": classif["interpretation"],
        }

        # Optional Sobel test if path has exactly 1 mediator (source -> M -> target)
        nodes = item.get("path_nodes", [])
        if include_sobel and len(nodes) == 3:
            med_construct = nodes[1]
            a_key = f"path:{source_construct}->{med_construct}"
            b_key = f"path:{med_construct}->{target_construct}"
            a_stat = param_summary.get(a_key, {})
            b_stat = param_summary.get(b_key, {})
            if a_stat and b_stat:
                entry["sobel_test"] = compute_sobel_test(
                    a_coef=float(a_stat.get("original", 0.0)),
                    b_coef=float(b_stat.get("original", 0.0)),
                    a_se=float(a_stat.get("standard_error", 0.0)),
                    b_se=float(b_stat.get("standard_error", 0.0)),
                )

        specific_indirect_results.append(entry)

    # Overall mediation classification based on total indirect effect
    overall_classification = classify_mediation(
        indirect_sig=tot_ind_sig,
        direct_sig=direct_sig,
        indirect_coef=total_indirect_coef,
        direct_coef=direct_coef,
    )

    # Variance Accounted For (VAF = indirect / total)
    vaf = (total_indirect_coef / total_effect_coef) if abs(total_effect_coef) > 1e-12 else None
    vaf_val = round(float(vaf * 100), 2) if vaf is not None else None

    # Auxiliary: direct effect in model WITHOUT mediators
    direct_without_mediators = None
    try:
        # Build reduced model: direct path source -> target only (exclude mediators)
        mediator_cids = set()
        for p in relevant_spec_ind:
            for node in p.get("path_nodes", [])[1:-1]:
                mediator_cids.add(node)

        red_paths = [
            p for p in spec_dict.get("paths", [])
            if not ((p.get("from") or p.get("from_node")) in mediator_cids or (p.get("to") or p.get("to_node")) in mediator_cids)
        ]
        red_spec = dict(spec_dict)
        red_spec["paths"] = red_paths
        res_aux = run_pipeline(df, red_spec, cfg)
        direct_without_mediators = round(float(res_aux.get("structural", {}).get("path_coefficients", {}).get(target_construct, {}).get(source_construct, 0.0)), 4)
    except Exception:
        direct_without_mediators = None

    return {
        "source": source_construct,
        "target": target_construct,
        "direct_effect": {
            "coefficient": round(direct_coef, 4),
            "standard_error": round(float(direct_stat.get("standard_error", 0.0)), 4),
            "t_statistic": round(float(direct_stat.get("t_statistic", 0.0)), 4),
            "p_value": round(float(direct_p), 4),
            "ci_lower": round(float(direct_stat.get("ci_lower", 0.0)), 4),
            "ci_upper": round(float(direct_stat.get("ci_upper", 0.0)), 4),
            "is_significant": direct_sig,
        },
        "total_indirect_effect": {
            "coefficient": round(total_indirect_coef, 4),
            "standard_error": round(float(tot_ind_stat.get("standard_error", 0.0)), 4),
            "t_statistic": round(float(tot_ind_stat.get("t_statistic", 0.0)), 4),
            "p_value": round(float(tot_ind_p), 4),
            "ci_lower": round(float(tot_ind_stat.get("ci_lower", 0.0)), 4),
            "ci_upper": round(float(tot_ind_stat.get("ci_upper", 0.0)), 4),
            "is_significant": tot_ind_sig,
        },
        "total_effect": {
            "coefficient": round(total_effect_coef, 4),
        },
        "direct_effect_without_mediators": direct_without_mediators,
        "specific_indirect_effects": specific_indirect_results,
        "overall_classification": overall_classification["classification"],
        "overall_interpretation": overall_classification["interpretation"],
        "vaf_percentage": vaf_val,
        "vaf_note": "VAF (Variance Accounted For) is reported for informational purposes; modern guidelines rely on bootstrap confidence intervals for classification (Zhao et al. 2010; Hair et al. 2017).",
    }
