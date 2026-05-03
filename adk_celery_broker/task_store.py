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
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


class TaskStatus:
    SUBMITTED = "submitted"
    WORKING = "working"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELED = "canceled"


@dataclass
class A2aTask:
    """Represents an A2A protocol task with lifecycle state."""

    id: str
    status: str
    payload: Dict[str, Any]
    result: Optional[Any] = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class BaseA2aTaskStore(ABC):
    """
    Abstract base class for A2A task stores.

    Implement this to back task state with a persistent store (e.g. Postgres,
    Redis, DynamoDB) so task status is visible across all pods and survives
    container restarts.

    This mirrors the injection pattern used by ADK's BaseSessionService /
    DatabaseSessionService but for the A2A task lifecycle rather than
    per-session agent state.

    Example::

        class PostgresTaskStore(BaseA2aTaskStore):
            def __init__(self, dsn: str):
                self._pool = create_engine(dsn)

            async def save(self, task: A2aTask) -> None:
                ...  # upsert into tasks table

            async def get(self, task_id: str) -> Optional[A2aTask]:
                ...  # SELECT by id

            async def list_tasks(self) -> List[A2aTask]:
                ...  # SELECT all

            async def delete(self, task_id: str) -> None:
                ...  # DELETE by id
    """

    @abstractmethod
    async def save(self, task: A2aTask) -> None:
        """Persist or update a task."""

    @abstractmethod
    async def get(self, task_id: str) -> Optional[A2aTask]:
        """Retrieve a task by ID, or None if not found."""

    @abstractmethod
    async def list_tasks(self) -> List[A2aTask]:
        """Return all known tasks."""

    @abstractmethod
    async def delete(self, task_id: str) -> None:
        """Remove a task from the store."""


class InMemoryA2aTaskStore(BaseA2aTaskStore):
    """
    Default in-memory task store.

    Suitable for local development and single-process deployments only.
    In multi-pod environments, replace this with a database-backed
    implementation of BaseA2aTaskStore.
    """

    def __init__(self) -> None:
        self._tasks: Dict[str, A2aTask] = {}
        self._lock = asyncio.Lock()

    async def save(self, task: A2aTask) -> None:
        async with self._lock:
            self._tasks[task.id] = task

    async def get(self, task_id: str) -> Optional[A2aTask]:
        async with self._lock:
            return self._tasks.get(task_id)

    async def list_tasks(self) -> List[A2aTask]:
        async with self._lock:
            return list(self._tasks.values())

    async def delete(self, task_id: str) -> None:
        async with self._lock:
            self._tasks.pop(task_id, None)
