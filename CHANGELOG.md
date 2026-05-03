# Changelog

## [0.2.0] — 2026-05-03

### Changed

- Polished README with badges, architecture diagram, API reference tables, and multi-pod Kubernetes usage guide.
- Switched `pyproject.toml` to PEP 639 SPDX license expression (`Apache-2.0`) — PyPI now shows the SPDX badge.
- Expanded keywords for PyPI discoverability (`persistent`, `multi-pod`, `llm`, `genai`, `postgres`, `postgresql`, etc.).
- Added classifiers: `Framework :: AsyncIO`, `Development Status :: 4 - Beta`, `Topic :: Database`.

## [0.1.0] — 2026-05-03

Library renamed from `adk-celery-broker` to `adk-task-persistence` and refocused on
the primary value: a persistent, pod-restart-safe A2A task store for Google Agent ADK.

### Added

- **`SqlAlchemyTaskStore`** — implements `a2a.server.tasks.TaskStore` ABC, works
  with PostgreSQL/MySQL/SQLite via async SQLAlchemy. Tasks stored as JSON for
  forward compatibility. Auto-creates schema.
- **`create_a2a_app()`** — builds ADK's native A2A stack with an injectable
  task store, today, without waiting for ADK PR #4970 to merge.
- **Optional Celery extension** under `adk_task_persistence.celery` for
  long-running agent runs that need to survive HTTP-pod restart.
- `py.typed` marker (PEP 561) for IDE / type-checker support.
- 18-test suite covering `SqlAlchemyTaskStore` and Celery worker logic.
- GitHub Actions CI (Python 3.10/3.11/3.12) + PyPI publish workflow.

### Changed

- **Package renamed** `adk-celery-broker` → `adk-task-persistence`.
- Primary public API is now `SqlAlchemyTaskStore` and `create_a2a_app()`.
- Custom `BaseA2aTaskStore` ABC and `A2aTask` dataclass removed in favour of
  the real `a2a.server.tasks.TaskStore` ABC and `a2a.types.Task`.
- Celery is now an opt-in extension (`pip install "adk-task-persistence[celery]"`).

### Removed

- `adk_celery_broker` module (superseded by `adk_task_persistence`).
- Custom `BaseA2aTaskStore` / `A2aTask` / `TaskStatus` classes.
- Custom A2A HTTP endpoints (replaced by ADK-native `A2AStarletteApplication`).
