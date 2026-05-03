import pytest

from adk_celery_broker.task_store import A2aTask, BaseA2aTaskStore, InMemoryA2aTaskStore, TaskStatus


def test_task_status_constants():
    assert TaskStatus.SUBMITTED == "submitted"
    assert TaskStatus.WORKING == "working"
    assert TaskStatus.COMPLETED == "completed"
    assert TaskStatus.FAILED == "failed"
    assert TaskStatus.CANCELED == "canceled"


def test_a2a_task_defaults():
    task = A2aTask(id="t1", status=TaskStatus.SUBMITTED, payload={"key": "val"})
    assert task.id == "t1"
    assert task.status == TaskStatus.SUBMITTED
    assert task.payload == {"key": "val"}
    assert task.result is None
    assert task.error is None
    assert task.metadata == {}


def test_base_task_store_is_abstract():
    with pytest.raises(TypeError):
        BaseA2aTaskStore()  # type: ignore[abstract]


@pytest.mark.asyncio
async def test_inmemory_save_and_get():
    store = InMemoryA2aTaskStore()
    task = A2aTask(id="t1", status=TaskStatus.SUBMITTED, payload={})
    await store.save(task)
    retrieved = await store.get("t1")
    assert retrieved is not None
    assert retrieved.id == "t1"
    assert retrieved.status == TaskStatus.SUBMITTED


@pytest.mark.asyncio
async def test_inmemory_get_missing_returns_none():
    store = InMemoryA2aTaskStore()
    assert await store.get("does-not-exist") is None


@pytest.mark.asyncio
async def test_inmemory_save_overwrites():
    store = InMemoryA2aTaskStore()
    task = A2aTask(id="t1", status=TaskStatus.SUBMITTED, payload={})
    await store.save(task)
    task.status = TaskStatus.COMPLETED
    task.result = {"answer": 42}
    await store.save(task)
    retrieved = await store.get("t1")
    assert retrieved.status == TaskStatus.COMPLETED
    assert retrieved.result == {"answer": 42}


@pytest.mark.asyncio
async def test_inmemory_list_tasks():
    store = InMemoryA2aTaskStore()
    await store.save(A2aTask(id="a", status=TaskStatus.SUBMITTED, payload={}))
    await store.save(A2aTask(id="b", status=TaskStatus.WORKING, payload={}))
    tasks = await store.list_tasks()
    ids = {t.id for t in tasks}
    assert ids == {"a", "b"}


@pytest.mark.asyncio
async def test_inmemory_delete():
    store = InMemoryA2aTaskStore()
    await store.save(A2aTask(id="t1", status=TaskStatus.SUBMITTED, payload={}))
    await store.delete("t1")
    assert await store.get("t1") is None


@pytest.mark.asyncio
async def test_inmemory_delete_nonexistent_is_noop():
    store = InMemoryA2aTaskStore()
    await store.delete("ghost")  # must not raise
