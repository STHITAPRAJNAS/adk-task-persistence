"""
Basic usage — SqlAlchemyTaskStore with create_a2a_app().

This is the recommended pattern: native ADK A2A stack with a persistent
task store.  Works with RemoteA2aAgent.  No Celery required.

Run:
    pip install adk-task-persistence aiosqlite
    python examples/basic_usage.py
"""

from sqlalchemy.ext.asyncio import create_async_engine

from adk_task_persistence import SqlAlchemyTaskStore, create_a2a_app

# 1. Create an async SQLAlchemy engine
#    For production use Postgres: "postgresql+asyncpg://user:pass@host/db"
engine = create_async_engine("sqlite+aiosqlite:///./tasks.db")

# 2. Create the task store
task_store = SqlAlchemyTaskStore(engine)

# 3. Build the ADK A2A app (replace the stubs below with your real ADK objects)
#
#    from google.adk.agents import LlmAgent
#    from google.adk.runners import Runner
#    from google.adk.sessions import DatabaseSessionService
#    from a2a.types import AgentCard
#
#    runner = Runner(
#        agent=LlmAgent(name="my_agent", model="gemini-2.0-flash"),
#        app_name="my_app",
#        session_service=DatabaseSessionService(DB_URL),
#    )
#    agent_card = AgentCard(...)
#
#    app = create_a2a_app(
#        runner=runner,
#        agent_card=agent_card,
#        task_store=task_store,
#        title="My Agent",
#    )

if __name__ == "__main__":
    print("Configure the runner + agent_card above, then run with:")
    print("    uvicorn examples.basic_usage:app --host 0.0.0.0 --port 8000")
