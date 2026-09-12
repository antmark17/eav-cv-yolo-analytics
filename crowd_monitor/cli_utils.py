from __future__ import annotations

from pathlib import Path


from .config import AppConfig, load_config

DEFAULT_CONFIG_PATH = Path("configs/camera.local.yaml")
EXAMPLE_CONFIG_PATH = Path("configs/camera.example.yaml")


def require_config(path: str | Path) -> Path:
    config_path = Path(path)
    if config_path.exists():
        return config_path
    raise FileNotFoundError(
        f"Configuration file not found: {config_path}. "
        f"Copy {EXAMPLE_CONFIG_PATH} to {DEFAULT_CONFIG_PATH} and edit it."
    )


def load_app_config(path: str | Path) -> AppConfig:
    return load_config(require_config(path))
