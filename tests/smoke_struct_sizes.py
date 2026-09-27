# -*- coding: utf-8 -*-
"""冒烟校验：验证 HCNetSDK.py 关键结构体大小与 C 头文件对齐（不加载 DLL）。"""
import ctypes
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from hik_sdk import HCNetSDK as hk

# 对照 HCNetSDK.h（本 SDK 版本）核实的 sizeof（64 位、默认对齐）
EXPECT = {
    "NET_DVR_USER_LOGIN_INFO": 416,
    "NET_DVR_PREVIEWINFO": 280,
    "NET_DVR_DEVICEINFO_V30": 80,
    "NET_DVR_DEVICEINFO_V40": 344,
    "NET_DVR_LOCAL_SDK_PATH": 384,
    "NET_DVR_LOCAL_GENERAL_CFG": 256,
    "NET_DVR_TIME": 24,
    "NET_DVR_STREAM_INFO": 72,
    "NET_DVR_VOD_PARA": 160,
    "NET_DVR_FILECOND_V50": 424,
    "NET_DVR_FINDDATA_V50": 572,
    "NET_DVR_PLAYCOND": 116,
    "NET_DVR_ALARMER": 372,
}

fails = 0
for name, expected in EXPECT.items():
    cls = getattr(hk, name, None)
    if cls is None:
        print(f"[MISS] {name}")
        fails += 1
        continue
    size = ctypes.sizeof(cls)
    status = "OK " if size == expected else "BAD"
    if size != expected:
        fails += 1
    print(f"[{status}] {name}: sizeof={size} (期望 {expected})")

# 校验回调类型可实例化
for cb_name in ("REALDATACALLBACK", "PLAYBACKCALLBACK"):
    cb = getattr(hk, cb_name)
    inst = cb(lambda *a: None)
    print(f"[OK ] {cb_name} 可实例化: {inst}")

print("RESULT:", "ALL PASS" if fails == 0 else f"{fails} FAILURES")
sys.exit(1 if fails else 0)
