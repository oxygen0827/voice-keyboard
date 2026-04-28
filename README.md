# Voice Keyboard

将语音实时转换为文字，直接输入到电脑任意输入框，并支持语音触发快捷键。

---

## 项目背景

市面上的无线麦克风（发射器 + 接收器）只做到了音频传输这一层。接收器插到电脑上，电脑收到的是音频流，用户还是要自己打字。

这个项目想往前再走几步：

```
传统无线麦克风：  说话 → 接收器 → 电脑听到声音

Voice Keyboard：  说话 → 接收器 → 语音识别 → 文字直接打进输入框
                                             → 特殊指令触发快捷键
```

接收器不再只是音频中转，而是变成一个「语音转键盘」的智能设备。

---

## 整体架构

```
┌─────────────┐    2.4G RF / 蓝牙    ┌──────────────────────────┐
│  无线麦克风  │ ──────────────────▶ │      接收器（ESP32-S3）    │
│   发射器     │                     │                          │
└─────────────┘                     │  ┌─────────────────────┐ │
                                    │  │  语音识别（STT）     │ │
                                    │  │  阿里云 NLS / Whisper│ │
                                    │  └──────────┬──────────┘ │
                                    │             │            │
                                    │  ┌──────────▼──────────┐ │
                                    │  │   USB 复合设备       │ │
                                    │  │  HID（快捷键/英文）  │ │
                                    │  │  CDC 串口（中文）    │ │
                                    │  └──────────┬──────────┘ │
                                    └─────────────┼────────────┘
                                                  │ USB-C
                                    ┌─────────────▼────────────┐
                                    │       PC / Mac / Linux   │
                                    │                          │
                                    │  ┌──────────────────┐   │
                                    │  │   Agent（后台）   │   │
                                    │  │  读串口 → 打字    │   │
                                    │  └──────────────────┘   │
                                    │                          │
                                    │   任意输入框 ← 文字输入  │
                                    └──────────────────────────┘
```

---

## 核心技术选型

### 为什么用 USB HID + CDC 复合设备，而不是纯 HID 键盘

USB HID 键盘协议发送的是**按键码（keycode）**，不是字符。`A` 键有 keycode，`Ctrl` 键有 keycode，但**汉字没有 keycode**。所以纯 HID 键盘无法直接输入中文。

解决方案：让接收器同时呈现两个 USB 接口：

| 接口 | 用途 | 原因 |
|------|------|------|
| HID Keyboard | 快捷键 + 纯英文输入 | 快捷键和 ASCII 字符有标准 keycode |
| CDC 串口 | 中文文字传输 | 串口可以传任意 Unicode 字符串 |

ESP32-S3 原生支持 USB Device 模式，可以同时呈现 HID + CDC，操作系统无需安装额外驱动。

**两种模式自动共存：**
- **未安装 Agent**：纯 HID 模式，英文正常输入，快捷键正常触发
- **已安装 Agent**：HID 负责快捷键，CDC 串口负责中文文字输入

---

### 为什么需要 PC Agent，而不是纯硬件

CDC 串口把文字送到电脑后，还需要一个程序把文字"打进"当前输入框。这件事操作系统提供了专门的 API，比任何硬件模拟都更可靠。

Agent 是一个极小的后台程序（打包后 < 15MB），开机自启，系统托盘常驻，用户感知不到它的存在。第一次运行需要授权一次系统权限，之后永久生效。

---

### 为什么不直接用 pynput.type() 输入中文（macOS）

测试发现，在 macOS 上用 pynput 逐字发送按键事件时，若系统开着中文输入法，英文字母会被输入法拦截转换，导致中英文混排乱码：

```
期望：Voice Keyboard 项目
实际：V里侧Kkeyboard项目
```

根本原因：pynput 发的是键盘事件，会经过系统输入法（IME）处理层。

---

### 三平台打字方案（均已验证）

各平台采用不同的系统级 API，**完全绕过 IME**，逐字输出任意 Unicode 字符：

#### macOS — Quartz CGEvent

```python
evt = Quartz.CGEventCreateKeyboardEvent(src, 0, key_down)
Quartz.CGEventKeyboardSetUnicodeString(evt, len(char), char)
Quartz.CGEventPost(Quartz.kCGHIDEventTap, evt)
```

`CGEventKeyboardSetUnicodeString` 直接把 Unicode 字符写进键盘事件，绕过键盘布局映射和 IME。依赖 `pyobjc-framework-Quartz`（macOS 自带框架绑定，仅在 macOS 上安装）。

#### Windows — SendInput + KEYEVENTF_UNICODE

```python
inp = _INPUT(type=INPUT_KEYBOARD,
             ki=_KEYBDINPUT(wVk=0, wScan=ord(char), dwFlags=KEYEVENTF_UNICODE))
user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(_INPUT))
```

`KEYEVENTF_UNICODE` 标志让 Windows 直接把字符发给当前焦点窗口的消息队列，不经过 IME。通过 `ctypes` 调用 Win32 API，**零额外依赖**。

#### Linux — pynput + X11 XTest

```python
for char in text:
    _kb.type(char)
    time.sleep(0.012)
```

pynput 在 Linux 底层走 X11 XTest 扩展，逐字发送 Unicode 键盘事件，无需额外安装。

---

### 语音识别（STT）选型依据

| 方案 | 延迟 | 中文 | 离线 | 推荐场景 |
|------|------|------|------|---------|
| 阿里云 NLS | 200–400ms | 最优，支持方言 | 否 | 中文为主，生产环境 |
| 腾讯云 ASR | 300–500ms | 优 | 否 | 中文备选 |
| Azure Speech | 300–500ms | 良 | 否 | 国际化场景 |
| Whisper.cpp | < 100ms（本地） | 良 | 是 | 隐私敏感，离线场景 |

当前 MVP 阶段 STT 模块尚未接入，由模拟器替代。

---

## 当前状态

### 已完成

- [x] PC Agent 核心打字模块（macOS / Windows / Linux 三平台逐字输入，均已验证）
- [x] 串口读取模块（自动识别 ESP32 设备，断线自动重连）
- [x] 语音指令 → 快捷键映射（支持运行时注册）
- [x] 开机自启动注册（三平台，`--install` / `--uninstall`）
- [x] ESP32 模拟器（macOS / Linux 无硬件联调）
- [x] 协议设计（`TEXT:` / `CMD:` 串口协议）
- [x] ESP32-S3 固件框架（USB HID + CDC 复合设备 + 路由逻辑）

### 待开发

#### STT 接入
- [ ] 阿里云 NLS 流式语音识别接入（`agent/stt.py`）
- [ ] Whisper.cpp 本地离线方案接入
- [ ] 流式识别边说边出字（partial result 处理）

#### ESP32-S3 固件
- [ ] 无线麦克风接收（2.4G RF 或蓝牙音频）
- [ ] 音频采集与预处理（降噪、增益）
- [ ] Wi-Fi 配网（Captive Portal 或蓝牙配对）
- [ ] 设备状态 LED 指示

#### Agent 完善
- [ ] 快捷键配置文件（`commands.yaml`，用户可自定义）
- [ ] 系统托盘 UI（状态显示、开关控制）
- [ ] Windows 模拟器（pty 替代方案，当前模拟器仅支持 Unix）

#### 打包发布
- [ ] PyInstaller 打包脚本（输出单文件 exe / app）
- [ ] macOS 辅助功能权限引导
- [ ] Windows 代码签名（避免 Defender 误报）

---

## 本地测试

### 环境要求

| 平台 | Python | 系统版本 | 备注 |
|------|--------|---------|------|
| macOS | 3.11+ | macOS 12+ | 需授权辅助功能 |
| Windows | 3.11+ | Windows 10+ | 需通过 UAC 弹窗 |
| Linux | 3.11+ | 主流发行版 | 需 X11 桌面环境 |

> **关于 `python` 命令：** macOS / Linux 系统不一定有 `python` 命令，本项目统一使用虚拟环境内的 Python，无需关心系统命令是否存在。

---

### 第一步：获取代码

```bash
git clone https://github.com/wangqioo/voice-keyboard.git
cd voice-keyboard
```

无法访问 GitHub 时，直接下载 ZIP 解压后进入目录即可。

---

### 第二步：安装依赖

**macOS / Linux：**

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

**Windows（命令提示符）：**

```bat
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
```

> `pyobjc-framework-Quartz` 是 macOS 专属依赖，Windows / Linux 安装时会自动跳过，不影响功能。

---

### macOS 测试

> **首次运行前必须授权辅助功能（只做一次）：**
> 系统设置 → 隐私与安全性 → 辅助功能 → 点击 `+` → 选择「终端」→ 打开开关
>
> 不授权的话程序正常运行，但不会有任何文字输出。

**验证打字模块：**

把光标点进任意输入框（备忘录、浏览器搜索框等），然后运行：

```bash
.venv/bin/python test/test_typing.py
```

等 3 秒，输入框内逐字打出中英文混排文本，并触发一次「保存」快捷键。

**完整串口联调（模拟真实 ESP32）：**

```bash
# 终端 1 — 启动模拟器，记下打印的串口路径
.venv/bin/python test/simulate_device.py

# 示例输出：
# [sim] 虚拟串口: /dev/ttys009
# [sim] 请在另一个终端运行:
# [sim]   python -m agent.main --port /dev/ttys009
```

```bash
# 终端 2 — 路径替换为终端 1 打印的实际值
.venv/bin/python -m agent.main --port /dev/ttys009
```

把光标点进任意输入框，等 3 秒，文字开始逐字打出。

**注册开机自启动：**

```bash
.venv/bin/python -m agent.main --install

# 撤销：
.venv/bin/python -m agent.main --uninstall
```

---

### Windows 测试

> **首次运行会弹出 UAC 授权弹窗**，点「是」即可，只弹一次。
>
> **注意路径分隔符：** Windows 下用反斜杠 `\`，不是 `/`。

**验证打字模块：**

把光标点进任意输入框（记事本、浏览器地址栏等），然后运行：

```bat
.venv\Scripts\python test\test_typing.py
```

等 3 秒，输入框内逐字打出中英文混排文本，并触发一次「保存」快捷键（Ctrl+S）。

**完整串口联调：**

Windows 不支持 `pty` 虚拟串口，有两种替代方式：

- **方式一（推荐）：直接接 ESP32-S3 硬件**，烧录固件后插入 USB，Agent 自动识别连接。
- **方式二：虚拟串口**，安装 [com0com](https://com0com.sourceforge.net/) 创建虚拟 COM 口对，用 PuTTY 或串口调试助手向其中一个口发送 `TEXT:` / `CMD:` 格式数据。

```bat
rem COM 口编号在设备管理器 → 端口 中查看
.venv\Scripts\python -m agent.main --port COM3
```

**注册开机自启动：**

```bat
.venv\Scripts\python -m agent.main --install

rem 撤销：
.venv\Scripts\python -m agent.main --uninstall
```

---

### Linux 测试

> 需要 X11 桌面环境。Wayland 下 pynput XTest 不可用，登录时请选择 X11 会话。

**验证打字模块：**

把光标点进任意输入框，然后运行：

```bash
.venv/bin/python test/test_typing.py
```

等 3 秒，输入框内逐字打出中英文混排文本。

**完整串口联调（步骤与 macOS 完全相同）：**

```bash
# 终端 1
.venv/bin/python test/simulate_device.py
# 示例输出：[sim] 虚拟串口: /dev/pts/3
```

```bash
# 终端 2 — 路径替换为终端 1 打印的实际值
.venv/bin/python -m agent.main --port /dev/pts/3
```

**注册开机自启动（GNOME / KDE 均支持）：**

```bash
.venv/bin/python -m agent.main --install
# 写入 ~/.config/autostart/voice-keyboard.desktop

# 撤销：
.venv/bin/python -m agent.main --uninstall
```

---

## 串口协议

ESP32 通过 CDC 串口向 Agent 发送消息，每条消息一行：

| 格式 | 含义 | 示例 |
|------|------|------|
| `TEXT:<内容>` | 打字输出 | `TEXT:今天天气真不错` |
| `CMD:<指令>` | 触发快捷键 | `CMD:保存` |

固件路由规则：
- `CMD:` → 始终走 HID，无 Agent 也可用
- `TEXT:` 纯 ASCII → 走 HID 直接打，无 Agent 也可用
- `TEXT:` 含中文 → 走 CDC 串口发给 Agent

### 内置指令表

| 指令 | macOS | Windows / Linux |
|------|-------|----------------|
| 截图 | Cmd+Shift+4 | Win+Shift+S |
| 保存 | Cmd+S | Ctrl+S |
| 复制 | Cmd+C | Ctrl+C |
| 粘贴 | Cmd+V | Ctrl+V |
| 撤销 | Cmd+Z | Ctrl+Z |
| 全选 | Cmd+A | Ctrl+A |
| 新标签 | Cmd+T | Ctrl+T |
| 关闭标签 | Cmd+W | Ctrl+W |
| 回车 | Enter | Enter |
| 删除 | Backspace | Backspace |
| 空格 | Space | Space |

---

## ESP32-S3 固件烧录

烧录前在 Arduino IDE 中配置：

| 选项 | 值 |
|------|-----|
| Board | ESP32S3 Dev Module |
| USB Mode | USB-OTG (TinyUSB) |
| USB CDC On Boot | Disabled |
| Upload Mode | UART0 / Hardware CDC |

烧录完成后，通过硬件 UART（TX=GPIO43, RX=GPIO44）发送测试数据验证路由逻辑：

```
TEXT:Hello World    → HID 直接打出（纯 ASCII）
TEXT:你好世界       → CDC 串口转发给 Agent
CMD:保存            → HID 触发 Ctrl+S
```

---

## License

MIT
