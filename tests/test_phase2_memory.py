"""
Phase 2 Evaluation Tests for Long-Term Memory.

Tests:
1. Basic memory save across restarts
2. Implicit save (auto-detect facts)
3. Location memory integration
4. Memory doesn't bleed between threads
5. Memory update (no duplicates)
"""

import sys
import os
import pytest

pytestmark = pytest.mark.side_effect

# Fix Windows console encoding
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8')

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.memory import LongTermMemory
from src.tools.wrapped_tools import save_memory, get_user_context
from src.graph.agent import _build_system_prompt_with_memory


def test_1_basic_save():
    """TEST 1 — Basic memory save across restarts"""
    print("\n" + "=" * 50)
    print("TEST 1 — Basic memory save")
    print("=" * 50)
    
    m = LongTermMemory()
    m.clear_all()
    
    # Save a memory
    m.save("I prefer dark mode", "preference")
    
    # Retrieve all
    memories = m.get_all()
    assert len(memories) == 1, f"Expected 1 memory, got {len(memories)}"
    assert "dark mode" in memories[0]["content"], "Memory content mismatch"
    
    print("✓ Memory saved successfully")
    print(f"  Content: {memories[0]['content']}")
    print("✓ TEST 1 PASSED")


def test_2_implicit_save():
    """TEST 2 — Implicit save via tools"""
    print("\n" + "=" * 50)
    print("TEST 2 — Implicit save via tools")
    print("=" * 50)
    
    # Use the tool to save
    result = save_memory.invoke({"content": "My standup meeting is every day at 10am", "category": "schedule"})
    assert "Remembered" in result, f"Unexpected result: {result}"
    
    # Verify it was saved
    m = LongTermMemory()
    memories = m.search("standup")
    assert len(memories) > 0, "Memory not found after save"
    
    print("✓ Memory saved via tool")
    print(f"  Tool result: {result}")
    print("✓ TEST 2 PASSED")


def test_3_location_memory():
    """TEST 3 — Location memory integration"""
    print("\n" + "=" * 50)
    print("TEST 3 — Location memory integration")
    print("=" * 50)
    
    m = LongTermMemory()
    m.save("I'm from Una, Himachal Pradesh", "location")
    
    # Verify location is in context
    context = m.get_context_string()
    assert "Una" in context, "Location not in context"
    
    # Verify it's in system prompt
    prompt = _build_system_prompt_with_memory()
    assert "Una" in prompt, "Location not in system prompt"
    
    print("✓ Location saved")
    print(f"  Context: {context}")
    print("✓ TEST 3 PASSED")


def test_4_memory_update():
    """TEST 4 — Memory update (no duplicates)"""
    print("\n" + "=" * 50)
    print("TEST 4 — Memory update (no duplicates)")
    print("=" * 50)
    
    m = LongTermMemory()
    m.clear_all()
    
    # Save original
    m.save("I wake up at 7am", "schedule")
    count1 = len(m.get_all())
    
    # Update with similar content
    m.save("I wake up at 6:30am", "schedule")
    count2 = len(m.get_all())
    
    # Should still have 1 memory (updated, not duplicated)
    assert count2 == count1, f"Memory was duplicated: {count1} -> {count2}"
    
    # Verify content was updated
    memories = m.get_all()
    assert "6:30am" in memories[0]["content"], f"Content not updated: {memories[0]['content']}"
    
    print(f"✓ Memory updated without duplication")
    print(f"  Count before: {count1}, after: {count2}")
    print(f"  Updated content: {memories[0]['content']}")
    print("✓ TEST 4 PASSED")


def test_5_context_injection():
    """TEST 5 — Memory context injection in system prompt"""
    print("\n" + "=" * 50)
    print("TEST 5 — Memory context injection in system prompt")
    print("=" * 50)
    
    m = LongTermMemory()
    m.save("Currently learning LangGraph", "project")
    
    prompt = _build_system_prompt_with_memory()
    
    # Check memory section is in prompt
    assert "What you know about this user" in prompt, "Memory section not in prompt"
    assert "LangGraph" in prompt, "Project memory not in prompt"
    
    print("✓ Memory context injected into system prompt")
    print(f"  Prompt contains 'What you know about this user': Yes")
    print(f"  Prompt contains 'LangGraph': Yes")
    print("✓ TEST 5 PASSED")


def test_5b_dynamic_memory_injection():
    """TEST 5b — Dynamic memory injection (memories added mid-session)"""
    print("\n" + "=" * 50)
    print("TEST 5b — Dynamic memory injection")
    print("=" * 50)
    
    m = LongTermMemory()
    
    # Get initial prompt
    prompt1 = _build_system_prompt_with_memory()
    
    # Save a new memory
    m.save("I love playing guitar", "preference")
    
    # Get updated prompt - should include new memory without restart
    prompt2 = _build_system_prompt_with_memory()
    
    # Verify the new memory is in the updated prompt
    assert "guitar" in prompt2, "New memory not reflected in prompt"
    assert prompt1 != prompt2, "Prompt should change when memory is added"
    
    print("✓ Memory dynamically injected without restart")
    print(f"  New memory 'guitar' in updated prompt: Yes")
    print("✓ TEST 5b PASSED")


def test_6_tool_registry():
    """TEST 6 — Verify tools are registered"""
    print("\n" + "=" * 50)
    print("TEST 6 — Tool registry check")
    print("=" * 50)
    
    from src.tools.wrapped_tools import ALL_TOOLS
    
    tool_names = [t.name for t in ALL_TOOLS]
    
    assert "save_memory" in tool_names, "save_memory not in tools"
    assert "get_user_context" in tool_names, "get_user_context not in tools"
    
    print(f"✓ All tools registered: {len(ALL_TOOLS)} tools")
    print(f"  Tool names: {tool_names}")
    print("✓ TEST 6 PASSED")


def run_all_tests():
    """Run all Phase 2 evaluation tests."""
    print("\n" + "=" * 60)
    print("PHASE 2 — LONG-TERM MEMORY EVALUATION TESTS")
    print("=" * 60)
    
    try:
        test_1_basic_save()
        test_2_implicit_save()
        test_3_location_memory()
        test_4_memory_update()
        test_5_context_injection()
        test_5b_dynamic_memory_injection()
        test_6_tool_registry()
        
        print("\n" + "=" * 60)
        print("✓ ALL TESTS PASSED!")
        print("=" * 60)
        print("\nPhase 2 Long-Term Memory is ready for evaluation.")
        print("\nTo complete the evaluation, run the assistant and test:")
        print("  1. Say 'remember that I prefer dark mode' → restart → 'what are my preferences?'")
        print("  2. Say 'my standup meeting is at 10am' → restart → 'remind me before standup'")
        print("  3. Say 'I'm from Una, HP' → restart → 'what's the weather?'")
        
    except AssertionError as e:
        print(f"\n✗ TEST FAILED: {e}")
        return False
    except Exception as e:
        print(f"\n✗ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    return True


if __name__ == "__main__":
    run_all_tests()
