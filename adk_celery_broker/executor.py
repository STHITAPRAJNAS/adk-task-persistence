# Copyright 2024
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import logging
import warnings
from typing import Any, Optional

from fastapi import FastAPI

from adk_celery_broker.registry import registry
from adk_celery_broker.router import get_celery_a2a_router
from adk_celery_broker.task_store import BaseA2aTaskStore, InMemoryA2aTaskStore

logger = logging.getLogger(__name__)


def get_fastapi_app(
    *,
    agent_id: str = "default",
    task_store: Optional[BaseA2aTaskStore] = None,
    **fastapi_kwargs: Any,
) -> FastAPI:
    """
    Build a FastAPI application that exposes A2A-compatible endpoints backed
    by Celery for distributed, fault-tolerant agent execution.

    This is a targeted replacement for Google ADK's ``get_fast_api_app`` with
    ``a2a=True``.  ADK always creates an ``InMemoryTaskStore`` internally when
    you enable A2A — there is no parameter to inject a custom one.  In
    multi-pod deployments this means task state lives only in the pod that
    accepted the request, so any poll that hits a different pod returns 404,
    and a container restart loses all task state silently.

    This function fills that gap: it accepts a ``task_store`` instance backed
    by any external store (Postgres, Redis, DynamoDB, …) so the entire cluster
    shares one consistent view of task state.

    ``session_service`` (ADK per-session agent state) is intentionally NOT a
    parameter here — it is only needed inside Celery workers, which reconstruct
    it via the factory registered in ``AgentRegistry``.

    Args:
        agent_id: ID previously registered via ``AgentRegistry.register()``.
        task_store: A ``BaseA2aTaskStore`` instance for A2A task lifecycle
            tracking (submitted → working → completed / failed).  Supply a
            database-backed implementation so all pods share the same task
            state.  Falls back to the factory in ``AgentRegistry`` if one was
            registered, otherwise defaults to ``InMemoryA2aTaskStore`` with a
            warning (not suitable for production multi-pod deployments).
        **fastapi_kwargs: Forwarded verbatim to ``FastAPI()``.  Accepts the
            standard FastAPI constructor arguments (``title``, ``description``,
            ``version``, ``lifespan``, ``docs_url``, etc.).

    Returns:
        A configured ``FastAPI`` application.  Add middleware and mount
        additional routers as you would with any ``FastAPI`` app.

    Example::

        from adk_celery_broker import get_fastapi_app, registry
        from myapp.stores import PostgresTaskStore
        from myapp.sessions import DatabaseSessionService

        def agent_factory():
            return MyAgent()

        def session_service_factory():
            return DatabaseSessionService(DB_URL)

        def task_store_factory():
            return PostgresTaskStore(DB_URL)

        registry.register(
            "my_agent",
            agent_factory=agent_factory,
            session_service_factory=session_service_factory,
            task_store_factory=task_store_factory,
        )

        app = get_fastapi_app(
            agent_id="my_agent",
            task_store=task_store_factory(),
            title="My Agent API",
        )
    """
    resolved_task_store = _resolve_task_store(agent_id, task_store)

    title = fastapi_kwargs.pop("title", "ADK Celery Broker")
    description = fastapi_kwargs.pop(
        "description",
        "A2A endpoints backed by Celery for distributed agent execution",
    )

    app = FastAPI(title=title, description=description, **fastapi_kwargs)

    router = get_celery_a2a_router(agent_id, resolved_task_store)
    app.include_router(router)

    return app


def _resolve_task_store(
    agent_id: str,
    task_store: Optional[BaseA2aTaskStore],
) -> BaseA2aTaskStore:
    if task_store is not None:
        return task_store

    # Try registry
    try:
        _, _, task_store_factory = registry.get(agent_id)
        if task_store_factory is not None:
            return task_store_factory()
    except KeyError:
        pass

    warnings.warn(
        f"No task_store provided for agent '{agent_id}' and none registered. "
        "Using InMemoryA2aTaskStore — task state will not survive pod restarts "
        "and will not be visible across multiple pods. "
        "Pass a database-backed BaseA2aTaskStore for production use.",
        stacklevel=2,
    )
    return InMemoryA2aTaskStore()
