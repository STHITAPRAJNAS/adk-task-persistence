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

logger = logging.getLogger(__name__)

@celery_app.task(
    bind=True,
    autoretry_for=(Exception,),
    max_retries=settings.max_retries,
    retry_backoff=settings.retry_backoff,
    retry_backoff_max=settings.retry_backoff_max,
    acks_late=True, # Important for reliability
    name="adk_celery_broker.worker.execute_a2a_task"
)
def execute_a2a_task(self, agent_id: str, task_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Celery task that executes the ADK agent's run loop asynchronously.

    Args:
        agent_id: The string ID of the agent registered in the AgentRegistry.
        task_id: The unique identifier for the A2A task session.
        payload: The JSON-RPC A2A payload.
    """
    logger.info(f"Starting execution for task {task_id} with agent_id {agent_id}")

    try:
        # 1. Use the AgentRegistry to instantiate the correct Agent and SessionService dynamically.
        agent_factory, session_service_factory = registry.get(agent_id)
        agent_instance = agent_factory()
        session_service_instance = session_service_factory()
    except KeyError as e:
        logger.error(f"AgentRegistry error: {e}")
        # Not retrying registry errors as they are likely configuration issues
        raise
    except Exception as e:
        logger.error(f"Failed to instantiate agent or session service: {e}")
        raise

    try:
        # Run the async logic in a synchronous Celery task
        result = asyncio.run(_run_agent_async(task_id, payload, agent_instance, session_service_instance))
        return result
    except Exception as e:
        logger.exception(f"Task {task_id} failed with exception.")
        # Re-raise to trigger Celery retry logic for transient network/LLM errors
        raise e

async def _run_agent_async(task_id: str, payload: Dict[str, Any], agent_instance: Any, session_service_instance: Any) -> Dict[str, Any]:
    """
    The core async logic for interacting with the ADK primitives.
    """
    # Mark as WORKING in DB
    try:
        if hasattr(session_service_instance, "update_task_status"):
             await session_service_instance.update_task_status(task_id, "WORKING")
    except Exception as e:
        logger.warning(f"Failed to update task status to WORKING for {task_id}: {e}")

    try:
        # 2. Load the existing A2A session state using the task_id.
        state = None
        if hasattr(session_service_instance, "load_state"):
            state = await session_service_instance.load_state(task_id)

        # 3. Execute the ADK agent run loop.
        final_response = None
        if hasattr(agent_instance, "run_stream"):
            async for chunk in agent_instance.run_stream(payload, state=state):
                final_response = chunk
        elif hasattr(agent_instance, "run"):
            final_response = await agent_instance.run(payload, state=state)
        elif hasattr(agent_instance, "__call__"):
            final_response = await agent_instance(payload, state=state)
        else:
             raise ValueError("Agent does not have a run, run_stream, or __call__ method.")

        # 4. Ensure all state changes are committed back to the SessionService.
        if hasattr(session_service_instance, "save_state_and_status"):
             await session_service_instance.save_state_and_status(
                 task_id,
                 state=final_response,
                 status="COMPLETED"
             )
        elif hasattr(session_service_instance, "update_task_status"):
             await session_service_instance.update_task_status(task_id, "COMPLETED")

        logger.info(f"Task {task_id} completed successfully.")
        return {"status": "COMPLETED", "result": final_response}

    except Exception as e:
        error_trace = traceback.format_exc()
        logger.error(f"Task {task_id} failed: {error_trace}")

        try:
             if hasattr(session_service_instance, "update_task_status"):
                 await session_service_instance.update_task_status(
                     task_id,
                     "FAILED",
                     error=str(e),
                     traceback=error_trace
                 )
        except Exception as inner_e:
             logger.error(f"Failed to update task {task_id} status to FAILED: {inner_e}")

        raise e
