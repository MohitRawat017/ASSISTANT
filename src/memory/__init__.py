"""
Memory package for Tsuzi Assistant.
- Long-term memory: Persistent facts about the user across sessions
"""

from .long_term_memory import LongTermMemory

__all__ = ["LongTermMemory"]