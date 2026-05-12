from __future__ import annotations

import argparse
import json
import logging
import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import chromadb
from model_cache import get_embedding_function


LOGGER = logging.getLogger("viernes.phase2.indexer")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_iso8601(value: str) -> datetime:
    normalized = value.replace("Z", "+00:00")
    return datetime.fromisoformat(normalized)


@dataclass
class EventRow:
    event_id: int
    timestamp: str
    app_name: str | None
    event_type: str
    value: str | None
    file_path: str | None


@dataclass
class SessionMemory:
    session_id: str
    start_ts: str
    end_ts: str
    event_count: int
    summary: str
    apps_json: str
    files_json: str
    metadata: dict[str, Any]
    max_event_id: int


class SemanticMemoryIndexer:
    def __init__(
        self,
        db_path: str = "events.db",
        chroma_path: str = "chroma_db",
        collection_name: str = "viernes_sessions",
        embedding_model: str = "all-MiniLM-L6-v2",
        inactivity_gap_seconds: int = 300,
        batch_size: int = 5000,
    ) -> None:
        self.db_path = Path(db_path)
        self.chroma_path = Path(chroma_path)
        self.collection_name = collection_name
        self.inactivity_gap_seconds = inactivity_gap_seconds
        self.batch_size = batch_size

        self.conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._ensure_tables()
        self._ensure_events_table()

        self.embedding_fn = get_embedding_function(model_name=embedding_model)
        self.chroma_client = chromadb.PersistentClient(path=str(self.chroma_path))
        self.collection = self.chroma_client.get_or_create_collection(
            name=self.collection_name,
            embedding_function=self.embedding_fn,
        )

    def _ensure_tables(self) -> None:
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS metadata (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS session_memories (
                session_id TEXT PRIMARY KEY,
                start_ts TEXT NOT NULL,
                end_ts TEXT NOT NULL,
                event_count INTEGER NOT NULL,
                summary TEXT NOT NULL,
                apps_json TEXT NOT NULL,
                files_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        self.conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_session_memories_start
            ON session_memories(start_ts)
            """
        )
        self.conn.commit()

    def _ensure_events_table(self) -> None:
        row = self.conn.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type='table' AND name='events'
            """
        ).fetchone()
        if row is None:
            raise RuntimeError(
                "No existe la tabla events. Ejecuta activity_logger.py y genera datos primero."
            )

    def _get_last_indexed_event_id(self) -> int:
        row = self.conn.execute(
            "SELECT value FROM metadata WHERE key = 'last_indexed_event_id'"
        ).fetchone()
        if row is None:
            return 0
        return int(row["value"])

    def _set_last_indexed_event_id(self, event_id: int) -> None:
        self.conn.execute(
            """
            INSERT INTO metadata (key, value)
            VALUES ('last_indexed_event_id', ?)
            ON CONFLICT(key) DO UPDATE SET value=excluded.value
            """,
            (str(event_id),),
        )
        self.conn.commit()

    def _fetch_new_events(self, since_id: int) -> list[EventRow]:
        rows = self.conn.execute(
            """
            SELECT id, timestamp, app_name, event_type, value, file_path
            FROM events
            WHERE id > ?
            ORDER BY id ASC
            LIMIT ?
            """,
            (since_id, self.batch_size),
        ).fetchall()
        return [
            EventRow(
                event_id=int(row["id"]),
                timestamp=str(row["timestamp"]),
                app_name=row["app_name"],
                event_type=str(row["event_type"]),
                value=row["value"],
                file_path=row["file_path"],
            )
            for row in rows
        ]

    def _split_into_sessions(self, events: list[EventRow]) -> list[list[EventRow]]:
        if not events:
            return []

        sessions: list[list[EventRow]] = []
        current: list[EventRow] = [events[0]]
        prev_ts = parse_iso8601(events[0].timestamp)

        for event in events[1:]:
            current_ts = parse_iso8601(event.timestamp)
            gap = (current_ts - prev_ts).total_seconds()
            if gap > self.inactivity_gap_seconds:
                sessions.append(current)
                current = [event]
            else:
                current.append(event)
            prev_ts = current_ts

        sessions.append(current)
        return sessions

    def _build_session(self, events: list[EventRow]) -> SessionMemory:
        start_ts = events[0].timestamp
        end_ts = events[-1].timestamp
        session_id = f"session-{events[0].event_id}-{events[-1].event_id}"

        app_counts: dict[str, int] = {}
        type_counts: dict[str, int] = {}
        files: list[str] = []

        for event in events:
            app_key = event.app_name or "unknown_app"
            app_counts[app_key] = app_counts.get(app_key, 0) + 1
            type_counts[event.event_type] = type_counts.get(event.event_type, 0) + 1
            if event.file_path:
                files.append(event.file_path)

        sorted_apps = sorted(app_counts.items(), key=lambda x: x[1], reverse=True)
        sorted_types = sorted(type_counts.items(), key=lambda x: x[1], reverse=True)
        unique_files = sorted(set(files))[:15]

        apps_text = ", ".join(f"{name} ({count})" for name, count in sorted_apps[:6])
        types_text = ", ".join(f"{name} ({count})" for name, count in sorted_types[:8])
        files_text = ", ".join(unique_files) if unique_files else "sin archivos"

        summary = (
            f"Sesion de trabajo entre {start_ts} y {end_ts}. "
            f"Apps principales: {apps_text if apps_text else 'sin apps identificadas'}. "
            f"Eventos: {types_text}. "
            f"Archivos relevantes: {files_text}."
        )

        metadata: dict[str, Any] = {
            "start_ts": start_ts,
            "end_ts": end_ts,
            "event_count": len(events),
            "top_apps": apps_text if apps_text else "unknown_app",
            "top_event_types": types_text,
            "files_json": json.dumps(unique_files),
        }

        return SessionMemory(
            session_id=session_id,
            start_ts=start_ts,
            end_ts=end_ts,
            event_count=len(events),
            summary=summary,
            apps_json=json.dumps([name for name, _ in sorted_apps]),
            files_json=json.dumps(unique_files),
            metadata=metadata,
            max_event_id=events[-1].event_id,
        )

    def _save_session_sqlite(self, session: SessionMemory) -> None:
        self.conn.execute(
            """
            INSERT INTO session_memories
            (session_id, start_ts, end_ts, event_count, summary, apps_json, files_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(session_id) DO UPDATE SET
                start_ts=excluded.start_ts,
                end_ts=excluded.end_ts,
                event_count=excluded.event_count,
                summary=excluded.summary,
                apps_json=excluded.apps_json,
                files_json=excluded.files_json
            """,
            (
                session.session_id,
                session.start_ts,
                session.end_ts,
                session.event_count,
                session.summary,
                session.apps_json,
                session.files_json,
                utc_now_iso(),
            ),
        )
        self.conn.commit()

    def _save_session_vector(self, session: SessionMemory) -> None:
        self.collection.upsert(
            ids=[session.session_id],
            documents=[session.summary],
            metadatas=[session.metadata],
        )

    def run_once(self) -> int:
        last_id = self._get_last_indexed_event_id()
        events = self._fetch_new_events(last_id)
        if not events:
            LOGGER.info("Sin eventos nuevos para indexar.")
            return 0

        sessions_raw = self._split_into_sessions(events)
        sessions = [self._build_session(chunk) for chunk in sessions_raw if chunk]
        if not sessions:
            LOGGER.info("No se generaron sesiones.")
            self._set_last_indexed_event_id(events[-1].event_id)
            return 0

        for session in sessions:
            self._save_session_sqlite(session)
            self._save_session_vector(session)

        self._set_last_indexed_event_id(events[-1].event_id)
        LOGGER.info(
            "Indexacion completada. Eventos: %s | Sesiones: %s | Ultimo id: %s",
            len(events),
            len(sessions),
            events[-1].event_id,
        )
        return len(sessions)

    def run_forever(self, interval_seconds: int = 600) -> None:
        LOGGER.info("Indexador semantico activo cada %s segundos.", interval_seconds)
        while True:
            self.run_once()
            time.sleep(interval_seconds)

    def close(self) -> None:
        self.conn.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fase 2 - Indexador de sesiones semanticas (events.db -> ChromaDB)."
    )
    parser.add_argument("--db-path", default="events.db")
    parser.add_argument("--chroma-path", default="chroma_db")
    parser.add_argument("--collection", default="viernes_sessions")
    parser.add_argument("--model", default="all-MiniLM-L6-v2")
    parser.add_argument("--interval-seconds", type=int, default=600)
    parser.add_argument("--once", action="store_true")
    return parser.parse_args()


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    args = parse_args()
    indexer = SemanticMemoryIndexer(
        db_path=args.db_path,
        chroma_path=args.chroma_path,
        collection_name=args.collection,
        embedding_model=args.model,
    )
    try:
        if args.once:
            indexer.run_once()
        else:
            indexer.run_forever(interval_seconds=args.interval_seconds)
    finally:
        indexer.close()


if __name__ == "__main__":
    main()

