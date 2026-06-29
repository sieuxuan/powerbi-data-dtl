from __future__ import annotations

import unittest

from core.config import RetryPolicy
from core.retry import run_with_retry


class RetryTests(unittest.TestCase):
    def test_run_with_retry_succeeds_after_transient_failures(self) -> None:
        attempts = {"count": 0}

        def operation() -> str:
            attempts["count"] += 1
            if attempts["count"] < 3:
                raise RuntimeError("temporary")
            return "ok"

        result = run_with_retry(operation, RetryPolicy(attempts=3, delay_seconds=0), label="test")

        self.assertEqual(result, "ok")
        self.assertEqual(attempts["count"], 3)

    def test_run_with_retry_stops_on_non_retryable_error(self) -> None:
        attempts = {"count": 0}

        def operation() -> str:
            attempts["count"] += 1
            raise ValueError("bad input")

        with self.assertRaises(ValueError):
            run_with_retry(
                operation,
                RetryPolicy(attempts=3, delay_seconds=0),
                label="test",
                retryable=lambda exc: not isinstance(exc, ValueError),
            )

        self.assertEqual(attempts["count"], 1)


if __name__ == "__main__":
    unittest.main()
