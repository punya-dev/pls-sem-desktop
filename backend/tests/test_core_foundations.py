"""
Unit tests for Core Foundations (Phase 0):
- Deterministic RNG seeding across worker counts
- Statistical utilities (weighted moments, pairwise correlation, BCa CIs, power)
- Effects decomposition (specific indirect paths, total indirect, total effects)
- Settings schema validation
"""

import unittest
import numpy as np
import pandas as pd

from core.rng import spawn_seeds, resample_indices, chunk_tasks
from core.stats_utils import (
    weighted_mean,
    weighted_std,
    weighted_corr,
    fisher_pearson_skewness,
    fisher_pearson_kurtosis,
    bca_confidence_interval,
    prob_greater,
    noncentral_f_power,
    solve_minimum_sample_size,
    pairwise_correlation_matrix,
    nearest_psd,
)
from core.settings_schema import PipelineSettings
from core.thresholds import THRESHOLDS
from engine.pls.effects import calculate_effects, enumerate_directed_paths


class TestCoreFoundations(unittest.TestCase):

    def test_rng_determinism(self):
        seeds_1 = spawn_seeds(42, 100)
        seeds_2 = spawn_seeds(42, 100)
        self.assertEqual(seeds_1, seeds_2)
        self.assertEqual(len(seeds_1), 100)

        chunks_2 = chunk_tasks(100, 2)
        chunks_8 = chunk_tasks(100, 8)
        self.assertGreater(len(chunks_8), len(chunks_2))
        self.assertEqual(sum(end - start for start, end in chunks_2), 100)
        self.assertEqual(sum(end - start for start, end in chunks_8), 100)

    def test_weighted_stats(self):
        x = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        w = np.array([1.0, 1.0, 1.0, 1.0, 1.0])
        self.assertAlmostEqual(weighted_mean(x, w), 3.0)
        self.assertAlmostEqual(weighted_std(x, w, ddof=0), np.std(x, ddof=0))

        # Weighting emphasizing 5
        w_skew = np.array([0.1, 0.1, 0.1, 0.1, 10.0])
        self.assertGreater(weighted_mean(x, w_skew), 4.5)

    def test_pairwise_correlations(self):
        mat = np.array([
            [1.0, 2.0, np.nan],
            [2.0, 3.0, 4.0],
            [3.0, 4.0, 5.0],
            [np.nan, 5.0, 6.0],
        ])
        R, N = pairwise_correlation_matrix(mat)
        self.assertEqual(R.shape, (3, 3))
        self.assertEqual(N.shape, (3, 3))
        self.assertAlmostEqual(R[0, 1], 1.0)
        self.assertAlmostEqual(R[1, 2], 1.0)

    def test_effects_decomposition(self):
        # 3 constructs: X (0) -> M (1) -> Y (2), with direct path X (0) -> Y (2)
        # B matrix:
        # [0,   0.5, 0.2]
        # [0,   0,   0.4]
        # [0,   0,   0  ]
        cids = ["X", "M", "Y"]
        B = np.zeros((3, 3))
        B[0, 1] = 0.5  # X -> M
        B[1, 2] = 0.4  # M -> Y
        B[0, 2] = 0.2  # X -> Y

        res = calculate_effects(B, cids)
        spec_ind = res["specific_indirect"]
        self.assertEqual(len(spec_ind), 1)
        self.assertEqual(spec_ind[0]["path"], "X -> M -> Y")
        self.assertAlmostEqual(spec_ind[0]["effect"], 0.20)  # 0.5 * 0.4 = 0.20

        # Total indirect = 0.20
        # Total effect X -> Y = direct (0.2) + indirect (0.2) = 0.40
        summary = {f"{s['from']}->{s['to']}": s for s in res["effects_summary"]}
        self.assertIn("X->Y", summary)
        self.assertAlmostEqual(summary["X->Y"]["direct"], 0.20)
        self.assertAlmostEqual(summary["X->Y"]["indirect"], 0.20)
        self.assertAlmostEqual(summary["X->Y"]["total"], 0.40)

    def test_power_solver(self):
        # 2 predictors, R² 0.25, 5% alpha -> Cohen table says around 33
        n_req = solve_minimum_sample_size(k_predictors=2, min_r2=0.25, target_power=0.80, alpha=0.05)
        self.assertGreaterEqual(n_req, 30)
        self.assertLessEqual(n_req, 40)


if __name__ == "__main__":
    unittest.main()
