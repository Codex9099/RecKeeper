# -*- coding: utf-8 -*-
"""RecKeeper 主服务：组合设备池、录像器与每日时段调度器。

调度线程按 tick 周期检查当前是否处于配置时段：
- 进入时段 -> 为每台启用的摄像机建立预览并开始客户端录像（新文件）
- 退出时段 -> 停止录像、关闭预览
- 失败（设备离线/网络抖动）-> 记录日志，下一 tick 自动重试
"""
import logging
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import Camera, RecKeeperConfig  # noqa: E402
from app.scheduler import DailyScheduler  # noqa: E402
from hik_sdk.device import DevicePool, LoginError  # noqa: E402
from hik_sdk.recorder import CameraRecorder, RecordError  # noqa: E402
from hik_sdk.sdk import SdkContext  # noqa: E402

logger = logging.getLogger("reckeeper.service")


class RecKeeperService:
    def __init__(self, config: RecKeeperConfig, sdk: SdkContext):
        self.config = config
        self.sdk = sdk
        self.device_pool = DevicePool(sdk)
        self.recorders = {}                 # cam_id -> CameraRecorder
        self.scheduler = DailyScheduler(
            periods=config.periods,
            tick_seconds=config.tick_seconds,
        )
        self.scheduler.on_tick = self._on_tick
        self._started = False

    # ---- 生命周期 ----
    def login_all(self):
        """登录所有启用的摄像机所属设备（同一设备去重）。返回失败计数。"""
        fails = 0
        for cam in self.config.enabled_cameras:
            try:
                user_id = self.device_pool.login(cam.ip, cam.port, cam.username, cam.password)
                self.recorders[cam.id] = CameraRecorder(self.sdk, user_id, cam)
            except LoginError as e:
                fails += 1
                logger.error("摄像机 %d（%s）设备登录失败: %s", cam.id, cam.name, e)
        return fails

    def start(self):
        """登录设备并启动调度线程。"""
        if self._started:
            return
        fails = self.login_all()
        if not self.recorders:
            raise RuntimeError("没有可用的摄像机（全部登录失败），请检查配置与网络")
        logger.info("设备登录完成：成功 %d / 失败 %d", len(self.recorders), fails)
        self.scheduler.start()
        self._started = True

    def stop(self):
        """停止调度、停止全部录像、注销设备、释放 SDK。"""
        if self.scheduler:
            self.scheduler.stop()
        for rec in self.recorders.values():
            try:
                rec.stop_record()
            except Exception:  # noqa: BLE001
                logger.exception("停止录像异常")
        self.device_pool.logout_all()
        self.sdk.cleanup()
        self._started = False
        logger.info("RecKeeper 已停止")

    # ---- 调度回调 ----
    def _on_tick(self, in_period: bool):
        for cam in self.config.enabled_cameras:
            rec = self.recorders.get(cam.id)
            if rec is None:
                # 之前登录失败，尝试重新登录
                try:
                    user_id = self.device_pool.login(cam.ip, cam.port, cam.username, cam.password)
                    self.recorders[cam.id] = CameraRecorder(self.sdk, user_id, cam)
                    rec = self.recorders[cam.id]
                except LoginError as e:
                    logger.warning("摄像机 %d 重登失败（下次 tick 再试）: %s", cam.id, e)
                    continue
            try:
                if in_period and not rec.recording:
                    rec.start_record(self._build_path(cam))
                elif not in_period and rec.recording:
                    rec.stop_record()
            except RecordError as e:
                logger.error("摄像机 %d 录像操作异常: %s（下次 tick 重试）", cam.id, e)

    # ---- 路径 ----
    def _build_path(self, cam: Camera) -> str:
        """按 保存目录/日期/cam{id}_{时间}.mp4 组织录像文件。"""
        now = datetime.now()
        day_dir = os.path.join(self.config.save_dir, now.strftime("%Y-%m-%d"))
        os.makedirs(day_dir, exist_ok=True)
        name = cam.name or f"cam{cam.id:02d}"
        return os.path.join(day_dir, f"{name}_{now.strftime('%Y%m%d_%H%M%S')}.mp4")
