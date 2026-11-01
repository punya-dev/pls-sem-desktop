"""
Automated Pytest Suite for SmartPLS 4 Parity.
Runs the comparison harness across all smartpls_*.json reference models
to guarantee that calculation results remain locked to SmartPLS 4 benchmarks.
"""

import os
import sys
import glob
import json
import pytest

# Ensure project root is on sys.path for tools
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from tools.compare_to_smartpls import compare_file, BACKEND_DIR


def get_reference_files():
    ref_dir = os.path.join(BACKEND_DIR, "tests", "reference")
    files = sorted(glob.glob(os.path.join(ref_dir, "smartpls_*.json")))
    return files


@pytest.mark.parametrize("ref_file", get_reference_files(), ids=lambda p: os.path.basename(p))
def test_smartpls_parity(ref_file):
    with open(ref_file, "r") as fp:
        ref_data = json.load(fp)

    # If essential reference metrics are missing, skip with message
    has_paths = bool(ref_data.get("paths") or ref_data.get("path_coefficients"))
    has_r2 = bool(ref_data.get("r2") or ref_data.get("r_squared"))

    if not has_paths and not has_r2:
        pytest.skip(f"Reference file {os.path.basename(ref_file)} lacks benchmark values.")

    passed = compare_file(ref_file)
    assert passed, f"SmartPLS parity failed for {os.path.basename(ref_file)}. See comparison tables above."

