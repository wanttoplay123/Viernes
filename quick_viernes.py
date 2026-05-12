from __future__ import annotations

import sqlite3
import json
from os_controller import OSController
from permissions import load_permissions

_controller = OSController(permissions=load_permissions())


def get_recent_activity():
    try:
        conn = sqlite3.connect("events.db")
        cursor = conn.execute(
            "SELECT app_name, timestamp FROM events ORDER BY timestamp DESC LIMIT 10"
        )
        rows = cursor.fetchall()
        conn.close()
        apps = list(set([r[0] for r in rows if r[0]]))
        return f"Actividad reciente: {', '.join(apps[:5])}" if apps else "Sin actividad reciente"
    except:
        return "Sin historial"


def process_command(user_input: str) -> str:
    user_input = user_input.lower().strip()

    if user_input in ["hola", "hi", "hello", "que tal"]:
        return "Hola! Estoy listo. Qué quieres que haga?"

    if "abrir" in user_input or "abre" in user_input:
        app = user_input.replace("abrir", "").replace("abre", "").strip()
        if "whatsapp" in app:
            app = "whatsapp"
        elif "notepad" in app or "bloc" in app or "bloque" in app:
            app = "notepad"
        elif "navegador" in app or "chrome" in app:
            app = "chrome"
        elif "explorador" in app or "archivos" in app:
            app = "explorer"
        elif "vscode" in app or "code" in app:
            app = "code"
        elif "facebook" in app:
            app = "chrome"
            _controller.open_url("https://facebook.com")
            return "Abriendo Facebook..."
        elif "youtube" in app:
            app = "chrome"
            _controller.open_url("https://youtube.com")
            return "Abriendo YouTube..."

        if app:
            try:
                result = _controller.execute_action("open_app", {"app": app})
                return f"[OK] {result.get('message', 'Hecho')}"
            except Exception as e:
                return f"[ERROR] No pude abrir {app}: {e}"

    if any(p in user_input for p in ["que estas", "que haces", "que hacia", "que estabas", "haces", "haciendo", "hacías"]):
        return get_recent_activity()

    if "busca" in user_input or "google" in user_input:
        query = user_input.replace("busca", "").replace("google", "").strip()
        if query:
            _controller.open_url(f"https://google.com/search?q={query}")
            return f"Buscando: {query}"

    return f"No entendí: {user_input}. Puedo: abrir apps, buscar en Google, mostrar actividad reciente"


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        cmd = " ".join(sys.argv[1:])
        print(f"> {cmd}")
        result = process_command(cmd)
        print(f"Viernes: {result}")
    else:
        print("Viernes Quick Mode")
        print("Ejemplos:")
        print("  python quick_viernes.py abrir notepad")
        print("  python quick_viernes.py abrir whatsapp")
        print("  python quick_viernes.py qué estás haciendo")
        print("  python quick_viernes.py busca python")