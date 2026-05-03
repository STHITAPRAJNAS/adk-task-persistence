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

import asyncio
import logging
import traceback
from typing import Any, Dict, Optional

from adk_celery_broker.celery_app import celery_app
from adk_celery_broker.config import settings
from adk_celery_broker.registry import registry
from adk_celery_broker.task_store import A2aTask, BaseA2aTaskStore, InMemoryA2aTaskStore, TaskStatus

logger = logging.getLogger(__name__)


@celery_app.task(
    bind=True,
    autoretry_for=(Exception,),
    max_retries=settings.max_retries,
    retry_backoff=settings.retry_backoff,
    retry_backoff_max=settings.retry_backoff_max,
    acks_late=True,
    name="adk_celery_broker.worker.execute_a2a_task",
)
def execute_a2a_task(
    self, agent_id: str, task_id: str, payload: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Celery task: run an ADK agent and persist results via the task store.

    The agent, session service, and task store are all reconstructed from
    factories registered in AgentRegistry so that this task is self-contained
    and can run in any worker process.
    """
    logger.info("Starting task %s (agent=%s)", task_id, agent_id)

    try:
        agent_factory, session_service_factory, task_store_factory = registry.get(agent_id)
        agent = agent_factory()
        session_service = session_service_factory()
        task_store: BaseA2aTaskStore = (
            task_store_factory() if task_store_factory is not None else InMemoryA2aTaskStore()
        )
    except KeyError as exc:
        logger.error("Registry error for agent '%s': %s", agent_id, exc)
        raise
    except Exception as exc:
        logger.error("Failed to instantiate components for agent '%s': %s", agent_id, exc)
        raise

    try:
        result = asyncio.run(
            _execute_async(task_id, payload, agent, session_service, task_store)
        )
        return result
    except Exception:
        logger.exception("Task %s raised an unhandled exception", task_id)
        raise


async def _execute_async(
    task_id: str,
    payload: Dict[str, Any],
    agent: Any,
    session_service: Any,
    task_store: BaseA2aTaskStore,
) -> Dict[str, Any]:
    """Core async execution: update task status, run agent, persist result."""
    # Mark as working
    working_task = await task_store.get(task_id)
    if working_task is None:
        working_task = A2aTask(id=task_id, status=TaskStatus.WORKING, payload=payload)
    else:
        working_task.status = TaskStatus.WORKING
    await task_store.save(working_task)

    try:
        final_result = await _run_agent(agent, session_service, payload)

        completed_task = await task_store.get(task_id)
        if completed_task is None:
            completed_task = A2aTask(id=task_id, status=TaskStatus.COMPLETED, payload=payload)
        completed_task.status = TaskStatus.COMPLETED
        completed_task.result = final_result
        await task_store.save(completed_task)

        logger.info("Task %s completed", task_id)
        return {"status": TaskStatus.COMPLETED, "result": final_result}

    except Exception as exc:
        error_trace = traceback.format_exc()
        logger.error("Task %s failed: %s", task_id, error_trace)

        try:
            failed_task = await task_store.get(task_id)
            if failed_task is None:
                failed_task = A2aTask(id=task_id, status=TaskStatus.FAILED, payload=payload)
            failed_task.status = TaskStatus.FAILED
            failed_task.error = str(exc)
            await task_store.save(failed_task)
        except Exception as store_exc:
            logger.error(
                "Failed to persist FAILED status for task %s: %s", task_id, store_exc
            )

        raise exc


async def _run_agent(agent: Any, session_service: Any, payload: Dict[str, Any]) -> Optional[Any]:
    """
    Execute the agent.

    Supports ADK Runner-based agents and simpler callable interfaces.
    If your agent is a proper ADK BaseAgent, register it via AgentRegistry
    and wire it to an ADK Runner in your agent_factory — then call
    runner.run_async() inside a thin wrapper and return the final event here.
    """
    # ADK Runner interface (preferred): runner.run_async() returns an async generator
    if hasattr(agent, "run_async"):
        final_event = None
        async for event in agent.run_async(payload, session_service=session_service):
            final_event = event
        return final_event

    # Streaming interface
    if hasattr(agent, "run_stream"):
        final_chunk = None
        async for chunk in agent.run_stream(payload, session_service=session_service):
            final_chunk = chunk
        return final_chunk

    # Simple async interface
    if hasattr(agent, "run"):
        return await agent.run(payload, session_service=session_service)

    # Async callable
    if callable(agent):
        result = agent(payload, session_service=session_service)
        if asyncio.iscoroutine(result):
            return await result
        return result

    raise TypeError(
        f"Agent {type(agent).__name__} does not expose run_async, run_stream, "
        "run, or __call__. Cannot execute."
    )
