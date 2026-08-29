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
SCRIPT_DIR = (
    PROJECT_ROOT / "skills" / "market-sensing-intelligence" / "scripts"
)
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import sqlite_store  # noqa: E402
from tools.research_agent import server  # noqa: E402


class SignalFavoriteStoreTests(unittest.TestCase):
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

    def test_favorites_are_idempotent_and_isolated_by_user(self) -> None:
        created = sqlite_store.put_signal_favorite(
            self.root, "opaque-user-a", "SIG-ONE"
        )
        repeated = sqlite_store.put_signal_favorite(
            self.root, "opaque-user-a", "SIG-ONE"
        )

        self.assertTrue(created["created"])
        self.assertFalse(repeated["created"])
        self.assertEqual(created["favorited_at"], repeated["favorited_at"])
        self.assertEqual(
            [{"signal_id": "SIG-ONE", "favorited_at": created["favorited_at"]}],
            sqlite_store.list_signal_favorites(self.root, "opaque-user-a"),
        )
        self.assertEqual([], sqlite_store.list_signal_favorites(self.root, "opaque-user-b"))

        self.assertTrue(
            sqlite_store.delete_signal_favorite(
                self.root, "opaque-user-a", "SIG-ONE"
            )
        )
        self.assertFalse(
            sqlite_store.delete_signal_favorite(
                self.root, "opaque-user-a", "SIG-ONE"
            )
        )

    def test_favorite_rejects_unknown_signal_and_records_schema_migration(self) -> None:
        with self.assertRaises(KeyError):
            sqlite_store.put_signal_favorite(
                self.root, "opaque-user-a", "SIG-UNKNOWN"
            )
        with sqlite_store.connection_scope(self.root) as connection:
            versions = {
                row[0]
                for row in connection.execute(
                    "SELECT version FROM wiki_schema_migrations"
                )
            }
        self.assertIn(sqlite_store.SCHEMA_VERSION, versions)


class SignalFavoriteApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        sqlite_store.upsert_record(
            self.root,
            "signals",
            "SIG-ONE",
            {"schema_version": 4, "signal_id": "SIG-ONE"},
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
        *,
        user_key: str | None = "opaque-user-a",
        headers: dict[str, str] | None = None,
    ) -> tuple[int, dict[str, object], dict[str, str]]:
        request_headers = dict(headers or {})
        if user_key is not None:
            request_headers[server.USER_KEY_HEADER] = user_key
        connection = http.client.HTTPConnection(*self.httpd.server_address, timeout=5)
        try:
            connection.request(method, path, headers=request_headers)
            response = connection.getresponse()
            raw = response.read()
            payload = json.loads(raw) if raw else {}
            return response.status, payload, dict(response.getheaders())
        finally:
            connection.close()

    def test_register_list_check_and_remove_favorite(self) -> None:
        status, created, _ = self.request("PUT", "/api/signal-favorites/SIG-ONE")
        self.assertEqual(201, status)
        self.assertTrue(created["favorited"])

        status, repeated, _ = self.request("PUT", "/api/signal-favorites/SIG-ONE")
        self.assertEqual(200, status)
        self.assertFalse(repeated["created"])

        status, listing, _ = self.request("GET", "/api/signal-favorites")
        self.assertEqual(200, status)
        self.assertEqual(1, listing["count"])
        self.assertEqual("SIG-ONE", listing["favorites"][0]["signal_id"])

        status, other_user, _ = self.request(
            "GET", "/api/signal-favorites", user_key="opaque-user-b"
        )
        self.assertEqual(200, status)
        self.assertEqual([], other_user["favorites"])

        status, state, _ = self.request("GET", "/api/signal-favorites/SIG-ONE")
        self.assertEqual(200, status)
        self.assertTrue(state["favorited"])

        status, removed, _ = self.request("DELETE", "/api/signal-favorites/SIG-ONE")
        self.assertEqual(200, status)
        self.assertTrue(removed["removed"])

        status, state, _ = self.request("GET", "/api/signal-favorites/SIG-ONE")
        self.assertEqual(200, status)
        self.assertFalse(state["favorited"])

    def test_contract_errors_and_cors_methods_are_explicit(self) -> None:
        status, missing_user, _ = self.request(
            "GET", "/api/signal-favorites", user_key=None
        )
        self.assertEqual(400, status)
        self.assertEqual("invalid_user_key", missing_user["error"])

        status, unknown, _ = self.request(
            "PUT", "/api/signal-favorites/SIG-UNKNOWN"
        )
        self.assertEqual(404, status)
        self.assertEqual("signal_not_found", unknown["error"])

        status, _, headers = self.request(
            "OPTIONS",
            "/api/signal-favorites/SIG-ONE",
            headers={"Origin": "http://127.0.0.1:8200"},
        )
        self.assertEqual(204, status)
        self.assertIn("PUT", headers["Access-Control-Allow-Methods"])
        self.assertIn("DELETE", headers["Access-Control-Allow-Methods"])
        self.assertIn(server.USER_KEY_HEADER, headers["Access-Control-Allow-Headers"])


if __name__ == "__main__":
    unittest.main()
