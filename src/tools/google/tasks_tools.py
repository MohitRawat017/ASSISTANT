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
    try:
        service = get_tasks_service()
        
        # Build task object
        body = {"title": title}
        if notes:
            body["notes"] = notes
        if due:
            body["due"] = due

        # Insert into default tasklist
        task = service.tasks().insert(
            tasklist="@default",  # User's main task list
            body=body
        ).execute()
        
        return {"success": True, "task_id": task.get("id", "")}
    except Exception as e:
        return {"success": False, "error": str(e)}


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
        result = (
            service.tasks()
            .list(
                tasklist="@default",
                showCompleted=show_completed
            )
            .execute()
        )

        tasks = []
        for item in result.get("items", []):
            tasks.append(
                {
                    "id": item.get("id", ""),
                    "title": item.get("title", "(no title)"),
                    "notes": item.get("notes", ""),
                    "due": item.get("due", ""),
                    "status": item.get("status", "needsAction"),
                }
            )
        return {"success": True, "tasks": tasks}
    except Exception as e:
        # HttpError.reason is the short API message; str(e) dumps the whole blob
        reason = getattr(e, "reason", None) or str(e)
        return {"success": False, "error": str(reason)[:200]}


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
    try:
        service = get_tasks_service()
        
        service.tasks().patch(
            tasklist="@default",
            task=task_id,
            body={"status": "completed"}
        ).execute()
        
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}


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
    try:
        service = get_tasks_service()
        service.tasks().delete(
            tasklist="@default",
            task=task_id
        ).execute()
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}
