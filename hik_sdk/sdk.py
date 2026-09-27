# -*- coding: utf-8 -*-
"""SDK 生命周期管理：加载 DLL、初始化组件路径、Init/Cleanup。"""
import ctypes
import logging
import os
import platform
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from hik_sdk import HCNetSDK as hk  # noqa: E402

logger = logging.getLogger("reckeeper.sdk")

_IS_WINDOWS = platform.system() == "Windows"


def enc_path(path: str) -> bytes:
    """Windows 下 SDK 字符串参数按本地 ANSI(GBK) 编码，Linux 用 UTF-8。"""
    if _IS_WINDOWS:
        return path.encode("gbk", errors="replace")
    return path.encode("utf-8", errors="replace")


class SdkContext:
    """设备网络 SDK 上下文：加载、初始化、清理（进程内唯一）。"""

    def __init__(self, lib_path: str, log_level: int = 3):
        self.lib_path = os.path.abspath(lib_path)
        self.log_level = log_level
        self.dll = None
        self._inited = False

    # ---- 加载与初始化 ----
    def load(self):
        """加载 HCNetSDK.dll 并设置组件/加密库路径（必须在 NET_DVR_Init 前）。"""
        dll_path = os.path.join(self.lib_path, "HCNetSDK.dll")
        if not os.path.isfile(dll_path):
            raise FileNotFoundError(f"找不到 HCNetSDK.dll: {dll_path}")
        self.dll = ctypes.CDLL(dll_path)
        hk.configure_sdk_dll(self.dll)

        # 2=NET_DVR_LOCAL_SDK_PATH 组件库路径（HCNetSDKCom 所在目录）
        sdk_path = hk.NET_DVR_LOCAL_SDK_PATH()
        sdk_path.sPath = enc_path(self.lib_path)
        if not self.dll.NET_DVR_SetSDKInitCfg(2, ctypes.byref(sdk_path)):
            logger.warning("NET_DVR_SetSDKInitCfg(2) 失败，错误码=%d", self.dll.NET_DVR_GetLastError())

        # 3=加密库路径 / 4=ssl 路径（候选文件名兼容 OpenSSL 3 与旧 1_1 包）
        if _IS_WINDOWS:
            crypto_candidates = ["libcrypto-3-x64.dll", "libcrypto-1_1-x64.dll"]
            ssl_candidates = ["libssl-3-x64.dll", "libssl-1_1-x64.dll"]
        else:
            crypto_candidates = ["libcrypto.so.1.1", "libcrypto.so.3"]
            ssl_candidates = ["libssl.so.1.1", "libssl.so.3"]
        crypto = next((os.path.join(self.lib_path, c) for c in crypto_candidates
                       if os.path.isfile(os.path.join(self.lib_path, c))), None)
        ssl = next((os.path.join(self.lib_path, c) for c in ssl_candidates
                    if os.path.isfile(os.path.join(self.lib_path, c))), None)
        if crypto:
            self.dll.NET_DVR_SetSDKInitCfg(3, ctypes.create_string_buffer(enc_path(crypto)))
        if ssl:
            self.dll.NET_DVR_SetSDKInitCfg(4, ctypes.create_string_buffer(enc_path(ssl)))
        logger.info("SDK DLL 加载完成: %s", dll_path)
        return self

    def init(self):
        """初始化 SDK 并开启日志（进程内只调用一次）。"""
        if self._inited:
            return self
        if self.dll is None:
            self.load()
        if not self.dll.NET_DVR_Init():
            raise RuntimeError(f"NET_DVR_Init 失败，错误码={self.dll.NET_DVR_GetLastError()}")
        # 日志（0 不写；1-4 级别递增）
        if self.log_level > 0:
            log_dir = os.path.join(self.lib_path, "..", "SdkLog")
            log_dir = os.path.abspath(log_dir)
            try:
                os.makedirs(log_dir, exist_ok=True)
            except OSError:
                log_dir = self.lib_path
            self.dll.NET_DVR_SetLogToFile(self.log_level, enc_path(log_dir + os.sep), False)
        # 本地通用配置：回放/预览保存文件不切片（0 默认切片 / 1 不切片）
        # 长时间录像默认保持 SDK 自动切片（不设置该字段），此处不强制。
        self._inited = True
        logger.info("SDK 初始化完成 (V6.1.11.30, build 20260805)")
        return self

    def last_error(self) -> int:
        return self.dll.NET_DVR_GetLastError() if self.dll else -1

    def cleanup(self):
        if self.dll is not None and self._inited:
            self.dll.NET_DVR_Cleanup()
            self._inited = False
            logger.info("SDK 已清理")
