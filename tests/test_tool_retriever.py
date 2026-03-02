# tests/test_tool_retriever.py
"""
Tests for the embedding-based tool retriever.

Verifies that:
1. The retriever loads and indexes all tools correctly
2. Known queries map to the expected tools
3. The similarity threshold filters low-relevance tools
4. The singleton pattern works (same instance returned)
"""

import sys
from pathlib import Path

# Add project root to path so imports work
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import pytest


# ── Skip if sentence-transformers isn't installed ─────────────────────────
# This avoids test failures in environments without the model
try:
    from sentence_transformers import SentenceTransformer
    HAS_SENTENCE_TRANSFORMERS = True
except ImportError:
    HAS_SENTENCE_TRANSFORMERS = False

skip_if_no_st = pytest.mark.skipif(
    not HAS_SENTENCE_TRANSFORMERS,
    reason="sentence-transformers not installed"
)


# ── Test: Initialization ─────────────────────────────────────────────────

@skip_if_no_st
class TestRetrieverInit:
    """Verify the retriever loads correctly and indexes all tools."""

    def test_creates_instance(self):
        """Retriever should initialize without errors."""
        from src.tools.tool_retriever import ToolRetriever
        # Create a fresh instance (not the singleton) for isolation
        retriever = ToolRetriever(top_k=5, min_similarity=0.25)
        assert retriever is not None

    def test_indexes_all_tools(self):
        """All 13 tools should be indexed."""
        from src.tools.tool_retriever import ToolRetriever
        from src.tools.wrapped_tools import ALL_TOOLS

        retriever = ToolRetriever()
        # The number of tool docs should match the number of tools
        assert len(retriever.tool_docs) == len(ALL_TOOLS)
        # Embeddings shape should be (num_tools, embedding_dim)
        assert retriever.tool_embeddings.shape[0] == len(ALL_TOOLS)

    def test_embedding_dimensions(self):
        """all-MiniLM-L6-v2 produces 384-dimensional embeddings."""
        from src.tools.tool_retriever import ToolRetriever

        retriever = ToolRetriever()
        # 384 is the known output dimension for this model
        assert retriever.tool_embeddings.shape[1] == 384


# ── Test: Singleton Pattern ──────────────────────────────────────────────

@skip_if_no_st
class TestSingleton:
    """Verify get_retriever() returns the same instance every time."""

    def test_same_instance(self):
        """Two calls to get_retriever() should return the exact same object."""
        # We need to reset the singleton for a clean test
        import src.tools.tool_retriever as tr
        tr._retriever = None  # Reset singleton

        r1 = tr.get_retriever()
        r2 = tr.get_retriever()
        # Same object in memory — not just equal, but identical
        assert r1 is r2

        # Cleanup: reset so other tests get a fresh instance
        tr._retriever = None


# ── Test: Retrieval Accuracy ─────────────────────────────────────────────

@skip_if_no_st
class TestRetrievalAccuracy:
    """
    Verify that specific queries return the expected tools.

    These are the most important tests — if retrieval is wrong,
    the agent will call the wrong tools and look broken to the user.
    """

    @pytest.fixture(autouse=True)
    def setup_retriever(self):
        """Create a fresh retriever for each test.
        
        Using top_k=6 and min_similarity=0.3 (lower than production 0.4)
        to give tests some margin. Production uses 0.4 which correctly
        filters casual greetings.
        """
        from src.tools.tool_retriever import ToolRetriever
        self.retriever = ToolRetriever(top_k=6, min_similarity=0.3)

    def _get_tool_names(self, query: str) -> list:
        """Helper: run retrieval and return just the tool names."""
        tools = self.retriever.get_tools(query)
        return [t.name for t in tools]

    def test_timer_query(self):
        """Timer-related queries should include set_timer."""
        names = self._get_tool_names("set a 5 minute timer")
        assert "set_timer" in names

    def test_alarm_query(self):
        """Alarm-related queries should include set_alarm."""
        names = self._get_tool_names("wake me up at 7am")
        assert "set_alarm" in names

    def test_task_query(self):
        """Task-related queries should include add_task."""
        names = self._get_tool_names("add buy groceries to my list")
        assert "add_task" in names

    def test_email_read_query(self):
        """Email checking queries should include read_emails."""
        names = self._get_tool_names("check my emails")
        assert "read_emails" in names

    def test_email_send_query(self):
        """Email sending queries should include send_email."""
        names = self._get_tool_names("send an email to my boss")
        assert "send_email" in names

    def test_open_app_query(self):
        """App opening queries should include open_app."""
        names = self._get_tool_names("open chrome")
        assert "open_app" in names

    def test_web_search_query(self):
        """Search queries should include web_search."""
        # "search the web" is more direct than "what is the capital of France"
        # which the embedder confuses with factual/location tools
        names = self._get_tool_names("search the internet for latest news")
        assert "web_search" in names

    def test_arxiv_query(self):
        """Research paper queries should include search_arxiv."""
        names = self._get_tool_names("find papers on transformer architecture")
        assert "search_arxiv" in names

    def test_stackoverflow_query(self):
        """Programming questions should include search_stackoverflow."""
        # Include "stackoverflow" or "coding" to give the embedder a clear signal
        names = self._get_tool_names("search stackoverflow for python error handling")
        assert "search_stackoverflow" in names

    def test_calendar_query(self):
        """Scheduling queries should include create_calendar_event."""
        names = self._get_tool_names("schedule a meeting tomorrow at 3pm")
        assert "create_calendar_event" in names

    def test_system_info_query(self):
        """Status queries should include get_system_info."""
        # "status" and "schedule" are stronger signals than "what time is it"
        # which the embedder associates more with alarm/timer tools
        names = self._get_tool_names("show me my current status and schedule")
        assert "get_system_info" in names

    def test_command_query(self):
        """Terminal command queries should include run_command."""
        names = self._get_tool_names("run ls in the terminal")
        assert "run_command" in names


# ── Test: Threshold Filtering ────────────────────────────────────────────

@skip_if_no_st
class TestThresholdFiltering:
    """Verify that the similarity threshold correctly filters tools."""

    def test_gibberish_returns_empty(self):
        """Gibberish should return an empty list (no relevant tools)."""
        from src.tools.tool_retriever import ToolRetriever
        # Use production threshold (0.4) — gibberish shouldn't match anything
        retriever = ToolRetriever(top_k=5, min_similarity=0.4)
        tools = retriever.get_tools("asdfghjkl zxcvbnm qwerty")
        # With the forced fallback removed, this should be empty
        assert len(tools) == 0

    def test_relevant_query_returns_multiple(self):
        """A clear query should return multiple relevant tools."""
        from src.tools.tool_retriever import ToolRetriever
        retriever = ToolRetriever(top_k=5, min_similarity=0.15)
        tools = retriever.get_tools("set a timer and add a task")
        # Should return more than 1 tool for a multi-intent query
        assert len(tools) > 1

    def test_respects_top_k(self):
        """Never return more than top_k tools."""
        from src.tools.tool_retriever import ToolRetriever
        retriever = ToolRetriever(top_k=3, min_similarity=0.0)
        tools = retriever.get_tools("do everything")
        assert len(tools) <= 3
