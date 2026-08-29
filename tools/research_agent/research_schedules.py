from __future__ import annotations

import json
import re
import sys
import threading
import uuid
from datetime import UTC, date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = PROJECT_ROOT / "skills" / "market-sensing-intelligence" / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import sqlite_store  # noqa: E402


TIMEZONE_NAME = "Asia/Seoul"
TIMEZONE = timezone(timedelta(hours=9), TIMEZONE_NAME)
FREQUENCIES = {"daily", "weekly", "monthly"}
_TIME_PATTERN = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d$")
_LOCK = threading.RLock()


def _iso_now() -> str:
    return datetime.now(UTC).isoformat()


def _payload(row: Any) -> dict[str, Any]:
    return json.loads(row["payload_json"])


def _next_month(value: date) -> date:
    if value.month == 12:
        return date(value.year + 1, 1, 1)
    return date(value.year, value.month + 1, 1)


def next_run_at(schedule: dict[str, Any], after: datetime | None = None) -> str:
    reference = after or datetime.now(UTC)
    if reference.tzinfo is None:
        reference = reference.replace(tzinfo=UTC)
    local_now = reference.astimezone(TIMEZONE)
    hour, minute = (int(part) for part in schedule["run_time"].split(":"))
    run_time = time(hour, minute, tzinfo=TIMEZONE)
    frequency = schedule["frequency"]

    if frequency == "daily":
        candidate_date = local_now.date()
        candidate = datetime.combine(candidate_date, run_time)
        if candidate <= local_now:
            candidate = datetime.combine(candidate_date + timedelta(days=1), run_time)
    elif frequency == "weekly":
        weekday = int(schedule["weekday"])
        delta = (weekday - local_now.weekday()) % 7
        candidate = datetime.combine(local_now.date() + timedelta(days=delta), run_time)
        if candidate <= local_now:
            candidate += timedelta(days=7)
    elif frequency == "monthly":
        day_of_month = int(schedule["day_of_month"])
        candidate_date = date(local_now.year, local_now.month, day_of_month)
        candidate = datetime.combine(candidate_date, run_time)
        if candidate <= local_now:
            next_month = _next_month(local_now.date())
            candidate = datetime.combine(
                date(next_month.year, next_month.month, day_of_month), run_time
            )
    else:
        raise ValueError("지원하지 않는 조사 주기입니다.")
    return candidate.astimezone(UTC).isoformat()


def _normalize(request: Any, data: dict[str, Any], existing: dict[str, Any] | None = None) -> dict[str, Any]:
    frequency = str(data.get("frequency") or (existing or {}).get("frequency") or "").strip().lower()
    if frequency not in FREQUENCIES:
        raise ValueError("조사 주기는 매일, 매주, 매월 중에서 선택해 주세요.")
    run_time = str(data.get("run_time") or (existing or {}).get("run_time") or "09:00").strip()
    if not _TIME_PATTERN.fullmatch(run_time):
        raise ValueError("실행 시각은 HH:MM 형식이어야 합니다.")
    lookback_days = int(data.get("lookback_days") or (existing or {}).get("lookback_days") or 14)
    if not 1 <= lookback_days <= 366:
        raise ValueError("반복 조사의 재탐색 기간은 1일 이상 366일 이하여야 합니다.")
    weekday = int(data.get("weekday", (existing or {}).get("weekday", 0)))
    if not 0 <= weekday <= 6:
        raise ValueError("요일 값이 올바르지 않습니다.")
    day_of_month = int(data.get("day_of_month", (existing or {}).get("day_of_month", 1)))
    if not 1 <= day_of_month <= 28:
        raise ValueError("월간 실행일은 매월 빠짐없이 실행되도록 1~28일로 설정해 주세요.")
    topic = str(request.topic).strip()
    name = str(data.get("name") or (existing or {}).get("name") or topic[:40]).strip()
    if not 1 <= len(name) <= 80:
        raise ValueError("일정 이름은 1자 이상 80자 이하로 입력해 주세요.")

    now = _iso_now()
    value = {
        "schema_version": 1,
        "schedule_id": (existing or {}).get("schedule_id") or str(uuid.uuid4()),
        "name": name,
        "topic": topic,
        "companies": list(request.companies),
        "business_axes": list(request.business_axes),
        "provider": str(request.provider),
        "publish": bool(request.publish),
        "frequency": frequency,
        "run_time": run_time,
        "weekday": weekday,
        "day_of_month": day_of_month,
        "lookback_days": lookback_days,
        "timezone": TIMEZONE_NAME,
        "enabled": bool(data.get("enabled", (existing or {}).get("enabled", True))),
        "created_at": (existing or {}).get("created_at") or now,
        "updated_at": now,
        "last_triggered_at": (existing or {}).get("last_triggered_at"),
        "last_run_id": (existing or {}).get("last_run_id"),
    }
    value["next_run_at"] = next_run_at(value)
    return value


def _write(root: Path, value: dict[str, Any]) -> dict[str, Any]:
    with sqlite_store.transaction(root) as connection:
        connection.execute(
            """
            INSERT INTO wiki_research_schedules(
                schedule_id, payload_json, enabled, next_run_at, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(schedule_id) DO UPDATE SET
                payload_json=excluded.payload_json,
                enabled=excluded.enabled,
                next_run_at=excluded.next_run_at,
                updated_at=excluded.updated_at
            """,
            (
                value["schedule_id"],
                json.dumps(value, ensure_ascii=False, sort_keys=True),
                int(value["enabled"]),
                value["next_run_at"],
                value["created_at"],
                value["updated_at"],
            ),
        )
    return dict(value)


def create_schedule(root: Path, request: Any, data: dict[str, Any]) -> dict[str, Any]:
    with _LOCK:
        return _write(root, _normalize(request, data))


def list_schedules(root: Path) -> list[dict[str, Any]]:
    with sqlite_store.connection_scope(root) as connection:
        rows = connection.execute(
            "SELECT payload_json FROM wiki_research_schedules ORDER BY created_at DESC, schedule_id"
        ).fetchall()
    return [_payload(row) for row in rows]


def get_schedule(root: Path, schedule_id: str) -> dict[str, Any] | None:
    with sqlite_store.connection_scope(root) as connection:
        row = connection.execute(
            "SELECT payload_json FROM wiki_research_schedules WHERE schedule_id=?",
            (schedule_id,),
        ).fetchone()
    return _payload(row) if row else None


def set_schedule_enabled(root: Path, schedule_id: str, enabled: bool) -> dict[str, Any]:
    with _LOCK:
        value = get_schedule(root, schedule_id)
        if value is None:
            raise KeyError(schedule_id)
        value["enabled"] = bool(enabled)
        value["updated_at"] = _iso_now()
        value["next_run_at"] = next_run_at(value)
        return _write(root, value)


def delete_schedule(root: Path, schedule_id: str) -> bool:
    with _LOCK, sqlite_store.transaction(root) as connection:
        cursor = connection.execute(
            "DELETE FROM wiki_research_schedules WHERE schedule_id=?", (schedule_id,)
        )
        return cursor.rowcount > 0


def claim_due_schedules(root: Path, now: datetime | None = None) -> list[dict[str, Any]]:
    reference = now or datetime.now(UTC)
    if reference.tzinfo is None:
        reference = reference.replace(tzinfo=UTC)
    due: list[dict[str, Any]] = []
    with _LOCK, sqlite_store.transaction(root) as connection:
        rows = connection.execute(
            """
            SELECT payload_json FROM wiki_research_schedules
            WHERE enabled=1 AND next_run_at<=?
            ORDER BY next_run_at, schedule_id
            """,
            (reference.astimezone(UTC).isoformat(),),
        ).fetchall()
        for row in rows:
            value = _payload(row)
            value["last_triggered_at"] = reference.astimezone(UTC).isoformat()
            value["updated_at"] = value["last_triggered_at"]
            value["next_run_at"] = next_run_at(value, reference)
            connection.execute(
                """
                UPDATE wiki_research_schedules
                SET payload_json=?, next_run_at=?, updated_at=?
                WHERE schedule_id=?
                """,
                (
                    json.dumps(value, ensure_ascii=False, sort_keys=True),
                    value["next_run_at"],
                    value["updated_at"],
                    value["schedule_id"],
                ),
            )
            due.append(value)
    return due


def mark_schedule_run(root: Path, schedule_id: str, run_id: str) -> None:
    with _LOCK:
        value = get_schedule(root, schedule_id)
        if value is None:
            return
        value["last_run_id"] = run_id
        value["updated_at"] = _iso_now()
        _write(root, value)


def request_dates(schedule: dict[str, Any], today: date | None = None) -> tuple[str, str]:
    end = today or datetime.now(TIMEZONE).date()
    start = end - timedelta(days=int(schedule["lookback_days"]) - 1)
    return start.isoformat(), end.isoformat()
