# Copyright 2024
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0

"""
AgentRunner — execution contract for Celery workers.

The worker calls ``AgentRunner.run(payload)`` with the raw A2A JSON-RPC
payload and stores whatever it returns as the task result.

For ADK agents, use ``AdkAgentRunner`` which wraps a ``google.adk.runners.Runner``,
parses the A2A message from the payload, and calls ``runner.run_async()``.
"""

import uuid
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional


class AgentRunner(ABC):
    """Implement this to wrap any agent runtime in a Celery worker."""

    @abstractmethod
    async def run(self, payload: Dict[str, Any]) -> Any:
        """Execute the agent with the A2A payload; return the final result."""


class AdkAgentRunner(AgentRunner):
    """
    Wraps a Google ADK ``Runner`` for Celery-based async execution.

    Parses ``params.message`` from the A2A payload into an ADK ``Content``
    object and calls ``runner.run_async()``.

    Usage::

        from google.adk.agents import LlmAgent
        from google.adk.runners import Runner
        from google.adk.sessions import DatabaseSessionService
        from adk_task_persistence.celery import AdkAgentRunner, registry

        def agent_factory() -> AdkAgentRunner:
            return AdkAgentRunner(
                Runner(
                    agent=LlmAgent(name="my_agent", model="gemini-2.0-flash"),
                    app_name="my_app",
                    session_service=DatabaseSessionService(DB_URL),
                )
            )

        registry.register(
            "my_agent",
            agent_factory=agent_factory,
            session_service_factory=lambda: None,  # embedded in runner above
            task_store_factory=lambda: SqlAlchemyTaskStore(engine),
        )
    """

    def __init__(self, runner: Any) -> None:
        self._runner = runner

    async def run(self, payload: Dict[str, Any]) -> Optional[Any]:
        try:
            from google.genai.types import Content, Part  # type: ignore[import]
        except ImportError as exc:
            raise ImportError(
                "google-adk must be installed to use AdkAgentRunner."
            ) from exc

        params: Dict[str, Any] = payload.get("params") or {}
        user_id = str(params.get("userId") or params.get("user_id") or "anonymous")
        session_id = str(
            params.get("sessionId") or params.get("session_id") or uuid.uuid4()
        )

        message: Dict[str, Any] = params.get("message") or {}
        text_parts = [
            Part(text=p["text"])
            for p in message.get("parts", [])
            if isinstance(p, dict) and "text" in p
        ]
        if not text_parts:
            text_parts = [Part(text=str(params or payload))]

        new_message = Content(role="user", parts=text_parts)

        final_event = None
        async for event in self._runner.run_async(
            user_id=user_id,
            session_id=session_id,
            new_message=new_message,
        ):
            final_event = event
            if hasattr(event, "is_final_response") and event.is_final_response():
                break

        if final_event is None:
            return None

        content = getattr(final_event, "content", None)
        if content is not None:
            return content.model_dump() if hasattr(content, "model_dump") else str(content)
        return str(final_event)
