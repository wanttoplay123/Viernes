from __future__ import annotations

import logging
import sqlite3
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from queue import Empty, Full, Queue
from typing import Optional

import pyperclip
from pynput import keyboard, mouse
from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

try:
    import pygetwindow as gw
except ImportError:  # pragma: no cover - handled by runtime dependency setup
    gw = None


LOGGER = logging.getLogger("viernes.activity_logger")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def compact_text(value: Optional[str], max_len: int = 220) -> Optional[str]:
    if value is None:
        return None
    text = value.replace("\r", " ").replace("\n", "\\n").strip()
    if not text:
        return None
    return text if len(text) <= max_len else f"{text[:max_len]}..."


def key_to_string(key: keyboard.KeyCode | keyboard.Key) -> str:
    if isinstance(key, keyboard.KeyCode):
        return key.char if key.char is not None else str(key)
    return str(key)


@dataclass
class EventRecord:
    timestamp: str
    app_name: Optional[str]
    event_type: str
    value: Optional[str] = None
    file_path: Optional[str] = None
    duration: Optional[float] = None


class SQLiteEventStore:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self.conn.execute("PRAGMA journal_mode=WAL;")
        self.conn.execute("PRAGMA synchronous=NORMAL;")
        self._create_schema()

    def _create_schema(self) -> None:
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                app_name TEXT,
                event_type TEXT NOT NULL,
                value TEXT,
                file_path TEXT,
                duration REAL
            )
            """
        )
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS metadata (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_events_timestamp ON events(timestamp)"
        )
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_events_type ON events(event_type)"
        )
        self.conn.commit()

    def insert_event(self, record: EventRecord) -> None:
        self.conn.execute(
            """
            INSERT INTO events (timestamp, app_name, event_type, value, file_path, duration)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                record.timestamp,
                record.app_name,
                record.event_type,
                record.value,
                record.file_path,
                record.duration,
            ),
        )
        self.conn.commit()

    def maybe_vacuum(self, min_days: int = 7) -> None:
        now_ts = time.time()
        row = self.conn.execute(
            "SELECT value FROM metadata WHERE key = 'last_vacuum_unix'"
        ).fetchone()
        last_vacuum = float(row[0]) if row else 0.0
        if now_ts - last_vacuum < (min_days * 24 * 60 * 60):
            return

        self.conn.execute("VACUUM")
        self.conn.execute(
            """
            INSERT INTO metadata (key, value)
            VALUES ('last_vacuum_unix', ?)
            ON CONFLICT(key) DO UPDATE SET value=excluded.value
            """,
            (str(now_ts),),
        )
        self.conn.commit()
        LOGGER.info("SQLite VACUUM ejecutado.")

    def close(self) -> None:
        self.conn.close()


class FileActivityHandler(FileSystemEventHandler):
    def __init__(self, logger_ref: "ActivityLogger") -> None:
        self.logger_ref = logger_ref

    def _handle(self, event: FileSystemEvent, event_type: str) -> None:
        if event.is_directory:
            return
        path = getattr(event, "src_path", None)
        self.logger_ref.log_event(
            event_type=event_type,
            value=Path(path).name if path else None,
            file_path=path,
        )

    def on_created(self, event: FileSystemEvent) -> None:
        self._handle(event, "file_created")

    def on_modified(self, event: FileSystemEvent) -> None:
        self._handle(event, "file_modified")

    def on_deleted(self, event: FileSystemEvent) -> None:
        self._handle(event, "file_deleted")

    def on_moved(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            return
        self.logger_ref.log_event(
            event_type="file_moved",
            value=f"{Path(event.src_path).name} -> {Path(event.dest_path).name}",
            file_path=event.dest_path,
        )


class ActivityLogger:
    def __init__(
        self,
        db_path: str = "events.db",
        min_event_interval_ms: int = 500,
        app_poll_seconds: float = 1.5,
        clipboard_poll_seconds: float = 0.6,
    ) -> None:
        self.store = SQLiteEventStore(Path(db_path))
        self.event_queue: Queue[EventRecord] = Queue(maxsize=5000)
        self.stop_event = threading.Event()
        self.min_event_interval_s = min_event_interval_ms / 1000.0
        self.app_poll_seconds = app_poll_seconds
        self.clipboard_poll_seconds = clipboard_poll_seconds

        self._last_event_mono = 0.0
        self._rate_lock = threading.Lock()
        self._last_vacuum_check_mono = 0.0

        self._keyboard_listener: Optional[keyboard.Listener] = None
        self._mouse_listener: Optional[mouse.Listener] = None
        self._observer: Optional[Observer] = None
        self._threads: list[threading.Thread] = []

        self._current_app: Optional[str] = None
        self._current_app_started_mono: Optional[float] = None
        self._last_clipboard: Optional[str] = None

    def _active_app_name(self) -> str:
        if gw is None:
            return "unknown_app"
        try:
            window = gw.getActiveWindow()
        except Exception as exc:
            LOGGER.warning("No se pudo leer la ventana activa: %s", exc)
            return "unknown_app"
        if not window or not window.title:
            return "unknown_app"
        return compact_text(window.title, 140) or "unknown_app"

    def _rate_limit_ok(self) -> bool:
        now = time.monotonic()
        with self._rate_lock:
            if now - self._last_event_mono < self.min_event_interval_s:
                return False
            self._last_event_mono = now
            return True

    def log_event(
        self,
        event_type: str,
        value: Optional[str] = None,
        file_path: Optional[str] = None,
        duration: Optional[float] = None,
        bypass_rate_limit: bool = False,
    ) -> None:
        if not bypass_rate_limit and not self._rate_limit_ok():
            return

        app_name = self._active_app_name()
        record = EventRecord(
            timestamp=utc_now_iso(),
            app_name=app_name,
            event_type=event_type,
            value=compact_text(value),
            file_path=file_path,
            duration=duration,
        )
        try:
            self.event_queue.put_nowait(record)
        except Full as exc:
            LOGGER.warning("Cola de eventos llena, evento descartado: %s", exc)

    def _writer_loop(self) -> None:
        while not self.stop_event.is_set() or not self.event_queue.empty():
            try:
                record = self.event_queue.get(timeout=0.4)
            except Empty:
                self._periodic_maintenance()
                continue

            try:
                self.store.insert_event(record)
            except sqlite3.Error as exc:
                LOGGER.error("Error guardando evento en SQLite: %s", exc)
            self._periodic_maintenance()

    def _periodic_maintenance(self) -> None:
        now_mono = time.monotonic()
        if now_mono - self._last_vacuum_check_mono < 300:
            return
        self._last_vacuum_check_mono = now_mono
        self.store.maybe_vacuum(min_days=7)

    def _app_tracker_loop(self) -> None:
        while not self.stop_event.is_set():
            app_name = self._active_app_name()
            now_mono = time.monotonic()

            if app_name != self._current_app:
                if self._current_app and self._current_app_started_mono is not None:
                    duration = now_mono - self._current_app_started_mono
                    self.log_event(
                        event_type="app_duration",
                        value=self._current_app,
                        duration=round(duration, 3),
                        bypass_rate_limit=True,
                    )
                self._current_app = app_name
                self._current_app_started_mono = now_mono
                self.log_event(event_type="app_focus", value=app_name)

            self.stop_event.wait(self.app_poll_seconds)

    def _clipboard_loop(self) -> None:
        while not self.stop_event.is_set():
            try:
                copied_text = pyperclip.paste()
            except pyperclip.PyperclipException as exc:
                LOGGER.warning("Clipboard no disponible: %s", exc)
                self.stop_event.wait(self.clipboard_poll_seconds)
                continue
            if copied_text and copied_text != self._last_clipboard:
                self._last_clipboard = copied_text
                self.log_event(event_type="clipboard_copy", value=copied_text)
            self.stop_event.wait(self.clipboard_poll_seconds)

    def _start_file_observer(self) -> None:
        watch_dirs = [
            Path.home() / "Desktop",
            Path.home() / "Documents",
            Path.home() / "Downloads",
        ]
        handler = FileActivityHandler(self)
        observer = Observer()

        watched = 0
        for directory in watch_dirs:
            if directory.exists():
                observer.schedule(handler, str(directory), recursive=True)
                watched += 1

        if watched == 0:
            LOGGER.warning("No se encontraron carpetas para watchdog.")
            return

        observer.start()
        self._observer = observer
        LOGGER.info("watchdog activo en %s carpetas.", watched)

    def _on_key_press(self, key: keyboard.KeyCode | keyboard.Key) -> None:
        self.log_event(event_type="key_press", value=key_to_string(key))

    def _on_click(
        self,
        x: int,
        y: int,
        button: mouse.Button,
        pressed: bool,
    ) -> None:
        if not pressed:
            return
        self.log_event(event_type="mouse_click", value=f"{button}@({x},{y})")

    def _on_scroll(self, x: int, y: int, dx: int, dy: int) -> None:
        self.log_event(
            event_type="mouse_scroll",
            value=f"pos=({x},{y}) delta=({dx},{dy})",
        )

    def start(self) -> None:
        LOGGER.info("Iniciando ActivityLogger.")

        writer = threading.Thread(target=self._writer_loop, daemon=True, name="writer")
        writer.start()
        self._threads.append(writer)

        app_tracker = threading.Thread(
            target=self._app_tracker_loop,
            daemon=True,
            name="app-tracker",
        )
        app_tracker.start()
        self._threads.append(app_tracker)

        clipboard = threading.Thread(
            target=self._clipboard_loop,
            daemon=True,
            name="clipboard",
        )
        clipboard.start()
        self._threads.append(clipboard)

        self._keyboard_listener = keyboard.Listener(on_press=self._on_key_press)
        self._mouse_listener = mouse.Listener(
            on_click=self._on_click,
            on_scroll=self._on_scroll,
        )
        self._keyboard_listener.start()
        self._mouse_listener.start()

        self._start_file_observer()

    def stop(self) -> None:
        LOGGER.info("Deteniendo ActivityLogger.")
        self.stop_event.set()

        if self._keyboard_listener is not None:
            self._keyboard_listener.stop()
        if self._mouse_listener is not None:
            self._mouse_listener.stop()
        if self._observer is not None:
            self._observer.stop()
            self._observer.join(timeout=3)

        if self._current_app and self._current_app_started_mono is not None:
            duration = time.monotonic() - self._current_app_started_mono
            self.log_event(
                event_type="app_duration",
                value=self._current_app,
                duration=round(duration, 3),
                bypass_rate_limit=True,
            )

        for thread in self._threads:
            thread.join(timeout=3)

        self.store.close()
        LOGGER.info("ActivityLogger detenido.")

    def run_forever(self) -> None:
        self.start()
        try:
            while not self.stop_event.is_set():
                time.sleep(0.8)
        except KeyboardInterrupt:
            LOGGER.info("Interrupcion recibida (Ctrl+C).")
        finally:
            self.stop()


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    logger = ActivityLogger(db_path="events.db", min_event_interval_ms=500)
    logger.run_forever()


if __name__ == "__main__":
    main()

