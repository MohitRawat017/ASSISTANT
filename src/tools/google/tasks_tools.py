"""
================================================================================
GOOGLE TASKS API TOOLS
================================================================================

Raw functions for Google Tasks operations. Google Tasks is a simple task
management system integrated with Gmail and Google Calendar.

KEY CONCEPTS:
=============
- Tasklist: A collection of tasks (like a project)
- Task: An individual to-do item
- Default tasklist: "@default" - the user's main task list

WHY GOOGLE TASKS?
=================
- Integrated with Google ecosystem
- Syncs across devices
- Simple and lightweight
- API is straightforward

API DOCUMENTATION:
==================
https://developers.google.com/tasks/reference/rest
"""

from src.tools.google.auth import get_tasks_service
from src.utils.config import Config
from src.utils.reliability import execute_google_read, execute_google_write, failure_result, stable_operation_id


def add_google_task(title: str, notes: str = "", due: str | None = None) -> dict:
    """
    Adds a task to the default Google Tasks list.
    
    DUE DATE FORMAT:
    ================
    Google Tasks expects ISO 8601 format with timezone:
    "2025-03-15T00:00:00.000Z" (UTC)
    
    The wrapper in wrapped_tools.py converts "YYYY-MM-DD" to this format.
    
    Args:
        title: Task title (required)
        notes: Optional notes/description
        due: Optional due date in ISO format
        
    Returns:
        {"success": True, "task_id": "..."} on success
        {"success": False, "error": "..."} on failure
    """
    operation_id = stable_operation_id("tasks", "add")
    try:
        service = get_tasks_service()
        
        # Build task object
        body = {"title": title}
        if notes:
            body["notes"] = notes
        if due:
            body["due"] = due

        # Insert into default tasklist
        result = execute_google_write(
            lambda: service.tasks().insert(tasklist="@default", body=body),
            provider="tasks",
            operation_id=operation_id,
        )
        if result.ok:
            result["task_id"] = result.pop("value", {}).get("id", "")
        return result
    except Exception as e:
        return failure_result(e, provider="tasks", operation_id=operation_id)


def get_google_tasks(show_completed: bool = False) -> dict:
    """
    Returns tasks from the default Google Tasks list.

    STATUS VALUES:
    ==============
    - "needsAction": Task is pending
    - "completed": Task is done

    Args:
        show_completed: Whether to include completed tasks

    Returns:
        {"success": True, "tasks": [...]} on success, where each task has:
        id, title, notes, due, status
        {"success": False, "error": "..."} on failure
    """
    try:
        service = get_tasks_service()

        # Fetch tasks; showCompleted=False excludes completed tasks server-side
        result = execute_google_read(
            lambda: service.tasks().list(
                tasklist="@default",
                showCompleted=show_completed
            ),
            operation_id=stable_operation_id("tasks", "list", str(show_completed)),
            max_retries=Config.GOOGLE_MAX_RETRIES,
        )
        if not result.ok:
            return result
        payload = result.pop("value", {})
        tasks = []
        for item in payload.get("items", []):
            tasks.append(
                {
                    "id": item.get("id", ""),
                    "title": item.get("title", "(no title)"),
                    "notes": item.get("notes", ""),
                    "due": item.get("due", ""),
                    "status": item.get("status", "needsAction"),
                }
            )
        result["tasks"] = tasks
        return result
    except Exception as e:
        return failure_result(e, provider="tasks", operation_id=stable_operation_id("tasks", "list"))


def complete_google_task(task_id: str) -> dict:
    """
    Marks a task as completed.
    
    HOW IT WORKS:
    =============
    Updates the task status from "needsAction" to "completed".
    Google Tasks automatically sets the completed timestamp.
    
    Args:
        task_id: Google Task ID
        
    Returns:
        {"success": True} on success
        {"success": False, "error": "..."} on failure
    """
    operation_id = stable_operation_id("tasks", "complete")
    try:
        service = get_tasks_service()
        
        return execute_google_write(
            lambda: service.tasks().patch(
                tasklist="@default", task=task_id, body={"status": "completed"}
            ),
            provider="tasks",
            operation_id=operation_id,
        )
    except Exception as e:
        return failure_result(e, provider="tasks", operation_id=operation_id)


def delete_google_task(task_id: str) -> dict:
    """
    Deletes a task by ID.
    
    WARNING:
    ========
    This is permanent - cannot be undone.
    Consider using complete_task instead of delete for most cases.
    
    Args:
        task_id: Google Task ID
        
    Returns:
        {"success": True} on success
        {"success": False, "error": "..."} on failure
    """
    operation_id = stable_operation_id("tasks", "delete")
    try:
        service = get_tasks_service()
        return execute_google_write(
            lambda: service.tasks().delete(tasklist="@default", task=task_id),
            provider="tasks",
            operation_id=operation_id,
        )
    except Exception as e:
        return failure_result(e, provider="tasks", operation_id=operation_id)
