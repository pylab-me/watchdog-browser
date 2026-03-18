from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import threading
from dataclasses import dataclass
from pathlib import Path
from queue import Empty, Queue
from tempfile import TemporaryDirectory
from urllib.parse import urlparse


try:
    from playwright.async_api import BrowserContext
    from playwright.async_api import Page
    from playwright.async_api import async_playwright
except ImportError:
    BrowserContext = None
    Page = None
    async_playwright = None

if __package__ in (None, ""):
    PROJECT_ROOT = Path(__file__).resolve().parent.parent
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))
    from src.db import TaskRepository
    from src.models import utc_now
    from src.state import compress_session_storage, compress_storage_state
else:
    from .db import TaskRepository
    from .models import utc_now
    from .state import compress_session_storage, compress_storage_state

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class BootstrapConfig:
    site_url: str
    reload_url: str
    state_scope_url: str
    refresh_interval_seconds: int = 86400
    retry_interval_seconds: int = 900
    browser_channel: str = "chrome"
    wait_until: str = "networkidle"
    settle_time_ms: int = 3000
    remark: str = ""


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Bootstrap the first cookie refresh task.")
    parser.add_argument("--site-url", required=True, help="Website URL to open in Playwright.")
    parser.add_argument(
        "--reload-url",
        default="",
        help="URL to revisit after initial page load. Defaults to site URL.",
    )
    parser.add_argument(
        "--state-scope-url",
        default="",
        help="Scope URL for collecting storage state. Defaults to site URL.",
    )
    parser.add_argument("--refresh-interval-seconds", type=int, default=86400)
    parser.add_argument("--retry-interval-seconds", type=int, default=900)
    parser.add_argument("--browser-channel", default="chrome")
    parser.add_argument("--wait-until", default="networkidle")
    parser.add_argument("--settle-time-ms", type=int, default=3000)
    parser.add_argument("--remark", default="", help="Optional remark stored in database.")
    parser.add_argument("--log-level", default="INFO")
    return parser


def start_user_command_thread(command_queue: Queue[str], stop_event: threading.Event) -> threading.Thread:
    """启动用户命令监听线程。"""

    def _reader() -> None:
        print("Commands: capture | status | quit")
        while not stop_event.is_set():
            try:
                command = input("> ").strip().lower()
            except EOFError:
                command = "quit"
            command_queue.put(command)
            if command == "quit":
                stop_event.set()
                return

    thread = threading.Thread(target=_reader, name="bootstrap-user-input", daemon=True)
    thread.start()
    return thread


async def run_bootstrap(config: BootstrapConfig) -> int:
    """启动浏览器，等待用户手动操作，然后捕获完整认证态写入数据库。"""
    if async_playwright is None:
        raise RuntimeError("playwright is required for bootstrap")

    repository = TaskRepository()
    command_queue: Queue[str] = Queue()
    stop_event = threading.Event()
    start_user_command_thread(command_queue, stop_event)
    reload_url = config.reload_url or config.site_url
    state_scope_url = config.state_scope_url or config.site_url
    temp_dir = TemporaryDirectory()

    try:
        async with async_playwright() as playwright:
            context: BrowserContext = await playwright.chromium.launch_persistent_context(
                user_data_dir=temp_dir.name,
                channel=config.browser_channel,
                headless=False,
                ignore_default_args=["--enable-automation"],
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--disable-dev-shm-usage",
                    "--no-first-run",
                    "--no-default-browser-check",
                ],
            )
            try:
                page = context.pages[0] if context.pages else await context.new_page()
                await page.goto(config.site_url, wait_until=config.wait_until)
                print(f"Opened: {config.site_url}")
                print(f"Temporary user data dir: {temp_dir.name}")
                print("Log in or complete any required actions in the browser window.")
                print("When the session is ready, type `capture` in this terminal.")

                while not stop_event.is_set():
                    try:
                        command = command_queue.get_nowait()
                    except Empty:
                        await asyncio.sleep(0.2)
                        continue

                    if command == "status":
                        current_url = page.url
                        print(f"Current page: {current_url}")
                        continue

                    if command == "capture":
                        if config.settle_time_ms > 0:
                            await page.wait_for_timeout(config.settle_time_ms)
                        session_storage = await capture_session_storage(page, state_scope_url)
                        storage_state = await context.storage_state(indexed_db=True)
                        task_id = repository.insert_task(
                            site_url=config.site_url,
                            reload_url=reload_url,
                            state_scope_url=state_scope_url,
                            storage_state=compress_storage_state(storage_state),
                            session_storage=compress_session_storage(session_storage),
                            next_poll_at=utc_now(),
                            refresh_interval_seconds=config.refresh_interval_seconds,
                            retry_interval_seconds=config.retry_interval_seconds,
                            headless=True,
                            browser_channel=config.browser_channel,
                            wait_until=config.wait_until,
                            settle_time_ms=config.settle_time_ms,
                            remark=config.remark,
                        )
                        print(
                            f"Inserted task id={task_id}, "
                            f"cookies={len(storage_state.get('cookies', []))}, "
                            f"origins={len(storage_state.get('origins', []))}, "
                            f"session_origins={len(session_storage)}"
                        )
                        stop_event.set()
                        return task_id

                    if command == "quit":
                        stop_event.set()
                        raise RuntimeError("Bootstrap cancelled by user")

                    print("Unknown command. Use: capture | status | quit")
            finally:
                stop_event.set()
                await context.close()
    finally:
        temp_dir.cleanup()


async def async_main() -> None:
    args = build_arg_parser().parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    config = BootstrapConfig(
        site_url=args.site_url,
        reload_url=args.reload_url,
        state_scope_url=args.state_scope_url,
        refresh_interval_seconds=args.refresh_interval_seconds,
        retry_interval_seconds=args.retry_interval_seconds,
        browser_channel=args.browser_channel,
        wait_until=args.wait_until,
        settle_time_ms=args.settle_time_ms,
        remark=args.remark,
    )
    await run_bootstrap(config)


def main() -> None:
    asyncio.run(async_main())


async def capture_session_storage(page: "Page", scope_url: str) -> dict[str, dict[str, str]]:
    origin = origin_from_url(scope_url)
    current_origin = origin_from_url(page.url)
    if current_origin != origin:
        await page.goto(scope_url, wait_until="domcontentloaded")
    data = await page.evaluate(
        """
        () => {
          const state = {};
          for (let i = 0; i < window.sessionStorage.length; i += 1) {
            const key = window.sessionStorage.key(i);
            if (key !== null) {
              state[key] = window.sessionStorage.getItem(key) ?? "";
            }
          }
          return state;
        }
        """
    )
    if not isinstance(data, dict):
        return {}
    return {origin: {str(key): str(value) for key, value in data.items()}}


def origin_from_url(url: str) -> str:
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}"


if __name__ == "__main__":
    main()
