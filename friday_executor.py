from __future__ import annotations

import argparse
import json
import re
from typing import Any

from action_bridge import plan_action_from_text
from os_controller import OSController
from permissions import load_permissions
from semantic_query import load_collection, search_sessions


def build_memory_context(matches: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for idx, item in enumerate(matches, start=1):
        metadata = item.get("metadata") or {}
        start_ts = metadata.get("start_ts", "N/A")
        end_ts = metadata.get("end_ts", "N/A")
        top_apps = metadata.get("top_apps", "N/A")
        lines.append(
            (
                f"[Sesion {idx}] id={item['id']} {start_ts}->{end_ts}\n"
                f"Apps: {top_apps}\n"
                f"Resumen: {item.get('document', '')}"
            )
        )
    return "\n\n".join(lines) if lines else "Sin sesiones en memoria."


def _extract_files_from_match(item: dict[str, Any]) -> list[str]:
    metadata = item.get("metadata") or {}
    files_json = metadata.get("files_json")
    files: list[str] = []

    if isinstance(files_json, str) and files_json.strip():
        parsed = json.loads(files_json)
        if isinstance(parsed, list):
            for value in parsed:
                if isinstance(value, str) and value:
                    files.append(value)

    if files:
        return files

    text = item.get("document", "")
    if not isinstance(text, str):
        return files

    for candidate in re.findall(r"[A-Za-z]:\\[^,\n]+", text):
        cleaned = candidate.strip().rstrip(".")
        files.append(cleaned)
    return files


def extract_context_files(matches: list[dict[str, Any]], limit: int) -> list[str]:
    dedup: list[str] = []
    seen: set[str] = set()
    for match in matches:
        for file_path in _extract_files_from_match(match):
            key = file_path.lower()
            if key in seen:
                continue
            seen.add(key)
            dedup.append(file_path)
            if len(dedup) >= limit:
                return dedup
    return dedup


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fase 3 - Ejecuta acciones del OS desde lenguaje natural usando memoria."
    )
    parser.add_argument("instruction", help="Instruccion en lenguaje natural")
    parser.add_argument("--chroma-path", default="chroma_db")
    parser.add_argument("--collection", default="viernes_sessions")
    parser.add_argument("--embedding-model", default="all-MiniLM-L6-v2")
    parser.add_argument("--llm-model", default="llama3.2:3b")
    parser.add_argument("--n-results", type=int, default=5)
    parser.add_argument("--permissions", default="permissions.json")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    collection = load_collection(
        chroma_path=args.chroma_path,
        collection_name=args.collection,
        embedding_model=args.embedding_model,
    )
    matches = search_sessions(
        collection=collection,
        query_text=args.instruction,
        n_results=args.n_results,
    )
    context = build_memory_context(matches)
    plan = plan_action_from_text(
        user_instruction=args.instruction,
        memory_context=context,
        model=args.llm_model,
    )

    controller = OSController(load_permissions(args.permissions))
    action = str(plan["action"])
    payload = plan["args"]
    if not isinstance(payload, dict):
        raise ValueError("El plan devuelto no contiene args validos.")

    if action == "open_context_files":
        count = int(payload.get("count", 3))
        files = extract_context_files(matches, limit=count)
        if not files:
            raise RuntimeError(
                "No se encontraron rutas de archivo en las sesiones recuperadas."
            )
        results: list[dict[str, str]] = []
        for file_path in files:
            results.append(controller.open_file(path=file_path))
        print(json.dumps({"plan": plan, "results": results}, indent=2, ensure_ascii=False))
        return

    result = controller.execute_action(action=action, args=payload)
    print(json.dumps({"plan": plan, "result": result}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()

