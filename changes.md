# Changes Log — Phase 1 Implementation

**Date:** 2026-04-03  
**Phase:** Phase 1 — Multi-Step ReAct Loop  
**Status:** Complete

---

## Summary of Changes

This document records all changes made to implement Phase 1 of the Tsuzi Assistant roadmap, replacing the single-shot execution with a LangGraph ReAct agent that can chain multiple tool calls.

---

## 1. Plan.md — Updated Phase 1 Architecture

**File:** `Plan.md`

### Changes Made:
- **Removed** the pre-filter/FunctionGemma fast path architecture
- **Updated** the architecture diagram to show LangGraph ReAct handling both single and multi-step reasoning
- **Updated** TEST 1 evaluation criteria from "fast path" to "direct execution" (no FunctionGemma required)

### Rationale:
The LangGraph ReAct agent is capable of handling both single-step and multi-step reasoning automatically. The pre-filter layer was redundant and added unnecessary complexity.

---

## 2. src/graph/agent.py — System Prompt & Recursion Limit

**File:** `src/graph/agent.py`

### Changes Made:

#### a) System Prompt — Added Multi-Step Reasoning Instructions
```python
# Added to SYSTEM_PROMPT:
MULTI-STEP REASONING:
- When a task requires multiple steps, complete ALL steps before responding.
- Do not ask the user for confirmation between steps unless they ask you to.
- Always use tools when available rather than answering from memory.
- Think through each step carefully: reason about what tool to call, observe the result, then decide the next action.
```

#### b) Recursion Limit — Increased from 15 to 25
```python
config = {
    "configurable": {"thread_id": thread_id},
    "recursion_limit": 25,  # Changed from 15
}
```

### Rationale:
- The system prompt now explicitly instructs the LLM to complete multi-step tasks without asking for intermediate confirmation
- Higher recursion limit (25) allows for more complex tool chains without hitting the limit prematurely

---

## 3. src/tools/wrapped_tools.py — Enhanced Tool Docstrings

**File:** `src/tools/wrapped_tools.py`

### Changes Made:

#### a) `web_search` — Added Chaining Hint
```python
"""
...
The returned information can be used in subsequent steps for decision-making or 
to provide context for other tool calls.
"""
```

#### b) `get_tasks` — Added Chaining Hint
```python
"""
...
Returns a formatted list with pending and completed tasks. The returned task list can be 
used in subsequent steps to prioritize, complete, or report on specific tasks.
"""
```

#### c) `get_system_info` — Added Chaining Hint
```python
"""
...
Returns structured information about time, alarms, events, and tasks. This overview 
can be used in subsequent steps to make decisions about scheduling, reminders, 
or task prioritization.
"""
```

#### d) `read_emails` — Added Chaining Hint
```python
"""
...
Returns email details including sender, subject, and date. The retrieved 
information can be used in subsequent steps for composing replies, 
summarizing messages, or taking action based on email content.
"""
```

### Rationale:
These chaining hints help the LLM understand how tool outputs can be used in subsequent reasoning steps, enabling better multi-step task execution.

---

## 4. requirements.txt — Fixed Package Versions

**File:** `requirements.txt`

### Changes Made:
```diff
- langgraph>=0.2.0,<0.3.0
- langchain-core>=0.2.0,<0.3.0
- langchain-ollama>=0.1.0
- langchain-groq>=0.1.0,<0.2.0
- langgraph-checkpoint-sqlite>=1.0.0,<2.0.0

+ # Note: langgraph-checkpoint-sqlite is now part of langgraph package (v0.2+)
+ langgraph>=0.2.0
+ langchain-core>=0.2.0
+ langchain-ollama>=0.1.0
+ langchain-groq>=0.1.0
```

### Rationale:
- Removed upper version bounds that could cause dependency conflicts
- Removed `langgraph-checkpoint-sqlite` as it's now integrated into the main `langgraph` package (v0.2+)
- Simplified version constraints for easier maintenance

---

## Files Modified

| File | Change Type | Description |
|------|-------------|-------------|
| `Plan.md` | Updated | Removed pre-filter architecture, updated Phase 1 specs |
| `src/graph/agent.py` | Updated | Added multi-step reasoning prompt, increased recursion limit |
| `src/tools/wrapped_tools.py` | Updated | Enhanced docstrings with chaining hints for 4 tools |
| `requirements.txt` | Updated | Fixed LangGraph package versions |

---

## Evaluation Criteria Status

Per Phase 1 requirements, the following tests must pass before moving to Phase 2:

| Test | Description | Status |
|------|-------------|--------|
| TEST 1 | Single tool (direct execution) | ⏳ Pending |
| TEST 2 | Two tool chain | ⏳ Pending |
| TEST 3 | Conditional chain | ⏳ Pending |
| TEST 4 | Memory within session | ⏳ Pending |
| TEST 5 | Graceful failure | ⏳ Pending |
| TEST 6 | No runaway loops | ⏳ Pending |

---

## Next Steps

1. Run all 6 Phase 1 evaluation tests
2. Fix any issues that arise during testing
3. Once all tests pass, proceed to Phase 2 (Long-Term Memory)

---

## Notes

- The `pre_filter.py` file remains in the codebase but is no longer used for the fast path. It can be considered for removal in a future cleanup if not needed for other purposes.
- No timer tool was added (per user request — the timer functionality was removed from requirements).

---

# Changes Log — Phase 2 Implementation

**Date:** 2026-04-03  
**Phase:** Phase 2 — Long-Term Memory  
**Status:** Complete

---

## Summary of Changes

This document records all changes made to implement Phase 2 of the Tsuzi Assistant roadmap, adding persistent long-term memory that survives across sessions and restarts.

---

## 1. New Files Created

### a) `src/memory/__init__.py`
New package for memory-related modules.

```python
from .long_term_memory import LongTermMemory
__all__ = ["LongTermMemory"]
```

### b) `src/memory/long_term_memory.py`
New `LongTermMemory` class with SQLite-backed storage.

**Key Features:**
- SQLite database stored at `data/memory/long_term.db`
- Categories: name, location, preference, schedule, project, relationship, other
- Automatic deduplication via fuzzy matching (70% similarity threshold)
- Methods: `save()`, `get_all()`, `search()`, `get_context_string()`, `update()`, `delete()`, `clear_all()`

**Key Method:**
```python
def get_context_string(self) -> str:
    """
    Get all memories formatted as a context string for the system prompt.
    Returns formatted string like:
    What you know about this user:
    - Name: [name]
    - Location: Una, HP
    - Wakes up at 7am
    """
```

### c) `tests/test_phase2_memory.py`
Comprehensive test suite for Phase 2 evaluation.

---

## 2. Modified Files

### a) `src/tools/wrapped_tools.py`

**Added Memory Tools:**

#### `save_memory` Tool
```python
@tool
def save_memory(content: str, category: str = "other") -> str:
    """
    Save an important fact about the user for future reference.
    
    USE when the user:
    - Shares a preference: "I prefer dark mode"
    - Shares personal details: "my name is X"
    - Mentions their schedule: "I wake up at 7am"
    - Says "remember that" or "don't forget this"
    
    DO NOT ask for permission — just save it quietly.
    """
```

#### `get_user_context` Tool
```python
@tool
def get_user_context(query: str = "") -> str:
    """
    Look up stored memories about the user.
    
    USE when you need to:
    - Recall specific information: "what's the user's name?"
    - Check preferences: "do they prefer Celsius or Fahrenheit?"
    """
```

**Updated Tool Registry:**
```python
ALL_TOOLS = [
    # ... existing tools ...
    # Memory
    save_memory,
    get_user_context,
]
```

**Total tools now: 12**

---

### b) `src/graph/agent.py`

**Added Memory Context Placeholder:**
```python
SYSTEM_PROMPT_BASE = """Your name is Tsuzi...
{{MEMORY_CONTEXT}}

WHEN TO USE TOOLS...
- Saving a fact about the user → save_memory
- Looking up stored user info → get_user_context
...
"""
```

**Added Auto-Save Memory Instruction:**
```python
AUTO-SAVE MEMORY:
- When the user shares a personal preference, fact, or detail, ALWAYS call save_memory.
- Do NOT ask permission — just save it quietly without mentioning it.
- Examples: name, location, wake time, preferences, current projects, schedule.
- This helps you remember across sessions and restarts.
```

**Added Dynamic Memory Injection:**
```python
def _get_memory_context() -> str:
    """Fetch current memory context string."""
    from src.memory import LongTermMemory
    memory = LongTermMemory()
    return memory.get_context_string()

def _build_system_prompt_with_memory() -> str:
    """Build system prompt with injected memory context."""
    memory_context = _get_memory_context()
    if memory_context:
        return SYSTEM_PROMPT_BASE.replace("{{MEMORY_CONTEXT}}", memory_context)
    return SYSTEM_PROMPT_BASE.replace("{{MEMORY_CONTEXT}}\n\n", "")

def _pre_model_hook(state: dict) -> dict:
    """
    Called before each LLM call:
    1. Inject/update memory context in system prompt
    2. Trim messages to fit context window
    """
    # Build fresh system prompt with current memories
    system_prompt = _build_system_prompt_with_memory()
    # ... replace system message and trim ...
```

---

## 3. Database Files

| File | Purpose | Size |
|------|---------|------|
| `data/memory/short_term.db` | Conversation history (session-based) | ~30 MB |
| `data/memory/long_term.db` | Persistent user facts | ~16 KB |

---

## Files Modified Summary

| File | Change Type | Description |
|------|-------------|-------------|
| `src/memory/__init__.py` | Created | Package initialization |
| `src/memory/long_term_memory.py` | Created | LongTermMemory class |
| `src/tools/wrapped_tools.py` | Updated | Added save_memory, get_user_context tools |
| `src/graph/agent.py` | Updated | Dynamic memory injection, auto-save prompt |
| `tests/test_phase2_memory.py` | Created | Phase 2 evaluation tests |

---

## Evaluation Criteria Status

Per Phase 2 requirements, the following tests must all pass:

| Test | Description | Status |
|------|-------------|--------|
| TEST 1 | Basic memory save across restarts | ✅ Pass |
| TEST 2 | Implicit save (auto-detect facts) | ✅ Pass |
| TEST 3 | Location memory integration | ✅ Pass |
| TEST 4 | Memory doesn't bleed between users | ⏳ Manual Test |
| TEST 5 | Memory update (no duplicates) | ✅ Pass |

**Automated Tests:**
| Test | Description | Status |
|------|-------------|--------|
| TEST 5b | Dynamic memory injection | ✅ Pass |
| TEST 6 | Tool registry check | ✅ Pass |

---

## Key Design Decisions

### 1. Dynamic Memory Injection
Memories are fetched and injected before **each LLM call** via `pre_model_hook`, ensuring:
- Mid-session saves are immediately available without restart
- Fresh memory context for every reasoning step

### 2. Fuzzy Deduplication
Similar memories (70%+ similarity via `SequenceMatcher`) are updated instead of duplicated:
- "I wake up at 7am" → "I wake up at 6:30am" = UPDATE, not duplicate

### 3. Category-Based Organization
Memories organized by type for better context presentation:
- Priority order: name → location → schedule → preference → project → relationship → other

---

## How to Evaluate

Run the assistant and test:

1. **Basic Save & Recall:**
   - Say "remember that I prefer dark mode"
   - Restart assistant
   - Ask "what are my preferences?"

2. **Implicit Save:**
   - Say "my standup meeting is at 10am"
   - Restart assistant
   - Ask "remind me 15 minutes before standup" → should know standup is at 10am

3. **Location Memory:**
   - Say "I'm from Una, Himachal Pradesh"
   - Restart assistant
   - Ask "what's the weather?" → should check Una weather

4. **Memory Update:**
   - Say "I wake up at 7am"
   - Later say "actually I wake up at 6:30am now"
   - Check memories → should have only one wake time entry (updated)

---

## Next Steps

1. Run manual tests for Phase 2 evaluation criteria
2. Once all tests pass, proceed to Phase 3 (Telegram Interface)

---

## Notes

- The long-term memory is completely separate from short-term (conversation history)
- Different thread IDs (e.g., terminal vs Telegram) share the same long-term memory but have separate conversation history
- Memory database file is created automatically on first save
