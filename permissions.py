from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse


@dataclass(frozen=True)
class PermissionsConfig:
    allowed_apps: list[str]
    allowed_directories: list[Path]
    allowed_email_recipients: list[str]
    allowed_browser_domains: list[str]

    def is_app_allowed(self, app_name: str) -> bool:
        return app_name.lower() in {name.lower() for name in self.allowed_apps}

    def is_path_allowed(self, path: str) -> bool:
        candidate = Path(path).expanduser().resolve(strict=False)
        for root in self.allowed_directories:
            if candidate == root:
                return True
            if root in candidate.parents:
                return True
        return False

    def is_email_allowed(self, email: str) -> bool:
        return email.lower() in {item.lower() for item in self.allowed_email_recipients}

    def is_domain_allowed(self, url: str) -> bool:
        parsed = urlparse(url)
        if not parsed.scheme or not parsed.hostname:
            raise ValueError(f"URL invalida: {url}")
        host = parsed.hostname.lower()
        allow_all = "*" in self.allowed_browser_domains
        if allow_all:
            return True
        return host in {domain.lower() for domain in self.allowed_browser_domains}


def _default_permissions() -> dict[str, list[str]]:
    project_root = Path(__file__).resolve().parent
    home = Path.home()
    return {
        "allowed_apps": ["notepad", "code", "msedge", "chrome", "explorer"],
        "allowed_directories": [
            str(project_root),
            str(home / "Documents"),
            str(home / "Downloads"),
        ],
        "allowed_email_recipients": [],
        "allowed_browser_domains": ["localhost", "127.0.0.1", "github.com", "google.com"],
    }


def load_permissions(path: str = "permissions.json") -> PermissionsConfig:
    config_path = Path(path)
    if not config_path.exists():
        config_path.write_text(
            json.dumps(_default_permissions(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    raw = json.loads(config_path.read_text(encoding="utf-8"))
    required = {
        "allowed_apps",
        "allowed_directories",
        "allowed_email_recipients",
        "allowed_browser_domains",
    }
    missing = required.difference(raw.keys())
    if missing:
        raise ValueError(f"permissions.json incompleto. Faltan claves: {sorted(missing)}")

    directories = [Path(item).expanduser().resolve(strict=False) for item in raw["allowed_directories"]]
    if not directories:
        raise ValueError("Debes definir al menos una carpeta en allowed_directories.")

    return PermissionsConfig(
        allowed_apps=list(raw["allowed_apps"]),
        allowed_directories=directories,
        allowed_email_recipients=list(raw["allowed_email_recipients"]),
        allowed_browser_domains=list(raw["allowed_browser_domains"]),
    )

