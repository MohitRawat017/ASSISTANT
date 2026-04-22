"""
Pytest configuration and fixtures for assistant tool testing.

This module provides shared fixtures, configuration, and utility functions
for testing the assistant's tools and managers.
"""

import os
import sys
import time
import json
import pytest
from datetime import datetime
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Test results directory
RESULTS_DIR = PROJECT_ROOT / "tests" / "test_results"
RESULTS_DIR.mkdir(exist_ok=True)

# Track test results for reporting
test_results = {
    "start_time": None,
    "end_time": None,
    "tests": [],
    "summary": {
        "total": 0,
        "passed": 0,
        "failed": 0,
        "skipped": 0,
        "errors": []
    }
}


def pytest_addoption(parser):
    parser.addoption(
        "--no-test-report",
        action="store_true",
        default=False,
        help="Do not write generated files under tests/test_results.",
    )


def pytest_unconfigure(config):
    """Called after all tests complete."""
    if config.getoption("--no-test-report", default=False):
        return

    test_results["end_time"] = datetime.now().isoformat()
    
    # Save detailed log
    log_path = RESULTS_DIR / "detailed_log.json"
    with open(log_path, "w") as f:
        json.dump(test_results, f, indent=2)
    
    # Generate markdown report
    generate_report()


def pytest_runtest_logreport(report):
    """Track each test result."""
    if report.when == "call":
        test_results["summary"]["total"] += 1
        
        result = {
            "name": report.nodeid,
            "outcome": report.outcome,
            "duration": getattr(report, "duration", 0),
            "timestamp": datetime.now().isoformat()
        }
        
        if report.outcome == "passed":
            test_results["summary"]["passed"] += 1
        elif report.outcome == "failed":
            test_results["summary"]["failed"] += 1
            if hasattr(report, "longrepr"):
                result["error"] = str(report.longrepr)
                test_results["summary"]["errors"].append({
                    "test": report.nodeid,
                    "error": str(report.longrepr)[:500]
                })
        elif report.outcome == "skipped":
            test_results["summary"]["skipped"] += 1
        
        test_results["tests"].append(result)


def generate_report():
    """Generate a human-readable markdown report."""
    summary = test_results["summary"]
    
    # Calculate health score
    if summary["total"] > 0:
        health_score = (summary["passed"] / summary["total"]) * 100
    else:
        health_score = 0
    
    lines = [
        "# Assistant Tool Test Report",
        "",
        f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"**Duration:** {test_results['start_time']} to {test_results['end_time']}",
        "",
        "---",
        "",
        "## Summary",
        "",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Total Tests | {summary['total']} |",
        f"| Passed | {summary['passed']} |",
        f"| Failed | {summary['failed']} |",
        f"| Skipped | {summary['skipped']} |",
        f"| **Health Score** | **{health_score:.1f}%** |",
        "",
    ]
    
    # Add failures section
    if summary["errors"]:
        lines.extend([
            "---",
            "",
            "## Errors",
            ""
        ])
        for err in summary["errors"][:10]:  # Limit to 10 errors
            lines.append(f"### {err['test']}")
            lines.append(f"```\n{err['error']}\n```")
            lines.append("")
    
    # Add test results by category
    lines.extend([
        "---",
        "",
        "## Test Details",
        ""
    ])
    
    for test in test_results["tests"]:
        status = "✅" if test["outcome"] == "passed" else "❌" if test["outcome"] == "failed" else "⏭️"
        lines.append(f"- {status} {test['name']} ({test['duration']:.2f}s)")
    
    # Write report
    report_path = RESULTS_DIR / "latest_report.md"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    
    # Write errors file
    if summary["errors"]:
        errors_path = RESULTS_DIR / "errors.txt"
        with open(errors_path, "w", encoding="utf-8") as f:
            for err in summary["errors"]:
                f.write(f"=== {err['test']} ===\n")
                f.write(f"{err['error']}\n\n")


# ── Fixtures ─────────────────────────────────────────────────────────────

@pytest.fixture
def project_root():
    """Return project root path."""
    return PROJECT_ROOT


@pytest.fixture
def data_dir(project_root):
    """Return data directory path."""
    return project_root / "data"


@pytest.fixture
def test_db_path(tmp_path):
    """Return a temporary database path for isolated testing."""
    return str(tmp_path / "test.db")


@pytest.fixture
def clean_env():
    """Save and restore environment variables."""
    original = os.environ.copy()
    yield
    # Restore
    os.environ.clear()
    os.environ.update(original)


@pytest.fixture
def mock_email_env(clean_env):
    """Set mock email environment variables."""
    os.environ["GMAIL_ADDRESS"] = "test@example.com"
    os.environ["GMAIL_APP_PASSWORD"] = "test_password"
    os.environ["REMINDER_EMAIL"] = "recipient@example.com"


# ── Helper Functions ──────────────────────────────────────────────────────

def check_dependency(module_name: str) -> bool:
    """Check if a module is available."""
    try:
        __import__(module_name)
        return True
    except ImportError:
        return False


def skip_if_missing(module_name: str):
    """Decorator/skip marker for tests requiring optional dependencies."""
    return pytest.mark.skipif(
        not check_dependency(module_name),
        reason=f"Missing dependency: {module_name}"
    )


def pytest_configure(config):
    """Called before test collection."""
    test_results["start_time"] = datetime.now().isoformat()

    # Category markers for organizing tests
    config.addinivalue_line("markers", "safe_smoke: deterministic smoke tests safe for CI")
    config.addinivalue_line("markers", "side_effect: tests that may mutate desktop, network, credentials, or local state")
    config.addinivalue_line("markers", "core: Core tools tests (alarm, calendar, tasks, etc.)")
    config.addinivalue_line("markers", "pc_control: PC control tests (volume, brightness, etc.)")
    config.addinivalue_line("markers", "file_ops: File operation tests")
    config.addinivalue_line("markers", "research: Research tool tests (web search, etc.)")
    config.addinivalue_line("markers", "habits: Habit tracking tests")
    config.addinivalue_line("markers", "email: Email tests (require credentials)")
    config.addinivalue_line("markers", "integration: Integration tests")
    config.addinivalue_line("markers", "requires_network: Tests that need internet")
    config.addinivalue_line("markers", "requires_gmail: Tests that need Gmail credentials")
