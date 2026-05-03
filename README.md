# adk-celery-broker

A production-ready distributed execution backend for Google Agent ADK that fills a concrete gap in ADK's A2A support: **injectable task store**.

## The Gap This Fills

Google ADK's `get_fast_api_app` already lets you inject a `session_service` (for ADK per-session state) and a `memory_service` via URI parameters, routing to `DatabaseSessionService` or similar backends.  But when you enable `a2a=True`, ADK **always** creates an `InMemoryTaskStore` internally — there is no parameter to supply your own.

This causes two hard production problems in multi-pod deployments:

| Problem | Root Cause |
|---|---|
| **Cross-pod 404 on status poll** | Task state lives only in the pod that accepted the request. The load balancer routes the next poll to a different pod, which has no record of the task. |
| **Silent state loss on restart** | A container restart wipes the `InMemoryTaskStore`. Any in-flight or queued tasks vanish with no error. |

ADK has already solved the equivalent problem for session and memory services via `DatabaseSessionService`.  `adk-celery-broker` applies the same pattern to **A2A task state**, plus uses Celery to decouple the HTTP ingress from the execution loop.

## How It Works

```
Client
  │
  ▼
FastAPI pod (any pod, no sticky sessions)
  │  POST /tasks → save A2aTask(status=submitted) → dispatch to Celery
  │  GET  /tasks/{id} → task_store.get(id)
  │
  ├── Shared Task Store (Postgres / Redis / …)  ◄──┐
  │                                                 │
  └── Celery Queue (Redis)                          │
          │                                         │
          ▼                                         │
      Celery Worker                                 │
        task_store.save(status=working)   ──────────┤
        runner.run_async(…)                         │
        task_store.save(status=completed) ──────────┘
```

Because every pod and every worker reads and writes the same external store, any pod can serve any status poll without sticky routing, and task state survives container restarts.

## Installation

```bash
pip install adk-celery-broker
```

## Quickstart

### 1. Implement `BaseA2aTaskStore` for your database

```python
# myapp/stores.py
from typing import Dict, List, Optional
from adk_celery_broker import A2aTask, BaseA2aTaskStore

class PostgresTaskStore(BaseA2aTaskStore):
    def __init__(self, pool):
        self._pool = pool  # e.g. asyncpg pool

    async def save(self, task: A2aTask) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO a2a_tasks (id, status, payload, result, error)
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (id) DO UPDATE
                SET status=$2, result=$4, error=$5
                """,
                task.id, task.status,
                json.dumps(task.payload),
                json.dumps(task.result) if task.result else None,
                task.error,
            )

    async def get(self, task_id: str) -> Optional[A2aTask]:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM a2a_tasks WHERE id=$1", task_id
            )
        if row is None:
            return None
        return A2aTask(
            id=row["id"], status=row["status"],
            payload=json.loads(row["payload"]),
            result=json.loads(row["result"]) if row["result"] else None,
            error=row["error"],
        )

    async def list_tasks(self) -> List[A2aTask]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch("SELECT * FROM a2a_tasks")
        return [A2aTask(id=r["id"], status=r["status"], payload=json.loads(r["payload"])) for r in rows]

    async def delete(self, task_id: str) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute("DELETE FROM a2a_tasks WHERE id=$1", task_id)
```

### 2. Register factories and build the app

```python
# main.py
from myapp.agents import MyAgent
from myapp.sessions import DatabaseSessionService
from myapp.stores import PostgresTaskStore
from adk_celery_broker import get_fastapi_app, registry

DB_URL = "postgresql://user:pass@db/mydb"

registry.register(
    "my_agent",
    agent_factory=lambda: MyAgent(),
    session_service_factory=lambda: DatabaseSessionService(DB_URL),
    task_store_factory=lambda: PostgresTaskStore(create_pool(DB_URL)),
)

app = get_fastapi_app(
    agent_id="my_agent",
    task_store=PostgresTaskStore(create_pool(DB_URL)),  # shared across requests in this pod
    title="My Agent API",
)
```

### 3. Run the worker

```bash
celery -A adk_celery_broker.celery_app worker --loglevel=info
```

### 4. Configure via environment variables

```bash
REDIS_BROKER_URL=redis://redis:6379/0
REDIS_BACKEND_URL=redis://redis:6379/0
MAX_RETRIES=3
```

## A2A Endpoints

| Method | Path | Description |
|---|---|---|
| `POST` | `/tasks` | Submit a task; returns `202 {"id": "…", "status": "submitted"}` |
| `GET` | `/tasks/{id}` | Poll task status; returns status + result/error when done |
| `GET` | `/tasks` | List all known tasks |

## Task Lifecycle

```
submitted → working → completed
                    ↘ failed
                    ↘ canceled
```

## `BaseA2aTaskStore` Interface

```python
class BaseA2aTaskStore(ABC):
    async def save(self, task: A2aTask) -> None: ...
    async def get(self, task_id: str) -> Optional[A2aTask]: ...
    async def list_tasks(self) -> List[A2aTask]: ...
    async def delete(self, task_id: str) -> None: ...
```

`A2aTask` fields: `id`, `status`, `payload`, `result`, `error`, `metadata`.

## Relationship to ADK's `session_service` and `memory_service`

| Injectable | ADK parameter | This library | Backed by |
|---|---|---|---|
| Session state (per conversation) | `session_service_uri` → `DatabaseSessionService` | `registry.register(session_service_factory=…)` | Your ADK session DB |
| Memory / knowledge | `memory_service_uri` | `registry.register(…)` | Your ADK memory store |
| **A2A task lifecycle** | ❌ not injectable in ADK | `task_store=` on `get_fastapi_app` | `BaseA2aTaskStore` impl |

## License

Apache 2.0
