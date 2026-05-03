# adk-task-persistence

[![PyPI](https://img.shields.io/pypi/v/adk-task-persistence)](https://pypi.org/project/adk-task-persistence/)
[![Python](https://img.shields.io/pypi/pyversions/adk-task-persistence)](https://pypi.org/project/adk-task-persistence/)
[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![CI](https://github.com/sthitaprajnas/adk-task-persistence/actions/workflows/ci.yml/badge.svg)](https://github.com/sthitaprajnas/adk-task-persistence/actions/workflows/ci.yml)

**Persistent, pod-restart-safe A2A task store for Google Agent ADK.**

Drop-in replacement for ADK's `InMemoryTaskStore`. Implements the real `a2a.server.tasks.TaskStore` ABC — backed by Postgres, MySQL, or SQLite. Works with `RemoteA2aAgent`, SSE streaming, and multi-pod Kubernetes deployments **today**.

```bash
pip install adk-task-persistence
```

---

## The Problem

Google ADK's `get_fast_api_app(a2a=True)` hardcodes `InMemoryTaskStore()` with no injection point. In any real deployment this causes:

| Symptom | Root cause |
|---|---|
| In-flight tasks vanish on pod restart | State lives in process memory |
| Status polls return 404 across pods | Each pod has its own store |
| Can't scale horizontally without sticky sessions | Defeats stateless pod design |

ADK already solved the same problem for **session state** via `DatabaseSessionService`. This library applies the same pattern to **A2A task state**.

---

## Features

- **Native ADK interface** — implements `a2a.server.tasks.TaskStore` ABC exactly; zero glue code
- **Any SQL database** — Postgres, MySQL, SQLite via async SQLAlchemy
- **Auto schema** — table created on first use; no migrations needed
- **Multi-pod safe** — shared task state across all replicas
- **Pod-restart safe** — tasks survive container restarts and rolling deploys
- **SSE / streaming preserved** — `RemoteA2aAgent` callers see identical A2A protocol responses
- **Forward-compatible** — ready for ADK PRs [#3839](https://github.com/google/adk-python/pull/3839) and [#4970](https://github.com/google/adk-python/pull/4970) with zero code changes
- **Optional Celery layer** — for agent runs that must survive an HTTP pod crash mid-execution
- **Typed** — `py.typed` marker, full type annotations

---

## Quick Start

```python
from sqlalchemy.ext.asyncio import create_async_engine
from adk_task_persistence import SqlAlchemyTaskStore, create_a2a_app

engine = create_async_engine("postgresql+asyncpg://user:pass@db/mydb")
task_store = SqlAlchemyTaskStore(engine)

app = create_a2a_app(
    runner=runner,           # google.adk.runners.Runner
    agent_card=agent_card,   # a2a.types.AgentCard
    task_store=task_store,
)
```

Run with:

```bash
uvicorn mymodule:app --host 0.0.0.0 --port 8000
```

---

## Installation

### Core (task persistence only)

```bash
pip install adk-task-persistence
```

Requires an async driver for your database:

```bash
# Postgres
pip install asyncpg

# SQLite (dev / testing)
pip install aiosqlite
```

### With Celery (agent-run survival)

```bash
pip install "adk-task-persistence[celery]"
```

---

## Usage

### 1. Basic — SQLite for local development

```python
from sqlalchemy.ext.asyncio import create_async_engine
from adk_task_persistence import SqlAlchemyTaskStore, create_a2a_app

engine = create_async_engine("sqlite+aiosqlite:///./tasks.db")
task_store = SqlAlchemyTaskStore(engine)

app = create_a2a_app(
    runner=runner,
    agent_card=agent_card,
    task_store=task_store,
    title="My Agent",
)
```

### 2. Production — Postgres on Kubernetes

```python
import os
from sqlalchemy.ext.asyncio import create_async_engine
from google.adk.agents import LlmAgent
from google.adk.runners import Runner
from google.adk.sessions import DatabaseSessionService
from a2a.types import AgentCard
from adk_task_persistence import SqlAlchemyTaskStore, create_a2a_app

DB_URL = os.environ["DB_URL"]  # postgresql+asyncpg://user:pass@host/db

agent = LlmAgent(name="my_agent", model="gemini-2.0-flash")
runner = Runner(
    agent=agent,
    app_name="my_app",
    session_service=DatabaseSessionService(db_url=DB_URL),
)
agent_card = AgentCard(name="My Agent", url="http://localhost:8000", version="1.0.0")

engine = create_async_engine(DB_URL)
task_store = SqlAlchemyTaskStore(engine)

app = create_a2a_app(runner=runner, agent_card=agent_card, task_store=task_store)
```

### 3. After ADK PR #4970 merges

Once upstream support lands, pass the store directly to `get_fast_api_app` — no helper needed:

```python
from google.adk.cli.fast_api import get_fast_api_app
from adk_task_persistence import SqlAlchemyTaskStore

app = get_fast_api_app(
    agents_dir="./agents",
    a2a=True,
    a2a_task_store=SqlAlchemyTaskStore(engine),
)
```

`SqlAlchemyTaskStore` is already interface-compatible — no changes required.

---

## Optional: Celery for Agent-Run Survival

The core library solves **task state persistence** (state survives pod restart; polls succeed cross-pod). If your agents run for minutes and you also need **execution** to survive an HTTP pod crash mid-run, add the Celery extension.

```python
from adk_task_persistence.celery import AdkAgentRunner, registry

registry.register(
    "my_agent",
    agent_factory=lambda: AdkAgentRunner(my_runner),
    session_service_factory=lambda: None,
    task_store_factory=lambda: SqlAlchemyTaskStore(engine),
)
```

Start a worker:

```bash
celery -A adk_task_persistence.celery worker --loglevel=info
```

The agent run executes inside the Celery worker. If the HTTP pod dies, the worker completes the task and writes the result to the shared store. Callers polling any pod will find the result.

---

## Multi-Pod Architecture

```
                    ┌─────────────────────────────┐
                    │       Load Balancer          │
                    └──────────┬──────────┬────────┘
                               │          │
                        ┌──────┘          └──────┐
                        ▼                        ▼
                 ┌─────────────┐          ┌─────────────┐
                 │  Agent Pod 1 │          │  Agent Pod 2 │
                 │             │          │             │
                 │  FastAPI +  │          │  FastAPI +  │
                 │  ADK Runner │          │  ADK Runner │
                 └──────┬──────┘          └──────┬──────┘
                        │                        │
                        └──────────┬─────────────┘
                                   ▼
                          ┌─────────────────┐
                          │   Postgres DB    │
                          │                 │
                          │  adk_a2a_tasks  │  ← SqlAlchemyTaskStore
                          │  adk_sessions   │  ← DatabaseSessionService
                          └─────────────────┘
```

Both pods share the same task and session state. Polls routed to any pod return the correct result.

---

## API Reference

### `SqlAlchemyTaskStore`

```python
SqlAlchemyTaskStore(
    engine: AsyncEngine,
    table_name: str = "adk_a2a_tasks",
    create_table: bool = True,
)
```

Implements `a2a.server.tasks.TaskStore`:

| Method | Signature |
|---|---|
| `save` | `async def save(task, context) -> None` |
| `get` | `async def get(task_id, context) -> Task \| None` |
| `list` | `async def list(params, context) -> ListTasksResponse` |
| `delete` | `async def delete(task_id, context) -> None` |

### `create_a2a_app`

```python
create_a2a_app(
    *,
    runner: Runner,
    agent_card: AgentCard,
    task_store: TaskStore,
    push_config_store=None,
    url_prefix: str = "",
    **fastapi_kwargs,
) -> FastAPI
```

Builds ADK's native A2A stack (`A2aAgentExecutor → DefaultRequestHandler → A2AStarletteApplication`) with your task store injected.

---

## Requirements

- Python 3.10+
- `google-adk >= 1.0.0`
- `sqlalchemy[asyncio] >= 2.0`
- `fastapi >= 0.110.1`
- `pydantic >= 2.6.4`
- Async DB driver: `asyncpg` (Postgres), `aiomysql` (MySQL), `aiosqlite` (SQLite)

---

## License

[Apache 2.0](LICENSE) — © Sthitaprajna Sahoo
