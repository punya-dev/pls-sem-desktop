"""
Unit tests for Parallel Bootstrapping and Cancellation (Phase 4).
"""

import threading
import time
import unittest
import numpy as np
import pandas as pd
from engine.pls.bootstrap import ParallelBootstrapper


class TestParallelBootstrap(unittest.TestCase):

    def setUp(self):
        np.random.seed(123)
        n = 150

        c1 = np.random.normal(0, 1, n)
        c2 = 0.6 * c1 + np.random.normal(0, 0.5, n)

        self.df = pd.DataFrame({
            "x1": 0.8 * c1 + np.random.normal(0, 0.4, n),
            "x2": 0.85 * c1 + np.random.normal(0, 0.4, n),
            "y1": 0.8 * c2 + np.random.normal(0, 0.4, n),
            "y2": 0.85 * c2 + np.random.normal(0, 0.4, n),
        })

        self.model_spec = {
            "constructs": [
                {"id": "X", "name": "X", "type": "reflective", "indicators": ["x1", "x2"]},
                {"id": "Y", "name": "Y", "type": "reflective", "indicators": ["y1", "y2"]},
            ],
            "indicators": [
                {"id": "x1", "column": "x1"},
                {"id": "x2", "column": "x2"},
                {"id": "y1", "column": "y1"},
                {"id": "y2", "column": "y2"},
            ],
            "paths": [
                {"from": "X", "to": "Y"},
            ],
        }

    def test_parallel_bootstrap_execution_and_progress(self):
        booter = ParallelBootstrapper(n_workers=2, chunk_size=10)
        progress_calls = []

        def on_progress(current, total):
            progress_calls.append((current, total))

        res = booter.run(
            self.df,
            self.model_spec,
            n_boot=100,
            seed=42,
            progress_callback=on_progress,
        )

        self.assertEqual(res["n_boot"], 100)
        self.assertGreater(len(progress_calls), 0)
        self.assertEqual(progress_calls[-1], (100, 100))

        # Check path significance
        paths = res["paths"]
        self.assertEqual(len(paths), 1)
        p0 = paths[0]
        self.assertEqual(p0["from"], "X")
        self.assertEqual(p0["to"], "Y")
        self.assertGreater(p0["original"], 0.4)
        self.assertGreater(p0["se"], 0.0)
        self.assertGreater(p0["t_stat"], 1.96)
        self.assertLess(p0["p_value"], 0.05)
        self.assertIn(p0["significance"], ["*", "**", "***"])
        self.assertLess(p0["ci_low"], p0["ci_high"])

    def test_parallel_bootstrap_cancellation(self):
        booter = ParallelBootstrapper(n_workers=2, chunk_size=5)
        cancel_event = threading.Event()

        def cancel_after_start(cur, tot):
            if cur >= 10:
                cancel_event.set()

        with self.assertRaises(InterruptedError):
            booter.run(
                self.df,
                self.model_spec,
                n_boot=200,
                seed=42,
                progress_callback=cancel_after_start,
                cancel_event=cancel_event,
            )


if __name__ == "__main__":
    unittest.main()
