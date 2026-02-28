"""
LangGraph ReAct Agent - Uses Groq (llama-3.3-70b-versatile) for tool calling.
"""

import os
import sqlite3
import time
from dotenv import load_dotenv
load_dotenv()

from langchain_groq import ChatGroq
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent
from langgraph.checkpoint.sqlite import SqliteSaver

from src.tools.tool_group import get_tools_for_query
from src.utils.config import Config

MEMORY_DIR = os.path.join(Config.BASE_DIR, "data", "memory")
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

# Initialize components
# llm = ChatGroq(
#     model="llama-3.3-70b-versatile",
#     api_key=Config.GROQ_API_KEY,
#     temperature=0.3,
#     max_tokens=1024,
# )
llm = ChatOpenAI(
    model="meta-llama/llama-3.1-8b-instruct",
    base_url="https://openrouter.ai/api/v1",
    api_key=Config.OPENROUTER_API_KEY,
    temperature=0.3,
    max_tokens=1024,
)

_conn = sqlite3.connect(os.path.join(MEMORY_DIR, "short_term.db"), check_same_thread=False)
checkpointer = SqliteSaver(conn=_conn)

MAX_RETRIES = 1


def _is_tool_use_error(e: Exception) -> bool:
    """Check if an exception is a Groq tool_use_failed error (400)."""
    err_str = str(e).lower()
    return "tool_use_failed" in err_str or "failed_generation" in err_str


def _build_agent(tools: list):
    """Create a react agent with the given tool subset."""
    return create_react_agent(
        model=llm,
        tools=tools,
        checkpointer=checkpointer,
        prompt=SYSTEM_PROMPT,
    )


def run_agent(user_input: str, thread_id: str = "default") -> str:
    """Run the agent synchronously with dynamic tool selection."""
    tools = get_tools_for_query(user_input)
    agent = _build_agent(tools)
    config = {"configurable": {"thread_id": thread_id}}

    for attempt in range(MAX_RETRIES + 1):
        try:
            result = agent.invoke(
                {"messages": [{"role": "user", "content": user_input}]},
                config
            )
            messages = result.get("messages", [])
            return messages[-1].content if messages else "Sorry, I couldn't process that."
        except Exception as e:
            if _is_tool_use_error(e) and attempt < MAX_RETRIES:
                print(f"⚠️ Tool call failed (attempt {attempt + 1}/{MAX_RETRIES + 1}), retrying...")
                time.sleep(0.5)
                continue
            raise

    return "Sorry, I couldn't process that after multiple attempts."


async def arun_agent(user_input: str, thread_id: str = "default") -> str:
    """Run the agent asynchronously with dynamic tool selection."""
    import asyncio
    tools = get_tools_for_query(user_input)
    agent = _build_agent(tools)
    config = {"configurable": {"thread_id": thread_id}}

    for attempt in range(MAX_RETRIES + 1):
        try:
            result = await agent.ainvoke(
                {"messages": [{"role": "user", "content": user_input}]},
                config
            )
            messages = result.get("messages", [])
            return messages[-1].content if messages else "Sorry, I couldn't process that."
        except Exception as e:
            if _is_tool_use_error(e) and attempt < MAX_RETRIES:
                print(f"⚠️ Tool call failed (attempt {attempt + 1}/{MAX_RETRIES + 1}), retrying...")
                await asyncio.sleep(0.5)
                continue
            raise

    return "Sorry, I couldn't process that after multiple attempts."