"""Tool abstraction, context, result types, registry, and authorization (spec 42).

Tools call only Inkstave's own spec-12/13 services via the injected ``ToolContext``;
they never reach external networks or the LLM. Expected failures are returned as
``ToolResult(ok=False, ...)`` — never raised into the graph.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, ClassVar, Literal
from uuid import UUID

from pydantic import BaseModel

from inkstave.agent.edits import StagedEdit
from inkstave.agent.llm.base import ToolSpec
from inkstave.authorization.capabilities import Capability, capabilities_for
from inkstave.authorization.service import role_for

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from inkstave.agent.settings import AgentSettings

ErrorCode = Literal[
    "not_found", "forbidden", "invalid_args", "too_large", "unsupported", "internal"
]


@dataclass
class ToolContext:
    """Per-turn execution context. ``project_id`` is fixed to the session's project.

    Deliberate deviation from spec 42 §5.2.1 (recorded here, see issue #168):
    §5.2.1 sketches ``ToolContext`` as a Pydantic ``BaseModel``
    (``arbitrary_types_allowed=True``) carrying explicit ``tree_service`` and
    ``doc_service`` fields. Inkstave instead injects a single ``db: AsyncSession``
    and calls the spec-12/13 services as module-level functions against it. This
    is the *chosen design*: the services are stateless over a session, so passing
    the ``AsyncSession`` (plus ``project_id``/``user_id``/``settings``/
    ``staged_edits``) is sufficient DI, avoids constructing/holding per-turn
    service objects, and keeps the context a plain dataclass (no Pydantic
    arbitrary-type plumbing). The §5.2.1 ``BaseModel``-with-service-fields shape
    is intentionally not adopted; callers depend only on the fields below.
    """

    db: AsyncSession
    project_id: str
    user_id: str
    settings: AgentSettings
    staged_edits: list[StagedEdit] = field(default_factory=list)
    # Safety (spec 49): audit events collected during a turn + injection flagging toggle.
    audit_events: list[dict[str, Any]] = field(default_factory=list)
    injection_guard: bool = True

    @property
    def project_uuid(self) -> UUID:
        return UUID(self.project_id)

    @property
    def user_uuid(self) -> UUID:
        return UUID(self.user_id)


class ToolError(BaseModel):
    code: ErrorCode
    message: str


class ToolResult(BaseModel):
    ok: bool
    data: dict[str, Any] | None = None
    error: ToolError | None = None

    @classmethod
    def success(cls, **data: Any) -> ToolResult:
        return cls(ok=True, data=data)

    @classmethod
    def failure(cls, code: ErrorCode, message: str) -> ToolResult:
        return cls(ok=False, error=ToolError(code=code, message=message))


class Tool(ABC):
    name: ClassVar[str]
    description: ClassVar[str]
    Args: ClassVar[type[BaseModel]]

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.name,
            description=self.description,
            parameters=self.Args.model_json_schema(),
        )

    @abstractmethod
    async def run(self, args: BaseModel, ctx: ToolContext) -> ToolResult: ...


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def specs(self) -> list[ToolSpec]:
        return [tool.spec() for tool in self._tools.values()]

    def __len__(self) -> int:
        return len(self._tools)


async def authorize(ctx: ToolContext, *, require_write: bool = False) -> ToolError | None:
    """Re-check the user's access to the session's project. Returns an error or None."""
    role = await role_for(ctx.db, ctx.user_uuid, ctx.project_uuid)
    caps = capabilities_for(role)
    if Capability.PROJECT_READ not in caps:
        return ToolError(code="forbidden", message="You do not have access to this project.")
    if require_write and Capability.DOC_WRITE not in caps:
        return ToolError(code="forbidden", message="This action requires editor access.")
    return None
