from src.tools.wrapped_tools import (
    set_alarm, set_timer, add_task, get_tasks, create_calendar_event,
    open_app, run_command, get_system_info,
    web_search, search_stackoverflow, search_arxiv,
    send_email, read_emails,
)

TOOLS_BY_CATEGORY = {
    "productivity": [set_alarm, set_timer, add_task, get_tasks, create_calendar_event],
    "system":       [open_app, run_command, get_system_info],
    "research":     [web_search, search_stackoverflow, search_arxiv],
    "communication": [send_email, read_emails],
}

VALID_CATEGORIES = list(TOOLS_BY_CATEGORY.keys())


def get_tools_for_category(category: str) -> list:
    return TOOLS_BY_CATEGORY.get(category, [])


def get_tool_schemas(category: str) -> list:
    tools = get_tools_for_category(category)
    schemas = []

    for tool in tools:
        args_str = ""
        if hasattr(tool, "args_schema") and tool.args_schema:
            try:
                if hasattr(tool.args_schema, "model_json_schema"):
                    schema = tool.args_schema.model_json_schema()
                else:
                    schema = tool.args_schema.schema()

                props = schema.get("properties", {})
                if props:
                    parts = [f"{n} ({i.get('type', 'str')})" for n, i in props.items()]
                    args_str = ", ".join(parts)
            except Exception:
                pass

        schemas.append({
            "name": tool.name,
            "args": args_str,
            "description": tool.description[:100] if tool.description else "",
        })

    return schemas
