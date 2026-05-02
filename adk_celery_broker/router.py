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

import uuid
from typing import Any, Dict, Callable

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import JSONResponse

from adk_celery_broker.worker import execute_a2a_task

def get_celery_a2a_router(agent_id: str, session_service_factory: Callable[..., Any]) -> APIRouter:
    """
    Creates the FastAPI APIRouter that handles A2A protocol compliant endpoints.

    Args:
        agent_id: The string ID of the agent registered in the AgentRegistry.
        session_service_factory: A callable that returns the ADK SessionService instance
                                 used for polling and initial state writing.
    """
    router = APIRouter()

    @router.post("/", status_code=status.HTTP_202_ACCEPTED)
    async def submit_task(request: Request) -> JSONResponse:
        """
        Accepts a standard A2A JSON-RPC request and dispatches to Celery.
        """
        try:
            payload = await request.json()
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid JSON payload")

        # Extract task_id from payload or generate one
        task_id = payload.get("id", str(uuid.uuid4()))

        # Instantiate session service to write initial state
        try:
            session_service = session_service_factory()
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to instantiate session service: {e}")

        # Write initial SUBMITTED state to the injected SessionService
        try:
            if hasattr(session_service, "create_task"):
                 await session_service.create_task(task_id, payload=payload, status="SUBMITTED")
            elif hasattr(session_service, "update_task_status"):
                 await session_service.update_task_status(task_id, "SUBMITTED")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to write initial state: {e}")

        # Dispatch payload to Celery
        execute_a2a_task.apply_async(args=[agent_id, task_id, payload], task_id=task_id)

        # Return A2A-compliant 202 Accepted response containing the task_id
        return JSONResponse(
            status_code=status.HTTP_202_ACCEPTED,
            content={"task_id": task_id, "status": "SUBMITTED"}
        )

    @router.get("/task/{task_id}")
    async def get_task_status(task_id: str) -> Dict[str, Any]:
        """
        Queries the SessionService to return the current A2A status
        and final payload if completed, strictly bypassing local memory.
        """
        try:
            session_service = session_service_factory()
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to instantiate session service: {e}")

        # Query DatabaseSessionService to bypass local memory
        if hasattr(session_service, "get_task_status"):
            task_info = await session_service.get_task_status(task_id)
            if not task_info:
                raise HTTPException(status_code=404, detail="Task not found")
            return task_info

        # Fallback if specific get_task_status is not implemented but get_state is
        if hasattr(session_service, "load_state"):
            state = await session_service.load_state(task_id)
            if state is None:
                 raise HTTPException(status_code=404, detail="Task not found")
            return state

        raise NotImplementedError("Session service missing required status retrieval methods.")

    return router
