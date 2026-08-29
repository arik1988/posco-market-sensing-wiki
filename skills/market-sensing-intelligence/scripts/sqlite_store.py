"""Single-file SQLite persistence for market-sensing-intelligence.

The public CLI still uses legacy-looking ``Path`` objects internally so that the
large validation layer can be migrated without changing its domain behaviour.
Those paths are logical record addresses only; canonical data is stored here.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator


DATABASE_ENV = "MYPIN_DATABASE_PATH"
DATABASE_RELATIVE_PATH = Path("data/market_sensing.db")
SCHEMA_VERSION = 5

COLLECTION_PATHS: dict[str, Path] = {
    "sources": Path(".system/source-records"),
    "source_candidates": Path(".system/source-candidates"),
    "claims": Path(".system/claims"),
    "signals": Path(".system/signals"),
    "signal_versions": Path(".system/signal-versions"),
    "insights": Path(".system/insights"),
    "risk_factors": Path(".system/risk-factors"),
    "observations": Path(".system/observations"),
    "events": Path(".system/events"),
    "company_impacts": Path(".system/company-impacts"),
    "scenarios": Path(".system/scenarios"),
    "trends": Path(".system/trends"),
    "theses": Path(".system/theses"),
    "warnings": Path(".system/warnings"),
    "reviews_pending": Path(".system/reviews/pending"),
    "reviews_resolved": Path(".system/reviews/resolved"),
    "runs": Path(".system/runs"),
}
PATH_COLLECTIONS = {path.as_posix(): name for name, path in COLLECTION_PATHS.items()}

ID_FIELDS = {
    "sources": "source_id",
    "claims": "claim_id",
    "signals": "signal_id",
    "signal_versions": "signal_version_id",
    "insights": "insight_id",
    "risk_factors": "risk_factor_id",
    "observations": "observation_version_id",
    "events": "event_version_id",
    "company_impacts": "company_impact_version_id",
    "scenarios": "scenario_version_id",
    "trends": "trend_id",
    "theses": "thesis_id",
    "warnings": "warning_id",
    "reviews_pending": "review_id",
    "reviews_resolved": "review_id",
    "runs": "run_id",
}

SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS wiki_schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS wiki_records (
    collection TEXT NOT NULL,
    record_id TEXT NOT NULL,
    schema_version INTEGER,
    payload_json TEXT NOT NULL CHECK (json_valid(payload_json)),
    content_sha256 TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (collection, record_id),
    UNIQUE (record_id)
);

CREATE INDEX IF NOT EXISTS idx_wiki_records_collection_updated
ON wiki_records(collection, updated_at DESC, record_id);

CREATE TABLE IF NOT EXISTS wiki_source_contents (
    source_id TEXT PRIMARY KEY,
    media_type TEXT NOT NULL,
    encoding TEXT,
    content BLOB NOT NULL,
    raw_sha256 TEXT NOT NULL,
    normalized_sha256 TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (source_id) REFERENCES wiki_records(record_id)
        ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED
);

CREATE TABLE IF NOT EXISTS wiki_binary_assets (
    asset_id TEXT PRIMARY KEY,
    source_id TEXT,
    media_type TEXT NOT NULL,
    content BLOB NOT NULL,
    content_sha256 TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}' CHECK (json_valid(metadata_json)),
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_wiki_binary_assets_source
ON wiki_binary_assets(source_id);

CREATE TABLE IF NOT EXISTS wiki_artifacts (
    artifact_id TEXT PRIMARY KEY,
    artifact_type TEXT NOT NULL,
    title TEXT NOT NULL,
    markdown_text TEXT,
    html_text TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}' CHECK (json_valid(metadata_json)),
    content_sha256 TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_wiki_artifacts_type_updated
ON wiki_artifacts(artifact_type, updated_at DESC);

CREATE TABLE IF NOT EXISTS wiki_settings (
    settings_id TEXT PRIMARY KEY,
    payload_json TEXT NOT NULL CHECK (json_valid(payload_json)),
    content_sha256 TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS wiki_operation_log (
    log_id INTEGER PRIMARY KEY AUTOINCREMENT,
    occurred_at TEXT NOT NULL,
    operation TEXT NOT NULL,
    detail TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS wiki_source_assets (
    source_id TEXT PRIMARY KEY,
    source_type TEXT NOT NULL,
    source_modality TEXT NOT NULL CHECK (
        source_modality IN ('MARKET', 'DOCUMENT', 'PHYSICAL', 'ATTENTION')
    ),
    payload_json TEXT NOT NULL CHECK (json_valid(payload_json)),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (source_id) REFERENCES wiki_records(record_id) ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS wiki_risk_factors (
    risk_factor_id TEXT PRIMARY KEY,
    taxonomy_version INTEGER NOT NULL CHECK (taxonomy_version >= 1),
    name TEXT NOT NULL,
    definition TEXT NOT NULL,
    category TEXT NOT NULL,
    parent_risk_factor_id TEXT,
    status TEXT NOT NULL CHECK (status IN ('active', 'retired')),
    payload_json TEXT NOT NULL CHECK (json_valid(payload_json)),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (parent_risk_factor_id) REFERENCES wiki_risk_factors(risk_factor_id)
        ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS wiki_signal_versions (
    signal_version_id TEXT PRIMARY KEY,
    signal_id TEXT NOT NULL,
    version_no INTEGER NOT NULL CHECK (version_no >= 1),
    canonical_key TEXT NOT NULL,
    payload_json TEXT NOT NULL CHECK (json_valid(payload_json)),
    content_sha256 TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (signal_id, version_no)
);

CREATE TABLE IF NOT EXISTS wiki_claim_versions (
    claim_version_id TEXT PRIMARY KEY,
    claim_id TEXT NOT NULL,
    version_no INTEGER NOT NULL CHECK (version_no >= 1),
    payload_json TEXT NOT NULL CHECK (json_valid(payload_json)),
    created_at TEXT NOT NULL,
    UNIQUE (claim_id, version_no)
);

CREATE INDEX IF NOT EXISTS idx_wiki_claim_versions_claim
ON wiki_claim_versions(claim_id, version_no DESC);

CREATE TABLE IF NOT EXISTS wiki_observation_versions (
    observation_version_id TEXT PRIMARY KEY,
    observation_id TEXT NOT NULL,
    version_no INTEGER NOT NULL CHECK (version_no >= 1),
    source_id TEXT NOT NULL,
    modality TEXT NOT NULL CHECK (
        modality IN ('MARKET', 'PHYSICAL', 'ATTENTION')
    ),
    payload_json TEXT NOT NULL CHECK (json_valid(payload_json)),
    created_at TEXT NOT NULL,
    UNIQUE (observation_id, version_no),
    FOREIGN KEY (source_id) REFERENCES wiki_source_assets(source_id) ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS wiki_event_versions (
    event_version_id TEXT PRIMARY KEY,
    event_id TEXT NOT NULL,
    version_no INTEGER NOT NULL CHECK (version_no >= 1),
    modality TEXT NOT NULL CHECK (
        modality IN ('MARKET', 'DOCUMENT', 'PHYSICAL', 'ATTENTION')
    ),
    payload_json TEXT NOT NULL CHECK (json_valid(payload_json)),
    created_at TEXT NOT NULL,
    UNIQUE (event_id, version_no)
);

CREATE INDEX IF NOT EXISTS idx_wiki_signal_versions_signal
ON wiki_signal_versions(signal_id, version_no DESC);

CREATE TABLE IF NOT EXISTS wiki_signal_evidence (
    signal_version_id TEXT NOT NULL,
    evidence_kind TEXT NOT NULL CHECK (
        evidence_kind IN ('claim', 'event', 'observation')
    ),
    evidence_version_id TEXT NOT NULL,
    modality TEXT NOT NULL CHECK (
        modality IN ('MARKET', 'DOCUMENT', 'PHYSICAL', 'ATTENTION')
    ),
    relation TEXT NOT NULL CHECK (relation IN ('support', 'contradict', 'context')),
    payload_json TEXT NOT NULL DEFAULT '{}' CHECK (json_valid(payload_json)),
    PRIMARY KEY (signal_version_id, evidence_kind, evidence_version_id, relation),
    FOREIGN KEY (signal_version_id) REFERENCES wiki_signal_versions(signal_version_id)
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_wiki_signal_evidence_subject
ON wiki_signal_evidence(evidence_kind, evidence_version_id);

CREATE TABLE IF NOT EXISTS wiki_risk_factor_links (
    risk_factor_id TEXT NOT NULL,
    subject_kind TEXT NOT NULL CHECK (
        subject_kind IN ('claim', 'event', 'observation', 'signal')
    ),
    subject_version_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (risk_factor_id, subject_kind, subject_version_id),
    FOREIGN KEY (risk_factor_id) REFERENCES wiki_risk_factors(risk_factor_id)
        ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS idx_wiki_risk_factor_links_subject
ON wiki_risk_factor_links(subject_kind, subject_version_id);

CREATE TABLE IF NOT EXISTS wiki_company_impact_versions (
    company_impact_version_id TEXT PRIMARY KEY,
    signal_version_id TEXT NOT NULL,
    company_id TEXT NOT NULL,
    business_axis TEXT NOT NULL,
    version_no INTEGER NOT NULL CHECK (version_no >= 1),
    payload_json TEXT NOT NULL CHECK (json_valid(payload_json)),
    created_at TEXT NOT NULL,
    UNIQUE (signal_version_id, company_id, business_axis, version_no),
    FOREIGN KEY (signal_version_id) REFERENCES wiki_signal_versions(signal_version_id)
        ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS wiki_scenario_versions (
    scenario_version_id TEXT PRIMARY KEY,
    signal_version_id TEXT NOT NULL,
    scenario_key TEXT NOT NULL,
    version_no INTEGER NOT NULL CHECK (version_no >= 1),
    payload_json TEXT NOT NULL CHECK (json_valid(payload_json)),
    created_at TEXT NOT NULL,
    UNIQUE (signal_version_id, scenario_key, version_no),
    FOREIGN KEY (signal_version_id) REFERENCES wiki_signal_versions(signal_version_id)
        ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS wiki_signal_favorites (
    user_key TEXT NOT NULL,
    signal_id TEXT NOT NULL,
    favorited_at TEXT NOT NULL,
    PRIMARY KEY (user_key, signal_id),
    FOREIGN KEY (signal_id) REFERENCES wiki_records(record_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_wiki_signal_favorites_user_time
ON wiki_signal_favorites(user_key, favorited_at DESC, signal_id);

CREATE INDEX IF NOT EXISTS idx_wiki_signal_favorites_signal
ON wiki_signal_favorites(signal_id);

CREATE TABLE IF NOT EXISTS wiki_signal_comments (
    comment_id TEXT PRIMARY KEY,
    signal_id TEXT NOT NULL,
    source_system TEXT NOT NULL,
    source_comment_id TEXT NOT NULL,
    parent_comment_id TEXT,
    author_user_key TEXT NOT NULL,
    author_display_name TEXT NOT NULL,
    author_company TEXT,
    author_department TEXT,
    stance TEXT NOT NULL CHECK (stance IN ('agree', 'skeptical')),
    comment_text TEXT NOT NULL CHECK (length(trim(comment_text)) > 0),
    decision_deadline TEXT CHECK (
        decision_deadline IS NULL OR (
            length(decision_deadline) = 10
            AND date(decision_deadline) = decision_deadline
        )
    ),
    source_created_at TEXT NOT NULL,
    source_updated_at TEXT NOT NULL,
    imported_at TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}' CHECK (json_valid(metadata_json)),
    UNIQUE (source_system, source_comment_id),
    FOREIGN KEY (signal_id) REFERENCES wiki_records(record_id) ON DELETE CASCADE,
    FOREIGN KEY (parent_comment_id) REFERENCES wiki_signal_comments(comment_id)
        ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_wiki_signal_comments_signal_time
ON wiki_signal_comments(signal_id, source_created_at DESC, comment_id);

CREATE INDEX IF NOT EXISTS idx_wiki_signal_comments_signal_stance
ON wiki_signal_comments(signal_id, stance, source_created_at DESC);

CREATE INDEX IF NOT EXISTS idx_wiki_signal_comments_deadline
ON wiki_signal_comments(signal_id, decision_deadline)
WHERE decision_deadline IS NOT NULL;

CREATE TABLE IF NOT EXISTS wiki_research_schedules (
    schedule_id TEXT PRIMARY KEY,
    payload_json TEXT NOT NULL CHECK (json_valid(payload_json)),
    enabled INTEGER NOT NULL CHECK (enabled IN (0, 1)),
    next_run_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_wiki_research_schedules_due
ON wiki_research_schedules(enabled, next_run_at, schedule_id);
"""


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _json_text(value: dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def database_path(root: Path) -> Path:
    configured = os.environ.get(DATABASE_ENV, "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    return (root.resolve() / DATABASE_RELATIVE_PATH).resolve()


def connect(root: Path) -> sqlite3.Connection:
    path = database_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=30)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 30000")
    connection.execute("PRAGMA journal_mode = WAL")
    connection.executescript(SCHEMA)
    applied_at = _now()
    connection.executemany(
        "INSERT OR IGNORE INTO wiki_schema_migrations(version, applied_at) VALUES (?, ?)",
        [(version, applied_at) for version in range(1, SCHEMA_VERSION + 1)],
    )
    connection.commit()
    return connection


@contextmanager
def transaction(root: Path) -> Iterator[sqlite3.Connection]:
    connection = connect(root)
    try:
        connection.execute("BEGIN IMMEDIATE")
        yield connection
        connection.commit()
    except BaseException:
        connection.rollback()
        raise
    finally:
        connection.close()


@contextmanager
def connection_scope(root: Path) -> Iterator[sqlite3.Connection]:
    connection = connect(root)
    try:
        yield connection
        connection.commit()
    except BaseException:
        connection.rollback()
        raise
    finally:
        connection.close()


def initialize(root: Path) -> Path:
    with connection_scope(root) as connection:
        connection.execute("PRAGMA optimize")
    return database_path(root)


def infer_root_and_collection(path: Path) -> tuple[Path, str] | None:
    resolved = path.resolve()
    normalized = resolved.as_posix()
    for relative, collection in PATH_COLLECTIONS.items():
        marker = "/" + relative + "/"
        if marker in normalized:
            root_text = normalized.split(marker, 1)[0]
            return Path(root_text), collection
    return None


def collection_for_directory(directory: Path) -> tuple[Path, str] | None:
    resolved = directory.resolve()
    normalized = resolved.as_posix().rstrip("/")
    for relative, collection in PATH_COLLECTIONS.items():
        suffix = "/" + relative
        if normalized.endswith(suffix):
            return Path(normalized[: -len(suffix)]), collection
    return None


def logical_record_path(root: Path, collection: str, record_id: str) -> Path:
    return root / COLLECTION_PATHS[collection] / f"{record_id}.json"


def upsert_record(root: Path, collection: str, record_id: str, value: dict[str, Any]) -> None:
    payload = _json_text(value)
    now = _now()
    with connection_scope(root) as connection:
        connection.execute(
            """
            INSERT INTO wiki_records(
                collection, record_id, schema_version, payload_json,
                content_sha256, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(record_id) DO UPDATE SET
                collection=excluded.collection,
                schema_version=excluded.schema_version,
                payload_json=excluded.payload_json,
                content_sha256=excluded.content_sha256,
                updated_at=excluded.updated_at
            """,
            (
                collection,
                record_id,
                value.get("schema_version"),
                payload,
                _digest(payload.encode("utf-8")),
                now,
                now,
            ),
        )


def put_risk_factor(root: Path, value: dict[str, Any]) -> None:
    """Persist a governed risk-factor definition and its JSON record together."""

    risk_factor_id = str(value["risk_factor_id"])
    upsert_record(root, "risk_factors", risk_factor_id, value)
    payload = _json_text(value)
    now = _now()
    with connection_scope(root) as connection:
        connection.execute(
            """
            INSERT INTO wiki_risk_factors(
                risk_factor_id, taxonomy_version, name, definition, category,
                parent_risk_factor_id, status, payload_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(risk_factor_id) DO UPDATE SET
                taxonomy_version=excluded.taxonomy_version,
                name=excluded.name,
                definition=excluded.definition,
                category=excluded.category,
                parent_risk_factor_id=excluded.parent_risk_factor_id,
                status=excluded.status,
                payload_json=excluded.payload_json,
                updated_at=excluded.updated_at
            """,
            (
                risk_factor_id,
                int(value["taxonomy_version"]),
                str(value["name"]),
                str(value["definition"]),
                str(value["category"]),
                value.get("parent_risk_factor_id"),
                str(value["status"]),
                payload,
                str(value.get("created_at") or now),
                str(value.get("updated_at") or now),
            ),
        )


def put_source_asset(root: Path, value: dict[str, Any]) -> None:
    source_id = str(value["source_id"])
    payload = _json_text(value)
    now = _now()
    with connection_scope(root) as connection:
        connection.execute(
            """
            INSERT INTO wiki_source_assets(
                source_id, source_type, source_modality, payload_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(source_id) DO UPDATE SET
                source_type=excluded.source_type,
                source_modality=excluded.source_modality,
                payload_json=excluded.payload_json,
                updated_at=excluded.updated_at
            """,
            (
                source_id,
                str(value["source_type"]),
                str(value["source_modality"]),
                payload,
                str(value.get("collected_at") or now),
                now,
            ),
        )


def put_claim_version(root: Path, value: dict[str, Any]) -> None:
    payload = _json_text(value)
    with connection_scope(root) as connection:
        connection.execute(
            """
            INSERT OR IGNORE INTO wiki_claim_versions(
                claim_version_id, claim_id, version_no, payload_json, created_at
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                str(value["claim_version_id"]),
                str(value["claim_id"]),
                int(value["version_no"]),
                payload,
                str(value.get("last_verified") or _now()),
            ),
        )


def put_observation_version(root: Path, value: dict[str, Any]) -> None:
    payload = _json_text(value)
    with connection_scope(root) as connection:
        connection.execute(
            """
            INSERT OR IGNORE INTO wiki_observation_versions(
                observation_version_id, observation_id, version_no, source_id,
                modality, payload_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(value["observation_version_id"]),
                str(value["observation_id"]),
                int(value["version_no"]),
                str(value["source_id"]),
                str(value["modality"]),
                payload,
                str(value.get("created_at") or _now()),
            ),
        )


def put_event_version(root: Path, value: dict[str, Any]) -> None:
    payload = _json_text(value)
    with connection_scope(root) as connection:
        connection.execute(
            """
            INSERT OR IGNORE INTO wiki_event_versions(
                event_version_id, event_id, version_no, modality, payload_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                str(value["event_version_id"]),
                str(value["event_id"]),
                int(value["version_no"]),
                str(value["modality"]),
                payload,
                str(value.get("created_at") or _now()),
            ),
        )


def put_signal_analytics_bundle(
    root: Path,
    signal_version: dict[str, Any],
    company_impacts: list[dict[str, Any]],
    scenarios: list[dict[str, Any]],
) -> None:
    """Atomically persist one canonical Signal version and its analytics graph."""

    signal_version_id = str(signal_version["signal_version_id"])
    signal_payload = _json_text(signal_version)
    now = str(signal_version.get("created_at") or _now())
    with transaction(root) as connection:
        connection.execute(
            """
            INSERT INTO wiki_signal_versions(
                signal_version_id, signal_id, version_no, canonical_key,
                payload_json, content_sha256, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                signal_version_id,
                str(signal_version["signal_id"]),
                int(signal_version["version_no"]),
                str(signal_version["canonical_key"]),
                signal_payload,
                _digest(signal_payload.encode("utf-8")),
                now,
            ),
        )
        for evidence in signal_version["evidence_refs"]:
            connection.execute(
                """
                INSERT INTO wiki_signal_evidence(
                    signal_version_id, evidence_kind, evidence_version_id,
                    modality, relation, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    signal_version_id,
                    str(evidence["kind"]),
                    str(evidence["version_id"]),
                    str(evidence["modality"]),
                    str(evidence["relation"]),
                    _json_text(evidence),
                ),
            )
        for risk_factor_id in signal_version["risk_factor_ids"]:
            connection.execute(
                """
                INSERT INTO wiki_risk_factor_links(
                    risk_factor_id, subject_kind, subject_version_id, created_at
                ) VALUES (?, 'signal', ?, ?)
                """,
                (str(risk_factor_id), signal_version_id, now),
            )
        for impact in company_impacts:
            payload = _json_text(impact)
            connection.execute(
                """
                INSERT INTO wiki_company_impact_versions(
                    company_impact_version_id, signal_version_id, company_id,
                    business_axis, version_no, payload_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(impact["company_impact_version_id"]),
                    signal_version_id,
                    str(impact["company_id"]),
                    str(impact["business_axis"]),
                    int(impact["version_no"]),
                    payload,
                    str(impact.get("created_at") or now),
                ),
            )
        for scenario in scenarios:
            payload = _json_text(scenario)
            connection.execute(
                """
                INSERT INTO wiki_scenario_versions(
                    scenario_version_id, signal_version_id, scenario_key,
                    version_no, payload_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    str(scenario["scenario_version_id"]),
                    signal_version_id,
                    str(scenario["scenario_key"]),
                    int(scenario["version_no"]),
                    payload,
                    str(scenario.get("created_at") or now),
                ),
            )


def put_risk_factor_links(
    root: Path,
    *,
    subject_kind: str,
    subject_version_id: str,
    risk_factor_ids: list[str],
    created_at: str | None = None,
) -> None:
    """Persist pre-promotion Observation, Event, or Claim risk-factor links."""

    now = created_at or _now()
    with transaction(root) as connection:
        for risk_factor_id in dict.fromkeys(risk_factor_ids):
            connection.execute(
                """
                INSERT INTO wiki_risk_factor_links(
                    risk_factor_id, subject_kind, subject_version_id, created_at
                ) VALUES (?, ?, ?, ?)
                """,
                (risk_factor_id, subject_kind, subject_version_id, now),
            )


def write_logical_json(path: Path, value: dict[str, Any]) -> bool:
    inferred = infer_root_and_collection(path)
    if inferred is None:
        return False
    root, collection = inferred
    id_field = ID_FIELDS.get(collection)
    record_id = str(value.get(id_field) if id_field else "").strip() or path.stem
    upsert_record(root, collection, record_id, value)
    return True


def read_record(root: Path, collection: str, record_id: str) -> dict[str, Any] | None:
    with connection_scope(root) as connection:
        row = connection.execute(
            "SELECT payload_json FROM wiki_records WHERE collection=? AND record_id=?",
            (collection, record_id),
        ).fetchone()
    return json.loads(row["payload_json"]) if row else None


def read_logical_json(path: Path) -> dict[str, Any] | None:
    inferred = infer_root_and_collection(path)
    if inferred is None:
        return None
    root, collection = inferred
    return read_record(root, collection, path.stem)


def list_records(root: Path, collection: str) -> list[tuple[Path, dict[str, Any]]]:
    with connection_scope(root) as connection:
        rows = connection.execute(
            "SELECT record_id, payload_json FROM wiki_records WHERE collection=? ORDER BY record_id",
            (collection,),
        ).fetchall()
    return [
        (logical_record_path(root, collection, row["record_id"]), json.loads(row["payload_json"]))
        for row in rows
    ]


def list_logical_json(directory: Path) -> list[tuple[Path, dict[str, Any]]] | None:
    inferred = collection_for_directory(directory)
    if inferred is None:
        return None
    return list_records(*inferred)


def record_exists(root: Path, collection: str, record_id: str) -> bool:
    with connection_scope(root) as connection:
        row = connection.execute(
            "SELECT 1 FROM wiki_records WHERE collection=? AND record_id=?",
            (collection, record_id),
        ).fetchone()
    return row is not None


def delete_record(root: Path, collection: str, record_id: str) -> None:
    with connection_scope(root) as connection:
        connection.execute(
            "DELETE FROM wiki_records WHERE collection=? AND record_id=?",
            (collection, record_id),
        )


def put_source_content(root: Path, source_id: str, content: bytes, media_type: str = "text/markdown") -> None:
    with connection_scope(root) as connection:
        connection.execute(
            """
            INSERT INTO wiki_source_contents(
                source_id, media_type, encoding, content, raw_sha256,
                normalized_sha256, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(source_id) DO UPDATE SET
                media_type=excluded.media_type,
                encoding=excluded.encoding,
                content=excluded.content,
                raw_sha256=excluded.raw_sha256,
                normalized_sha256=excluded.normalized_sha256
            """,
            (
                source_id,
                media_type,
                "utf-8" if media_type.startswith("text/") else None,
                content,
                _digest(content),
                _digest(" ".join(content.decode("utf-8", errors="replace").split()).casefold().encode("utf-8")),
                _now(),
            ),
        )


def get_source_content(root: Path, source_id: str) -> bytes | None:
    with connection_scope(root) as connection:
        row = connection.execute(
            "SELECT content FROM wiki_source_contents WHERE source_id=?",
            (source_id,),
        ).fetchone()
    return bytes(row["content"]) if row else None


def put_binary_asset(
    root: Path,
    asset_id: str,
    content: bytes,
    *,
    source_id: str | None = None,
    media_type: str = "application/octet-stream",
    metadata: dict[str, Any] | None = None,
) -> None:
    with connection_scope(root) as connection:
        connection.execute(
            """
            INSERT INTO wiki_binary_assets(
                asset_id, source_id, media_type, content, content_sha256,
                metadata_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(asset_id) DO UPDATE SET
                source_id=excluded.source_id,
                media_type=excluded.media_type,
                content=excluded.content,
                content_sha256=excluded.content_sha256,
                metadata_json=excluded.metadata_json
            """,
            (asset_id, source_id, media_type, content, _digest(content), _json_text(metadata or {}), _now()),
        )


def get_binary_asset(root: Path, asset_id: str) -> bytes | None:
    with connection_scope(root) as connection:
        row = connection.execute(
            "SELECT content FROM wiki_binary_assets WHERE asset_id=?", (asset_id,)
        ).fetchone()
    return bytes(row["content"]) if row else None


def put_artifact(
    root: Path,
    artifact_id: str,
    artifact_type: str,
    title: str,
    *,
    markdown_text: str | None = None,
    html_text: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    payload = ((markdown_text or "") + "\0" + (html_text or "")).encode("utf-8")
    now = _now()
    with connection_scope(root) as connection:
        connection.execute(
            """
            INSERT INTO wiki_artifacts(
                artifact_id, artifact_type, title, markdown_text, html_text,
                metadata_json, content_sha256, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(artifact_id) DO UPDATE SET
                artifact_type=excluded.artifact_type,
                title=excluded.title,
                markdown_text=excluded.markdown_text,
                html_text=excluded.html_text,
                metadata_json=excluded.metadata_json,
                content_sha256=excluded.content_sha256,
                updated_at=excluded.updated_at
            """,
            (
                artifact_id,
                artifact_type,
                title,
                markdown_text,
                html_text,
                _json_text(metadata or {}),
                _digest(payload),
                now,
                now,
            ),
        )


def get_artifact(root: Path, artifact_id: str) -> dict[str, Any] | None:
    with connection_scope(root) as connection:
        row = connection.execute(
            "SELECT * FROM wiki_artifacts WHERE artifact_id=?", (artifact_id,)
        ).fetchone()
    if row is None:
        return None
    value = dict(row)
    value["metadata"] = json.loads(value.pop("metadata_json"))
    return value


def list_artifacts(root: Path, artifact_type: str | None = None) -> list[dict[str, Any]]:
    query = "SELECT * FROM wiki_artifacts"
    params: tuple[Any, ...] = ()
    if artifact_type:
        query += " WHERE artifact_type=?"
        params = (artifact_type,)
    query += " ORDER BY updated_at DESC, artifact_id"
    with connection_scope(root) as connection:
        rows = connection.execute(query, params).fetchall()
    values = []
    for row in rows:
        value = dict(row)
        value["metadata"] = json.loads(value.pop("metadata_json"))
        values.append(value)
    return values


def put_settings(root: Path, settings_id: str, value: dict[str, Any]) -> None:
    payload = _json_text(value)
    with connection_scope(root) as connection:
        connection.execute(
            """
            INSERT INTO wiki_settings(settings_id, payload_json, content_sha256, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(settings_id) DO UPDATE SET
                payload_json=excluded.payload_json,
                content_sha256=excluded.content_sha256,
                updated_at=excluded.updated_at
            """,
            (settings_id, payload, _digest(payload.encode("utf-8")), _now()),
        )


def get_settings(root: Path, settings_id: str) -> dict[str, Any] | None:
    with connection_scope(root) as connection:
        row = connection.execute(
            "SELECT payload_json FROM wiki_settings WHERE settings_id=?", (settings_id,)
        ).fetchone()
    return json.loads(row["payload_json"]) if row else None


def append_operation_log(root: Path, occurred_at: str, operation: str, detail: str) -> None:
    with connection_scope(root) as connection:
        connection.execute(
            "INSERT INTO wiki_operation_log(occurred_at, operation, detail) VALUES (?, ?, ?)",
            (occurred_at, operation, detail),
        )


def _favorite_identity(value: object, field: str, maximum: int) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{field} is required")
    if len(text) > maximum:
        raise ValueError(f"{field} must be at most {maximum} characters")
    if any(ord(character) < 32 or ord(character) == 127 for character in text):
        raise ValueError(f"{field} must not contain control characters")
    return text


def validate_favorite_user_key(value: object) -> str:
    """Validate the opaque, authentication-derived owner key used by the API."""
    return _favorite_identity(value, "user_key", 128)


def put_signal_favorite(root: Path, user_key: str, signal_id: str) -> dict[str, Any]:
    """Idempotently save one user's favorite against a stable Signal identity."""
    normalized_user = validate_favorite_user_key(user_key)
    normalized_signal = _favorite_identity(signal_id, "signal_id", 128)
    with transaction(root) as connection:
        signal = connection.execute(
            """
            SELECT 1
            FROM wiki_records
            WHERE collection = 'signals' AND record_id = ?
            """,
            (normalized_signal,),
        ).fetchone()
        if signal is None:
            raise KeyError(normalized_signal)
        favorited_at = _now()
        cursor = connection.execute(
            """
            INSERT OR IGNORE INTO wiki_signal_favorites(
                user_key, signal_id, favorited_at
            ) VALUES (?, ?, ?)
            """,
            (normalized_user, normalized_signal, favorited_at),
        )
        row = connection.execute(
            """
            SELECT signal_id, favorited_at
            FROM wiki_signal_favorites
            WHERE user_key = ? AND signal_id = ?
            """,
            (normalized_user, normalized_signal),
        ).fetchone()
    return {
        "signal_id": row["signal_id"],
        "favorited": True,
        "favorited_at": row["favorited_at"],
        "created": cursor.rowcount == 1,
    }


def delete_signal_favorite(root: Path, user_key: str, signal_id: str) -> bool:
    """Idempotently remove one user's favorite without changing Signal data."""
    normalized_user = validate_favorite_user_key(user_key)
    normalized_signal = _favorite_identity(signal_id, "signal_id", 128)
    with transaction(root) as connection:
        signal = connection.execute(
            """
            SELECT 1
            FROM wiki_records
            WHERE collection = 'signals' AND record_id = ?
            """,
            (normalized_signal,),
        ).fetchone()
        if signal is None:
            raise KeyError(normalized_signal)
        cursor = connection.execute(
            """
            DELETE FROM wiki_signal_favorites
            WHERE user_key = ? AND signal_id = ?
            """,
            (normalized_user, normalized_signal),
        )
    return cursor.rowcount == 1


def get_signal_favorite(root: Path, user_key: str, signal_id: str) -> dict[str, Any]:
    normalized_user = validate_favorite_user_key(user_key)
    normalized_signal = _favorite_identity(signal_id, "signal_id", 128)
    with connection_scope(root) as connection:
        signal = connection.execute(
            """
            SELECT 1
            FROM wiki_records
            WHERE collection = 'signals' AND record_id = ?
            """,
            (normalized_signal,),
        ).fetchone()
        if signal is None:
            raise KeyError(normalized_signal)
        row = connection.execute(
            """
            SELECT signal_id, favorited_at
            FROM wiki_signal_favorites
            WHERE user_key = ? AND signal_id = ?
            """,
            (normalized_user, normalized_signal),
        ).fetchone()
    return {
        "signal_id": normalized_signal,
        "favorited": row is not None,
        "favorited_at": row["favorited_at"] if row is not None else None,
    }


def list_signal_favorites(root: Path, user_key: str) -> list[dict[str, str]]:
    normalized_user = validate_favorite_user_key(user_key)
    with connection_scope(root) as connection:
        rows = connection.execute(
            """
            SELECT favorite.signal_id, favorite.favorited_at
            FROM wiki_signal_favorites AS favorite
            JOIN wiki_records AS signal
              ON signal.record_id = favorite.signal_id
             AND signal.collection = 'signals'
            WHERE favorite.user_key = ?
            ORDER BY favorite.favorited_at DESC, favorite.signal_id
            """,
            (normalized_user,),
        ).fetchall()
    return [
        {"signal_id": row["signal_id"], "favorited_at": row["favorited_at"]}
        for row in rows
    ]


def integrity(root: Path) -> dict[str, Any]:
    with connection_scope(root) as connection:
        integrity_check = connection.execute("PRAGMA integrity_check").fetchone()[0]
        foreign_key_check = [dict(row) for row in connection.execute("PRAGMA foreign_key_check")]
        record_counts = {
            row["collection"]: row["count"]
            for row in connection.execute(
                "SELECT collection, COUNT(*) AS count FROM wiki_records GROUP BY collection"
            )
        }
        source_content_count = connection.execute(
            "SELECT COUNT(*) FROM wiki_source_contents"
        ).fetchone()[0]
        artifact_count = connection.execute("SELECT COUNT(*) FROM wiki_artifacts").fetchone()[0]
        analytics_tables = (
            "wiki_source_assets",
            "wiki_risk_factors",
            "wiki_claim_versions",
            "wiki_observation_versions",
            "wiki_event_versions",
            "wiki_signal_versions",
            "wiki_signal_evidence",
            "wiki_risk_factor_links",
            "wiki_company_impact_versions",
            "wiki_scenario_versions",
            "wiki_signal_favorites",
            "wiki_signal_comments",
        )
        analytics_counts = {
            table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in analytics_tables
        }
    return {
        "database": str(database_path(root)),
        "integrity_check": integrity_check,
        "foreign_key_check": foreign_key_check,
        "record_counts": record_counts,
        "source_content_count": source_content_count,
        "artifact_count": artifact_count,
        "analytics_counts": analytics_counts,
    }


def online_backup(root: Path, destination: Path) -> Path:
    destination = destination.resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    source = connect(root)
    target = sqlite3.connect(destination)
    try:
        source.backup(target)
        target.commit()
        if target.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise RuntimeError("SQLite backup integrity_check failed")
    finally:
        target.close()
        source.close()
    return destination
