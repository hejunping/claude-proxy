from __future__ import annotations

import json
import time
import uuid

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse

import claude_runner
from config import AVAILABLE_MODELS, DEFAULT_PORT
from models import (
    ChatCompletionChunk,
    ChatCompletionRequest,
    ChatCompletionResponse,
    Choice,
    ChoiceMessage,
    DeltaContent,
    StreamChoice,
    Usage,
)

app = FastAPI(title="Claude CLI Proxy", version="1.0.0")


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/v1/models")
async def list_models():
    return {
        "object": "list",
        "data": [
            {
                "id": model_id,
                "object": "model",
                "created": 1700000000,
                "owned_by": "anthropic",
            }
            for model_id in AVAILABLE_MODELS
        ],
    }


@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    body = await request.json()
    req = ChatCompletionRequest(**body)
    messages = [{"role": m.role, "content": m.content} for m in req.messages]

    session_id = request.headers.get("X-Session-ID")
    is_resume = session_id is not None

    if not session_id:
        session_id = str(uuid.uuid4())

    if req.stream:
        response = StreamingResponse(
            stream_response(messages, req, session_id=session_id, is_resume=is_resume),
            media_type="text/event-stream",
        )
        response.headers["X-Session-ID"] = session_id
        return response

    try:
        result = await claude_runner.run_sync(
            messages=messages,
            model=req.model,
            max_tokens=req.max_tokens,
            session_id=session_id if not is_resume else None,
            resume_session_id=session_id if is_resume else None,
        )
    except FileNotFoundError:
        raise HTTPException(status_code=503, detail="Claude CLI not found in PATH")
    except TimeoutError as e:
        raise HTTPException(status_code=504, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))

    resp = ChatCompletionResponse(
        model=result["model"],
        choices=[
            Choice(message=ChoiceMessage(content=result["text"]))
        ],
        usage=Usage(**result["usage"]),
    )
    response = JSONResponse(content=resp.model_dump())
    response.headers["X-Session-ID"] = session_id
    return response


async def stream_response(messages: list, request: ChatCompletionRequest, session_id: str, is_resume: bool):
    completion_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"
    created = int(time.time())
    model = request.model

    first_chunk = ChatCompletionChunk(
        id=completion_id,
        created=created,
        model=model,
        choices=[StreamChoice(delta=DeltaContent(role="assistant"))],
    )
    yield f"data: {first_chunk.model_dump_json()}\n\n"

    try:
        async for event in claude_runner.run_stream(
            messages=messages,
            model=request.model,
            max_tokens=request.max_tokens,
            session_id=session_id if not is_resume else None,
            resume_session_id=session_id if is_resume else None,
        ):
            if event["type"] == "delta":
                chunk = ChatCompletionChunk(
                    id=completion_id,
                    created=created,
                    model=model,
                    choices=[StreamChoice(delta=DeltaContent(content=event["text"]))],
                )
                yield f"data: {chunk.model_dump_json()}\n\n"

            elif event["type"] == "stop":
                final_chunk = ChatCompletionChunk(
                    id=completion_id,
                    created=created,
                    model=model,
                    choices=[StreamChoice(delta=DeltaContent(), finish_reason="stop")],
                )
                yield f"data: {final_chunk.model_dump_json()}\n\n"

    except FileNotFoundError:
        error = json.dumps({"error": {"message": "Claude CLI not found", "type": "server_error"}})
        yield f"data: {error}\n\n"

    yield "data: [DONE]\n\n"


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=DEFAULT_PORT, log_level="info")
