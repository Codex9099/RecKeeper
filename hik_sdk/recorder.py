# -*- coding: utf-8 -*-
"""摄像机录像器：实时预览取流 + 客户端录像（对应官方 Demo main.py 功能 2）。

链路（与 Demo 一致，去掉窗口/播放库部分）：
    NET_DVR_RealPlay_V40(hPlayWnd=0, 码流回调) -> NET_DVR_SaveRealData(保存到文件)
    -> NET_DVR_StopSaveRealData + NET_DVR_StopRealPlay
"""
import ctypes
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from hik_sdk import HCNetSDK as hk  # noqa: E402
from hik_sdk.sdk import SdkContext, enc_path  # noqa: E402
from app.config import Camera  # noqa: E402

logger = logging.getLogger("reckeeper.recorder")


class RecordError(Exception):
    """录像操作失败，携带 SDK 错误码。"""

    def __init__(self, action: str, error_code: int):
        self.action = action
        self.error_code = error_code
        super().__init__(f"{action} 失败，SDK 错误码={error_code}")


class CameraRecorder:
    """单个摄像机通道的实时预览 + 录像（后台无界面）。"""

    # 码流回调实例必须保持全局引用，防止被 GC 回收导致回调失效
    _stream_cb = None

    def __init__(self, sdk: SdkContext, user_id: int, camera: Camera):
        self.sdk = sdk
        self.user_id = user_id
        self.camera = camera
        self.real_handle = -1
        self.recording = False
        self.current_file: str = ""

    # ---- 内部 ----
    @staticmethod
    def _on_stream(l_real_handle, dw_data_type, p_buffer, dw_buf_size, p_user):
        """后台录像模式：只取流不处理码流（SDK 仍需回调参数）。"""
        # 若未来需要边录边分析，可在此投递数据到业务队列
        pass

    @classmethod
    def _callback(cls):
        if cls._stream_cb is None:
            cls._stream_cb = hk.REALDATACALLBACK(cls._on_stream)
        return cls._stream_cb

    # ---- 对外 ----
    def start_record(self, filepath: str):
        """建立实时预览并开始客户端录像（等价 Demo: OpenPreview + CaptureVideo）。"""
        if self.recording:
            return True
        preview = hk.NET_DVR_PREVIEWINFO()
        preview.lChannel = self.camera.channel
        preview.dwStreamType = self.camera.stream_type   # 0 主 / 1 子 / 2 三码流
        preview.dwLinkMode = 0                           # 0 TCP
        preview.hPlayWnd = 0                             # 0 = 不显示，仅取流
        preview.bBlocked = 0                             # 非阻塞取流（轮询调度场景，避免失败卡 5s）
        preview.bPassbackRecord = 0

        handle = self.sdk.dll.NET_DVR_RealPlay_V40(
            self.user_id, ctypes.byref(preview), self._callback(), None)
        if handle < 0:
            raise RecordError(f"NET_DVR_RealPlay_V40(摄像机 {self.camera.id} 通道 {self.camera.channel})",
                              self.sdk.last_error())
        self.real_handle = handle

        ok = self.sdk.dll.NET_DVR_SaveRealData(handle, enc_path(filepath))
        if not ok:
            code = self.sdk.last_error()
            self.sdk.dll.NET_DVR_StopRealPlay(handle)
            self.real_handle = -1
            raise RecordError(f"NET_DVR_SaveRealData(摄像机 {self.camera.id} -> {filepath})", code)

        self.recording = True
        self.current_file = filepath
        logger.info("摄像机 %d（%s）开始录像 -> %s", self.camera.id, self.camera.name, filepath)
        return True

    def stop_record(self):
        """停止客户端录像并关闭预览（等价 Demo: CleanRealUp）。"""
        if not self.recording:
            return
        if self.real_handle >= 0:
            self.sdk.dll.NET_DVR_StopSaveRealData(self.real_handle)
            self.sdk.dll.NET_DVR_StopRealPlay(self.real_handle)
        logger.info("摄像机 %d（%s）停止录像 <- %s", self.camera.id, self.camera.name, self.current_file)
        self.real_handle = -1
        self.recording = False
        self.current_file = ""
