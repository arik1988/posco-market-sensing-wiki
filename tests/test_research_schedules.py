from __future__ import annotations

import tempfile
import json
import threading
import unittest
from datetime import UTC, date, datetime
from pathlib import Path
from types import SimpleNamespace
from http.server import ThreadingHTTPServer
from urllib.request import Request, urlopen
from unittest.mock import patch

from tools.research_agent.research_schedules import (
    claim_due_schedules,
    create_schedule,
    delete_schedule,
    list_schedules,
    next_run_at,
    request_dates,
    set_schedule_enabled,
)
from tools.research_agent import server


class ResearchScheduleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name) / "market-sensing-wiki"
        self.root.mkdir(parents=True)
        self.request = SimpleNamespace(
            topic="철강 수입규제와 원료 가격 변화",
            companies=("POSCO",),
            business_axes=("철강",),
            provider="codex",
            publish=True,
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_schedule_crud_is_persisted_in_single_sqlite(self) -> None:
        created = create_schedule(
            self.root,
            self.request,
            {
                "frequency": "weekly",
                "run_time": "09:30",
                "weekday": 0,
                "lookback_days": 14,
            },
        )
        self.assertEqual(len(list_schedules(self.root)), 1)
        self.assertEqual(created["timezone"], "Asia/Seoul")
        self.assertEqual(created["business_axes"], ["철강"])

        paused = set_schedule_enabled(self.root, created["schedule_id"], False)
        self.assertFalse(paused["enabled"])
        self.assertTrue(delete_schedule(self.root, created["schedule_id"]))
        self.assertEqual(list_schedules(self.root), [])

    def test_due_schedule_is_claimed_once_and_moves_forward(self) -> None:
        created = create_schedule(
            self.root,
            self.request,
            {"frequency": "daily", "run_time": "09:00", "lookback_days": 7},
        )
        trigger_at = datetime(2026, 8, 29, 1, 0, tzinfo=UTC)
        import tools.research_agent.research_schedules as schedules

        with schedules.sqlite_store.transaction(self.root) as connection:
            payload = created | {"next_run_at": "2026-08-28T00:00:00+00:00"}
            connection.execute(
                "UPDATE wiki_research_schedules SET payload_json=?, next_run_at=? WHERE schedule_id=?",
                (
                    schedules.json.dumps(payload, ensure_ascii=False, sort_keys=True),
                    payload["next_run_at"],
                    created["schedule_id"],
                ),
            )

        claimed = claim_due_schedules(self.root, trigger_at)
        self.assertEqual([item["schedule_id"] for item in claimed], [created["schedule_id"]])
        self.assertEqual(claim_due_schedules(self.root, trigger_at), [])

    def test_next_run_and_rolling_period_use_seoul_business_time(self) -> None:
        weekly = {
            "frequency": "weekly",
            "run_time": "09:00",
            "weekday": 0,
            "day_of_month": 1,
        }
        self.assertEqual(
            next_run_at(weekly, datetime(2026, 8, 31, 1, 0, tzinfo=UTC)),
            "2026-09-07T00:00:00+00:00",
        )
        self.assertEqual(
            request_dates({"lookback_days": 14}, date(2026, 8, 29)),
            ("2026-08-16", "2026-08-29"),
        )

    def test_monthly_schedule_rejects_days_that_can_be_skipped(self) -> None:
        with self.assertRaisesRegex(ValueError, "1~28일"):
            create_schedule(
                self.root,
                self.request,
                {
                    "frequency": "monthly",
                    "run_time": "09:00",
                    "day_of_month": 31,
                    "lookback_days": 30,
                },
            )

    def test_schedule_http_api_creates_pauses_lists_and_deletes(self) -> None:
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{httpd.server_port}"

        def call(path: str, method: str = "GET", payload: dict | None = None):
            body = json.dumps(payload).encode() if payload is not None else None
            request = Request(
                base + path,
                data=body,
                method=method,
                headers={"Content-Type": "application/json"},
            )
            with urlopen(request, timeout=5) as response:
                return response.status, json.loads(response.read())

        try:
            with patch.object(server, "WIKI_ROOT", self.root):
                status, created = call(
                    "/api/research/schedules",
                    "POST",
                    {
                        "topic": self.request.topic,
                        "companies": ["POSCO"],
                        "date_from": "2026-08-16",
                        "date_to": "2026-08-29",
                        "provider": "codex",
                        "publish": True,
                        "frequency": "daily",
                        "run_time": "09:00",
                        "lookback_days": 14,
                    },
                )
                self.assertEqual(status, 201)
                schedule_id = created["schedule_id"]
                _, listed = call("/api/research/schedules")
                self.assertEqual(listed["count"], 1)
                _, paused = call(
                    f"/api/research/schedules/{schedule_id}",
                    "PUT",
                    {"enabled": False},
                )
                self.assertFalse(paused["enabled"])
                _, removed = call(
                    f"/api/research/schedules/{schedule_id}", "DELETE"
                )
                self.assertTrue(removed["removed"])
        finally:
            httpd.shutdown()
            httpd.server_close()
            thread.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
