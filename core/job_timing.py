"""Small monotonic timing helper for job instrumentation."""

from __future__ import annotations

from dataclasses import dataclass
from time import monotonic
from typing import Callable


Clock = Callable[[], float]


@dataclass
class TimingStep:
    name: str
    started_at: float
    ended_at: float | None = None
    status: str = "running"


class JobTiming:
    def __init__(self, clock: Clock = monotonic):
        self._clock = clock
        self._started_at = clock()
        self._steps: list[TimingStep] = []

    def start_step(self, name: str) -> TimingStep:
        step = TimingStep(name=name, started_at=self._clock())
        self._steps.append(step)
        return step

    def end_step(self, step: TimingStep, status: str = "completed") -> TimingStep:
        if step.ended_at is None:
            step.ended_at = self._clock()
            step.status = status
        return step

    def fail_step(self, step: TimingStep) -> TimingStep:
        return self.end_step(step, status="failed")

    def summary(self) -> dict:
        now = self._clock()
        return {
            "total_duration_seconds": _seconds(now - self._started_at),
            "steps": [self._step_summary(step, now) for step in self._steps],
        }

    def _step_summary(self, step: TimingStep, now: float) -> dict:
        ended_at = step.ended_at
        end_offset = None if ended_at is None else _seconds(ended_at - self._started_at)
        duration_end = now if ended_at is None else ended_at
        return {
            "name": step.name,
            "status": step.status,
            "start_seconds": _seconds(step.started_at - self._started_at),
            "end_seconds": end_offset,
            "duration_seconds": _seconds(duration_end - step.started_at),
        }


def _seconds(value: float) -> float:
    return round(max(0.0, value), 6)
