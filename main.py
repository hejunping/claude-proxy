from __future__ import annotations

import hmac
import json
import logging
import uuid
from typing import Any, Dict, List, Optional, Union

import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse

import claude_runner
from config import (
    API_KEY_AUTO_GENERATED,
    API_KEYS,
    AVAILABLE_MODELS,
    DEFAULT_PORT,
)
from models import (
    MessagesRequest,
    MessagesResponse,
    ModelInfo,
    Usage,
    _new_message_id,
)

logger = logging.getLogger("claude_proxy")

app = FastAPI(title="Claude CLI Proxy", version="2.0.0")

ANTHROPIC_VERSION = "2023-06-01"


def _new_request_id() -> str:
    return "req_" + uuid.uuid4().hex[:24]


def _extract_api_key(request: Request) -> Optional[str]:
    key = request.headers.get("x-api-key")
    if key:
        return key.strip()
    auth = request.headers.get("authorization") or ""
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return None


def _key_is_valid(provided: str) -> bool:
    return any(hmac.compare_digest(provided, k) for k in API_KEYS)


# IMPORTANT: middleware registration order = innermost first.
# Final wrapping (outer -> inner): CORS -> add_response_headers -> auth -> route.
# This guarantees that 401s from auth still pass back through add_response_headers
# (so request-id is set) and CORS (so the browser can read the body).

@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    if request.method == "OPTIONS":
        return await call_next(request)

    provided = _extract_api_key(request)
    if not provided:
        return JSONResponse(
            status_code=401,
            content={
                "type": "error",
                "error": {
                    "type": "authentication_error",
                    "message": (
                        "Missing API key. Provide it via 'x-api-key: <key>' "
                        "or 'Authorization: Bearer <key>'."
                    ),
                },
            },
        )
    if not _key_is_valid(provided):
        return JSONResponse(
            status_code=401,
            content={
                "type": "error",
                "error": {
                    "type": "authentication_error",
                    "message": "Invalid API key.",
                },
            },
        )
    return await call_next(request)


@app.middleware("http")
async def add_response_headers(request: Request, call_next):
    response = await call_next(request)
    req_id = _new_request_id()
    response.headers.setdefault("request-id", req_id)
    response.headers.setdefault("anthropic-request-id", req_id)
    response.headers.setdefault("anthropic-version", ANTHROPIC_VERSION)
    return response


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Session-ID", "anthropic-request-id", "request-id", "anthropic-version"],
)


@app.on_event("startup")
async def _log_auth_banner() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    if API_KEY_AUTO_GENERATED:
        key = API_KEYS[0]
        logger.warning(
            "PROXY_API_KEYS not set. Generated a temporary key for this process:\n"
            "    %s\n"
            "  Pass it via 'x-api-key' or 'Authorization: Bearer <key>'.\n"
            "  Set PROXY_API_KEYS=<key1,key2,...> in env for a stable key.",
            key,
        )
    else:
        logger.info("API key auth enabled (%d key%s configured).", len(API_KEYS), "" if len(API_KEYS) == 1 else "s")


def anthropic_error(
    message: str,
    error_type: str = "api_error",
    status_code: int = 500,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "type": "error",
            "error": {"type": error_type, "message": message},
        },
    )


def extract_text(content: Union[str, List[Dict[str, Any]]]) -> str:
    if isinstance(content, str):
        return content
    parts: List[str] = []
    for block in content:
        if not isinstance(block, dict):
            continue
        btype = block.get("type")
        if btype == "text":
            parts.append(block.get("text", ""))
        elif btype == "tool_result":
            inner = block.get("content")
            if isinstance(inner, str):
                parts.append(inner)
            elif isinstance(inner, list):
                parts.append(extract_text(inner))
    return "\n".join(parts)


def flatten_system(system: Optional[Union[str, List[Dict[str, Any]]]]) -> Optional[str]:
    if system is None:
        return None
    if isinstance(system, str):
        return system
    parts: List[str] = []
    for block in system:
        if isinstance(block, dict) and block.get("type") == "text":
            parts.append(block.get("text", ""))
    return "\n".join(p for p in parts if p) or None


def normalize_messages(req: MessagesRequest) -> List[Dict[str, str]]:
    flat: List[Dict[str, str]] = []
    sys_text = flatten_system(req.system)
    if sys_text:
        flat.append({"role": "system", "content": sys_text})
    for m in req.messages:
        flat.append({"role": m.role, "content": extract_text(m.content)})
    return flat


def sse(event: str, data: Dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@app.get("/health")
async def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.get("/v1/models")
async def list_models() -> Dict[str, Any]:
    data = [
        ModelInfo(
            id=model_id,
            display_name=model_id.replace("-", " ").title(),
            created_at="2025-01-01T00:00:00Z",
        ).model_dump()
        for model_id in AVAILABLE_MODELS
    ]
    return {
        "data": data,
        "first_id": data[0]["id"] if data else None,
        "last_id": data[-1]["id"] if data else None,
        "has_more": False,
    }


@app.post("/v1/messages")
async def messages_endpoint(request: Request):
    try:
        body = await request.json()
    except json.JSONDecodeError:
        return anthropic_error("Invalid JSON body", "invalid_request_error", 400)

    try:
        req = MessagesRequest(**body)
    except Exception as e:
        return anthropic_error(str(e), "invalid_request_error", 400)

    flat_messages = normalize_messages(req)

    incoming_session = request.headers.get("X-Session-ID")
    is_resume = incoming_session is not None
    session_id = incoming_session or str(uuid.uuid4())

    if req.stream:
        response = StreamingResponse(
            stream_messages(flat_messages, req, session_id=session_id, is_resume=is_resume),
            media_type="text/event-stream",
        )
        response.headers["X-Session-ID"] = session_id
        return response

    try:
        result = await claude_runner.run_sync(
            messages=flat_messages,
            model=req.model,
            max_tokens=req.max_tokens,
            session_id=session_id if not is_resume else None,
            resume_session_id=session_id if is_resume else None,
        )
    except FileNotFoundError:
        return anthropic_error("Claude CLI not found in PATH", "api_error", 503)
    except TimeoutError as e:
        return anthropic_error(str(e), "timeout_error", 504)
    except RuntimeError as e:
        return anthropic_error(str(e), "api_error", 502)

    resp = MessagesResponse(
        model=result["model"],
        content=[{"type": "text", "text": result["text"]}],
        stop_reason=result.get("stop_reason", "end_turn"),
        stop_sequence=result.get("stop_sequence"),
        usage=Usage(**result["usage"]),
    )
    response = JSONResponse(content=resp.model_dump())
    response.headers["X-Session-ID"] = session_id
    return response


async def stream_messages(
    flat_messages: List[Dict[str, str]],
    request: MessagesRequest,
    session_id: Optional[str],
    is_resume: bool,
):
    message_id = _new_message_id()
    model = request.model
    output_tokens = 0
    final_usage: Optional[Dict[str, int]] = None
    final_stop_reason = "end_turn"
    final_stop_sequence: Optional[str] = None
    content_block_started = False

    yield sse("message_start", {
        "type": "message_start",
        "message": {
            "id": message_id,
            "type": "message",
            "role": "assistant",
            "content": [],
            "model": model,
            "stop_reason": None,
            "stop_sequence": None,
            "usage": {
                "input_tokens": 0,
                "output_tokens": 0,
                "cache_creation_input_tokens": 0,
                "cache_read_input_tokens": 0,
            },
        },
    })

    try:
        async for event in claude_runner.run_stream(
            messages=flat_messages,
            model=request.model,
            max_tokens=request.max_tokens,
            session_id=session_id if not is_resume else None,
            resume_session_id=session_id if is_resume else None,
        ):
            etype = event["type"]

            if etype == "delta":
                if not content_block_started:
                    yield sse("content_block_start", {
                        "type": "content_block_start",
                        "index": 0,
                        "content_block": {"type": "text", "text": ""},
                    })
                    content_block_started = True
                text = event["text"]
                output_tokens += max(1, len(text) // 4)
                yield sse("content_block_delta", {
                    "type": "content_block_delta",
                    "index": 0,
                    "delta": {"type": "text_delta", "text": text},
                })

            elif etype == "usage":
                final_usage = {
                    "input_tokens": event.get("input_tokens", 0),
                    "output_tokens": event.get("output_tokens", output_tokens),
                }
                for k in ("cache_creation_input_tokens", "cache_read_input_tokens"):
                    if k in event:
                        final_usage[k] = event[k]

            elif etype == "stop":
                final_stop_reason = event.get("stop_reason") or "end_turn"
                final_stop_sequence = event.get("stop_sequence")

        if content_block_started:
            yield sse("content_block_stop", {
                "type": "content_block_stop",
                "index": 0,
            })

        delta_usage = final_usage or {"input_tokens": 0, "output_tokens": output_tokens}
        delta_usage.setdefault("cache_creation_input_tokens", 0)
        delta_usage.setdefault("cache_read_input_tokens", 0)
        yield sse("message_delta", {
            "type": "message_delta",
            "delta": {
                "stop_reason": final_stop_reason,
                "stop_sequence": final_stop_sequence,
            },
            "usage": delta_usage,
        })

        yield sse("message_stop", {"type": "message_stop"})

    except FileNotFoundError:
        yield sse("error", {
            "type": "error",
            "error": {"type": "api_error", "message": "Claude CLI not found in PATH"},
        })
    except TimeoutError as e:
        yield sse("error", {
            "type": "error",
            "error": {"type": "timeout_error", "message": str(e)},
        })
    except RuntimeError as e:
        yield sse("error", {
            "type": "error",
            "error": {"type": "api_error", "message": str(e)},
        })


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=DEFAULT_PORT, log_level="info")
