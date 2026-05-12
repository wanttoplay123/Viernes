from __future__ import annotations

import logging
import os
import subprocess
import sys
from pathlib import Path

LOGGER = logging.getLogger("viernes.autostart")

APP_NAME = "ViernesAI"
SCRIPT_PATH = Path(__file__).parent / "main.py"
TASK_NAME = "ViernesAI_AutoStart"


def get_python_executable() -> str:
    if hasattr(sys, "executable"):
        return sys.executable
    return "python"


def create_startup_shortcut():
    import winshell
    from win32com.client import Dispatch

    startup_path = winshell.startup()
    shortcut_path = Path(startup_path) / f"{APP_NAME}.lnk"

    shell = Dispatch("WScript.Shell")
    shortcut = shell.CreateShortcut(str(shortcut_path))
    shortcut.TargetPath = get_python_executable()
    shortcut.Arguments = f'"{SCRIPT_PATH}"'
    shortcut.WorkingDirectory = str(SCRIPT_PATH.parent)
    shortcut.Description = "Viernes AI - Asistente personal"
    shortcut.Save()

    LOGGER.info(f"Atajo creado en: {shortcut_path}")
    return shortcut_path


def register_task_scheduler():
    python_exe = get_python_executable()
    script_path = str(SCRIPT_PATH.absolute())

    command = f'schtasks /create /tn "{TASK_NAME}" /tr "{python_exe} \\"{script_path}\\"" /sc onlogon /rl limited /f'

    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True
        )

        if result.returncode == 0:
            LOGGER.info("Tarea programada creada exitosamente")
            return True
        else:
            LOGGER.error(f"Error al crear tarea: {result.stderr}")
            return False

    except Exception as e:
        LOGGER.error(f"Excepción creando tarea: {e}")
        return False


def remove_startup_shortcut():
    try:
        import winshell
        startup_path = winshell.startup()
        shortcut_path = Path(startup_path) / f"{APP_NAME}.lnk"

        if shortcut_path.exists():
            shortcut_path.unlink()
            LOGGER.info(f"Atajo eliminado: {shortcut_path}")
            return True
    except Exception as e:
        LOGGER.error(f"Error eliminando atajo: {e}")

    return False


def remove_task_scheduler():
    command = f'schtasks /delete /tn "{TASK_NAME}" /f'

    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True
        )

        if result.returncode == 0:
            LOGGER.info("Tarea programada eliminada")
            return True
        else:
            LOGGER.warning(f"Error eliminando tarea: {result.stderr}")
            return False

    except Exception as e:
        LOGGER.error(f"Excepción eliminando tarea: {e}")
        return False


def is_autostart_enabled() -> bool:
    try:
        command = f'schtasks /query /tn "{TASK_NAME}"'
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True
        )
        return result.returncode == 0
    except:
        return False


def enable_autostart(method: str = "task"):
    LOGGER.info(f"Habilitando auto-inicio con método: {method}")

    if method == "shortcut":
        return create_startup_shortcut()
    elif method == "task":
        return register_task_scheduler()
    else:
        LOGGER.error(f"Método desconocido: {method}")
        return False


def disable_autostart(method: str = "task"):
    LOGGER.info(f"Deshabilitando auto-inicio con método: {method}")

    if method == "shortcut":
        return remove_startup_shortcut()
    elif method == "task":
        return remove_task_scheduler()
    else:
        LOGGER.error(f"Método desconocido: {method}")
        return False


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Viernes Auto-inicio")
    parser.add_argument("--enable", action="store_true", help="Habilitar auto-inicio")
    parser.add_argument("--disable", action="store_true", help="Deshabilitar auto-inicio")
    parser.add_argument("--status", action="store_true", help="Verificar estado")
    parser.add_argument("--method", default="task", choices=["task", "shortcut"], help="Método a usar")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    if args.enable:
        enable_autostart(args.method)
    elif args.disable:
        disable_autostart(args.method)
    elif args.status:
        enabled = is_autostart_enabled()
        print(f"Auto-inicio {'habilitado' if enabled else 'deshabilitado'}")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()