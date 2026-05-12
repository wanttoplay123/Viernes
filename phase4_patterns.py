from __future__ import annotations

import argparse
import json
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ollama_client import generate_ollama
from plyer import notification


PATTERN_TYPES = [
    "startup_routine",
    "organization",
    "communication",
    "coding_workflow",
    "research_workflow",
    "other",
]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def slugify(value: str, max_len: int = 60) -> str:
    lowered = value.lower().strip()
    lowered = re.sub(r"[^a-z0-9]+", "-", lowered)
    lowered = re.sub(r"-{2,}", "-", lowered).strip("-")
    return lowered[:max_len] if lowered else "pattern"


@dataclass
class EventToken:
    event_id: int
    timestamp: str
    token: str


@dataclass
class PatternCandidate:
    sequence: tuple[str, ...]
    occurrences: int
    first_event_id: int
    last_event_id: int
    first_timestamp: str
    last_timestamp: str


def ensure_tables(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS automation_patterns (
            pattern_id TEXT PRIMARY KEY,
            sequence_json TEXT NOT NULL,
            occurrences INTEGER NOT NULL,
            first_event_id INTEGER NOT NULL,
            last_event_id INTEGER NOT NULL,
            first_timestamp TEXT NOT NULL,
            last_timestamp TEXT NOT NULL,
            classification_type TEXT NOT NULL,
            classification_summary TEXT NOT NULL,
            automation_goal TEXT NOT NULL,
            status TEXT NOT NULL,
            recipe_path TEXT,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS automation_feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pattern_id TEXT NOT NULL,
            feedback_status TEXT NOT NULL,
            notes TEXT,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.commit()


def fetch_event_tokens(conn: sqlite3.Connection, limit: int = 5000) -> list[EventToken]:
    rows = conn.execute(
        """
        SELECT id, timestamp, app_name, event_type
        FROM events
        ORDER BY id DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()

    ordered = list(reversed(rows))
    tokens: list[EventToken] = []
    for row in ordered:
        app_name = row["app_name"] if row["app_name"] else "unknown_app"
        event_type = row["event_type"]
        token = f"{app_name}|{event_type}"
        tokens.append(
            EventToken(
                event_id=int(row["id"]),
                timestamp=str(row["timestamp"]),
                token=token,
            )
        )
    return tokens


def detect_frequent_sequences(
    events: list[EventToken],
    min_sequence_len: int = 3,
    max_sequence_len: int = 5,
    min_occurrences: int = 3,
) -> list[PatternCandidate]:
    if len(events) < min_sequence_len:
        return []

    sequence_hits: dict[tuple[str, ...], list[int]] = {}
    token_list = [item.token for item in events]

    for length in range(min_sequence_len, max_sequence_len + 1):
        for start in range(0, len(token_list) - length + 1):
            seq = tuple(token_list[start : start + length])
            sequence_hits.setdefault(seq, []).append(start)

    candidates: list[PatternCandidate] = []
    for sequence, starts in sequence_hits.items():
        if len(starts) < min_occurrences:
            continue
        first_idx = starts[0]
        last_idx = starts[-1] + len(sequence) - 1
        first_event = events[first_idx]
        last_event = events[last_idx]
        candidates.append(
            PatternCandidate(
                sequence=sequence,
                occurrences=len(starts),
                first_event_id=first_event.event_id,
                last_event_id=last_event.event_id,
                first_timestamp=first_event.timestamp,
                last_timestamp=last_event.timestamp,
            )
        )

    candidates.sort(key=lambda item: (item.occurrences, len(item.sequence)), reverse=True)
    return candidates


def _extract_json_block(raw_text: str) -> str:
    start = raw_text.find("{")
    end = raw_text.rfind("}")
    if start < 0 or end < 0 or end <= start:
        raise ValueError("El modelo no devolvio un JSON valido para clasificacion.")
    return raw_text[start : end + 1]


def classify_pattern(candidate: PatternCandidate, model: str) -> dict[str, str]:
    sequence_text = " -> ".join(candidate.sequence)
    prompt = (
        "Clasifica este patron de actividad para automatizacion de escritorio.\n"
        f"Tipos permitidos: {', '.join(PATTERN_TYPES)}.\n"
        "Devuelve SOLO JSON con:\n"
        '{"type":"...","summary":"...","automation_goal":"..."}\n\n'
        f"Patron: {sequence_text}\n"
        f"Ocurrencias: {candidate.occurrences}\n"
        f"Rango temporal: {candidate.first_timestamp} -> {candidate.last_timestamp}\n"
        "JSON:"
    )

    raw = generate_ollama(model=model, prompt=prompt, timeout_seconds=90)
    parsed = json.loads(_extract_json_block(raw))
    if not isinstance(parsed, dict):
        raise ValueError("Clasificacion invalida: no es objeto JSON.")

    pattern_type = str(parsed.get("type", "other"))
    if pattern_type not in PATTERN_TYPES:
        raise ValueError(f"Clasificacion fuera de tipos permitidos: {pattern_type}")

    summary = str(parsed.get("summary", "")).strip()
    goal = str(parsed.get("automation_goal", "")).strip()
    if not summary or not goal:
        raise ValueError("Clasificacion invalida: faltan summary/automation_goal.")

    return {"type": pattern_type, "summary": summary, "automation_goal": goal}


def notify_candidate(pattern_id: str, summary: str, occurrences: int) -> None:
    notification.notify(
        title="Viernes detecto una rutina repetida",
        message=f"{summary} ({occurrences} repeticiones). Usa --approve-pattern {pattern_id}",
        app_name="Viernes",
        timeout=10,
    )


def build_recipe_code(candidate: PatternCandidate, classification: dict[str, str], model: str) -> str:
    sequence_text = " -> ".join(candidate.sequence)
    prompt = (
        "Genera un script Python ejecutable para automatizar el siguiente patron.\n"
        "Usa funciones claras y comentarios minimos.\n"
        "Devuelve SOLO codigo Python, sin markdown.\n\n"
        f"Tipo: {classification['type']}\n"
        f"Objetivo: {classification['automation_goal']}\n"
        f"Secuencia detectada: {sequence_text}\n"
    )
    code = generate_ollama(model=model, prompt=prompt, timeout_seconds=120)
    return code.strip()


def save_recipe(pattern_id: str, code: str, recipes_dir: Path) -> Path:
    recipes_dir.mkdir(parents=True, exist_ok=True)
    script_path = recipes_dir / f"{pattern_id}.py"
    script_path.write_text(code + "\n", encoding="utf-8")
    return script_path


def upsert_pattern(
    conn: sqlite3.Connection,
    pattern_id: str,
    candidate: PatternCandidate,
    classification: dict[str, str],
    status: str,
    recipe_path: str | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO automation_patterns (
            pattern_id, sequence_json, occurrences, first_event_id, last_event_id,
            first_timestamp, last_timestamp, classification_type, classification_summary,
            automation_goal, status, recipe_path, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(pattern_id) DO UPDATE SET
            occurrences=excluded.occurrences,
            last_event_id=excluded.last_event_id,
            last_timestamp=excluded.last_timestamp,
            classification_type=excluded.classification_type,
            classification_summary=excluded.classification_summary,
            automation_goal=excluded.automation_goal,
            status=excluded.status,
            recipe_path=excluded.recipe_path
        """,
        (
            pattern_id,
            json.dumps(candidate.sequence, ensure_ascii=False),
            candidate.occurrences,
            candidate.first_event_id,
            candidate.last_event_id,
            candidate.first_timestamp,
            candidate.last_timestamp,
            classification["type"],
            classification["summary"],
            classification["automation_goal"],
            status,
            recipe_path,
            utc_now_iso(),
        ),
    )
    conn.commit()


def add_feedback(
    conn: sqlite3.Connection,
    pattern_id: str,
    feedback_status: str,
    notes: str | None,
) -> None:
    allowed = {"approved", "rejected", "corrected"}
    if feedback_status not in allowed:
        raise ValueError(f"feedback_status invalido: {feedback_status}")

    conn.execute(
        """
        INSERT INTO automation_feedback (pattern_id, feedback_status, notes, created_at)
        VALUES (?, ?, ?, ?)
        """,
        (pattern_id, feedback_status, notes, utc_now_iso()),
    )
    conn.execute(
        """
        UPDATE automation_patterns
        SET status = ?
        WHERE pattern_id = ?
        """,
        (feedback_status, pattern_id),
    )
    conn.commit()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fase 4 - Deteccion de patrones, clasificacion y recetas automatizadas."
    )
    parser.add_argument("--db-path", default="events.db")
    parser.add_argument("--llm-model", default="llama3.2:3b")
    parser.add_argument("--min-occurrences", type=int, default=3)
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--notify", action="store_true")
    parser.add_argument("--auto-approve", action="store_true")
    parser.add_argument("--recipes-dir", default="recipes")
    parser.add_argument("--approve-pattern", default=None)
    parser.add_argument("--feedback-status", default=None)
    parser.add_argument("--feedback-notes", default=None)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    conn = sqlite3.connect(args.db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    ensure_tables(conn)

    if args.approve_pattern and args.feedback_status:
        add_feedback(
            conn,
            pattern_id=args.approve_pattern,
            feedback_status=args.feedback_status,
            notes=args.feedback_notes,
        )
        print(
            json.dumps(
                {
                    "status": "ok",
                    "message": "Feedback registrado",
                    "pattern_id": args.approve_pattern,
                    "feedback_status": args.feedback_status,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return

    events = fetch_event_tokens(conn)
    candidates = detect_frequent_sequences(
        events=events,
        min_sequence_len=3,
        max_sequence_len=5,
        min_occurrences=args.min_occurrences,
    )[: args.top_k]

    output: list[dict[str, Any]] = []
    for candidate in candidates:
        classification = classify_pattern(candidate, model=args.llm_model)
        fingerprint = (
            f"{candidate.first_event_id}-{candidate.last_event_id}-{candidate.occurrences}"
        )
        pattern_id = slugify(f"{classification['type']}-{fingerprint}")
        status = "pending"
        recipe_path: str | None = None

        if args.auto_approve:
            recipe_code = build_recipe_code(
                candidate=candidate,
                classification=classification,
                model=args.llm_model,
            )
            saved = save_recipe(
                pattern_id=pattern_id,
                code=recipe_code,
                recipes_dir=Path(args.recipes_dir),
            )
            recipe_path = str(saved)
            status = "approved"

        upsert_pattern(
            conn=conn,
            pattern_id=pattern_id,
            candidate=candidate,
            classification=classification,
            status=status,
            recipe_path=recipe_path,
        )

        if args.auto_approve:
            add_feedback(
                conn=conn,
                pattern_id=pattern_id,
                feedback_status="approved",
                notes="Aprobado automatico via --auto-approve",
            )

        if args.notify:
            notify_candidate(
                pattern_id=pattern_id,
                summary=classification["summary"],
                occurrences=candidate.occurrences,
            )

        output.append(
            {
                "pattern_id": pattern_id,
                "occurrences": candidate.occurrences,
                "sequence": list(candidate.sequence),
                "classification": classification,
                "status": status,
                "recipe_path": recipe_path,
            }
        )

    print(json.dumps({"patterns": output}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

