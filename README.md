# Voice Keyboard

Voice Keyboard 是一个本地优先的语音键盘引擎。它的目标不是聊天，而是把语音变成当前电脑里的文字输入或键盘操作：听写、改写选中文字、触发快捷键、打开应用、切换窗口、调用备忘短语等。

当前你正在使用的稳定方案是：

- 本项目：`/Users/hushaohong/vibe-coding/voice-keyboard`
- 硬件固件项目：`/Users/hushaohong/vibe-coding/nRF52840-optimization`
- 固件目录：`/Users/hushaohong/vibe-coding/nRF52840-optimization/firmware/PsyGuardVoiceKeyboard/`
- 不再使用：`PdmBleAudioOptimized` 实验固件
- XIAO 稳定配置：`trim_silence: false`、`normalize_gain: false`

## 现在怎么打开应用

在终端运行：

```bash
cd /Users/hushaohong/vibe-coding/voice-keyboard
scripts/run-local.sh --background --ui
tail -f .local/logs/voice-keyboard-local.log
```

这三行的意思：

- 第一行进入项目目录。
- 第二行在后台启动 Voice Keyboard，并显示 macOS 右上角菜单栏 `VK` 图标。
- 第三行实时查看日志，方便确认 BLE、热键和识别状态。

如果只想启动应用、不看日志，运行：

```bash
cd /Users/hushaohong/vibe-coding/voice-keyboard
scripts/run-local.sh --background --ui
```

停止应用：

```bash
cd /Users/hushaohong/vibe-coding/voice-keyboard
scripts/run-local.sh --kill-only
```

查看是否正在运行：

```bash
cd /Users/hushaohong/vibe-coding/voice-keyboard
scripts/run-local.sh --status
```

查看最近日志：

```bash
cd /Users/hushaohong/vibe-coding/voice-keyboard
tail -n 80 .local/logs/voice-keyboard-local.log
```

正常启动后，日志里应该能看到：

```text
[ptt] XIAO 音频处理 trim_silence=off normalize_gain=off
[ui] 菜单栏 + 主窗口已就绪（点击右上角 VK 麦克风图标）
[xiao] BLE 已连接，等待热键开始录音
```

如果日志一直显示：

```text
[xiao] 未找到 XIAO/PsyGuard BLE 设备，请确认固件在广播
```

先检查 XIAO 板子是否通电、是否已经刷入 `PsyGuardVoiceKeyboard` 固件、是否被 Arduino 串口或上传流程占用。

## 当前稳定配置

你的用户配置文件在：

```text
/Users/hushaohong/.voice-keyboard/config.yaml
```

当前稳定配置应包含：

```yaml
audio:
  mode: ptt
  ptt_key: shift_r
  ai_key: alt_r
  toggle_key: f8
  device: xiao_ble
  xiao_ble:
    trim_silence: false
    normalize_gain: false
```

说明：

- `ptt_key: shift_r`：按住右 Shift 说话，松开后识别并输入。
- `ai_key: alt_r`：按住右 Option/Alt 说 Instruction Mode 指令。
- `toggle_key: f8`：临时启停录音。
- `device: xiao_ble`：使用 XIAO nRF52840 BLE 麦克风。
- `trim_silence: false`：不自动裁剪首尾，避免短句开头被误切。
- `normalize_gain: false`：不自动增益，避免放大 BLE 噪声。

## 硬件固件

当前稳定固件只使用：

```text
/Users/hushaohong/vibe-coding/nRF52840-optimization/firmware/PsyGuardVoiceKeyboard/PsyGuardVoiceKeyboard.ino
```

Arduino IDE 烧录建议：

1. 打开 `PsyGuardVoiceKeyboard.ino`
2. Board 按实物选择，例如 `XIAO nRF52840 Plus`
3. Port 选择 `/dev/cu.usbmodem...`
4. 点击 Upload
5. 上传完成后再启动 Voice Keyboard

不要再刷 `PdmBleAudioOptimized`。这个实验固件已经从硬件项目里删除，当前 Voice Keyboard Engine 稳定路径不使用它。

## 常用命令

列出麦克风设备：

```bash
cd /Users/hushaohong/vibe-coding/voice-keyboard
.venv/bin/python -m agent.main --list-devices
```

前台运行，方便调试：

```bash
cd /Users/hushaohong/vibe-coding/voice-keyboard
.venv/bin/python -u -m agent.main --no-serial
```

无菜单栏运行：

```bash
cd /Users/hushaohong/vibe-coding/voice-keyboard
.venv/bin/python -u -m agent.main --no-serial --no-ui
```

检查 macOS 权限：

```bash
cd /Users/hushaohong/vibe-coding/voice-keyboard
scripts/run-local.sh --permissions
```

macOS 权限说明：从源码运行时，系统设置里的麦克风、辅助功能、输入监控权限通常授予 Terminal/iTerm/Python；打包 App 运行时才授予 `Voice Keyboard.app`。

## 配置文件

仓库里的示例配置：

```text
config.yaml.example
```

你的个人配置：

```text
~/.voice-keyboard/config.yaml
```

如果个人配置存在，它会优先生效。

常见配置段：

- `stt`：Dictation Mode 的语音识别 provider。
- `ai_stt`：Instruction Mode 可选的独立语音识别 provider。
- `polish_stt`：微润色听写可选的独立语音识别 provider。
- `llm`：Instruction Mode、改写、微润色、生成文字使用的模型 provider。
- `audio`：录音模式、热键、麦克风设备、XIAO BLE 设置。
- `typing`：文字插入方式。
- `correction_memory`：本地听写纠错记忆。
- `instruction_mode`：指令识别、本地覆盖、备忘触发词、训练同步等。

敏感信息不要提交到 git。API key 放在个人 `config.yaml`、`.env` 或环境变量里。

## Headless CLI

只录音并打印识别结果，不往当前输入框打字：

```bash
cd /Users/hushaohong/vibe-coding/voice-keyboard
.venv/bin/python -m agent.cli --once
.venv/bin/python -m agent.cli --once --seconds 5
.venv/bin/python -m agent.cli --loop
```

## 开发与测试

运行本地测试：

```bash
cd /Users/hushaohong/vibe-coding/voice-keyboard
scripts/test-local.sh
```

常用聚焦测试：

```bash
cd /Users/hushaohong/vibe-coding/voice-keyboard
pytest test/test_capture_path.py test/test_runtime_composition.py
pytest test/test_correction_memory.py test/test_screen_ocr_capture.py
```

编译检查：

```bash
cd /Users/hushaohong/vibe-coding/voice-keyboard
python -m compileall -q agent training_server tools test
```

## 项目文档

- [Agent guide](AGENTS.md)
- [Ubiquitous language](UBIQUITOUS_LANGUAGE.md)
- [Current stage plan](docs/stage-development-plan.md)
- [Intent training](docs/intent-training.md)
- [Intent training server](docs/intent-training-server.md)

## 当前结论

当前效果较好的稳定基线是：

```text
PsyGuardVoiceKeyboard 固件
device: xiao_ble
trim_silence: false
normalize_gain: false
scripts/run-local.sh --background --ui
```

后续如果识别效果变差，优先检查是否偏离了这条基线。

## License

MIT
