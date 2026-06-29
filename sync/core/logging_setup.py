"""Thiết lập logging ra console và file xoay vòng theo ngày chạy."""

from __future__ import annotations

import logging
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

from .config import LoggingConfig


def setup_logging(config: LoggingConfig, base_dir: Path) -> None:
    """Configure root logging handlers."""
    level = getattr(logging, config.level.upper(), logging.INFO)
    log_dir = Path(config.file_dir)
    if not log_dir.is_absolute():
        log_dir = base_dir / log_dir
    log_dir.mkdir(parents=True, exist_ok=True)

    log_file = log_dir / f"sync_{datetime.now().date().isoformat()}.log"
    formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()

    console = logging.StreamHandler()
    console.setFormatter(formatter)
    console.setLevel(level)

    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=max(1, config.max_file_size_mb) * 1024 * 1024,
        backupCount=max(0, config.backup_count),
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(level)

    root.addHandler(console)
    root.addHandler(file_handler)
