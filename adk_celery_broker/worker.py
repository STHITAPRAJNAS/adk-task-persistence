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
from typing import Any, Dict

from adk_celery_broker.celery_app import celery_app
from adk_celery_broker.config import settings
from adk_celery_broker.registry import registry
from adk_celery_broker.runner import AgentRunner
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
    Celery task: execute an ADK agent and persist the result via the task store.

    All components are reconstructed from factories registered in
    ``AgentRegistry`` so this task is fully self-contained and can run in any
    worker process without shared in-process state.
    """
    logger.info("Starting task %s (agent=%s)", task_id, agent_id)

    try:
        agent_factory, _, task_store_factory = registry.get(agent_id)
        agent_runner: AgentRunner = agent_factory()
        if not isinstance(agent_runner, AgentRunner):
            raise TypeError(
                f"agent_factory for '{agent_id}' must return an AgentRunner instance, "
                f"got {type(agent_runner).__name__}. "
                "Wrap your agent with AdkAgentRunner or implement AgentRunner.run()."
            )
        task_store: BaseA2aTaskStore = (
            task_store_factory() if task_store_factory is not None else InMemoryA2aTaskStore()
        )
    except KeyError as exc:
        logger.error("Registry lookup failed for agent '%s': %s", agent_id, exc)
        raise
    except Exception as exc:
        logger.error("Failed to build components for agent '%s': %s", agent_id, exc)
        raise

    try:
        return asyncio.run(_execute_async(task_id, payload, agent_runner, task_store))
    except Exception:
        logger.exception("Task %s raised an unhandled exception", task_id)
        raise


async def _execute_async(
    task_id: str,
    payload: Dict[str, Any],
    agent_runner: AgentRunner,
    task_store: BaseA2aTaskStore,
) -> Dict[str, Any]:
    """Transition task through working → completed/failed and persist each state."""
    task = await task_store.get(task_id)
    if task is None:
        task = A2aTask(id=task_id, status=TaskStatus.WORKING, payload=payload)
    else:
        task.status = TaskStatus.WORKING
    await task_store.save(task)

    try:
        result = await agent_runner.run(payload)

        task = await task_store.get(task_id) or A2aTask(
            id=task_id, status=TaskStatus.COMPLETED, payload=payload
        )
        task.status = TaskStatus.COMPLETED
        task.result = result
        await task_store.save(task)

        logger.info("Task %s completed successfully", task_id)
        return {"status": TaskStatus.COMPLETED, "result": result}

    except Exception as exc:
        error_trace = traceback.format_exc()
        logger.error("Task %s failed:\n%s", task_id, error_trace)

        try:
            task = await task_store.get(task_id) or A2aTask(
                id=task_id, status=TaskStatus.FAILED, payload=payload
            )
            task.status = TaskStatus.FAILED
            task.error = str(exc)
            await task_store.save(task)
        except Exception as store_exc:
            logger.error(
                "Failed to persist FAILED status for task %s: %s", task_id, store_exc
            )

        raise exc
