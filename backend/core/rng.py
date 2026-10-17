"""
RNG & Parallel Seed Management.
Provides deterministic SeedSequence spawning so that stochastic procedures
(bootstrap, permutation, blindfolding, FIMIX) return identical results regardless of worker counts.
"""

from typing import List, Optional, Tuple
import math
import numpy as np


def spawn_seeds(master_seed: Optional[int], n: int) -> List[int]:
    """
    Deterministically spawns n integer seeds from a master seed using SeedSequence.
    If master_seed is None, a default fixed seed 42 is used for reproducibility.
    """
    seed_val = 42 if master_seed is None else master_seed
    ss = np.random.SeedSequence(seed_val)
    child_seeds = ss.generate_state(n)
    return [int(s) for s in child_seeds]


def resample_indices(n_samples: int, rng: np.random.Generator) -> np.ndarray:
    """
    Draws bootstrap resample indices with replacement of size n_samples.
    """
    return rng.choice(n_samples, size=n_samples, replace=True)


def chunk_tasks(n_tasks: int, n_workers: int, min_chunk_size: int = 5, max_chunk_size: int = 50) -> List[Tuple[int, int]]:
    """
    Splits n_tasks into roughly equal chunk ranges (start, end) across workers.
    """
    if n_tasks <= 0:
        return []
    target_chunks = max(1, n_workers * 4)
    chunk_size = max(min_chunk_size, min(max_chunk_size, math.ceil(n_tasks / target_chunks)))
    chunks = []
    for start in range(0, n_tasks, chunk_size):
        end = min(start + chunk_size, n_tasks)
        chunks.append((start, end))
    return chunks
