import pytest

from adk_celery_broker.registry import AgentRegistry


@pytest.fixture(autouse=True)
def fresh_registry():
    reg = AgentRegistry()
    yield reg


def test_register_and_get(fresh_registry):
    agent_f = lambda: "agent"
    session_f = lambda: "session"
    task_f = lambda: "store"

    fresh_registry.register("a1", agent_f, session_f, task_f)
    af, sf, tf = fresh_registry.get("a1")

    assert af is agent_f
    assert sf is session_f
    assert tf is task_f


def test_register_without_task_store_factory(fresh_registry):
    fresh_registry.register("a1", lambda: None, lambda: None)
    _, _, tf = fresh_registry.get("a1")
    assert tf is None


def test_get_unknown_agent_raises(fresh_registry):
    with pytest.raises(KeyError, match="'unknown'"):
        fresh_registry.get("unknown")


def test_register_overwrites_existing(fresh_registry):
    fresh_registry.register("a1", lambda: "v1", lambda: None)
    fresh_registry.register("a1", lambda: "v2", lambda: None)
    af, _, _ = fresh_registry.get("a1")
    assert af() == "v2"


def test_clear_removes_all(fresh_registry):
    fresh_registry.register("a1", lambda: None, lambda: None)
    fresh_registry._clear()
    with pytest.raises(KeyError):
        fresh_registry.get("a1")


def test_multiple_agents(fresh_registry):
    for i in range(3):
        fresh_registry.register(f"agent_{i}", lambda: i, lambda: None)
    for i in range(3):
        fresh_registry.get(f"agent_{i}")  # must not raise
