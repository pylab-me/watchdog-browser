from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path


if __package__ in (None, ""):
    PROJECT_ROOT = Path(__file__).resolve().parent.parent
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))
    from src.db import TaskRepository
    from src.refresher import CookieRefreshService
else:
    from .db import TaskRepository
    from .refresher import CookieRefreshService


def build_arg_parser() -> argparse.ArgumentParser:
    """构建命令行参数。"""
    parser = argparse.ArgumentParser(description="Refresh website cookies from database tasks.")
    parser.add_argument(
        "--log-level",
        default="INFO",
        help="Logging level, such as INFO or DEBUG.",
    )
    return parser


async def async_main() -> None:
    """异步入口。"""
    args = build_arg_parser().parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    repository = TaskRepository()
    service = CookieRefreshService(repository)
    await service.run_forever()


def main() -> None:
    """同步入口。"""
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
