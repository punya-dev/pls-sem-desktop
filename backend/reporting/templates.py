"""
Summary Templates Module (Section 26: REP-02).
Builds textbook summary tables matching Hair et al. (2017) reporting standards:
1. Reflective measurement model summary
2. Formative measurement model summary
3. Discriminant validity assessment (Fornell-Larcker & HTMT)
4. Structural model assessment (VIF, Paths, R^2, f^2, Q^2)
5. Model fit summary
6. Advanced analysis templates (Mediation, Moderation, IPMA, PLSpredict)
"""

from typing import List, Dict, Any, Optional
import numpy as np


def _fmt(val: Any, decimals: int = 3) -> str:
    if val is None or (isinstance(val, float) and (np.isnan(val) or np.isinf(val))):
        return "-"
    if isinstance(val, (float, np.floating)):
        return f"{val:.{decimals}f}"
    return str(val)


def build_reflective_summary(results: Dict[str, Any], decimals: int = 3) -> Dict[str, Any]:
    meas = results.get("measurement", {})
    rel = results.get("reliability_and_validity", {})
    loadings = meas.get("outer_loadings", {})
    alphas = rel.get("cronbachs_alpha", {})
    rho_as = rel.get("rho_a", {})
    crs = rel.get("composite_reliability", {})
    aves = rel.get("ave", {})

    rows = []
    for cid, inds in loadings.items():
        alpha_val = alphas.get(cid)
        rho_a_val = rho_as.get(cid)
        cr_val = crs.get(cid)
        ave_val = aves.get(cid)

        # Skip formative or empty blocks
        if cr_val is None and ave_val is None:
            continue

        for i, (iid, lam) in enumerate(inds.items()):
            lam_sq = lam ** 2 if lam is not None else None
            # Reliability & AVE displayed on first row of construct
            a_str = _fmt(alpha_val, decimals) if i == 0 else ""
            rho_str = _fmt(rho_a_val, decimals) if i == 0 else ""
            cr_str = _fmt(cr_val, decimals) if i == 0 else ""
            ave_str = _fmt(ave_val, decimals) if i == 0 else ""

            # Validity verdict: loading >= 0.708 (indicator reliability >= 0.50)
            status = "Retain" if (lam is not None and lam >= 0.708) else ("Evaluate" if (lam is not None and lam >= 0.40) else "Remove")

            rows.append([
                cid if i == 0 else "",
                iid,
                _fmt(lam, decimals),
                _fmt(lam_sq, decimals),
                a_str,
                rho_str,
                cr_str,
                ave_str,
                status,
            ])

    return {
        "title": "Reflective Measurement Model Evaluation Summary",
        "columns": [
            "Construct",
            "Indicator",
            "Outer Loading",
            "Indicator Reliability (λ²)",
            "Cronbach's α",
            "rho_A",
            "Composite Reliability (CR)",
            "AVE",
            "Verdict",
        ],
        "rows": rows,
        "footnotes": [
            "Loadings >= 0.708 indicate that the construct explains >= 50% of indicator variance (Hair et al., 2017).",
            "Composite reliability and Cronbach's alpha should be between 0.70 and 0.90.",
            "AVE values >= 0.50 indicate adequate convergent validity.",
        ],
    }


def build_formative_summary(results: Dict[str, Any], decimals: int = 3) -> Dict[str, Any]:
    meas = results.get("measurement", {})
    weights = meas.get("outer_weights", {})
    loadings = meas.get("outer_loadings", {})
    outer_vif = meas.get("outer_vif", {})
    sig = results.get("significance", {})
    params = sig.get("parameters", {})

    rows = []
    for cid, inds in weights.items():
        # Check if formative (has weights)
        vifs = outer_vif.get(cid, {})
        for iid, w in inds.items():
            lam = loadings.get(cid, {}).get(iid)
            vif_val = vifs.get(iid) if isinstance(vifs, dict) else None

            # Look up bootstrap stats for the weight
            w_key = f"weight:{cid}->{iid}"
            w_st = params.get(w_key, {})
            t_val = w_st.get("t_stat")
            p_val = w_st.get("p_value")
            ci = w_st.get("ci_percentile", [None, None])

            # Hair et al. retention rule:
            # Significant weight -> Retain
            # Insignificant weight but loading >= 0.50 -> Retain
            # Insignificant weight and loading < 0.50 but significant -> Retain with justification
            # Otherwise -> Consider removal
            decision = "Retain"
            if p_val is not None and p_val > 0.05:
                if lam is not None and lam >= 0.50:
                    decision = "Retain (Absolute importance)"
                else:
                    decision = "Evaluate removal"

            ci_str = f"[{_fmt(ci[0], decimals)}, {_fmt(ci[1], decimals)}]" if ci[0] is not None else "-"

            rows.append([
                cid,
                iid,
                _fmt(w, decimals),
                _fmt(lam, decimals),
                _fmt(vif_val, decimals),
                _fmt(t_val, decimals),
                _fmt(p_val, 4) if p_val is not None else "-",
                ci_str,
                decision,
            ])

    return {
        "title": "Formative Measurement Model Evaluation Summary",
        "columns": [
            "Construct",
            "Indicator",
            "Outer Weight",
            "Outer Loading",
            "Outer VIF",
            "t-value (Weight)",
            "p-value",
            "95% CI",
            "Retention Decision",
        ],
        "rows": rows,
        "footnotes": [
            "VIF values < 3.0 indicate absence of critical collinearity (Hair et al., 2017).",
            "Indicators with non-significant weights but loadings >= 0.50 are retained based on absolute contribution.",
        ],
    }


def build_discriminant_validity_summary(results: Dict[str, Any], decimals: int = 3) -> Dict[str, Any]:
    rel = results.get("reliability_and_validity", {})
    htmt = rel.get("htmt", {})
    fl = rel.get("fornell_larcker", {})
    constructs = sorted(list(htmt.keys()))

    rows = []
    for i, c1 in enumerate(constructs):
        for j, c2 in enumerate(constructs):
            if i >= j:
                continue
            htmt_val = htmt.get(c1, {}).get(c2)
            corr_val = fl.get(c1, {}).get(c2)

            htmt_ok = (htmt_val < 0.90) if (htmt_val is not None and not np.isnan(htmt_val)) else True
            fl_diag1 = fl.get(c1, {}).get(c1)
            fl_diag2 = fl.get(c2, {}).get(c2)
            fl_ok = True
            if corr_val is not None and fl_diag1 is not None and fl_diag2 is not None:
                fl_ok = (corr_val < fl_diag1) and (corr_val < fl_diag2)

            rows.append([
                f"{c1} - {c2}",
                _fmt(htmt_val, decimals),
                "Supported (< 0.90)" if htmt_ok else "Discriminant Issue (>= 0.90)",
                _fmt(corr_val, decimals),
                _fmt(fl_diag1, decimals),
                _fmt(fl_diag2, decimals),
                "Supported" if fl_ok else "Fails FL",
            ])

    return {
        "title": "Discriminant Validity Summary (HTMT and Fornell-Larcker)",
        "columns": [
            "Construct Pair",
            "HTMT Ratio",
            "HTMT Assessment",
            "Construct Correlation",
            "sqrt(AVE) Construct 1",
            "sqrt(AVE) Construct 2",
            "Fornell-Larcker Assessment",
        ],
        "rows": rows,
        "footnotes": [
            "HTMT values < 0.90 (or < 0.85 for conceptually distinct constructs) indicate established discriminant validity (Henseler et al., 2015).",
            "Under Fornell-Larcker, the square root of AVE must exceed any bivariate correlation with other constructs.",
        ],
    }


def build_structural_summary(results: Dict[str, Any], decimals: int = 3) -> Dict[str, Any]:
    struct = results.get("structural", {})
    paths = struct.get("path_coefficients", {})
    r2_map = struct.get("r_squared", {})
    r2_adj_map = struct.get("r_squared_adj", {})
    f2_map = struct.get("f_squared", {})
    inner_vif = struct.get("inner_vif", {})
    sig = results.get("significance", {})
    params = sig.get("parameters", {})

    rows = []
    for src, targets in paths.items():
        for tgt, beta in targets.items():
            f2_val = f2_map.get(src, {}).get(tgt)
            vif_val = inner_vif.get(tgt, {}).get(src)
            r2_val = r2_map.get(tgt)
            r2_adj = r2_adj_map.get(tgt)

            p_key = f"path:{src}->{tgt}"
            st = params.get(p_key, {})
            t_val = st.get("t_stat")
            p_val = st.get("p_value")
            ci = st.get("ci_percentile", [None, None])
            ci_str = f"[{_fmt(ci[0], decimals)}, {_fmt(ci[1], decimals)}]" if ci[0] is not None else "-"

            # f2 classification
            f2_desc = "-"
            if f2_val is not None:
                if f2_val >= 0.35:
                    f2_desc = "Large (>= 0.35)"
                elif f2_val >= 0.15:
                    f2_desc = "Medium (>= 0.15)"
                elif f2_val >= 0.02:
                    f2_desc = "Small (>= 0.02)"
                else:
                    f2_desc = "None (< 0.02)"

            rows.append([
                src,
                tgt,
                _fmt(beta, decimals),
                _fmt(t_val, decimals),
                _fmt(p_val, 4) if p_val is not None else "-",
                ci_str,
                _fmt(vif_val, decimals),
                _fmt(f2_val, decimals) + f" ({f2_desc})",
                _fmt(r2_val, decimals),
                _fmt(r2_adj, decimals),
            ])

    return {
        "title": "Structural Model Evaluation Summary",
        "columns": [
            "Predictor",
            "Target",
            "Path Coef (β)",
            "t-value",
            "p-value",
            "95% CI",
            "Inner VIF",
            "f² Effect Size",
            "Target R²",
            "Target Adjusted R²",
        ],
        "rows": rows,
        "footnotes": [
            "Inner VIF < 3.0 indicates absence of multicollinearity (Hair et al., 2017).",
            "Effect sizes f²: 0.02 = small, 0.15 = medium, 0.35 = large (Cohen, 1988).",
        ],
    }


def build_fit_summary(results: Dict[str, Any], decimals: int = 3) -> Dict[str, Any]:
    fit = results.get("fit", {})
    if not fit or "saturated_model" not in fit:
        return {"title": "Model Fit Summary", "columns": ["Metric", "Value"], "rows": [["Status", "Not evaluated"]]}

    sat = fit.get("saturated_model", {})
    est = fit.get("estimated_model", {})
    rms_theta = fit.get("rms_theta")
    gof = fit.get("gof", {})

    rows = [
        ["SRMR (Saturated Model)", _fmt(sat.get("srmr"), decimals), "< 0.08", "Acceptable" if sat.get("srmr_ok") else "Fails cutoff"],
        ["SRMR (Estimated Model)", _fmt(est.get("srmr"), decimals), "< 0.08", "Acceptable" if est.get("srmr_ok") else "Fails cutoff"],
        ["d_ULS (Saturated)", _fmt(sat.get("d_uls"), decimals), "N/A", "-"],
        ["d_G (Saturated)", _fmt(sat.get("d_g"), decimals), "N/A", "-"],
        ["d_ULS (Estimated)", _fmt(est.get("d_uls"), decimals), "N/A", "-"],
        ["d_G (Estimated)", _fmt(est.get("d_g"), decimals), "N/A", "-"],
        ["RMS_theta", _fmt(rms_theta, decimals), "< 0.12", "Acceptable" if fit.get("rms_theta_ok") else "Fails cutoff"],
        ["Tenenhaus GoF (Cautionary)", _fmt(gof.get("gof"), decimals), "Descriptive", "Not recommended as model fit criterion"],
    ]

    return {
        "title": "Model Fit Criteria Summary",
        "columns": ["Criterion", "Value", "Threshold", "Assessment"],
        "rows": rows,
        "footnotes": [
            "SRMR < 0.08 indicates good fit (Hu & Bentler, 1999).",
            "RMS_theta < 0.12 is applicable to reflective measurement models (Lohmöller, 1989).",
            "GoF is provided for historical comparison only (Henseler & Sarstedt, 2013).",
        ],
    }
