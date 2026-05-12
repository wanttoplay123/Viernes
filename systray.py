from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Optional

import pystray
from PIL import Image

LOGGER = logging.getLogger("viernes.systray")

_icon: Optional[pystray.Icon] = None
_menu_callbacks = {}


def create_default_icon() -> Image.Image:
    width = 64
    height = 64

    img = Image.new("RGB", (width, height), color=(79, 142, 247))
    return img


def setup_systray(
    title: str = "Viernes AI",
    icon_path: Optional[Path] = None,
    menu_items: dict = None,
    callbacks: dict = None
):
    global _icon, _menu_callbacks

    if icon_path and icon_path.exists():
        icon_image = Image.open(icon_path)
    else:
        icon_image = create_default_icon()

    if callbacks:
        _menu_callbacks = callbacks

    if menu_items is None:
        menu_items = [
            ("Mostrar estado", "status"),
            ("Iniciar logger", "start_logger"),
            ("Detener logger", "stop_logger"),
            ("---", None),
            ("Buscar en memoria", "search"),
            ("---", None),
            ("Salir", "quit")
        ]

    menu = pystray.Menu(
        *(pystray.MenuItem(label, lambda _: handle_menu_action(action))
          for label, action in menu_items)
    )

    _icon = pystray.Icon("viernes", icon_image, title, menu)
    LOGGER.info("System tray inicializado")

    return _icon


def handle_menu_action(action: str):
    LOGGER.info(f"Acción de menú: {action}")

    callback = _menu_callbacks.get(action)
    if callback:
        try:
            callback(action)
        except Exception as e:
            LOGGER.error(f"Error ejecutando callback {action}: {e}")

    if action == "quit":
        stop_systray()


def run_systray(blocking: bool = True):
    global _icon
    if _icon:
        LOGGER.info("Iniciando system tray...")
        if blocking:
            _icon.run()
        else:
            thread = threading.Thread(target=_icon.run, daemon=True)
            thread.start()
    else:
        LOGGER.warning("System tray no inicializado")


def stop_systray():
    global _icon
    if _icon:
        LOGGER.info("Deteniendo system tray...")
        _icon.stop()
        _icon = None


def notify(title: str, message: str):
    global _icon
    if _icon:
        _icon.notify(message, title)


def update_menu(menu_items: dict):
    global _icon
    if _icon:
        _icon.menu = pystray.Menu(
            *(pystray.MenuItem(label, lambda _: handle_menu_action(action))
              for label, action in menu_items)
        )


class SystrayManager:
    def __init__(self):
        self.icon = None
        self.running = False

    def start(
        self,
        title: str = "Viernes AI",
        icon_path: Optional[Path] = None,
        on_status: callable = None,
        on_start_logger: callable = None,
        on_stop_logger: callable = None,
        on_search: callable = None,
        on_quit: callable = None
    ):
        callbacks = {}
        if on_status:
            callbacks["status"] = on_status
        if on_start_logger:
            callbacks["start_logger"] = on_start_logger
        if on_stop_logger:
            callbacks["stop_logger"] = on_stop_logger
        if on_search:
            callbacks["search"] = on_search
        if on_quit:
            callbacks["quit"] = on_quit

        self.icon = setup_systray(title, icon_path, callbacks=callbacks)
        self.running = True
        run_systray(blocking=False)

    def stop(self):
        self.running = False
        stop_systray()

    def notify(self, title: str, message: str):
        notify(title, message)


def main():
    import argparse
    import time

    parser = argparse.ArgumentParser(description="Viernes Systray")
    parser.add_argument("--test", action="store_true", help="Probar system tray")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    def on_menu(action):
        LOGGER.info(f"Menu clickeado: {action}")

    manager = SystrayManager()
    manager.start(on_status=on_menu, on_quit=lambda _: manager.stop())

    try:
        while manager.running:
            time.sleep(1)
    except KeyboardInterrupt:
        manager.stop()


if __name__ == "__main__":
    main()