"""Durable SQLite checkpointing for the LangGraph agent.

The installed ``langgraph-checkpoint-sqlite`` package exposes a synchronous
``SqliteSaver`` whose async methods intentionally raise ``NotImplementedError``.
This adapter keeps one SQLite connection for the process and bridges the async
methods through worker threads, preserving the existing sync and async agent
entry points without maintaining two independent checkpoint stores.
"""

from __future__ import annotations

import asyncio
import os
import sqlite3
from collections.abc import AsyncIterator, Sequence
from typing import Any

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.checkpoint.base import (
    ChannelVersions,
    Checkpoint,
    CheckpointMetadata,
    CheckpointTuple,
)
from langchain_core.runnables import RunnableConfig


class PersistentSqliteSaver(SqliteSaver):
    """A process-lifetime, sync/async-compatible SQLite checkpoint saver."""

    def __init__(self, db_path: str, *, busy_timeout_ms: int = 10_000) -> None:
        self.db_path = os.path.abspath(db_path)
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        timeout_seconds = max(1, int(busy_timeout_ms)) / 1000
        connection = sqlite3.connect(
            self.db_path,
            timeout=timeout_seconds,
            check_same_thread=False,
        )
        super().__init__(connection)
        self.busy_timeout_ms = max(1, int(busy_timeout_ms))
        connection.execute(f"PRAGMA busy_timeout={self.busy_timeout_ms}")
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=NORMAL")
        self.setup()

    async def aput(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: ChannelVersions,
    ) -> RunnableConfig:
        return await asyncio.to_thread(
            self.put, config, checkpoint, metadata, new_versions
        )

    async def aput_writes(
        self,
        config: RunnableConfig,
        writes: Sequence[tuple[str, Any]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        await asyncio.to_thread(self.put_writes, config, writes, task_id, task_path)

    async def aget(self, config: RunnableConfig) -> Checkpoint | None:
        value = await self.aget_tuple(config)
        return value.checkpoint if value else None

    async def aget_tuple(self, config: RunnableConfig) -> CheckpointTuple | None:
        return await asyncio.to_thread(self.get_tuple, config)

    async def alist(
        self,
        config: RunnableConfig | None,
        *,
        filter: dict[str, Any] | None = None,
        before: RunnableConfig | None = None,
        limit: int | None = None,
    ) -> AsyncIterator[CheckpointTuple]:
        values = await asyncio.to_thread(
            lambda: list(
                self.list(config, filter=filter, before=before, limit=limit)
            )
        )
        for value in values:
            yield value

    async def adelete_thread(self, thread_id: str) -> None:
        await asyncio.to_thread(self.delete_thread, thread_id)

    async def aprune(
        self,
        thread_ids: Sequence[str],
        *,
        strategy: str = "keep_latest",
    ) -> None:
        await asyncio.to_thread(self.prune, thread_ids, strategy=strategy)

    def prune(
        self,
        thread_ids: Sequence[str],
        *,
        strategy: str = "keep_latest",
    ) -> None:
        """Prune checkpoint rows using the schema owned by the saver package.

        ``langgraph-checkpoint-sqlite==3.1.2`` leaves this base method
        unimplemented. The normal graph uses full channel snapshots, so
        retaining the latest checkpoint per namespace preserves the resumable
        state while bounding unneeded historical rows.
        """
        if strategy not in {"keep_latest", "delete"}:
            raise ValueError("strategy must be 'keep_latest' or 'delete'")
        with self.cursor() as cur:
            for thread_id in thread_ids:
                if strategy == "delete":
                    cur.execute("DELETE FROM writes WHERE thread_id = ?", (str(thread_id),))
                    cur.execute("DELETE FROM checkpoints WHERE thread_id = ?", (str(thread_id),))
                    continue

                rows = cur.execute(
                    "SELECT checkpoint_ns, checkpoint_id FROM checkpoints "
                    "WHERE thread_id = ? ORDER BY checkpoint_ns, checkpoint_id DESC",
                    (str(thread_id),),
                ).fetchall()
                latest: set[str] = set()
                for namespace, checkpoint_id in rows:
                    if namespace not in latest:
                        latest.add(namespace)
                        continue
                    cur.execute(
                        "DELETE FROM writes WHERE thread_id = ? AND checkpoint_ns = ? AND checkpoint_id = ?",
                        (str(thread_id), namespace, checkpoint_id),
                    )
                    cur.execute(
                        "DELETE FROM checkpoints WHERE thread_id = ? AND checkpoint_ns = ? AND checkpoint_id = ?",
                        (str(thread_id), namespace, checkpoint_id),
                    )

    def close(self) -> None:
        """Close the process-lifetime SQLite connection."""
        self.conn.close()


def build_checkpoint_saver(
    db_path: str,
    *,
    busy_timeout_ms: int = 10_000,
) -> PersistentSqliteSaver:
    """Create and initialize the application's durable checkpoint store."""
    return PersistentSqliteSaver(db_path, busy_timeout_ms=busy_timeout_ms)
