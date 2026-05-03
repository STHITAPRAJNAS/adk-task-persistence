"""
Tests for SqlAlchemyTaskStore using an in-memory SQLite database.

The a2a types (Task, ServerCallContext, etc.) are provided by the stubs
registered in conftest.py so these tests run without google-adk installed.
"""

import pytest
from sqlalchemy.ext.asyncio import create_async_engine

from tests.conftest import ListTasksRequest, ServerCallContext, Task, TaskState, TaskStatus
from adk_task_persistence.stores.sqlalchemy_task_store import SqlAlchemyTaskStore


@pytest.fixture
async def engine():
    eng = create_async_engine("sqlite+aiosqlite:///:memory:")
    yield eng
    await eng.dispose()


@pytest.fixture
async def store(engine):
    s = SqlAlchemyTaskStore(engine, table_name="test_tasks")
    yield s


def _ctx():
    return ServerCallContext()


def _task(task_id, state=TaskState.SUBMITTED):
    return Task(id=task_id, status=TaskStatus(state=state))


@pytest.mark.asyncio
async def test_save_and_get(store):
    task = _task("t1")
    await store.save(task, _ctx())
    result = await store.get("t1", _ctx())
    assert result is not None
    assert result.id == "t1"
    assert result.status.state == TaskState.SUBMITTED


@pytest.mark.asyncio
async def test_get_missing_returns_none(store):
    assert await store.get("ghost", _ctx()) is None


@pytest.mark.asyncio
async def test_save_updates_existing_row(store):
    task = _task("t1")
    await store.save(task, _ctx())
    task.status = TaskStatus(state=TaskState.WORKING)
    await store.save(task, _ctx())
    result = await store.get("t1", _ctx())
    assert result.status.state == TaskState.WORKING


@pytest.mark.asyncio
async def test_save_result_field(store):
    task = _task("t1")
    task.result = {"answer": 42}
    await store.save(task, _ctx())
    result = await store.get("t1", _ctx())
    assert result.result == {"answer": 42}


@pytest.mark.asyncio
async def test_save_error_field(store):
    task = _task("t1", TaskState.FAILED)
    task.error = "something exploded"
    await store.save(task, _ctx())
    result = await store.get("t1", _ctx())
    assert result.error == "something exploded"


@pytest.mark.asyncio
async def test_list_empty(store):
    response = await store.list(ListTasksRequest(), _ctx())
    assert response.tasks == []


@pytest.mark.asyncio
async def test_list_all_tasks(store):
    for i in range(3):
        await store.save(_task(f"t{i}"), _ctx())
    response = await store.list(ListTasksRequest(), _ctx())
    assert len(response.tasks) == 3


@pytest.mark.asyncio
async def test_list_filters_by_task_ids(store):
    for i in range(4):
        await store.save(_task(f"t{i}"), _ctx())
    response = await store.list(ListTasksRequest(task_ids=["t0", "t2"]), _ctx())
    ids = {t.id for t in response.tasks}
    assert ids == {"t0", "t2"}


@pytest.mark.asyncio
async def test_delete_removes_task(store):
    await store.save(_task("t1"), _ctx())
    await store.delete("t1", _ctx())
    assert await store.get("t1", _ctx()) is None


@pytest.mark.asyncio
async def test_delete_nonexistent_is_noop(store):
    await store.delete("ghost", _ctx())


@pytest.mark.asyncio
async def test_table_created_on_first_use(engine):
    store = SqlAlchemyTaskStore(engine, table_name="auto_created", create_table=True)
    await store.save(_task("t1"), _ctx())
    result = await store.get("t1", _ctx())
    assert result is not None


@pytest.mark.asyncio
async def test_multiple_saves_are_idempotent(store):
    task = _task("t1")
    for _ in range(5):
        await store.save(task, _ctx())
    response = await store.list(ListTasksRequest(), _ctx())
    assert len(response.tasks) == 1
