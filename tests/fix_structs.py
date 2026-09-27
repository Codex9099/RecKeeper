# -*- coding: utf-8 -*-
"""修正 HCNetSDK.py 中两个与 C 头文件不一致的结构体定义（官方 Demo 的 bug）。"""
import io

PATH = r"E:\works\2030\RecKeeper\hik_sdk\HCNetSDK.py"

with open(PATH, "r", encoding="utf-8") as f:
    src = f.read()

# ---- 1. NET_DVR_VOD_PARA：byDrawFrame 应为 BYTE(1)，dwFileIndex 应为 DWORD(4)，
#        并补充 byUseAsyn 字段，byRes2[19] 与头文件一致，总大小 160 ----
old_vod = """        ("hWnd", c_uint32),
        ("byDrawFrame", c_uint64),  # 0:不抽帧，1：抽帧
        ("byVolumeType", c_uint32),  # 0-普通录像卷  1-存档卷
        ("byVolumeNum", c_ubyte),  # 卷号，目前指存档卷号
        ("byStreamType", c_ubyte),  # 码流类型 0-主码流， 1-子码流，2-码流三
        ("dwFileIndex", c_ubyte),  # 存档卷上的录像文件索引，搜索存档卷录像时返回的值
        ("byAudioFile", c_ubyte),  # 音频文件0-否，1-是
        ("byCourseFile", c_ubyte),  # 课程文件0-否，1-是
        ("byDownload", c_ubyte),  # 是否下载 0-否，1-是
        ("byOptimalStreamType", c_ubyte),  # 是否按最优码流类型回放 0-否，1-是（对于双码流设备，某一段时间内的录像文件与指定码流类型不同，则返回实际码流类型的录像）
        ("byRes2", c_ubyte * 20),  # 预留
    ]"""
new_vod = """        ("hWnd", c_uint32),
        ("byDrawFrame", c_ubyte),  # 0:不抽帧，1：抽帧（修正：原 Demo 误用 c_uint64）
        ("byVolumeType", c_ubyte),  # 0-普通录像卷  1-存档卷（修正：原 Demo 误用 c_uint32）
        ("byVolumeNum", c_ubyte),  # 卷号，目前指存档卷号
        ("byStreamType", c_ubyte),  # 码流类型 0-主码流， 1-子码流，2-码流三
        ("dwFileIndex", c_uint32),  # 存档卷上的录像文件索引（修正：原 Demo 误用 c_ubyte）
        ("byAudioFile", c_ubyte),  # 音频文件0-否，1-是
        ("byCourseFile", c_ubyte),  # 课程文件0-否，1-是
        ("byDownload", c_ubyte),  # 是否下载 0-否，1-是
        ("byOptimalStreamType", c_ubyte),  # 是否按最优码流类型回放 0-否，1-是（对于双码流设备，某一段时间内的录像文件与指定码流类型不同，则返回实际码流类型的录像）
        ("byUseAsyn", c_ubyte),  # 0-使用同步IO，1-使用异步IO（与头文件一致）
        ("byRes2", c_ubyte * 19),  # 预留
    ]"""
assert old_vod in src, "VOD_PARA 旧文本未找到"
src = src.replace(old_vod, new_vod)

# ---- 2. NET_DVR_FILECOND_V50：byRes[20] 应为 byRes[252]（总大小 424）----
old_fc = """        ("dwTimeout", c_uint32),  # 预留
        ("byRes", c_ubyte * 20),  # 预留
    ]"""
new_fc = """        ("dwTimeout", c_uint32),  # 预留
        ("byRes", c_ubyte * 252),  # 预留（修正：原 Demo 误用 20，正确 252）
    ]"""
assert old_fc in src, "FILECOND_V50 旧文本未找到"
src = src.replace(old_fc, new_fc)

with open(PATH, "w", encoding="utf-8", newline="") as f:
    f.write(src)

print("修正完成")
