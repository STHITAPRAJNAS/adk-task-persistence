"""
Shared test fixtures and a2a-sdk mocks.

a2a-sdk is a runtime dependency of google-adk which is not installed in the
test environment.  We register lightweight Pydantic stand-ins under the
``a2a.*`` module paths so the production code can ``import a2a.types`` etc.
without ImportError.
"""

import sys
import types
from unittest.mock import MagicMock

import pytest
from pydantic import BaseModel


class TaskState:
    SUBMITTED = "submitted"
    WORKING = "working"
    COMPLETED = "completed"
    FAILED = "failed"

    def __init__(self, value: str) -> None:
        self.value = value

    def __eq__(self, other: object) -> bool:
        return isinstance(other, TaskState) and self.value == other.value


class TaskStatus(BaseModel):
    state: str = TaskState.SUBMITTED

    def __init__(self, state=TaskState.SUBMITTED, **data):
        if isinstance(state, TaskState):
            state = state.value
        super().__init__(state=state, **data)


class Task(BaseModel):
    id: str
    status: TaskStatus = TaskStatus()
    result: object = None
    error: str | None = None


class ListTasksRequest(BaseModel):
    task_ids: list[str] = []


class ListTasksResponse(BaseModel):
    tasks: list[Task] = []


class ServerCallContext:
    pass


def _register_a2a_stubs() -> None:
    a2a = types.ModuleType("a2a")
    a2a_types = types.ModuleType("a2a.types")
    a2a_types.Task = Task
    a2a_types.TaskStatus = TaskStatus
    a2a_types.TaskState = TaskState
    a2a_types.ListTasksRequest = ListTasksRequest
    a2a_types.ListTasksResponse = ListTasksResponse

    a2a_server = types.ModuleType("a2a.server")
    a2a_server_tasks = types.ModuleType("a2a.server.tasks")
    a2a_server_tasks.TaskStore = object
    a2a_server_context = types.ModuleType("a2a.server.context")
    a2a_server_context.ServerCallContext = ServerCallContext
    a2a_server_apps = types.ModuleType("a2a.server.apps")
    a2a_server_request_handlers = types.ModuleType("a2a.server.request_handlers")

    sys.modules.setdefault("a2a", a2a)
    sys.modules.setdefault("a2a.types", a2a_types)
    sys.modules.setdefault("a2a.server", a2a_server)
    sys.modules.setdefault("a2a.server.tasks", a2a_server_tasks)
    sys.modules.setdefault("a2a.server.context", a2a_server_context)
    sys.modules.setdefault("a2a.server.apps", a2a_server_apps)
    sys.modules.setdefault("a2a.server.request_handlers", a2a_server_request_handlers)


_register_a2a_stubs()
