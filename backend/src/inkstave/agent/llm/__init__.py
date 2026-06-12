"""LLM client interface + implementations (spec 41)."""

from inkstave.agent.llm.base import (
    LLMClient,
    LLMError,
    LLMMessage,
    LLMResponse,
    LLMStreamChunk,
    LLMUsage,
    ToolCall,
    ToolSpec,
)
from inkstave.agent.llm.fake import FakeLLM

__all__ = [
    "FakeLLM",
    "LLMClient",
    "LLMError",
    "LLMMessage",
    "LLMResponse",
    "LLMStreamChunk",
    "LLMUsage",
    "ToolCall",
    "ToolSpec",
]
