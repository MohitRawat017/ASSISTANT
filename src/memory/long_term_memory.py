"""
Long-term memory storage for Tsuzi Assistant.
Persists facts about the user across sessions and restarts.
"""

import sqlite3
import uuid
import os
import logging
from datetime import datetime
from typing import Optional, List, Dict
from difflib import SequenceMatcher

logger = logging.getLogger(__name__)


class LongTermMemory:
    """
    SQLite-backed long-term memory storage.
    Stores facts about the user that persist forever.
    Separate from the short-term checkpointer (conversation history).
    """
    
    # Memory categories for organization
    CATEGORIES = ["name", "location", "preference", "schedule", "project", "relationship", "other"]
    
    def __init__(self, db_path: str = None):
        from src.utils.config import Config
        self.db_path = db_path or os.path.join(Config.MEMORY_DIR, "long_term.db")
        self._init_db()
    
    def _init_db(self):
        """Create memories table if needed."""
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS memories (
                    id TEXT PRIMARY KEY,
                    content TEXT NOT NULL,
                    category TEXT DEFAULT 'other',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            # Create index for faster category searches
            conn.execute("CREATE INDEX IF NOT EXISTS idx_category ON memories(category)")
            conn.commit()
    
    def save(self, content: str, category: str = "other") -> str:
        """
        Save a new memory. Returns memory ID.
        If similar memory exists, updates it instead of duplicating.
        """
        category = category.lower() if category.lower() in self.CATEGORIES else "other"
        
        # Check for similar existing memory
        existing = self._find_similar(content)
        if existing:
            # Update existing memory
            self.update(existing["id"], content)
            logger.info(f"[LongTermMemory] Updated existing memory: {content[:50]}...")
            return existing["id"]
        
        # Create new memory
        memory_id = str(uuid.uuid4())
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    "INSERT INTO memories (id, content, category) VALUES (?, ?, ?)",
                    (memory_id, content, category)
                )
                conn.commit()
            logger.info(f"[LongTermMemory] Saved new memory: {content[:50]}...")
            return memory_id
        except Exception as e:
            logger.error(f"[LongTermMemory] Error saving memory: {e}")
            return None
    
    def update(self, memory_id: str, content: str, category: str = None):
        """Update an existing memory."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                if category:
                    conn.execute(
                        "UPDATE memories SET content = ?, category = ?, updated_at = ? WHERE id = ?",
                        (content, category, datetime.now().isoformat(), memory_id)
                    )
                else:
                    conn.execute(
                        "UPDATE memories SET content = ?, updated_at = ? WHERE id = ?",
                        (content, datetime.now().isoformat(), memory_id)
                    )
                conn.commit()
            return True
        except Exception as e:
            logger.error(f"[LongTermMemory] Error updating memory: {e}")
            return False
    
    def delete(self, memory_id: str):
        """Delete a memory."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
                conn.commit()
            return True
        except Exception as e:
            logger.error(f"[LongTermMemory] Error deleting memory: {e}")
            return False
    
    def get_all(self) -> List[Dict]:
        """Get all memories ordered by creation time."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    "SELECT * FROM memories ORDER BY created_at ASC"
                ).fetchall()
                return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"[LongTermMemory] Error loading memories: {e}")
            return []
    
    def get_by_category(self, category: str) -> List[Dict]:
        """Get memories by category."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    "SELECT * FROM memories WHERE category = ? ORDER BY created_at ASC",
                    (category,)
                ).fetchall()
                return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"[LongTermMemory] Error loading memories by category: {e}")
            return []
    
    def search(self, query: str, limit: int = 5) -> List[Dict]:
        """
        Search memories by content (case-insensitive substring match).
        Returns memories containing the query string.
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    "SELECT * FROM memories WHERE content LIKE ? ORDER BY created_at DESC LIMIT ?",
                    (f"%{query}%", limit)
                ).fetchall()
                return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"[LongTermMemory] Error searching memories: {e}")
            return []
    
    def get_context_string(self) -> str:
        """
        Get all memories formatted as a context string for the system prompt.
        Returns formatted string like:
        - Name: [name]
        - Location: Una, HP
        - Wakes up at 7am
        ...
        """
        memories = self.get_all()
        if not memories:
            return ""
        
        lines = ["What you know about this user:"]
        
        # Group by category for better organization
        categorized = {}
        for m in memories:
            cat = m.get("category", "other")
            if cat not in categorized:
                categorized[cat] = []
            categorized[cat].append(m)
        
        # Order: name first, then location, then others
        priority_order = ["name", "location", "schedule", "preference", "project", "relationship", "other"]
        
        for cat in priority_order:
            if cat in categorized:
                for m in categorized[cat]:
                    content = m["content"]
                    # Capitalize first letter if needed
                    if content and content[0].islower():
                        content = content[0].upper() + content[1:]
                    lines.append(f"- {content}")
        
        return "\n".join(lines)
    
    def _find_similar(self, content: str, threshold: float = 0.7) -> Optional[Dict]:
        """
        Find a memory with similar content.
        Uses SequenceMatcher for fuzzy matching.
        Returns the memory dict if found, None otherwise.
        """
        memories = self.get_all()
        content_lower = content.lower()
        
        for m in memories:
            existing = m["content"].lower()
            # Check for high similarity
            ratio = SequenceMatcher(None, content_lower, existing).ratio()
            if ratio >= threshold:
                return m
            
            # Also check if one contains the other (for partial updates)
            if content_lower in existing or existing in content_lower:
                return m
        
        return None
    
    def clear_all(self):
        """Clear all memories (use with caution)."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("DELETE FROM memories")
                conn.commit()
            logger.warning("[LongTermMemory] All memories cleared")
            return True
        except Exception as e:
            logger.error(f"[LongTermMemory] Error clearing memories: {e}")
            return False