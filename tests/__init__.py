"""
Assistant Tool Testing Framework

This package contains comprehensive tests for all assistant tools and managers.

Usage:
    # Run all tests
    python tests/run_tests.py
    
    # Run quick smoke tests
    python tests/run_tests.py --smoke
    
    # Run specific category
    python tests/run_tests.py --category core
    
    # Check dependencies
    python tests/run_tests.py --install-deps
    
    # Or use pytest directly
    pytest tests/ -v
"""

from tests.conftest import check_dependency, skip_if_missing

__all__ = ["check_dependency", "skip_if_missing"]