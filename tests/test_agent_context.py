import pytest

from langgraph_mini.agent.context import MissingContextError, get_context


def test_get_context_extracts_requester_id_and_thread_id():
    config = {"configurable": {"requester_id": "u1", "thread_id": "t1"}}

    ctx = get_context(config)

    assert ctx.requester_id == "u1"
    assert ctx.thread_id == "t1"


def test_get_context_raises_when_requester_id_missing():
    config = {"configurable": {"thread_id": "t1"}}

    with pytest.raises(MissingContextError):
        get_context(config)


def test_get_context_raises_when_configurable_missing():
    with pytest.raises(MissingContextError):
        get_context({})
