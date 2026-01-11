from __future__ import annotations

from apps.worker.main import get_worker_status


def test_worker_status_line() -> None:
    assert get_worker_status() == "worker alive"
