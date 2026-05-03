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
Agent execution contract for Celery workers.

The worker calls AgentRunner.run(payload) with the raw A2A JSON-RPC payload
dict and stores whatever is returned as the task result.  Implement this ABC
to wrap any agent runtime — Google ADK Runner, LangChain, a raw LLM call, etc.
"""

import uuid
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional


class AgentRunner(ABC):
    """
    Contract for agent execution inside Celery workers.

    The single method ``run(payload)`` receives the full A2A JSON-RPC request
    dict and must return a JSON-serialisable result that is stored in the task
    store as ``A2aTask.result``.

    Example — minimal custom runner::

        class EchoRunner(AgentRunner):
            async def run(self, payload: dict) -> dict:
                return {"echo": payload}

        registry.register("echo", agent_factory=EchoRunner, ...)
    """

    @abstractmethod
    async def run(self, payload: Dict[str, Any]) -> Any:
        """Execute the agent and return the final result."""


class AdkAgentRunner(AgentRunner):
    """
    Wraps a Google ADK ``Runner`` for use as an ``AgentRunner``.

    Parses the standard A2A ``params.message`` from the payload and converts
    it into an ADK ``Content`` object before calling ``runner.run_async()``.
    The final event's content is returned as the task result.

    Usage::

        from google.adk.agents import LlmAgent
        from google.adk.runners import Runner
        from google.adk.sessions import DatabaseSessionService
        from adk_celery_broker import AdkAgentRunner, registry

        def agent_factory() -> AdkAgentRunner:
            session_service = DatabaseSessionService(DB_URL)
            runner = Runner(
                agent=LlmAgent(name="my_agent", model="gemini-2.0-flash"),
                app_name="my_app",
                session_service=session_service,
            )
            return AdkAgentRunner(runner)

        registry.register(
            "my_agent",
            agent_factory=agent_factory,
            session_service_factory=lambda: DatabaseSessionService(DB_URL),
            task_store_factory=lambda: MyPostgresTaskStore(DB_URL),
        )

    The ``session_service_factory`` stored in the registry is not used directly
    by the worker — the session service is embedded inside the ADK ``Runner``
    you build in ``agent_factory``.  It is stored in the registry so that the
    HTTP process can reference it independently if needed (e.g. pre-creating
    sessions before submitting tasks).
    """

    def __init__(self, runner: Any) -> None:
        """
        Args:
            runner: A configured ``google.adk.runners.Runner`` instance.
        """
        self._runner = runner

    async def run(self, payload: Dict[str, Any]) -> Optional[Any]:
        try:
            from google.genai.types import Content, Part  # type: ignore[import]
        except ImportError as exc:
            raise ImportError(
                "google-adk is required to use AdkAgentRunner. "
                "Install it with: pip install google-adk"
            ) from exc

        params: Dict[str, Any] = payload.get("params") or {}
        user_id: str = str(params.get("userId") or params.get("user_id") or "anonymous")
        session_id: str = str(
            params.get("sessionId") or params.get("session_id") or uuid.uuid4()
        )

        message: Dict[str, Any] = params.get("message") or {}
        text_parts = [
            Part(text=p["text"])
            for p in message.get("parts", [])
            if isinstance(p, dict) and "text" in p
        ]
        if not text_parts:
            # Graceful fallback for non-standard payloads
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
            if hasattr(content, "model_dump"):
                return content.model_dump()
            return str(content)

        return str(final_event)
