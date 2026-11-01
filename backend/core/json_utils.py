"""
JSON sanitization utility for ensuring RFC 8259 strict compliance (no NaN, Inf, -Inf).
Starlette / FastAPI's JSONResponse enforces allow_nan=False, causing unhandled 500
errors if statistical calculations result in NaN or Inf values.
"""

import math
from typing import Any
import numpy as np


def sanitize_for_json(obj: Any) -> Any:
    """
    Recursively replaces NaN, Infinity, -Infinity with None so that the object
    is strictly compliant with standard JSON and Starlette/FastAPI's JSONResponse.
    Also converts numpy primitives and arrays into Python standard types.
    """
    if obj is None:
        return None
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    if isinstance(obj, (np.floating,)):
        val = float(obj)
        if math.isnan(val) or math.isinf(val):
            return None
        return val
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.bool_,)):
        return bool(obj)
    if isinstance(obj, np.ndarray):
        return [sanitize_for_json(item) for item in obj.tolist()]
    if isinstance(obj, dict):
        return {str(k): sanitize_for_json(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [sanitize_for_json(item) for item in obj]
    if hasattr(obj, "model_dump"):
        return sanitize_for_json(obj.model_dump())
    if hasattr(obj, "to_dict"):
        return sanitize_for_json(obj.to_dict())
    return obj

