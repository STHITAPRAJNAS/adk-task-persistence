"""
Optional Celery integration — for agent runs that must survive HTTP pod restart.

Use this pattern only when:
* Your agent runs are long (minutes)
* You need execution to resume / retry if the worker pod dies mid-run
* You need horizontal scaling of agent execution independent of HTTP pods

For the simpler "task state survives pod restart" use case, just use
SqlAlchemyTaskStore + create_a2a_app() — no Celery needed.

Install:
    pip install "adk-task-persistence[celery]"

Run the API:
    uvicorn examples.with_celery:app --host 0.0.0.0 --port 8000

Run a worker (separate process, Redis must be running):
    celery -A adk_task_persistence.celery worker --loglevel=info
"""

import os

from sqlalchemy.ext.asyncio import create_async_engine

from adk_task_persistence import SqlAlchemyTaskStore
from adk_task_persistence.celery import AdkAgentRunner, registry

DB_URL = os.environ.get("DB_URL", "postgresql+asyncpg://user:pass@localhost/mydb")
APP_NAME = "my_adk_agent"


def agent_factory() -> AdkAgentRunner:
    """Reconstructed by the worker on each task — must be self-contained."""
    from google.adk.agents import LlmAgent
    from google.adk.runners import Runner
    from google.adk.sessions import DatabaseSessionService

    return AdkAgentRunner(
        Runner(
            agent=LlmAgent(name="my_agent", model="gemini-2.0-flash"),
            app_name=APP_NAME,
            session_service=DatabaseSessionService(db_url=DB_URL),
        )
    )


def task_store_factory() -> SqlAlchemyTaskStore:
    return SqlAlchemyTaskStore(create_async_engine(DB_URL))


registry.register(
    APP_NAME,
    agent_factory=agent_factory,
    session_service_factory=lambda: None,
    task_store_factory=task_store_factory,
)

from adk_task_persistence import create_a2a_app  # noqa: E402

# (Build runner + agent_card as in with_adk_runner.py, then:)
# app = create_a2a_app(runner=runner, agent_card=agent_card, task_store=task_store_factory(), ...)
