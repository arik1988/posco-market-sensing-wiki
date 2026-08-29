from __future__ import annotations

import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = (
    PROJECT_ROOT / "skills" / "market-sensing-intelligence" / "scripts"
)
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import sqlite_store  # noqa: E402


USER_KEY_HEADER = "X-Mypin-User-Key"


def validate_user_key(value: object) -> str:
    return sqlite_store.validate_favorite_user_key(value)


def list_favorites(root: Path, user_key: str) -> list[dict[str, str]]:
    return sqlite_store.list_signal_favorites(root, user_key)


def get_favorite(root: Path, user_key: str, signal_id: str) -> dict[str, Any]:
    return sqlite_store.get_signal_favorite(root, user_key, signal_id)


def save_favorite(root: Path, user_key: str, signal_id: str) -> dict[str, Any]:
    return sqlite_store.put_signal_favorite(root, user_key, signal_id)


def remove_favorite(root: Path, user_key: str, signal_id: str) -> bool:
    return sqlite_store.delete_signal_favorite(root, user_key, signal_id)
