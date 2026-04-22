"""
Test script for open_app fixes:
1. Single APP_MAP source of truth
2. Already running check - focus instead of new instance
3. Proper method chaining - no duplicate launches
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Fix Windows console encoding for unicode characters
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

import time
import pytest

pytestmark = pytest.mark.side_effect


def test_single_app_map():
    """Verify APP_MAP is the single source of truth."""
    print("\n=== TEST 1: Single APP_MAP ===")
    
    from src.tools.pc_automation.app_launcher import APP_MAP
    from src.tools.wrapped_tools import open_app
    
    # Check that key apps exist in APP_MAP
    required_apps = ["notepad", "terminal", "settings", "chrome", "spotify"]
    missing = []
    for app in required_apps:
        if app not in APP_MAP:
            missing.append(app)
    
    if missing:
        print(f"✗ Missing apps in APP_MAP: {missing}")
        return False
    
    print(f"APP_MAP has {len(APP_MAP)} entries")
    print("Required apps present: " + ", ".join(required_apps))
    print("✓ TEST 1 PASSED: APP_MAP is comprehensive")
    return True


def test_already_running_focus():
    """Test that second 'open notepad' focuses instead of opening new instance."""
    print("\n=== TEST 2: Already Running Focus ===")
    
    from src.tools.pc_automation.app_launcher import open_application, close_application, is_app_running
    
    # First, make sure notepad is not running
    print("Ensuring notepad is closed...")
    close_application("notepad")
    time.sleep(0.5)
    
    # Open notepad first time
    print("Opening notepad (first call)...")
    result = open_application("notepad")
    print(f"First open result: {result}")
    time.sleep(1)  # Wait for it to open
    
    # Check if running
    running = is_app_running("notepad")
    print(f"Is notepad running? {running}")
    
    if not running.get("running"):
        print("✗ Notepad didn't open")
        return False
    
    # Now call the tool function which should detect it's running
    print("\nCalling open_app tool (should focus, not open new)...")
    # Import the tool function directly
    from src.tools.wrapped_tools import open_app as open_app_tool
    
    # Call the tool - this should return "already running" message
    result = open_app_tool.invoke({"app_name": "notepad"})
    print(f"Second call result: {result}")
    
    # Clean up
    print("\nCleaning up - closing notepad...")
    close_application("notepad")
    
    if "already" in result.lower() or "focused" in result.lower():
        print("✓ TEST 2 PASSED: Second call focused existing window")
        return True
    else:
        print(f"✗ TEST 2 FAILED: Expected focus message, got: {result}")
        return False


def test_open_terminal():
    """Test opening Windows Terminal."""
    print("\n=== TEST 3: Open Terminal ===")
    
    from src.tools.pc_automation.app_launcher import open_application, close_application
    
    print("Opening terminal...")
    result = open_application("terminal")
    print(f"Result: {result}")
    
    time.sleep(1)
    
    # Clean up
    print("Closing terminal...")
    close_application("terminal")
    time.sleep(0.5)
    
    if result.get("success"):
        print("✓ TEST 3 PASSED: Terminal opened successfully")
        return True
    else:
        print("✗ TEST 3 FAILED: Terminal did not open")
        return False


def test_open_settings():
    """Test opening Windows Settings."""
    print("\n=== TEST 4: Open Settings ===")
    
    from src.tools.pc_automation.app_launcher import open_application
    
    print("Opening settings...")
    result = open_application("settings")
    print(f"Result: {result}")
    
    time.sleep(1)
    
    # Note: Settings is hard to close programmatically, so we just verify it opened
    if result.get("success"):
        print("✓ TEST 4 PASSED: Settings opened successfully")
        print("(Note: Settings window may still be open - close manually if needed)")
        return True
    else:
        print("✗ TEST 4 FAILED: Settings did not open")
        return False


def main():
    print("=" * 50)
    print("TESTING OPEN_APP FIXES")
    print("=" * 50)
    
    results = []
    
    # Test 1: Single APP_MAP
    results.append(("Single APP_MAP", test_single_app_map()))
    
    # Test 2: Already running focus
    results.append(("Already Running Focus", test_already_running_focus()))
    
    # Test 3: Open terminal
    results.append(("Open Terminal", test_open_terminal()))
    
    # Test 4: Open settings
    results.append(("Open Settings", test_open_settings()))
    
    print("\n" + "=" * 50)
    print("SUMMARY")
    print("=" * 50)
    for name, passed in results:
        status = "✓ PASSED" if passed else "✗ FAILED"
        print(f"{name}: {status}")
    
    all_passed = all(r[1] for r in results)
    print("=" * 50)
    if all_passed:
        print("ALL TESTS PASSED!")
    else:
        print("SOME TESTS FAILED")
    
    return all_passed


if __name__ == "__main__":
    main()
