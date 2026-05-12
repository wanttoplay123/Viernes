from __future__ import annotations

import json

from ollama_client import generate_ollama


ACTION_SPEC = """
Acciones permitidas:
1) open_file {"path":"C:\\\\...","app":"opcional"}
2) open_app {"app":"notepad|code|chrome|msedge|explorer"}
3) copy_file {"src":"C:\\\\...","dst":"C:\\\\..."}
4) move_file {"src":"C:\\\\...","dst":"C:\\\\..."}
5) delete_file {"path":"C:\\\\..."}
6) open_url {"url":"https://..."}
7) extract_page_text {"url":"https://...","selector":"body"}
8) send_email {"to":"correo@dominio.com","subject":"...","body":"..."}
9) mouse_click {"x":120,"y":340}
10) type_text {"text":"...","interval":0.02}
11) screenshot {"path":"C:\\\\...\\\\captura.png"}
12) open_context_files {"count":3}

Reglas:
- Devuelve SOLO JSON valido, sin markdown ni texto extra.
- Formato exacto:
{"action":"<accion>","args":{...},"reason":"<frase corta>"}
- No inventes rutas ni correos fuera del contexto.
"""


def _extract_json_block(raw_text: str) -> str:
    start = raw_text.find("{")
    end = raw_text.rfind("}")
    if start < 0 or end < 0 or end <= start:
        raise ValueError("El modelo no devolvio un bloque JSON valido.")
    return raw_text[start : end + 1]


def plan_action_from_text(
    user_instruction: str,
    memory_context: str,
    model: str = "llama3.2:3b",
) -> dict[str, object]:
    prompt = (
        "Eres el puente texto->JSON->accion de Viernes.\n"
        "Debes elegir UNA accion segura basada en la instruccion.\n\n"
        f"{ACTION_SPEC}\n\n"
        f"Instruccion del usuario:\n{user_instruction}\n\n"
        f"Contexto recuperado de memoria:\n{memory_context}\n\n"
        "JSON:"
    )
    raw = generate_ollama(model=model, prompt=prompt, timeout_seconds=90)
    json_text = _extract_json_block(raw)

    try:
        parsed = json.loads(json_text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"JSON invalido retornado por el modelo: {exc}") from exc

    if not isinstance(parsed, dict):
        raise ValueError("La respuesta JSON no es un objeto.")
    if not isinstance(parsed.get("action"), str):
        raise ValueError("El campo 'action' debe ser string.")
    if not isinstance(parsed.get("args"), dict):
        raise ValueError("El campo 'args' debe ser objeto.")
    return parsed

