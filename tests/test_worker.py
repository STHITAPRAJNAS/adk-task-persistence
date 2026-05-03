import asyncio

import pytest

from adk_celery_broker.runner import AgentRunner
from adk_celery_broker.task_store import A2aTask, InMemoryA2aTaskStore, TaskStatus
from adk_celery_broker.worker import _execute_async


# ── Helpers ───────────────────────────────────────────────────────────────────

class SuccessRunner(AgentRunner):
    async def run(self, payload):
        return {"answer": 42}


class FailingRunner(AgentRunner):
    async def run(self, payload):
        raise ValueError("agent exploded")


class EchoRunner(AgentRunner):
    async def run(self, payload):
        return payload


# ── _execute_async ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_execute_transitions_to_completed():
    store = InMemoryA2aTaskStore()
    await store.save(A2aTask(id="t1", status=TaskStatus.SUBMITTED, payload={}))

    result = await _execute_async("t1", {}, SuccessRunner(), store)

    assert result["status"] == TaskStatus.COMPLETED
    assert result["result"] == {"answer": 42}

    task = await store.get("t1")
    assert task.status == TaskStatus.COMPLETED
    assert task.result == {"answer": 42}


@pytest.mark.asyncio
async def test_execute_transitions_to_working_then_completed():
    store = InMemoryA2aTaskStore()
    statuses = []

    class TrackingRunner(AgentRunner):
        async def run(self, payload):
            t = await store.get("t1")
            statuses.append(t.status)
            return "ok"

    await store.save(A2aTask(id="t1", status=TaskStatus.SUBMITTED, payload={}))
    await _execute_async("t1", {}, TrackingRunner(), store)

    assert statuses == [TaskStatus.WORKING]


@pytest.mark.asyncio
async def test_execute_transitions_to_failed_on_exception():
    store = InMemoryA2aTaskStore()
    await store.save(A2aTask(id="t1", status=TaskStatus.SUBMITTED, payload={}))

    with pytest.raises(ValueError, match="agent exploded"):
        await _execute_async("t1", {}, FailingRunner(), store)

    task = await store.get("t1")
    assert task.status == TaskStatus.FAILED
    assert "agent exploded" in task.error


@pytest.mark.asyncio
async def test_execute_creates_task_if_not_in_store():
    store = InMemoryA2aTaskStore()
    # Do NOT pre-populate the store
    result = await _execute_async("new-task", {"x": 1}, EchoRunner(), store)

    assert result["status"] == TaskStatus.COMPLETED
    task = await store.get("new-task")
    assert task is not None
    assert task.status == TaskStatus.COMPLETED


@pytest.mark.asyncio
async def test_execute_stores_error_string_on_failure():
    store = InMemoryA2aTaskStore()

    class BoomRunner(AgentRunner):
        async def run(self, payload):
            raise RuntimeError("something went wrong")

    with pytest.raises(RuntimeError):
        await _execute_async("t1", {}, BoomRunner(), store)

    task = await store.get("t1")
    assert task.error == "something went wrong"


# ── AgentRunner ABC ───────────────────────────────────────────────────────────

def test_agent_runner_is_abstract():
    with pytest.raises(TypeError):
        AgentRunner()  # type: ignore[abstract]


def test_concrete_runner_must_implement_run():
    class Incomplete(AgentRunner):
        pass  # missing run()

    with pytest.raises(TypeError):
        Incomplete()  # type: ignore[abstract]
