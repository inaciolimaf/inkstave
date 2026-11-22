"""The sweep intervals in settings drive the worker's ARQ cron schedule.

HISTORY_COMPACT_INTERVAL_S and NOTIFICATION_SWEEP_INTERVAL_S used to be read by nothing;
the cron minutes are now derived from them with the same rule as the retention sweep.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from inkstave.modules.history.versions.jobs import compact_history
from inkstave.modules.notifications.inbox.jobs import sweep_notifications


def _settings(**overrides: int) -> Any:
    values = {
        "compile_retention_sweep_s": 3600,
        "history_compact_interval_s": 300,
        "notification_sweep_interval_s": 3600,
    }
    return SimpleNamespace(**(values | overrides))


def _cron_jobs(settings: Any) -> list[Any]:
    # Imported here: the worker reads the settings at import, after the test environment is set.
    from inkstave import worker

    return worker._cron_jobs(settings)


def _minutes_for(jobs: list[Any], coroutine: Any) -> set[int]:
    matches = [job for job in jobs if job.coroutine is coroutine]
    assert len(matches) == 1
    return set(matches[0].minute)


def test_defaults_keep_the_five_minute_compaction_and_the_hourly_sweep() -> None:
    jobs = _cron_jobs(_settings())
    assert _minutes_for(jobs, compact_history) == set(range(0, 60, 5))
    assert _minutes_for(jobs, sweep_notifications) == {0}


def test_history_compact_interval_sets_the_compaction_minutes() -> None:
    jobs = _cron_jobs(_settings(history_compact_interval_s=900))
    assert _minutes_for(jobs, compact_history) == {0, 15, 30, 45}


def test_notification_sweep_interval_sets_the_sweep_minutes() -> None:
    jobs = _cron_jobs(_settings(notification_sweep_interval_s=1800))
    assert _minutes_for(jobs, sweep_notifications) == {0, 30}
