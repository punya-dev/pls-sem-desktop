"""
Parallel Bootstrapping Engine for PLS-SEM (Phase 4).

Uses multiprocessing across CPU cores to run resamples in parallel with
progress callbacks, cancellation support, and statistical significance calculations.
"""

import math
import os
import threading
from concurrent.futures import ProcessPoolExecutor, as_completed
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from scipy import stats


def _run_bootstrap_chunk(
    seeds: List[int],
    data_matrix: np.ndarray,
    col_names: List[str],
    spec_dict: Dict[str, Any],
    scheme: str,
    max_iter: int,
    tol: float,
    sign_alignment: bool,
) -> List[Tuple[Dict[Tuple[str, str], float], Dict[Tuple[str, str], float], Dict[Tuple[str, str], float]]]:
    """
    Top-level worker function executed in child processes.
    Takes a list of seeds and returns a list of results for each resample.
    """
    from engine.pls.algorithm import PLSAlgorithm

    algo = PLSAlgorithm(
        scheme=scheme,
        max_iter=max_iter,
        tol=tol,
        sign_alignment=sign_alignment,
        missing_treatment="mean",
    )

    n_samples = data_matrix.shape[0]
    constructs, _, paths = algo._parse_spec(spec_dict)

    chunk_results = []
    df_template = pd.DataFrame(data_matrix, columns=col_names)

    for s in seeds:
        rng = np.random.default_rng(s)
        indices = rng.choice(n_samples, size=n_samples, replace=True)
        resampled_df = df_template.iloc[indices].reset_index(drop=True)

        try:
            res = algo.fit(resampled_df, spec_dict)
            b_paths: Dict[Tuple[str, str], float] = {}
            for (from_c, to_c) in paths:
                val = res["structural"]["path_coefficients"].get(to_c, {}).get(from_c, 0.0)
                b_paths[(from_c, to_c)] = float(val)

            b_loadings: Dict[Tuple[str, str], float] = {}
            b_weights: Dict[Tuple[str, str], float] = {}
            for cid, cinfo in constructs.items():
                for iid in cinfo["indicators"]:
                    l_val = res["measurement"]["outer_loadings"].get(cid, {}).get(iid, 0.0)
                    w_val = res["measurement"]["outer_weights"].get(cid, {}).get(iid, 0.0)
                    b_loadings[(cid, iid)] = float(l_val)
                    b_weights[(cid, iid)] = float(w_val)

            chunk_results.append((b_paths, b_loadings, b_weights))
        except Exception:
            continue

    return chunk_results


class ParallelBootstrapper:
    """
    Orchestrates parallel bootstrapping with CPU process pools, progress tracking,
    and cancellation.
    """

    def __init__(
        self,
        n_workers: Optional[int] = None,
        chunk_size: int = 25,
    ):
        self.n_workers = n_workers or max(1, (os.cpu_count() or 4) - 1)
        self.chunk_size = chunk_size

    def run(
        self,
        data: pd.DataFrame,
        model_spec: Any,
        n_boot: int = 500,
        seed: Optional[int] = 42,
        scheme: str = "path",
        max_iter: int = 300,
        tol: float = 1e-7,
        sign_alignment: bool = True,
        progress_callback: Optional[Callable[[int, int], None]] = None,
        cancel_event: Optional[threading.Event] = None,
    ) -> Dict[str, Any]:
        """
        Executes parallel bootstrap across CPU workers.
        """
        from engine.pls.algorithm import PLSAlgorithm

        base_algo = PLSAlgorithm(
            scheme=scheme,
            max_iter=max_iter,
            tol=tol,
            sign_alignment=sign_alignment,
            missing_treatment="mean",
        )
        base_res = base_algo.fit(data, model_spec)
        constructs, ind_col_map, paths = base_algo._parse_spec(model_spec)

        if hasattr(model_spec, "model_dump"):
            spec_dict = model_spec.model_dump(by_alias=True)
        elif isinstance(model_spec, dict):
            spec_dict = model_spec
        else:
            raise TypeError("model_spec must be a dictionary or ModelSpec instance")

        # Collect required indicators and pre-clean
        all_required_cols = []
        for c in constructs.values():
            for iid in c["indicators"]:
                col = ind_col_map.get(iid, iid)
                all_required_cols.append(col)

        sub_df = data[all_required_cols].copy()
        for col in all_required_cols:
            sub_df[col] = pd.to_numeric(sub_df[col], errors="coerce")
            sub_df[col] = sub_df[col].replace([-99, "-99"], np.nan)
            col_mean = sub_df[col].mean()
            if pd.notna(col_mean):
                sub_df[col] = sub_df[col].fillna(col_mean)
        sub_df = sub_df.dropna()

        data_matrix = sub_df.to_numpy(dtype=float)
        col_names = list(sub_df.columns)

        # Generate unique reproducible seeds for each bootstrap resample
        master_rng = np.random.default_rng(seed if seed is not None else 42)
        all_seeds = [int(master_rng.integers(1, 2**31 - 1)) for _ in range(n_boot)]

        # Chunk seeds
        chunk_size = max(5, min(self.chunk_size, math.ceil(n_boot / (self.n_workers * 4))))
        seed_chunks = [all_seeds[i : i + chunk_size] for i in range(0, n_boot, chunk_size)]

        boot_paths: Dict[Tuple[str, str], List[float]] = {p: [] for p in paths}
        boot_loadings: Dict[Tuple[str, str], List[float]] = {}
        boot_weights: Dict[Tuple[str, str], List[float]] = {}

        for cid, cinfo in constructs.items():
            for iid in cinfo["indicators"]:
                boot_loadings[(cid, iid)] = []
                boot_weights[(cid, iid)] = []

        completed_count = 0

        # Run parallel executor
        with ProcessPoolExecutor(max_workers=self.n_workers) as executor:
            future_to_chunk = {
                executor.submit(
                    _run_bootstrap_chunk,
                    chunk,
                    data_matrix,
                    col_names,
                    spec_dict,
                    scheme,
                    max_iter,
                    tol,
                    sign_alignment,
                ): len(chunk)
                for chunk in seed_chunks
            }

            for future in as_completed(future_to_chunk):
                if cancel_event is not None and cancel_event.is_set():
                    executor.shutdown(wait=False, cancel_futures=True)
                    raise InterruptedError("Bootstrapping was cancelled by the user.")

                chunk_len = future_to_chunk[future]
                try:
                    resample_results = future.result()
                    for b_p, b_l, b_w in resample_results:
                        for p_k, p_v in b_p.items():
                            boot_paths[p_k].append(p_v)
                        for l_k, l_v in b_l.items():
                            boot_loadings[l_k].append(l_v)
                        for w_k, w_v in b_w.items():
                            boot_weights[w_k].append(w_v)
                except Exception as exc:
                    print(f"Bootstrap chunk failed: {exc}")

                completed_count += chunk_len
                if progress_callback:
                    progress_callback(min(completed_count, n_boot), n_boot)

        def _stats(original_val: float, sample_dist: List[float]) -> Dict[str, Any]:
            if not sample_dist:
                return {
                    "original": float(original_val),
                    "mean": float(original_val),
                    "se": 0.0,
                    "t_stat": 0.0,
                    "p_value": 1.0,
                    "ci_low": float(original_val),
                    "ci_high": float(original_val),
                    "significance": "ns",
                }
            se = float(np.std(sample_dist, ddof=1))
            t_stat = float(original_val / se) if se > 1e-9 else 0.0
            p_val = float(2.0 * (1.0 - stats.norm.cdf(abs(t_stat))))
            ci_low = float(np.percentile(sample_dist, 2.5))
            ci_high = float(np.percentile(sample_dist, 97.5))

            if p_val < 0.001:
                sig = "***"
            elif p_val < 0.01:
                sig = "**"
            elif p_val < 0.05:
                sig = "*"
            else:
                sig = "ns"

            return {
                "original": float(original_val),
                "mean": float(np.mean(sample_dist)),
                "se": se,
                "t_stat": t_stat,
                "p_value": p_val,
                "ci_low": ci_low,
                "ci_high": ci_high,
                "significance": sig,
            }

        construct_names = base_res.get("construct_names", {})
        indicator_names = base_res.get("indicator_names", {})

        path_significance = []
        for (from_c, to_c), dist in boot_paths.items():
            orig = base_res["structural"]["path_coefficients"].get(to_c, {}).get(from_c, 0.0)
            st = _stats(orig, dist)
            st["from"] = from_c
            st["to"] = to_c
            st["from_name"] = construct_names.get(from_c, from_c)
            st["to_name"] = construct_names.get(to_c, to_c)
            path_significance.append(st)

        loading_significance = []
        for (cid, iid), dist in boot_loadings.items():
            orig = base_res["measurement"]["outer_loadings"].get(cid, {}).get(iid, 0.0)
            st = _stats(orig, dist)
            st["construct"] = cid
            st["construct_name"] = construct_names.get(cid, cid)
            st["indicator"] = iid
            st["indicator_name"] = indicator_names.get(iid, iid)
            loading_significance.append(st)

        weight_significance = []
        for (cid, iid), dist in boot_weights.items():
            orig = base_res["measurement"]["outer_weights"].get(cid, {}).get(iid, 0.0)
            st = _stats(orig, dist)
            st["construct"] = cid
            st["construct_name"] = construct_names.get(cid, cid)
            st["indicator"] = iid
            st["indicator_name"] = indicator_names.get(iid, iid)
            weight_significance.append(st)

        return {
            "n_boot": n_boot,
            "actual_samples": len(list(boot_paths.values())[0]) if boot_paths else 0,
            "paths": path_significance,
            "loadings": loading_significance,
            "weights": weight_significance,
        }
