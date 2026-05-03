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

from typing import Any, Callable, Optional
from fastapi import FastAPI
from adk_celery_broker.router import get_celery_a2a_router
from adk_celery_broker.registry import registry

def get_celery_fastapi_app(
    agent_id: str = "default",
    session_service_factory: Optional[Callable[..., Any]] = None,
    stateful_task_store: Optional[Any] = None,
    **fastapi_kwargs
) -> FastAPI:
    """
    Primary interface/builder class that replaces ADK's native get_fastapi_app.

    This function initializes a FastAPI application and mounts the custom A2A compliant router
    that decouples the ingress from the execution loop. It intercepts ADK-specific kwargs
    like `stateful_task_store` to maintain backwards compatibility with the ADK CLI.

    Args:
        agent_id: The string ID of the agent registered in the AgentRegistry. Defaults to 'default'.
        session_service_factory: Optional. A callable returning a SessionService instance.
                                 If None, it retrieves it from the AgentRegistry using the agent_id.
        stateful_task_store: Maintains compatibility with ADK CLI native arguments.
        **fastapi_kwargs: Additional kwargs to pass to FastAPI() (e.g., middleware, title).

    Returns:
        A configured FastAPI application ready to be served by Uvicorn.
    """
    # Maintain compatibility: if stateful_task_store is passed and no session service is provided,
    # we can use the stateful_task_store as the session service.
    if session_service_factory is None and stateful_task_store is not None:
        session_service_factory = lambda: stateful_task_store

    # If session service factory is STILL not provided explicitly, look it up in the registry
    if session_service_factory is None:
        try:
            _, session_service_factory = registry.get(agent_id)
        except KeyError:
            raise ValueError(
                f"session_service_factory must be provided, stateful_task_store must be passed, "
                f"or agent_id '{agent_id}' must be registered in AgentRegistry."
            )

    # Initialize FastAPI
    title = fastapi_kwargs.pop("title", "ADK Celery Broker API")
    description = fastapi_kwargs.pop("description", "A2A HTTP Ingress backed by Celery and Redis")

    app = FastAPI(
        title=title,
        description=description,
        **fastapi_kwargs
    )

    # Create and include the router
    router = get_celery_a2a_router(agent_id, session_service_factory)
    app.include_router(router)

    return app
