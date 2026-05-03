# adk-task-persistence

**Persistent, pod-restart-safe A2A task store for Google Agent ADK.**

Drop-in replacement for ADK's `InMemoryTaskStore`. Native fit with ADK's A2A stack — fully compatible with `RemoteA2aAgent` and SSE streaming. Works in multi-pod EKS / Kubernetes deployments today.

```bash
pip install adk-task-persistence
```

---

## The Problem

Google ADK's `get_fast_api_app(a2a=True)` always creates an in-process `InMemoryTaskStore`. There is no parameter to inject a persistent one. In any non-trivial deployment this causes:

1. **Pod-restart data loss** — every in-flight task vanishes silently when a container restarts
2. **Cross-pod 404s** — status polls routed to a different pod return "not found"
3. **No horizontal scaling without sticky sessions** — defeats the purpose of stateless web pods

ADK has already solved the equivalent problem for session state via `DatabaseSessionService`.  This library applies the same pattern to A2A task state.

---

## The Solution

`SqlAlchemyTaskStore` implements ADK's real `a2a.server.tasks.TaskStore` ABC. Tasks are written to your database (Postgres / MySQL / SQLite) instead of in-process memory.

```
                  ┌──────────────────────────────┐
                  │  POSTGRES (SqlAlchemyTaskStore)│
                  │  id │ data (JSON Task)        │
                  └────────────────┬─────────────┘
                                   │ shared by all pods
        ┌──────────────────────────┼───────────────────────────┐
        ▼                          ▼                           ▼
   AgentApp Pod A           AgentApp Pod B           AgentApp Pod C
   (handles request,        (serves status poll      (also serves polls)
    streams via SSE)         even though Pod A
                             accepted the request)
```

The HTTP/SSE protocol is unchanged.  `RemoteA2aAgent` callers see exactly the same A2A streaming responses they always have.  The only difference is *where* task state is written.

---

## Quick Start

### 1. Pick a database

```python
from sqlalchemy.ext.asyncio import create_async_engine
from adk_task_persistence import SqlAlchemyTaskStore

engine = create_async_engine("postgresql+asyncpg://user:pass@db/mydb")
task_store = SqlAlchemyTaskStore(engine)
```

The schema is auto-created on first use:

```sql
CREATE TABLE adk_a2a_tasks (
    id         VARCHAR(255) PRIMARY KEY,
    data       TEXT NOT NULL,                  -- JSON-serialised a2a.types.Task
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now()
);
```

### 2. Wire it into your ADK app

**Today** — use `create_a2a_app()` to build the native ADK A2A stack with your store:

```python
from google.adk.agents import LlmAgent
from google.adk.runners import Runner
from google.adk.sessions import DatabaseSessionService
from a2a.types import AgentCard
from adk_task_persistence import SqlAlchemyTaskStore, create_a2a_app

runner = Runner(
    agent=LlmAgent(name="my_agent", model="gemini-2.0-flash"),
    app_name="my_app",
    session_service=DatabaseSessionService(DB_URL),
)

app = create_a2a_app(
    runner=runner,
    agent_card=AgentCard(name="My Agent", url="http://localhost:8000", ...),
    task_store=SqlAlchemyTaskStore(engine),
)
```

**After ADK PR [#4970](https://github.com/google/adk-python/pull/4970) merges** — pass it directly:

```python
from google.adk.cli.fast_api import get_fast_api_app

app = get_fast_api_app(
    agents_dir="./agents",
    a2a=True,
    a2a_task_store=SqlAlchemyTaskStore(engine),    # ← same class, one parameter
)
```

`SqlAlchemyTaskStore` is interface-compatible with the upstream PRs — when they merge, you keep the same store class, you just pass it directly to ADK.

---

## What this library is NOT

| Concern | Solution |
|---|---|
| Task state survives pod restart | `SqlAlchemyTaskStore` ✅ |
| Status polls work from any pod | `SqlAlchemyTaskStore` ✅ |
| Task state shared across pods | `SqlAlchemyTaskStore` ✅ |
| `RemoteA2aAgent` keeps working | Native ADK A2A stack — yes ✅ |
| Long-running agent runs (minutes) survive HTTP pod restart | Optional Celery extension (see below) |
| Replace ADK's session service | Use ADK's `DatabaseSessionService` directly |

---

## Optional: Celery for Agent-Run Survival

If your agents run for minutes and you need execution to survive an HTTP pod crash mid-run, use the optional Celery extension.

```bash
pip install "adk-task-persistence[celery]"
```

```python
from adk_task_persistence.celery import AdkAgentRunner, registry

def agent_factory():
    return AdkAgentRunner(my_runner)

registry.register(
    "my_agent",
    agent_factory=agent_factory,
    session_service_factory=lambda: None,
    task_store_factory=lambda: SqlAlchemyTaskStore(engine),
)
```

```bash
celery -A adk_task_persistence.celery worker --loglevel=info
```

This is a separate concern from the task store — most users only need `SqlAlchemyTaskStore`.

---

## API Reference

### `SqlAlchemyTaskStore(engine, table_name="adk_a2a_tasks", create_table=True)`

Implements `a2a.server.tasks.TaskStore`:

| Method | Behaviour |
|---|---|
| `save(task, context)` | Upsert task row, JSON-serialised |
| `get(task_id, context)` | Return `Task` or `None` |
| `list(params, context)` | Return `ListTasksResponse`; honours `params.task_ids` filter |
| `delete(task_id, context)` | Remove row; no-op if absent |

### `create_a2a_app(*, runner, agent_card, task_store, **fastapi_kwargs)`

Builds a `FastAPI` app with ADK's full A2A stack (`A2aAgentExecutor` → `DefaultRequestHandler` → `A2AStarletteApplication`) using your task store. Equivalent to `get_fast_api_app(a2a_task_store=...)` but works today.

---

## Compatibility

| Component | Version |
|---|---|
| Python | 3.10+ |
| google-adk | 1.0+ |
| SQLAlchemy | 2.0+ (async) |
| Tested DBs | PostgreSQL, SQLite |

---

## License

Apache 2.0
