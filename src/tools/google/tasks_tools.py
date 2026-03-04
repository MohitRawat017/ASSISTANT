"""
Google Tasks raw functions.
No @tool decorators — those live in wrapped_tools.py.
"""

from src.tools.google.auth import get_tasks_service


def add_google_task(title: str, notes: str = "", due: str = None) -> dict:
    """
    Adds a task to the default Google Tasks list.

    Args:
        title: Task title.
        notes: Optional notes/description.
        due: Optional due date in ISO format "2025-03-15T00:00:00.000Z"

    Returns:
        {"success": True, "task_id": "..."}
    """
    try:
        service = get_tasks_service()
        body = {"title": title}
        if notes:
            body["notes"] = notes
        if due:
            body["due"] = due

        task = service.tasks().insert(tasklist="@default", body=body).execute()
        return {"success": True, "task_id": task.get("id", "")}
    except Exception as e:
        return {"success": False, "error": str(e)}


def get_google_tasks(show_completed: bool = False) -> list:
    """
    Returns tasks from the default Google Tasks list.

    Returns:
        list of {"id", "title", "notes", "due", "status"}
    """
    try:
        service = get_tasks_service()
        result = (
            service.tasks()
            .list(tasklist="@default", showCompleted=show_completed)
            .execute()
        )
        tasks = []
        for item in result.get("items", []):
            if not show_completed and item.get("status") == "completed":
                continue
            tasks.append(
                {
                    "id": item.get("id", ""),
                    "title": item.get("title", "(no title)"),
                    "notes": item.get("notes", ""),
                    "due": item.get("due", ""),
                    "status": item.get("status", "needsAction"),
                }
            )
        return tasks
    except Exception as e:
        return []


def complete_google_task(task_id: str) -> dict:
    """
    Marks a task as completed.

    Returns:
        {"success": True/False}
    """
    try:
        service = get_tasks_service()
        service.tasks().patch(
            tasklist="@default", task=task_id, body={"status": "completed"}
        ).execute()
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}


def delete_google_task(task_id: str) -> dict:
    """
    Deletes a task by ID.

    Returns:
        {"success": True/False}
    """
    try:
        service = get_tasks_service()
        service.tasks().delete(tasklist="@default", task=task_id).execute()
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}
