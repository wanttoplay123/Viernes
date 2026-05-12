from __future__ import annotations

import argparse
import logging
import signal
import sys
import threading
import time
from pathlib import Path

LOGGER = logging.getLogger("viernes.main")


class ViernesOrchestrator:
    def __init__(self):
        self.running = False
        self.threads = []
        self.logger_process = None
        self.indexer_thread = None

    def start_logger(self, background: bool = True):
        LOGGER.info("Iniciando activity_logger...")
        try:
            from activity_logger import main as logger_main
            if background:
                thread = threading.Thread(target=logger_main, daemon=True)
                thread.start()
                self.threads.append(thread)
                LOGGER.info("Activity logger iniciado en background")
            else:
                logger_main()
        except Exception as e:
            LOGGER.error(f"Error iniciando logger: {e}")

    def start_indexer(self, interval_minutes: int = 10):
        LOGGER.info(f"Iniciando indexador cada {interval_minutes} minutos...")
        from phase2_indexer import main as indexer_main

        def index_loop():
            while self.running:
                try:
                    indexer_main()
                except Exception as e:
                    LOGGER.error(f"Error en indexación: {e}")
                time.sleep(interval_minutes * 60)

        thread = threading.Thread(target=index_loop, daemon=True)
        thread.start()
        self.threads.append(thread)

    def start_patterns(self, interval_hours: int = 24):
        LOGGER.info(f"Iniciando detector de patrones cada {interval_hours} horas...")
        from phase4_patterns import detect_and_notify

        def patterns_loop():
            while self.running:
                try:
                    detect_and_notify()
                except Exception as e:
                    LOGGER.error(f"Error en detección de patrones: {e}")
                time.sleep(interval_hours * 3600)

        thread = threading.Thread(target=patterns_loop, daemon=True)
        thread.start()
        self.threads.append(thread)

    def start(self, modules: list[str] = None):
        if modules is None:
            modules = ["logger", "indexer", "patterns"]

        LOGGER.info(f"Iniciando Viernes AI con módulos: {modules}")
        self.running = True

        if "logger" in modules:
            self.start_logger()

        if "indexer" in modules:
            self.start_indexer()

        if "patterns" in modules:
            self.start_patterns()

        LOGGER.info("Viernes AI iniciado correctamente")

        try:
            while self.running:
                time.sleep(1)
        except KeyboardInterrupt:
            LOGGER.info("Deteniendo Viernes...")
            self.stop()

    def stop(self):
        self.running = False
        LOGGER.info("Viernes detenido")


def main():
    parser = argparse.ArgumentParser(description="Viernes AI - Orquestador principal")
    parser.add_argument(
        "--modules",
        nargs="+",
        default=["logger", "indexer", "patterns"],
        choices=["logger", "indexer", "patterns", "all"],
        help="Módulos a iniciar"
    )
    parser.add_argument(
        "--indexer-interval",
        type=int,
        default=10,
        help="Intervalo de indexación en minutos (default: 10)"
    )
    parser.add_argument(
        "--patterns-interval",
        type=int,
        default=24,
        help="Intervalo de detección de patrones en horas (default: 24)"
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    if "all" in args.modules:
        modules = ["logger", "indexer", "patterns"]
    else:
        modules = args.modules

    orchestrator = ViernesOrchestrator()

    def signal_handler(sig, frame):
        LOGGER.info("Señal de terminación recibida")
        orchestrator.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    orchestrator.start(modules)


if __name__ == "__main__":
    main()