from __future__ import annotations

import json
import re
import sys
import uuid
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = PROJECT_ROOT / "skills" / "market-sensing-intelligence" / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import sqlite_store  # noqa: E402


_KEY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")


def list_comments(wiki_root: Path, signal_id: str) -> list[dict[str, Any]]:
    with sqlite_store.connection_scope(wiki_root) as connection:
        rows = connection.execute(
            "SELECT * FROM wiki_signal_comments WHERE signal_id=? "
            "ORDER BY source_created_at ASC, comment_id ASC",
            (signal_id,),
        ).fetchall()
    return [_row_payload(row) for row in rows]


def get_comment(wiki_root: Path, comment_id: str) -> dict[str, Any] | None:
    with sqlite_store.connection_scope(wiki_root) as connection:
        row = connection.execute(
            "SELECT * FROM wiki_signal_comments WHERE comment_id=?", (comment_id,)
        ).fetchone()
    return _row_payload(row) if row else None


def upsert_comment(wiki_root: Path, data: dict[str, Any]) -> dict[str, Any]:
    values = _validate_comment(data)
    with sqlite_store.transaction(wiki_root) as connection:
        signal = connection.execute(
            "SELECT 1 FROM wiki_records WHERE collection='signals' AND record_id=?",
            (values["signal_id"],),
        ).fetchone()
        if signal is None:
            raise KeyError("signal_not_found")
        if values["parent_comment_id"]:
            parent = connection.execute(
                "SELECT signal_id FROM wiki_signal_comments WHERE comment_id=?",
                (values["parent_comment_id"],),
            ).fetchone()
            if parent is None or parent["signal_id"] != values["signal_id"]:
                raise ValueError("부모 의견은 같은 Signal에 존재해야 합니다.")
        existing = connection.execute(
            "SELECT comment_id FROM wiki_signal_comments "
            "WHERE source_system=? AND source_comment_id=?",
            (values["source_system"], values["source_comment_id"]),
        ).fetchone()
        created = existing is None
        comment_id = (
            f"CMT-{uuid.uuid4().hex[:20].upper()}"
            if created
            else str(existing["comment_id"])
        )
        values["comment_id"] = comment_id
        columns = tuple(values)
        placeholders = ", ".join("?" for _ in columns)
        updates = ", ".join(
            f"{column}=excluded.{column}"
            for column in columns
            if column not in {"comment_id", "source_system", "source_comment_id"}
        )
        connection.execute(
            f"INSERT INTO wiki_signal_comments ({', '.join(columns)}) "
            f"VALUES ({placeholders}) "
            f"ON CONFLICT(source_system, source_comment_id) DO UPDATE SET {updates}",
            tuple(values[column] for column in columns),
        )
    return {**(get_comment(wiki_root, comment_id) or {}), "created": created}


def delete_comment(wiki_root: Path, comment_id: str) -> bool:
    with sqlite_store.transaction(wiki_root) as connection:
        replies = connection.execute(
            "SELECT COUNT(*) FROM wiki_signal_comments WHERE parent_comment_id=?",
            (comment_id,),
        ).fetchone()[0]
        if replies:
            raise ValueError("답글이 있는 의견은 먼저 하위 의견을 삭제해야 합니다.")
        result = connection.execute(
            "DELETE FROM wiki_signal_comments WHERE comment_id=?", (comment_id,)
        )
    return result.rowcount > 0


def _validate_comment(data: dict[str, Any]) -> dict[str, Any]:
    def required(name: str, limit: int) -> str:
        value = str(data.get(name) or "").strip()
        if not value or len(value) > limit:
            raise ValueError(f"{name}은 1자 이상 {limit}자 이하로 입력해 주세요.")
        return value

    signal_id = required("signal_id", 128)
    source_system = required("source_system", 80)
    source_comment_id = required("source_comment_id", 160)
    author_user_key = required("author_user_key", 128)
    if not all(_KEY.fullmatch(value) for value in (signal_id, source_system, source_comment_id, author_user_key)):
        raise ValueError("식별자 형식이 올바르지 않습니다.")
    stance = required("stance", 16)
    if stance not in {"agree", "skeptical"}:
        raise ValueError("stance는 agree 또는 skeptical이어야 합니다.")
    comment_text = required("comment_text", 20_000)
    decision_deadline = str(data.get("decision_deadline") or "").strip() or None
    if decision_deadline:
        try:
            date.fromisoformat(decision_deadline)
        except ValueError as exc:
            raise ValueError("decision_deadline은 유효한 YYYY-MM-DD여야 합니다.") from exc
    source_created_at = _iso_datetime(required("source_created_at", 64), "source_created_at")
    source_updated_at = _iso_datetime(
        str(data.get("source_updated_at") or source_created_at), "source_updated_at"
    )
    metadata = data.get("metadata", {})
    if not isinstance(metadata, dict):
        raise ValueError("metadata는 JSON 객체여야 합니다.")
    optional_limits = {
        "parent_comment_id": 128,
        "author_display_name": 120,
        "author_company": 120,
        "author_department": 120,
    }
    optional = {
        name: (str(data.get(name) or "").strip() or None)
        for name in optional_limits
    }
    for name, limit in optional_limits.items():
        if optional[name] and len(str(optional[name])) > limit:
            raise ValueError(f"{name}은 {limit}자 이하여야 합니다.")
    return {
        "comment_id": "",
        "signal_id": signal_id,
        "source_system": source_system,
        "source_comment_id": source_comment_id,
        **optional,
        "author_user_key": author_user_key,
        "stance": stance,
        "comment_text": comment_text,
        "decision_deadline": decision_deadline,
        "source_created_at": source_created_at,
        "source_updated_at": source_updated_at,
        "imported_at": datetime.now(UTC).isoformat(),
        "metadata_json": json.dumps(metadata, ensure_ascii=False, sort_keys=True),
    }


def _iso_datetime(value: str, name: str) -> str:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{name}은 유효한 ISO 8601 시각이어야 합니다.") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{name}에는 timezone이 필요합니다.")
    return parsed.isoformat()


def _row_payload(row: Any) -> dict[str, Any]:
    payload = dict(row)
    payload["metadata"] = json.loads(payload.pop("metadata_json"))
    return payload
