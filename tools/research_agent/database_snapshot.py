from __future__ import annotations

import hashlib
import sys
import tempfile
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterator


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = PROJECT_ROOT / "skills" / "market-sensing-intelligence" / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import sqlite_store  # noqa: E402


@contextmanager
def database_snapshot(wiki_root: Path) -> Iterator[dict[str, object]]:
    """Create and clean up a transactionally consistent SQLite snapshot."""

    generated_at = datetime.now(UTC)
    filename = f"market_sensing-{generated_at:%Y%m%dT%H%M%SZ}.db"
    with tempfile.TemporaryDirectory(prefix="market-sensing-snapshot-") as temp_dir:
        snapshot_path = Path(temp_dir) / filename
        sqlite_store.online_backup(wiki_root, snapshot_path)
        digest = hashlib.sha256()
        with snapshot_path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        yield {
            "path": snapshot_path,
            "filename": filename,
            "generated_at": generated_at.isoformat(),
            "size": snapshot_path.stat().st_size,
            "sha256": digest.hexdigest(),
        }
