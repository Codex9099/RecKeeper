# -*- coding: utf-8 -*-
"""RecKeeper 命令行入口：后台录像服务（无界面）。

用法：
    python main.py --config config.json                  # 常规启动
    python main.py --config config.json --check          # 校验配置并测试登录后退出
    python main.py --config config.json --log-level DEBUG

后台化（Windows）：
    pythonw main.py --config config.json                 # 无控制台窗口运行
    start /b python main.py --config config.json         # 后台运行
"""
import argparse
import logging
import os
import sys
import time

from app.config import ConfigError, load_config
from app.service import RecKeeperService
from hik_sdk.sdk import SdkContext

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
LOG_LEVELS = {"DEBUG": logging.DEBUG, "INFO": logging.INFO,
              "WARNING": logging.WARNING, "ERROR": logging.ERROR}


def setup_logging(log_dir: str, level: int, check_mode: bool = False):
    os.makedirs(log_dir, exist_ok=True)
    handlers = [logging.StreamHandler()]
    if not check_mode:  # --check 只输出到控制台
        handlers.append(logging.FileHandler(
            os.path.join(log_dir, "reckeeper.log"), encoding="utf-8"))
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=handlers,
    )


def parse_args(argv=None):
    p = argparse.ArgumentParser(
        prog="RecKeeper",
        description="海康威视设备网络SDK 后台录像保存服务（无界面，按每日时段自动录像）",
    )
    p.add_argument("--config", default=os.path.join(PROJECT_ROOT, "config.json"),
                   help="配置文件路径（默认 ./config.json）")
    p.add_argument("--log-level", choices=list(LOG_LEVELS), default="INFO",
                   help="日志级别（默认 INFO）")
    p.add_argument("--check", action="store_true",
                   help="校验配置并测试登录全部设备后退出（不录像）")
    return p.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    cfg = None
    sdk = None
    service = None
    try:
        # 1. 加载配置
        cfg = load_config(args.config)
        setup_logging(cfg.log_dir, LOG_LEVELS[args.log_level], check_mode=args.check)
        log = logging.getLogger("reckeeper.main")
        log.info("RecKeeper 启动，配置文件=%s", os.path.abspath(args.config))
        log.info("录像保存目录=%s，每日时段=%s，摄像机=%d 台（启用 %d）",
                 cfg.save_dir,
                 ", ".join(f"{p.start}-{p.end}" for p in cfg.periods),
                 len(cfg.cameras), len(cfg.enabled_cameras))
        for w in cfg.sdk_warnings:
            log.warning("%s", w)

        # 2. 初始化 SDK
        sdk = SdkContext(cfg.sdk_lib_path, cfg.sdk_log_level).init()

        # 3. 服务
        service = RecKeeperService(cfg, sdk)
        if args.check:
            fails = service.login_all()
            log.info("--- 登录检查结果 ---")
            for cam in cfg.enabled_cameras:
                rec = service.recorders.get(cam.id)
                info = service.device_pool.device_info(cam.ip, cam.port)
                if rec is not None and info is not None:
                    serial = bytes(info.struDeviceV30.sSerialNumber).decode("gbk", "ignore").strip("\x00")
                    log.info("摄像机 %d（%s）%s:%d 登录成功，lUserID=%d，序列号=%s",
                             cam.id, cam.name, cam.ip, cam.port, rec.user_id, serial or "N/A")
                else:
                    log.info("摄像机 %d（%s）%s:%d 登录失败", cam.id, cam.name, cam.ip, cam.port)
            log.info("登录检查完成：成功 %d / 失败 %d", len(service.recorders), fails)
            return 0 if fails == 0 else 2

        # 4. 正常启动：登录 + 调度线程
        service.start()
        log.info("RecKeeper 运行中（Ctrl+C 退出）...")
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logging.getLogger("reckeeper.main").info("收到 Ctrl+C，正在退出...")
    except ConfigError as e:
        logging.getLogger("reckeeper.main").error("配置错误: %s", e)
        return 1
    except Exception as e:  # noqa: BLE001
        logging.getLogger("reckeeper.main").exception("启动失败: %s", e)
        return 1
    finally:
        if service is not None:
            try:
                service.stop()
            except Exception:  # noqa: BLE001
                logging.getLogger("reckeeper.main").exception("停止服务异常")
        elif sdk is not None:
            try:
                sdk.cleanup()
            except Exception:  # noqa: BLE001
                pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
