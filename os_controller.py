from __future__ import annotations

import os
import shutil
import smtplib
import subprocess
from email.message import EmailMessage
from pathlib import Path

import pyautogui
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright

from permissions import PermissionsConfig


class OSController:
    def __init__(self, permissions: PermissionsConfig) -> None:
        self.permissions = permissions

    def open_file(self, path: str, app: str | None = None) -> dict[str, str]:
        if not self.permissions.is_path_allowed(path):
            raise PermissionError(f"Ruta fuera de whitelist: {path}")

        file_path = Path(path).expanduser().resolve(strict=False)
        if not file_path.exists():
            raise FileNotFoundError(f"Archivo no encontrado: {file_path}")

        if app is not None:
            self.open_app(app, file_arg=str(file_path))
            return {"status": "ok", "message": f"Archivo abierto con app {app}: {file_path}"}

        if os.name == "nt":
            os.startfile(str(file_path))
        else:
            subprocess.Popen(["xdg-open", str(file_path)])

        return {"status": "ok", "message": f"Archivo abierto: {file_path}"}

    def open_app(self, app: str, file_arg: str | None = None) -> dict[str, str]:
        if not self.permissions.is_app_allowed(app):
            raise PermissionError(f"App fuera de whitelist: {app}")

        import platform
        if platform.system() == "Windows":
            app_with_ext = f"{app}.exe" if not app.endswith(".exe") else app
            command = ["start", "", app_with_ext]
            subprocess.run(command, shell=True)
        else:
            command = [app]
            if file_arg is not None:
                command.append(file_arg)
            subprocess.Popen(command)
        return {"status": "ok", "message": f"Aplicacion abierta: {app}"}

    def copy_file(self, src: str, dst: str) -> dict[str, str]:
        if not self.permissions.is_path_allowed(src):
            raise PermissionError(f"Ruta origen fuera de whitelist: {src}")
        if not self.permissions.is_path_allowed(dst):
            raise PermissionError(f"Ruta destino fuera de whitelist: {dst}")

        src_path = Path(src).expanduser().resolve(strict=False)
        dst_path = Path(dst).expanduser().resolve(strict=False)
        if not src_path.exists():
            raise FileNotFoundError(f"Archivo origen no encontrado: {src_path}")

        dst_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src_path, dst_path)
        return {"status": "ok", "message": f"Archivo copiado: {src_path} -> {dst_path}"}

    def move_file(self, src: str, dst: str) -> dict[str, str]:
        if not self.permissions.is_path_allowed(src):
            raise PermissionError(f"Ruta origen fuera de whitelist: {src}")
        if not self.permissions.is_path_allowed(dst):
            raise PermissionError(f"Ruta destino fuera de whitelist: {dst}")

        src_path = Path(src).expanduser().resolve(strict=False)
        dst_path = Path(dst).expanduser().resolve(strict=False)
        if not src_path.exists():
            raise FileNotFoundError(f"Archivo origen no encontrado: {src_path}")

        dst_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src_path), str(dst_path))
        return {"status": "ok", "message": f"Archivo movido: {src_path} -> {dst_path}"}

    def delete_file(self, path: str) -> dict[str, str]:
        if not self.permissions.is_path_allowed(path):
            raise PermissionError(f"Ruta fuera de whitelist: {path}")

        target = Path(path).expanduser().resolve(strict=False)
        if not target.exists():
            raise FileNotFoundError(f"Archivo no encontrado: {target}")
        if target.is_dir():
            raise IsADirectoryError(f"La ruta es carpeta, no archivo: {target}")

        target.unlink()
        return {"status": "ok", "message": f"Archivo eliminado: {target}"}

    def click(self, x: int, y: int) -> dict[str, str]:
        pyautogui.click(x=x, y=y)
        return {"status": "ok", "message": f"Click ejecutado en ({x}, {y})"}

    def type_text(self, text: str, interval: float = 0.02) -> dict[str, str]:
        pyautogui.write(text, interval=interval)
        return {"status": "ok", "message": "Texto escrito por teclado virtual"}

    def screenshot(self, output_path: str) -> dict[str, str]:
        if not self.permissions.is_path_allowed(output_path):
            raise PermissionError(f"Ruta fuera de whitelist: {output_path}")

        target = Path(output_path).expanduser().resolve(strict=False)
        target.parent.mkdir(parents=True, exist_ok=True)
        image = pyautogui.screenshot()
        image.save(str(target))
        return {"status": "ok", "message": f"Screenshot guardado en {target}"}

    def browser_open(self, url: str) -> dict[str, str]:
        if not self.permissions.is_domain_allowed(url):
            raise PermissionError(f"Dominio no permitido en whitelist: {url}")

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=False)
            page = browser.new_page()
            page.goto(url, wait_until="domcontentloaded")
            browser.close()

        return {"status": "ok", "message": f"URL abierta en Chromium: {url}"}

    def browser_extract_text(self, url: str, selector: str = "body") -> dict[str, str]:
        if not self.permissions.is_domain_allowed(url):
            raise PermissionError(f"Dominio no permitido en whitelist: {url}")

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(url, wait_until="domcontentloaded")
            text = page.inner_text(selector)
            browser.close()

        return {"status": "ok", "text": text}

    def send_email(self, to: str, subject: str, body: str) -> dict[str, str]:
        if not self.permissions.is_email_allowed(to):
            raise PermissionError(f"Destinatario no aprobado en whitelist: {to}")

        smtp_host = os.environ.get("FRIDAY_SMTP_HOST")
        smtp_port_raw = os.environ.get("FRIDAY_SMTP_PORT", "587")
        smtp_user = os.environ.get("FRIDAY_SMTP_USER")
        smtp_password = os.environ.get("FRIDAY_SMTP_PASSWORD")
        mail_from = os.environ.get("FRIDAY_EMAIL_FROM", smtp_user)

        if not smtp_host or not smtp_user or not smtp_password or not mail_from:
            raise RuntimeError(
                "Faltan credenciales SMTP en variables de entorno (FRIDAY_SMTP_*)."
            )

        smtp_port = int(smtp_port_raw)
        message = EmailMessage()
        message["From"] = mail_from
        message["To"] = to
        message["Subject"] = subject
        message.set_content(body)

        with smtplib.SMTP(smtp_host, smtp_port, timeout=30) as server:
            server.starttls()
            server.login(smtp_user, smtp_password)
            server.send_message(message)

        return {"status": "ok", "message": f"Correo enviado a {to}"}

    def execute_action(self, action: str, args: dict[str, object]) -> dict[str, str]:
        try:
            if action == "open_file":
                path = str(args["path"])
                app = str(args["app"]) if "app" in args and args["app"] else None
                return self.open_file(path=path, app=app)
            if action == "open_app":
                return self.open_app(app=str(args["app"]))
            if action == "copy_file":
                return self.copy_file(src=str(args["src"]), dst=str(args["dst"]))
            if action == "move_file":
                return self.move_file(src=str(args["src"]), dst=str(args["dst"]))
            if action == "delete_file":
                return self.delete_file(path=str(args["path"]))
            if action == "open_url":
                return self.browser_open(url=str(args["url"]))
            if action == "extract_page_text":
                selector = str(args["selector"]) if "selector" in args else "body"
                return self.browser_extract_text(url=str(args["url"]), selector=selector)
            if action == "send_email":
                return self.send_email(
                    to=str(args["to"]),
                    subject=str(args["subject"]),
                    body=str(args["body"]),
                )
            if action == "mouse_click":
                return self.click(x=int(args["x"]), y=int(args["y"]))
            if action == "type_text":
                interval = float(args["interval"]) if "interval" in args else 0.02
                return self.type_text(text=str(args["text"]), interval=interval)
            if action == "screenshot":
                return self.screenshot(output_path=str(args["path"]))
        except KeyError as exc:
            raise ValueError(f"Falta argumento requerido en accion {action}: {exc}") from exc
        except subprocess.SubprocessError as exc:
            raise RuntimeError(f"Fallo ejecutando subprocess para accion {action}: {exc}") from exc
        except OSError as exc:
            raise RuntimeError(f"Fallo de sistema en accion {action}: {exc}") from exc
        except smtplib.SMTPException as exc:
            raise RuntimeError(f"Fallo SMTP en accion {action}: {exc}") from exc
        except PlaywrightError as exc:
            raise RuntimeError(f"Fallo Playwright en accion {action}: {exc}") from exc

        raise ValueError(f"Accion no soportada: {action}")

    def open_url(self, url: str) -> dict[str, str]:
        import platform
        if platform.system() == "Windows":
            subprocess.run(["start", "", url], shell=True)
        else:
            subprocess.run(["xdg-open", url])
        return {"status": "ok", "message": f"Abierto: {url}"}

