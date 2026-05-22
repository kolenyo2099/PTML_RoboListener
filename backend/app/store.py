"""SQLite persistence for alert records.

Only alert history is stored server-side. User preferences
remain in browser local storage so they are easy to reset.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from .settings import DATABASE_PATH, DEFAULT_OUTPUT_DIR


def connect() -> sqlite3.Connection:
    DEFAULT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    _ensure_schema(connection)
    return connection


def init_db() -> None:
    with connect() as db:
        _ensure_schema(db)


def _ensure_schema(db: sqlite3.Connection) -> None:
    # SQLite doesn't support ALTER COLUMN, so we recreate the table when the
    # stationId column is still the legacy INTEGER type (from the RapidAPI era).
    row = db.execute("PRAGMA table_info(alerts)").fetchall()
    if row:
        col_types = {r[1]: r[2] for r in row}
        if col_types.get("stationId", "").upper() == "INTEGER":
            db.execute("DROP TABLE alerts")
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS alerts (
            id TEXT PRIMARY KEY,
            stationId TEXT,
            stationName TEXT,
            countryName TEXT,
            countryCode TEXT,
            languageCode TEXT,
            matchedKeyword TEXT,
            transcriptSnippet TEXT,
            fullTranscriptPath TEXT,
            clipPath TEXT,
            clipDurationSeconds REAL,
            detectedAt TEXT,
            reviewed INTEGER,
            chunkIndex INTEGER,
            matchMode TEXT,
            spaCyModelUsed TEXT
        )
        """
    )


def add_alert(alert: dict) -> None:
    with connect() as db:
        db.execute(
            """
            INSERT OR REPLACE INTO alerts VALUES (
                :id, :stationId, :stationName, :countryName, :countryCode,
                :languageCode, :matchedKeyword, :transcriptSnippet,
                :fullTranscriptPath, :clipPath, :clipDurationSeconds,
                :detectedAt, :reviewed, :chunkIndex, :matchMode,
                :spaCyModelUsed
            )
            """,
            {**alert, "reviewed": int(alert.get("reviewed", False))},
        )


def list_alerts(language: str | None = None) -> list[dict]:
    with connect() as db:
        if language:
            rows = db.execute("SELECT * FROM alerts WHERE languageCode = ? ORDER BY detectedAt DESC", (language,)).fetchall()
        else:
            rows = db.execute("SELECT * FROM alerts ORDER BY detectedAt DESC").fetchall()
    return [_row_to_alert(row) for row in rows]


def update_alert(alert_id: str, reviewed: bool) -> dict | None:
    with connect() as db:
        db.execute("UPDATE alerts SET reviewed = ? WHERE id = ?", (int(reviewed), alert_id))
        row = db.execute("SELECT * FROM alerts WHERE id = ?", (alert_id,)).fetchone()
    return _row_to_alert(row) if row else None


def delete_alert(alert_id: str) -> None:
    with connect() as db:
        db.execute("DELETE FROM alerts WHERE id = ?", (alert_id,))


def clip_exists(path: str) -> bool:
    return bool(path) and Path(path).exists()


def _row_to_alert(row: sqlite3.Row) -> dict:
    alert = dict(row)
    alert["reviewed"] = bool(alert["reviewed"])
    alert["clipExists"] = clip_exists(alert.get("clipPath", ""))
    return alert
