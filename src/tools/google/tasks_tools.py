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

================================================================================
KEY CONCEPTS FOR INTERVIEW:
================================================================================

Q: What is "@default" tasklist?
A: Every Google account has a default task list. Using "@default" as the
   tasklist ID refers to this main list without needing to know its actual ID.

================================================================================
"""

from src.tools.google.auth import get_tasks_service


def add_google_task(title: str, notes: str = "", due: str = None) -> dict:
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


def get_google_tasks(show_completed: bool = False) -> list:
    """
    Returns tasks from the default Google Tasks list.
    
    STATUS VALUES:
    ==============
    - "needsAction": Task is pending
    - "completed": Task is done
    
    Args:
        show_completed: Whether to include completed tasks
        
    Returns:
        List of task dicts with: id, title, notes, due, status
        Empty list on error
    """
    try:
        service = get_tasks_service()
        
        # Fetch tasks
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
            # Filter by status if not showing completed
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


# =============================================================================
# INTERVIEW QUESTIONS FOR THIS FILE
# =============================================================================
"""
Q1: What's the difference between tasklist and task?
A: Tasklist: A collection/container (like a project)
   Task: An individual to-do item within a tasklist
   
   A user can have multiple tasklists, but we use @default for simplicity.

Q2: Why use patch() instead of update() for completing tasks?
A: patch(): Updates only specified fields (partial update)
   update(): Replaces entire resource (full update)
   
   patch() is safer - won't accidentally overwrite other fields.

Q3: How would you create a new tasklist?
A: service.tasklists().insert(body={"title": "New List"}).execute()
   Returns the new tasklist ID for future operations.

Q4: What fields can a task have?
A: - id: Unique identifier
   - title: Task name
   - notes: Description
   - due: Due date (RFC 3339 timestamp)
   - status: "needsAction" or "completed"
   - completed: Completion timestamp (auto-set)
   - deleted: Soft delete flag
   - hidden: Hidden from list
   - parent: Parent task ID (for subtasks)
   - position: Order position

Q5: How would you implement subtasks?
A: Set the "parent" field to another task's ID:
   service.tasks().insert(
       tasklist="@default",
       body={
           "title": "Subtask",
           "parent": parent_task_id
       }
   ).execute()

Q6: What's the rate limit for Tasks API?
A: - 500,000 requests/day
   - 10 requests/second
   
   Very generous for personal use.

Q7: How would you move a task to a different list?
A: Use tasks().move():
   service.tasks().move(
       tasklist="@default",
       task=task_id,
       destinationTasklist=other_list_id
   ).execute()

Q8: How would you reorder tasks?
A: Use the "position" field with tasks().move() or patch():
   service.tasks().move(
       tasklist="@default",
       task=task_id,
       parent=parent_id,      # Optional: new parent
       previous=prev_task_id  # Insert after this task
   ).execute()

Q9: Can tasks have reminders?
A: Not directly in Google Tasks API. But you can:
   1. Read task due dates
   2. Create Calendar events or alarms for reminders
   3. Or use Google Calendar reminders integration

Q10: How would you sync tasks to a local database?
A: 1. Store last sync timestamp
   2. On sync, fetch all tasks
   3. Compare with local state (by ID)
   4. Update/create/delete as needed
   5. Store new sync timestamp
   
   Or use the updatedMin parameter for incremental sync.
"""