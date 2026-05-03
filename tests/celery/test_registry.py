import pytest
from adk_persistence.celery.registry import AgentRegistry


@pytest.fixture
def reg():
    return AgentRegistry()


def test_register_and_get(reg):
    af, sf, tf = lambda: "a", lambda: "s", lambda: "t"
    reg.register("a1", af, sf, tf)
    assert reg.get("a1") == (af, sf, tf)


def test_register_without_task_store(reg):
    reg.register("a1", lambda: None, lambda: None)
    _, _, tf = reg.get("a1")
    assert tf is None


def test_unknown_agent_raises(reg):
    with pytest.raises(KeyError, match="'x'"):
        reg.get("x")


def test_clear(reg):
    reg.register("a1", lambda: None, lambda: None)
    reg._clear()
    with pytest.raises(KeyError):
        reg.get("a1")
