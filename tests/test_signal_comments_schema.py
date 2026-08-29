from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = PROJECT_ROOT / "skills" / "market-sensing-intelligence" / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import sqlite_store  # noqa: E402


class SignalCommentSchemaTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        sqlite_store.upsert_record(
            self.root,
            "signals",
            "SIG-ONE",
            {"schema_version": 4, "signal_id": "SIG-ONE"},
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def insert_comment(self, **overrides: object) -> None:
        values = {
            "comment_id": "CMT-ONE",
            "signal_id": "SIG-ONE",
            "source_system": "mypin",
            "source_comment_id": "remote-comment-1",
            "parent_comment_id": None,
            "author_user_key": "opaque-user-1",
            "author_display_name": "테스트 사용자",
            "author_company": "테스트 회사",
            "author_department": "테스트 부서",
            "stance": "agree",
            "comment_text": "의견 본문입니다.",
            "decision_deadline": None,
            "source_created_at": "2026-08-19T10:20:00+09:00",
            "source_updated_at": "2026-08-19T10:20:00+09:00",
            "imported_at": "2026-08-29T09:00:00+09:00",
            "metadata_json": json.dumps({}, ensure_ascii=False),
        }
        values.update(overrides)
        columns = tuple(values)
        placeholders = ", ".join("?" for _ in columns)
        with sqlite_store.transaction(self.root) as connection:
            connection.execute(
                f"INSERT INTO wiki_signal_comments ({', '.join(columns)}) "
                f"VALUES ({placeholders})",
                tuple(values[column] for column in columns),
            )

    def test_empty_comment_space_is_created_at_schema_version_four(self) -> None:
        with sqlite_store.connection_scope(self.root) as connection:
            count = connection.execute(
                "SELECT COUNT(*) FROM wiki_signal_comments"
            ).fetchone()[0]
            migration = connection.execute(
                "SELECT 1 FROM wiki_schema_migrations WHERE version = 4"
            ).fetchone()

        self.assertEqual(0, count)
        self.assertIsNotNone(migration)

    def test_comment_contract_supports_nullable_deadline_and_idempotent_source_key(self) -> None:
        self.insert_comment()
        with self.assertRaises(sqlite3.IntegrityError):
            self.insert_comment(comment_id="CMT-TWO")

        with sqlite_store.connection_scope(self.root) as connection:
            row = connection.execute(
                "SELECT stance, decision_deadline FROM wiki_signal_comments"
            ).fetchone()
        self.assertEqual("agree", row["stance"])
        self.assertIsNone(row["decision_deadline"])

    def test_comment_contract_rejects_unknown_signal_stance_and_invalid_deadline(self) -> None:
        invalid_cases = (
            {"comment_id": "CMT-A", "signal_id": "SIG-UNKNOWN"},
            {"comment_id": "CMT-B", "source_comment_id": "remote-b", "stance": "neutral"},
            {
                "comment_id": "CMT-C",
                "source_comment_id": "remote-c",
                "decision_deadline": "2026-02-30",
            },
        )
        for overrides in invalid_cases:
            with self.subTest(overrides=overrides), self.assertRaises(sqlite3.IntegrityError):
                self.insert_comment(**overrides)

    def test_comment_rows_follow_signal_deletion_without_touching_other_records(self) -> None:
        self.insert_comment()
        with sqlite_store.transaction(self.root) as connection:
            connection.execute(
                "DELETE FROM wiki_records WHERE collection='signals' AND record_id='SIG-ONE'"
            )
            remaining = connection.execute(
                "SELECT COUNT(*) FROM wiki_signal_comments"
            ).fetchone()[0]
        self.assertEqual(0, remaining)


if __name__ == "__main__":
    unittest.main()
