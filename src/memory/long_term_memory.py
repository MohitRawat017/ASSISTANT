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
    DATABASE SCHEMA:
    ================
    memories table:
    - id: UUID primary key
    - content: The fact to remember (e.g., "User's name is Mohit")
    - category: Type of fact (name, location, preference, etc.)
    - created_at: When the memory was first saved
    - updated_at: When the memory was last updated
    
    DESIGN DECISIONS:
    =================
    1. SQLite: Simple, reliable, no external dependencies
    2. UUID IDs: Globally unique, no auto-increment coupling
    3. Category index: Fast lookups by category type
    4. Timestamps: Enable "when did I tell you this?" queries
    """
    
    # Valid memory categories - keeps data organized
    CATEGORIES = ["name", "location", "preference", "schedule", "project", "relationship", "other"]
    
    def __init__(self, db_path: str = None):
        from src.utils.config import Config
        self.db_path = db_path or os.path.join(Config.MEMORY_DIR, "long_term.db")
        self._init_db()
    
    def _init_db(self):
        """
        Create memories table if it doesn't exist.
        
        This is called on every instantiation - it's safe to call
        multiple times because of "IF NOT EXISTS".
        
        The index on category speeds up:
        - get_by_category() queries
        - Filtering in get_context_string()
        """
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
            # Index for faster category searches
            conn.execute("CREATE INDEX IF NOT EXISTS idx_category ON memories(category)")
            conn.commit()
    
    def save(self, content: str, category: str = "other") -> str:

        # Validate and normalize category
        category = category.lower() if category.lower() in self.CATEGORIES else "other"
        
        # Check for similar existing memory
        existing = self._find_similar(content)
        if existing:
            # Update existing memory instead of creating duplicate
            self.update(existing["id"], content)
            logger.info(f"[LongTermMemory] Updated existing memory: {content[:50]}...")
            return existing["id"]
        
        # Create new memory with UUID
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
        """
        Delete a memory by ID.
        
        Note: No "forget" tool is currently exposed to the LLM.
        This is intentional - we don't want the assistant to forget
        things without the user explicitly asking.
        
        Args:
            memory_id: UUID of the memory to delete
            
        Returns:
            True on success, False on failure
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
                conn.commit()
            return True
        except Exception as e:
            logger.error(f"[LongTermMemory] Error deleting memory: {e}")
            return False
    
    def get_all(self) -> List[Dict]:
        """
        Get all memories ordered by creation time.
        
        Returns:
            List of memory dictionaries with all fields
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row  # Return dict-like rows
                rows = conn.execute(
                    "SELECT * FROM memories ORDER BY created_at ASC"
                ).fetchall()
                return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"[LongTermMemory] Error loading memories: {e}")
            return []
    
    def get_by_category(self, category: str) -> List[Dict]:
        """
        Get memories filtered by category.
        
        Useful for queries like "what are my preferences?"
        
        Args:
            category: Category to filter by (e.g., "preference", "location")
            
        Returns:
            List of memory dictionaries in that category
        """
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
        
        Args:
            query: Search term to look for in memory content
            limit: Maximum number of results to return
            
        Returns:
            List of matching memory dictionaries
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                # LIKE with wildcards does substring matching
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
        
        This is THE key method for memory injection. It produces a
        human-readable list that gets injected into the LLM's system prompt.
        
        FORMAT:
        =======
        What you know about this user:
        - Name: Mohit
        - Location: Una, HP
        - Wakes up at 7am
        - Prefers dark mode
        - Currently learning LangGraph
        
        The output is designed to be:
        1. Human-readable (LLM processes it naturally)
        2. Organized (important categories first)
        3. Concise (no unnecessary metadata)
        
        Returns:
            Formatted string for system prompt, or empty string if no memories
        """
        memories = self.get_all()
        if not memories:
            return ""
        
        lines = ["What you know about this user:"]
        
        # Group memories by category for organized output
        categorized = {}
        for m in memories:
            cat = m.get("category", "other")
            if cat not in categorized:
                categorized[cat] = []
            categorized[cat].append(m)
        
        # Order categories by priority
        # Name and location first (most personal), then schedule, etc.
        priority_order = ["name", "location", "schedule", "preference", "project", "relationship", "other"]
        
        for cat in priority_order:
            if cat in categorized:
                for m in categorized[cat]:
                    content = m["content"]
                    # Capitalize first letter if needed for consistency
                    if content and content[0].islower():
                        content = content[0].upper() + content[1:]
                    lines.append(f"- {content}")
        
        return "\n".join(lines)
    
    def _find_similar(self, content: str, threshold: float = 0.7) -> Optional[Dict]:
        """
        Find a memory with similar content.
        
        Uses SequenceMatcher for fuzzy matching. This prevents:
        1. Duplicate memories from rephrased statements
        2. Conflicting memories (e.g., old and new wake times)
        
        TWO-STEP MATCHING:
        ==================
        1. Similarity ratio >= threshold (70%)
           Catches: "I live in Una" vs "I'm from Una"
        
        2. One contains the other (substring match)
           Catches: "I wake at 7" vs "I wake at 7am"
        
        Args:
            content: Content to search for similar memories
            threshold: Similarity ratio threshold (0.0 to 1.0)
            
        Returns:
            Similar memory dict if found, None otherwise
        """
        memories = self.get_all()
        content_lower = content.lower()
        
        for m in memories:
            existing = m["content"].lower()
            
            # Check for high similarity ratio
            ratio = SequenceMatcher(None, content_lower, existing).ratio()
            if ratio >= threshold:
                return m
            
            # Also check if one contains the other (for partial updates)
            if content_lower in existing or existing in content_lower:
                return m
        
        return None
    
    def clear_all(self):
        """
        Clear all memories (use with caution).
        
        This is a destructive operation! Mainly useful for:
        - Testing
        - Resetting user data
        - Privacy compliance (GDPR "right to be forgotten")
        
        Returns:
            True on success, False on failure
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("DELETE FROM memories")
                conn.commit()
            logger.warning("[LongTermMemory] All memories cleared")
            return True
        except Exception as e:
            logger.error(f"[LongTermMemory] Error clearing memories: {e}")
            return False

