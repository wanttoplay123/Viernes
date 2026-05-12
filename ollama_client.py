from __future__ import annotations

import json
import urllib.error
import urllib.request


def generate_ollama(model: str, prompt: str, timeout_seconds: int = 90) -> str:
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
    }
    request = urllib.request.Request(
        url="http://localhost:11434/api/generate",
        data=json.dumps(payload).encode("utf-8"),
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

