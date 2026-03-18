from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Optional


UTC = timezone.utc


def utc_now() -> datetime:
    """返回当前 UTC 时间。"""
    return datetime.now(tz=UTC)


def ensure_utc(value: datetime) -> datetime:
    """规范化为 UTC aware datetime。"""
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


@dataclass(slots=True)
class CookieRefreshTask:
    """数据库中的浏览器状态刷新任务。"""

    task_id: int
    site_url: str
    reload_url: str
    state_scope_url: str
    storage_state: Optional[bytes]
    session_storage: Optional[bytes]
    next_poll_at: datetime
    refresh_interval_seconds: int = 86400
    retry_interval_seconds: int = 900
    headless: bool = True
    browser_channel: str = "chrome"
    enabled: bool = True
    wait_until: str = "networkidle"
    settle_time_ms: int = 3000
    remark: str = ""
    last_refreshed_at: Optional[datetime] = None
    last_error: str = ""

    def due_at(self, base_time: Optional[datetime] = None) -> bool:
        """判断任务是否已到期。"""
        compare_time = ensure_utc(base_time or utc_now())
        return ensure_utc(self.next_poll_at) <= compare_time

    def next_success_time(self, base_time: Optional[datetime] = None) -> datetime:
        """成功后的下次刷新时间。"""
        anchor = ensure_utc(base_time or utc_now())
        return anchor + timedelta(seconds=self.refresh_interval_seconds)

    def next_retry_time(self, base_time: Optional[datetime] = None) -> datetime:
        """失败后的下次重试时间。"""
        anchor = ensure_utc(base_time or utc_now())
        return anchor + timedelta(seconds=self.retry_interval_seconds)

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "CookieRefreshTask":
        """从数据库记录构造任务对象。"""
        return cls(
            task_id=int(row["id"]),
            site_url=str(row["site_url"]),
            reload_url=str(row.get("reload_url") or row["site_url"]),
            state_scope_url=str(row.get("state_scope_url") or row["site_url"]),
            storage_state=row.get("storage_state"),
            session_storage=row.get("session_storage"),
            next_poll_at=ensure_utc(_coerce_datetime(row["next_poll_at"])),
            refresh_interval_seconds=int(row.get("refresh_interval_seconds") or 86400),
            retry_interval_seconds=int(row.get("retry_interval_seconds") or 900),
            headless=bool(row.get("headless", 1)),
            browser_channel=str(row.get("browser_channel") or "chrome"),
            enabled=bool(row.get("enabled", 1)),
            wait_until=str(row.get("wait_until") or "networkidle"),
            settle_time_ms=int(row.get("settle_time_ms") or 3000),
            remark=str(row.get("remark") or ""),
            last_refreshed_at=_coerce_optional_datetime(row.get("last_refreshed_at")),
            last_error=str(row.get("last_error") or ""),
        )


def _coerce_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        text = value.strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        return datetime.fromisoformat(text)
    raise TypeError(f"Unsupported datetime value: {value!r}")


def _coerce_optional_datetime(value: Any) -> Optional[datetime]:
    if value in (None, ""):
        return None
    return ensure_utc(_coerce_datetime(value))
