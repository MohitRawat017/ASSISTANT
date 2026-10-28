"""Durable alarm lifecycle persistence and atomic delivery transitions."""

from __future__ import annotations

import logging
import os
import sqlite3
import uuid
from datetime import datetime, timedelta
from typing import Any

from src.scheduler_windows import WindowsScheduler
from src.utils.config import Config
from src.utils.reliability import ToolResult, stable_operation_id

logger = logging.getLogger(__name__)
DATA_DIR = os.path.join(Config.BASE_DIR, "data")


class AlarmManager:
    """SQLite-backed alarm store.

    The schema intentionally remains provider-neutral.  ``notified`` and the
    original ``time``/``scheduled_task_name`` columns are retained for old
    databases and standalone reminder processes.
    """

    def __init__(self, db_path: str | None = None):
        self.db_path = db_path or os.path.join(DATA_DIR, "alarms.db")
        self.init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

    @staticmethod
    def _now(value: datetime | str | None = None) -> datetime:
        if value is None:
            return datetime.now()
        if isinstance(value, datetime):
            return value
        return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)

    @staticmethod
    def _iso(value: datetime | str | None = None) -> str:
        return AlarmManager._now(value).isoformat(timespec="seconds")

    def init_db(self) -> None:
        db_dir = os.path.dirname(self.db_path)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS alarms (
                    id TEXT PRIMARY KEY,
                    time TEXT NOT NULL,
                    label TEXT,
                    enabled BOOLEAN DEFAULT 1,
                    notified BOOLEAN DEFAULT 0,
                    scheduled_task_name TEXT,
                    target_at TEXT,
                    occurrence TEXT DEFAULT 'daily',
                    lifecycle TEXT DEFAULT 'active',
                    status TEXT DEFAULT 'active',
                    schedule_state TEXT DEFAULT 'pending',
                    delivery_state TEXT DEFAULT 'pending',
                    cleanup_state TEXT DEFAULT 'pending',
                    delivery_claim TEXT,
                    delivery_lease TEXT,
                    delivery_claimed_at TEXT,
                    delivery_lease_until TEXT,
                    attempt_count INTEGER DEFAULT 0,
                    last_attempt_at TEXT,
                    last_error TEXT,
                    last_hint TEXT,
                    operation_id TEXT
                )
                """
            )
            self.migrate(conn)

    def migrate(self, conn: sqlite3.Connection) -> None:
        """Add R3 columns to databases created by earlier releases."""
        existing = {row[1] for row in conn.execute("PRAGMA table_info(alarms)").fetchall()}
        lifecycle_was_missing = "lifecycle" not in existing
        status_was_missing = "status" not in existing
        schedule_was_missing = "schedule_state" not in existing
        delivery_was_missing = "delivery_state" not in existing
        cleanup_was_missing = "cleanup_state" not in existing
        columns = {
            "notified": "BOOLEAN DEFAULT 0",
            "scheduled_task_name": "TEXT",
            "target_at": "TEXT",
            "occurrence": "TEXT DEFAULT 'once'",
            "lifecycle": "TEXT DEFAULT 'active'",
            "status": "TEXT DEFAULT 'active'",
            "schedule_state": "TEXT DEFAULT 'pending'",
            "delivery_state": "TEXT DEFAULT 'pending'",
            "cleanup_state": "TEXT DEFAULT 'pending'",
            "delivery_claim": "TEXT",
            "delivery_lease": "TEXT",
            "delivery_claimed_at": "TEXT",
            "delivery_lease_until": "TEXT",
            "attempt_count": "INTEGER DEFAULT 0",
            "last_attempt_at": "TEXT",
            "last_error": "TEXT",
            "last_hint": "TEXT",
            "operation_id": "TEXT",
        }
        for name, definition in columns.items():
            if name not in existing:
                conn.execute(f"ALTER TABLE alarms ADD COLUMN {name} {definition}")

        # Generic per-run/channel audit rows avoid provider-specific columns.
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS alarm_delivery_attempts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                alarm_id TEXT NOT NULL,
                attempt_id TEXT,
                channel TEXT NOT NULL,
                state TEXT NOT NULL,
                code TEXT,
                error TEXT,
                hint TEXT,
                operation_id TEXT,
                created_at TEXT NOT NULL
            )
            """
        )
        # Normalize NULLs introduced by ALTER TABLE while preserving notified.
        # Preserve explicit lifecycle states during every startup migration.
        if lifecycle_was_missing:
            conn.execute("UPDATE alarms SET lifecycle = CASE WHEN notified = 1 THEN 'delivered' WHEN enabled = 0 THEN 'disabled' ELSE 'active' END")
        else:
            conn.execute("UPDATE alarms SET lifecycle = CASE WHEN lifecycle IS NULL OR lifecycle = '' THEN CASE WHEN notified = 1 THEN 'delivered' WHEN enabled = 0 THEN 'disabled' ELSE 'active' END ELSE lifecycle END")
        if status_was_missing:
            conn.execute("UPDATE alarms SET status = lifecycle")
        else:
            conn.execute("UPDATE alarms SET status = lifecycle WHERE status IS NULL OR status = ''")
        if schedule_was_missing:
            conn.execute("UPDATE alarms SET schedule_state = CASE WHEN scheduled_task_name IS NOT NULL AND scheduled_task_name != '' THEN 'scheduled' ELSE 'pending' END")
        else:
            conn.execute("UPDATE alarms SET schedule_state = COALESCE(schedule_state, 'pending')")
        if delivery_was_missing:
            conn.execute("UPDATE alarms SET delivery_state = CASE WHEN notified = 1 THEN 'succeeded' ELSE 'pending' END")
        else:
            conn.execute("UPDATE alarms SET delivery_state = COALESCE(delivery_state, 'pending')")
        if cleanup_was_missing:
            conn.execute("UPDATE alarms SET cleanup_state = 'pending'")
        else:
            conn.execute("UPDATE alarms SET cleanup_state = COALESCE(cleanup_state, 'pending')")
        conn.execute("UPDATE alarms SET attempt_count = COALESCE(attempt_count, 0)")
        # Populate durable values for rows created by R1/R2 without changing
        # their original time or notified semantics.
        for row in conn.execute("SELECT id, time, target_at, operation_id FROM alarms").fetchall():
            target = row[2] or self._target_for_time(row[1])
            operation_id = row[3] or stable_operation_id("alarm", "schedule", row[0])
            conn.execute("UPDATE alarms SET target_at = ?, operation_id = ? WHERE id = ?", (target, operation_id, row[0]))
        conn.commit()

    def _target_for_time(self, time: str, now: datetime | None = None) -> str:
        current = self._now(now)
        hour, minute = map(int, time.split(":"))
        target = current.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if target <= current:
            target += timedelta(days=1)
        return self._iso(target)

    def add_alarm(
        self,
        time: str,
        label: str = "Alarm",
        *,
        target_at: datetime | str | None = None,
        occurrence: str = "once",
        operation_id: str | None = None,
    ) -> str | None:
        try:
            datetime.strptime(time, "%H:%M")
        except ValueError:
            logger.error("[AlarmManager] Invalid time '%s' (expected HH:MM)", time)
            return None
        alarm_id = str(uuid.uuid4())
        target = self._iso(target_at) if target_at else self._target_for_time(time)
        op_id = operation_id or stable_operation_id("alarm", "schedule", alarm_id)
        try:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO alarms
                    (id, time, label, target_at, occurrence, lifecycle, status,
                     schedule_state, delivery_state, cleanup_state, operation_id)
                    VALUES (?, ?, ?, ?, ?, 'active', 'active', 'pending',
                            'pending', 'pending', ?)
                    """,
                    (alarm_id, time, label, target, occurrence, op_id),
                )
                conn.commit()
            return alarm_id
        except Exception as exc:
            logger.error("[AlarmManager] Error adding alarm: %s", exc)
            return None

    def get_alarms(self) -> list[dict[str, Any]]:
        try:
            with self._connect() as conn:
                return [dict(row) for row in conn.execute("SELECT * FROM alarms ORDER BY target_at, time ASC")]
        except Exception as exc:
            logger.error("[AlarmManager] Error loading alarms: %s", exc)
            return []

    def get_alarm_by_id(self, alarm_id: str) -> dict[str, Any] | None:
        try:
            with self._connect() as conn:
                row = conn.execute("SELECT * FROM alarms WHERE id = ?", (alarm_id,)).fetchone()
                return dict(row) if row else None
        except Exception as exc:
            logger.error("[AlarmManager] Error fetching alarm: %s", exc)
            return None

    def _update(self, alarm_id: str, values: dict[str, Any], *, where: str = "", params: tuple = ()) -> bool:
        if not values:
            return False
        assignments = ", ".join(f"{key} = ?" for key in values)
        try:
            with self._connect() as conn:
                cur = conn.execute(
                    f"UPDATE alarms SET {assignments} WHERE id = ? {where}",
                    tuple(values.values()) + (alarm_id,) + params,
                )
                conn.commit()
                return cur.rowcount == 1
        except sqlite3.Error as exc:
            logger.error("[AlarmManager] transition failed for %s: %s", alarm_id, exc)
            return False

    def set_schedule_state(
        self, alarm_id: str, state: str, *, task_name: str | None = None,
        code: str | None = None, hint: str | None = None, error: str | None = None,
    ) -> bool:
        values: dict[str, Any] = {"schedule_state": state, "last_hint": hint, "last_error": error}
        if task_name is not None:
            values["scheduled_task_name"] = task_name
        return self._update(alarm_id, values)

    def set_scheduled_task(self, alarm_id: str, task_name: str) -> bool:
        return self._update(
            alarm_id,
            {"schedule_state": "scheduled", "scheduled_task_name": task_name, "last_hint": None, "last_error": None},
            where="AND enabled = 1 AND lifecycle NOT IN ('disabled', 'cancelled', 'delivered', 'delivery_unknown')",
        )

    def claim_for_delivery(
        self, alarm_id: str, *, now: datetime | str | None = None,
        lease_seconds: int = 300, claim_token: str | None = None,
    ) -> dict[str, Any] | None:
        current = self._now(now)
        now_text = self._iso(current)
        lease_until = self._iso(current + timedelta(seconds=lease_seconds))
        token = claim_token or uuid.uuid4().hex
        try:
            with self._connect() as conn:
                cur = conn.execute(
                    """
                    UPDATE alarms
                       SET delivery_claim = ?, delivery_lease = ?, delivery_claimed_at = ?,
                           delivery_lease_until = ?, delivery_state = 'claimed',
                           attempt_count = COALESCE(attempt_count, 0) + 1,
                           last_attempt_at = ?
                     WHERE id = ? AND enabled = 1 AND notified = 0
                       AND lifecycle NOT IN ('disabled', 'cancelled', 'delivered', 'delivery_unknown')
                       AND delivery_state IN ('pending', 'failed', 'overdue')
                       AND (delivery_claim IS NULL OR delivery_claim = '')
                    """,
                    (token, lease_until, now_text, lease_until, now_text, alarm_id),
                )
                if cur.rowcount != 1:
                    conn.rollback()
                    return None
                row = conn.execute("SELECT * FROM alarms WHERE id = ?", (alarm_id,)).fetchone()
                conn.commit()
                return dict(row) if row else None
        except sqlite3.Error as exc:
            logger.error("[AlarmManager] claim failed for %s: %s", alarm_id, exc)
            return None

    # Alias used by reconciliation/consumers that prefer an explicit name.
    claim_delivery = claim_for_delivery

    def _claimed_update(self, alarm_id: str, claim: str | None, values: dict[str, Any]) -> bool:
        # Completion must carry the worker's claim. A cancelled/disabled row
        # can never be overwritten by a worker that started before the state
        # transition.
        if not claim:
            return False
        where = "AND delivery_claim = ? AND lifecycle NOT IN ('disabled', 'cancelled')"
        params = (claim,)
        return self._update(alarm_id, values, where=where, params=params)

    def record_channel_outcome(
        self, alarm_id: str, channel: str, result: ToolResult | dict[str, Any] | bool,
        *, attempt_id: str | None = None, now: datetime | str | None = None,
    ) -> bool:
        if isinstance(result, bool):
            state, code, error, hint, op_id = ("succeeded", "ok", None, "", None) if result else ("failed", "delivery_failed", "delivery failed", "Try again later.", None)
        else:
            state = "succeeded" if result.get("ok", result.get("success", False)) else ("unknown" if result.get("unknown_outcome") else "failed")
            code = result.get("code")
            error = result.get("error")
            hint = result.get("hint")
            op_id = result.get("operation_id")
        try:
            with self._connect() as conn:
                conn.execute(
                    "INSERT INTO alarm_delivery_attempts (alarm_id, attempt_id, channel, state, code, error, hint, operation_id, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (alarm_id, attempt_id, channel, state, code, error, hint, op_id, self._iso(now)),
                )
                conn.commit()
            return True
        except sqlite3.Error as exc:
            logger.error("[AlarmManager] channel outcome failed: %s", exc)
            return False

    def mark_delivery_success(self, alarm_id: str, *, claim: str | None = None, hint: str = "") -> bool:
        return self._claimed_update(
            alarm_id, claim,
            {"notified": 1, "lifecycle": "delivered", "status": "delivered", "delivery_state": "succeeded", "delivery_claim": None, "delivery_lease": None, "delivery_claimed_at": None, "delivery_lease_until": None, "cleanup_state": "pending", "last_error": None, "last_hint": hint},
        )

    def mark_notified(self, alarm_id: str) -> bool:
        row = self.get_alarm_by_id(alarm_id)
        return self.mark_delivery_success(alarm_id, claim=(row or {}).get("delivery_claim"))

    def mark_delivery_failure(self, alarm_id: str, error: str, *, hint: str = "Try again later.", claim: str | None = None) -> bool:
        row = self.get_alarm_by_id(alarm_id) or {}
        lifecycle = "overdue" if row.get("lifecycle") == "overdue" else "active"
        return self._claimed_update(
            alarm_id, claim,
            {"lifecycle": lifecycle, "status": lifecycle, "delivery_state": "failed", "delivery_claim": None, "delivery_lease": None, "delivery_claimed_at": None, "delivery_lease_until": None, "last_error": error, "last_hint": hint},
        )

    def mark_delivery_unknown(self, alarm_id: str, error: str, *, hint: str = "Check the delivery provider before retrying.", claim: str | None = None) -> bool:
        return self._claimed_update(
            alarm_id, claim,
            {"lifecycle": "delivery_unknown", "status": "delivery_unknown", "delivery_state": "delivery_unknown", "delivery_claim": None, "delivery_lease": None, "delivery_claimed_at": None, "delivery_lease_until": None, "last_error": error, "last_hint": hint},
        )

    def mark_cleanup_done(self, alarm_id: str) -> bool:
        return self._update(alarm_id, {"cleanup_state": "done", "last_error": None})

    def mark_cleanup_failed(self, alarm_id: str, error: str, *, hint: str = "Retry cleanup from reconciliation.", unknown: bool = False) -> bool:
        return self._update(alarm_id, {"cleanup_state": "unknown" if unknown else "failed", "last_error": error, "last_hint": hint})

    def cancel_alarm(self, alarm_id: str, *, scheduler=WindowsScheduler) -> bool:
        row = self.get_alarm_by_id(alarm_id)
        if not row:
            return False
        changed = self._update(
            alarm_id,
            {"enabled": 0, "lifecycle": "cancelled", "status": "cancelled", "delivery_state": "skipped", "delivery_claim": None, "delivery_lease": None, "delivery_claimed_at": None, "delivery_lease_until": None, "cleanup_state": "pending"},
        )
        if not changed:
            return False
        task_name = row.get("scheduled_task_name")
        if not task_name:
            self.mark_cleanup_done(alarm_id)
            return True
        try:
            raw = scheduler.unregister_task_result(task_name) if hasattr(scheduler, "unregister_task_result") else scheduler.unregister_task(task_name)
            ok = raw.ok if isinstance(raw, ToolResult) else bool(raw.get("ok", raw.get("success", False))) if isinstance(raw, dict) else bool(raw)
            if ok:
                self.mark_cleanup_done(alarm_id)
                self._update(alarm_id, {"scheduled_task_name": None, "schedule_state": "cancelled"})
            else:
                unknown = bool(raw.get("unknown_outcome", False)) if isinstance(raw, dict) else bool(getattr(raw, "unknown_outcome", False))
                error = raw.get("error", "cancel cleanup failed") if isinstance(raw, dict) else "cancel cleanup failed"
                self.mark_cleanup_failed(alarm_id, error, unknown=unknown)
        except Exception as exc:
            self.mark_cleanup_failed(alarm_id, str(exc), unknown=True)
        return True

    def delete_alarm(self, alarm_id: str, *, scheduler=WindowsScheduler) -> bool:
        """Cancel instead of hard-deleting so unresolved cleanup is recoverable."""
        return self.cancel_alarm(alarm_id, scheduler=scheduler)

    def toggle_alarm(self, alarm_id: str, enabled: bool, *, scheduler=WindowsScheduler) -> bool:
        row = self.get_alarm_by_id(alarm_id) or {}
        if enabled:
            was_inactive = row.get("lifecycle") in {"disabled", "cancelled"}
            lifecycle = "active" if was_inactive else row.get("lifecycle", "active")
            delivery = "pending" if lifecycle == "active" and not row.get("notified") else row.get("delivery_state", "pending")
            values = {"enabled": 1, "lifecycle": lifecycle, "status": lifecycle, "delivery_state": delivery}
            if was_inactive:
                values.update({"schedule_state": "pending", "cleanup_state": "pending"})
                if row.get("cleanup_state") == "done":
                    values["scheduled_task_name"] = None
            return self._update(alarm_id, values)
        changed = self._update(
            alarm_id,
            {"enabled": 0, "lifecycle": "disabled", "status": "disabled",
             "schedule_state": "disabled",
             "delivery_state": "skipped", "delivery_claim": None,
             "delivery_lease": None, "delivery_claimed_at": None,
             "delivery_lease_until": None, "cleanup_state": "pending"},
        )
        if changed and row.get("scheduled_task_name"):
            try:
                raw = scheduler.unregister_task_result(row["scheduled_task_name"]) if hasattr(scheduler, "unregister_task_result") else scheduler.unregister_task(row["scheduled_task_name"])
                ok = raw.ok if isinstance(raw, ToolResult) else bool(raw.get("ok", raw.get("success", False))) if isinstance(raw, dict) else bool(raw)
                if ok:
                    self.mark_cleanup_done(alarm_id)
                    self._update(alarm_id, {"scheduled_task_name": None})
                else:
                    unknown = bool(raw.get("unknown_outcome", False)) if isinstance(raw, dict) else bool(getattr(raw, "unknown_outcome", False))
                    error = raw.get("error", "disable cleanup failed") if isinstance(raw, dict) else "disable cleanup failed"
                    self.mark_cleanup_failed(alarm_id, error, unknown=unknown)
            except Exception as exc:
                self.mark_cleanup_failed(alarm_id, str(exc), unknown=True)
        return changed

    def stale_claims(self, *, now: datetime | str | None = None) -> list[dict[str, Any]]:
        current = self._iso(now)
        with self._connect() as conn:
            return [dict(row) for row in conn.execute("SELECT * FROM alarms WHERE delivery_claim IS NOT NULL AND delivery_claim != '' AND delivery_lease_until < ?", (current,))]

    def mark_stale_claims_unknown(self, *, now: datetime | str | None = None) -> int:
        stale = self.stale_claims(now=now)
        for row in stale:
            self.mark_delivery_unknown(row["id"], "delivery lease expired", hint="The previous worker may have delivered; inspect the provider before retrying.", claim=row.get("delivery_claim"))
        return len(stale)

    def delivery_attempts(self, alarm_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            return [dict(row) for row in conn.execute("SELECT * FROM alarm_delivery_attempts WHERE alarm_id = ? ORDER BY id", (alarm_id,))]

    def status_result(self, alarm_id: str) -> ToolResult:
        row = self.get_alarm_by_id(alarm_id)
        if not row:
            return ToolResult(False, code="not_found", hint="Check the alarm ID.", operation_id=stable_operation_id("alarm", "status", alarm_id))
        return ToolResult(True, operation_id=row.get("operation_id") or stable_operation_id("alarm", "status", alarm_id), alarm=row)
