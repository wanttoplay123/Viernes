from __future__ import annotations

import json
import time
import urllib.error
import urllib.request

OLLAMA_URL = "http://localhost:11434/api/generate"
DEFAULT_MODEL = "llama3.2:1b"
_WARMED_UP = False


def generate_ollama(
    model: str,
    prompt: str,
    timeout_seconds: int = 90,
    keep_alive: str = "30m"
) -> str:
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "keep_alive": keep_alive,
    }
    data_bytes = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url=OLLAMA_URL,
        data=data_bytes,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        raise RuntimeError(
            "No se pudo conectar a Ollama en localhost:11434. Verifica que este corriendo."
        ) from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError("Respuesta JSON invalida desde Ollama.") from exc

    text = data.get("response")
    if not isinstance(text, str) or not text.strip():
        raise RuntimeError("Ollama no devolvio texto util.")
    return text.strip()


def warmup_model(model: str = DEFAULT_MODEL, timeout: int = 120) -> float:
    global _WARMED_UP
    if _WARMED_UP:
        return 0.0

    start = time.time()
    try:
        payload = {
            "model": model,
            "prompt": "responde solo: ok",
            "stream": False,
            "keep_alive": "60m",
        }
        data_bytes = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            url=OLLAMA_URL,
            data=data_bytes,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=timeout) as response:
            json.loads(response.read().decode("utf-8"))

        elapsed = time.time() - start
        _WARMED_UP = True
        return elapsed

    except Exception as exc:
        raise RuntimeError(
            f"No se pudo cargar el modelo {model} en Ollama: {exc}"
        ) from exc


def is_running() -> bool:
    try:
        request = urllib.request.Request(
            url=OLLAMA_URL,
            data=b'{}',
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=3):
            return True
    except Exception:
        return False
