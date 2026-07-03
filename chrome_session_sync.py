"""Sync sélectif des cookies Cursor entre profils Chrome (sans écraser Google)."""
from __future__ import annotations

import os
import shutil
import sqlite3
import time
from typing import List, Tuple

_CURSOR_HOST_FRAGMENTS = (
    "cursor.com",
    "cursor.sh",
    "workos.com",
    "authenticator.cursor",
)

_CURSOR_COOKIE_NAMES = frozenset(
    {
        "WorkosCursorSessionToken",
        "cursor-web-target-synced-user",
        "workos_id",
        "workos_session",
    }
)


def _cookies_db_path(user_data_dir: str, profile_dir: str) -> str:
    return os.path.join(user_data_dir, profile_dir, "Network", "Cookies")


def _is_cursor_cookie(host_key: str, name: str) -> bool:
    hk = (host_key or "").lower()
    nm = (name or "").lower()
    if any(frag in hk for frag in _CURSOR_HOST_FRAGMENTS):
        return True
    if nm in {n.lower() for n in _CURSOR_COOKIE_NAMES}:
        return True
    return "cursor" in nm or "workos" in nm


def _delete_journal(db_path: str) -> None:
    for suffix in ("-journal", "-wal", "-shm"):
        try:
            p = db_path + suffix
            if os.path.exists(p):
                os.remove(p)
        except OSError:
            pass


def merge_cursor_cookies_sqlite(src_db: str, dst_db: str) -> int:
    """
    Fusionne uniquement les cookies Cursor/WorkOS de src_db vers dst_db.
    Retourne le nombre de cookies fusionnés.
    """
    if not os.path.isfile(src_db):
        return 0

    dst_parent = os.path.dirname(dst_db)
    if dst_parent:
        os.makedirs(dst_parent, exist_ok=True)

    if not os.path.isfile(dst_db):
        shutil.copy2(src_db, dst_db)
        return -1

    merged = 0
    src = sqlite3.connect(f"file:{src_db}?mode=ro", uri=True)
    dst = sqlite3.connect(dst_db, timeout=8.0)
    try:
        cols: List[str] = [row[1] for row in src.execute("PRAGMA table_info(cookies)").fetchall()]
        if not cols:
            return 0

        try:
            host_i = cols.index("host_key")
            name_i = cols.index("name")
            path_i = cols.index("path")
        except ValueError:
            return 0

        col_list = ", ".join(cols)
        placeholders = ", ".join("?" * len(cols))
        rows = src.execute(f"SELECT {col_list} FROM cookies").fetchall()

        for row in rows:
            host_key = row[host_i]
            name = row[name_i]
            if not _is_cursor_cookie(str(host_key or ""), str(name or "")):
                continue
            path = row[path_i]
            dst.execute(
                "DELETE FROM cookies WHERE host_key=? AND name=? AND path=?",
                (host_key, name, path),
            )
            dst.execute(
                f"INSERT INTO cookies ({col_list}) VALUES ({placeholders})",
                row,
            )
            merged += 1
        dst.commit()
    finally:
        src.close()
        dst.close()

    _delete_journal(dst_db)
    return merged


def sync_cursor_cookies_between_profiles(
    src_ud: str, dst_ud: str, profile_dir: str
) -> int:
    """Copie ciblée des cookies Cursor entre deux User Data Chrome."""
    src_db = _cookies_db_path(src_ud, profile_dir)
    dst_db = _cookies_db_path(dst_ud, profile_dir)
    for attempt in range(4):
        try:
            return merge_cursor_cookies_sqlite(src_db, dst_db)
        except (sqlite3.OperationalError, PermissionError):
            if attempt + 1 >= 4:
                raise
            time.sleep(0.55 * (attempt + 1))
    return 0
