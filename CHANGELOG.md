# Changelog

All notable changes to this project are documented here.
Versioning follows [Semantic Versioning](https://semver.org/).

---

## [0.1.0] — 2026-05-03

Library renamed from `adk-celery-broker` to `adk-persistence` and refocused on
the primary value: a persistent, pod-restart-safe A2A task store for Google
Agent ADK.

### Added

- **`SqlAlchemyTaskStore`** — implements `a2a.server.tasks.TaskStore` ABC and
  works with PostgreSQL, MySQL, and SQLite via async SQLAlchemy.  Tasks are
  stored as JSON for forward compatibility with future `a2a.types.Task`
  schema changes.  Auto-creates the schema on first use.
- **`create_a2a_app()`** helper — builds ADK's native A2A stack
  (`A2aAgentExecutor` → `DefaultRequestHandler` → `A2AStarletteApplication`)
  with an injectable task store, today, without waiting for ADK PR #4970 to
  merge.
- **Optional Celery extension** under `adk_persistence.celery` for
  long-running agent runs that need to survive HTTP-pod restart.  Includes
  `AgentRunner` ABC, `AdkAgentRunner` wrapper, registry, and Celery worker.
- `py.typed` marker (PEP 561) for IDE / type-checker support.
- 18-test suite covering `SqlAlchemyTaskStore` (in-memory SQLite) and the
  Celery worker logic.

### Changed

- **Package renamed** `adk-celery-broker` → `adk-persistence`.
- **Module renamed** `adk_celery_broker` → `adk_persistence`.
- Primary public API is now `SqlAlchemyTaskStore` and `create_a2a_app()`.
  The previous custom A2A endpoints (`POST /tasks` / `GET /tasks/{id}`) are
  gone — we use ADK's native A2A stack so `RemoteA2aAgent` callers and SSE
  streaming work unchanged.
- Custom `BaseA2aTaskStore` ABC and `A2aTask` dataclass removed in favour of
  the real `a2a.server.tasks.TaskStore` ABC and `a2a.types.Task` Pydantic
  model.  This means a `SqlAlchemyTaskStore` instance plugs directly into
  ADK once `get_fast_api_app(a2a_task_store=...)` lands upstream.
- Celery is now an opt-in extension (`pip install "adk-persistence[celery]"`)
  rather than a core dependency.

### Removed

- `adk_celery_broker` module (superseded by `adk_persistence`).
- Custom `BaseA2aTaskStore` / `A2aTask` / `TaskStatus` classes.
- Custom A2A HTTP endpoints (replaced by ADK-native `A2AStarletteApplication`).

---

## [0.2.0-pre] — `adk-celery-broker`

Internal preview release on `feature/injectable-task-store` branch.  Never
published to PyPI.  Used a custom A2A protocol implementation; superseded by
`adk-persistence` 0.1.0.
