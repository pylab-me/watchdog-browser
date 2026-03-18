# watchdog-browser

`watchdog-browser` refreshes browser auth state from websites with Playwright and stores the latest state back into PostgreSQL.

It is not cookie-only. The project persists:

- cookies
- localStorage
- IndexedDB
- sessionStorage

The main storage format is Playwright `storageState`, plus a separate `session_storage` snapshot because `sessionStorage` is not covered by `storage_state()` by default.

## Core Flow

For each task, the worker does this:

1. Load `storage_state + session_storage` from PostgreSQL
2. Restore them into a fresh temporary Playwright browser context
3. Open `site_url`
4. Wait for the page to settle
5. Visit `reload_url` or fallback to `site_url`
6. Wait again
7. Capture the latest `storageState + sessionStorage`
8. Compress and write them back to the database

All Playwright runs use a temporary user data directory.

## Main Features

- Postgres-backed task scheduler
- 1-day refresh interval by default
- 15-minute retry interval by default
- Manual bootstrap flow for the first task
- `remark` field for task notes
- Helper to convert stored cookies into HTTP headers

## Installation

```bash
python -m pip install build
python -m build --wheel
python -m pip install dist\watchdog_browser-0.1.0-py3-none-any.whl
```

## Package API

```python
from watchdog_browser import TaskRepository, build_headers_for_task

repo = TaskRepository()
headers = repo.build_headers_for_task(123)

headers2 = build_headers_for_task(123)
```

Example result:

```python
{"Cookie": "sid=abc; uid=42"}
```

## CLI

Bootstrap the first task:

```bash
watchdog-browser-bootstrap --site-url https://example.com
```

Run the worker:

```bash
watchdog-browser-worker
```

You can also run locally without installation:

```bash
python bootstrap_task.py --site-url https://example.com
python run_worker.py
```

## Database

The task table is defined in [schema.sql](/M:/CodeHub/watchdog-browser/schema.sql).

Important fields:

- `site_url`
- `reload_url`
- `state_scope_url`
- `storage_state`
- `session_storage`
- `remark`
- `next_poll_at`

## Build Automation

GitHub Actions workflow: [.github/workflows/build-wheel.yml](/M:/CodeHub/watchdog-browser/.github/workflows/build-wheel.yml)

It will:

- build a wheel
- install the built wheel
- verify `from watchdog_browser import TaskRepository, build_headers_for_task`
- upload the wheel artifact
