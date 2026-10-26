"""
Tsuzi agent core — LangGraph ReAct agent (V2).

LOCAL-FIRST CONTRACT: the text model runs on Ollama on the owner's
machine. Cloud vision (NVIDIA) is a separate, optional accelerator
used only by src/vision/screen_vision.py.

RESPONSIBILITIES:
- Build and cache the ReAct agent (ChatOllama + wrapped tools + MemorySaver)
- Refresh long-term memory into the system prompt on every query
- Keep short-term history per thread_id (terminal, each Telegram chat, digest)
- Print the concise debug trace and append JSONL records to
  logs/agent_traces/agent_trace_YYYYMMDD.jsonl
"""

import json
import logging
import os
import re
import time
from datetime import datetime, timedelta

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.messages import trim_messages
from langchain_ollama import ChatOllama
from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import create_react_agent

from src.tools.wrapped_tools import ALL_TOOLS
from src.utils.config import Config
from src.utils.redaction import (
    MAX_ARG_LEN,
    MAX_QUERY_LEN,
    MAX_RESPONSE_LEN,
    MAX_RESULT_LEN,
    redact_string,
    redact_value,
)

logger = logging.getLogger(__name__)

MEMORY_DIR = Config.MEMORY_DIR
os.makedirs(MEMORY_DIR, exist_ok=True)

checkpointer = MemorySaver()

BASE_SYSTEM_PROMPT = """Your name is Tsuzi. You are a warm, cheerful AI assistant.
Address the user as "master".

CAPABILITIES — use the provided tools for these:
- Alarms and reminders
- Calendar events and Google Tasks
- Email (send, read, search)
- Web search
- Long-term memory about the user
- PC control: open/close/focus apps, windows, volume, brightness,
  screenshots, mouse and keyboard
- Screen vision: find and click UI elements by description, read the screen

RULES:
- For any action above, ALWAYS call the appropriate tool.
- For casual conversation, respond directly without tools.
- Be concise — responses are read aloud via TTS or sent as chat messages.
- Be warm and playful. Address the user as "master".
- If a tool fails or is unavailable, tell the user briefly.
- Never invent tool results.
"""


def _build_system_prompt_with_memory() -> str:
    """Base prompt plus a freshly read long-term memory section.

    Called on every query (dynamic prompt), so memories saved mid-session
    appear in the next query without a restart.
    """
    prompt = BASE_SYSTEM_PROMPT
    try:
        from src.memory import LongTermMemory

        context = LongTermMemory().get_context_string()
        if context:
            prompt += "\n" + context
    except Exception as e:
        logger.warning("Could not load memory context: %s", e)
    return prompt


def _system_prompt_state(state: dict) -> list:
    """create_react_agent prompt callable — rebuilt per query for memory refresh."""
    return [{"role": "system", "content": _build_system_prompt_with_memory()}]


def _estimate_tokens(messages) -> int:
    total = 0
    for m in messages:
        content = m.content if hasattr(m, "content") else str(m)
        total += len(content) // 4 if content else 0
    return total


trimmer = trim_messages(
    max_tokens=6000,
    strategy="last",
    token_counter=_estimate_tokens,
    include_system=True,
    allow_partial=False,
    start_on="human",
)


def _trim_state(state: dict) -> dict:
    messages = state.get("messages", [])
    trimmed = trimmer.invoke(messages)
    return {"messages": trimmed}


llm = ChatOllama(
    model=Config.OLLAMA_MODEL,
    base_url=Config.OLLAMA_BASE_URL,
    temperature=0.3,
)

_agent = None


def _get_agent():
    global _agent
    if _agent is None:
        _agent = create_react_agent(
            model=llm,
            tools=ALL_TOOLS,
            checkpointer=checkpointer,
            prompt=_system_prompt_state,
            pre_model_hook=_trim_state,
        )
    return _agent


async def initialize_agent():
    """Eagerly build the agent at startup (called by src.main)."""
    _prune_old_traces()
    _get_agent()
    logger.info(
        "Agent initialized with MemorySaver (model=%s at %s)",
        Config.OLLAMA_MODEL,
        Config.OLLAMA_BASE_URL,
    )


# ── Debug tracing ───────────────────────────────────────────────────────────


def _debug(source: str, thread_id: str, message: str):
    if Config.DEBUG_MODE:
        print(f"[debug][{source}][{thread_id[:8]}] {message}")


class _ToolTraceHandler(BaseCallbackHandler):
    """Live tool-call prints; best-effort, never breaks the agent run."""

    def __init__(self, source: str, thread_id: str):
        self.source = source
        self.thread_id = thread_id

    def on_tool_start(self, serialized, input_str, **kwargs):
        try:
            name = serialized.get("name", "tool") if isinstance(serialized, dict) else "tool"
            _debug(self.source, self.thread_id, f"Calling tool: {name} | args: {redact_string(str(input_str), 300)}")
        except Exception:
            pass

    def on_tool_end(self, output, **kwargs):
        try:
            _debug(self.source, self.thread_id, f"Tool result: -> {redact_string(str(output), 300)}")
        except Exception:
            pass


def _extract_tool_events(messages: list) -> tuple[list, list]:
    """Collect ordered tool calls and results from the final message list."""
    calls, results = [], []
    for m in messages:
        tool_calls = getattr(m, "tool_calls", None)
        if tool_calls:
            for tc in tool_calls:
                try:
                    args = tc.get("args", {})
                except Exception:
                    args = str(tc)
                calls.append({"name": tc.get("name", "tool"), "args": args})
        elif m.__class__.__name__ == "ToolMessage":
            content = m.content if isinstance(m.content, str) else str(m.content)
            results.append({"name": getattr(m, "name", "tool"), "result": content[:2000]})
    return calls, results


def _write_trace_record(record: dict):
    """Redact + bound one record, append it to today's JSONL, prune old files.

    Redaction happens at this single choke point so every trace writer is
    covered (ADR 0001): secrets are scrubbed and long values bounded, while
    diagnostic fields (tool names, duration_s, thread_id) stay intact.
    """
    record["query"] = redact_value(record.get("query"), MAX_QUERY_LEN)
    record["tool_calls"] = redact_value(record.get("tool_calls"), MAX_ARG_LEN)
    record["tool_results"] = redact_value(record.get("tool_results"), MAX_RESULT_LEN)
    record["final_response"] = redact_value(record.get("final_response"), MAX_RESPONSE_LEN)
    record["error"] = redact_value(record.get("error"), MAX_RESULT_LEN)
    try:
        os.makedirs(Config.DEBUG_LOG_DIR, exist_ok=True)
        path = os.path.join(
            Config.DEBUG_LOG_DIR, f"agent_trace_{datetime.now().strftime('%Y%m%d')}.jsonl"
        )
        line = json.dumps(record, ensure_ascii=False, default=str) + "\n"
        _rotate_trace_if_needed(path, len(line.encode("utf-8")))
        with open(path, "a", encoding="utf-8") as f:
            f.write(line)
    except OSError as e:
        logger.warning("Could not write agent trace: %s", e)
    _prune_old_traces()


def _rotate_trace_if_needed(path: str, incoming_bytes: int) -> None:
    """Rotate the current day's trace before it exceeds its size budget."""
    max_bytes = max(1, int(Config.TRACE_MAX_BYTES))
    if not os.path.exists(path) or os.path.getsize(path) + incoming_bytes <= max_bytes:
        return

    backup_count = max(0, int(Config.TRACE_BACKUP_COUNT))
    if backup_count == 0:
        os.remove(path)
        return

    stem, suffix = os.path.splitext(path)
    for index in range(backup_count, 0, -1):
        source = f"{stem}.{index}{suffix}"
        destination = f"{stem}.{index + 1}{suffix}"
        if os.path.exists(source):
            if index == backup_count:
                os.remove(source)
            else:
                os.replace(source, destination)
    os.replace(path, f"{stem}.1{suffix}")


def _prune_old_traces():
    """Delete agent_trace_*.jsonl files older than Config.TRACE_RETENTION_DAYS.

    Retention age comes from the YYYYMMDD in the filename; names that do not
    parse fall back to file mtime. Best-effort: never breaks trace writing.
    """
    try:
        cutoff = (datetime.now() - timedelta(days=Config.TRACE_RETENTION_DAYS)).date()
        for name in os.listdir(Config.DEBUG_LOG_DIR):
            if not (name.startswith("agent_trace_") and name.endswith(".jsonl")):
                continue
            full_path = os.path.join(Config.DEBUG_LOG_DIR, name)
            try:
                match = re.match(r"agent_trace_(\d{8})(?:\.\d+)?\.jsonl$", name)
                if not match:
                    raise ValueError("unparseable trace filename")
                file_date = datetime.strptime(match.group(1), "%Y%m%d").date()
            except ValueError:
                file_date = datetime.fromtimestamp(os.path.getmtime(full_path)).date()
            if file_date < cutoff:
                os.remove(full_path)
    except OSError as e:
        logger.warning("Could not prune old agent traces: %s", e)


def _final_text(messages: list) -> str:
    last = messages[-1] if messages else None
    if last is None:
        return "Sorry, I couldn't process that."
    content = getattr(last, "content", last)
    if isinstance(content, list):
        content = "\n".join(
            str(item.get("text", item)) if isinstance(item, dict) else str(item)
            for item in content
        )
    return str(content) if content else "Sorry, I couldn't process that."


def _run_config(thread_id: str, source: str) -> dict:
    return {
        "configurable": {"thread_id": thread_id},
        "recursion_limit": 15,
        "callbacks": [_ToolTraceHandler(source, thread_id)],
    }


def _summarize(user_input: str, thread_id: str, source: str, result, t_start: float, error=None) -> str:
    messages = result.get("messages", []) if isinstance(result, dict) else []
    calls, tool_results = _extract_tool_events(messages)
    final_response = _final_text(messages) if not error else None
    duration = round(time.perf_counter() - t_start, 3)

    _debug(source, thread_id, f"Query: {redact_string(user_input, 300)}")
    if error is None:
        _debug(source, thread_id, f"Final response: {redact_string(final_response, 300)}")

    _write_trace_record(
        {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "source": source,
            "thread_id": thread_id,
            "query": user_input,
            "tool_calls": calls,
            "tool_results": tool_results,
            "final_response": final_response,
            "duration_s": duration,
            "error": str(error) if error else None,
        }
    )
    return final_response


def run_agent(user_input: str, thread_id: str = "", source: str = "unknown") -> str:
    if not thread_id:
        thread_id = f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    t_start = time.perf_counter()
    try:
        result = _get_agent().invoke(
            {"messages": [{"role": "user", "content": user_input}]},
            _run_config(thread_id, source),
        )
        return _summarize(user_input, thread_id, source, result, t_start)
    except Exception as e:
        logger.error("Agent error: %s", e)
        _summarize(user_input, thread_id, source, {}, t_start, error=e)
        return "Sorry, something went wrong. Please try again."


async def arun_agent(user_input: str, thread_id: str = "", source: str = "unknown") -> str:
    if not thread_id:
        thread_id = f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    t_start = time.perf_counter()
    try:
        result = await _get_agent().ainvoke(
            {"messages": [{"role": "user", "content": user_input}]},
            _run_config(thread_id, source),
        )
        return _summarize(user_input, thread_id, source, result, t_start)
    except Exception as e:
        logger.error("Async agent error: %s", e)
        _summarize(user_input, thread_id, source, {}, t_start, error=e)
        return "Sorry, something went wrong."
