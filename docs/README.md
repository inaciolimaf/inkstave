# Inkstave Documentation

Start here. Inkstave is a from-scratch, real-time collaborative LaTeX editor with
a built-in AI writing agent (inspired by Overleaf Community Edition, sharing no
code with it).

## Guides

- **[User Guide](user-guide.md)** — sign up, edit, compile, SyncTeX, history,
  collaboration & sharing, and the AI agent.
- **[Admin / Operations Guide](admin-guide.md)** — deploy, the full environment
  variable reference, first-run bootstrap, scaling, backups, LaTeX packages,
  observability, upgrades, and troubleshooting.
- **[Architecture](architecture.md)** — services, data-flow diagrams (request,
  compile, collaboration, agent), the data model, and ADR links.
- **[API Reference](api-reference.md)** — how to view the live OpenAPI docs and
  the generated [`api/openapi.json`](api/openapi.json).

## Repository docs

- **[../README.md](../README.md)** — project overview & quickstart.
- **[../CONTRIBUTING.md](../CONTRIBUTING.md)** — contributing, the test budget,
  and the no-Overleaf-code originality rule.
- **[Architecture Decision Records](adr/)** — per-spec design decisions.
- **[Refactor logs](refactors/)** — what each refactor pass changed.
- **[E2E strategy](e2e-strategy.md)** — the Playwright smoke suite & stubs.
- **[Security checklist](security-checklist.md)** — the spec-52/55 review gate.

## Release

- **[Release checklist](release-checklist.md)** — build → migrate → bootstrap →
  smoke → tag.
- **[Originality audit](originality-audit.md)** — reproducible proof of
  independence from Overleaf.
- **[Changelog](CHANGELOG.md)** — the final release-readiness pass.

## Assets

Diagram sources and screenshot placeholders live under [`assets/`](assets/).
