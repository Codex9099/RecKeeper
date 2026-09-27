# -*- coding: utf-8 -*-
"""每日时段调度器单元测试（含跨天、多段、边界、注入时钟）。"""
import unittest
from datetime import datetime, timedelta

from app.config import Period
from app.scheduler import DailyScheduler, in_any_period


def dt(h, m, s=0):
    return datetime(2026, 9, 28, h, m, s)


class TestInAnyPeriod(unittest.TestCase):
    def setUp(self):
        self.day = [Period("08:00", "12:00"), Period("14:00", "18:00")]
        self.overnight = [Period("22:00", "06:00")]

    def test_single_period_hit(self):
        self.assertTrue(in_any_period(dt(9, 0), [Period("08:00", "12:00")]))

    def test_single_period_miss(self):
        self.assertFalse(in_any_period(dt(13, 0), [Period("08:00", "12:00")]))

    def test_start_inclusive_end_exclusive(self):
        self.assertTrue(in_any_period(dt(8, 0), [Period("08:00", "12:00")]))
        self.assertFalse(in_any_period(dt(12, 0), [Period("08:00", "12:00")]))

    def test_multi_period(self):
        self.assertTrue(in_any_period(dt(15, 30), self.day))
        self.assertFalse(in_any_period(dt(13, 0), self.day))

    def test_overnight_late(self):
        self.assertTrue(in_any_period(dt(23, 0), self.overnight))
        self.assertTrue(in_any_period(dt(23, 59), self.overnight))

    def test_overnight_early(self):
        self.assertTrue(in_any_period(dt(0, 0), self.overnight))
        self.assertTrue(in_any_period(dt(5, 59), self.overnight))

    def test_overnight_miss(self):
        self.assertFalse(in_any_period(dt(12, 0), self.overnight))

    def test_overnight_boundary(self):
        self.assertTrue(in_any_period(dt(22, 0), self.overnight))
        self.assertFalse(in_any_period(dt(6, 0), self.overnight))

    def test_overnight_mixed_with_day(self):
        periods = [Period("22:00", "06:00"), Period("08:00", "12:00")]
        self.assertTrue(in_any_period(dt(10, 0), periods))
        self.assertTrue(in_any_period(dt(3, 0), periods))
        self.assertFalse(in_any_period(dt(7, 0), periods))


class FakeClock:
    """可前进的假时钟。"""

    def __init__(self, start: datetime):
        self.now_value = start

    def now(self):
        return self.now_value

    def advance(self, seconds):
        self.now_value += timedelta(seconds=seconds)


class TestDailyScheduler(unittest.TestCase):
    def test_should_record_with_fake_clock(self):
        clock = FakeClock(dt(9, 0))
        sched = DailyScheduler([Period("08:00", "12:00")], now_func=clock.now, tick_seconds=15)
        self.assertTrue(sched.should_record())
        clock.advance(4 * 3600)
        self.assertFalse(sched.should_record())
        clock.now_value = dt(10, 30)
        self.assertTrue(sched.should_record())

    def test_on_tick_fired_until_stop(self):
        ticks = []
        clock = FakeClock(dt(9, 0))
        sched = DailyScheduler([Period("08:00", "12:00")], now_func=clock.now, tick_seconds=1)
        sched.on_tick = lambda in_period: ticks.append(in_period)
        sched.start()
        try:
            import time
            time.sleep(0.4)
        finally:
            sched.stop()
        self.assertGreaterEqual(len(ticks), 1)
        self.assertTrue(all(ticks))

    def test_stop_idempotent(self):
        sched = DailyScheduler([Period("00:00", "23:59")], tick_seconds=1)
        sched.start()
        sched.stop()
        sched.stop()  # 二次停止不报错


if __name__ == "__main__":
    unittest.main()
