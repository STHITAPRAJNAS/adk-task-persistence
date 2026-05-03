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

The HTTP/SSE protocol is unchanged. `RemoteA2aAgent` callers see exactly the same A2A streaming responses they always have. The only difference is *where* task state is written.

---

## Quick Start

```python
from sqlalchemy.ext.asyncio import create_async_engine
from adk_task_persistence import SqlAlchemyTaskStore, create_a2a_app

engine = create_async_engine("postgresql+asyncpg://user:pass@db/mydb")
task_store = SqlAlchemyTaskStore(engine)

# Build the ADK A2A stack with persistent task state:
app = create_a2a_app(
    runner=runner,
    agent_card=agent_card,
    task_store=task_store,
)
```

**After ADK PR [#4970](https://github.com/google/adk-python/pull/4970) merges**, pass it directly to `get_fast_api_app`:

```python
from google.adk.cli.fast_api import get_fast_api_app

app = get_fast_api_app(
    agents_dir="./agents",
    a2a=True,
    a2a_task_store=SqlAlchemyTaskStore(engine),    # ← same class, one parameter
)
```

`SqlAlchemyTaskStore` is interface-compatible with the upstream PRs.

---

## Optional: Celery for Agent-Run Survival

If your agents run for minutes and you need execution to survive an HTTP pod crash mid-run, use the optional Celery extension.

```bash
pip install "adk-task-persistence[celery]"
```

```python
from adk_task_persistence.celery import AdkAgentRunner, registry

registry.register(
    "my_agent",
    agent_factory=lambda: AdkAgentRunner(my_runner),
    session_service_factory=lambda: None,
    task_store_factory=lambda: SqlAlchemyTaskStore(engine),
)
```

```bash
celery -A adk_task_persistence.celery worker --loglevel=info
```

---

## License

Apache 2.0
