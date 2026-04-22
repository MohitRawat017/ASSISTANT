"""
Test script for the three bug fixes:
1. close_app - null check in close_application
2. typing - reduced PAUSE for faster typing
3. volume - COM initialization
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


def test_close_app():
    """Test 1: Close notepad"""
    print("\n=== TEST 1: Close App ===")
    
    # First, open notepad
    from src.tools.pc_automation.app_launcher import open_application, close_application
    
    print("Opening notepad...")
    result = open_application("notepad")
    print(f"Open result: {result}")
    
    # Wait for it to open
    time.sleep(1)
    
    # Now close it
    print("Closing notepad...")
    result = close_application("notepad")
    print(f"Close result: {result}")
    
    if result.get("success"):
        print("✓ TEST 1 PASSED: Notepad closed successfully")
        return True
    else:
        print("✗ TEST 1 FAILED: Could not close notepad")
        return False


def test_typing():
    """Test 2: Open notepad and type hello world"""
    print("\n=== TEST 2: Typing ===")
    
    from src.tools.pc_automation.app_launcher import open_application
    from src.tools.pc_automation.mouse_keyboard import type_text
    import pyautogui
    
    # Check PAUSE setting
    print(f"pyautogui.PAUSE = {pyautogui.PAUSE}")
    if pyautogui.PAUSE > 0.05:
        print(f"✗ PAUSE is too high ({pyautogui.PAUSE}), should be <= 0.05")
        return False
    
    # Open notepad
    print("Opening notepad...")
    result = open_application("notepad")
    print(f"Open result: {result}")
    
    # Wait for window to be ready (as per docstring instruction)
    print("Waiting 0.5s for window to load...")
    time.sleep(0.5)
    
    # Type text
    print("Typing 'hello world'...")
    start_time = time.perf_counter()
    result = type_text("hello world")
    elapsed = time.perf_counter() - start_time
    print(f"Type result: {result}")
    print(f"Typing took: {elapsed:.2f}s")
    
    # Wait a moment to see the result
    time.sleep(0.5)
    
    # Close notepad (don't save)
    print("Closing notepad...")
    from src.tools.pc_automation.app_launcher import close_application
    close_application("notepad")
    time.sleep(0.5)
    
    # For typing 11 chars with PAUSE=0.02 and interval=0.05, should take ~0.77s max
    # (11 * (0.02 + 0.05) = 0.77)
    if elapsed < 2.0:  # Allow some overhead
        print("✓ TEST 2 PASSED: Typing completed without freeze")
        return True
    else:
        print(f"✗ TEST 2 FAILED: Typing took too long ({elapsed:.2f}s)")
        return False


def test_volume():
    """Test 3: Set volume to 40"""
    print("\n=== TEST 3: Volume Control ===")
    
    from src.tools.pc_automation.system_controls import set_volume, get_volume
    
    try:
        # Get current volume
        print("Getting current volume...")
        result = get_volume()
        print(f"Current volume: {result}")
        original_volume = result.get("volume", 50)
        
        # Set volume to 40
        print("Setting volume to 40...")
        result = set_volume(40)
        print(f"Set result: {result}")
        
        # Verify
        print("Verifying volume...")
        result = get_volume()
        print(f"New volume: {result}")
        
        # Restore original volume
        print(f"Restoring volume to {original_volume}...")
        set_volume(original_volume)
        
        if result.get("success") and result.get("volume") == 40:
            print("✓ TEST 3 PASSED: Volume control works without COM error")
            return True
        else:
            print("✗ TEST 3 FAILED: Volume was not set correctly")
            return False
            
    except Exception as e:
        print(f"✗ TEST 3 FAILED: Exception - {e}")
        return False


def main():
    print("=" * 50)
    print("TESTING THREE BUG FIXES")
    print("=" * 50)
    
    results = []
    
    # Test 3 first (volume) - doesn't need GUI interaction
    results.append(("Volume", test_volume()))
    
    # Test 1 (close) - opens and closes notepad
    results.append(("Close App", test_close_app()))
    
    # Test 2 (typing) - opens, types, closes
    results.append(("Typing", test_typing()))
    
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
