"""Windows Task Scheduler adapter with explicit definite/unknown outcomes."""

from __future__ import annotations

import os
import re
import subprocess
import sys
from datetime import datetime, timedelta
from typing import Any, Callable

from src.utils.reliability import ToolResult, stable_operation_id


class WindowsScheduler:
    TASK_PREFIX = "TsuziReminder_"
    # Injectable seams used by deterministic tests. Production keeps the old
    # schtasks command and 15 second timeout.
    runner: Callable[..., Any] | None = None
    now: Callable[[], datetime] = datetime.now
    last_register_result: ToolResult | None = None
    last_unregister_result: ToolResult | None = None

    @classmethod
    def _run(cls, *args, **kwargs):
        return (cls.runner or subprocess.run)(*args, **kwargs)

    @staticmethod
    def _safe_alarm_id(alarm_id: str) -> str:
        safe_id = re.sub(r"[^A-Za-z0-9_-]", "_", str(alarm_id).strip())
        return safe_id or "unknown"

    @staticmethod
    def task_name_for_alarm(alarm_id: str) -> str:
        return f"{WindowsScheduler.TASK_PREFIX}{WindowsScheduler._safe_alarm_id(alarm_id)}"

    @staticmethod
    def bat_filename_for_alarm(alarm_id: str) -> str:
        return f"reminder_{WindowsScheduler._safe_alarm_id(alarm_id)}.bat"

    @classmethod
    def register_alarm_result(cls, alarm_id: str, fire_time: str, label: str = "Alarm") -> ToolResult:
        task_name = cls.task_name_for_alarm(alarm_id)
        safe_alarm_id = cls._safe_alarm_id(alarm_id)
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        script_path = os.path.join(base_dir, "src", "services", "send_reminder.py")
        bat_path = None
        operation_id = stable_operation_id("windows_scheduler", "register", alarm_id)
        try:
            datetime.strptime(fire_time, "%H:%M")
            current = cls.now()
            hour, minute = map(int, fire_time.split(":"))
            alarm_dt = current.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if alarm_dt <= current:
                alarm_dt += timedelta(days=1)
            schedule_date = alarm_dt.strftime("%m/%d/%Y")
            bat_dir = os.path.join(base_dir, "data")
            os.makedirs(bat_dir, exist_ok=True)
            bat_path = os.path.join(bat_dir, cls.bat_filename_for_alarm(alarm_id))
            with open(bat_path, "w", encoding="ascii") as handle:
                # Alarm IDs are generated UUIDs. Quote the original identity
                # so the worker can always resolve the same database row.
                handle.write(f'@"{sys.executable}" "{script_path}" --alarm_id "{alarm_id}"\n')
            result = cls._run(
                ["schtasks", "/create", "/tn", task_name, "/tr", f'"{bat_path}"',
                 "/sc", "once", "/st", fire_time, "/sd", schedule_date, "/f"],
                capture_output=True, text=True, timeout=15,
            )
            return cls._finish_register(
                ToolResult(
                    result.returncode == 0,
                    code="ok" if result.returncode == 0 else "schedule_failed",
                    hint="" if result.returncode == 0 else "Windows Task Scheduler rejected the alarm; it remains recoverable in the database.",
                    error=None if result.returncode == 0 else (getattr(result, "stderr", "") or "schtasks returned a non-zero exit code").strip(),
                    operation_id=operation_id, provider="windows_scheduler", task_name=task_name if result.returncode == 0 else None,
                ),
                bat_path,
            )
        except ValueError:
            return cls._finish_register(ToolResult(False, code="invalid_input", hint="Use HH:MM time.", operation_id=operation_id, provider="windows_scheduler"), bat_path)
        except subprocess.TimeoutExpired as exc:
            # The command may have reached Windows before the client timed out.
            return cls._finish_register(ToolResult(False, code="unknown_outcome", unknown_outcome=True, hint="Scheduler registration timed out; inspect Task Scheduler before retrying.", error=str(exc), operation_id=operation_id, provider="windows_scheduler", task_name=task_name), bat_path, preserve_bat=True)
        except (OSError, subprocess.SubprocessError) as exc:
            return cls._finish_register(ToolResult(False, code="schedule_failed", hint="Windows Task Scheduler could not be reached; the alarm remains recoverable.", error=str(exc), operation_id=operation_id, provider="windows_scheduler"), bat_path)
        except Exception as exc:
            return cls._finish_register(ToolResult(False, code="schedule_failed", hint="Scheduler registration failed; the alarm remains recoverable.", error=str(exc), operation_id=operation_id, provider="windows_scheduler"), bat_path)

    @classmethod
    def _finish_register(cls, result: ToolResult, bat_path: str | None, preserve_bat: bool = False) -> ToolResult:
        cls.last_register_result = result
        if bat_path and (not result.ok) and not preserve_bat:
            try:
                os.remove(bat_path)
            except OSError:
                pass
        return result

    @classmethod
    def register_alarm(cls, alarm_id: str, fire_time: str, label: str = "Alarm") -> str:
        """Legacy string API: empty means registration was not definite."""
        result = cls.register_alarm_result(alarm_id, fire_time, label)
        return str(result.get("task_name") or "") if result.ok else ""

    register_alarm_with_result = register_alarm_result

    @classmethod
    def unregister_task_result(cls, task_name: str) -> ToolResult:
        operation_id = stable_operation_id("windows_scheduler", "unregister", task_name)
        if not task_name:
            result = ToolResult(False, code="invalid_input", hint="A stored task name is required.", operation_id=operation_id, provider="windows_scheduler")
            cls.last_unregister_result = result
            return result
        try:
            response = cls._run(["schtasks", "/delete", "/tn", task_name, "/f"], capture_output=True, text=True, timeout=15)
            if response.returncode == 0:
                cls._remove_bat_for_task(task_name)
                result = ToolResult(True, operation_id=operation_id, provider="windows_scheduler", task_name=task_name)
            else:
                present = cls.query_task(task_name)
                if present is False:
                    cls._remove_bat_for_task(task_name)
                    result = ToolResult(True, hint="Task was already absent; cleanup is complete.", operation_id=operation_id, provider="windows_scheduler", task_name=task_name, already_absent=True)
                elif present is None:
                    result = ToolResult(False, code="unknown_outcome", unknown_outcome=True, hint="Task deletion failed and its state could not be queried; inspect Task Scheduler before retrying.", error=(getattr(response, "stderr", "") or "schtasks returned a non-zero exit code").strip(), operation_id=operation_id, provider="windows_scheduler", task_name=task_name)
                else:
                    result = ToolResult(False, code="cleanup_failed", hint="Task cleanup failed; retry reconciliation.", error=(getattr(response, "stderr", "") or "schtasks returned a non-zero exit code").strip(), operation_id=operation_id, provider="windows_scheduler", task_name=task_name)
        except subprocess.TimeoutExpired as exc:
            result = ToolResult(False, code="unknown_outcome", unknown_outcome=True, hint="Task cleanup timed out; inspect Task Scheduler before retrying.", error=str(exc), operation_id=operation_id, provider="windows_scheduler")
        except (OSError, subprocess.SubprocessError) as exc:
            result = ToolResult(False, code="cleanup_failed", hint="Task cleanup could not be reached; retry reconciliation.", error=str(exc), operation_id=operation_id, provider="windows_scheduler")
        except Exception as exc:
            result = ToolResult(False, code="cleanup_failed", hint="Task cleanup failed; retry reconciliation.", error=str(exc), operation_id=operation_id, provider="windows_scheduler")
        cls.last_unregister_result = result
        return result

    @classmethod
    def unregister_task(cls, task_name: str) -> bool:
        return bool(cls.unregister_task_result(task_name).ok)

    unregister_task_with_result = unregister_task_result

    @classmethod
    def _remove_bat_for_task(cls, task_name: str) -> None:
        alarm_id = str(task_name).removeprefix(cls.TASK_PREFIX)
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        try:
            os.remove(os.path.join(base_dir, "data", cls.bat_filename_for_alarm(alarm_id)))
        except OSError:
            pass

    @classmethod
    def query_task(cls, task_name: str) -> bool | None:
        """Return present/absent when schtasks can answer, otherwise None."""
        if not task_name:
            return False
        try:
            response = cls._run(["schtasks", "/query", "/tn", task_name], capture_output=True, text=True, timeout=15)
            return response.returncode == 0
        except (subprocess.TimeoutExpired, OSError, subprocess.SubprocessError):
            return None

    @classmethod
    def query_tasks(cls) -> dict[str, bool] | None:
        # Kept deliberately small: reconciliation only needs an injectable
        # query seam, not a provider-specific task schema.
        return None
