from __future__ import annotations

import hashlib
import http.client
import json
import os
import sqlite3
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
from tools.research_agent.operations import OperationRequest, operation_catalog  # noqa: E402


class ExternalControlApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name) / "market-sensing-wiki"
        self.root.mkdir(parents=True)
        sqlite_store.upsert_record(
            self.root,
            "signals",
            "SIG-EXTERNAL-API",
            {"schema_version": 4, "signal_id": "SIG-EXTERNAL-API"},
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
    ) -> tuple[int, bytes, dict[str, str]]:
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        headers = {"Content-Type": "application/json"} if body is not None else {}
        connection = http.client.HTTPConnection(*self.httpd.server_address, timeout=10)
        try:
            connection.request(method, path, body=body, headers=headers)
            response = connection.getresponse()
            return response.status, response.read(), dict(response.getheaders())
        finally:
            connection.close()

    def test_downloads_integrity_checked_online_backup(self) -> None:
        status, body, headers = self.request("GET", "/api/database/snapshot")

        self.assertEqual(200, status)
        self.assertEqual("application/vnd.sqlite3", headers["Content-Type"])
        self.assertIn("market_sensing-", headers["Content-Disposition"])
        self.assertEqual("no-store", headers["Cache-Control"])
        self.assertEqual(hashlib.sha256(body).hexdigest(), headers["X-Snapshot-SHA256"])

        downloaded = Path(self.temporary.name) / "downloaded.db"
        downloaded.write_bytes(body)
        connection = sqlite3.connect(downloaded)
        try:
            self.assertEqual("ok", connection.execute("PRAGMA integrity_check").fetchone()[0])
            payload = connection.execute(
                "SELECT payload_json FROM wiki_records WHERE collection='signals' AND record_id=?",
                ("SIG-EXTERNAL-API",),
            ).fetchone()
        finally:
            connection.close()
        self.assertIsNotNone(payload)

    def test_starts_research_with_existing_serial_job_queue_contract(self) -> None:
        accepted = {
            "run_id": "00000000-0000-0000-0000-000000000001",
            "status": "queued",
            "provider": "codex",
            "codex_model": "gpt-5.6-luna",
            "codex_effort": "medium",
            "publish": True,
        }
        payload = {
            "topic": "철강 수입규제 변화",
            "topic_company": "POSCO",
            "company_axes": [{"company": "POSCO", "business_axis": "철강"}],
            "date_from": "2026-08-01",
            "date_to": "2026-08-30",
            "provider": "codex",
            "codex_model": "gpt-5.6-luna",
            "codex_effort": "medium",
            "publish": True,
        }
        with patch.object(server.JOBS, "create", return_value=accepted) as create:
            status, body, _ = self.request("POST", "/api/research/runs", payload)

        self.assertEqual(202, status)
        self.assertEqual(accepted, json.loads(body))
        request = create.call_args.args[0]
        self.assertEqual("POSCO", request.topic_company)
        self.assertTrue(request.publish)

    def test_operation_catalog_and_queue_cover_governed_cli_functions(self) -> None:
        catalog = operation_catalog()
        commands = {item["command"] for item in catalog["operations"]}
        self.assertIn("add-source", commands)
        self.assertIn("add-signal", commands)
        self.assertIn("audit", commands)
        self.assertIn("prune-to-signals", commands)
        add_source = next(
            item for item in catalog["operations"] if item["command"] == "add-source"
        )
        content = next(
            item for item in add_source["parameters"] if item["name"] == "content_file"
        )
        self.assertTrue(content["input_file"])

        accepted = {
            "operation_id": "00000000-0000-0000-0000-000000000002",
            "command": "audit",
            "status": "queued",
        }
        with patch.object(server.OPERATION_JOBS, "create", return_value=accepted) as create:
            status, body, _ = self.request(
                "POST",
                "/api/operations",
                {"command": "audit", "arguments": ["--stale-days", "90"]},
            )
        self.assertEqual(202, status)
        self.assertEqual(accepted, json.loads(body))
        self.assertEqual("audit", create.call_args.args[0].command)

    def test_maintenance_operation_requires_explicit_confirmation(self) -> None:
        status, body, _ = self.request(
            "POST",
            "/api/operations",
            {"command": "prune-to-signals", "arguments": ["--signal-id", "SIG-ONE"]},
        )
        self.assertEqual(400, status)
        self.assertEqual("invalid_operation", json.loads(body)["error"])
        request = OperationRequest.from_dict(
            {
                "command": "prune-to-signals",
                "arguments": ["--signal-id", "SIG-ONE"],
                "confirm": "prune-to-signals",
            }
        )
        self.assertEqual("prune-to-signals", request.confirm)

    def test_configured_local_browser_origin_is_allowed(self) -> None:
        connection = http.client.HTTPConnection(*self.httpd.server_address, timeout=10)
        try:
            with patch.dict(
                os.environ,
                {"MARKET_API_ALLOWED_ORIGINS": "http://127.0.0.1:8000"},
            ):
                connection.request(
                    "OPTIONS",
                    "/api/settings",
                    headers={"Origin": "http://127.0.0.1:8000"},
                )
                response = connection.getresponse()
                response.read()
                headers = dict(response.getheaders())
        finally:
            connection.close()
        self.assertEqual(204, response.status)
        self.assertEqual(
            "http://127.0.0.1:8000", headers["Access-Control-Allow-Origin"]
        )
        self.assertIn("PATCH", headers["Access-Control-Allow-Methods"])


class WatchScopeApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.project_root = Path(self.temporary.name)
        self.root = self.project_root / "market-sensing-wiki"
        self.root.mkdir(parents=True)
        (self.project_root / "WIKI-SETTINGS.md").write_text(
            """# 테스트 설정

## 분석 관점

- 외부 변화

## 우선 기업

- POSCO

## 우선 회사·사업축

- POSCO | 철강

## 우선 기술


## 우선 프로젝트


## 우선 국가


## 중점 관찰 항목

- business_axis

## 우선 출처 유형

- government

## 학술 탐색 범위


## 리스크 신호

- delay

## 보고서 중점

- 회사 영향
""",
            encoding="utf-8",
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
        self, method: str, payload: dict[str, object] | None = None
    ) -> tuple[int, dict[str, object]]:
        return self.request_path(method, "/api/settings/company-axes", payload)

    def request_path(
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
            return response.status, json.loads(response.read())
        finally:
            connection.close()

    def test_add_replace_remove_scope_and_sync_sqlite_settings(self) -> None:
        status, initial = self.request("GET")
        self.assertEqual(200, status)
        self.assertEqual(
            [{"company": "POSCO", "business_axis": "철강"}],
            initial["company_axes"],
        )

        custom = {"company": "New Company", "business_axis": "신사업"}
        status, added = self.request("POST", {"company_axes": [custom]})
        self.assertEqual(200, status)
        self.assertIn(custom, added["company_axes"])

        replacement = [
            {"company": "POSCO Holdings", "business_axis": "전략광물"},
            {"company": "POSCO Holdings", "business_axis": "리튬"},
        ]
        status, replaced = self.request("PUT", {"company_axes": replacement})
        self.assertEqual(200, status)
        self.assertEqual(replacement, replaced["company_axes"])

        status, remaining = self.request(
            "DELETE", {"company_axes": [replacement[1]]}
        )
        self.assertEqual(200, status)
        self.assertEqual([replacement[0]], remaining["company_axes"])
        markdown = (self.project_root / "WIKI-SETTINGS.md").read_text(encoding="utf-8")
        self.assertIn("- POSCO Holdings | 전략광물", markdown)
        self.assertNotIn("- POSCO Holdings | 리튬", markdown)
        stored = sqlite_store.get_settings(self.root, "watchlist")
        self.assertEqual(["POSCO Holdings | 전략광물"], stored["company_axes"])

    def test_rejects_removing_last_scope(self) -> None:
        status, payload = self.request(
            "DELETE",
            {"company_axes": [{"company": "POSCO", "business_axis": "철강"}]},
        )
        self.assertEqual(400, status)
        self.assertEqual("invalid_company_axes", payload["error"])

    def test_patch_all_settings_preserves_omitted_sections_and_syncs_cache(self) -> None:
        status, changed = self.request_path(
            "PATCH",
            "/api/settings",
            {
                "technologies": ["수소환원제철"],
                "countries": ["대한민국", "미국"],
                "search_overlap_days": 9,
            },
        )
        self.assertEqual(200, status)
        self.assertEqual(["수소환원제철"], changed["technologies"])
        self.assertEqual(["대한민국", "미국"], changed["countries"])
        self.assertEqual(9, changed["search_overlap_days"])
        self.assertEqual(["외부 변화"], changed["focus"])
        markdown = (self.project_root / "WIKI-SETTINGS.md").read_text(encoding="utf-8")
        self.assertIn("## 운영 값", markdown)
        self.assertIn("- 검색 겹침 일수: 9", markdown)

        status, fetched = self.request_path("GET", "/api/settings")
        self.assertEqual(200, status)
        self.assertEqual(["수소환원제철"], fetched["technologies"])

    def test_research_uses_registered_scope_when_request_omits_scope(self) -> None:
        accepted = {
            "run_id": "00000000-0000-0000-0000-000000000003",
            "status": "queued",
        }
        with patch.object(server.JOBS, "create", return_value=accepted) as create:
            status, _ = self.request_path(
                "POST",
                "/api/research/runs",
                {
                    "topic": "철강 수입규제 변화",
                    "topic_company": "POSCO",
                    "date_from": "2026-08-01",
                    "date_to": "2026-08-30",
                    "provider": "codex",
                },
            )
        self.assertEqual(202, status)
        request = create.call_args.args[0]
        self.assertEqual((("POSCO", "철강"),), request.company_axes)


if __name__ == "__main__":
    unittest.main()
