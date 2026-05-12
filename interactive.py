from __future__ import annotations

import logging
import sqlite3
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Optional

from os_controller import OSController
from permissions import load_permissions
from ollama_client import generate_ollama

LOGGER = logging.getLogger("viernes.interactive")

_controller = OSController(permissions=load_permissions())
_whisper_model = None
_tts_engine = None
_icon = None


def load_tts():
    global _tts_engine
    if _tts_engine is None:
        try:
            import pyttsx3
            _tts_engine = pyttsx3.init()
            _tts_engine.setProperty("rate", 150)
            LOGGER.info("TTS listo")
        except Exception as e:
            LOGGER.warning(f"TTS no disponible: {e}")


def speak(text: str):
    load_tts()
    if _tts_engine:
        try:
            _tts_engine.say(text)
            _tts_engine.runAndWait()
        except Exception as e:
            LOGGER.error(f"TTS error: {e}")


def listen_voice() -> Optional[str]:
    global _whisper_model
    if _whisper_model is None:
        LOGGER.info("Cargando Whisper (primera vez)...")
        try:
            import whisper
            _whisper_model = whisper.load_model("small")
        except Exception as e:
            LOGGER.error(f"Whisper no disponible: {e}")
            return None

    try:
        import pyaudio
        import numpy as np
        audio = pyaudio.PyAudio()
        stream = audio.open(format=pyaudio.paInt16, channels=1, rate=16000, input=True, frames_per_buffer=1024)
        LOGGER.info("Escuchando... (3 segundos)")
        frames = []
        for _ in range(int(16000 / 1024 * 3)):
            data = stream.read(1024)
            frames.append(data)
        stream.stop_stream()
        stream.close()
        audio.terminate()
        audio_np = np.frombuffer(b"".join(frames), np.int16).astype(np.float32) / 32768.0
        result = _whisper_model.transcribe(audio_np, language="es")
        return result["text"].strip() or None
    except Exception as e:
        LOGGER.error(f"Error escuchando: {e}")
        return None


COMMANDS = {
    "notepad": "notepad",
    "bloc de notas": "notepad",
    "bloque de notas": "notepad",
    "whatsapp": "WhatsApp",
    "chrome": "chrome",
    "navegador": "chrome",
    "explorador": "explorer",
    "explorer": "explorer",
    "vscode": "code",
    "code": "code",
    "visual studio": "code",
    "discord": "discord",
    "telegram": "telegram",
}


def parse_command(text: str) -> Optional[dict]:
    t = text.lower().strip()

    if t in ["hola", "hi", "hello", "buenas", "que tal"]:
        return {"type": "response", "text": "Hola! Estoy listo. Que necesitas?"}

    if t in ["salir", "exit", "quit", "chao", "adios"]:
        return {"type": "exit"}

    if "abrir" in t or "abre" in t or "open" in t or "abrime" in t:
        parts = t.replace("abrime", "abrir").replace("abre", "abrir").replace("open", "abrir").split("abrir")
        if len(parts) > 1:
            app_name = parts[-1].strip().strip(".").strip("!")
            if "facebook" in app_name:
                return {"type": "url", "url": "https://facebook.com", "msg": "Abriendo Facebook..."}
            if "youtube" in app_name:
                return {"type": "url", "url": "https://youtube.com", "msg": "Abriendo YouTube..."}
            if "google" in app_name:
                return {"type": "url", "url": "https://google.com", "msg": "Abriendo Google..."}
            for key, val in COMMANDS.items():
                if key in app_name:
                    return {"type": "app", "app": val, "msg": f"Abriendo {val}..."}
            return {"type": "app", "app": app_name, "msg": f"Abriendo {app_name}..."}

    if "facebook" in t:
        return {"type": "url", "url": "https://facebook.com", "msg": "Abriendo Facebook..."}
    if "youtube" in t:
        return {"type": "url", "url": "https://youtube.com", "msg": "Abriendo YouTube..."}
    if "google" in t and "busca" not in t and "buscar" not in t:
        return {"type": "url", "url": "https://google.com", "msg": "Abriendo Google..."}

    if t.startswith("busca ") or t.startswith("buscar ") or t.startswith("googlea ") or t.startswith("google "):
        query = t.replace("busca ", "").replace("buscar ", "").replace("googlea ", "").replace("google ", "")
        return {"type": "search", "query": query}

    if "que" in t and ("haces" in t or "haciendo" in t or "estas" in t or "hacias" in t or "hacia" in t):
        return {"type": "activity"}

    if "que" in t and ("recuerdas" in t or "sabes" in t or "paso" in t):
        return {"type": "memory"}

    if t.startswith("escribe ") or t.startswith("type ") or t.startswith("teclea "):
        text_to_type = t.replace("escribe ", "").replace("type ", "").replace("teclea ", "")
        return {"type": "type_text", "text": text_to_type}

    if "click" in t or "clica" in t or "haz clic" in t:
        return {"type": "response", "text": "Dime las coordenadas (x,y) o usa el mouse manualmente"}

    if "screenshot" in t or "captura" in t or "pantallazo" in t:
        path = f"C:\\Users\\USUARIO\\Pictures\\captura_{int(time.time())}.png"
        return {"type": "screenshot", "path": path}

    return None


def get_recent_activity() -> str:
    try:
        conn = sqlite3.connect("events.db")
        cursor = conn.execute("SELECT DISTINCT app_name FROM events WHERE app_name IS NOT NULL AND app_name != '' ORDER BY timestamp DESC LIMIT 8")
        rows = cursor.fetchall()
        conn.close()
        apps = [r[0] for r in rows if r[0] and r[0] != "unknown_app"]
        if apps:
            return f"Actividad reciente: {', '.join(apps)}"
        return "No hay actividad registrada aun. Sigue usando el PC y Viernes va aprendiendo."
    except Exception as e:
        return f"No pude leer el historial: {e}"


def get_memory_context() -> str:
    try:
        conn = sqlite3.connect("events.db")
        cursor = conn.execute("SELECT app_name, event_type, value, timestamp FROM events ORDER BY timestamp DESC LIMIT 5")
        rows = cursor.fetchall()
        conn.close()
        if rows:
            lines = []
            for r in rows:
                app, etype, val, ts = r
                val_short = (val[:60] + "...") if val and len(val) > 60 else (val or "")
                lines.append(f"[{ts}] {app} | {etype} | {val_short}")
            return "\n".join(lines)
        return "Sin historial"
    except Exception as e:
        return f"Error: {e}"


def execute_parsed(cmd: dict) -> str:
    if cmd["type"] == "response":
        return cmd["text"]

    if cmd["type"] == "url":
        try:
            _controller.open_url(cmd["url"])
            return cmd.get("msg", f"Abriendo URL...")
        except Exception as e:
            return f"Error abriendo URL: {e}"

    if cmd["type"] == "app":
        try:
            result = _controller.execute_action("open_app", {"app": cmd["app"]})
            return cmd.get("msg", f"Abriendo {cmd['app']}...")
        except PermissionError:
            return f"No tengo permisos para abrir '{cmd['app']}'. Agregalo a permissions.json"
        except Exception as e:
            return f"Error abriendo {cmd['app']}: {e}"

    if cmd["type"] == "search":
        try:
            _controller.open_url(f"https://google.com/search?q={cmd['query']}")
            return f"Buscando: {cmd['query']}"
        except Exception as e:
            return f"Error buscando: {e}"

    if cmd["type"] == "activity":
        return get_recent_activity()

    if cmd["type"] == "memory":
        context = get_memory_context()
        prompt = (
            "Responde en 1-2 lineas sobre esta actividad:\n"
            f"{context}\n\n"
            "Usuario pregunta que recuerdas."
        )
        try:
            return generate_ollama(model="llama3.2:3b", prompt=prompt, timeout_seconds=30)
        except Exception as e:
            return get_recent_activity()

    if cmd["type"] == "type_text":
        try:
            _controller.execute_action("type_text", {"text": cmd["text"]})
            return f"Escribiendo: {cmd['text']}"
        except Exception as e:
            return f"Error escribiendo: {e}"

    if cmd["type"] == "screenshot":
        try:
            _controller.execute_action("screenshot", {"path": cmd["path"]})
            return f"Captura guardada en {cmd['path']}"
        except Exception as e:
            return f"Error en captura: {e}"

    return "No entendi el comando."


def process_command(user_input: str) -> str:
    if not user_input or not user_input.strip():
        return "Di algo!"

    cmd = parse_command(user_input)
    if cmd:
        if cmd["type"] == "exit":
            return "__EXIT__"
        return execute_parsed(cmd)

    prompt = (
        "Eres Viernes, asistente local. La consulta NO coincide con comandos rapidos.\n"
        "Responde en UNA linea, breve.\n"
        f"Usuario: {user_input}\n\n"
        "Si quiere ejecutar una accion, responde SOLO con:\n"
        "ACCION: <abrir|buscar|escribir> <detalle>\n"
        "Si no, responde normal."
    )
    try:
        return generate_ollama(model="llama3.2:3b", prompt=prompt, timeout_seconds=30)
    except Exception as e:
        return f"Error con la IA: {e}. Intenta con 'abrir notepad' o 'que haces'."


def setup_systray():
    global _icon
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (64, 64), color=(79, 142, 247))
    draw = ImageDraw.Draw(img)
    draw.rectangle([16, 20, 48, 44], fill="white")
    draw.rectangle([20, 24, 44, 40], fill=(79, 142, 247))

    def on_status(icon, item):
        print(get_recent_activity())

    def on_voice(icon, item):
        print("[VOZ] Habla ahora...")
        text = listen_voice()
        if text:
            print(f"Escuche: {text}")
            result = process_command(text)
            print(f"Viernes: {result}")
            speak(result)
        else:
            print("No escuche nada")

    def on_quit(icon, item):
        if _icon:
            _icon.stop()
        sys.exit(0)

    menu = pystray.Menu(
        pystray.MenuItem("Estado", on_status),
        pystray.MenuItem("VOZ", on_voice),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Salir", on_quit),
    )

    try:
        _icon = pystray.Icon("viernes", img, "Viernes AI", menu)
        threading.Thread(target=_icon.run, daemon=True).start()
        LOGGER.info("Systray iniciado")
    except Exception as e:
        LOGGER.warning(f"Systray no disponible: {e}")


def test_mode():
    tests = [
        ("hola", "Saludo"),
        ("abrir notepad", "Abrir app"),
        ("abrir whatsapp", "Abrir app"),
        ("abrir facebook", "URL"),
        ("abrir youtube", "URL"),
        ("busca python", "Buscar"),
        ("que haces", "Actividad"),
        ("que recuerdas", "Memoria"),
    ]
    print("Probando comandos...")
    for cmd, desc in tests:
        result = process_command(cmd)
        print(f"  [{desc}] {cmd} -> {result}")
    print("Listo!")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Viernes AI")
    parser.add_argument("--cmd", type=str, help="Comando directo")
    parser.add_argument("--voice", action="store_true", help="Modo voz")
    parser.add_argument("--test", action="store_true", help="Test rapido")
    parser.add_argument("--systray", action="store_true", help="Solo systray")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")

    if args.test:
        test_mode()
        return

    if args.cmd:
        result = process_command(args.cmd)
        print(f"Viernes: {result}")
        return

    if args.voice:
        print("[VOZ] Habla ahora...")
        text = listen_voice()
        if text:
            print(f"Escuche: {text}")
            result = process_command(text)
            print(f"Viernes: {result}")
            speak(result)
        else:
            print("No escuche nada")
        return

    if args.systray:
        setup_systray()
        print("Systray iniciado. Icono en la bandeja del sistema.")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass
        return

    setup_systray()
    print("\n" + "="*50)
    print("  VIERNES AI - Listo")
    print("  Comandos rapidos sin IA (instantaneo):")
    print("    abrir notepad / whatsapp / facebook")
    print("    busca python")
    print("    que haces")
    print("    escribe hola mundo")
    print("    screenshot")
    print("  Comandos con IA (tarda ~10-30s):")
    print("    cualquier otra cosa")
    print("="*50 + "\n")

    while True:
        try:
            inp = input("> ").strip()
            if not inp:
                continue
            if inp.lower() in ["salir", "exit", "quit"]:
                break
            result = process_command(inp)
            if result == "__EXIT__":
                break
            print(f"Viernes: {result}")
        except (KeyboardInterrupt, EOFError):
            break
        except Exception as e:
            print(f"Error: {e}")


if __name__ == "__main__":
    main()