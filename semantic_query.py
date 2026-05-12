from __future__ import annotations

import argparse
import logging
from typing import Any

import chromadb
from chromadb.api.models.Collection import Collection
from ollama_client import generate_ollama
from model_cache import get_embedding_function


LOGGER = logging.getLogger("viernes.phase2.semantic_query")


def load_collection(
    chroma_path: str,
    collection_name: str,
    embedding_model: str,
) -> Collection:
    client = chromadb.PersistentClient(path=chroma_path)
    embedding_fn = get_embedding_function(model_name=embedding_model)
    return client.get_or_create_collection(
        name=collection_name,
        embedding_function=embedding_fn,
    )


def search_sessions(
    collection: Collection,
    query_text: str,
    n_results: int,
) -> list[dict[str, Any]]:
    result = collection.query(query_texts=[query_text], n_results=n_results)
    ids = result.get("ids", [[]])[0]
    docs = result.get("documents", [[]])[0]
    metas = result.get("metadatas", [[]])[0]
    distances = result.get("distances", [[]])[0]

    rows: list[dict[str, Any]] = []
    for idx, session_id in enumerate(ids):
        rows.append(
            {
                "id": session_id,
                "document": docs[idx] if idx < len(docs) else "",
                "metadata": metas[idx] if idx < len(metas) else {},
                "distance": distances[idx] if idx < len(distances) else None,
            }
        )
    return rows


def build_prompt(question: str, matches: list[dict[str, Any]]) -> str:
    context_lines: list[str] = []
    for i, item in enumerate(matches, start=1):
        metadata = item["metadata"] or {}
        start_ts = metadata.get("start_ts", "N/A")
        end_ts = metadata.get("end_ts", "N/A")
        context_lines.append(
            (
                f"[Sesion {i}] id={item['id']} | {start_ts} -> {end_ts}\n"
                f"Resumen: {item['document']}"
            )
        )

    context_block = "\n\n".join(context_lines) if context_lines else "Sin contexto."
    return (
        "Eres Viernes, un asistente personal local. Responde en espanol, breve y precisa.\n"
        "Usa solo el contexto dado. Si no hay evidencia suficiente, dilo claramente.\n\n"
        f"Contexto de sesiones:\n{context_block}\n\n"
        f"Pregunta del usuario: {question}\n\n"
        "Respuesta:"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fase 2 - Consulta semantica de sesiones (ChromaDB + Ollama local)."
    )
    parser.add_argument("question", help="Pregunta en lenguaje natural")
    parser.add_argument("--chroma-path", default="chroma_db")
    parser.add_argument("--collection", default="viernes_sessions")
    parser.add_argument("--embedding-model", default="all-MiniLM-L6-v2")
    parser.add_argument("--llm-model", default="llama3.2:3b")
    parser.add_argument("--n-results", type=int, default=5)
    parser.add_argument("--no-llm", action="store_true")
    return parser.parse_args()


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    args = parse_args()

    collection = load_collection(
        chroma_path=args.chroma_path,
        collection_name=args.collection,
        embedding_model=args.embedding_model,
    )
    matches = search_sessions(
        collection=collection,
        query_text=args.question,
        n_results=args.n_results,
    )
    if not matches:
        raise RuntimeError(
            "No hay sesiones indexadas. Ejecuta phase2_indexer.py --once despues de generar eventos."
        )

    print("\n=== Sesiones relevantes ===")
    for i, item in enumerate(matches, start=1):
        metadata = item["metadata"] or {}
        print(
            f"{i}. {item['id']} | {metadata.get('start_ts', 'N/A')} -> {metadata.get('end_ts', 'N/A')}"
        )
        print(f"   {item['document']}")

    if args.no_llm:
        return

    prompt = build_prompt(args.question, matches)
    answer = generate_ollama(model=args.llm_model, prompt=prompt, timeout_seconds=90)
    print("\n=== Respuesta de Viernes ===")
    print(answer)


if __name__ == "__main__":
    main()

