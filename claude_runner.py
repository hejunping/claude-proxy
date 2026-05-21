from __future__ import annotations

import asyncio
import json
from typing import AsyncGenerator, List, Optional, Tuple

from config import CLAUDE_BARE, CLAUDE_CLI_PATH, MODEL_MAP, REQUEST_TIMEOUT


def resolve_model(model: str) -> Optional[str]:
    if model in MODEL_MAP:
        return MODEL_MAP[model]
    return model


def build_prompt(messages: List[dict]) -> Tuple[str, Optional[str]]:
    system_parts = []
    conversation = []

    for msg in messages:
        if msg["role"] == "system":
            system_parts.append(msg["content"])
        else:
            conversation.append(msg)

    system_prompt = "\n".join(system_parts) if system_parts else None

    if not conversation:
        return "", system_prompt

    if len(conversation) == 1:
        return conversation[0]["content"], system_prompt

    # Multi-turn: format as conversation, last user message is the prompt
    history_lines = []
    for msg in conversation[:-1]:
        role_label = "User" if msg["role"] == "user" else "Assistant"
        history_lines.append(f"{role_label}: {msg['content']}")

    last_message = conversation[-1]["content"]
    prompt = "[Previous conversation]\n" + "\n".join(history_lines) + f"\n\n[Current request]\n{last_message}"
    return prompt, system_prompt


def build_command(
    prompt: str,
    system_prompt: Optional[str],
    model: Optional[str],
    streaming: bool,
    session_id: Optional[str] = None,
    resume_session_id: Optional[str] = None,
) -> List[str]:
    cmd = [CLAUDE_CLI_PATH, "-p", prompt]

    if streaming:
        cmd.extend(["--output-format", "stream-json", "--verbose"])
    else:
        cmd.extend(["--output-format", "json"])

    if CLAUDE_BARE:
        cmd.append("--bare")

    if resume_session_id:
        cmd.extend(["--resume", resume_session_id])
    elif session_id:
        cmd.extend(["--session-id", session_id])

    if system_prompt:
        cmd.extend(["--system-prompt", system_prompt])

    if model:
        resolved = resolve_model(model)
        if resolved:
            cmd.extend(["--model", resolved])

    return cmd


async def run_sync(
    messages: List[dict],
    model: str,
    max_tokens: Optional[int] = None,
    session_id: Optional[str] = None,
    resume_session_id: Optional[str] = None,
) -> dict:
    del max_tokens  # accepted for API compatibility, but Claude CLI doesn't expose a token cap

    if resume_session_id:
        last_user = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
        prompt = last_user
        system_prompt = None
    else:
        prompt, system_prompt = build_prompt(messages)

    cmd = build_command(
        prompt, system_prompt, model,
        streaming=False, session_id=session_id, resume_session_id=resume_session_id,
    )

    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    try:
        stdout, stderr = await asyncio.wait_for(
            process.communicate(), timeout=REQUEST_TIMEOUT
        )
    except asyncio.TimeoutError:
        process.kill()
        raise TimeoutError(f"Claude CLI timed out after {REQUEST_TIMEOUT}s")

    if process.returncode != 0:
        error_msg = stderr.decode().strip() if stderr else "Unknown CLI error"
        raise RuntimeError(f"Claude CLI error (exit {process.returncode}): {error_msg}")

    result = json.loads(stdout.decode())
    text = result.get("result", "")
    raw_usage = result.get("usage", {}) or {}
    usage = {
        "input_tokens": raw_usage.get("input_tokens", 0),
        "output_tokens": raw_usage.get("output_tokens", 0),
    }
    if "cache_creation_input_tokens" in raw_usage:
        usage["cache_creation_input_tokens"] = raw_usage["cache_creation_input_tokens"]
    if "cache_read_input_tokens" in raw_usage:
        usage["cache_read_input_tokens"] = raw_usage["cache_read_input_tokens"]

    return {
        "text": text,
        "usage": usage,
        "model": result.get("model", model),
        "stop_reason": result.get("stop_reason", "end_turn"),
        "stop_sequence": result.get("stop_sequence"),
    }


async def run_stream(
    messages: List[dict],
    model: str,
    max_tokens: Optional[int] = None,
    session_id: Optional[str] = None,
    resume_session_id: Optional[str] = None,
) -> AsyncGenerator[dict, None]:
    del max_tokens  # accepted for API compatibility, but Claude CLI doesn't expose a token cap

    if resume_session_id:
        last_user = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
        prompt = last_user
        system_prompt = None
    else:
        prompt, system_prompt = build_prompt(messages)

    cmd = build_command(
        prompt, system_prompt, model,
        streaming=True, session_id=session_id, resume_session_id=resume_session_id,
    )

    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    sent_text_length = 0

    try:
        async for line in process.stdout:
            line = line.decode().strip()
            if not line:
                continue

            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue

            event_type = data.get("type")

            if event_type == "assistant":
                message = data.get("message", {})
                content_blocks = message.get("content", [])
                for block in content_blocks:
                    if block.get("type") == "text":
                        full_text = block.get("text", "")
                        if len(full_text) > sent_text_length:
                            delta = full_text[sent_text_length:]
                            sent_text_length = len(full_text)
                            yield {"type": "delta", "text": delta}

            elif event_type == "result":
                usage = data.get("usage", {}) or {}
                usage_event: dict = {
                    "type": "usage",
                    "input_tokens": usage.get("input_tokens", 0),
                    "output_tokens": usage.get("output_tokens", 0),
                }
                if "cache_creation_input_tokens" in usage:
                    usage_event["cache_creation_input_tokens"] = usage["cache_creation_input_tokens"]
                if "cache_read_input_tokens" in usage:
                    usage_event["cache_read_input_tokens"] = usage["cache_read_input_tokens"]
                yield usage_event
                yield {
                    "type": "stop",
                    "stop_reason": data.get("stop_reason", "end_turn"),
                    "stop_sequence": data.get("stop_sequence"),
                }

        await process.wait()

    except (asyncio.CancelledError, GeneratorExit):
        process.kill()
        await process.wait()
        raise
