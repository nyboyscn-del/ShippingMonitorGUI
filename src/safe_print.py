"""Console-safe output helpers shared by console and windowed builds.

``print`` raises ``AttributeError`` when a PyInstaller ``--noconsole`` build has
``sys.stdout`` set to ``None``. ``safe_print`` keeps the original console text
for interactive runs, mirrors every message into the ``logging`` pipeline, and
silently degrades when no usable stream exists.
"""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOG_FILE_NAME = "ShippingMonitorGUI.log"
_HANDLER_MARKER = "_shipping_monitor_log_handler"


def _runtime_log_path() -> Path:
    try:
        from config_manager import runtime_root

        return runtime_root() / "logs" / LOG_FILE_NAME
    except Exception:  # noqa: BLE001 - logging setup must never block startup
        return Path(__file__).resolve().parents[1] / "logs" / LOG_FILE_NAME


def configure_runtime_logging(log_path: str | Path | None = None, level: int = logging.INFO) -> Path:
    """Attach the shared rotating file handler once and return the log path."""
    path = Path(log_path) if log_path is not None else _runtime_log_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        return path

    root = logging.getLogger()
    if any(getattr(handler, _HANDLER_MARKER, False) for handler in root.handlers):
        return path

    try:
        handler = RotatingFileHandler(
            path,
            maxBytes=5 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8",
        )
    except OSError:
        return path
    handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
    setattr(handler, _HANDLER_MARKER, True)
    root.addHandler(handler)
    if root.level == logging.NOTSET or root.level > level:
        root.setLevel(level)
    return path


def safe_print(*args, file=None, sep: str = " ", end: str = "\n", flush: bool = False, level: int = logging.INFO, **kwargs) -> None:
    """Print to a real stream when available and always log the same text."""
    del kwargs
    try:
        message = sep.join(str(arg) for arg in args)
    except Exception:  # noqa: BLE001
        message = " ".join(repr(arg) for arg in args)

    try:
        logging.getLogger("ShippingMonitorGUI").log(level, message)
    except Exception:  # noqa: BLE001
        pass

    stream = sys.stdout if file is None else file
    if stream is None:
        return
    try:
        stream.write(message)
        if end:
            stream.write(end)
        if flush:
            stream.flush()
    except Exception:  # noqa: BLE001 - broken/closed console must not crash the app
        return

