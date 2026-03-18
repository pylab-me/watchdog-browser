import unittest
from datetime import timedelta

from src.models import utc_now
from src.refresher import compute_sleep_hint, MAX_SLEEP_SECONDS


class SchedulerTest(unittest.TestCase):
    def test_due_task_should_run_immediately(self) -> None:
        now = utc_now()
        self.assertEqual(compute_sleep_hint(now - timedelta(seconds=1), now), 0.0)

    def test_sleep_should_not_exceed_15_minutes(self) -> None:
        now = utc_now()
        value = compute_sleep_hint(now + timedelta(days=1), now)
        self.assertEqual(value, float(MAX_SLEEP_SECONDS))


if __name__ == "__main__":
    unittest.main()
