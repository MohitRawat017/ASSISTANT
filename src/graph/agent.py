import os
import sqlite3
import logging
from datetime import datetime
from dotenv import load_dotenv
load_dotenv()

from langchain_ollama import ChatOllama
from langchain_groq import ChatGroq
from langchain_core.messages import trim_messages
from langgraph.prebuilt import create_react_agent
from langgraph.checkpoint.sqlite import SqliteSaver

from src.tools.tool_retriever import get_retriever
from src.utils.config import Config

logger = logging.getLogger(__name__)

# ── Config from environment ──────────────────────────
# Issue #7 fix: model name in env so you can switch without editing code.
# Set OLLAMA_MODEL in .env to override. Default: qwen2.5:7b
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:7b")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

MEMORY_DIR = Config.MEMORY_DIR
os.makedirs(MEMORY_DIR, exist_ok=True)

SYSTEM_PROMPT = """Your name is Tsuzi. You are a warm, cheerful AI assistant.
Address the user as "master".

CAPABILITIES — use the provided tools for these:
- Timers and alarms
- Calendar events and reminders  
- Task management
- Web search, arXiv, Stack Overflow
- Email (send and read)
- Open apps and terminal commands

RULES:
- For any action above, ALWAYS call the appropriate tool. Never describe what you would do.
- For casual conversation, respond directly without tools.
- Be concise — responses are read aloud via TTS. One or two sentences max.
- Be warm, curious, and playful. Address the user as "master".
- If a tool fails, tell the user briefly and suggest an alternative.
"""

# ── Issue #6 fix: Ollama health check ─────────────────
# Validate the server is reachable at startup so we get a clear error
# instead of a confusing crash deep inside invoke().
def _check_ollama():
    """Quick health check — warns if Ollama is unreachable."""
    import requests
    try:
        resp = requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=3)
        if resp.status_code == 200:
            logger.info(f"✅ Ollama connected at {OLLAMA_BASE_URL}")
        else:
            logger.warning(f"⚠️ Ollama returned status {resp.status_code}")
    except requests.ConnectionError:
        logger.warning(
            f"⚠️ Cannot reach Ollama at {OLLAMA_BASE_URL}. "
            "Make sure Ollama is running (ollama serve)."
        )
    except Exception as e:
        logger.warning(f"⚠️ Ollama check failed: {e}")

_check_ollama()

# ── LLM ──────────────────────────────────────────────
# llm = ChatOllama(
#     model=OLLAMA_MODEL,
#     temperature=0.3,
#     base_url=OLLAMA_BASE_URL,
# )

llm = ChatGroq(
    model="llama-3.3-70b-versatile",
    temperature=0.3,
    api_key=Config.GROQ_API_KEY,
)

# ── Memory ───────────────────────────────────────────
_conn = sqlite3.connect(
    os.path.join(MEMORY_DIR, "short_term.db"),
    check_same_thread=False
)
checkpointer = SqliteSaver(conn=_conn)

# ── Session thread ID ────────────────────────────────
# Each app launch gets a unique thread_id so stale tool_calls from
# a previous crashed/interrupted session don't cause INVALID_CHAT_HISTORY.
SESSION_THREAD_ID = f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

# ── Issue #5 fix: Token-estimate based trimming ──────
# Previous approach: token_counter=len counted MESSAGES (so max_tokens=10
# meant "keep 10 messages"). This is fragile — tool calls add multiple
# messages per turn, so 10 messages might only be 2-3 actual exchanges.
#
# Better approach: estimate tokens as len(content)//4 (rough 4-chars-per-token
# heuristic). max_tokens=4000 gives ~16K chars of context, which is safe
# for qwen2.5:7b's 32K context window while leaving room for the system
# prompt and tool schemas.
def _estimate_tokens(messages) -> int:
    """Rough token count: ~4 characters per token."""
    total = 0
    for m in messages:
        # Some messages have string content, some have structured content
        content = m.content if hasattr(m, "content") else str(m)
        total += len(content) // 4 if content else 0
    return total

trimmer = trim_messages(
    max_tokens=6000,              # ~24K chars of context (increased from 4000)
    strategy="last",              # keep the most recent messages
    token_counter=_estimate_tokens,
    include_system=True,          # always keep the system prompt
    allow_partial=False,          # don't truncate mid-message
    start_on="human",             # ensure context starts on a user message
)

# ── Issue #1 fix: Wrap trimmer for pre_model_hook ────
# pre_model_hook receives the full LangGraph STATE DICT (not a message list).
# trim_messages only works on message lists. So we extract messages from
# the state, trim them, and put them back. Without this wrapper, passing
# the raw trimmer causes:
#   "Expected dict, got [HumanMessage(content='messages', ...)]"
def _trim_state(state: dict) -> dict:
    """
    Trim the message history inside the agent state dict.

    pre_model_hook contract:
    - Receives: full state dict with 'messages' key
    - Must return: a dict (modified state)

    We extract just the messages, run the trimmer on them,
    and return ONLY the trimmed messages key.
    
    FIX: Previously returned {**state, "messages": trimmed} which spread
    all state keys including internal LangGraph keys like 'remaining_steps'.
    This caused the warning: "wrote to unknown channel remaining_steps".
    By returning only {"messages": trimmed}, we avoid writing to channels
    that don't exist in the graph definition.
    """
    messages = state.get("messages", [])
    trimmed = trimmer.invoke(messages)
    return {"messages": trimmed}


def _get_recent_messages(thread_id: str, limit: int = 3) -> list:
    """
    Fetch recent messages from the conversation history for context-aware retrieval.
    
    This helps the tool retriever understand follow-up queries like "yea" or "yes"
    by combining them with previous context.
    
    Args:
        thread_id: The conversation thread ID.
        limit: Max number of recent messages to return.
    
    Returns:
        List of message content strings (user and assistant messages).
    """
    try:
        # Get the current state from checkpointer
        config = {"configurable": {"thread_id": thread_id}}
        state = checkpointer.get(config)
        
        if not state or "messages" not in state:
            return []
        
        messages = state["messages"]
        recent = []
        
        # Get last N messages (both user and assistant)
        for msg in messages[-(limit * 2):]:
            if hasattr(msg, "content"):
                content = msg.content if isinstance(msg.content, str) else str(msg.content)
                role = "user" if msg.__class__.__name__ == "HumanMessage" else "assistant"
                recent.append(f"{role}: {content}")
        
        return recent[-limit:] if recent else []
    except Exception as e:
        logger.debug(f"Failed to get recent messages: {e}")
        return []


def _get_agent(tools: list):
    """
    Build a ReAct agent with a specific set of tools.

    API usage (langgraph 1.0.9):
    - prompt=SYSTEM_PROMPT → string becomes system message for the LLM,
      so it knows to respond directly for casual conversation.
    - pre_model_hook=_trim_state → our wrapper function that trims
      message history. Receives/returns state dicts (not message lists).
    - If no tools are provided (e.g., for a casual greeting), we still
      create the agent — it will just respond without tool calls.
    """
    return create_react_agent(
        model=llm,
        tools=tools,
        checkpointer=checkpointer,
        prompt=SYSTEM_PROMPT,
        pre_model_hook=_trim_state,
    )


def run_agent(user_input: str, thread_id: str = "") -> str:
    """
    Process a user message and return the assistant's response.

    Flow:
    1. Get conversation history for context-aware retrieval
    2. Retrieve relevant tools via embedding similarity
    3. Build a ReAct agent with those tools (may be empty for casual chat)
    4. Invoke the agent with the user message
    5. Return the final response text
    """
    if not thread_id:
        thread_id = SESSION_THREAD_ID

    # Get conversation history for context-aware tool retrieval
    # This helps match follow-up queries like "yea" to the previous tool
    conversation_history = _get_recent_messages(thread_id, limit=3)
    
    # Get tools matched to this specific query via embeddings.
    # Pass conversation history for context-aware retrieval.
    retriever = get_retriever()
    tools = retriever.get_tools(user_input, conversation_history=conversation_history)
    agent = _get_agent(tools)

    config = {
        "configurable": {"thread_id": thread_id},
        "recursion_limit": 15,  # Increased from 8 to see what's looping
    }

    try:
        result = agent.invoke(
            {"messages": [{"role": "user", "content": user_input}]},
            config
        )
        messages = result.get("messages", [])

        last = messages[-1] if messages else None
        if last and hasattr(last, "usage_metadata") and last.usage_metadata:
            u = last.usage_metadata
            print(f"🔢 Tokens — in: {u.get('input_tokens', '?')} | out: {u.get('output_tokens', '?')}")

        return last.content if last else "Sorry, I couldn't process that."

    except Exception as e:
        print(f"❌ Agent error: {e}")
        return "Sorry, something went wrong. Please try again."


async def arun_agent(user_input: str, thread_id: str = "") -> str:
    """
    Async version of run_agent — same logic, but uses ainvoke().
    Used when the caller is already in an async context (e.g., websocket handler).
    """
    if not thread_id:
        thread_id = SESSION_THREAD_ID

    # Get conversation history for context-aware tool retrieval
    conversation_history = _get_recent_messages(thread_id, limit=3)
    
    retriever = get_retriever()
    tools = retriever.get_tools(user_input, conversation_history=conversation_history)
    agent = _get_agent(tools)

    config = {
        "configurable": {"thread_id": thread_id},
        "recursion_limit": 15,  # Increased from 8
    }

    try:
        result = await agent.ainvoke(
            {"messages": [{"role": "user", "content": user_input}]},
            config
        )
        messages = result.get("messages", [])
        last = messages[-1] if messages else None
        return last.content if last else "Sorry, I couldn't process that."

    except Exception as e:
        print(f"❌ Async agent error: {e}")
        return "Sorry, something went wrong."