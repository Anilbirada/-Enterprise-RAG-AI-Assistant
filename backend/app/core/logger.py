import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any, Dict


SENSITIVE_KEYS = {"password", "secret", "token", "authorization", "api_key", "secret_key"}


def mask_sensitive_data(data: Any) -> Any:
    """Recursively masks sensitive keys in dictionaries or lists."""
    if isinstance(data, dict):
        masked = {}
        for k, v in data.items():
            if any(s in k.lower() for s in SENSITIVE_KEYS):
                masked[k] = "******"
            elif isinstance(v, (dict, list)):
                masked[k] = mask_sensitive_data(v)
            else:
                masked[k] = v
        return masked
    elif isinstance(data, list):
        return [mask_sensitive_data(item) for item in data]
    return data


class JSONFormatter(logging.Formatter):
    """Custom structured JSON log formatter for enterprise observability."""

    def format(self, record: logging.LogRecord) -> str:
        log_record: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        # Include extra attributes passed to logger (like request_id, tenant_id)
        if hasattr(record, "request_id"):
            log_record["request_id"] = record.request_id
        if hasattr(record, "tenant_id"):
            log_record["tenant_id"] = record.tenant_id

        # Attach exception info if present
        if record.exc_info:
            log_record["exception"] = self.formatException(record.exc_info)

        # Mask sensitive keys if dictionary payload is attached
        if hasattr(record, "payload") and isinstance(record.payload, dict):
            log_record["payload"] = mask_sensitive_data(record.payload)

        return json.dumps(log_record)


def setup_logging(log_level: str = "INFO", log_format: str = "json") -> logging.Logger:
    """Configures root application logging with handlers and formatters."""
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level.upper())

    # Avoid duplicate handlers if setup_logging is called multiple times
    if not root_logger.handlers:
        console_handler = logging.StreamHandler(sys.stdout)
        if log_format.lower() == "json":
            console_handler.setFormatter(JSONFormatter())
        else:
            formatter = logging.Formatter(
                fmt="%(asctime)s [%(levelname)s] %(name)s (%(module)s:%(lineno)d): %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
            console_handler.setFormatter(formatter)
        root_logger.addHandler(console_handler)

    # Suppress verbose noisy third-party loggers
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)

    return logging.getLogger("enterprise_rag")
