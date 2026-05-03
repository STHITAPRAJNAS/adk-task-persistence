# Copyright 2024
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0

"""
Celery task for optional async agent execution.

This is the secondary concern of adk-persistence: keeping the HTTP pod free
during long-running (minutes-scale) agent invocations.  The primary concern
— pod-restart-safe task state — is solved by SqlAlchemyTaskStore alone and
does not require Celery.

The worker uses the A2A task store (SqlAlchemyTaskStore) to track lifecycle
state.  Because the store is shared across pods and workers, any pod can
serve status polls at any time.
"""

import asyncio
import logging
import traceback
from typing import Any, Dict

from adk_persistence.celery.celery_app import celery_app
from adk_persistence.celery.config import settings
from adk_persistence.celery.registry import registry
from adk_persistence.celery.runner import AgentRunner

logger = logging.getLogger(__name__)

# Task status strings that match the a2a.types.TaskState enum values
_WORKING = "working"
_COMPLETED = "completed"
_FAILED = "failed"


@celery_app.task(
    bind=True,
    autoretry_for=(Exception,),
    max_retries=settings.max_retries,
    retry_backoff=settings.retry_backoff,
    retry_backoff_max=settings.retry_backoff_max,
    acks_late=True,
    name="adk_persistence.celery.worker.execute_a2a_task",
)
def execute_a2a_task(
    self, agent_id: str, task_id: str, payload: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Run an ADK agent asynchronously and persist the result via the task store.

    All components are reconstructed from AgentRegistry factories so this
    task is self-contained and portable across worker processes/pods.
    """
    logger.info("Starting task %s (agent=%s)", task_id, agent_id)

    try:
        agent_factory, _, task_store_factory = registry.get(agent_id)
        agent_runner: AgentRunner = agent_factory()
        if not isinstance(agent_runner, AgentRunner):
            raise TypeError(
                f"agent_factory for '{agent_id}' must return an AgentRunner, "
                f"got {type(agent_runner).__name__}. "
                "Use AdkAgentRunner or implement AgentRunner.run()."
            )
        task_store = task_store_factory() if task_store_factory is not None else None
    except KeyError as exc:
        logger.error("Registry lookup failed for agent '%s': %s", agent_id, exc)
        raise
    except Exception as exc:
        logger.error("Failed to build components for agent '%s': %s", agent_id, exc)
        raise

    try:
        return asyncio.run(
            _execute_async(task_id, payload, agent_runner, task_store)
        )
    except Exception:
        logger.exception("Task %s raised an unhandled exception", task_id)
        raise


async def _execute_async(
    task_id: str,
    payload: Dict[str, Any],
    agent_runner: AgentRunner,
    task_store: Any,
) -> Dict[str, Any]:
    """Transition task through working → completed/failed, persist each state."""
    await _update_task_state(task_store, task_id, _WORKING)

    try:
        result = await agent_runner.run(payload)
        await _update_task_state(task_store, task_id, _COMPLETED, result=result)
        logger.info("Task %s completed", task_id)
        return {"status": _COMPLETED, "result": result}

    except Exception as exc:
        logger.error("Task %s failed:\n%s", task_id, traceback.format_exc())
        try:
            await _update_task_state(task_store, task_id, _FAILED, error=str(exc))
        except Exception as store_exc:
            logger.error(
                "Failed to persist FAILED status for task %s: %s", task_id, store_exc
            )
        raise exc


async def _update_task_state(
    task_store: Any,
    task_id: str,
    state: str,
    result: Any = None,
    error: str | None = None,
) -> None:
    """
    Update task state in the store.

    Works with both SqlAlchemyTaskStore (a2a.types.Task) and any
    store that accepts save() with a context.
    """
    if task_store is None:
        logger.warning("No task_store registered for task %s; state not persisted", task_id)
        return

    try:
        # Build a minimal context — a2a.server.context.ServerCallContext
        from a2a.server.context import ServerCallContext  # type: ignore[import]
        from a2a.types import Task, TaskState, TaskStatus  # type: ignore[import]

        ctx = ServerCallContext()
        existing: Task | None = await task_store.get(task_id, ctx)

        if existing is not None:
            existing.status = TaskStatus(state=TaskState(state))
            if result is not None:
                existing.result = result
            if error is not None:
                existing.error = error
            await task_store.save(existing, ctx)
        else:
            task = Task(
                id=task_id,
                status=TaskStatus(state=TaskState(state)),
            )
            await task_store.save(task, ctx)

    except Exception as exc:
        logger.error(
            "Failed to update task %s to state '%s': %s", task_id, state, exc
        )
