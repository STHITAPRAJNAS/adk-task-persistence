import warnings

import pytest
from fastapi import FastAPI

from adk_celery_broker.executor import get_fastapi_app, _resolve_task_store
from adk_celery_broker.registry import AgentRegistry
from adk_celery_broker.task_store import BaseA2aTaskStore, InMemoryA2aTaskStore


@pytest.fixture(autouse=True)
def isolated_registry(monkeypatch):
    """Give each test its own clean registry so they don't share state."""
    reg = AgentRegistry()
    import adk_celery_broker.executor as mod
    monkeypatch.setattr(mod, "registry", reg)
    return reg


def test_get_fastapi_app_returns_fastapi_instance():
    store = InMemoryA2aTaskStore()
    app = get_fastapi_app(agent_id="x", task_store=store)
    assert isinstance(app, FastAPI)


def test_get_fastapi_app_uses_provided_task_store():
    store = InMemoryA2aTaskStore()
    resolved = _resolve_task_store("x", store)
    assert resolved is store


def test_get_fastapi_app_falls_back_to_registry(isolated_registry):
    custom_store = InMemoryA2aTaskStore()
    isolated_registry.register(
        "a1",
        agent_factory=lambda: None,
        session_service_factory=lambda: None,
        task_store_factory=lambda: custom_store,
    )
    resolved = _resolve_task_store("a1", None)
    assert resolved is custom_store


def test_get_fastapi_app_warns_and_uses_inmemory_when_no_store():
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        resolved = _resolve_task_store("unknown_agent", None)

    assert isinstance(resolved, InMemoryA2aTaskStore)
    assert any("InMemoryA2aTaskStore" in str(w.message) for w in caught)


def test_get_fastapi_app_accepts_fastapi_kwargs():
    store = InMemoryA2aTaskStore()
    app = get_fastapi_app(
        agent_id="x",
        task_store=store,
        title="Custom Title",
        version="9.9.9",
    )
    assert app.title == "Custom Title"
    assert app.version == "9.9.9"


def test_routes_are_registered():
    store = InMemoryA2aTaskStore()
    app = get_fastapi_app(agent_id="x", task_store=store)
    paths = {r.path for r in app.routes}
    assert "/tasks" in paths
    assert "/tasks/{task_id}" in paths
