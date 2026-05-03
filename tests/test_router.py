from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from adk_celery_broker.router import get_celery_a2a_router
from adk_celery_broker.task_store import A2aTask, InMemoryA2aTaskStore, TaskStatus


@pytest.fixture
def store():
    return InMemoryA2aTaskStore()


@pytest.fixture
def app(store):
    a = FastAPI()
    a.include_router(get_celery_a2a_router("test_agent", store))
    return a


@pytest.fixture
def client(app):
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


# ── POST /tasks ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_submit_returns_202(client, store):
    with patch("adk_celery_broker.router.execute_a2a_task") as mock_task:
        mock_task.apply_async = MagicMock()
        async with client as c:
            resp = await c.post("/tasks", json={"method": "tasks/send", "params": {}})

    assert resp.status_code == 202
    body = resp.json()
    assert body["status"] == TaskStatus.SUBMITTED
    assert "id" in body


@pytest.mark.asyncio
async def test_submit_uses_payload_id(client, store):
    with patch("adk_celery_broker.router.execute_a2a_task") as mock_task:
        mock_task.apply_async = MagicMock()
        async with client as c:
            resp = await c.post("/tasks", json={"id": "my-id-123"})

    assert resp.json()["id"] == "my-id-123"


@pytest.mark.asyncio
async def test_submit_persists_task_as_submitted(client, store):
    with patch("adk_celery_broker.router.execute_a2a_task") as mock_task:
        mock_task.apply_async = MagicMock()
        async with client as c:
            resp = await c.post("/tasks", json={"id": "t1"})

    task = await store.get("t1")
    assert task is not None
    assert task.status == TaskStatus.SUBMITTED


@pytest.mark.asyncio
async def test_submit_dispatches_to_celery(client, store):
    with patch("adk_celery_broker.router.execute_a2a_task") as mock_task:
        mock_task.apply_async = MagicMock()
        async with client as c:
            await c.post("/tasks", json={"id": "t1"})

    mock_task.apply_async.assert_called_once()
    args = mock_task.apply_async.call_args
    assert args.kwargs["task_id"] == "t1"


@pytest.mark.asyncio
async def test_submit_invalid_json_returns_400(client):
    async with client as c:
        resp = await c.post(
            "/tasks",
            content=b"not-json",
            headers={"Content-Type": "application/json"},
        )
    assert resp.status_code == 400


# ── GET /tasks/{task_id} ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_task_returns_status(client, store):
    await store.save(A2aTask(id="t1", status=TaskStatus.WORKING, payload={}))
    async with client as c:
        resp = await c.get("/tasks/t1")
    assert resp.status_code == 200
    assert resp.json()["status"] == TaskStatus.WORKING


@pytest.mark.asyncio
async def test_get_task_includes_result_when_complete(client, store):
    task = A2aTask(id="t1", status=TaskStatus.COMPLETED, payload={}, result={"ans": 1})
    await store.save(task)
    async with client as c:
        resp = await c.get("/tasks/t1")
    assert resp.json()["result"] == {"ans": 1}


@pytest.mark.asyncio
async def test_get_task_includes_error_when_failed(client, store):
    task = A2aTask(id="t1", status=TaskStatus.FAILED, payload={}, error="boom")
    await store.save(task)
    async with client as c:
        resp = await c.get("/tasks/t1")
    assert resp.json()["error"] == "boom"


@pytest.mark.asyncio
async def test_get_task_unknown_returns_404(client):
    async with client as c:
        resp = await c.get("/tasks/does-not-exist")
    assert resp.status_code == 404


# ── GET /tasks ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_tasks_empty(client):
    async with client as c:
        resp = await c.get("/tasks")
    assert resp.status_code == 200
    assert resp.json()["tasks"] == []


@pytest.mark.asyncio
async def test_list_tasks_returns_all(client, store):
    for i in range(3):
        await store.save(A2aTask(id=f"t{i}", status=TaskStatus.SUBMITTED, payload={}))
    async with client as c:
        resp = await c.get("/tasks")
    assert len(resp.json()["tasks"]) == 3
