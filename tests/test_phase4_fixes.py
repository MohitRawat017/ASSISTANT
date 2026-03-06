"""
Quick test for Phase 4 fixes - verify basic PC automation works.
Run: python -m tests.test_phase4_fixes
"""

import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

def test_imports():
    """Test that all PC automation modules import correctly."""
    print("Testing imports...")
    
    from src.tools.pc_automation.screenshot import take_screenshot, take_region_screenshot
    from src.tools.pc_automation.mouse_keyboard import (
        mouse_click, mouse_move, type_text, press_key, hotkey, scroll, get_screen_size
    )
    from src.tools.pc_automation.window_manager import (
        get_open_windows, focus_window,
        minimize_window, maximize_window, minimize_all_windows
    )
    from src.tools.pc_automation.system_controls import (
        set_volume, get_volume, mute_volume, unmute_volume,
        set_brightness, get_brightness, lock_screen, get_pc_stats
    )
    from src.tools.pc_automation.app_launcher import (
        open_application, close_application, is_app_running
    )
    print("[OK] All imports successful")
    return True


def test_get_pc_stats():
    """Test get_pc_stats uses correct Windows drive path."""
    print("\nTesting get_pc_stats (Issue 1 fix)...")
    
    from src.tools.pc_automation.system_controls import get_pc_stats
    import os
    
    result = get_pc_stats()
    
    # Should return dict with expected keys
    assert "cpu_percent" in result, "Missing cpu_percent"
    assert "memory_percent" in result, "Missing memory_percent"
    assert "memory_available_gb" in result, "Missing memory_available_gb"
    assert "disk_free_gb" in result, "Missing disk_free_gb"
    
    # Disk free should be a positive number (proves Windows path works)
    assert result["disk_free_gb"] > 0, f"Invalid disk_free_gb: {result['disk_free_gb']}"
    
    print(f"  CPU: {result['cpu_percent']}%")
    print(f"  Memory: {result['memory_percent']}% used ({result['memory_available_gb']}GB free)")
    print(f"  Disk: {result['disk_free_gb']}GB free")
    print("[OK] get_pc_stats works correctly")
    return True


def test_list_open_windows():
    """Test list_open_windows function."""
    print("\nTesting list_open_windows...")
    
    from src.tools.pc_automation.window_manager import get_open_windows
    
    windows = get_open_windows()
    
    # Should return a list (may be empty but shouldn't error)
    assert isinstance(windows, list), "Should return a list"
    
    print(f"  Found {len(windows)} open windows")
    for w in windows[:5]:
        print(f"    - {w['title'][:50]}... ({w['process']})")
    
    print("[OK] list_open_windows works correctly")
    return True


def test_screen_size():
    """Test get_screen_size function."""
    print("\nTesting get_screen_size...")
    
    from src.tools.pc_automation.mouse_keyboard import get_screen_size
    
    result = get_screen_size()
    
    assert "width" in result, "Missing width"
    assert "height" in result, "Missing height"
    assert result["width"] > 0, f"Invalid width: {result['width']}"
    assert result["height"] > 0, f"Invalid height: {result['height']}"
    
    print(f"  Screen resolution: {result['width']}x{result['height']}")
    print("[OK] get_screen_size works correctly")
    return True


def test_get_volume():
    """Test get_volume function."""
    print("\nTesting get_volume...")
    
    from src.tools.pc_automation.system_controls import get_volume
    
    result = get_volume()
    
    assert result["success"], f"get_volume failed: {result}"
    assert "volume" in result, "Missing volume in result"
    assert 0 <= result["volume"] <= 100, f"Volume out of range: {result['volume']}"
    
    print(f"  Current volume: {result['volume']}%")
    print("[OK] get_volume works correctly")
    return True


def test_wrapped_tools_import():
    """Test that wrapped_tools imports all PC automation tools correctly."""
    print("\nTesting wrapped_tools imports...")
    
    from src.tools.wrapped_tools import (
        open_app, close_app, list_open_windows, focus_app,
        control_volume, control_brightness, lock_screen_tool, get_pc_status,
        take_screenshot_tool, click_at, type_text_tool, press_keyboard_key,
        hotkey_tool, minimize_all, screenshot_to_telegram
    )
    
    print("[OK] All wrapped tools imported successfully")
    return True


def main():
    """Run all tests."""
    print("=" * 60)
    print("Phase 4 Fixes Verification Tests")
    print("=" * 60)
    
    tests = [
        test_imports,
        test_get_pc_stats,
        test_list_open_windows,
        test_screen_size,
        test_get_volume,
        test_wrapped_tools_import,
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            if test():
                passed += 1
        except Exception as e:
            print(f"[FAIL] {test.__name__} FAILED: {e}")
            failed += 1
    
    print("\n" + "=" * 60)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 60)
    
    return failed == 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)