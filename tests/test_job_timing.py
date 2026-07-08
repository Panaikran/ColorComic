import json
import unittest

from core.job_timing import JobTiming


class FakeClock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


class JobTimingTests(unittest.TestCase):
    def test_records_completed_step_duration(self):
        clock = FakeClock()
        timing = JobTiming(clock=clock)

        step = timing.start_step("PDF export")
        clock.advance(1.25)
        timing.end_step(step)

        summary = timing.summary()

        self.assertEqual(summary["steps"][0]["name"], "PDF export")
        self.assertEqual(summary["steps"][0]["status"], "completed")
        self.assertEqual(summary["steps"][0]["duration_seconds"], 1.25)
        self.assertEqual(summary["steps"][0]["end_seconds"], 1.25)

    def test_summary_handles_running_step_without_end_time(self):
        clock = FakeClock()
        timing = JobTiming(clock=clock)

        timing.start_step("model load")
        clock.advance(2.5)

        step = timing.summary()["steps"][0]

        self.assertEqual(step["status"], "running")
        self.assertIsNone(step["end_seconds"])
        self.assertEqual(step["duration_seconds"], 2.5)

    def test_failed_step_is_marked_and_ended(self):
        clock = FakeClock()
        timing = JobTiming(clock=clock)

        step = timing.start_step("page 1 colorization")
        clock.advance(0.5)
        timing.fail_step(step)

        summary = timing.summary()

        self.assertEqual(summary["steps"][0]["status"], "failed")
        self.assertEqual(summary["steps"][0]["duration_seconds"], 0.5)

    def test_summary_is_json_serializable(self):
        timing = JobTiming(clock=FakeClock())
        timing.start_step("preflight")

        json.dumps(timing.summary())


if __name__ == "__main__":
    unittest.main()
