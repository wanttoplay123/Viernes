from __future__ import annotations

import io
import logging
import threading
import time
from typing import Optional

import pyttsx3
import pyaudio
import numpy as np

LOGGER = logging.getLogger("viernes.voice")

_listener = None
_is_listening = False


def load_whisper_model(model_name: str = "small"):
    try:
        import whisper
        LOGGER.info(f"Cargando modelo whisper: {model_name}")
        return whisper.load_model(model_name)
    except Exception as e:
        LOGGER.error(f"Error cargando whisper: {e}")
        return None


def listen_and_transcribe(
    duration_seconds: float = 5.0,
    sample_rate: int = 16000,
    model=None
) -> Optional[str]:
    try:
        import whisper

        if model is None:
            model = whisper.load_model("small")

        audio = pyaudio.PyAudio()
        stream = audio.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=sample_rate,
            input=True,
            frames_per_buffer=1024
        )

        LOGGER.info("Escuchando...")
        frames = []
        for _ in range(int(sample_rate / 1024 * duration_seconds)):
            data = stream.read(1024)
            frames.append(data)

        stream.stop_stream()
        stream.close()
        audio.terminate()

        audio_np = np.frombuffer(b"".join(frames), np.int16).astype(np.float32) / 32768.0

        result = model.transcribe(audio_np, language="es")
        text = result["text"].strip()

        LOGGER.info(f"Transcrito: {text}")
        return text if text else None

    except Exception as e:
        LOGGER.error(f"Error en transcripción: {e}")
        return None


def speak(text: str, rate: int = 150) -> None:
    try:
        engine = pyttsx3.init()
        engine.setProperty("rate", rate)
        engine.say(text)
        engine.runAndWait()
    except Exception as e:
        LOGGER.error(f"Error en TTS: {e}")


def continuous_listen(callback, model=None, sample_rate: int = 16000):
    global _is_listening
    _is_listening = True

    if model is None:
        try:
            import whisper
            model = whisper.load_model("small")
        except Exception as e:
            LOGGER.error(f"No se pudo cargar whisper: {e}")
            return

    audio = pyaudio.PyAudio()
    stream = audio.open(
        format=pyaudio.paInt16,
        channels=1,
        rate=sample_rate,
        input=True,
        frames_per_buffer=4096
    )

    buffer = []
    silence_threshold = 30
    silence_frames = 0

    LOGGER.info("Escucha continua iniciada")

    while _is_listening:
        try:
            data = stream.read(4096)
            buffer.append(data)

            audio_data = np.frombuffer(data, np.int16)
            if np.abs(audio_data).mean() < 500:
                silence_frames += 1
            else:
                silence_frames = 0

            if silence_frames > silence_threshold and len(buffer) > 0:
                audio_bytes = b"".join(buffer)
                audio_np = np.frombuffer(audio_bytes, np.int16).astype(np.float32) / 32768.0

                result = model.transcribe(audio_np, language="es")
                text = result["text"].strip()

                if text:
                    callback(text)

                buffer = []
                silence_frames = 0

        except Exception as e:
            LOGGER.error(f"Error en escucha continua: {e}")
            time.sleep(1)

    stream.stop_stream()
    stream.close()
    audio.terminate()
    LOGGER.info("Escucha continua detenida")


def stop_listening():
    global _is_listening
    _is_listening = False


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Viernes Voice - Módulo de voz")
    parser.add_argument("--listen", action="store_true", help="Escuchar y transcribir")
    parser.add_argument("--speak", type=str, help="Texto a hablar")
    parser.add_argument("--model", default="small", help="Modelo whisper (tiny, small, medium, large)")
    parser.add_argument("--duration", type=float, default=5.0, help="Duración de escucha en segundos")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    if args.listen:
        model = load_whisper_model(args.model)
        text = listen_and_transcribe(duration_seconds=args.duration, model=model)
        if text:
            print(f"Texto: {text}")
    elif args.speak:
        speak(args.speak)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()