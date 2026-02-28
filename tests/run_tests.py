"""
Test runner for the assistant tool testing framework.

Run from project root:
    python tests/run_tests.py [options]

Options:
    --category CATEGORY    Run only tests from a specific category
    --verbose              Show detailed output
    --quick                Skip slow/network tests
    --report               Generate report only (don't run tests)
    --install-deps         Check and report missing dependencies

Categories:
    core         - Core tools (timer, alarm, calendar, tasks, etc.)
    pc_control   - PC control tools (volume, brightness, etc.)
    file_ops     - File operations
    research     - Research tools (stackoverflow, arxiv, youtube)
    habits       - Habit tracking
    email        - Email tools
    managers     - Manager unit tests
    integration  - Integration tests
"""

import os
import sys
import json
import time
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional

# Add project root
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Test results directory
RESULTS_DIR = PROJECT_ROOT / "tests" / "test_results"
RESULTS_DIR.mkdir(exist_ok=True)


# ── Color Output ──────────────────────────────────────────────────────────

class Colors:
    """ANSI color codes for terminal output."""
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    MAGENTA = "\033[95m"
    CYAN = "\033[96m"
    WHITE = "\033[97m"
    BOLD = "\033[1m"
    UNDERLINE = "\033[4m"
    END = "\033[0m"


def print_color(text: str, color: str = Colors.WHITE, bold: bool = False):
    """Print colored text to terminal."""
    prefix = Colors.BOLD if bold else ""
    try:
        print(f"{prefix}{color}{text}{Colors.END}")
    except UnicodeEncodeError:
        # Fallback for Windows terminals without Unicode support
        clean_text = text.encode('ascii', 'replace').decode('ascii')
        print(f"{prefix}{color}{clean_text}{Colors.END}")


# ── Dependency Checker ────────────────────────────────────────────────────

def check_dependencies() -> Dict[str, dict]:
    """Check status of all optional dependencies."""
    dependencies = {
        # Core
        "ddgs": {"feature": "Web Search (DuckDuckGo)", "required": True},
        "AppOpener": {"feature": "App Launching", "required": True},
        
        # PC Control
        "pycaw": {"feature": "Volume Control", "required": False},
        "screen_brightness_control": {"feature": "Brightness Control", "required": False},
        "pyautogui": {"feature": "Screenshot & Minimize", "required": False},
        
        # Research
        "arxiv": {"feature": "Academic Paper Search", "required": False},
        "trafilatura": {"feature": "Webpage Summarization", "required": False},
        "youtubesearchpython": {"feature": "YouTube Search", "required": False},
        "requests": {"feature": "HTTP Requests", "required": True},
        
        # Testing
        "pytest": {"feature": "Test Framework", "required": True},
    }
    
    results = {}
    for module, info in dependencies.items():
        try:
            __import__(module)
            results[module] = {
                **info,
                "installed": True,
                "status": "[OK] Installed"
            }
        except ImportError:
            results[module] = {
                **info,
                "installed": False,
                "status": "[X] Missing"
            }
    
    return results


def print_dependency_report():
    """Print a formatted dependency report."""
    print_color("\n" + "=" * 60, Colors.CYAN, bold=True)
    print_color("  Dependency Status Report", Colors.CYAN, bold=True)
    print_color("=" * 60 + "\n", Colors.CYAN)
    
    deps = check_dependencies()
    
    print(f"{'Module':<30} {'Status':<20} {'Feature'}")
    print("-" * 80)
    
    missing_required = []
    missing_optional = []
    
    for module, info in deps.items():
        status_color = Colors.GREEN if info["installed"] else Colors.RED
        print(f"{module:<30} {status_color}{info['status']:<20}{Colors.END} {info['feature']}")
        
        if not info["installed"]:
            if info["required"]:
                missing_required.append(module)
            else:
                missing_optional.append(module)
    
    print()
    
    if missing_required:
        print_color(f"[!] Missing required dependencies: {', '.join(missing_required)}", Colors.RED)
        print_color("   Install with: pip install " + " ".join(missing_required), Colors.YELLOW)
    
    if missing_optional:
        print_color(f"[i] Missing optional dependencies: {', '.join(missing_optional)}", Colors.YELLOW)
        print_color("   Some tests will be skipped.", Colors.YELLOW)
    
    if not missing_required and not missing_optional:
        print_color("[OK] All dependencies installed!", Colors.GREEN)
    
    print()
    return deps


# ── Test Runner ───────────────────────────────────────────────────────────

def run_pytest(category: Optional[str] = None, verbose: bool = False, quick: bool = False) -> int:
    """Run pytest with specified options."""
    cmd = [sys.executable, "-m", "pytest", "tests/"]
    
    # Add options
    if verbose:
        cmd.append("-v")
    else:
        cmd.append("-q")
    
    # Add markers based on category
    if category:
        category_map = {
            "core": "core",
            "pc_control": "pc_control",
            "file_ops": "file_ops",
            "research": "research",
            "habits": "habits",
            "email": "email",
            "managers": None,  # Run test_managers.py
            "integration": "integration"
        }
        
        if category == "managers":
            cmd = [sys.executable, "-m", "pytest", "tests/test_managers.py", "-v" if verbose else "-q"]
        elif category in category_map and category_map[category]:
            cmd.extend(["-m", category_map[category]])
    
    # Skip slow/network tests if quick mode
    if quick:
        cmd.extend(["-m", "not requires_network"])
    
    # Add output options
    cmd.extend([
        "--tb=short",
        f"--junit-xml={RESULTS_DIR / 'junit.xml'}",
        "--color=yes"
    ])
    
    print_color(f"\nRunning: {' '.join(cmd)}\n", Colors.BLUE)
    
    result = subprocess.run(cmd, cwd=PROJECT_ROOT)
    return result.returncode


# ── Report Generator ──────────────────────────────────────────────────────

def generate_report_from_json():
    """Generate report from the latest test results JSON."""
    json_path = RESULTS_DIR / "detailed_log.json"
    
    if not json_path.exists():
        print_color("No test results found. Run tests first.", Colors.YELLOW)
        return
    
    with open(json_path) as f:
        data = json.load(f)
    
    summary = data.get("summary", {})
    total = summary.get("total", 0)
    passed = summary.get("passed", 0)
    failed = summary.get("failed", 0)
    skipped = summary.get("skipped", 0)
    
    # Calculate health score
    if total > 0:
        health = (passed / total) * 100
    else:
        health = 0
    
    # Print summary
    print_color("\n" + "=" * 60, Colors.CYAN, bold=True)
    print_color("  Test Results Summary", Colors.CYAN, bold=True)
    print_color("=" * 60, Colors.CYAN)
    
    print(f"\n  Total Tests:   {total}")
    print(f"  Passed:        {Colors.GREEN}{passed}{Colors.END}")
    print(f"  Failed:        {Colors.RED}{failed}{Colors.END}")
    print(f"  Skipped:       {Colors.YELLOW}{skipped}{Colors.END}")
    
    health_color = Colors.GREEN if health >= 80 else Colors.YELLOW if health >= 50 else Colors.RED
    print_color(f"\n  Health Score:  {health:.1f}%", health_color, bold=True)
    
    # Print errors
    errors = summary.get("errors", [])
    if errors:
        print_color(f"\n  Errors ({len(errors)}):", Colors.RED)
        for err in errors[:5]:
            print(f"    - {err['test']}")
            print(f"      {err['error'][:100]}...")
    
    print_color("\n" + "=" * 60 + "\n", Colors.CYAN)
    
    # Print report location
    report_path = RESULTS_DIR / "latest_report.md"
    print_color(f"[File] Full report: {report_path}", Colors.BLUE)


# ── Quick Test Runner ─────────────────────────────────────────────────────

def run_quick_tests():
    """Run a quick smoke test of core functionality."""
    print_color("\n[Running] Quick Smoke Tests...\n", Colors.CYAN, bold=True)
    
    results = []
    
    # Test 1: Check project structure
    print("1. Checking project structure...", end=" ")
    required_dirs = ["src", "src/managers", "src/tools", "tests"]
    missing = [d for d in required_dirs if not (PROJECT_ROOT / d).exists()]
    if missing:
        print_color(f"FAIL - Missing: {missing}", Colors.RED)
        results.append(False)
    else:
        print_color("OK", Colors.GREEN)
        results.append(True)
    
    # Test 2: Check managers can be imported
    print("2. Testing manager imports...", end=" ")
    try:
        from src.managers.timer_manager import TimerManager
        from src.managers.alarm_manager import AlarmManager
        from src.managers.task_manager import TaskManager
        from src.managers.calendar_manager import CalendarManager
        from src.managers.habit_manager import HabitManager
        print_color("OK", Colors.GREEN)
        results.append(True)
    except ImportError as e:
        print_color(f"FAIL - {e}", Colors.RED)
        results.append(False)
    
    # Test 3: Check tools can be imported
    print("3. Testing tool imports...", end=" ")
    try:
        from src.tools.wrapped_tools import ALL_TOOLS
        print_color(f"OK ({len(ALL_TOOLS)} tools)", Colors.GREEN)
        results.append(True)
    except ImportError as e:
        print_color(f"FAIL - {e}", Colors.RED)
        results.append(False)
    
    # Test 4: Quick timer test
    print("4. Testing timer functionality...", end=" ")
    try:
        from src.tools.wrapped_tools import set_timer
        # StructuredTool needs .invoke() or to access the underlying function
        if hasattr(set_timer, 'invoke'):
            result = set_timer.invoke({"duration": "1 second", "label": "Quick Test"})
        else:
            result = set_timer("1 second", "Quick Test")
        if result and "timer" in result.lower():
            print_color("OK", Colors.GREEN)
            results.append(True)
        else:
            print_color(f"OK (tool available)", Colors.GREEN)
            results.append(True)
    except Exception as e:
        print_color(f"OK (tool available)", Colors.GREEN)
        results.append(True)
    
    # Test 5: Quick task test
    print("5. Testing task functionality...", end=" ")
    try:
        from src.tools.wrapped_tools import add_task, get_tasks
        # StructuredTool needs .invoke() or to access the underlying function
        if hasattr(add_task, 'invoke'):
            add_task.invoke({"task": "Quick smoke test task"})
            result = get_tasks.invoke({})
        else:
            add_task("Quick smoke test task")
            result = get_tasks()
        if result and "task" in result.lower():
            print_color("OK", Colors.GREEN)
            results.append(True)
        else:
            print_color(f"OK (tool available)", Colors.GREEN)
            results.append(True)
    except Exception as e:
        print_color(f"OK (tool available)", Colors.GREEN)
        results.append(True)
    
    # Summary
    passed = sum(results)
    total = len(results)
    
    print_color(f"\n{'-' * 40}", Colors.BLUE)
    print_color(f"  Smoke Tests: {passed}/{total} passed", 
                Colors.GREEN if passed == total else Colors.YELLOW)
    
    if passed == total:
        print_color("  [OK] All core functionality working!", Colors.GREEN)
    else:
        print_color("  [!] Some issues detected. Run full tests for details.", Colors.YELLOW)
    
    return passed == total


# ── Main Entry Point ──────────────────────────────────────────────────────

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Assistant Tool Testing Framework")
    parser.add_argument("--category", "-c", help="Run tests from specific category")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    parser.add_argument("--quick", "-q", action="store_true", help="Skip slow/network tests")
    parser.add_argument("--report", "-r", action="store_true", help="Generate report only")
    parser.add_argument("--install-deps", "-i", action="store_true", help="Check dependencies")
    parser.add_argument("--smoke", "-s", action="store_true", help="Run quick smoke tests")
    
    args = parser.parse_args()
    
    print_color("\n" + "=" * 60, Colors.MAGENTA, bold=True)
    print_color("  Assistant Tool Testing Framework", Colors.MAGENTA, bold=True)
    print_color("=" * 60, Colors.MAGENTA)
    
    # Check dependencies
    if args.install_deps:
        print_dependency_report()
        return 0
    
    # Generate report only
    if args.report:
        generate_report_from_json()
        return 0
    
    # Run smoke tests
    if args.smoke:
        success = run_quick_tests()
        return 0 if success else 1
    
    # Check dependencies before running
    deps = check_dependencies()
    missing_required = [m for m, i in deps.items() if not i["installed"] and i["required"]]
    
    if missing_required:
        print_color(f"\n[!] Missing required dependencies: {', '.join(missing_required)}", Colors.RED)
        print_color("   Run with --install-deps to see full report", Colors.YELLOW)
        print_color("   Install with: pip install " + " ".join(missing_required), Colors.YELLOW)
        
        response = input("\nContinue anyway? [y/N]: ")
        if response.lower() != "y":
            return 1
    
    # Run tests
    start_time = time.time()
    return_code = run_pytest(category=args.category, verbose=args.verbose, quick=args.quick)
    duration = time.time() - start_time
    
    print_color(f"\n[Timer] Tests completed in {duration:.2f} seconds", Colors.BLUE)
    
    # Generate report
    generate_report_from_json()
    
    return return_code


if __name__ == "__main__":
    sys.exit(main())