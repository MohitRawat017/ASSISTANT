import logging
from src.tools.pre_filter import is_casual_query
from src.tools.intent_router import predict_intent
from src.tools.tools_by_category import get_tools_for_category, get_tool_schemas
from src.tools.tool_router import predict_tool

logger = logging.getLogger(__name__)


def _get_llm_response(query: str) -> str:
    from src.graph.agent import run_agent
    return run_agent(query)


def _execute_tool(tool_name: str, tool_args: dict, category: str) -> str:
    tools = get_tools_for_category(category)
    tool_obj = next((t for t in tools if t.name == tool_name), None)

    if tool_obj is None:
        return f"Sorry, I couldn't find the tool '{tool_name}'."

    try:
        return str(tool_obj.invoke(tool_args))
    except Exception as e:
        return f"Tool failed: {str(e)[:200]}"


def route_query(query: str) -> str:
    # Layer 0: fast string-match for casual inputs, go straight to LLM
    if is_casual_query(query):
        return _get_llm_response(query)

    # Layer 1: MiniLM intent classification
    try:
        intent = predict_intent(query)
    except Exception as e:
        logger.error(f"MiniLM failed: {e}")
        return _get_llm_response(query)

    label = intent["label"]

    # If MiniLM says it's casual, let the LLM handle conversation
    if label == "casual":
        return _get_llm_response(query)

    # Layer 2: get the tool schemas for the detected category
    tool_schemas = get_tool_schemas(label)
    if not tool_schemas:
        return _get_llm_response(query)

    # Layer 3: FunctionGemma picks the exact tool + args
    try:
        tool_result = predict_tool(query, tool_schemas)
    except Exception as e:
        logger.error(f"FunctionGemma failed: {e}")
        return _get_llm_response(query)

    # Layer 4: execute the selected tool directly
    if tool_result is None:
        return _get_llm_response(query)

    return _execute_tool(tool_result["tool"], tool_result["args"], label)
