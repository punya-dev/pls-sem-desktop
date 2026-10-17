"""
Hierarchical Component Models (HCM / Higher-Order Constructs) (Section 18: HCM-01 to HCM-08).
Source of truth: Hair et al. (2017) Ch. 8 & Becker et al. (2012).
Supports Repeated-Indicators and Disjoint Two-Stage approaches across
RR (reflective-reflective), RF (reflective-formative), FR (formative-reflective), and FF (formative-formative).
"""

from typing import List, Dict, Any, Optional, Tuple, Union
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
    Constructs a repeated-indicators model specification (HCM-02).
    The HOC receives all indicators of its lower-order components (LOCs).
    """
    warnings: List[str] = []
    # Identify LOC indicators
    loc_inds_map: Dict[str, List[str]] = {}
    for c in spec_dict.get("constructs", []):
        cid = c["id"]
        if cid in loc_ids:
            if "indicators" in c and c["indicators"]:
                loc_inds_map[cid] = list(c["indicators"])
            else:
                loc_inds_map[cid] = [
                    (ind.get("name") or ind.get("column") or ind.get("id"))
                    for ind in spec_dict.get("indicators", [])
                    if (ind.get("construct_id") or ind.get("construct")) == cid
                ]

    # Balance check: do LOCs have equal indicator counts? (VAL-08)
    counts = [len(inds) for inds in loc_inds_map.values()]
    if len(set(counts)) > 1:
        warnings.append(
            f"LOC indicator counts are unequal ({dict(zip(loc_inds_map.keys(), counts))}). "
            f"In the repeated-indicators approach, the HOC will be biased toward the larger LOC. "
            f"Consider using the disjoint two-stage approach (Hair et al. 2017)."
        )

    all_hoc_inds = []
    for inds in loc_inds_map.values():
        all_hoc_inds.extend(inds)

    hoc_mode = "formative" if hoc_type in ("RF", "FF") else "reflective"

    if hoc_type in ("RF", "FF"):
        warnings.append(
            "Formative HOC with repeated indicators suffers from artificial R^2=1 when antecedent constructs exist. "
            "The disjoint two-stage approach is strongly recommended for RF and FF models (Becker et al. 2012)."
        )

    # Clone spec and update/add HOC
    new_constructs = []
    hoc_found = False
    for c in spec_dict.get("constructs", []):
        if c["id"] == hoc_id:
            c_copy = dict(c)
            c_copy["indicators"] = all_hoc_inds
            c_copy["type"] = hoc_mode
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
            "order": "higher",
            "components": loc_ids,
            "hoc_type": hoc_type,
            "indicators": all_hoc_inds,
        })

    # Add paths between HOC and LOCs:
    # Reflective HOC (RR, FR): HOC -> LOC
    # Formative HOC (RF, FF): LOC -> HOC
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


def run_disjoint_two_stage_hcm(
    df: pd.DataFrame,
    spec_dict: Dict[str, Any],
    hoc_id: str,
    loc_ids: List[str],
    hoc_type: str = "RF",
    settings: Optional[PipelineSettings] = None,
) -> Dict[str, Any]:
    """
    Executes Disjoint Two-Stage HCM estimation (HCM-03).
    Stage 1: LOCs connected directly to other constructs.
    Stage 2: LOC scores become single indicators of the HOC.
    """
    cfg = settings or PipelineSettings()
    # Step 1: Stage 1 Model
    # Remove HOC from spec, ensure LOCs connect to whatever HOC was connected to
    stage1_paths = []
    for p in spec_dict.get("paths", []):
        fc = p.get("from") or p.get("from_node")
        tc = p.get("to") or p.get("to_node")
        if fc == hoc_id:
            # Route from all LOCs to tc
            for loc in loc_ids:
                stage1_paths.append({"from": loc, "to": tc})
        elif tc == hoc_id:
            # Route from fc to all LOCs
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

    # Step 2: Build Stage 2 Data & Spec
    df_stage2 = df.copy()
    stage2_hoc_inds = []
    for loc_id in loc_ids:
        col_name = f"score_{loc_id}"
        loc_score = np.asarray(scores_stage1.get(loc_id, np.zeros(len(df))), dtype=float)
        # Standardize LOC score for Stage 2
        loc_score_std = (loc_score - np.mean(loc_score)) / (np.std(loc_score, ddof=0) or 1.0)
        df_stage2[col_name] = loc_score_std
        stage2_hoc_inds.append(col_name)

    hoc_mode = "formative" if hoc_type in ("RF", "FF") else "reflective"

    # In Stage 2, LOCs are removed from the model and replaced by the HOC measured by LOC scores
    stage2_constructs = [c for c in stage1_constructs if c["id"] not in loc_ids] + [{
        "id": hoc_id,
        "name": hoc_id,
        "type": hoc_mode,
        "order": "higher",
        "components": loc_ids,
        "hoc_type": hoc_type,
        "indicators": stage2_hoc_inds,
    }]

    # In Stage 2 paths: restore paths involving HOC, remove paths involving LOCs
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

    # Assess HOC measurement model (HCM-04)
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
        # Formative HOC: Check collinearity among LOC scores
        X_locs = np.column_stack([df_stage2[col].values for col in stage2_hoc_inds])
        if len(stage2_hoc_inds) > 1:
            vifs = calculate_vif(X_locs)
            hoc_assessment["collinearity_vif"] = {
                loc: round(float(v), 4) for loc, v in zip(loc_ids, vifs)
            }
    else:
        # Reflective HOC: Internal consistency
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
    }


def analyze_hcm(
    df: pd.DataFrame,
    spec: Union[Dict[str, Any], Any],
    hoc_id: str,
    loc_ids: List[str],
    hoc_type: str = "RR",  # "RR", "RF", "FR", "FF"
    approach: str = "repeated_indicators",  # "repeated_indicators" or "two_stage"
    settings: Optional[PipelineSettings] = None,
) -> Dict[str, Any]:
    """
    Main entry point for Hierarchical Component Model analysis (HCM-01 to HCM-08).
    """
    spec_dict = spec.model_dump(by_alias=True) if hasattr(spec, "model_dump") else (spec if isinstance(spec, dict) else {})
    cfg = settings or PipelineSettings()

    # Blocking centroid weighting with HCM (HCM-06)
    if cfg.inner_weighting == "centroid":
        raise ValueError(
            "Centroid weighting is not supported for Hierarchical Component Models (HCM-06). "
            "Please select 'path' (recommended) or 'factor' weighting (Hair et al. 2017)."
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

    # Repeated indicators approach
    rep_spec, warnings = build_repeated_indicators_spec(
        spec_dict=spec_dict,
        hoc_id=hoc_id,
        loc_ids=loc_ids,
        hoc_type=hoc_type,
    )

    res_rep = run_pipeline(df, rep_spec, cfg)

    # Extract HOC evaluation
    meas = res_rep.get("measurement", {})
    weights = meas.get("outer_weights", {}).get(hoc_id, {})
    loadings = meas.get("outer_loadings", {}).get(hoc_id, {})

    hoc_assessment: Dict[str, Any] = {
        "hoc_type": hoc_type,
        "approach": "repeated_indicators",
        "outer_weights": weights,
        "outer_loadings": loadings,
    }

    if hoc_type in ("RR", "FR"):
        rel = res_rep.get("reliability_and_validity", {})
        hoc_assessment["cronbachs_alpha"] = rel.get("cronbachs_alpha", {}).get(hoc_id)
        hoc_assessment["composite_reliability"] = rel.get("composite_reliability", {}).get(hoc_id)
        hoc_assessment["ave"] = rel.get("ave", {}).get(hoc_id)

    return {
        "hoc_id": hoc_id,
        "loc_ids": loc_ids,
        "hoc_type": hoc_type,
        "approach": "repeated_indicators",
        "warnings": warnings,
        "hoc_assessment": hoc_assessment,
        "results": res_rep,
    }
