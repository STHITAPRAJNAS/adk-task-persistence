"""Tests for the Celery worker's _execute_async logic."""

import pytest

from adk_task_persistence.celery.runner import AgentRunner
from adk_task_persistence.celery.worker import _execute_async
from tests.conftest import ServerCallContext, Task, TaskState, TaskStatus


class DictTaskStore:
    def __init__(self):
        self._data = {}

    async def save(self, task, context):
        self._data[task.id] = task

    async def get(self, task_id, context):
        return self._data.get(task_id)

    async def list(self, params, context):
        return list(self._data.values())

    async def delete(self, task_id, context):
        self._data.pop(task_id, None)


class SuccessRunner(AgentRunner):
    async def run(self, payload):
        return {"answer": 42}


class FailingRunner(AgentRunner):
    async def run(self, payload):
        raise ValueError("agent exploded")


@pytest.mark.asyncio
async def test_completes_and_writes_result(monkeypatch):
    store = DictTaskStore()
    task = Task(id="t1", status=TaskStatus(state=TaskState.SUBMITTED))
    await store.save(task, ServerCallContext())

    import adk_task_persistence.celery.worker as w_mod

    async def patched(ts, tid, state, result=None, error=None):
        ctx = ServerCallContext()
        existing = await ts.get(tid, ctx)
        if existing is None:
            existing = Task(id=tid, status=TaskStatus(state=state))
        existing.status = TaskStatus(state=state)
        if result is not None:
            existing.result = result
        if error is not None:
            existing.error = error
        await ts.save(existing, ctx)

    monkeypatch.setattr(w_mod, "_update_task_state", patched)

    result = await _execute_async("t1", {}, SuccessRunner(), store)

    assert result["status"] == "completed"
    assert result["result"] == {"answer": 42}
    saved = await store.get("t1", ServerCallContext())
    assert saved.status.state == "completed"
    assert saved.result == {"answer": 42}


@pytest.mark.asyncio
async def test_fails_and_writes_error(monkeypatch):
    store = DictTaskStore()
    task = Task(id="t1", status=TaskStatus())
    await store.save(task, ServerCallContext())

    import adk_task_persistence.celery.worker as w_mod

    async def patched(ts, tid, state, result=None, error=None):
        ctx = ServerCallContext()
        t = await ts.get(tid, ctx) or Task(id=tid, status=TaskStatus())
        t.status = TaskStatus(state=state)
        if error:
            t.error = error
        await ts.save(t, ctx)

    monkeypatch.setattr(w_mod, "_update_task_state", patched)

    with pytest.raises(ValueError, match="agent exploded"):
        await _execute_async("t1", {}, FailingRunner(), store)

    saved = await store.get("t1", ServerCallContext())
    assert saved.status.state == "failed"
    assert "agent exploded" in saved.error
