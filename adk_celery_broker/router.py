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
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import JSONResponse

from adk_celery_broker.task_store import A2aTask, BaseA2aTaskStore, TaskStatus
from adk_celery_broker.worker import execute_a2a_task


def get_celery_a2a_router(agent_id: str, task_store: BaseA2aTaskStore) -> APIRouter:
    """
    Build the FastAPI router for A2A-compatible endpoints backed by Celery.

    The task_store is a shared instance (e.g. a connection-pooled database
    client) that is read by both the HTTP pods and the Celery workers.  This
    is what makes status polling work correctly across multiple pods without
    sticky sessions.

    Args:
        agent_id: ID registered via AgentRegistry.register().
        task_store: Persistent store for A2A task lifecycle state.  Must be
                    the same backing store that the Celery workers write to.
    """
    router = APIRouter()

    @router.post("/tasks", status_code=status.HTTP_202_ACCEPTED)
    async def submit_task(request: Request) -> JSONResponse:
        """Accept an A2A JSON-RPC request and hand it off to Celery."""
        try:
            payload = await request.json()
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid JSON payload")

        task_id = payload.get("id") or str(uuid.uuid4())

        task = A2aTask(id=task_id, status=TaskStatus.SUBMITTED, payload=payload)
        try:
            await task_store.save(task)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Task store error: {exc}")

        execute_a2a_task.apply_async(args=[agent_id, task_id, payload], task_id=task_id)

        return JSONResponse(
            status_code=status.HTTP_202_ACCEPTED,
            content={"id": task_id, "status": TaskStatus.SUBMITTED},
        )

    @router.get("/tasks/{task_id}")
    async def get_task(task_id: str) -> Dict[str, Any]:
        """
        Return the current lifecycle state of an A2A task.

        Because this reads from the shared task_store (not local memory), any
        pod in the cluster can serve this request regardless of which pod
        originally accepted the submission.
        """
        try:
            task = await task_store.get(task_id)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Task store error: {exc}")

        if task is None:
            raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found")

        response: Dict[str, Any] = {"id": task.id, "status": task.status}
        if task.result is not None:
            response["result"] = task.result
        if task.error is not None:
            response["error"] = task.error
        return response

    @router.get("/tasks")
    async def list_tasks() -> Dict[str, Any]:
        """Return all known tasks from the task store."""
        try:
            tasks = await task_store.list_tasks()
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Task store error: {exc}")

        return {
            "tasks": [
                {"id": t.id, "status": t.status}
                for t in tasks
            ]
        }

    return router
