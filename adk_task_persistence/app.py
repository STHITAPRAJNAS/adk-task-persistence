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

"""
create_a2a_app() — build an ADK A2A FastAPI app with an injectable TaskStore.

This wires ADK's native A2A stack (DefaultRequestHandler +
A2AStarletteApplication) with a custom TaskStore so you get:

* Full A2A protocol compliance (SSE streaming, proper task lifecycle)
* RemoteA2aAgent compatibility (callers get streaming responses as normal)
* Pod-restart survival (task state lives in the DB, not in-process memory)

Once ADK PR #4970 merges you can replace this with::

    get_fast_api_app(..., a2a=True, a2a_task_store=SqlAlchemyTaskStore(engine))

Until then, use this helper.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

_ADK_IMPORT_ERROR = (
    "google-adk must be installed to use create_a2a_app(). "
    "Install it with: pip install google-adk"
)


def create_a2a_app(
    *,
    runner: Any,
    agent_card: Any,
    task_store: Any,
    push_config_store: Optional[Any] = None,
    url_prefix: str = "",
    **fastapi_kwargs: Any,
) -> Any:  # FastAPI
    """
    Build an ADK A2A application with a persistent, injectable TaskStore.

    This constructs ADK's native A2A request handler stack
    (``A2aAgentExecutor`` → ``DefaultRequestHandler`` →
    ``A2AStarletteApplication``) and mounts it on a FastAPI app.

    The result is **fully compatible with RemoteA2aAgent** — callers receive
    the standard SSE streaming response.  The only difference from ADK's
    default is that task state is written to your ``task_store`` instead of
    an in-process ``InMemoryTaskStore``, so all pods in the cluster share
    the same view of task state and state survives pod restarts.

    Args:
        runner: A configured ``google.adk.runners.Runner`` instance.
        agent_card: The ``AgentCard`` describing this agent (used by
            ``A2AStarletteApplication`` to serve the ``/.well-known/agent``
            endpoint).
        task_store: Any ``a2a.server.tasks.TaskStore`` implementation —
            typically ``SqlAlchemyTaskStore``.
        push_config_store: Optional push-notification config store.  Defaults
            to ADK's ``InMemoryPushNotificationConfigStore``.
        url_prefix: Mount prefix for the A2A Starlette sub-app.  Defaults
            to ``"/"`` (root).
        **fastapi_kwargs: Forwarded to ``FastAPI()``.

    Returns:
        A configured ``FastAPI`` application.

    Example::

        from sqlalchemy.ext.asyncio import create_async_engine
        from google.adk.agents import LlmAgent
        from google.adk.runners import Runner
        from google.adk.sessions import DatabaseSessionService
        from adk_task_persistence import SqlAlchemyTaskStore, create_a2a_app

        engine = create_async_engine("postgresql+asyncpg://...")
        runner = Runner(
            agent=LlmAgent(name="my_agent", model="gemini-2.0-flash"),
            app_name="my_app",
            session_service=DatabaseSessionService(DB_URL),
        )
        app = create_a2a_app(
            runner=runner,
            agent_card=agent_card,
            task_store=SqlAlchemyTaskStore(engine),
            title="My Agent",
        )
    """
    try:
        from fastapi import FastAPI
    except ImportError as exc:
        raise ImportError("fastapi must be installed.") from exc

    try:
        from a2a.server.apps import A2AStarletteApplication  # type: ignore[import]
        from a2a.server.request_handlers import DefaultRequestHandler  # type: ignore[import]
    except ImportError as exc:
        raise ImportError(_ADK_IMPORT_ERROR) from exc

    try:
        from a2a.server.tasks import (  # type: ignore[import]
            InMemoryPushNotificationConfigStore,
        )
    except ImportError:
        InMemoryPushNotificationConfigStore = None  # type: ignore[assignment,misc]

    # Resolve A2aAgentExecutor — try known import paths across ADK versions
    A2aAgentExecutor = _import_a2a_agent_executor()

    if push_config_store is None and InMemoryPushNotificationConfigStore is not None:
        push_config_store = InMemoryPushNotificationConfigStore()

    handler = DefaultRequestHandler(
        agent_executor=A2aAgentExecutor(runner=runner),
        task_store=task_store,
        push_config_store=push_config_store,
    )

    a2a_starlette = A2AStarletteApplication(
        agent_card=agent_card,
        http_handler=handler,
    )

    title = fastapi_kwargs.pop("title", "ADK Agent")
    description = fastapi_kwargs.pop("description", "")
    app = FastAPI(title=title, description=description, **fastapi_kwargs)
    app.mount(url_prefix or "/", a2a_starlette)

    return app


def _import_a2a_agent_executor() -> Any:
    """
    Import A2aAgentExecutor, trying known locations across ADK versions.

    ADK's internal module layout has changed between versions.  We try
    the most common paths in order and surface a clear error if none work.
    """
    candidates = [
        "google.adk.a2a.executor.a2a_agent_executor",
        "google.adk.a2a.executor",
        "google.adk.a2a.utils.agent_to_a2a",
        "google.adk.a2a",
    ]
    for module_path in candidates:
        try:
            import importlib
            mod = importlib.import_module(module_path)
            if hasattr(mod, "A2aAgentExecutor"):
                return mod.A2aAgentExecutor
        except ImportError:
            continue

    raise ImportError(
        "Could not import A2aAgentExecutor from google-adk. "
        "Ensure google-adk >= 1.0.0 is installed: pip install google-adk. "
        f"Tried: {candidates}"
    )
