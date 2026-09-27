# -*- coding: utf-8 -*-
"""RecKeeper 配置加载与校验。

配置文件为 JSON，结构：
{
  "sdk":       {"lib_path": "...", "log_level": 3},
  "recording": {"save_dir": "...", "periods": [{"start":"00:00","end":"08:00"}, ...]},
  "cameras":   [ {"id":1, "name":"cam01", "ip":"...", "port":8000,
                  "username":"admin", "password":"...", "channel":1,
                  "stream_type":0, "enabled":true}, ... ]   # 1~8 台
}
"""
import json
import os
import re

from dataclasses import dataclass, field
from typing import List

TIME_RE = re.compile(r"^(?P<h>\d{1,2}):(?P<m>\d{2})$")

# 依据《请先看这里：Demo内容说明和注意事项.txt》与库文件目录核实的依赖清单：
# critical 缺失即报错；recommended 缺失仅告警（不影响基础预览/录像链路）
SDK_CRITICAL_FILES = ["HCNetSDK.dll", "HCCore.dll", "HCNetSDKCom"]
SDK_CRITICAL_DLLS = ["hlog.dll", "hpr.dll", "zlib1.dll"]
# 加密库二选一（OpenSSL 3 为当前版本，1_1 为旧包）
SDK_CRYPTO_CANDIDATES = ["libcrypto-3-x64.dll", "libcrypto-1_1-x64.dll"]
SDK_SSL_CANDIDATES = ["libssl-3-x64.dll", "libssl-1_1-x64.dll"]
# 推荐但非必需（播放/渲染/扩展组件，后台纯录像链路用不到）
SDK_RECOMMENDED_DLLS = [
    "PlayCtrl.dll", "SuperRender.dll", "AudioRender.dll",
    "libmmd.dll", "libsafefunc.dll", "NPQos.dll", "HXVA.dll",
    "HmMerge.dll", "MP_Render.dll", "OpenAL32.dll", "GdiPlus.dll",
]


class ConfigError(Exception):
    """配置不合法。"""


@dataclass
class Period:
    """每日录像时段（支持跨天，如 22:00-06:00）。"""
    start: str  # "HH:MM"
    end: str    # "HH:MM"

    def __post_init__(self):
        self.start_min = _to_minutes(self.start)
        self.end_min = _to_minutes(self.end)
        if self.start_min == self.end_min:
            raise ConfigError(f"时段 {self.start}-{self.end} 开始与结束时间不能相同")


@dataclass
class Camera:
    id: int
    name: str
    ip: str
    port: int
    username: str
    password: str
    channel: int
    stream_type: int = 0   # 0 主码流 / 1 子码流 / 2 三码流
    enabled: bool = True


@dataclass
class RecKeeperConfig:
    sdk_lib_path: str          # HCNetSDK.dll 所在目录
    save_dir: str              # 录像保存根目录
    periods: List[Period]
    cameras: List[Camera]
    sdk_log_level: int = 3     # 0 无 / 1 错误 / 2 警告 / 3 信息 / 4 调试
    tick_seconds: int = 15     # 调度检查周期（秒）
    log_dir: str = "logs"      # 运行日志目录（相对项目根或绝对路径）
    camera_count_limit: int = 8
    sdk_warnings: List[str] = field(default_factory=list)  # SDK 目录非必需文件缺失提示

    @property
    def enabled_cameras(self) -> List[Camera]:
        return [c for c in self.cameras if c.enabled]


def _to_minutes(hhmm: str) -> int:
    m = TIME_RE.match(hhmm.strip())
    if not m:
        raise ConfigError(f"时间格式错误: {hhmm!r}，应为 HH:MM（如 08:00、23:59）")
    h, mi = int(m.group("h")), int(m.group("m"))
    if h > 23 or mi > 59:
        raise ConfigError(f"时间越界: {hhmm!r}（小时 0-23，分钟 0-59）")
    return h * 60 + mi


def _require(d: dict, key: str, default=None):
    if key not in d or d[key] is None:
        if default is not None:
            return default
        raise ConfigError(f"缺少必需配置项: {key}")
    return d[key]


def load_config(path: str) -> RecKeeperConfig:
    """加载并校验配置文件。"""
    if not os.path.isfile(path):
        raise ConfigError(f"配置文件不存在: {path}")
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except json.JSONDecodeError as e:
        raise ConfigError(f"配置文件 JSON 解析失败: {e}") from e
    if not isinstance(raw, dict):
        raise ConfigError("配置文件顶层必须是 JSON 对象")

    # ---- sdk 段 ----
    sdk = _require(raw, "sdk", {}) or {}
    if not isinstance(sdk, dict):
        raise ConfigError("sdk 段必须是对象")
    lib_path = _require(sdk, "lib_path")
    if not os.path.isdir(lib_path):
        raise ConfigError(f"SDK 库目录不存在: {lib_path}")
    warnings = []

    def _present(name):
        return os.path.exists(os.path.join(lib_path, name))

    # 1) 必需：主库 + 核心库 + 组件文件夹（HCNetSDKCom 文件夹名不可修改，须与 DLL 同目录）
    missing = [f for f in SDK_CRITICAL_FILES if not _present(f)]
    if missing:
        raise ConfigError(
            f"SDK 库目录缺少必需文件/目录: {missing}；"
            f"HCNetSDKCom 文件夹须与 HCNetSDK.dll、HCCore.dll 同目录且不可改名（目录: {lib_path}）")
    # 2) 必需：文档点名的依赖库（hlog/hpr/zlib1）
    missing = [f for f in SDK_CRITICAL_DLLS if not _present(f)]
    if missing:
        raise ConfigError(f"SDK 库目录缺少必需依赖库: {missing}（目录: {lib_path}）")
    # 3) 必需（二选一）：OpenSSL 加密库（libcrypto/libssl）
    if not any(_present(f) for f in SDK_CRYPTO_CANDIDATES):
        raise ConfigError(
            f"SDK 库目录缺少加密库: {SDK_CRYPTO_CANDIDATES} 任一（目录: {lib_path}）")
    if not any(_present(f) for f in SDK_SSL_CANDIDATES):
        raise ConfigError(
            f"SDK 库目录缺少加密库: {SDK_SSL_CANDIDATES} 任一（目录: {lib_path}）")
    # 4) 推荐：非必需组件（后台纯录像链路用不到，缺失仅告警）
    missing = [f for f in SDK_RECOMMENDED_DLLS if not _present(f)]
    if missing:
        warnings.append(f"SDK 库目录缺少非必需组件: {missing}（预览显示/播放库相关功能可能受限）")
    sdk_log_level = int(_require(sdk, "log_level", 3))
    if sdk_log_level not in (0, 1, 2, 3, 4):
        raise ConfigError("sdk.log_level 取值 0-4")

    # ---- recording 段 ----
    rec = _require(raw, "recording", {}) or {}
    if not isinstance(rec, dict):
        raise ConfigError("recording 段必须是对象")
    save_dir = _require(rec, "save_dir")
    try:
        os.makedirs(save_dir, exist_ok=True)
    except OSError as e:
        raise ConfigError(f"无法创建录像保存目录 {save_dir}: {e}") from e
    periods_raw = _require(rec, "periods")
    if not isinstance(periods_raw, list) or not periods_raw:
        raise ConfigError("recording.periods 必须是至少包含一个时段的数组")
    periods = []
    for p in periods_raw:
        if not isinstance(p, dict) or "start" not in p or "end" not in p:
            raise ConfigError(f"时段配置格式错误: {p!r}，应为 {{\"start\":\"HH:MM\",\"end\":\"HH:MM\"}}")
        periods.append(Period(str(p["start"]), str(p["end"])))

    # ---- cameras 段 ----
    cameras_raw = _require(raw, "cameras")
    if not isinstance(cameras_raw, list) or not cameras_raw:
        raise ConfigError("cameras 必须是包含至少一台摄像机的数组")
    if len(cameras_raw) > 8:
        raise ConfigError(f"最多支持 8 台摄像机，当前配置 {len(cameras_raw)} 台")
    cameras: List[Camera] = []
    seen_ids = set()
    for i, c in enumerate(cameras_raw):
        if not isinstance(c, dict):
            raise ConfigError(f"cameras[{i}] 必须是对象")
        cam = Camera(
            id=int(_require(c, "id")),
            name=str(_require(c, "name", f"cam{int(_require(c, 'id')):02d}")),
            ip=str(_require(c, "ip")),
            port=int(_require(c, "port", 8000)),
            username=str(_require(c, "username", "admin")),
            password=str(_require(c, "password", "")),
            channel=int(_require(c, "channel", 1)),
            stream_type=int(_require(c, "stream_type", 0)),
            enabled=bool(_require(c, "enabled", True)),
        )
        if cam.id in seen_ids:
            raise ConfigError(f"摄像机 id 重复: {cam.id}")
        seen_ids.add(cam.id)
        if cam.port < 1 or cam.port > 65535:
            raise ConfigError(f"摄像机 {cam.id} 端口越界: {cam.port}")
        if cam.channel < 1:
            raise ConfigError(f"摄像机 {cam.id} 通道号必须 >= 1")
        if cam.stream_type not in (0, 1, 2):
            raise ConfigError(f"摄像机 {cam.id} stream_type 取值 0(主)/1(子)/2(三码流)")
        cameras.append(cam)
    if not any(c.enabled for c in cameras):
        raise ConfigError("至少需要一台 enabled=true 的摄像机")

    # ---- 其他 ----
    tick = int(_require(raw, "tick_seconds", 15))
    if tick < 5:
        raise ConfigError("tick_seconds 不能小于 5 秒")
    log_dir = str(_require(raw, "log_dir", "logs"))

    return RecKeeperConfig(
        sdk_lib_path=lib_path,
        save_dir=save_dir,
        periods=periods,
        cameras=cameras,
        sdk_log_level=sdk_log_level,
        tick_seconds=tick,
        log_dir=log_dir,
        sdk_warnings=warnings,
    )
