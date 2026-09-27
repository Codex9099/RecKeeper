# -*- coding: utf-8 -*-
"""每日录像时段调度器。

- 支持一天内多个时段（如 08:00-12:00、14:00-18:00）
- 支持跨天时段（如 22:00-06:00，表示前一日 22 点到当日 6 点）
- 时钟可注入（now_func），便于单元测试与模拟
"""
import logging
import threading
import time
from datetime import datetime
from typing import Callable, List, Optional

from app.config import Period

logger = logging.getLogger("reckeeper.scheduler")


def in_any_period(dt: datetime, periods: List[Period]) -> bool:
    """判断 dt 的时分是否落在任意一个时段内（含跨天时段）。"""
    cur = dt.hour * 60 + dt.minute
    for p in periods:
        s, e = p.start_min, p.end_min
        if s <= e:                      # 当天时段
            if s <= cur < e:
                return True
        else:                           # 跨天时段，如 22:00-06:00
            if cur >= s or cur < e:
                return True
    return False


class DailyScheduler:
    """轮询式每日调度器：每秒/每 tick 检查一次当前是否处于录像时段。"""

    def __init__(self, periods: List[Period],
                 now_func: Optional[Callable[[], datetime]] = None,
                 tick_seconds: int = 15):
        self.periods = periods
        self.now_func = now_func or (lambda: datetime.now())
        self.tick_seconds = max(1, int(tick_seconds))
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def should_record(self) -> bool:
        return in_any_period(self.now_func(), self.periods)

    def start(self):
        """后台启动调度线程（不阻塞）。"""
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, name="reckeeper-scheduler", daemon=True)
        self._thread.start()
        logger.info("调度器已启动，时段=%s，检查周期=%ds",
                    ", ".join(f"{p.start}-{p.end}" for p in self.periods), self.tick_seconds)

    def _run(self):
        while not self._stop_event.is_set():
            try:
                self.on_tick(self.should_record())
            except Exception:  # noqa: BLE001
                logger.exception("调度 tick 执行异常")
            self._stop_event.wait(self.tick_seconds)

    def on_tick(self, in_period: bool):
        """子类覆写：每个检查周期回调，in_period 表示当前是否在录像时段。"""

    def stop(self):
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=self.tick_seconds + 5)
            self._thread = None
        logger.info("调度器已停止")
