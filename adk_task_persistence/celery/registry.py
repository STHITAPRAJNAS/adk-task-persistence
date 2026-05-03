# Copyright 2024
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0

from typing import Any, Callable, Dict, Optional, Tuple


class AgentRegistry:
    """
    Registry mapping agent IDs to factory functions for Celery workers.

    Workers run in separate processes and cannot share live objects across
    process boundaries.  Factories allow each worker to reconstruct all
    components independently.

    Usage::

        from adk_task_persistence.celery import registry

        registry.register(
            "my_agent",
            agent_factory=lambda: MyAdkAgentRunner(),
            session_service_factory=lambda: DatabaseSessionService(DB_URL),
            task_store_factory=lambda: SqlAlchemyTaskStore(engine),
        )
    """

    def __init__(self) -> None:
        self._registry: Dict[
            str,
            Tuple[
                Callable[..., Any],
                Callable[..., Any],
                Optional[Callable[..., Any]],
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
            agent_id: Unique string key.
            agent_factory: Returns an ``AgentRunner`` instance.
            session_service_factory: Returns a ``BaseSessionService``.
                Embed the session service inside your ``AgentRunner`` (e.g.
                pass it to the ADK ``Runner`` constructor); this factory is
                stored for reference but is not called by workers directly.
            task_store_factory: Returns a ``SqlAlchemyTaskStore`` (or any
                ``a2a.server.tasks.TaskStore``).  Workers call this to get
                their own store instance for writing task state.
        """
        self._registry[agent_id] = (
            agent_factory,
            session_service_factory,
            task_store_factory,
        )

    def get(
        self, agent_id: str
    ) -> Tuple[Callable[..., Any], Callable[..., Any], Optional[Callable[..., Any]]]:
        """Return ``(agent_factory, session_service_factory, task_store_factory)``."""
        if agent_id not in self._registry:
            raise KeyError(
                f"Agent ID '{agent_id}' not found. "
                "Call registry.register() before dispatching tasks."
            )
        return self._registry[agent_id]

    def _clear(self) -> None:
        """Remove all entries. For test isolation only."""
        self._registry.clear()


registry = AgentRegistry()
