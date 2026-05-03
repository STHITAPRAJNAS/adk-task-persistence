"""
Full Google ADK integration — adk-celery-broker with AdkAgentRunner.

Shows how to wire a real ADK LlmAgent + DatabaseSessionService + a custom
database-backed task store into the distributed Celery execution model.

Prerequisites:
    pip install google-adk asyncpg sqlalchemy[asyncio]

Environment variables:
    GOOGLE_API_KEY      — Gemini API key
    DB_URL              — async SQLAlchemy URL, e.g. postgresql+asyncpg://user:pass@host/db
    REDIS_BROKER_URL    — Redis URL for Celery (default: redis://localhost:6379/0)

Run the API:
    uvicorn examples.with_adk_runner:app --reload

Run a Celery worker:
    celery -A adk_celery_broker.celery_app worker --loglevel=info

Submit a task:
    curl -X POST http://localhost:8000/tasks \\
         -H "Content-Type: application/json" \\
         -d '{
               "id": "task-1",
               "params": {
                 "sessionId": "session-abc",
                 "userId": "user-123",
                 "message": {"role": "user", "parts": [{"text": "What is 2+2?"}]}
               }
             }'

Poll for result:
    curl http://localhost:8000/tasks/task-1
"""

import os
from typing import Any, Dict, List, Optional

import uvicorn

from adk_celery_broker import (
    A2aTask,
    AdkAgentRunner,
    BaseA2aTaskStore,
    TaskStatus,
    get_fastapi_app,
    registry,
)

DB_URL = os.environ.get("DB_URL", "postgresql+asyncpg://user:pass@localhost/mydb")
AGENT_ID = "my_adk_agent"

# ---------------------------------------------------------------------------
# Custom task store backed by SQLAlchemy (production pattern)
# Replace the stub below with your real async DB client.
# ---------------------------------------------------------------------------

class PostgresTaskStore(BaseA2aTaskStore):
    """
    Example SQLAlchemy-based task store.

    In a real implementation, create an async engine/pool in __init__ and use
    it in each method.  The SQL schema you need::

        CREATE TABLE a2a_tasks (
            id      TEXT PRIMARY KEY,
            status  TEXT NOT NULL,
            payload JSONB,
            result  JSONB,
            error   TEXT
        );
    """

    def __init__(self, db_url: str) -> None:
        self._db_url = db_url
        # self._engine = create_async_engine(db_url)

    async def save(self, task: A2aTask) -> None:
        # async with self._engine.begin() as conn:
        #     await conn.execute(
        #         text("""
        #             INSERT INTO a2a_tasks (id, status, payload, result, error)
        #             VALUES (:id, :status, :payload::jsonb, :result::jsonb, :error)
        #             ON CONFLICT (id) DO UPDATE
        #             SET status=:status, result=:result::jsonb, error=:error
        #         """),
        #         {"id": task.id, "status": task.status, ...}
        #     )
        raise NotImplementedError("Wire up your async DB client here")

    async def get(self, task_id: str) -> Optional[A2aTask]:
        raise NotImplementedError

    async def list_tasks(self) -> List[A2aTask]:
        raise NotImplementedError

    async def delete(self, task_id: str) -> None:
        raise NotImplementedError


# ---------------------------------------------------------------------------
# agent_factory: builds an AdkAgentRunner from a real ADK Runner.
# The runner embeds the session service — workers call agent_factory() to
# reconstruct the full runner in their own process.
# ---------------------------------------------------------------------------

def agent_factory() -> AdkAgentRunner:
    from google.adk.agents import LlmAgent                    # type: ignore[import]
    from google.adk.runners import Runner                     # type: ignore[import]
    from google.adk.sessions import DatabaseSessionService    # type: ignore[import]

    agent = LlmAgent(
        name="my_agent",
        model="gemini-2.0-flash",
        instruction="You are a helpful assistant.",
    )
    session_service = DatabaseSessionService(db_url=DB_URL)
    runner = Runner(
        agent=agent,
        app_name=AGENT_ID,
        session_service=session_service,
    )
    return AdkAgentRunner(runner)


# ---------------------------------------------------------------------------
# Register everything
# ---------------------------------------------------------------------------

registry.register(
    AGENT_ID,
    agent_factory=agent_factory,
    session_service_factory=lambda: None,           # session service is inside the runner
    task_store_factory=lambda: PostgresTaskStore(DB_URL),
)

# ---------------------------------------------------------------------------
# Build the FastAPI app
# ---------------------------------------------------------------------------

app = get_fastapi_app(
    agent_id=AGENT_ID,
    task_store=PostgresTaskStore(DB_URL),  # shared instance for this HTTP pod
    title="ADK Agent API",
    version="1.0.0",
)

if __name__ == "__main__":
    uvicorn.run("examples.with_adk_runner:app", host="0.0.0.0", port=8000, reload=True)
