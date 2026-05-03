# Copyright 2024
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0

"""
adk-persistence — production-ready storage layer for Google Agent ADK.

Primary use: replace ADK's ``InMemoryTaskStore`` with a database-backed
implementation so A2A task state survives pod restarts and is visible
across all pods in a Kubernetes cluster.

Quick start::

    from sqlalchemy.ext.asyncio import create_async_engine
    from adk_persistence import SqlAlchemyTaskStore, create_a2a_app

    engine = create_async_engine("postgresql+asyncpg://user:pass@host/db")
    store  = SqlAlchemyTaskStore(engine)

    # Build a native ADK A2A app with persistent task state:
    app = create_a2a_app(runner=runner, agent_card=card, task_store=store)

    # After ADK PR #4970 merges you can use ADK directly instead:
    # app = get_fast_api_app(..., a2a=True, a2a_task_store=store)

Optional Celery extension (for offloading long-running agent runs)::

    from adk_persistence.celery import AgentRunner, AdkAgentRunner, registry
"""

from adk_persistence.app import create_a2a_app
from adk_persistence.stores.sqlalchemy_task_store import SqlAlchemyTaskStore

__all__ = [
    "SqlAlchemyTaskStore",
    "create_a2a_app",
]
