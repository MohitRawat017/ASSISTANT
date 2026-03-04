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