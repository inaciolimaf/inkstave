"""view_image tool: hands an image from the project to the model."""

from __future__ import annotations

import base64
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from inkstave.modules.agent.file_ops.paths import normalize_path
from inkstave.modules.agent.llm.base import LLMImage
from inkstave.modules.agent.tools._common import load_tree
from inkstave.modules.agent.tools.base import Tool, ToolContext, ToolResult, authorize
from inkstave.modules.projects import BlobMissingError, TreeEntityType, open_file_content

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from uuid import UUID

_UNSUPPORTED = "Only PNG, JPEG, GIF and WebP images can be viewed."


def sniff_image(head: bytes) -> str | None:
    """The media type the bytes prove, since an upload's declared type is the client's word."""
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if head.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if head.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "image/webp"
    return None


async def _read_capped(stream: AsyncIterator[bytes], cap: int) -> bytes | None:
    """The whole stream, or ``None`` as soon as it passes ``cap``."""
    chunks: list[bytes] = []
    size = 0
    async for chunk in stream:
        size += len(chunk)
        if size > cap:
            return None
        chunks.append(chunk)
    return b"".join(chunks)


class ViewImageArgs(BaseModel):
    path: str = Field(min_length=1, description="Path of a PNG, JPEG, GIF or WebP file in the project.")


class ViewImageTool(Tool):
    name = "view_image"
    description = "Look at an image in the project (PNG, JPEG, GIF or WebP)."
    Args = ViewImageArgs

    async def run(self, args: ViewImageArgs, ctx: ToolContext) -> ToolResult:  # type: ignore[override]
        if (denied := await authorize(ctx)) is not None:
            return ToolResult(ok=False, error=denied)
        path = normalize_path(args.path)
        entity_id = await _file_at(ctx, path)
        if entity_id is None:
            return ToolResult.failure("not_found", "No such file in this project.")
        data = await _load_bytes(ctx, entity_id)
        if isinstance(data, ToolResult):
            return data
        media_type = sniff_image(data)
        if media_type is None:
            return ToolResult.failure("unsupported", _UNSUPPORTED)
        image = LLMImage(media_type=media_type, data=base64.b64encode(data).decode("ascii"))
        result = {"path": path, "media_type": media_type, "size_bytes": len(data)}
        return ToolResult(ok=True, data=result, images=[image])


async def _file_at(ctx: ToolContext, path: str) -> UUID | None:
    entities, paths = await load_tree(ctx)
    found = (e for e in entities if paths[e.id] == path and e.type == TreeEntityType.file)
    entity = next(found, None)
    return None if entity is None else entity.id


async def _load_bytes(ctx: ToolContext, entity_id: UUID) -> bytes | ToolResult:
    if ctx.object_store is None:
        return ToolResult.failure("internal", "File storage is not available to this run.")
    try:
        _row, stream = await open_file_content(ctx.db, ctx.object_store, ctx.project_uuid, entity_id)
    except BlobMissingError:
        return ToolResult.failure("not_found", "The file's stored content is missing.")
    data = await _read_capped(stream, ctx.settings.agent_tool_image_max_bytes)
    if data is None:
        return ToolResult.failure("too_large", "The image is too large to view.")
    return data
