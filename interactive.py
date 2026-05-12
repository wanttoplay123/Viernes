from __future__ import annotations

import logging
import threading
import time
from pathlib import Path
from typing import Optional

from action_bridge import plan_action_from_text
from model_cache import get_embedding_function
from ollama_client import generate_ollama
from os_controller import OSController
from permissions import load_permissions
from semantic_query import load_collection, search_sessions
import pystray
from PIL import Image

LOGGER = logging.getLogger("viernes.interactive")

_model = None
_controller = None
_collection = None
_whisper_model = None
_tts_engine = None
_icon = None


def create_icon():
    width = 64
    height = 64
    from PIL import ImageDraw
    img = Image.new("RGB", (width, height), color=(79, 142, 247))
    draw = ImageDraw.Draw(img)
    draw.rectangle([16, 20, 48, 44], fill="white")
    draw.rectangle([20, 24, 44, 40], fill=(79, 142, 247))
    return img


def setup_systray():
    global _icon

    def on_status(icon, item):
        print("📊 Estado: Todos los módulos activos")

    def on_voice(icon, item):
        print("\n🎤 Modo voz activado...")
        text = listen_voice()
        if text:
            print(f"Escuché: {text}")
            response = process_command(text)
            print(f"Viernes: {response}")
            speak(response)
        else:
            print("No detecté nada")

    def on_quit(icon, item):
        print("\n👋 Cerrando Viernes...")
        if _icon:
            _icon.stop()
        sys.exit(0)

    menu = pystray.Menu(
        pystray.MenuItem("Estado", on_status),
        pystray.MenuItem("🎤 Activar voz", on_voice),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Salir", on_quit)
    )

    _icon = pystray.Icon("viernes", create_icon(), "Viernes AI", menu)
    _icon.run_detached()
    LOGGER.info("Systray iniciado")


def load_models():
    global _model, _controller, _collection, _whisper_model, _tts_engine

    LOGGER.info("Cargando modelos...")

    get_embedding_function("all-MiniLM-L6-v2")
    LOGGER.info("Embedding model loaded")

    _controller = OSController(permissions=load_permissions())
    LOGGER.info("OS Controller listo")

    _collection = load_collection(
        chroma_path="chroma_db",
        collection_name="viernes_sessions",
        embedding_model="all-MiniLM-L6-v2"
    )
    LOGGER.info("ChromaDB collection lista")

    try:
        import whisper
        _whisper_model = whisper.load_model("small")
        LOGGER.info("Whisper loaded")
    except Exception as e:
        LOGGER.warning(f"No se pudo cargar whisper: {e}")

    try:
        import pyttsx3
        _tts_engine = pyttsx3.init()
        _tts_engine.setProperty("rate", 150)
        LOGGER.info("TTS ready")
    except Exception as e:
        LOGGER.warning(f"No se pudo cargar TTS: {e}")

    setup_systray()
    LOGGER.info("Todos los modelos cargados!")


def speak(text: str):
    if _tts_engine:
        try:
            _tts_engine.say(text)
            _tts_engine.runAndWait()
        except Exception as e:
            LOGGER.error(f"TTS error: {e}")


def listen_voice() -> Optional[str]:
    if not _whisper_model:
        LOGGER.warning("Whisper no cargado")
        return None

    try:
        import pyaudio
        import whisper
        import numpy as np

        audio = pyaudio.PyAudio()
        stream = audio.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=16000,
            input=True,
            frames_per_buffer=1024
        )

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
        return result["text"].strip() if result["text"].strip() else None

    except Exception as e:
        LOGGER.error(f"Error en voz: {e}")
        return None


def process_command(user_input: str) -> str:
    LOGGER.info(f"Procesando: {user_input}")

    matches = search_sessions(
        collection=_collection,
        query_text=user_input,
        n_results=3
    )

    context_lines = []
    for i, item in enumerate(matches, start=1):
        metadata = item.get("metadata") or {}
        start_ts = metadata.get("start_ts", "N/A")
        context_lines.append(f"[Sesion {i}] {start_ts}: {item.get('document', '')[:100]}")

    context = "\n".join(context_lines) if context_lines else "Sin contexto relevante."

    prompt = (
        "Eres Viernes, asistente personal local. Analiza si el usuario quiere ejecutar una acción o hacer una pregunta.\n"
        f"Contexto de memoria: {context}\n\n"
        f"Usuario: {user_input}\n\n"
        "Responde en español. Si es una acción, devuelve SOLO JSON con formato:\n"
        '{"action": "open_app|search|memory", "args": {...}, "reason": "..."}\n'
        "Si es pregunta, responde normalmente."
    )

    response = generate_ollama(model="llama3.2:3b", prompt=prompt, timeout_seconds=30)

    if response.startswith("{"):
        import json
        try:
            plan = json.loads(response)
            if plan.get("action"):
                result = _controller.execute_action(plan["action"], plan.get("args", {}))
                return f"✅ {result.get('message', 'Hecho')}"
        except:
            pass

    return response


def interactive_loop():
    load_models()

    print("\n" + "="*50)
    print("  VIERNES INTERACTIVO")
    print("  Escribe o habla (di 'salir' para terminar)")
    print("="*50 + "\n")

    speak("Viernes listo. Puedes hablar o escribir.")

    while True:
        try:
            print("> ", end="", flush=True)
            user_input = input()

            if not user_input.strip():
                continue

            if user_input.lower() in ["salir", "exit", "quit"]:
                speak("Hasta luego")
                break

            if user_input.lower() == "voz":
                print("🎤 Escuchando...")
                user_input = listen_voice() or ""
                if user_input:
                    print(f"Escuché: {user_input}")
                else:
                    print("No escuché nada")
                    continue

            response = process_command(user_input)
            print(f"\nViernes: {response}\n")
            speak(response)

        except KeyboardInterrupt:
            print("\nHasta luego!")
            break
        except Exception as e:
            LOGGER.error(f"Error: {e}")
            print(f"Error: {e}")


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s"
    )
    interactive_loop()