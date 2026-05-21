from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, ConfigDict, Field


def _new_message_id() -> str:
    return f"msg_{uuid.uuid4().hex[:24]}"


class Message(BaseModel):
    role: str
    content: Union[str, List[Dict[str, Any]]]


class SystemBlock(BaseModel):
    type: str = "text"
    text: str

    model_config = ConfigDict(extra="allow")


class MessagesRequest(BaseModel):
    model: str
    messages: List[Message]
    max_tokens: int = 1024
    system: Optional[Union[str, List[Dict[str, Any]]]] = None
    metadata: Optional[Dict[str, Any]] = None
    stop_sequences: Optional[List[str]] = None
    stream: bool = False
    temperature: Optional[float] = None
    top_p: Optional[float] = None
    top_k: Optional[int] = None
    tools: Optional[List[Dict[str, Any]]] = None
    tool_choice: Optional[Dict[str, Any]] = None

    model_config = ConfigDict(extra="allow")


class Usage(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_input_tokens: Optional[int] = None
    cache_read_input_tokens: Optional[int] = None

    model_config = ConfigDict(extra="allow")


class TextBlock(BaseModel):
    type: str = "text"
    text: str


class MessagesResponse(BaseModel):
    id: str = Field(default_factory=_new_message_id)
    type: str = "message"
    role: str = "assistant"
    content: List[Dict[str, Any]]
    model: str
    stop_reason: Optional[str] = "end_turn"
    stop_sequence: Optional[str] = None
    usage: Usage


class ModelInfo(BaseModel):
    type: str = "model"
    id: str
    display_name: str
    created_at: str
