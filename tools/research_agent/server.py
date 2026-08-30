from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import threading
import uuid
from datetime import UTC, datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

from .cli_tools import ALL_COMMANDS, MarketSensingCli
from .database_snapshot import database_snapshot, sqlite_store
from .operations import OperationRequest, operation_catalog, parse_cli_result
from .signal_favorites import (
    USER_KEY_HEADER,
    get_favorite,
    list_favorites,
    remove_favorite,
    save_favorite,
    validate_user_key,
)
from .signal_comments import delete_comment, get_comment, list_comments, upsert_comment
from .research_schedules import (
    claim_due_schedules,
    create_schedule,
    delete_schedule,
    get_schedule,
    list_schedules,
    mark_schedule_run,
    request_dates,
    set_schedule_enabled,
)
from .watch_scope import (
    add_watch_scope,
    get_all_settings,
    get_watch_scope,
    patch_all_settings,
    remove_watch_scope,
    replace_watch_scope,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
WIKI_ROOT = PROJECT_ROOT / "market-sensing-wiki"
_RUN_PATH = re.compile(r"^/api/research/runs/(?P<run_id>[0-9a-f-]{36})$")
_SCHEDULES_PATH = re.compile(r"^/api/research/schedules/?$")
_SCHEDULE_PATH = re.compile(
    r"^/api/research/schedules/(?P<schedule_id>[0-9a-f-]{36})/?$"
)
_FAVORITES_PATH = re.compile(r"^/api/signal-favorites/?$")
_FAVORITE_PATH = re.compile(
    r"^/api/signal-favorites/(?P<signal_id>[A-Za-z0-9][A-Za-z0-9._:-]{1,127})/?$"
)
_OPERATIONS_PATH = re.compile(r"^/api/operations/?$")
_OPERATION_PATH = re.compile(
    r"^/api/operations/(?P<operation_id>[0-9a-f-]{36})/?$"
)
_WATCH_SCOPE_PATH = re.compile(r"^/api/settings/company-axes/?$")
_SETTINGS_PATH = re.compile(r"^/api/settings/?$")
_COMMENTS_PATH = re.compile(r"^/api/signal-comments/?$")
_COMMENT_PATH = re.compile(
    r"^/api/signal-comments/(?P<comment_id>CMT-[A-Z0-9]{8,64})/?$"
)
DATABASE_EXECUTION_LOCK = threading.Lock()


class JobStore:
    def __init__(self, execution_lock: threading.Lock) -> None:
        self._lock = threading.Lock()
        self._execution_lock = execution_lock
        self._jobs: dict[str, dict[str, Any]] = {}
        self._scheduler_stop = threading.Event()
        self._scheduler_thread: threading.Thread | None = None

    def create(self, request: Any) -> dict[str, Any]:
        run_id = str(uuid.uuid4())
        job = {
            "run_id": run_id,
            "status": "queued",
            "provider": request.provider,
            "codex_model": request.codex_model,
            "codex_effort": request.codex_effort,
            "publish": request.publish,
            "created_at": datetime.now(UTC).isoformat(),
            "updated_at": datetime.now(UTC).isoformat(),
            "result": None,
            "error": None,
        }
        with self._lock:
            self._jobs[run_id] = job
            while len(self._jobs) > 100:
                oldest = next(iter(self._jobs))
                if self._jobs[oldest]["status"] in {"queued", "running"}:
                    break
                self._jobs.pop(oldest)
        threading.Thread(
            target=self._execute, args=(run_id, request), daemon=True
        ).start()
        return dict(job)

    def get(self, run_id: str) -> dict[str, Any] | None:
        with self._lock:
            job = self._jobs.get(run_id)
            return dict(job) if job else None

    def start_scheduler(self) -> None:
        if self._scheduler_thread and self._scheduler_thread.is_alive():
            return
        self._scheduler_stop.clear()
        self._scheduler_thread = threading.Thread(
            target=self._schedule_loop, name="research-scheduler", daemon=True
        )
        self._scheduler_thread.start()

    def stop_scheduler(self) -> None:
        self._scheduler_stop.set()
        if self._scheduler_thread:
            self._scheduler_thread.join(timeout=2)

    def _schedule_loop(self) -> None:
        while not self._scheduler_stop.is_set():
            try:
                from .service import ResearchRequest

                for schedule in claim_due_schedules(WIKI_ROOT):
                    date_from, date_to = request_dates(schedule)
                    request = ResearchRequest.from_dict(
                        {
                            **schedule,
                            "date_from": date_from,
                            "date_to": date_to,
                        }
                    )
                    job = self.create(request)
                    mark_schedule_run(WIKI_ROOT, schedule["schedule_id"], job["run_id"])
            except Exception as exc:
                print(f"[research-agent] schedule check failed: {exc}")
            self._scheduler_stop.wait(30)

    def _execute(self, run_id: str, request: Any) -> None:
        with self._execution_lock:
            self._update(run_id, status="running")
            try:
                from .service import run_research

                result = asyncio.run(run_research(request, PROJECT_ROOT))
            except Exception as exc:
                self._update(
                    run_id,
                    status="failed",
                    error={"message": str(exc), "type": type(exc).__name__},
                )
            else:
                self._update(run_id, status="completed", result=result)

    def _update(self, run_id: str, **values: Any) -> None:
        with self._lock:
            self._jobs[run_id].update(values)
            self._jobs[run_id]["updated_at"] = datetime.now(UTC).isoformat()


class OperationJobStore:
    def __init__(self, execution_lock: threading.Lock) -> None:
        self._lock = threading.Lock()
        self._execution_lock = execution_lock
        self._jobs: dict[str, dict[str, Any]] = {}

    def create(self, request: OperationRequest) -> dict[str, Any]:
        operation_id = str(uuid.uuid4())
        now = datetime.now(UTC).isoformat()
        job = {
            "operation_id": operation_id,
            "command": request.command,
            "status": "queued",
            "created_at": now,
            "updated_at": now,
            "result": None,
            "error": None,
        }
        with self._lock:
            self._jobs[operation_id] = job
            self._trim_completed()
        threading.Thread(
            target=self._execute,
            args=(operation_id, request),
            daemon=True,
            name=f"market-operation-{operation_id[:8]}",
        ).start()
        return dict(job)

    def get(self, operation_id: str) -> dict[str, Any] | None:
        with self._lock:
            job = self._jobs.get(operation_id)
            return dict(job) if job else None

    def _execute(self, operation_id: str, request: OperationRequest) -> None:
        with self._execution_lock:
            self._update(operation_id, status="running")
            try:
                arguments = list(request.arguments)
                if request.command == "prune-to-signals" and "--dry-run" not in arguments:
                    database = sqlite_store.database_path(WIKI_ROOT)
                    backup = (
                        database.parent
                        / "backups"
                        / f"api-prune-{operation_id}.db"
                    )
                    arguments.extend(["--backup-path", str(backup)])
                cli = MarketSensingCli(
                    PROJECT_ROOT,
                    publish=True,
                    allowed_commands=set(ALL_COMMANDS),
                )
                result = asyncio.run(
                    cli.run(
                        request.command,
                        arguments,
                        request.input_files,
                        server_managed_paths=True,
                    )
                )
                result = parse_cli_result(result)
                if not result.get("ok"):
                    raise RuntimeError(str(result.get("stderr") or result.get("error")))
            except Exception as exc:
                self._update(
                    operation_id,
                    status="failed",
                    error={"message": str(exc), "type": type(exc).__name__},
                )
            else:
                self._update(operation_id, status="completed", result=result)

    def _update(self, operation_id: str, **values: Any) -> None:
        with self._lock:
            self._jobs[operation_id].update(values)
            self._jobs[operation_id]["updated_at"] = datetime.now(UTC).isoformat()

    def _trim_completed(self) -> None:
        while len(self._jobs) > 100:
            oldest = next(iter(self._jobs))
            if self._jobs[oldest]["status"] in {"queued", "running"}:
                break
            self._jobs.pop(oldest)


JOBS = JobStore(DATABASE_EXECUTION_LOCK)
OPERATION_JOBS = OperationJobStore(DATABASE_EXECUTION_LOCK)


class Handler(BaseHTTPRequestHandler):
    server_version = "MarketResearchAgent/1.0"

    def do_OPTIONS(self) -> None:
        self.send_response(HTTPStatus.NO_CONTENT)
        self._cors_headers()
        self.end_headers()

    def do_GET(self) -> None:
        path = urlsplit(self.path).path
        if path == "/health":
            self._json(HTTPStatus.OK, {"status": "ok", "search": "duckduckgo_lite"})
            return
        if path in {"/api/capabilities", "/api/capabilities/"}:
            self._json(HTTPStatus.OK, self._capabilities())
            return
        if path in {"/api/database/snapshot", "/api/database/snapshot/"}:
            self._database_snapshot()
            return
        if _SETTINGS_PATH.fullmatch(path):
            try:
                with DATABASE_EXECUTION_LOCK:
                    settings = get_all_settings(WIKI_ROOT)
            except ValueError as exc:
                self._json(
                    HTTPStatus.INTERNAL_SERVER_ERROR,
                    {"error": "settings_invalid", "message": str(exc)},
                )
                return
            self._json(HTTPStatus.OK, settings)
            return
        if _WATCH_SCOPE_PATH.fullmatch(path):
            try:
                with DATABASE_EXECUTION_LOCK:
                    scope = get_watch_scope(WIKI_ROOT)
            except ValueError as exc:
                self._json(
                    HTTPStatus.INTERNAL_SERVER_ERROR,
                    {"error": "settings_invalid", "message": str(exc)},
                )
                return
            self._json(HTTPStatus.OK, scope)
            return
        if _OPERATIONS_PATH.fullmatch(path):
            self._json(HTTPStatus.OK, operation_catalog())
            return
        if _COMMENTS_PATH.fullmatch(path):
            query = parse_qs(urlsplit(self.path).query)
            signal_id = str((query.get("signal_id") or [""])[0]).strip()
            if not signal_id:
                self._json(
                    HTTPStatus.BAD_REQUEST,
                    {"error": "signal_id_required"},
                )
                return
            comments = list_comments(WIKI_ROOT, signal_id)
            self._json(HTTPStatus.OK, {"comments": comments, "count": len(comments)})
            return
        comment_match = _COMMENT_PATH.fullmatch(path)
        if comment_match:
            comment = get_comment(WIKI_ROOT, comment_match.group("comment_id"))
            self._json(
                HTTPStatus.OK if comment else HTTPStatus.NOT_FOUND,
                comment or {"error": "comment_not_found"},
            )
            return
        operation_match = _OPERATION_PATH.fullmatch(path)
        if operation_match:
            job = OPERATION_JOBS.get(operation_match.group("operation_id"))
            self._json(
                HTTPStatus.OK if job else HTTPStatus.NOT_FOUND,
                job or {"error": "operation_not_found"},
            )
            return
        if path == "/api/research/providers":
            from .settings import provider_readiness

            self._json(HTTPStatus.OK, {"providers": provider_readiness()})
            return
        if _SCHEDULES_PATH.fullmatch(path):
            schedules = list_schedules(WIKI_ROOT)
            self._json(HTTPStatus.OK, {"schedules": schedules, "count": len(schedules)})
            return
        schedule_match = _SCHEDULE_PATH.fullmatch(path)
        if schedule_match:
            schedule = get_schedule(WIKI_ROOT, schedule_match.group("schedule_id"))
            self._json(
                HTTPStatus.OK if schedule else HTTPStatus.NOT_FOUND,
                schedule or {"error": "schedule_not_found"},
            )
            return
        if _FAVORITES_PATH.fullmatch(path):
            user_key = self._favorite_user_key()
            if user_key is None:
                return
            favorites = list_favorites(WIKI_ROOT, user_key)
            self._json(
                HTTPStatus.OK,
                {"favorites": favorites, "count": len(favorites)},
            )
            return
        favorite_match = _FAVORITE_PATH.fullmatch(path)
        if favorite_match:
            user_key = self._favorite_user_key()
            if user_key is None:
                return
            try:
                result = get_favorite(
                    WIKI_ROOT, user_key, favorite_match.group("signal_id")
                )
            except KeyError:
                self._signal_not_found(favorite_match.group("signal_id"))
                return
            self._json(HTTPStatus.OK, result)
            return
        match = _RUN_PATH.fullmatch(path)
        if match:
            job = JOBS.get(match.group("run_id"))
            self._json(
                HTTPStatus.OK if job else HTTPStatus.NOT_FOUND,
                job or {"error": "run_not_found"},
            )
            return
        self._json(HTTPStatus.NOT_FOUND, {"error": "not_found"})

    def do_POST(self) -> None:
        path = urlsplit(self.path).path
        if _WATCH_SCOPE_PATH.fullmatch(path):
            try:
                data = self._read_json()
                with DATABASE_EXECUTION_LOCK:
                    scope = add_watch_scope(WIKI_ROOT, data.get("company_axes"))
            except (ValueError, json.JSONDecodeError) as exc:
                self._json(
                    HTTPStatus.BAD_REQUEST,
                    {"error": "invalid_company_axes", "message": str(exc)},
                )
                return
            self._json(HTTPStatus.OK, scope)
            return
        if _OPERATIONS_PATH.fullmatch(path):
            try:
                request = OperationRequest.from_dict(
                    self._read_json(max_bytes=28 * 1024 * 1024)
                )
            except (ValueError, json.JSONDecodeError) as exc:
                self._json(
                    HTTPStatus.BAD_REQUEST,
                    {"error": "invalid_operation", "message": str(exc)},
                )
                return
            self._json(HTTPStatus.ACCEPTED, OPERATION_JOBS.create(request))
            return
        if _COMMENTS_PATH.fullmatch(path):
            try:
                data = self._read_json()
                with DATABASE_EXECUTION_LOCK:
                    comment = upsert_comment(WIKI_ROOT, data)
            except KeyError:
                self._json(HTTPStatus.NOT_FOUND, {"error": "signal_not_found"})
                return
            except (ValueError, json.JSONDecodeError) as exc:
                self._json(
                    HTTPStatus.BAD_REQUEST,
                    {"error": "invalid_comment", "message": str(exc)},
                )
                return
            self._json(HTTPStatus.CREATED if comment["created"] else HTTPStatus.OK, comment)
            return
        if path not in {"/api/research/runs", "/api/research/schedules", "/api/research/schedules/"}:
            self._json(HTTPStatus.NOT_FOUND, {"error": "not_found"})
            return
        try:
            from .service import ResearchRequest

            data = self._read_json()
            data = self._with_default_scope(data)
            request = ResearchRequest.from_dict(data)
        except (ValueError, json.JSONDecodeError) as exc:
            self._json(
                HTTPStatus.BAD_REQUEST,
                {"error": "invalid_request", "message": str(exc)},
            )
            return
        if _SCHEDULES_PATH.fullmatch(path):
            try:
                schedule = create_schedule(WIKI_ROOT, request, data)
            except ValueError as exc:
                self._json(
                    HTTPStatus.BAD_REQUEST,
                    {"error": "invalid_schedule", "message": str(exc)},
                )
                return
            self._json(HTTPStatus.CREATED, schedule)
            return
        self._json(HTTPStatus.ACCEPTED, JOBS.create(request))

    def do_PUT(self) -> None:
        path = urlsplit(self.path).path
        if _WATCH_SCOPE_PATH.fullmatch(path):
            try:
                data = self._read_json()
                with DATABASE_EXECUTION_LOCK:
                    scope = replace_watch_scope(WIKI_ROOT, data.get("company_axes"))
            except (ValueError, json.JSONDecodeError) as exc:
                self._json(
                    HTTPStatus.BAD_REQUEST,
                    {"error": "invalid_company_axes", "message": str(exc)},
                )
                return
            self._json(HTTPStatus.OK, scope)
            return
        schedule_match = _SCHEDULE_PATH.fullmatch(path)
        if schedule_match:
            try:
                data = self._read_json()
                if "enabled" not in data:
                    raise ValueError("활성 여부를 지정해 주세요.")
                schedule = set_schedule_enabled(
                    WIKI_ROOT, schedule_match.group("schedule_id"), bool(data["enabled"])
                )
            except KeyError:
                self._json(HTTPStatus.NOT_FOUND, {"error": "schedule_not_found"})
                return
            except (ValueError, json.JSONDecodeError) as exc:
                self._json(
                    HTTPStatus.BAD_REQUEST,
                    {"error": "invalid_schedule", "message": str(exc)},
                )
                return
            self._json(HTTPStatus.OK, schedule)
            return
        match = _FAVORITE_PATH.fullmatch(path)
        if not match:
            self._json(HTTPStatus.NOT_FOUND, {"error": "not_found"})
            return
        user_key = self._favorite_user_key()
        if user_key is None:
            return
        try:
            result = save_favorite(WIKI_ROOT, user_key, match.group("signal_id"))
        except KeyError:
            self._signal_not_found(match.group("signal_id"))
            return
        self._json(HTTPStatus.CREATED if result["created"] else HTTPStatus.OK, result)

    def do_DELETE(self) -> None:
        path = urlsplit(self.path).path
        if _WATCH_SCOPE_PATH.fullmatch(path):
            try:
                data = self._read_json()
                with DATABASE_EXECUTION_LOCK:
                    scope = remove_watch_scope(WIKI_ROOT, data.get("company_axes"))
            except (ValueError, json.JSONDecodeError) as exc:
                self._json(
                    HTTPStatus.BAD_REQUEST,
                    {"error": "invalid_company_axes", "message": str(exc)},
                )
                return
            self._json(HTTPStatus.OK, scope)
            return
        comment_match = _COMMENT_PATH.fullmatch(path)
        if comment_match:
            try:
                with DATABASE_EXECUTION_LOCK:
                    removed = delete_comment(WIKI_ROOT, comment_match.group("comment_id"))
            except ValueError as exc:
                self._json(
                    HTTPStatus.CONFLICT,
                    {"error": "comment_has_replies", "message": str(exc)},
                )
                return
            self._json(
                HTTPStatus.OK if removed else HTTPStatus.NOT_FOUND,
                {"removed": removed, "error": None if removed else "comment_not_found"},
            )
            return
        schedule_match = _SCHEDULE_PATH.fullmatch(path)
        if schedule_match:
            removed = delete_schedule(WIKI_ROOT, schedule_match.group("schedule_id"))
            self._json(
                HTTPStatus.OK if removed else HTTPStatus.NOT_FOUND,
                {"removed": removed, "error": None if removed else "schedule_not_found"},
            )
            return
        match = _FAVORITE_PATH.fullmatch(path)
        if not match:
            self._json(HTTPStatus.NOT_FOUND, {"error": "not_found"})
            return
        user_key = self._favorite_user_key()
        if user_key is None:
            return
        signal_id = match.group("signal_id")
        try:
            removed = remove_favorite(WIKI_ROOT, user_key, signal_id)
        except KeyError:
            self._signal_not_found(signal_id)
            return
        self._json(
            HTTPStatus.OK,
            {"signal_id": signal_id, "favorited": False, "removed": removed},
        )

    def do_PATCH(self) -> None:
        path = urlsplit(self.path).path
        if not _SETTINGS_PATH.fullmatch(path):
            self._json(HTTPStatus.NOT_FOUND, {"error": "not_found"})
            return
        try:
            data = self._read_json()
            with DATABASE_EXECUTION_LOCK:
                settings = patch_all_settings(WIKI_ROOT, data)
        except (ValueError, json.JSONDecodeError) as exc:
            self._json(
                HTTPStatus.BAD_REQUEST,
                {"error": "invalid_settings", "message": str(exc)},
            )
            return
        self._json(HTTPStatus.OK, settings)

    def _favorite_user_key(self) -> str | None:
        user_key = self.headers.get(USER_KEY_HEADER, "").strip()
        try:
            return validate_user_key(user_key)
        except ValueError as exc:
            self._json(
                HTTPStatus.BAD_REQUEST,
                {"error": "invalid_user_key", "message": str(exc)},
            )
            return None

    def _signal_not_found(self, signal_id: str) -> None:
        self._json(
            HTTPStatus.NOT_FOUND,
            {"error": "signal_not_found", "signal_id": signal_id},
        )

    def _with_default_scope(self, data: dict[str, Any]) -> dict[str, Any]:
        if data.get("company_axes") is not None or data.get("companies"):
            return data
        with DATABASE_EXECUTION_LOCK:
            scope = get_watch_scope(WIKI_ROOT)
        return {**data, "company_axes": scope["company_axes"]}

    def _capabilities(self) -> dict[str, Any]:
        return {
            "api_version": 1,
            "binding": "loopback",
            "endpoints": {
                "company_axes": "/api/settings/company-axes",
                "settings": "/api/settings",
                "research_runs": "/api/research/runs",
                "research_schedules": "/api/research/schedules",
                "operations": "/api/operations",
                "database_snapshot": "/api/database/snapshot",
                "signal_favorites": "/api/signal-favorites",
                "signal_comments": "/api/signal-comments",
            },
            "operation_count": len(ALL_COMMANDS),
        }

    def _database_snapshot(self) -> None:
        headers_sent = False
        try:
            with database_snapshot(WIKI_ROOT) as snapshot:
                path = snapshot["path"]
                if not isinstance(path, Path):
                    raise RuntimeError("SQLite snapshot path is invalid")
                self.send_response(HTTPStatus.OK)
                self._cors_headers()
                self.send_header("Content-Type", "application/vnd.sqlite3")
                self.send_header(
                    "Content-Disposition",
                    f'attachment; filename="{snapshot["filename"]}"',
                )
                self.send_header("Content-Length", str(snapshot["size"]))
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Snapshot-Generated-At", str(snapshot["generated_at"]))
                self.send_header("X-Snapshot-SHA256", str(snapshot["sha256"]))
                self.end_headers()
                headers_sent = True
                with path.open("rb") as stream:
                    shutil.copyfileobj(stream, self.wfile, length=1024 * 1024)
        except (BrokenPipeError, ConnectionResetError):
            return
        except Exception as exc:
            if not headers_sent:
                self._json(
                    HTTPStatus.INTERNAL_SERVER_ERROR,
                    {"error": "snapshot_failed", "message": str(exc)},
                )
            else:
                print(f"[research-agent] snapshot transfer failed: {exc}")

    def _read_json(self, *, max_bytes: int = 64 * 1024) -> dict[str, Any]:
        length = int(self.headers.get("content-length", "0"))
        if not 0 < length <= max_bytes:
            raise ValueError("요청 크기가 올바르지 않습니다.")
        data = json.loads(self.rfile.read(length))
        if not isinstance(data, dict):
            raise ValueError("요청 본문은 JSON 객체여야 합니다.")
        return data

    def log_message(self, fmt: str, *args: object) -> None:
        print(f"[research-agent] {self.address_string()} {fmt % args}")

    def _json(self, status: HTTPStatus, payload: object) -> None:
        body = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(status)
        self._cors_headers()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _cors_headers(self) -> None:
        origin = self.headers.get("Origin", "")
        allowed_origins = {
            "http://127.0.0.1:8200",
            "http://localhost:8200",
            *(
                item.strip()
                for item in os.environ.get("MARKET_API_ALLOWED_ORIGINS", "").split(",")
                if item.strip()
            ),
        }
        if origin in allowed_origins:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
        self.send_header(
            "Access-Control-Allow-Headers", f"Content-Type, {USER_KEY_HEADER}"
        )
        self.send_header(
            "Access-Control-Allow-Methods", "GET, POST, PUT, PATCH, DELETE, OPTIONS"
        )


def main() -> None:
    server = ThreadingHTTPServer(("127.0.0.1", 8201), Handler)
    JOBS.start_scheduler()
    print("Market Research Agent API: http://127.0.0.1:8201")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        JOBS.stop_scheduler()
        server.server_close()


if __name__ == "__main__":
    main()
