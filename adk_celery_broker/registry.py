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
    Singleton registry mapping string IDs to agent, session-service, and
    task-store factory functions.

    Factories are used (rather than instances) so that Celery workers —
    running in separate processes — can reconstruct all ADK primitives
    independently without pickling live objects across process boundaries.

    Usage::

        registry.register(
            "my_agent",
            agent_factory=lambda: MyAgent(),
            session_service_factory=lambda: DatabaseSessionService(DB_URL),
            task_store_factory=lambda: PostgresTaskStore(DB_URL),
        )
    """

    _registry: Dict[
        str,
        Tuple[
            Callable[..., Any],           # agent_factory
            Callable[..., Any],           # session_service_factory
            Optional[Callable[..., Any]], # task_store_factory
        ],
    ] = {}

    @classmethod
    def register(
        cls,
        agent_id: str,
        agent_factory: Callable[..., Any],
        session_service_factory: Callable[..., Any],
        task_store_factory: Optional[Callable[..., Any]] = None,
    ) -> None:
        """
        Register factories under a unique agent ID.

        Args:
            agent_id: Unique string identifier for this agent configuration.
            agent_factory: Returns an ADK BaseAgent instance.
            session_service_factory: Returns a BaseSessionService instance.
            task_store_factory: Returns a BaseA2aTaskStore instance.
                                Omit to use the default InMemoryA2aTaskStore
                                (not suitable for multi-pod deployments).
        """
        cls._registry[agent_id] = (agent_factory, session_service_factory, task_store_factory)

    @classmethod
    def get(
        cls, agent_id: str
    ) -> Tuple[Callable[..., Any], Callable[..., Any], Optional[Callable[..., Any]]]:
        """Return (agent_factory, session_service_factory, task_store_factory)."""
        if agent_id not in cls._registry:
            raise KeyError(
                f"Agent ID '{agent_id}' not found in AgentRegistry. "
                "Call registry.register() before dispatching tasks."
            )
        return cls._registry[agent_id]


# Singleton
registry = AgentRegistry()
