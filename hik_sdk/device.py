# -*- coding: utf-8 -*-
"""设备登录管理：多台设备去重登录、统一注销。"""
import ctypes
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from hik_sdk import HCNetSDK as hk  # noqa: E402
from hik_sdk.sdk import SdkContext, enc_path  # noqa: E402

logger = logging.getLogger("reckeeper.device")


class LoginError(Exception):
    def __init__(self, ip, port, error_code):
        self.ip = ip
        self.port = port
        self.error_code = error_code
        super().__init__(f"登录设备 {ip}:{port} 失败，错误码={error_code}")


class DevicePool:
    """设备登录池：以 (ip, port) 去重，同一设备只登录一次，多通道共用句柄。"""

    def __init__(self, sdk: SdkContext):
        self.sdk = sdk
        self._users = {}   # (ip, port) -> lUserID
        self._infos = {}   # (ip, port) -> NET_DVR_DEVICEINFO_V40

    def login(self, ip: str, port: int, username: str, password: str) -> int:
        """登录设备，返回 lUserID（已登录则复用）。"""
        key = (ip, int(port))
        if key in self._users:
            return self._users[key]

        info = hk.NET_DVR_USER_LOGIN_INFO()
        info.sDeviceAddress = enc_path(ip)[:128]
        info.wPort = int(port)
        info.sUserName = enc_path(username)[:63]
        info.sPassword = enc_path(password)[:63]
        info.bUseAsynLogin = 0          # 同步登录
        info.byLoginMode = 0            # 0 Private
        info.byUseUTCTime = 0
        dev_info = hk.NET_DVR_DEVICEINFO_V40()
        user_id = self.sdk.dll.NET_DVR_Login_V40(ctypes.byref(info), ctypes.byref(dev_info))
        if user_id < 0:
            code = self.sdk.last_error()
            logger.error("登录设备 %s:%d 失败，错误码=%d", ip, port, code)
            raise LoginError(ip, port, code)
        self._users[key] = user_id
        self._infos[key] = dev_info
        logger.info("登录设备成功 %s:%d -> lUserID=%d（序列号 %s）",
                    ip, port, user_id,
                    bytes(dev_info.struDeviceV30.sSerialNumber).decode("gbk", "ignore").strip("\x00") or "N/A")
        return user_id

    def device_info(self, ip: str, port: int):
        return self._infos.get((ip, int(port)))

    def logout(self, ip: str, port: int):
        key = (ip, int(port))
        uid = self._users.pop(key, None)
        if uid is not None:
            self.sdk.dll.NET_DVR_Logout(uid)
            self._infos.pop(key, None)
            logger.info("注销设备 %s:%d (lUserID=%d)", ip, port, uid)

    def logout_all(self):
        for key, uid in list(self._users.items()):
            self.sdk.dll.NET_DVR_Logout(uid)
            logger.info("注销设备 %s:%d (lUserID=%d)", key[0], key[1], uid)
        self._users.clear()
        self._infos.clear()
