from __future__ import annotations

import os
from typing import Any


try:
    from sqlalchemy import create_engine
except ImportError:
    create_engine = None

remote_ = os.getenv(
    "WATCHDOG_BROWSER_REMOTE_DSN",
    "postgresql+psycopg2://user:password@127.0.0.1:5432/watchdog_browser?client_encoding=utf8",
)

local_ = os.getenv(
    "WATCHDOG_BROWSER_LOCAL_DSN",
    "postgresql+psycopg2://user:password@127.0.0.1:5432/watchdog_browser?client_encoding=utf8",
)

engine: Any = None


def get_engine():
    global engine
    if engine is None:
        if create_engine is None:
            raise RuntimeError("sqlalchemy is required for database access")

        engine = create_engine(
            local_,
            pool_recycle=3600,
            pool_size=5,
            pool_use_lifo=True,
        )
    return engine
