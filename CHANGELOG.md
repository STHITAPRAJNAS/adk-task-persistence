# Changelog

All notable changes to this project are documented here.
Versioning follows [Semantic Versioning](https://semver.org/).

---

## [0.2.0] — 2026-05-03

### Added

- **`AgentRunner` ABC** (`adk_celery_broker.runner`) — canonical contract for
  agent execution inside Celery workers.  Implement `async def run(payload)`
  to wrap any agent runtime.
- **`AdkAgentRunner`** — wraps a Google ADK `Runner`, parses A2A
  `params.message` into an ADK `Content` object, and streams events from
  `runner.run_async()`.
- **`BaseA2aTaskStore` ABC** (`adk_celery_broker.task_store`) — injectable
  interface for A2A task lifecycle storage (`save`, `get`, `list_tasks`,
  `delete`).  Mirrors the `BaseSessionService` / `DatabaseSessionService`
  injection pattern that ADK already uses for session state, filling the
  equivalent gap for A2A task tracking.
- **`InMemoryA2aTaskStore`** — default implementation for local development.
  Emits a `UserWarning` when used without explicit configuration.
- **`A2aTask` dataclass** and **`TaskStatus` constants** for typed task
  lifecycle representation.
- **`task_store_factory`** parameter to `AgentRegistry.register()`.
- **`task_store=`** parameter to `get_fastapi_app()`.
- **`GET /tasks`** endpoint — list all known tasks from the shared store.
- **`py.typed` marker** (PEP 561) for IDE / type-checker support.
- **39-test unit suite** covering task store, registry, router, executor, and
  worker logic without requiring a running Redis or Celery broker.
- **GitHub Actions CI** (`ci.yml`) — runs tests on Python 3.10/3.11/3.12 on
  every push and pull request.
- **GitHub Actions publish** (`publish.yml`) — builds and publishes to PyPI on
  version tag push using PyPI trusted publishing (no API token required).
- **`examples/basic_usage.py`** — minimal custom `AgentRunner` pattern.
- **`examples/with_adk_runner.py`** — full ADK `LlmAgent` + `DatabaseSessionService`
  + custom `PostgresTaskStore` wiring.

### Changed

- `get_fastapi_app()` no longer accepts `stateful_task_store` (was a
  fabricated ADK-compatibility shim that conflated session service with task
  store — two unrelated concerns).
- `AgentRegistry._registry` is now an instance variable (was a class-level
  mutable dict that caused state bleed across test cases).
- `AgentRegistry.register()` now accepts an optional `task_store_factory`.
- Workers resolve the session service from inside the `AgentRunner` (embedded
  at construction) rather than as a separate registry lookup.
- `warnings.warn` in `_resolve_task_store` uses `stacklevel=2` (was `3`)
  so the warning points at the actual `get_fastapi_app()` call site.
- Removed unused `agent_factory_path` / `session_service_factory_path`
  settings from `CeleryConfig` — these were config keys with no code reading
  them.

### Fixed

- `_registry` class-level mutable default no longer bleeds state between
  independent `AgentRegistry` instances created in tests.

---

## [0.1.0] — 2025-01-01

Initial release — Celery-backed A2A task submission and polling with
`AgentRegistry` and `get_celery_fastapi_app`.
