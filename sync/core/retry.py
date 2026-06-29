"""Tiện ích retry cho các thao tác IO dễ lỗi tạm thời."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import TypeVar

from .config import RetryPolicy


T = TypeVar("T")


def run_with_retry(
    operation: Callable[[], T],
    policy: RetryPolicy,
    *,
    label: str,
    logger: logging.Logger | None = None,
    retryable: Callable[[Exception], bool] | None = None,
) -> T:
    """Run an operation with a fixed-delay retry policy."""
    active_logger = logger or logging.getLogger(__name__)
    last_error: Exception | None = None

    for attempt in range(1, policy.attempts + 1):
        try:
            return operation()
        except Exception as exc:
            last_error = exc
            should_retry = retryable(exc) if retryable else True
            if attempt >= policy.attempts or not should_retry:
                raise
            active_logger.warning(
                "%s failed on attempt %s/%s: %s. Retrying in %ss.",
                label,
                attempt,
                policy.attempts,
                exc,
                policy.delay_seconds,
            )
            if policy.delay_seconds > 0:
                time.sleep(policy.delay_seconds)

    raise RuntimeError(f"{label} failed") from last_error
