from __future__ import annotations

import http.client
import json
import sys
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = PROJECT_ROOT / "skills" / "market-sensing-intelligence" / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import sqlite_store  # noqa: E402
from tools.research_agent import server  # noqa: E402


class SignalCommentsApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        sqlite_store.upsert_record(
            self.root,
            "signals",
            "SIG-COMMENT",
            {"schema_version": 4, "signal_id": "SIG-COMMENT"},
        )
        self.wiki_root_patch = patch.object(server, "WIKI_ROOT", self.root)
        self.wiki_root_patch.start()
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=5)
        self.wiki_root_patch.stop()
        self.temporary.cleanup()

    def request(
        self,
        method: str,
        path: str,
        payload: dict[str, object] | None = None,
    ) -> tuple[int, dict[str, object]]:
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        headers = {"Content-Type": "application/json"} if body else {}
        connection = http.client.HTTPConnection(*self.httpd.server_address, timeout=10)
        try:
            connection.request(method, path, body=body, headers=headers)
            response = connection.getresponse()
            raw = response.read()
            return response.status, json.loads(raw) if raw else {}
        finally:
            connection.close()

    def payload(self) -> dict[str, object]:
        return {
            "signal_id": "SIG-COMMENT",
            "source_system": "mypin",
            "source_comment_id": "remote-1",
            "author_user_key": "opaque-user-1",
            "author_display_name": "테스트 사용자",
            "author_company": "POSCO",
            "author_department": "전략",
            "stance": "agree",
            "comment_text": "이 판단에 동의합니다.",
            "decision_deadline": None,
            "source_created_at": "2026-08-30T09:00:00+09:00",
            "source_updated_at": "2026-08-30T09:00:00+09:00",
            "metadata": {"channel": "mypin"},
        }

    def test_upsert_list_get_and_delete_are_idempotent(self) -> None:
        status, created = self.request("POST", "/api/signal-comments", self.payload())
        self.assertEqual(201, status)
        self.assertTrue(created["created"])
        comment_id = str(created["comment_id"])

        changed = {**self.payload(), "stance": "skeptical", "comment_text": "추가 검토가 필요합니다."}
        status, updated = self.request("POST", "/api/signal-comments", changed)
        self.assertEqual(200, status)
        self.assertFalse(updated["created"])
        self.assertEqual(comment_id, updated["comment_id"])
        self.assertEqual("skeptical", updated["stance"])

        status, listing = self.request(
            "GET", "/api/signal-comments?signal_id=SIG-COMMENT"
        )
        self.assertEqual(200, status)
        self.assertEqual(1, listing["count"])

        status, single = self.request("GET", f"/api/signal-comments/{comment_id}")
        self.assertEqual(200, status)
        self.assertEqual({"channel": "mypin"}, single["metadata"])

        status, removed = self.request("DELETE", f"/api/signal-comments/{comment_id}")
        self.assertEqual(200, status)
        self.assertTrue(removed["removed"])

    def test_rejects_unknown_signal_and_invalid_stance(self) -> None:
        status, missing = self.request(
            "POST",
            "/api/signal-comments",
            {**self.payload(), "signal_id": "SIG-UNKNOWN"},
        )
        self.assertEqual(404, status)
        self.assertEqual("signal_not_found", missing["error"])

        status, invalid = self.request(
            "POST",
            "/api/signal-comments",
            {**self.payload(), "stance": "neutral"},
        )
        self.assertEqual(400, status)
        self.assertEqual("invalid_comment", invalid["error"])

    def test_parent_with_replies_requires_child_deletion_first(self) -> None:
        _, parent = self.request("POST", "/api/signal-comments", self.payload())
        child_payload = {
            **self.payload(),
            "source_comment_id": "remote-2",
            "parent_comment_id": parent["comment_id"],
        }
        status, _ = self.request("POST", "/api/signal-comments", child_payload)
        self.assertEqual(201, status)
        status, conflict = self.request(
            "DELETE", f'/api/signal-comments/{parent["comment_id"]}'
        )
        self.assertEqual(409, status)
        self.assertEqual("comment_has_replies", conflict["error"])


if __name__ == "__main__":
    unittest.main()
