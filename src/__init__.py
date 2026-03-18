"""Public package exports for watchdog-browser."""

from .db import TaskRepository
from .state import storage_state_to_cookie_header, storage_state_to_headers


def build_headers_for_task(task_id: int) -> dict[str, str]:
    """Load one task from database and build HTTP headers from storage cookies."""
    repository = TaskRepository()
    return repository.build_headers_for_task(task_id)


__all__ = [
    "TaskRepository",
    "build_headers_for_task",
    "storage_state_to_cookie_header",
    "storage_state_to_headers",
]
