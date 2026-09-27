# -*- coding: utf-8 -*-
"""配置加载与校验的单元测试。"""
import json
import os
import tempfile
import unittest

from app.config import ConfigError, Period, load_config

VALID_SDK_LIB = r"E:\works\2030\海康威视SDK\HCNetSDKV6.1.11.30_build20260805_Win64_ZH\库文件"


def make_cfg(tmp, n_cams=8, periods=None, **overrides):
    cameras = [
        {"id": i + 1, "name": f"cam{i+1:02d}", "ip": f"192.168.1.{101+i}",
         "port": 8000, "username": "admin", "password": "pw",
         "channel": 1, "stream_type": 0, "enabled": True}
        for i in range(n_cams)
    ]
    cfg = {
        "sdk": {"lib_path": VALID_SDK_LIB, "log_level": 3},
        "recording": {"save_dir": os.path.join(tmp, "rec"), "periods": periods if periods is not None else [{"start": "00:00", "end": "23:59"}]},
        "cameras": cameras,
    }
    cfg.update(overrides)
    p = os.path.join(tmp, "config.json")
    with open(p, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False)
    return p


class TestConfigLoad(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="reckeeper_test_")

    def test_valid_8_cameras(self):
        cfg = load_config(make_cfg(self.tmp))
        self.assertEqual(len(cfg.cameras), 8)
        self.assertEqual(len(cfg.enabled_cameras), 8)
        self.assertEqual(cfg.periods[0].start_min, 0)
        self.assertEqual(cfg.periods[0].end_min, 1439)

    def test_missing_sdk_lib_path(self):
        with self.assertRaises(ConfigError):
            load_config(make_cfg(self.tmp, sdk={"log_level": 3}))

    def test_sdk_lib_path_not_exist(self):
        with self.assertRaises(ConfigError):
            load_config(make_cfg(self.tmp, sdk={"lib_path": r"Z:\not_exist"}))

    def test_no_periods(self):
        with self.assertRaises(ConfigError):
            load_config(make_cfg(self.tmp, periods=[]))

    def test_bad_period_format(self):
        with self.assertRaises(ConfigError):
            load_config(make_cfg(self.tmp, periods=[{"start": "25:00", "end": "23:59"}]))

    def test_period_start_equals_end(self):
        with self.assertRaises(ConfigError):
            load_config(make_cfg(self.tmp, periods=[{"start": "08:00", "end": "08:00"}]))

    def test_too_many_cameras(self):
        with self.assertRaises(ConfigError):
            load_config(make_cfg(self.tmp, n_cams=9))

    def test_duplicate_camera_id(self):
        cfg = make_cfg(self.tmp)
        with open(cfg, "r", encoding="utf-8") as f:
            raw = json.load(f)
        raw["cameras"][1]["id"] = 1
        with open(cfg, "w", encoding="utf-8") as f:
            json.dump(raw, f, ensure_ascii=False)
        with self.assertRaises(ConfigError):
            load_config(cfg)

    def test_all_disabled(self):
        cfg = make_cfg(self.tmp)
        with open(cfg, "r", encoding="utf-8") as f:
            raw = json.load(f)
        for c in raw["cameras"]:
            c["enabled"] = False
        with open(cfg, "w", encoding="utf-8") as f:
            json.dump(raw, f, ensure_ascii=False)
        with self.assertRaises(ConfigError):
            load_config(cfg)

    def test_bad_channel(self):
        with self.assertRaises(ConfigError):
            load_config(make_cfg(self.tmp, cameras=[
                {"id": 1, "ip": "1.2.3.4", "channel": 0}]))

    def test_bad_stream_type(self):
        with self.assertRaises(ConfigError):
            load_config(make_cfg(self.tmp, cameras=[
                {"id": 1, "ip": "1.2.3.4", "stream_type": 5}]))

    def test_overnight_period_ok(self):
        p = Period("22:00", "06:00")
        self.assertEqual((p.start_min, p.end_min), (22 * 60, 6 * 60))


def build_sdk_dir(base, extra_files=None, missing=None, include_recommended=True):
    """构造一个完整的 SDK 目录（校验只查存在性，文件内容可为空）。"""
    d = os.path.join(base, "sdk_min")
    os.makedirs(os.path.join(d, "HCNetSDKCom"), exist_ok=True)
    required = ["HCNetSDK.dll", "HCCore.dll", "hlog.dll", "hpr.dll", "zlib1.dll",
                "libcrypto-3-x64.dll", "libssl-3-x64.dll"]
    if include_recommended:
        required += ["PlayCtrl.dll", "SuperRender.dll", "AudioRender.dll",
                     "libmmd.dll", "libsafefunc.dll", "NPQos.dll", "HXVA.dll",
                     "HmMerge.dll", "MP_Render.dll", "OpenAL32.dll", "GdiPlus.dll"]
    for f in required:
        if not missing or f not in missing:
            open(os.path.join(d, f), "wb").close()
    for f in (extra_files or []):
        open(os.path.join(d, f), "wb").close()
    return d


class TestSdkDirIntegrity(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="reckeeper_sdk_")

    def test_minimal_complete_dir_ok(self):
        lib = build_sdk_dir(self.tmp)
        cfg = load_config(make_cfg(self.tmp, sdk={"lib_path": lib}))
        self.assertEqual(cfg.sdk_lib_path, lib)
        self.assertEqual(cfg.sdk_warnings, [])   # 无告警

    def test_missing_critical_component(self):
        lib = build_sdk_dir(self.tmp, missing=["HCNetSDKCom", "hlog.dll"])
        with self.assertRaises(ConfigError):
            load_config(make_cfg(self.tmp, sdk={"lib_path": lib}))

    def test_missing_crypto_lib(self):
        lib = build_sdk_dir(self.tmp, missing=["libcrypto-3-x64.dll", "libcrypto-1_1-x64.dll"])
        with self.assertRaises(ConfigError):
            load_config(make_cfg(self.tmp, sdk={"lib_path": lib}))

    def test_missing_ssl_lib(self):
        lib = build_sdk_dir(self.tmp, missing=["libssl-3-x64.dll", "libssl-1_1-x64.dll"])
        with self.assertRaises(ConfigError):
            load_config(make_cfg(self.tmp, sdk={"lib_path": lib}))

    def test_missing_recommended_only_warns(self):
        lib = build_sdk_dir(self.tmp, include_recommended=False)  # 无 PlayCtrl 等推荐组件
        cfg = load_config(make_cfg(self.tmp, sdk={"lib_path": lib}))
        self.assertTrue(any("非必需组件" in w for w in cfg.sdk_warnings))


if __name__ == "__main__":
    unittest.main()
