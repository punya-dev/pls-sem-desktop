from typing import List, Optional, Dict, Set, Any
from pydantic import BaseModel, Field
import numpy as np

from model_spec import ModelSpec
from core.issues import Issue, IssueTarget
from core.thresholds import THRESHOLDS


class ValidationResult(BaseModel):
    is_valid: bool
    errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    exogenous_constructs: List[str] = Field(default_factory=list)
    endogenous_constructs: List[str] = Field(default_factory=list)
    isolated_constructs: List[str] = Field(default_factory=list)
    issues: List[Issue] = Field(default_factory=list)


def detect_cycles(construct_ids: Set[str], paths: List[Any]) -> Optional[List[str]]:
    """
    Finds a directed cycle if present using DFS.
    Returns the cycle as a list of construct IDs (e.g. ['C1', 'C2', 'C1']), or None if acyclic.
    """
    adjacency: Dict[str, List[str]] = {cid: [] for cid in construct_ids}
    for p in paths:
        from_id = p.from_node if hasattr(p, "from_node") else p.get("from") or p.get("from_node")
        to_id = p.to_node if hasattr(p, "to_node") else p.get("to") or p.get("to_node")
        if from_id in adjacency:
            adjacency[from_id].append(to_id)

    # 0 = unvisited, 1 = visiting, 2 = visited
    state: Dict[str, int] = {cid: 0 for cid in construct_ids}
    parent: Dict[str, Optional[str]] = {cid: None for cid in construct_ids}
    cycle_nodes: Optional[List[str]] = None

    def dfs(u: str) -> bool:
        nonlocal cycle_nodes
        state[u] = 1
        for v in adjacency.get(u, []):
            if v not in state:
                continue
            if state[v] == 1:
                # Cycle found! Trace back from u to v
                cycle = [v]
                curr = u
                while curr is not None and curr != v:
                    cycle.append(curr)
                    curr = parent.get(curr)
                cycle.append(v)
                cycle.reverse()
                cycle_nodes = cycle
                return True
            elif state[v] == 0:
                parent[v] = u
                if dfs(v):
                    return True
        state[u] = 2
        return False

    for node in construct_ids:
        if state[node] == 0:
            if dfs(node):
                return cycle_nodes

    return None


def validate_model_spec(
    spec: ModelSpec,
    dataset_columns: Optional[List[str]] = None,
    n_samples: Optional[int] = None,
    data_df: Optional[Any] = None,
) -> ValidationResult:
    errors: List[str] = []
    warnings: List[str] = []
    issues: List[Issue] = []

    def add_issue(code: str, severity: str, target_type: str, target_id: str, message: str, advice: Optional[str] = None):
        iss = Issue(
            code=code,
            severity=severity,
            target=IssueTarget(type=target_type, id=target_id),
            message=message,
            advice=advice,
        )
        issues.append(iss)
        if severity == "error":
            errors.append(message)
        elif severity == "warning":
            warnings.append(message)

    # 1. Constructs checks
    if not spec.constructs:
        add_issue("NO_CONSTRUCTS", "error", "model", "model", "Model must define at least one construct.")

    construct_ids: Set[str] = set()
    construct_names: Set[str] = set()
    construct_id_to_name: Dict[str, str] = {}
    hoc_construct_ids: Set[str] = set()
    loc_components_map: Dict[str, List[str]] = {}

    for c in spec.constructs:
        cid = str(c.id).strip()
        cname = str(c.name).strip()

        if not cid:
            add_issue("EMPTY_CONSTRUCT_ID", "error", "construct", cid, "Construct ID cannot be empty.")
            continue

        if cid in construct_ids:
            add_issue("DUPLICATE_CONSTRUCT_ID", "error", "construct", cid, f"Duplicate construct ID '{cid}'.")
        else:
            construct_ids.add(cid)
            construct_id_to_name[cid] = cname

        if not cname:
            add_issue("EMPTY_CONSTRUCT_NAME", "error", "construct", cid, f"Construct '{cid}' has an empty name.")
        elif cname in construct_names:
            add_issue("DUPLICATE_CONSTRUCT_NAME", "warning", "construct", cid, f"Multiple constructs share the name '{cname}'.")
        else:
            construct_names.add(cname)

        if c.order == "higher":
            hoc_construct_ids.add(cid)
            loc_components_map[cid] = list(c.components or [])

        # Construct indicator count
        n_ind = len(c.indicators) if c.indicators else 0
        if n_ind == 0:
            add_issue("NO_INDICATORS", "error", "construct", cid, f"Construct '{cname or cid}' must have at least 1 indicator.")
        elif n_ind == 1:
            # VAL-03 [P1] Single-item advisor
            add_issue(
                "SINGLE_ITEM_CONSTRUCT",
                "info",
                "construct",
                cid,
                f"Construct '{cname or cid}' is single-item. Internal consistency (alpha, CR, AVE) is not interpretable.",
                "Single-item measures are only acceptable for concrete, singular attributes (e.g. sales, price, or global ratings). Multi-item scales are strongly recommended for abstract attitudes/traits.",
            )

        # VAL-05 [P1] Sum scores warning
        if c.weighting == "sum_scores":
            add_issue(
                "SUM_SCORES_USED",
                "warning",
                "construct",
                cid,
                f"Construct '{cname or cid}' uses sum scores (equal weights).",
                "Sum scores assume all indicators are equally important and bias structural path estimates. The PLS path weighting scheme is recommended.",
            )

        # VAL-07 [P1] Formative max weight reference (1 / sqrt(n))
        if c.type == "formative" and n_ind > 0:
            max_w = 1.0 / np.sqrt(n_ind)
            add_issue(
                "FORMATIVE_MAX_WEIGHT",
                "info",
                "construct",
                cid,
                f"Formative construct '{cname or cid}' has {n_ind} indicators. Maximum possible weight with uncorrelated items is {max_w:.3f}.",
                "With many formative indicators, statistical power decreases and weights become smaller. Consider grouping indicators into lower-order components if nonsignificant weights occur.",
            )

    # 2. Indicators checks
    indicator_ids: Set[str] = set()
    indicator_id_to_col: Dict[str, str] = {}

    for ind in spec.indicators:
        iid = str(ind.id).strip()
        col = str(ind.column).strip()

        if not iid:
            add_issue("EMPTY_INDICATOR_ID", "error", "indicator", iid, "Indicator ID cannot be empty.")
            continue

        if iid in indicator_ids:
            add_issue("DUPLICATE_INDICATOR_ID", "error", "indicator", iid, f"Duplicate indicator ID '{iid}'.")
        else:
            indicator_ids.add(iid)
            indicator_id_to_col[iid] = col

        if not col:
            add_issue("EMPTY_COLUMN_MAPPING", "error", "indicator", iid, f"Indicator '{iid}' has an empty column mapping.")
        elif dataset_columns is not None and col not in dataset_columns:
            add_issue("COLUMN_NOT_IN_DATASET", "error", "indicator", iid, f"Indicator '{iid}' mapped to column '{col}' which does not exist in the dataset.")

    # 3. Construct-indicator linkage & orphan indicator checks
    assigned_indicators: Dict[str, List[str]] = {}
    for c in spec.constructs:
        cid = str(c.id).strip()
        for iid in c.indicators:
            iid_str = str(iid).strip()
            if iid_str not in indicator_ids:
                add_issue("UNKNOWN_INDICATOR_REF", "error", "construct", cid, f"Construct '{c.name or cid}' references unknown indicator '{iid_str}'.")
            else:
                assigned_indicators.setdefault(iid_str, []).append(cid)

    for iid in indicator_ids:
        assigned = assigned_indicators.get(iid, [])
        if len(assigned) == 0:
            add_issue("ORPHAN_INDICATOR", "error", "indicator", iid, f"Orphan indicator '{iid}' (column '{indicator_id_to_col.get(iid, '')}') is not assigned to any construct.")
        elif len(assigned) > 1:
            # Check if this shared indicator is permitted due to HOC repeated indicators (Task S4-3 / Section 18)
            is_valid_hoc_sharing = False
            for hoc_id in hoc_construct_ids:
                loc_list = loc_components_map.get(hoc_id, [])
                if hoc_id in assigned and any(loc_id in assigned for loc_id in loc_list):
                    is_valid_hoc_sharing = True
                    break

            if not is_valid_hoc_sharing:
                construct_labels = [construct_id_to_name.get(cid, cid) for cid in assigned]
                add_issue(
                    "SHARED_INDICATOR",
                    "error",
                    "indicator",
                    iid,
                    f"Indicator '{iid}' is assigned to multiple constructs: {', '.join(construct_labels)}. Shared indicators are only supported in Hierarchical Component Models (HCM).",
                )

    # VAL-08 [P1] Repeated-indicator balance check for HOCs
    for hoc_id in hoc_construct_ids:
        locs = loc_components_map.get(hoc_id, [])
        loc_counts = []
        for loc_id in locs:
            for c in spec.constructs:
                if str(c.id) == loc_id:
                    loc_counts.append(len(c.indicators))
        if loc_counts and (max(loc_counts) - min(loc_counts) > 3):
            add_issue(
                "UNBALANCED_HOC_LOCS",
                "warning",
                "construct",
                hoc_id,
                f"Higher-Order Construct '{construct_id_to_name.get(hoc_id, hoc_id)}' has lower-order components with unequal indicator counts ({min(loc_counts)} to {max(loc_counts)}).",
                "Unequal numbers of indicators across LOCs bias the HOC relationship toward the component with more indicators. Consider the two-stage HCM approach.",
            )

    # 4. Paths checks
    path_pairs: Set[tuple] = set()
    in_degrees: Dict[str, int] = {cid: 0 for cid in construct_ids}
    out_degrees: Dict[str, int] = {cid: 0 for cid in construct_ids}

    for p in spec.paths:
        from_node = str(p.from_node).strip()
        to_node = str(p.to_node).strip()

        if from_node not in construct_ids:
            add_issue("UNKNOWN_SOURCE_NODE", "error", "path", f"{from_node}->{to_node}", f"Path references unknown source construct '{from_node}'.")
        if to_node not in construct_ids:
            add_issue("UNKNOWN_TARGET_NODE", "error", "path", f"{from_node}->{to_node}", f"Path references unknown target construct '{to_node}'.")

        if from_node in construct_ids and to_node in construct_ids:
            if from_node == to_node:
                add_issue("SELF_LOOP_PATH", "error", "path", f"{from_node}->{to_node}", f"Self-loop path detected on construct '{construct_id_to_name.get(from_node, from_node)}' ({from_node} -> {to_node}).")

            pair = (from_node, to_node)
            if pair in path_pairs:
                add_issue("DUPLICATE_PATH", "warning", "path", f"{from_node}->{to_node}", f"Duplicate path from '{construct_id_to_name.get(from_node, from_node)}' to '{construct_id_to_name.get(to_node, to_node)}'.")
            else:
                path_pairs.add(pair)
                out_degrees[from_node] += 1
                in_degrees[to_node] += 1

    # 5. Cycle check (DAG validation - MOD-14)
    cycle = detect_cycles(construct_ids, spec.paths)
    if cycle:
        cycle_chain = " -> ".join([construct_id_to_name.get(cid, cid) for cid in cycle])
        add_issue("CYCLE_DETECTED", "error", "model", "model", f"Cycle detected in structural model: {cycle_chain}. Recursive models are not supported in standard PLS-SEM.")

    # 6. Exogenous / Endogenous classification (MOD-13)
    exogenous = [cid for cid in construct_ids if in_degrees.get(cid, 0) == 0 and out_degrees.get(cid, 0) > 0]
    endogenous = [cid for cid in construct_ids if in_degrees.get(cid, 0) > 0]
    isolated = [cid for cid in construct_ids if in_degrees.get(cid, 0) == 0 and out_degrees.get(cid, 0) == 0]

    if isolated and len(construct_ids) > 1:
        isolated_names = [construct_id_to_name.get(cid, cid) for cid in isolated]
        add_issue("ISOLATED_CONSTRUCT", "warning", "model", "model", f"Isolated construct(s) without any structural paths: {', '.join(isolated_names)}.")

    # 7. Moderating effects validation (MOD-M01..M03)
    for me in spec.moderating_effects:
        me_id = str(me.id)
        mod_c = str(me.moderator).strip()
        src_c = str(me.source).strip()
        tgt_c = str(me.target).strip()

        if mod_c not in construct_ids:
            add_issue("UNKNOWN_MODERATOR", "error", "moderator", me_id, f"Moderator '{mod_c}' not found in constructs.")
        if src_c not in construct_ids:
            add_issue("UNKNOWN_MOD_SOURCE", "error", "moderator", me_id, f"Independent construct '{src_c}' not found in constructs.")
        if tgt_c not in construct_ids:
            add_issue("UNKNOWN_MOD_TARGET", "error", "moderator", me_id, f"Target construct '{tgt_c}' not found in constructs.")

        if src_c in construct_ids and tgt_c in construct_ids:
            if (src_c, tgt_c) not in path_pairs:
                add_issue("MISSING_MAIN_PATH_FOR_MODERATION", "error", "moderator", me_id, f"Direct path from '{src_c}' to '{tgt_c}' must exist to test moderation.")

        if mod_c in construct_ids and tgt_c in construct_ids:
            if (mod_c, tgt_c) not in path_pairs:
                add_issue(
                    "MISSING_MODERATOR_DIRECT_PATH",
                    "warning",
                    "moderator",
                    me_id,
                    f"Direct path from moderator '{mod_c}' to target '{tgt_c}' is missing.",
                    "The direct effect of the moderator must be included in the model; omitting it inflates the interaction effect.",
                )

    # 8. Sample size / 10-times rule check (VAL-02 / SAM-01)
    max_formative = 0
    for c in spec.constructs:
        if c.type == "formative":
            max_formative = max(max_formative, len(c.indicators))
    max_arrows = max(in_degrees.values()) if in_degrees else 0
    min_n_10x = 10 * max(max_formative, max_arrows)

    if n_samples is not None and min_n_10x > 0:
        if n_samples < min_n_10x:
            add_issue(
                "SAMPLE_SIZE_BELOW_10X",
                "warning",
                "dataset",
                "sample_size",
                f"Sample size ({n_samples}) is below the 10-times rule recommendation ({min_n_10x}).",
                f"The 10-times rule requires 10 × max(formative indicators={max_formative}, structural predictors={max_arrows}) = {min_n_10x} observations.",
            )

    # 9. Matrix singularity check (VAL-01) if data_df is provided
    if data_df is not None:
        for c in spec.constructs:
            cid = str(c.id)
            cols = [indicator_id_to_col.get(iid) for iid in c.indicators if iid in indicator_id_to_col]
            valid_cols = [col for col in cols if col in data_df.columns]
            if len(valid_cols) > 0:
                sub = data_df[valid_cols].apply(pd.to_numeric, errors='coerce')
                # Check zero variance
                zero_var_cols = [col for col in valid_cols if sub[col].std() == 0 or np.isnan(sub[col].std())]
                if zero_var_cols:
                    add_issue(
                        "ZERO_VARIANCE_INDICATOR",
                        "error",
                        "indicator",
                        ", ".join(zero_var_cols),
                        f"Indicators {zero_var_cols} in construct '{c.name or cid}' have zero variance.",
                        "Standardization requires variance > 0. Remove constant indicators.",
                    )
                # Check collinear block
                if len(valid_cols) > 1 and not zero_var_cols:
                    corr = sub.corr().to_numpy()
                    if np.linalg.matrix_rank(corr) < len(valid_cols) or np.abs(np.linalg.det(corr)) < 1e-10:
                        add_issue(
                            "SINGULAR_INDICATOR_BLOCK",
                            "error",
                            "construct",
                            cid,
                            f"Indicator block for construct '{c.name or cid}' is singular or perfectly collinear.",
                            "Check for duplicate indicators or linear combinations of items.",
                        )

    return ValidationResult(
        is_valid=(len(errors) == 0),
        errors=errors,
        warnings=warnings,
        exogenous_constructs=exogenous,
        endogenous_constructs=endogenous,
        isolated_constructs=isolated,
        issues=issues,
    )
