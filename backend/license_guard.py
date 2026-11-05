"""
License guard middleware for FastAPI.

Gates computation-heavy endpoints behind license validation.
In development mode (DEV_MODE=true), all requests are allowed.

The frontend sends the license token in the X-License-Token header.
This middleware verifies the token's Ed25519 signature and checks expiry.

For floating licenses, this is where we would check with the license server
to verify seat availability. For now, we validate the token offline.
"""

import os
import json
import base64
import hashlib
import time
from typing import Optional, List
from datetime import datetime, timezone
from functools import lru_cache

from fastapi import Request, HTTPException

# ─── Configuration ──────────────────────────────────────────────────────

# Set to True during development to bypass all license checks
DEV_MODE = os.environ.get("STATSEM_DEV_MODE", "true").lower() == "true"

# Routes that require a valid license
GATED_PREFIXES: List[str] = [
    "/project/run-pls",
    "/project/bootstrap-start",
    "/blindfolding/run",
    "/analysis/mediation",
    "/analysis/moderation",
    "/analysis/quadratic",
    "/analysis/ipma",
    "/analysis/mga",
    "/analysis/fimix",
    "/analysis/cta",
    "/analysis/micom",
    "/analysis/hcm",
    "/power/calculate",
]

# ─── Token Verification ────────────────────────────────────────────────

def _load_verifying_key() -> Optional[bytes]:
    """
    Load the Ed25519 verifying (public) key.
    In dev mode, loads from the dev keypair directory.
    In production, this would be a hardcoded key.
    """
    try:
        # Try loading from the same dev_keys dir that Rust uses
        config_dir = os.path.expanduser("~/Library/Application Support/StatSEM/dev_keys")
        if not os.path.exists(config_dir):
            # Linux fallback
            config_dir = os.path.expanduser("~/.config/StatSEM/dev_keys")
        
        vk_path = os.path.join(config_dir, "verifying_key.b64")
        if os.path.exists(vk_path):
            with open(vk_path, "r") as f:
                vk_b64 = f.read().strip()
            return base64.b64decode(vk_b64)
    except Exception as e:
        print(f"[license_guard] Warning: Could not load verifying key: {e}")
    
    return None


def _verify_token(token_string: str) -> dict:
    """
    Verify a signed license token and return the payload.
    
    Token format: base64-encoded JSON containing:
      { "payload_b64": "...", "signature_b64": "..." }
    
    The payload_b64 is verified against the signature using Ed25519.
    """
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    except ImportError:
        # If cryptography is not installed, we can't verify tokens
        # In dev mode this is fine; in production we'd require it
        if DEV_MODE:
            # Try to decode the payload without verification in dev mode
            try:
                token_json = base64.b64decode(token_string)
                token_data = json.loads(token_json)
                payload_json = base64.b64decode(token_data["payload_b64"])
                return json.loads(payload_json)
            except Exception:
                pass
        raise HTTPException(
            status_code=500,
            detail="License verification requires the 'cryptography' package"
        )
    
    # Load verifying key
    vk_bytes = _load_verifying_key()
    if vk_bytes is None:
        if DEV_MODE:
            # In dev mode without a key, try to decode without verification
            try:
                token_json = base64.b64decode(token_string)
                token_data = json.loads(token_json)
                payload_json = base64.b64decode(token_data["payload_b64"])
                return json.loads(payload_json)
            except Exception as e:
                raise HTTPException(status_code=403, detail=f"Invalid license token format: {e}")
        raise HTTPException(status_code=500, detail="License verification key not configured")
    
    try:
        # Decode the token envelope
        token_json = base64.b64decode(token_string)
        token_data = json.loads(token_json)
        
        payload_b64 = token_data["payload_b64"]
        signature_b64 = token_data["signature_b64"]
        
        # Verify Ed25519 signature
        public_key = Ed25519PublicKey.from_public_bytes(vk_bytes)
        signature = base64.b64decode(signature_b64)
        public_key.verify(signature, payload_b64.encode("utf-8"))
        
        # Decode and return payload
        payload_json = base64.b64decode(payload_b64)
        payload = json.loads(payload_json)
        
        return payload
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=403, detail=f"License verification failed: {e}")


def _check_expiry(payload: dict) -> None:
    """Check if the license has expired."""
    expires_at = payload.get("expires_at", "")
    if not expires_at:
        raise HTTPException(status_code=403, detail="License has no expiry date")
    
    try:
        # Parse ISO 8601 datetime
        expiry = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        if now > expiry:
            raise HTTPException(
                status_code=403,
                detail=f"License expired on {expiry.strftime('%Y-%m-%d')}. Please renew your subscription."
            )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=403, detail=f"Invalid license expiry date: {e}")


def _check_feature(payload: dict, path: str) -> None:
    """Check if the license includes the required feature for this endpoint."""
    features = payload.get("features", [])
    
    # Map routes to required features
    feature_map = {
        "/project/run-pls": "pls_basic",
        "/project/bootstrap-start": "bootstrap",
        "/blindfolding/run": "blindfolding",
        "/analysis/mediation": "mediation",
        "/analysis/moderation": "moderation",
        "/analysis/quadratic": "quadratic",
        "/analysis/ipma": "ipma",
        "/analysis/mga": "mga",
        "/analysis/fimix": "fimix",
        "/analysis/cta": "cta",
        "/analysis/micom": "micom",
        "/analysis/hcm": "hcm",
        "/power/calculate": "power_analysis",
    }
    
    required = feature_map.get(path)
    if required and required not in features:
        tier = payload.get("tier", "unknown")
        raise HTTPException(
            status_code=403,
            detail=f"Your {tier} license does not include this feature. Please upgrade your plan."
        )


# ─── FastAPI Dependency ─────────────────────────────────────────────────

async def verify_license(request: Request):
    """
    FastAPI dependency that verifies the license for gated routes.
    
    Usage in main.py:
        @app.post("/project/run-pls")
        async def run_pls(..., _license=Depends(verify_license)):
            ...
    """
    # Check if this route needs license verification
    path = request.url.path
    is_gated = any(path.startswith(prefix) for prefix in GATED_PREFIXES)
    
    if not is_gated:
        return  # Not a gated route, allow through
    
    # In dev mode, bypass all checks
    if DEV_MODE:
        return
    
    # Get the license token from headers
    token_string = request.headers.get("X-License-Token", "")
    if not token_string:
        raise HTTPException(
            status_code=403,
            detail="No license token provided. Please activate your StatSEM license."
        )
    
    # Verify the token
    payload = _verify_token(token_string)
    
    # Check expiry
    _check_expiry(payload)
    
    # Check feature access
    _check_feature(payload, path)
    
    # For floating licenses, we would check seat availability here
    # TODO: Implement floating license seat check when license server is ready
    mode = payload.get("mode", "node_locked")
    if mode == "floating":
        # In the future: POST to license server to claim/renew a seat lease
        # For now: allow through (floating seats are server-managed)
        pass
    
    # All checks passed
    return


# ─── Utility: Check if a route is gated ────────────────────────────────

def is_gated_route(path: str) -> bool:
    """Check if a given path is a license-gated route."""
    return any(path.startswith(prefix) for prefix in GATED_PREFIXES)


def get_gated_routes() -> List[str]:
    """Return the list of gated route prefixes."""
    return GATED_PREFIXES.copy()
