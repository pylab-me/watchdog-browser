from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import urlparse


try:
    from playwright.async_api import Error as PlaywrightError
    from playwright.async_api import Browser
    from playwright.async_api import BrowserContext
    from playwright.async_api import Page
    from playwright.async_api import async_playwright
except ImportError:
    PlaywrightError = Exception
    Browser = None
    BrowserContext = None
    Page = None
    async_playwright = None

from .db import TaskRepository
from .models import CookieRefreshTask, utc_now
from .state import (
    compress_session_storage,
    compress_storage_state,
    decompress_session_storage,
    decompress_storage_state,
)


logger = logging.getLogger(__name__)

MAX_SLEEP_SECONDS = 900


@dataclass(slots=True)
class RefreshResult:
    """单次刷新结果。"""

    storage_state: bytes
    session_storage: bytes | None
    refreshed_at: datetime


class CookieRefreshService:
    """从数据库拉取任务并刷新浏览器认证态。"""

    def __init__(self, repository: TaskRepository) -> None:
        self.repository = repository

    async def run_forever(self) -> None:
        """常驻轮询任务。"""
        while True:
            now = utc_now()
            due_tasks = self.repository.fetch_due_tasks(now)

            if due_tasks:
                for task in due_tasks:
                    await self._run_single_task(task)
                continue

            sleep_seconds = self._compute_sleep_seconds(now)
            logger.info("No due tasks, sleep %.1f seconds", sleep_seconds)
            await asyncio.sleep(sleep_seconds)

    def _compute_sleep_seconds(self, now) -> float:
        next_due = self.repository.fetch_next_due_time()
        if next_due is None:
            return float(MAX_SLEEP_SECONDS)

        delta = (next_due - now).total_seconds()
        if delta <= 0:
            return 0.0
        return float(min(delta, MAX_SLEEP_SECONDS))

    async def _run_single_task(self, task: CookieRefreshTask) -> None:
        logger.info("Refreshing task id=%s site=%s", task.task_id, task.site_url)
        try:
            result = await self.refresh_task(task)
        except Exception as exc:
            logger.exception("Refresh failed for task id=%s", task.task_id)
            self.repository.mark_failure(
                task_id=task.task_id,
                error_message=str(exc),
                next_poll_at=task.next_retry_time(),
            )
            return

        self.repository.mark_success(
            task_id=task.task_id,
            storage_state=result.storage_state,
            session_storage=result.session_storage,
            refreshed_at=result.refreshed_at,
            next_poll_at=task.next_success_time(result.refreshed_at),
        )

    async def refresh_task(self, task: CookieRefreshTask) -> RefreshResult:
        """打开页面并抓取最新 storage state。"""
        if async_playwright is None:
            raise RuntimeError("playwright is required for storage state refresh")

        existing_storage_state = decompress_storage_state(task.storage_state)
        existing_session_storage = decompress_session_storage(task.session_storage)
        refreshed_at = utc_now()

        async with async_playwright() as playwright:
            browser: Browser = await playwright.chromium.launch(
                channel=task.browser_channel,
                headless=task.headless,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--disable-dev-shm-usage",
                    "--no-first-run",
                    "--no-default-browser-check",
                ],
            )
            temp_dir = TemporaryDirectory()
            state_file = f"{temp_dir.name}/storage_state.json"
            _write_storage_state_file(state_file, existing_storage_state)
            context: BrowserContext | None = None
            try:
                context = await browser.new_context(storage_state=state_file)
                page = await context.new_page()
                await _restore_session_storage(page, existing_session_storage, task.state_scope_url)
                await page.goto(task.site_url, wait_until=task.wait_until)
                if task.settle_time_ms > 0:
                    await page.wait_for_timeout(task.settle_time_ms)
                await page.goto(task.reload_url or task.site_url, wait_until=task.wait_until)
                if task.settle_time_ms > 0:
                    await page.wait_for_timeout(task.settle_time_ms)
                session_storage = await _capture_session_storage(page, task.state_scope_url)
                storage_state = await context.storage_state(indexed_db=True)
                return RefreshResult(
                    storage_state=compress_storage_state(storage_state),
                    session_storage=compress_session_storage(session_storage),
                    refreshed_at=refreshed_at,
                )
            except PlaywrightError as exc:
                raise RuntimeError(f"Playwright refresh failed: {exc}") from exc
            finally:
                if context is not None:
                    await context.close()
                temp_dir.cleanup()
                await browser.close()


def compute_sleep_hint(next_due_time, now=None) -> float:
    """测试辅助函数。"""
    current = now or utc_now()
    delta = (next_due_time - current).total_seconds()
    if delta <= 0:
        return 0.0
    return min(delta, MAX_SLEEP_SECONDS)


def _write_storage_state_file(filename: str, storage_state: dict) -> None:
    Path(filename).write_text(
        json.dumps(storage_state, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )


async def _restore_session_storage(
    page: "Page",
    session_storage: dict[str, dict[str, str]],
    site_url: str,
) -> None:
    origin = _origin_from_url(site_url)
    current_state = session_storage.get(origin)
    if not current_state:
        return
    await page.add_init_script(
        """
        (state) => {
          for (const [key, value] of Object.entries(state)) {
            window.sessionStorage.setItem(key, value);
          }
        }
        """,
        current_state,
    )


async def _capture_session_storage(page: "Page", scope_url: str) -> dict[str, dict[str, str]]:
    origin = _origin_from_url(scope_url)
    current_origin = _origin_from_url(page.url)
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


def _origin_from_url(url: str) -> str:
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}"
