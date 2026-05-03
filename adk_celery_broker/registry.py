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

from typing import Any, Callable, Dict, Optional, Tuple


class AgentRegistry:
    """
    Registry mapping string IDs to agent, session-service, and task-store
    factory functions.

    Factories (not instances) are stored so that Celery workers running in
    separate processes can reconstruct all ADK primitives independently without
    pickling live objects across process boundaries.

    The module-level ``registry`` singleton is the normal entry point::

        from adk_celery_broker import registry

        registry.register(
            "my_agent",
            agent_factory=lambda: MyAdkAgentRunner(),
            session_service_factory=lambda: DatabaseSessionService(DB_URL),
            task_store_factory=lambda: PostgresTaskStore(DB_URL),
        )
    """

    def __init__(self) -> None:
        self._registry: Dict[
            str,
            Tuple[
                Callable[..., Any],            # agent_factory → AgentRunner
                Callable[..., Any],            # session_service_factory → BaseSessionService
                Optional[Callable[..., Any]],  # task_store_factory → BaseA2aTaskStore
            ],
        ] = {}

    def register(
        self,
        agent_id: str,
        agent_factory: Callable[..., Any],
        session_service_factory: Callable[..., Any],
        task_store_factory: Optional[Callable[..., Any]] = None,
    ) -> None:
        """
        Register factories under a unique agent ID.

        Args:
            agent_id: Unique string identifier for this agent configuration.
            agent_factory: Zero-argument callable returning an ``AgentRunner``
                instance.  Use ``AdkAgentRunner`` to wrap a Google ADK
                ``Runner``, or implement ``AgentRunner`` directly.
            session_service_factory: Zero-argument callable returning an ADK
                ``BaseSessionService``.  The worker does not call this
                directly — embed the session service inside your ``AgentRunner``
                (e.g. pass it to the ADK ``Runner`` constructor).  Stored here
                so the HTTP process can reference it if needed.
            task_store_factory: Zero-argument callable returning a
                ``BaseA2aTaskStore``.  Both the HTTP pod and workers call this
                to get their own store instance.  Omit to fall back to
                ``InMemoryA2aTaskStore`` (not suitable for multi-pod deploys).
        """
        self._registry[agent_id] = (agent_factory, session_service_factory, task_store_factory)

    def get(
        self, agent_id: str
    ) -> Tuple[Callable[..., Any], Callable[..., Any], Optional[Callable[..., Any]]]:
        """Return ``(agent_factory, session_service_factory, task_store_factory)``."""
        if agent_id not in self._registry:
            raise KeyError(
                f"Agent ID '{agent_id}' not found in AgentRegistry. "
                "Call registry.register() before dispatching tasks."
            )
        return self._registry[agent_id]

    def _clear(self) -> None:
        """Remove all registrations. Intended for use in tests only."""
        self._registry.clear()


# Module-level singleton
registry = AgentRegistry()
