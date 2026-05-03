"""
Basic usage — adk-celery-broker with a custom AgentRunner.

This is the minimal pattern for getting a distributed A2A API running.
Replace EchoRunner with your real agent logic.

Run the API:
    uvicorn examples.basic_usage:app --reload

Run a Celery worker (separate terminal, Redis must be running):
    celery -A adk_celery_broker.celery_app worker --loglevel=info

Submit a task:
    curl -X POST http://localhost:8000/tasks \\
         -H "Content-Type: application/json" \\
         -d '{"id": "task-1", "params": {"message": {"parts": [{"text": "Hello"}]}}}'

Poll for result:
    curl http://localhost:8000/tasks/task-1
"""

from typing import Any, Dict

import uvicorn

from adk_celery_broker import AgentRunner, InMemoryA2aTaskStore, get_fastapi_app, registry

# ---------------------------------------------------------------------------
# 1. Implement AgentRunner with your business logic
# ---------------------------------------------------------------------------

class EchoRunner(AgentRunner):
    """Trivial runner that echoes the payload back as the result."""

    async def run(self, payload: Dict[str, Any]) -> Any:
        params = payload.get("params", {})
        message = params.get("message", {})
        parts = message.get("parts", [])
        text = " ".join(p.get("text", "") for p in parts if "text" in p)
        return {"echo": text or str(payload)}


# ---------------------------------------------------------------------------
# 2. Register factories — the worker reconstructs these in a separate process
# ---------------------------------------------------------------------------

AGENT_ID = "echo_agent"

registry.register(
    AGENT_ID,
    agent_factory=EchoRunner,             # zero-arg callable → AgentRunner
    session_service_factory=lambda: None, # no ADK session service needed here
    # task_store_factory omitted → InMemoryA2aTaskStore (fine for single process)
)

# ---------------------------------------------------------------------------
# 3. Build the FastAPI app
#    Pass a shared task_store so all pods can read task status.
#    For production, replace InMemoryA2aTaskStore with a DB-backed subclass.
# ---------------------------------------------------------------------------

app = get_fastapi_app(
    agent_id=AGENT_ID,
    task_store=InMemoryA2aTaskStore(),  # replace with PostgresTaskStore() in prod
    title="Echo Agent API",
    version="1.0.0",
)

# ---------------------------------------------------------------------------
# 4. Add any middleware you need (CORS, auth, etc.)
# ---------------------------------------------------------------------------

# from fastapi.middleware.cors import CORSMiddleware
# app.add_middleware(CORSMiddleware, allow_origins=["*"], ...)

if __name__ == "__main__":
    uvicorn.run("examples.basic_usage:app", host="0.0.0.0", port=8000, reload=True)
