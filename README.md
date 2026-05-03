# adk-celery-broker

A production-ready, highly available distributed execution backend for Google Agent ADK.

## Why use adk-celery-broker?

Google Agent ADK provides a robust framework for building agents, but its default `get_fastapi_app` uses an in-memory execution loop. This poses challenges in containerized, distributed environments like Kubernetes:
- **Multi-Pod Polling Issue:** If an A2A request is handled by Pod A, the execution runs in Pod A's memory. If the client polls for status and the load balancer routes the request to Pod B, Pod B will have no knowledge of the task.
- **Container Restarts:** If a container is killed or restarted during an LLM call or long-running execution, the state is lost and the task fails silently.

`adk-celery-broker` solves this by decoupling the HTTP ingress (FastAPI) from the execution loop. It passes the task to a robust Celery worker pool backed by Redis. Status polling bypasses local memory entirely, querying the ADK `SessionService` directly, making your agent architecture truly stateless and fault-tolerant.

## How it works with existing Google ADK applications

This package acts as a seamless, drop-in replacement for the native ADK execution loop. Because it is built directly on top of the native `SessionService` and `BaseAgent` abstractions, **you do not need to rewrite your agent logic**.

Instead of wrapping your agent with `get_fastapi_app`, you wrap factory functions (to allow lazy loading in separate worker processes) using `AgentRegistry.register(...)`, and then serve the decoupled HTTP endpoints using `get_celery_fastapi_app()`. The A2A protocol behavior (`POST /`, `GET /task/{task_id}`) remains identical to the native implementation.

### Compatibility with ADK CLI and `agui`

If you are using the `adk` CLI tool or the `agui` middleware, `get_celery_fastapi_app` is fully compatible. You can pass native arguments like `stateful_task_store` directly to the builder, and it will transparently map them or pass them through to the underlying FastAPI application. Furthermore, because it returns a standard `FastAPI` instance, you can mount `agui` or any other middleware using `app.add_middleware(...)`.

## Installation

```bash
pip install adk-celery-broker
```

## Quickstart

```python
import uvicorn
from my_app.agents import MyCustomAgent
from my_app.db import MyPostgresSessionService

from adk_celery_broker.registry import registry
from adk_celery_broker.executor import get_celery_fastapi_app

# 1. Define factories for your existing ADK primitives
def agent_factory():
    return MyCustomAgent()

def session_service_factory():
    return MyPostgresSessionService()

# 2. Register them under a unique ID so distributed workers know how to build them
AGENT_ID = "my_custom_agent"
registry.register(AGENT_ID, agent_factory, session_service_factory)

# 3. Create the FastAPI app (Drop-in replacement for ADK's native wrapper)
app = get_celery_fastapi_app(agent_id=AGENT_ID)

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000)
```

## Running the Worker

In your production deployment, run the Celery worker alongside your API pods:

```bash
celery -A adk_celery_broker.celery_app worker --loglevel=info
```
