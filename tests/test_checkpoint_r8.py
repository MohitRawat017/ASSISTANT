"""Deterministic R8 SQLite checkpoint coverage."""

import asyncio

import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langgraph.prebuilt import create_react_agent

from src.graph.checkpoint import PersistentSqliteSaver


class _DeterministicModel(BaseChatModel):
    @property
    def _llm_type(self):
        return "deterministic-test-model"

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        return ChatResult(
            generations=[ChatGeneration(message=AIMessage(content="ack"))]
        )


def _checkpoint(checkpoint_id: str, message: str) -> dict:
    return {
        "v": 1,
        "id": checkpoint_id,
        "ts": "2026-10-27T00:00:00+00:00",
        "channel_values": {"messages": [message]},
        "channel_versions": {"messages": 1},
        "versions_seen": {},
        "updated_channels": ["messages"],
    }


def _config(thread_id: str) -> dict:
    return {"configurable": {"thread_id": thread_id, "checkpoint_ns": ""}}


@pytest.mark.safe_smoke
def test_checkpoint_survives_new_saver_instance_and_isolates_threads(tmp_path):
    path = str(tmp_path / "checkpoints.db")
    saver = PersistentSqliteSaver(path)
    saver.put(_config("terminal"), _checkpoint("cp-1", "hello"), {"source": "input"}, {})
    saver.close()

    restarted = PersistentSqliteSaver(path)
    assert restarted.get_tuple(_config("terminal")).checkpoint["channel_values"]["messages"] == ["hello"]
    assert restarted.get_tuple(_config("telegram")) is None
    restarted.close()


@pytest.mark.safe_smoke
def test_async_checkpoint_methods_share_the_same_store(tmp_path):
    path = str(tmp_path / "checkpoints.db")
    saver = PersistentSqliteSaver(path)

    async def exercise():
        await saver.aput(_config("telegram"), _checkpoint("cp-1", "voice"), {"source": "input"}, {})
        value = await saver.aget_tuple(_config("telegram"))
        assert value is not None
        assert value.checkpoint["channel_values"]["messages"] == ["voice"]
        rows = [row async for row in saver.alist(_config("telegram"))]
        assert len(rows) == 1

    asyncio.run(exercise())
    saver.close()


@pytest.mark.safe_smoke
def test_clear_thread_removes_only_requested_thread(tmp_path):
    from src.graph import agent

    path = str(tmp_path / "checkpoints.db")
    saver = PersistentSqliteSaver(path)
    saver.put(_config("keep"), _checkpoint("cp-keep", "keep"), {"source": "input"}, {})
    saver.put(_config("clear"), _checkpoint("cp-clear", "clear"), {"source": "input"}, {})
    previous = agent.checkpointer
    agent.checkpointer = saver
    try:
        assert agent.clear_thread("clear") is True
        assert saver.get_tuple(_config("clear")) is None
        assert saver.get_tuple(_config("keep")) is not None
    finally:
        agent.checkpointer = previous
        saver.close()


@pytest.mark.safe_smoke
def test_langgraph_restart_resumes_same_thread(tmp_path):
    path = str(tmp_path / "checkpoints.db")
    config = _config("restartable")

    first_saver = PersistentSqliteSaver(path)
    first_graph = create_react_agent(_DeterministicModel(), [], checkpointer=first_saver)
    first_graph.invoke({"messages": [{"role": "user", "content": "first"}]}, config)
    first_saver.prune(["restartable"], strategy="keep_latest")
    first_saver.close()

    second_saver = PersistentSqliteSaver(path)
    second_graph = create_react_agent(_DeterministicModel(), [], checkpointer=second_saver)
    result = second_graph.invoke({"messages": [{"role": "user", "content": "second"}]}, config)
    assert [message.content for message in result["messages"] if hasattr(message, "content")].count("first") == 1
    assert [message.content for message in result["messages"] if hasattr(message, "content")].count("second") == 1
    second_saver.close()
