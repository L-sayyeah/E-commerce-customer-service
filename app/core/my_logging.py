import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from app.core.config import settings


def setup_logging():
    log_level = getattr(logging, settings.log_level.upper(), logging.INFO)
    log_path = Path(settings.log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    # 日志格式 时间 | 日志级别 | 记录器名称 | 文件名:行号 | 日志消息
    log_format = "%(asctime)s - %(levelname)s - %(name)s - %(funcName)s - %(filename)s:%(lineno)d -  - %(message)s"

    handlers: list[logging.Handler] = [
        logging.StreamHandler(sys.stdout),
        RotatingFileHandler(
            filename=log_path,
            maxBytes=20 * 1024 * 1024,
            backupCount=10,
            encoding="utf-8"
        )
    ]

    logging.basicConfig(
        level=log_level,
        format=log_format,
        handlers=handlers,
        force=True
    )

    logging.getLogger("sqlalchemy").setLevel(
        logging.INFO if settings.debug else logging.WARNING
    )