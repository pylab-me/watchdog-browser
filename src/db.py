from __future__ import annotations

from datetime import datetime
from typing import Optional, TYPE_CHECKING


try:
    from sqlalchemy import text
except ImportError:
    text = None

if TYPE_CHECKING:
    from sqlalchemy.engine import Connection

from .engine import get_engine

from .models import CookieRefreshTask, ensure_utc, utc_now
from .state import storage_state_to_headers


def _sql_text(query: str):
    if text is None:
        raise RuntimeError("sqlalchemy is required for database access")
    return text(query)


class TaskRepository:
    """Postgres 数据库访问层。"""

    def connect(self) -> "Connection":
        """创建数据库连接。"""
        return get_engine().connect()

    def fetch_due_tasks(self, now: datetime) -> list[CookieRefreshTask]:
        """读取当前应执行的任务。"""
        now_text = ensure_utc(now).isoformat()
        query = _sql_text("""
        SELECT
          id,
          site_url,
          reload_url,
          state_scope_url,
          storage_state,
          session_storage,
          next_poll_at,
          refresh_interval_seconds,
          retry_interval_seconds,
          headless,
          browser_channel,
          enabled,
          wait_until,
          settle_time_ms,
          remark,
          last_refreshed_at,
          last_error
        FROM cookie_refresh_tasks
        WHERE enabled = TRUE
          AND next_poll_at <= :now_text
        ORDER BY next_poll_at ASC, id ASC
        """)
        with self.connect() as connection:
            rows = connection.execute(query, {"now_text": now_text}).mappings().all()
        return [CookieRefreshTask.from_row(dict(row)) for row in rows]

    def fetch_next_due_time(self) -> Optional[datetime]:
        """读取最早的下次轮询时间。"""
        query = _sql_text("""
        SELECT next_poll_at
        FROM cookie_refresh_tasks
        WHERE enabled = TRUE
        ORDER BY next_poll_at ASC, id ASC
        LIMIT 1
        """)
        with self.connect() as connection:
            row = connection.execute(query).mappings().first()
        if row is None:
            return None
        return ensure_utc(row["next_poll_at"])

    def fetch_task_by_id(self, task_id: int) -> Optional[CookieRefreshTask]:
        """按 id 读取单条任务。"""
        query = _sql_text("""
        SELECT
          id,
          site_url,
          reload_url,
          state_scope_url,
          storage_state,
          session_storage,
          next_poll_at,
          refresh_interval_seconds,
          retry_interval_seconds,
          headless,
          browser_channel,
          enabled,
          wait_until,
          settle_time_ms,
          remark,
          last_refreshed_at,
          last_error
        FROM cookie_refresh_tasks
        WHERE id = :task_id
        LIMIT 1
        """)
        with self.connect() as connection:
            row = connection.execute(query, {"task_id": task_id}).mappings().first()
        if row is None:
            return None
        return CookieRefreshTask.from_row(dict(row))

    def build_headers_for_task(self, task_id: int) -> dict[str, str]:
        """从数据库任务读取 cookies，并转成 HTTP headers dict。"""
        task = self.fetch_task_by_id(task_id)
        if task is None:
            raise KeyError(f"Task not found: {task_id}")
        return storage_state_to_headers(task.storage_state)

    def mark_success(
        self,
        task_id: int,
        storage_state: bytes,
        session_storage: bytes | None,
        refreshed_at: datetime,
        next_poll_at: datetime,
    ) -> None:
        """写回成功结果。"""
        query = _sql_text("""
        UPDATE cookie_refresh_tasks
        SET storage_state = :storage_state,
            session_storage = :session_storage,
            last_refreshed_at = :refreshed_at,
            next_poll_at = :next_poll_at,
            last_error = '',
            updated_at = :updated_at
        WHERE id = :task_id
        """)
        refreshed_text = ensure_utc(refreshed_at).isoformat()
        next_poll_text = ensure_utc(next_poll_at).isoformat()
        with self.connect() as connection:
            connection.execute(
                query,
                {
                    "storage_state": storage_state,
                    "session_storage": session_storage,
                    "refreshed_at": refreshed_text,
                    "next_poll_at": next_poll_text,
                    "updated_at": refreshed_text,
                    "task_id": task_id,
                },
            )
            connection.commit()

    def mark_failure(self, task_id: int, error_message: str, next_poll_at: datetime) -> None:
        """写回失败结果。"""
        query = _sql_text("""
        UPDATE cookie_refresh_tasks
        SET last_error = :last_error,
            next_poll_at = :next_poll_at,
            updated_at = :updated_at
        WHERE id = :task_id
        """)
        now_text = utc_now().isoformat()
        next_poll_text = ensure_utc(next_poll_at).isoformat()
        with self.connect() as connection:
            connection.execute(
                query,
                {
                    "last_error": error_message[:2000],
                    "next_poll_at": next_poll_text,
                    "updated_at": now_text,
                    "task_id": task_id,
                },
            )
            connection.commit()

    def insert_task(
        self,
        site_url: str,
        reload_url: str,
        state_scope_url: str,
        storage_state: bytes,
        session_storage: bytes | None,
        next_poll_at: datetime,
        refresh_interval_seconds: int = 86400,
        retry_interval_seconds: int = 900,
        headless: bool = True,
        browser_channel: str = "chrome",
        wait_until: str = "networkidle",
        settle_time_ms: int = 3000,
        remark: str = "",
    ) -> int:
        """插入首条 storage state 刷新任务。"""
        now_text = utc_now().isoformat()
        query = _sql_text("""
        INSERT INTO cookie_refresh_tasks (
            site_url,
            reload_url,
            state_scope_url,
            storage_state,
            session_storage,
            next_poll_at,
            refresh_interval_seconds,
            retry_interval_seconds,
            headless,
            browser_channel,
            enabled,
            wait_until,
            settle_time_ms,
            remark,
            last_refreshed_at,
            last_error,
            updated_at
        ) VALUES (
            :site_url,
            :reload_url,
            :state_scope_url,
            :storage_state,
            :session_storage,
            :next_poll_at,
            :refresh_interval_seconds,
            :retry_interval_seconds,
            :headless,
            :browser_channel,
            TRUE,
            :wait_until,
            :settle_time_ms,
            :remark,
            :last_refreshed_at,
            '',
            :updated_at
        )
        RETURNING id
        """)
        params = {
            "site_url": site_url,
            "reload_url": reload_url,
            "state_scope_url": state_scope_url,
            "storage_state": storage_state,
            "session_storage": session_storage,
            "next_poll_at": ensure_utc(next_poll_at).isoformat(),
            "refresh_interval_seconds": refresh_interval_seconds,
            "retry_interval_seconds": retry_interval_seconds,
            "headless": headless,
            "browser_channel": browser_channel,
            "wait_until": wait_until,
            "settle_time_ms": settle_time_ms,
            "remark": remark,
            "last_refreshed_at": now_text,
            "updated_at": now_text,
        }
        with self.connect() as connection:
            task_id = int(connection.execute(query, params).scalar_one())
            connection.commit()
        return task_id
