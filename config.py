import os

CLAUDE_CLI_PATH = os.environ.get("CLAUDE_CLI_PATH", "claude")
DEFAULT_PORT = int(os.environ.get("PROXY_PORT", "9090"))
REQUEST_TIMEOUT = int(os.environ.get("REQUEST_TIMEOUT", "300"))

MODEL_MAP = {
    "gpt-4": "opus",
    "gpt-4o": "sonnet",
    "gpt-4o-mini": "haiku",
    "gpt-3.5-turbo": "haiku",
    "claude-opus": "opus",
    "claude-sonnet": "sonnet",
    "claude-haiku": "haiku",
}

AVAILABLE_MODELS = [
    "claude-opus-4-7",
    "claude-sonnet-4-6",
    "claude-haiku-4-5",
]
