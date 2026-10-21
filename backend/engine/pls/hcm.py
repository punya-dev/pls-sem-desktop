"""
Hierarchical Component Models (HCM / Higher-Order Constructs) (A18-HCM-01 to A18-HCM-20).
Source of truth: Hair et al. (2018) Ch. 2 & Becker et al. (2012).

Supports:
1. Four HCM types: RR (reflective-reflective), RF (reflective-formative), FR (formative-reflective), and FF (formative-formative).
2. Repeated-Indicators approach and Disjoint Two-Stage approach.
3. Manual HOC reliability and convergent validity based on HOC–LOC loadings:
   - AVE = mean of squared loadings
   - Composite reliability rho_c = (sum l_i)^2 / [ (sum l_i)^2 + sum (1 - l_i^2) ]
   - Standardized Cronbach's alpha = M * r_bar / [ 1 + (M - 1) * r_bar ]
4. Becker et al. (2012) collect-type total effects analysis for endogenous formative HOCs.
5. Lohmöller premature convergence detection and weighting scheme presets (factor weighting for 2018 preset).
"""

from typing import List, Dict, Any, Optional, Tuple, Union
import math
import numpy as np
import pandas as pd

from core.settings_schema import PipelineSettings
from engine.pls.algorithm import run_pipeline, calculate_vif


def build_repeated_indicators_spec(
    spec_dict: Dict[str, Any],
    hoc_id: str,
    loc_ids: List[str],
    hoc_type: str = "RR",  # "RR", "RF", "FR", "FF"
) -> Tuple[Dict[str, Any], List[str]]:
    """
    Constructs a repeated-indicators model specification (A18-HCM-04).
    The HOC receives all indicators of its lower-order components (LOCs).
    """
    warnings: List[str] = []
    loc_inds_map: Dict[str, List[str]] = {}

    from engine.pls.algorithm import parse_model_spec
    constructs_dict, ind_col_map, paths_list = parse_model_spec(spec_dict)

    for cid in loc_ids:
        if cid in constructs_dict:
            c_info = constructs_dict[cid]
            loc_inds_map[cid] = [
                ind_col_map.get(iid, iid)
                for iid in c_info.get("indicators", [])
            ]

    # Indicator count balance check (A18-HCM-06)
    counts = [len(inds) for inds in loc_inds_map.values()]
    if len(set(counts)) > 1:
        warnings.append(
            f"LOC indicator counts are unequal ({dict(zip(loc_inds_map.keys(), counts))}). "
            f"The HOC will be disproportionately biased toward the LOC with more indicators. "
            f"Consider equalizing indicators or using the two-stage approach (Hair et al. 2018)."
        )

    all_hoc_inds = []
    for inds in loc_inds_map.values():
        for ind in inds:
            if ind not in all_hoc_inds:
                all_hoc_inds.append(ind)

    hoc_mode = "formative" if hoc_type in ("RF", "FF") else "reflective"

    # Endogenous formative HOC warning (A18-HCM-09)
    paths = spec_dict.get("paths", [])
    external_antecedents = [
        (p.get("from") or p.get("from_node"))
        for p in paths
        if (p.get("to") or p.get("to_node")) == hoc_id and (p.get("from") or p.get("from_node")) not in loc_ids
    ]

    if hoc_type in ("RF", "FF") and external_antecedents:
        warnings.append(
            f"INADMISSIBLE SETUP (Exhibit 2.12): Formative HOC '{hoc_id}' has external antecedent constructs "
            f"({external_antecedents}). The LOCs will explain almost 100% of the HOC variance (R² ≈ 1.0), "
            f"forcing antecedent paths near zero and rendering them non-significant. "
            f"Use the Becker et al. (2012) total effects analysis or the two-stage approach instead."
        )

    # Clone constructs and update/add HOC
    new_constructs = []
    hoc_found = False
    for c in spec_dict.get("constructs", []):
        if c["id"] == hoc_id:
            c_copy = dict(c)
            c_copy["indicators"] = all_hoc_inds
            c_copy["type"] = hoc_mode
            c_copy["outer_mode"] = "B" if hoc_mode == "formative" else "A"
            c_copy["order"] = "higher"
            c_copy["components"] = loc_ids
            c_copy["hoc_type"] = hoc_type
            new_constructs.append(c_copy)
            hoc_found = True
        else:
            new_constructs.append(c)

    if not hoc_found:
        new_constructs.append({
            "id": hoc_id,
            "name": hoc_id,
            "type": hoc_mode,
            "outer_mode": "B" if hoc_mode == "formative" else "A",
            "order": "higher",
            "components": loc_ids,
            "hoc_type": hoc_type,
            "indicators": all_hoc_inds,
        })

    # Add paths between HOC and LOCs:
    # Reflective HOC (RR, FR): HOC -> LOC (Spread model)
    # Formative HOC (RF, FF): LOC -> HOC (Collect model)
    new_paths = list(spec_dict.get("paths", []))
    for loc_id in loc_ids:
        if hoc_type in ("RR", "FR"):
            if not any((p.get("from") or p.get("from_node")) == hoc_id and (p.get("to") or p.get("to_node")) == loc_id for p in new_paths):
                new_paths.append({"from": hoc_id, "to": loc_id})
        else:
            if not any((p.get("from") or p.get("from_node")) == loc_id and (p.get("to") or p.get("to_node")) == hoc_id for p in new_paths):
                new_paths.append({"from": loc_id, "to": hoc_id})

    new_spec = {
        "constructs": new_constructs,
        "indicators": list(spec_dict.get("indicators", [])),
        "paths": new_paths,
    }

    return new_spec, warnings


def build_collect_type_total_effects_spec(
    spec_dict: Dict[str, Any],
    hoc_id: str,
    loc_ids: List[str],
) -> Dict[str, Any]:
    """
    Builds the Becker et al. (2012) collect-type total effects structure (A18-HCM-10):
    Adds paths from each external antecedent to each LOC of the HOC, while retaining direct paths to the HOC.
    """
    paths = list(spec_dict.get("paths", []))
    external_antecedents = []
    downstream_targets = []

    for p in paths:
        fc = p.get("from") or p.get("from_node")
        tc = p.get("to") or p.get("to_node")
        if tc == hoc_id and fc not in loc_ids and fc not in external_antecedents:
            external_antecedents.append(fc)
        elif fc == hoc_id and tc not in loc_ids and tc not in downstream_targets:
            downstream_targets.append(tc)

    new_paths = list(paths)
    for ant in external_antecedents:
        for loc in loc_ids:
            if not any((p.get("from") or p.get("from_node")) == ant and (p.get("to") or p.get("to_node")) == loc for p in new_paths):
                new_paths.append({"from": ant, "to": loc})

    for tgt in downstream_targets:
        for loc in loc_ids:
            if not any((p.get("from") or p.get("from_node")) == loc and (p.get("to") or p.get("to_node")) == tgt for p in new_paths):
                new_paths.append({"from": loc, "to": tgt})

    return {
        "constructs": list(spec_dict.get("constructs", [])),
        "indicators": list(spec_dict.get("indicators", [])),
        "paths": new_paths,
    }


def compute_manual_hoc_reliability(
    hoc_loc_loadings: Dict[str, float],
    loc_correlations: np.ndarray,
) -> Dict[str, float]:
    """
    Computes manual HOC measurement model metrics based on HOC–LOC loadings (A18-HCM-15):
    - AVE = mean of squared loadings
    - Composite Reliability rho_c = (sum l_i)^2 / [ (sum l_i)^2 + sum (1 - l_i^2) ]
    - Standardized Cronbach's alpha = M * r_bar / [ 1 + (M - 1) * r_bar ]
    """
    loadings = np.array(list(hoc_loc_loadings.values()), dtype=float)
    M = len(loadings)
    if M == 0:
        return {"ave": 0.0, "composite_reliability": 0.0, "cronbachs_alpha": 0.0}

    # AVE: mean of squared loadings (Book: (0.914^2 + 0.891^2)/2 = 0.815)
    ave = float(np.mean(loadings ** 2))

    # Composite reliability rho_c
    sum_l = float(np.sum(loadings))
    sum_l_sq = sum_l ** 2
    sum_var_e = float(np.sum(1.0 - (loadings ** 2)))
    cr = float(sum_l_sq / (sum_l_sq + sum_var_e)) if (sum_l_sq + sum_var_e) > 1e-12 else 0.0

    # Standardized Cronbach's alpha: based on average off-diagonal correlation among LOCs
    if M > 1 and loc_correlations.size > 1:
        off_diag = []
        for u in range(M):
            for v in range(u + 1, M):
                off_diag.append(loc_correlations[u, v])
        r_bar = float(np.mean(off_diag)) if off_diag else 0.5
        alpha = float((M * r_bar) / (1.0 + (M - 1.0) * r_bar))
    else:
        alpha = 1.0

    return {
        "ave": round(ave, 4),
        "composite_reliability": round(cr, 4),
        "cronbachs_alpha": round(alpha, 4),
    }


def run_disjoint_two_stage_hcm(
    df: pd.DataFrame,
    spec_dict: Dict[str, Any],
    hoc_id: str,
    loc_ids: List[str],
    hoc_type: str = "RF",
    settings: Optional[PipelineSettings] = None,
) -> Dict[str, Any]:
    """
    Executes Disjoint Two-Stage HCM estimation (A18-HCM-11, A18-HCM-12).
    Stage 1: LOCs connected directly to other constructs.
    Stage 2: LOC scores become manifest indicators of the HOC.
    """
    cfg = settings or PipelineSettings()

    # Stage 1: LOCs connected directly to what HOC was connected to
    stage1_paths = []
    for p in spec_dict.get("paths", []):
        fc = p.get("from") or p.get("from_node")
        tc = p.get("to") or p.get("to_node")
        if fc == hoc_id:
            for loc in loc_ids:
                stage1_paths.append({"from": loc, "to": tc})
        elif tc == hoc_id:
            for loc in loc_ids:
                stage1_paths.append({"from": fc, "to": loc})
        else:
            stage1_paths.append(p)

    stage1_constructs = [c for c in spec_dict.get("constructs", []) if c["id"] != hoc_id]
    stage1_spec = {
        "constructs": stage1_constructs,
        "indicators": spec_dict.get("indicators", []),
        "paths": stage1_paths,
    }

    res_stage1 = run_pipeline(df, stage1_spec, cfg)
    scores_stage1 = res_stage1.get("construct_scores", {})

    # Stage 2: Create dataset with standardized LOC scores as manifest indicators
    df_stage2 = df.copy()
    stage2_hoc_inds = []
    for loc_id in loc_ids:
        col_name = f"score_{loc_id}"
        loc_score = np.asarray(scores_stage1.get(loc_id, np.zeros(len(df))), dtype=float)
        loc_score_std = (loc_score - np.mean(loc_score)) / (np.std(loc_score, ddof=0) or 1.0)
        df_stage2[col_name] = loc_score_std
        stage2_hoc_inds.append(col_name)

    hoc_mode = "formative" if hoc_type in ("RF", "FF") else "reflective"

    stage2_constructs = [c for c in stage1_constructs if c["id"] not in loc_ids] + [{
        "id": hoc_id,
        "name": hoc_id,
        "type": hoc_mode,
        "outer_mode": "B" if hoc_mode == "formative" else "A",
        "order": "higher",
        "components": loc_ids,
        "hoc_type": hoc_type,
        "indicators": stage2_hoc_inds,
    }]

    stage2_paths = []
    for p in spec_dict.get("paths", []):
        fc = p.get("from") or p.get("from_node")
        tc = p.get("to") or p.get("to_node")
        if fc not in loc_ids and tc not in loc_ids:
            stage2_paths.append(p)

    stage2_indicators = [
        ind for ind in spec_dict.get("indicators", [])
        if (ind.get("construct_id") or ind.get("construct")) not in loc_ids
    ] + [{"name": col_name, "construct_id": hoc_id} for col_name in stage2_hoc_inds]

    stage2_spec = {
        "constructs": stage2_constructs,
        "indicators": stage2_indicators,
        "paths": stage2_paths,
    }

    res_stage2 = run_pipeline(df_stage2, stage2_spec, cfg)

    meas2 = res_stage2.get("measurement", {})
    weights2 = meas2.get("outer_weights", {}).get(hoc_id, {})
    loadings2 = meas2.get("outer_loadings", {}).get(hoc_id, {})

    hoc_assessment: Dict[str, Any] = {
        "hoc_type": hoc_type,
        "approach": "two_stage",
        "loc_indicators": stage2_hoc_inds,
        "outer_weights": weights2,
        "outer_loadings": loadings2,
    }

    if hoc_mode == "formative":
        X_locs = np.column_stack([df_stage2[col].values for col in stage2_hoc_inds])
        if len(stage2_hoc_inds) > 1:
            vifs = calculate_vif(X_locs)
            hoc_assessment["collinearity_vif"] = {
                loc: round(float(v), 4) for loc, v in zip(loc_ids, vifs)
            }
    else:
        rel2 = res_stage2.get("reliability_and_validity", {})
        hoc_assessment["cronbachs_alpha"] = rel2.get("cronbachs_alpha", {}).get(hoc_id)
        hoc_assessment["composite_reliability"] = rel2.get("composite_reliability", {}).get(hoc_id)
        hoc_assessment["ave"] = rel2.get("ave", {}).get(hoc_id)

    return {
        "hoc_id": hoc_id,
        "loc_ids": loc_ids,
        "hoc_type": hoc_type,
        "approach": "two_stage",
        "hoc_assessment": hoc_assessment,
        "stage1_results": res_stage1,
        "stage2_results": res_stage2,
        "stage2_structural": res_stage2.get("structural"),
        "stage2_scores": res_stage2.get("construct_scores", {}),
    }


def analyze_hcm(
    df: pd.DataFrame,
    spec: Union[Dict[str, Any], Any],
    hoc_id: str,
    loc_ids: List[str],
    hoc_type: str = "RR",  # "RR", "RF", "FR", "FF"
    approach: str = "repeated_indicators",  # "repeated_indicators", "two_stage", "total_effects"
    inner_weighting: Optional[str] = None,  # Default "factor" for 2018 preset
    settings: Optional[PipelineSettings] = None,
) -> Dict[str, Any]:
    """
    Main entry point for Hierarchical Component Model analysis (A18-HCM-01 to A18-HCM-20).
    """
    spec_dict = spec.model_dump(mode="json", by_alias=True) if hasattr(spec, "model_dump") else (spec if isinstance(spec, dict) else {})
    cfg = settings or PipelineSettings()

    # 2018 Preset: recommend factor weighting scheme (A18-HCM-07)
    if inner_weighting:
        cfg.inner_weighting = inner_weighting
    elif cfg.inner_weighting == "centroid":
        raise ValueError(
            "Centroid weighting is not supported for Hierarchical Component Models (A18-HCM-07). "
            "Please select 'factor' (recommended by Hair et al. 2018) or 'path' weighting."
        )

    # Detect Lohmöller premature convergence constellations (A18-HCM-07)
    premature_warnings: List[str] = []
    if cfg.inner_weighting == "path":
        if hoc_type in ("RR", "FR"):
            premature_warnings.append(
                "Lohmöller caution: Mode A for LOCs and HOC with LOC -> HOC relationships and path weighting "
                "can exhibit premature convergence depending on initial starting values. Factor weighting is recommended."
            )
        elif hoc_type in ("RF", "FF"):
            premature_warnings.append(
                "Lohmöller caution: Mode A for LOCs and Mode B for HOC with HOC -> LOC relationships and path weighting "
                "can exhibit premature convergence. Factor weighting is recommended (Hair et al. 2018)."
            )

    if approach == "two_stage":
        return run_disjoint_two_stage_hcm(
            df=df,
            spec_dict=spec_dict,
            hoc_id=hoc_id,
            loc_ids=loc_ids,
            hoc_type=hoc_type,
            settings=cfg,
        )

    if approach == "total_effects":
        # Becker et al. (2012) total effects collect-type structure (A18-HCM-10)
        tot_spec = build_collect_type_total_effects_spec(spec_dict, hoc_id, loc_ids)
        rep_spec, warnings = build_repeated_indicators_spec(
            spec_dict=tot_spec,
            hoc_id=hoc_id,
            loc_ids=loc_ids,
            hoc_type=hoc_type,
        )
        res_tot = run_pipeline(df, rep_spec, cfg)

        # Primary total effects table for HOC
        effects = res_tot.get("structural", {}).get("effects", [])
        hoc_total_effects = [e for e in effects if e.get("to") == hoc_id]

        # Collinearity VIF of LOCs
        scores = res_tot.get("construct_scores", {})
        X_locs = np.column_stack([np.asarray(scores.get(loc, np.zeros(len(df))), dtype=float) for loc in loc_ids])
        loc_vifs = calculate_vif(X_locs) if len(loc_ids) > 1 else [1.0]

        return {
            "hoc_id": hoc_id,
            "loc_ids": loc_ids,
            "hoc_type": hoc_type,
            "approach": "total_effects",
            "warnings": warnings + premature_warnings,
            "hoc_total_effects": hoc_total_effects,
            "loc_vifs": {loc: round(float(v), 4) for loc, v in zip(loc_ids, loc_vifs)},
            "results": res_tot,
        }

    # Standard Repeated Indicators approach
    rep_spec, warnings = build_repeated_indicators_spec(
        spec_dict=spec_dict,
        hoc_id=hoc_id,
        loc_ids=loc_ids,
        hoc_type=hoc_type,
    )

    res_rep = run_pipeline(df, rep_spec, cfg)

    # Extract HOC-LOC loadings / weights
    scores = res_rep.get("construct_scores", {})
    y_hoc = np.asarray(scores.get(hoc_id, np.zeros(len(df))), dtype=float)
    hoc_loc_loadings: Dict[str, float] = {}
    X_loc_matrix = []

    for loc in loc_ids:
        y_loc = np.asarray(scores.get(loc, np.zeros(len(df))), dtype=float)
        X_loc_matrix.append(y_loc)
        corr_hl = float(np.corrcoef(y_hoc, y_loc)[0, 1]) if (np.std(y_hoc) > 1e-12 and np.std(y_loc) > 1e-12) else 1.0
        hoc_loc_loadings[loc] = round(corr_hl, 4)

    X_loc_arr = np.column_stack(X_loc_matrix) if X_loc_matrix else np.zeros((len(df), 1))
    loc_corrs = np.corrcoef(X_loc_arr, rowvar=False) if len(loc_ids) > 1 else np.array([[1.0]])

    # A18-HCM-15: Manual HOC reliability and validity
    manual_metrics = compute_manual_hoc_reliability(hoc_loc_loadings, loc_corrs)

    # Reflective-reflective suitability check: LOC correlation > 0.5 (A18-HCM-17)
    loc_corr_high = bool(loc_corrs[0, 1] > 0.5) if len(loc_ids) >= 2 else True

    hoc_assessment: Dict[str, Any] = {
        "hoc_type": hoc_type,
        "approach": "repeated_indicators",
        "hoc_loc_loadings": hoc_loc_loadings,
        "manual_ave": manual_metrics["ave"],
        "manual_composite_reliability": manual_metrics["composite_reliability"],
        "manual_cronbachs_alpha": manual_metrics["cronbachs_alpha"],
        "loc_correlation_supports_reflective": loc_corr_high,
    }

    meas = res_rep.get("measurement", {})
    hoc_assessment["outer_weights"] = meas.get("outer_weights", {}).get(hoc_id, {})
    hoc_assessment["outer_loadings"] = meas.get("outer_loadings", {}).get(hoc_id, {})

    if hoc_type in ("RF", "FF"):
        loc_vifs = calculate_vif(X_loc_arr) if len(loc_ids) > 1 else [1.0]
        hoc_assessment["loc_collinearity_vif"] = {loc: round(float(v), 4) for loc, v in zip(loc_ids, loc_vifs)}

    return {
        "hoc_id": hoc_id,
        "loc_ids": loc_ids,
        "hoc_type": hoc_type,
        "approach": "repeated_indicators",
        "warnings": warnings + premature_warnings,
        "hoc_assessment": hoc_assessment,
        "results": res_rep,
    }
