"""
Structured Logging Configuration with Secrets Sanitizer.
Ensures MONGODB_URI passwords, auth tokens, and API keys are never printed in logs.
"""

import re
import logging
import sys

# Patterns to mask in logs
SECRET_PATTERNS = [
    (
        re.compile(r"mongodb(?:\+srv)?://([^:]+):([^@]+)@", re.IGNORECASE),
        r"mongodb://\1:***@",
    ),
    (re.compile(r"(AIzaSy[a-zA-Z0-9_\-]{30,})", re.IGNORECASE), r"AIzaSy***"),
    (re.compile(r"(gsk_[a-zA-Z0-9_\-]{30,})", re.IGNORECASE), r"gsk_***"),
    (re.compile(r'("password"\s*:\s*)"[^"]+"', re.IGNORECASE), r'\1"***"'),
    (re.compile(r'("password_hash"\s*:\s*)"[^"]+"', re.IGNORECASE), r'\1"***"'),
]


class SecretsSanitizingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            for pattern, repl in SECRET_PATTERNS:
                record.msg = pattern.sub(repl, record.msg)
        if record.args:
            if isinstance(record.args, dict):
                clean_args = {}
                for k, v in record.args.items():
                    if isinstance(v, str):
                        for pattern, repl in SECRET_PATTERNS:
                            v = pattern.sub(repl, v)
                    clean_args[k] = v
                record.args = clean_args
            elif isinstance(record.args, (list, tuple)):
                clean_args = []
                for v in record.args:
                    if isinstance(v, str):
                        for pattern, repl in SECRET_PATTERNS:
                            v = pattern.sub(repl, v)
                    clean_args.append(v)
                record.args = tuple(clean_args)
        return True


def setup_logging(log_level: int = logging.INFO):
    """Sets up formatted, sanitized logging."""
    logger = logging.getLogger()
    logger.setLevel(log_level)

    # Avoid duplicate handlers
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        formatter = logging.Formatter(
            fmt="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        handler.setFormatter(formatter)
        handler.addFilter(SecretsSanitizingFilter())
        logger.addHandler(handler)
    else:
        for handler in logger.handlers:
            handler.addFilter(SecretsSanitizingFilter())

    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


setup_logging()
logger = logging.getLogger("app")
