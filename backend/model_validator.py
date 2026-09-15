from typing import List, Optional, Dict, Set, Any
from pydantic import BaseModel, Field
from model_spec import ModelSpec


class ValidationResult(BaseModel):
    is_valid: bool
    errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    exogenous_constructs: List[str] = Field(default_factory=list)
    endogenous_constructs: List[str] = Field(default_factory=list)
    isolated_constructs: List[str] = Field(default_factory=list)


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


def validate_model_spec(spec: ModelSpec, dataset_columns: Optional[List[str]] = None) -> ValidationResult:
    errors: List[str] = []
    warnings: List[str] = []

    # 1. Constructs checks
    if not spec.constructs:
        errors.append("Model must define at least one construct.")

    construct_ids: Set[str] = set()
    construct_names: Set[str] = set()
    construct_id_to_name: Dict[str, str] = {}

    for c in spec.constructs:
        cid = str(c.id).strip()
        cname = str(c.name).strip()

        if not cid:
            errors.append("Construct ID cannot be empty.")
            continue

        if cid in construct_ids:
            errors.append(f"Duplicate construct ID '{cid}'.")
        else:
            construct_ids.add(cid)
            construct_id_to_name[cid] = cname

        if not cname:
            errors.append(f"Construct '{cid}' has an empty name.")
        elif cname in construct_names:
            warnings.append(f"Multiple constructs share the name '{cname}'.")
        else:
            construct_names.add(cname)

        if not c.indicators or len(c.indicators) == 0:
            errors.append(f"Construct '{cname or cid}' must have at least 1 indicator.")

    # 2. Indicators checks
    indicator_ids: Set[str] = set()
    indicator_id_to_col: Dict[str, str] = {}

    for ind in spec.indicators:
        iid = str(ind.id).strip()
        col = str(ind.column).strip()

        if not iid:
            errors.append("Indicator ID cannot be empty.")
            continue

        if iid in indicator_ids:
            errors.append(f"Duplicate indicator ID '{iid}'.")
        else:
            indicator_ids.add(iid)
            indicator_id_to_col[iid] = col

        if not col:
            errors.append(f"Indicator '{iid}' has an empty column mapping.")
        elif dataset_columns is not None and col not in dataset_columns:
            errors.append(f"Indicator '{iid}' mapped to column '{col}' which does not exist in the dataset.")

    # 3. Construct-indicator linkage & orphan indicator checks
    assigned_indicators: Dict[str, List[str]] = {}  # indicator_id -> list of construct_ids
    for c in spec.constructs:
        cid = str(c.id).strip()
        for iid in c.indicators:
            iid_str = str(iid).strip()
            if iid_str not in indicator_ids:
                errors.append(f"Construct '{c.name or cid}' references unknown indicator '{iid_str}'.")
            else:
                assigned_indicators.setdefault(iid_str, []).append(cid)

    for iid in indicator_ids:
        assigned = assigned_indicators.get(iid, [])
        if len(assigned) == 0:
            errors.append(f"Orphan indicator '{iid}' (column '{indicator_id_to_col.get(iid, '')}') is not assigned to any construct.")
        elif len(assigned) > 1:
            construct_labels = [construct_id_to_name.get(cid, cid) for cid in assigned]
            errors.append(f"Indicator '{iid}' is assigned to multiple constructs: {', '.join(construct_labels)}. Shared indicators are not supported.")

    # 4. Paths checks
    path_pairs: Set[tuple] = set()
    in_degrees: Dict[str, int] = {cid: 0 for cid in construct_ids}
    out_degrees: Dict[str, int] = {cid: 0 for cid in construct_ids}

    for p in spec.paths:
        from_node = str(p.from_node).strip()
        to_node = str(p.to_node).strip()

        if from_node not in construct_ids:
            errors.append(f"Path references unknown source construct '{from_node}'.")
        if to_node not in construct_ids:
            errors.append(f"Path references unknown target construct '{to_node}'.")

        if from_node in construct_ids and to_node in construct_ids:
            if from_node == to_node:
                errors.append(f"Self-loop path detected on construct '{construct_id_to_name.get(from_node, from_node)}' ({from_node} -> {to_node}).")
            
            pair = (from_node, to_node)
            if pair in path_pairs:
                warnings.append(f"Duplicate path from '{construct_id_to_name.get(from_node, from_node)}' to '{construct_id_to_name.get(to_node, to_node)}'.")
            else:
                path_pairs.add(pair)
                out_degrees[from_node] += 1
                in_degrees[to_node] += 1

    # 5. Cycle check (DAG validation)
    cycle = detect_cycles(construct_ids, spec.paths)
    if cycle:
        cycle_chain = " -> ".join([construct_id_to_name.get(cid, cid) for cid in cycle])
        errors.append(f"Cycle detected in structural model: {cycle_chain}. Recursive models are not supported in v1.")

    # 6. Exogenous / Endogenous classification
    exogenous = [cid for cid in construct_ids if in_degrees.get(cid, 0) == 0 and out_degrees.get(cid, 0) > 0]
    endogenous = [cid for cid in construct_ids if in_degrees.get(cid, 0) > 0]
    isolated = [cid for cid in construct_ids if in_degrees.get(cid, 0) == 0 and out_degrees.get(cid, 0) == 0]

    if isolated and len(construct_ids) > 1:
        isolated_names = [construct_id_to_name.get(cid, cid) for cid in isolated]
        warnings.append(f"Isolated construct(s) without any structural paths: {', '.join(isolated_names)}.")

    return ValidationResult(
        is_valid=(len(errors) == 0),
        errors=errors,
        warnings=warnings,
        exogenous_constructs=exogenous,
        endogenous_constructs=endogenous,
        isolated_constructs=isolated,
    )
