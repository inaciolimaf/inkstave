"""Optional demo seed data (spec 57 §5.5).

Creates one demo user + a sample project with a starter ``main.tex``. Never runs
automatically; refuses in production unless ``force=True``; idempotent (re-running
does not duplicate the demo).
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from inkstave.auth.password import PasswordHasher
from inkstave.config import Settings
from inkstave.db.models.tree_entity import TreeEntityType
from inkstave.db.models.user import User
from inkstave.services.document_service import set_content_from_collab
from inkstave.services.project import create_project
from inkstave.services.tree_service import create_entity
from inkstave.services.user import normalise_email

logger = logging.getLogger("inkstave.bootstrap")

DEMO_EMAIL = "demo@example.com"
DEMO_PASSWORD = "demoPassw0rd"  # noqa: S105 — a documented, non-production demo credential

_STARTER_TEX = r"""\documentclass{article}
\title{Welcome to Inkstave}
\author{Demo User}
\begin{document}
\maketitle
\input{sections/intro}

\section{Next steps}
This is a demo project. Edit, compile, and try the AI agent. The introduction
above lives in its own file under \texttt{sections/} to show a multi-file build.

\bibliographystyle{plain}
\bibliography{references}
\end{document}
"""

_INTRO_TEX = r"""\section{Introduction}
Inkstave is a real-time collaborative \LaTeX{} editor with a built-in AI writing
agent. This section is pulled in from \texttt{sections/intro.tex} via
\verb|\input{sections/intro}| to demonstrate a working multi-file project.
"""

_REFERENCES_BIB = r"""@misc{inkstave,
  title  = {Inkstave},
  author = {Demo User},
  year   = {2026},
  note   = {A collaborative LaTeX editor with an AI writing agent.}
}
"""


async def seed_demo(
    session: AsyncSession, hasher: PasswordHasher, *, settings: Settings, force: bool = False
) -> bool:
    """Seed the demo user + project. Returns True if created, False if it existed.

    Caller owns the transaction.
    """
    if settings.environment == "prod" and not force:
        raise RuntimeError("refusing to seed demo data in production (pass force=True to override)")

    email = normalise_email(DEMO_EMAIL)
    existing = await session.scalar(select(User).where(User.email == email))
    if existing is not None:
        return False  # idempotent

    user = User(email=email, hashed_password=hasher.hash(DEMO_PASSWORD), display_name="Demo User")
    session.add(user)
    await session.flush()

    project = await create_project(session, user.id, "Demo Project")
    await session.flush()

    # A genuinely multi-file project: main.tex \input's sections/intro.tex and
    # cites references.bib, so a fresh instance opens to a working sample build.
    main_doc = await create_entity(session, project.id, TreeEntityType.doc, "main.tex", None)
    await set_content_from_collab(session, main_doc.id, _STARTER_TEX)

    sections = await create_entity(session, project.id, TreeEntityType.folder, "sections", None)
    await session.flush()
    intro_doc = await create_entity(
        session, project.id, TreeEntityType.doc, "intro.tex", sections.id
    )
    await set_content_from_collab(session, intro_doc.id, _INTRO_TEX)

    refs_doc = await create_entity(session, project.id, TreeEntityType.doc, "references.bib", None)
    await set_content_from_collab(session, refs_doc.id, _REFERENCES_BIB)

    await session.flush()
    logger.info("Seeded demo user %s and project %s", user.email, project.id)
    return True
