from __future__ import annotations

import os
import secrets
from typing import List, Tuple

CLAUDE_CLI_PATH = os.environ.get("CLAUDE_CLI_PATH", "claude")
DEFAULT_PORT = int(os.environ.get("PROXY_PORT", "9090"))
REQUEST_TIMEOUT = int(os.environ.get("REQUEST_TIMEOUT", "300"))

MODEL_MAP = {
    "claude-opus": "opus",
    "claude-sonnet": "sonnet",
    "claude-haiku": "haiku",
}

AVAILABLE_MODELS = [
    "claude-opus-4-7",
    "claude-sonnet-4-6",
    "claude-haiku-4-5",
]


def _load_api_keys() -> Tuple[List[str], bool]:
    raw = os.environ.get("PROXY_API_KEYS") or os.environ.get("PROXY_API_KEY") or ""
    keys = [k.strip() for k in raw.split(",") if k.strip()]
    if keys:
        return keys, False
    generated = "sk-proxy-" + secrets.token_urlsafe(32)
    return [generated], True


API_KEYS, API_KEY_AUTO_GENERATED = _load_api_keys()
