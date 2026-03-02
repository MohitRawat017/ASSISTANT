import os
import sqlite3
import logging
from datetime import datetime
from dotenv import load_dotenv
load_dotenv()

from langchain_groq import ChatGroq
from langchain_core.messages import trim_messages
from langgraph.prebuilt import create_react_agent
from langgraph.checkpoint.sqlite import SqliteSaver

from src.tools.tool_retriever import get_retriever
from src.utils.config import Config

logger = logging.getLogger(__name__)

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
- For any action above, ALWAYS call the appropriate tool.
- For casual conversation, respond directly without tools.
- Be concise — responses are read aloud via TTS.
- Be warm and playful. Address the user as "master".
- If a tool fails, tell the user briefly.
"""

llm = ChatGroq(
    model="llama-3.3-70b-versatile",
    temperature=0.3,
    api_key=Config.GROQ_API_KEY,
)

_conn = sqlite3.connect(os.path.join(MEMORY_DIR, "short_term.db"), check_same_thread=False)
checkpointer = SqliteSaver(conn=_conn)

SESSION_THREAD_ID = f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}"


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


def _get_recent_messages(thread_id: str, limit: int = 3) -> list:
    try:
        config = {"configurable": {"thread_id": thread_id}}
        state = checkpointer.get(config)
        if not state or "messages" not in state:
            return []
        recent = []
        for msg in state["messages"][-(limit * 2):]:
            if hasattr(msg, "content"):
                content = msg.content if isinstance(msg.content, str) else str(msg.content)
                role = "user" if msg.__class__.__name__ == "HumanMessage" else "assistant"
                recent.append(f"{role}: {content}")
        return recent[-limit:] if recent else []
    except Exception:
        return []


def _get_agent(tools: list):
    return create_react_agent(
        model=llm,
        tools=tools,
        checkpointer=checkpointer,
        prompt=SYSTEM_PROMPT,
        pre_model_hook=_trim_state,
    )


def run_agent(user_input: str, thread_id: str = "") -> str:
    if not thread_id:
        thread_id = SESSION_THREAD_ID

    conversation_history = _get_recent_messages(thread_id, limit=3)
    retriever = get_retriever()
    tools = retriever.get_tools(user_input, conversation_history=conversation_history)
    agent = _get_agent(tools)

    config = {
        "configurable": {"thread_id": thread_id},
        "recursion_limit": 15,
    }

    try:
        result = agent.invoke({"messages": [{"role": "user", "content": user_input}]}, config)
        messages = result.get("messages", [])
        last = messages[-1] if messages else None
        return last.content if last else "Sorry, I couldn't process that."
    except Exception as e:
        logger.error(f"Agent error: {e}")
        return "Sorry, something went wrong. Please try again."


async def arun_agent(user_input: str, thread_id: str = "") -> str:
    if not thread_id:
        thread_id = SESSION_THREAD_ID

    conversation_history = _get_recent_messages(thread_id, limit=3)
    retriever = get_retriever()
    tools = retriever.get_tools(user_input, conversation_history=conversation_history)
    agent = _get_agent(tools)

    config = {
        "configurable": {"thread_id": thread_id},
        "recursion_limit": 15,
    }

    try:
        result = await agent.ainvoke({"messages": [{"role": "user", "content": user_input}]}, config)
        messages = result.get("messages", [])
        last = messages[-1] if messages else None
        return last.content if last else "Sorry, I couldn't process that."
    except Exception as e:
        logger.error(f"Async agent error: {e}")
        return "Sorry, something went wrong."