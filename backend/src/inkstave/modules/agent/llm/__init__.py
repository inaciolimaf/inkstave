"""LLM client interface + implementations (spec 41)."""

from inkstave.modules.agent.llm.base import (
    LLMClient,
    LLMError,
    LLMMessage,
    LLMResponse,
    LLMStreamChunk,
    LLMUsage,
    ToolCall,
    ToolSpec,
)
from inkstave.modules.agent.llm.fake import FakeLLM

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
