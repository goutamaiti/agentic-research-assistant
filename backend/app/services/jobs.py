"""Minimal background job execution for long-running analysis.

A single worker thread processes jobs in order, which is enough for a local, one-user
prototype and keeps SQLite writes serialised. Job state lives in ``processing_runs``, so
an interrupted job is detected on the next start (see ``AnalysisService.recover``).
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Protocol

logger = logging.getLogger(__name__)


class JobRunner(Protocol):
    def submit(self, fn: Callable[..., Any], *args: Any) -> None: ...

    def shutdown(self) -> None: ...


class ThreadJobRunner:
    def __init__(self) -> None:
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="analysis")

    def submit(self, fn: Callable[..., Any], *args: Any) -> None:
        future = self._executor.submit(fn, *args)
        future.add_done_callback(_log_unexpected_failure)

    def shutdown(self) -> None:
        # Queued jobs are cancelled; their runs are marked interrupted on next startup.
        self._executor.shutdown(wait=False, cancel_futures=True)


class InlineJobRunner:
    """Runs jobs synchronously. Used by tests for deterministic behaviour."""

    def submit(self, fn: Callable[..., Any], *args: Any) -> None:
        fn(*args)

    def shutdown(self) -> None:
        return None


def _log_unexpected_failure(future: Any) -> None:
    if not future.cancelled() and future.exception() is not None:
        logger.error("Background job crashed", exc_info=future.exception())
