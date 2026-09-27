# RecKeeper

海康威视设备网络 SDK 后台录像保存服务（无界面、按每日时段自动保存摄像机视频）。

- 纯 Python 标准库（ctypes 调用 HCNetSDK.dll），无第三方依赖
- 后台运行，无 GUI；命令行启动，支持少量必要参数
- 设备登录信息存放在 JSON 配置文件，支持 1~8 台摄像机
- 录像链路与官方 Demo（`main.py` 功能 2）一致：`NET_DVR_RealPlay_V40` 取流 + `NET_DVR_SaveRealData` 客户端录像
- 保存路径按 日期目录 组织；每日录像时间段可配置（支持多段、跨天）

## 目录结构

```
RecKeeper/
├── main.py                # 入口（命令行参数：--config / --log-level / --check）
├── config.json            # 配置文件（8 台摄像机 + 全局配置）
├── config.example.json    # 配置示例（多时段）
├── README.md
├── hik_sdk/               # SDK 封装层
│   ├── HCNetSDK.py        #   ctypes 结构体/常量/回调（官方 Demo 派生 + 函数签名声明）
│   ├── sdk.py             #   SDK 生命周期：DLL 加载、组件路径、Init/Cleanup
│   ├── device.py          #   设备登录池（同设备去重登录）
│   └── recorder.py        #   摄像机录像器（RealPlay + SaveRealData）
├── app/
│   ├── config.py          # JSON 配置加载与校验
│   ├── scheduler.py       # 每日时段调度器（多段/跨天，时钟可注入）
│   └── service.py         # 主服务（登录 + 调度线程 + 录像切换）
├── tests/                 # 单元测试（配置校验、调度器）
├── recordings/            # 录像输出（运行自动生成：recordings/日期/cam01_时间.mp4）
└── logs/                  # 运行日志（reckeeper.log）
```

## 快速开始

### 0. SDK 运行库部署（依据 Demo《请先看这里》注意事项）

程序通过 `sdk.lib_path` 直接引用海康 SDK 的【库文件】目录（`config.json` 已配置），启动时自动校验目录完整性：

- **必需（缺失即报错）**：`HCNetSDK.dll`、`HCCore.dll`、`HCNetSDKCom\` 文件夹、`hlog.dll`、`hpr.dll`、`zlib1.dll`、加密库 `libcrypto-3-x64.dll` / `libssl-3-x64.dll`（旧包为 `-1_1-` 版本，二选一即可）
- **约束**：`HCNetSDKCom` 文件夹必须与 `HCNetSDK.dll`、`HCCore.dll` 在同一目录，**文件夹名不可修改**
- **非必需（缺失仅告警）**：`PlayCtrl.dll`、`SuperRender.dll`、`AudioRender.dll`、`libmmd.dll`、`NPQos.dll` 等（后台纯录像链路用不到，涉及预览显示/播放库才需要）

> 提示：程序始终用绝对路径加载 DLL（`ctypes.CDLL`）并通过 `NET_DVR_SetSDKInitCfg(2/3/4)` 显式指定组件与加密库路径，避免误加载系统 `Windows\System32` 下的旧版 `HCNetSDK.dll`。
> 若自行部署后发现功能异常且未指定加载路径，可尝试在程序运行时删除 `HCNetSDK.dll`：能删掉说明程序误用了 System32 下的同名旧库，应清理该目录下的相关 dll。

### 1. 修改配置 `config.json`

```jsonc
{
  "sdk": { "lib_path": "E:\\...\\HCNetSDKV6.1.11.30_build20260805_Win64_ZH\\库文件" },
  "recording": {
    "save_dir": "E:\\works\\2030\\RecKeeper\\recordings",
    "periods": [
      { "start": "00:00", "end": "23:59" }          // 全天；可多段：{"start":"08:00","end":"12:00"}, ...
    ]
  },
  "cameras": [
    { "id": 1, "name": "cam01", "ip": "192.168.1.101", "port": 8000,
      "username": "admin", "password": "真实密码", "channel": 1,
      "stream_type": 0, "enabled": true },
    // ... 最多 8 台；同一台 NVR 多通道：ip/port/user 相同，channel 不同
  ]
}
```

- `stream_type`：`0` 主码流（清晰、文件大）/ `1` 子码流（省带宽、文件小）/ `2` 三码流
- 多路 NVR：把多台摄像机的 `ip/port/username` 配成同一台 NVR、`channel` 配成不同通道号即可（程序自动去重登录）

### 2. 检查配置与设备连通性（不录像）

```bat
python main.py --config config.json --check
```

会加载配置、初始化 SDK、登录全部设备并打印每台的登录结果与设备序列号，然后退出。
返回码：`0` 全部登录成功，`2` 有失败，`1` 配置/SDK 错误。

### 3. 正式运行（后台）

```bat
python main.py --config config.json            :: 前台运行，Ctrl+C 退出
python main.py --config config.json --log-level DEBUG

:: Windows 无控制台窗口后台运行
pythonw main.py --config config.json
:: 或
start /b python main.py --config config.json
```

## 配置项说明

| 配置 | 说明 | 默认 |
|---|---|---|
| `sdk.lib_path` | HCNetSDK.dll 所在目录（须含 HCCore.dll 与 HCNetSDKCom 文件夹） | 必填 |
| `sdk.log_level` | SDK 自身日志级别：0 无 / 1 错误 / 2 警告 / 3 信息 / 4 调试 | 3 |
| `recording.save_dir` | 录像保存根目录 | 必填 |
| `recording.periods` | 每日录像时段数组，`HH:MM` 格式；支持跨天（如 22:00-06:00） | 必填 |
| `log_dir` | 运行日志目录 | logs |
| `tick_seconds` | 调度检查周期（秒），进入/退出时段的最长响应延迟 | 15 |
| `cameras[]` | 摄像机数组（1~8 台）：id 唯一、ip/port/username/password/channel/stream_type/enabled | 必填 |

## 录像文件说明

- 目录：`<save_dir>/<YYYY-MM-DD>/<cam_name>_<YYYYMMDD_HHMMSS>.mp4`
  （例：`recordings/2026-09-28/cam01_20260928_080000.mp4`）
- 格式：PS 封装（H.264/H.265，随设备主/子码流），与 Demo 的 `NET_DVR_SaveRealData` 一致；
  单文件超过 1024MB 时 SDK 自动切片（追加 `_1`、`_2` 后缀）
- 每进入一个时段生成一个新文件；退出时段自动停止保存

## 常见问题

- **登录失败错误码 7/10**：IP 或端口错误（SDK 用设备服务端口 8000，不是网页 80）
- **错误码 1**：用户名或密码错误；连续多次错误设备会锁定 IP（错误码 153，需重启设备或等待解锁）
- **错误码 52**：设备登录用户数达到上限（频繁启停程序导致），等旧会话超时释放
- **错误码 107~114**：`HCNetSDKCom` 组件缺失或与 DLL 不在同目录
- 无界面运行时不加载播放库（PlayCtrl.dll），仅依赖 HCNetSDK.dll + HCCore.dll + HCNetSDKCom

## 测试

```bat
python -m unittest discover -s tests -v          :: 单元测试（配置校验、时段判定、调度器）
python tests\smoke_struct_sizes.py               :: 结构体与 C 头文件对齐校验
```

- 单元测试覆盖：配置校验（缺项/越界/时段格式/8 台上限）、时段判定（多段、跨天、边界）、调度器 tick
- 结构体校验覆盖：登录/预览/设备信息/回放/查找等 13 个关键结构体的 sizeof 与 `HCNetSDK.h` 对齐
  （框架已修正官方 Python Demo 中 `NET_DVR_VOD_PARA`、`NET_DVR_FILECOND_V50` 两处字段类型错误）
