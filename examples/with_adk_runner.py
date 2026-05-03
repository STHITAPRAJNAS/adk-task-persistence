"""
Full ADK + Postgres + multi-pod EKS deployment example.

Replaces ADK's InMemoryTaskStore with a Postgres-backed SqlAlchemyTaskStore.
Uses ADK's native A2A stack (SSE streaming, RemoteA2aAgent compatibility).
Makes task state survive pod restarts and shareable across pods.
No Celery — agent runs synchronously inside the HTTP request.

Environment variables:
    GOOGLE_API_KEY    — Gemini API key
    DB_URL            — async SQLAlchemy URL, e.g.
                        postgresql+asyncpg://user:pass@db/mydb

Run:
    uvicorn examples.with_adk_runner:app --host 0.0.0.0 --port 8000
"""

import os

from sqlalchemy.ext.asyncio import create_async_engine

from adk_task_persistence import SqlAlchemyTaskStore, create_a2a_app

DB_URL = os.environ.get("DB_URL", "postgresql+asyncpg://user:pass@localhost/mydb")
APP_NAME = "my_adk_agent"

from google.adk.agents import LlmAgent                    # type: ignore[import]
from google.adk.runners import Runner                     # type: ignore[import]
from google.adk.sessions import DatabaseSessionService    # type: ignore[import]
from a2a.types import AgentCard                           # type: ignore[import]

agent = LlmAgent(
    name="my_agent",
    model="gemini-2.0-flash",
    instruction="You are a helpful assistant.",
)

runner = Runner(
    agent=agent,
    app_name=APP_NAME,
    session_service=DatabaseSessionService(db_url=DB_URL),
)

agent_card = AgentCard(
    name="My Agent",
    description="A helpful assistant agent",
    url="http://localhost:8000",
    version="1.0.0",
)

engine = create_async_engine(DB_URL)
task_store = SqlAlchemyTaskStore(engine)

app = create_a2a_app(
    runner=runner,
    agent_card=agent_card,
    task_store=task_store,
    title="My ADK Agent API",
    version="1.0.0",
)

# After ADK PR #4970 merges, you can simplify to:
#
# from google.adk.cli.fast_api import get_fast_api_app
# app = get_fast_api_app(agents_dir="./agents", a2a=True, a2a_task_store=task_store)
