"""
Structural Model Effects Computation (Direct, Specific Indirect, Total Indirect, Total Effects).
Decomposes specific indirect paths (e.g., X -> M1 -> Y, X -> M2 -> Y) and verifies
that the sum of specific indirect effects exactly matches the matrix formulation (I - B)^(-1) - I.
"""

from typing import List, Dict, Any, Tuple, Union
import numpy as np


def enumerate_directed_paths(
    adj_matrix: np.ndarray,
    construct_ids: List[str],
    max_length: int = 8,
    max_paths: int = 1000,
) -> List[List[int]]:
    """
    Finds all directed paths with length >= 2 (i.e. containing at least 1 mediator)
    between all pairs of constructs in the DAG using Depth-First Search.
    Returns list of paths where each path is a list of node indices: [source, ..., target].
    """
    n = len(construct_ids)
    all_paths: List[List[int]] = []

    def dfs(current: int, target: int, visited: List[int]):
        if len(all_paths) >= max_paths:
            return
        if len(visited) > max_length:
            return

        for nxt in range(n):
            if adj_matrix[current, nxt] != 0:
                if nxt == target:
                    if len(visited) >= 2:  # at least source -> mediator -> target
                        all_paths.append(visited + [target])
                elif nxt not in visited:
                    dfs(nxt, target, visited + [nxt])

    for i in range(n):
        for j in range(n):
            if i != j:
                dfs(i, j, [i])

    return all_paths


def calculate_effects(
    path_matrix: Union[np.ndarray, Dict[str, Dict[str, float]]],
    construct_ids: List[str],
) -> Dict[str, Any]:
    """
    Computes direct, specific indirect, total indirect, and total effects.
    path_matrix[i, j] is the direct path from construct i to construct j.
    """
    n = len(construct_ids)
    c_idx_map = {cid: idx for idx, cid in enumerate(construct_ids)}

    if isinstance(path_matrix, dict):
        mat = np.zeros((n, n), dtype=float)
        for to_c, from_map in path_matrix.items():
            if to_c in c_idx_map:
                for from_c, val in from_map.items():
                    if from_c in c_idx_map:
                        mat[c_idx_map[from_c], c_idx_map[to_c]] = float(val)
        path_matrix = mat

    # Total effects matrix: T = (I - B)^(-1) - I = B + B^2 + B^3 + ...
    ident = np.eye(n)
    try:
        total_effects_mat = np.linalg.inv(ident - path_matrix) - ident
    except np.linalg.LinAlgError:
        total_effects_mat = path_matrix.copy()

    indirect_effects_mat = total_effects_mat - path_matrix

    # Adjacency for path enumeration (where direct path != 0)
    adj = (np.abs(path_matrix) > 1e-12).astype(float)
    paths_indices = enumerate_directed_paths(adj, construct_ids)

    specific_indirect_list: List[Dict[str, Any]] = []
    for p_nodes in paths_indices:
        # Compute product of coefficients along this path
        coef = 1.0
        for step in range(len(p_nodes) - 1):
            u = p_nodes[step]
            v = p_nodes[step + 1]
            coef *= float(path_matrix[u, v])

        path_cids = [construct_ids[idx] for idx in p_nodes]
        path_str = " -> ".join(path_cids)

        specific_indirect_list.append({
            "source": construct_ids[p_nodes[0]],
            "target": construct_ids[p_nodes[-1]],
            "path": path_str,
            "path_nodes": path_cids,
            "effect": float(coef),
        })

    # Summary table of pairs with non-zero effects
    effects_summary = []
    for i in range(n):
        for j in range(n):
            from_id = construct_ids[i]
            to_id = construct_ids[j]
            direct = float(path_matrix[i, j])
            indirect = float(indirect_effects_mat[i, j])
            total = float(total_effects_mat[i, j])

            if abs(direct) > 1e-7 or abs(indirect) > 1e-7 or abs(total) > 1e-7:
                # Find specific indirect effects between this pair
                spec_ind = [p for p in specific_indirect_list if p["source"] == from_id and p["target"] == to_id]
                effects_summary.append({
                    "from": from_id,
                    "to": to_id,
                    "direct": direct,
                    "indirect": indirect,
                    "total": total,
                    "specific_indirect": spec_ind,
                })

    return {
        "direct_matrix": path_matrix.tolist() if hasattr(path_matrix, "tolist") else path_matrix,
        "total_indirect_matrix": indirect_effects_mat.tolist() if hasattr(indirect_effects_mat, "tolist") else indirect_effects_mat,
        "total_effects_matrix": total_effects_mat.tolist() if hasattr(total_effects_mat, "tolist") else total_effects_mat,
        "specific_indirect": specific_indirect_list,
        "effects_summary": effects_summary,
    }
