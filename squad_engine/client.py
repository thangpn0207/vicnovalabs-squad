#!/usr/bin/env python3
"""
TypeSafe / Jev AI Client Manager with Graceful Offline Fallback.
Safely retrieves API keys from environment or IDE configs without hardcoded secrets.
"""

import os
import sys
from pathlib import Path
from typing import Optional, Dict, Any
from .config import get_config


def load_env_api_key() -> Optional[str]:
    """Retrieve TYPESAFE_API_KEY from os.environ, project .env, or IDE global config."""
    config = get_config()
    return config.typesafe_api_key


_CLIENT_INSTANCE = None
_CLIENT_API_KEY = None


def get_typesafe_client():
    """Retrieve or instantiate a shared TypeSafeClient singleton to reuse connections and avoid socket leaks."""
    global _CLIENT_INSTANCE, _CLIENT_API_KEY
    api_key = load_env_api_key()
    if not api_key:
        return None
    if _CLIENT_INSTANCE is not None and _CLIENT_API_KEY == api_key:
        return _CLIENT_INSTANCE
    try:
        from typesafe_sdk import TypeSafeClient
        if _CLIENT_INSTANCE is not None:
            try:
                _CLIENT_INSTANCE.close()
            except Exception:
                pass
        _CLIENT_INSTANCE = TypeSafeClient(api_key=api_key)
        _CLIENT_API_KEY = api_key
        return _CLIENT_INSTANCE
    except Exception:
        return None


def close_typesafe_client() -> None:
    """Explicitly close and release the shared TypeSafeClient and underlying sockets."""
    global _CLIENT_INSTANCE, _CLIENT_API_KEY
    if _CLIENT_INSTANCE is not None:
        try:
            _CLIENT_INSTANCE.close()
        except Exception:
            pass
        _CLIENT_INSTANCE = None
        _CLIENT_API_KEY = None


def get_api_status() -> Dict[str, Any]:
    """Check Jev / TypeSafe connection status."""
    api_key = load_env_api_key()
    client = get_typesafe_client()
    return {
        "configured": bool(api_key),
        "connected": client is not None,
        "provider": "typesafe-jev" if client is not None else "offline-heuristics",
        "note": "Ready (System One AI active)" if client is not None else "Offline Mode: 100% functional via rule-based heuristics (0 tokens used)."
    }

