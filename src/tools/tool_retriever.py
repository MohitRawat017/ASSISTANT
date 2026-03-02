# src/tools/tool_retriever.py
"""
Embedding-based tool retriever for dynamic tool selection.

Instead of matching keywords (brittle, misses paraphrases), we embed
both tool descriptions and the user query into the same vector space,
then pick the tools whose embeddings are closest to the query.

This means "remind me to buy milk" correctly matches `add_task`
even though the word "task" never appears in the query.
"""

import os
import json
import hashlib
import logging
from datetime import datetime
from typing import List, Optional

import numpy as np
from sentence_transformers import SentenceTransformer
from src.tools.wrapped_tools import ALL_TOOLS
from src.utils.config import Config

logger = logging.getLogger(__name__)

# ── Cache & log paths ────────────────────────────────────────────────────
# We store these in /data so they persist across runs but stay out of src/
CACHE_DIR = os.path.join(Config.BASE_DIR, "data")
EMBEDDING_CACHE_PATH = os.path.join(CACHE_DIR, "tool_embeddings.npy")
HASH_CACHE_PATH = os.path.join(CACHE_DIR, "tool_embeddings_hash.txt")
RETRIEVAL_LOG_PATH = os.path.join(CACHE_DIR, "retrieval_log.jsonl")


class ToolRetriever:
    """
    Picks the most relevant tools for a user query using cosine similarity
    between sentence embeddings.

    Why embeddings over keywords?
    - Keywords fail on paraphrases ("start chrome" vs "open chrome")
    - Keywords need manual maintenance every time a tool changes
    - Embeddings generalize to queries we never explicitly listed
    """

    def __init__(self, top_k: int = 5, min_similarity: float = 0.25):
        """
        Args:
            top_k: Max tools to return. 5 is a good balance — enough to
                cover multi-intent queries, few enough to not bloat context.
            min_similarity: Floor score (0–1). Tools scoring below this are
                dropped UNLESS it would leave us with zero tools (we always
                return at least one).
        """
        self.top_k = top_k
        self.min_similarity = min_similarity
        self.tools = ALL_TOOLS

        # all-MiniLM-L6-v2: 384-dim embeddings, ~80MB, fast on CPU.
        # Good enough for short sentences (tool descriptions are 1-3 lines).
        # Heavier models (e.g. all-mpnet-base-v2) give ~2% better accuracy
        # but are 3x slower — not worth it for 13 tools.
        logger.info("Loading embedding model (all-MiniLM-L6-v2)...")
        self.embedder = SentenceTransformer("all-MiniLM-L6-v2")
        logger.info("Embedding model loaded.")

        self._build_index()

    # ── Index building ───────────────────────────────────────────────────

    def _get_tool_doc(self, tool) -> str:
        """
        Build a rich text representation of a tool for embedding.

        We combine name + description + argument names because:
        - Name alone is too short for meaningful embeddings
        - Description carries the semantic meaning
        - Arg names help disambiguate similar tools
          (e.g. "duration" helps distinguish timer from alarm)
        """
        doc = f"{tool.name}: {tool.description}"

        # Pull argument info from the Pydantic schema that LangChain
        # auto-generates for each @tool function
        if hasattr(tool, "args_schema") and tool.args_schema:
            try:
                # Pydantic V2 uses model_json_schema(), V1 used schema()
                if hasattr(tool.args_schema, "model_json_schema"):
                    schema = tool.args_schema.model_json_schema()
                else:
                    schema = tool.args_schema.schema()
                props = schema.get("properties", {})
                if props:
                    # Format: "duration (str), label (str)"
                    args_str = ", ".join(
                        f"{name} ({info.get('type', 'str')})"
                        for name, info in props.items()
                    )
                    doc += f" | Args: {args_str}"
            except Exception:
                # Schema parsing isn't critical — skip silently
                pass

        return doc

    def _compute_docs_hash(self, tool_docs: List[str]) -> str:
        """
        SHA-256 hash of all tool docs concatenated.

        We use this to detect when tool descriptions change, so we know
        to re-encode instead of using stale cached embeddings.
        """
        combined = "\n".join(tool_docs)
        return hashlib.sha256(combined.encode()).hexdigest()

    def _try_load_cache(self, current_hash: str) -> Optional[np.ndarray]:
        """
        Load embeddings from disk if:
        1. Cache files exist
        2. The stored hash matches current tool docs
        3. The array shape matches the current tool count

        This saves ~1-2s on startup since we skip re-encoding.
        """
        try:
            if os.path.exists(HASH_CACHE_PATH) and os.path.exists(EMBEDDING_CACHE_PATH):
                with open(HASH_CACHE_PATH, "r") as f:
                    cached_hash = f.read().strip()
                if cached_hash == current_hash:
                    embeddings = np.load(EMBEDDING_CACHE_PATH)
                    logger.info("Loaded tool embeddings from disk cache.")
                    return embeddings
        except Exception as e:
            logger.warning(f"Cache load failed, will re-encode: {e}")
        return None

    def _save_cache(self, embeddings: np.ndarray, doc_hash: str):
        """Save embeddings + hash to disk for next cold start."""
        try:
            os.makedirs(CACHE_DIR, exist_ok=True)
            np.save(EMBEDDING_CACHE_PATH, embeddings)
            with open(HASH_CACHE_PATH, "w") as f:
                f.write(doc_hash)
            logger.info("Tool embeddings cached to disk.")
        except Exception as e:
            logger.warning(f"Failed to cache embeddings: {e}")

    def _build_index(self):
        """
        Embed all tool descriptions and store the vectors.

        Flow:
        1. Build text docs from all tools
        2. Hash the docs to check if anything changed
        3. Try loading cached embeddings (fast path)
        4. If cache miss → re-encode with SentenceTransformer (slow path)
        5. Save new embeddings to disk for next time
        """
        self.tool_docs = [self._get_tool_doc(tool) for tool in self.tools]
        doc_hash = self._compute_docs_hash(self.tool_docs)

        # Fast path: load from cache if tool docs haven't changed
        cached = self._try_load_cache(doc_hash)
        if cached is not None and cached.shape[0] == len(self.tools):
            self.tool_embeddings = cached
            return

        # Slow path: encode all tool docs from scratch
        logger.info(f"Encoding {len(self.tools)} tool descriptions...")
        self.tool_embeddings = self.embedder.encode(
            self.tool_docs,
            # Normalize so dot product = cosine similarity (saves a step later)
            normalize_embeddings=True,
            show_progress_bar=False
        )
        self._save_cache(self.tool_embeddings, doc_hash)
        logger.info("Tool index built and cached.")

    def rebuild_index(self):
        """
        Re-index all tools. Call this if you add/remove tools at runtime
        or update docstrings without restarting the app.
        """
        self.tools = ALL_TOOLS
        self._build_index()

    # ── Retrieval ────────────────────────────────────────────────────────

    def _log_retrieval(self, query: str, selected: List[dict]):
        """
        Append a retrieval record to the JSONL log.

        This log is invaluable for tuning: you can review which tools
        get selected for which queries, spot mismatches, and adjust
        docstrings or thresholds accordingly.

        Format: one JSON object per line (easy to parse with pandas).
        """
        try:
            os.makedirs(os.path.dirname(RETRIEVAL_LOG_PATH), exist_ok=True)
            record = {
                "timestamp": datetime.now().isoformat(),
                "query": query,
                "tools": [
                    {"name": t["name"], "score": round(t["score"], 4)}
                    for t in selected
                ]
            }
            with open(RETRIEVAL_LOG_PATH, "a", encoding="utf-8") as f:
                f.write(json.dumps(record) + "\n")
        except Exception as e:
            # Logging failure is non-critical — don't crash the retrieval
            logger.debug(f"Failed to log retrieval: {e}")

    def get_tools(self, query: str, conversation_history: list = None) -> list:
        """
        Return the most relevant tools for a user query.

        Steps:
        1. Build enriched query with conversation context (if provided)
        2. Embed the query into the same vector space as tools
        3. Compute cosine similarity with all tool embeddings
        4. Rank by score, take top_k
        5. Filter out tools below min_similarity threshold
        6. Return fallback tools if no tools match.

        Args:
            query: The user's natural language input.
            conversation_history: Optional list of recent message strings.
                Helps disambiguate follow-up queries like "yea" or "yes"
                by combining with previous context.

        Returns:
            List of LangChain tool objects, best match first.
            Falls back to web_search if no tools match above threshold.
        """
        # Build enriched query with conversation context
        enriched_query = query
        if conversation_history:
            # Take last 3 messages as context
            context = " | ".join(conversation_history[-3:])
            enriched_query = f"{context} | {query}"
            logger.debug(f"Enriched query: '{enriched_query}'")

        # Embed the query — must use same normalization as tool embeddings
        query_embedding = self.embedder.encode(
            enriched_query,
            normalize_embeddings=True
        )

        # Cosine similarity = dot product when both vectors are normalized.
        # Result shape: (num_tools,) — one score per tool.
        scores = np.dot(self.tool_embeddings, query_embedding)

        # Sort indices by score, highest first
        ranked_indices = np.argsort(scores)[::-1]

        # Pick top_k tools that meet the similarity threshold.
        selected = []
        for i in ranked_indices[:self.top_k]:
            score = float(scores[i])
            if score >= self.min_similarity:
                selected.append({
                    "index": int(i),
                    "name": self.tools[i].name,
                    "score": score
                })

        # Log for analysis (non-blocking, won't crash on failure)
        self._log_retrieval(query, selected)

        # Debug output
        if selected:
            logger.info(f"Query: '{query}' → {[s['name'] for s in selected]}")
            for s in selected:
                logger.debug(f"  {s['name']}: {s['score']:.3f}")
        else:
            # When no tools match, return fallback (web_search)
            logger.info(f"Query: '{query}' → no tools matched, using fallback: web_search")
            return FALLBACK_TOOLS

        return [self.tools[s["index"]] for s in selected]


# ── Fallback Tools ────────────────────────────────────────────────────────
# When no tools match the query above the similarity threshold, we provide
# a fallback set of "universal" tools that can handle most general queries.
# This prevents the LLM from hallucinating tool names when no tools are
# provided (which caused raw JSON output like {"name": "weather", ...}).
#
# web_search is ideal as fallback because:
# - It handles factual queries (weather, news, definitions)
# - It can find research papers, tutorials, etc.
# - It's safe and doesn't modify system state
from src.tools.wrapped_tools import web_search

FALLBACK_TOOLS = [web_search]


# ── Singleton ────────────────────────────────────────────────────────────
# Why a singleton?
# The SentenceTransformer model takes ~2s to load. Creating a new instance
# per query would be wasteful. Instead, we load once and reuse forever.
# The get_retriever() function is the public API — import this, not the class.

_retriever: Optional[ToolRetriever] = None


def get_retriever(top_k: int = 5, min_similarity: float = 0.25) -> ToolRetriever:
    """
    Get or create the singleton ToolRetriever.

    First call creates the instance (loads model + builds index).
    All subsequent calls return the same instance instantly.

    Args:
        top_k: Max tools per query (only used on first call).
        min_similarity: Min score threshold (only used on first call).
            0.4 is a good balance — high enough to filter out casual
            greetings, low enough to catch paraphrased tool requests.
    """
    global _retriever
    if _retriever is None:
        _retriever = ToolRetriever(top_k=top_k, min_similarity=min_similarity)
    return _retriever