# Voice Keyboard

Voice Keyboard 是一个本地优先的语音键盘效率工具。它把语音转成当前输入框里的文字，也可以把语音当成指令来执行文本编辑、快捷键、窗口操作、应用启动和记忆库操作。

这个项目的核心目标不是做一个聊天机器人，而是让用户用语音更快地完成“输入、修改、操作电脑”这些键盘相关工作。

## 当前状态

当前仓库已经支持 Windows 客户端的主要使用流程，并保留 macOS 相关适配代码。Windows 侧已经重点补齐了托盘、主窗口、快捷键配置、语言切换、历史记录、记忆库和 AI 意图反馈等能力。

当前还在继续建设 AI 意图训练闭环：客户端会采集意图判断样本，训练服务可以接收和标注样本，后续会基于真实数据训练更快、更准的本地意图模型。

阶段性开发说明见：

- [docs/stage-development-plan.md](docs/stage-development-plan.md)
- [docs/intent-training-server.md](docs/intent-training-server.md)
- [docs/intent-training.md](docs/intent-training.md)

## 主要功能

### 语音转文字

- 按住语音转文字热键后说话。
- 识别完成后，把文字输入到当前光标所在位置。
- 支持原文模式。
- 支持微润色模式。
- 支持本地状态提示。

### AI 指令模式

- 按住 AI 功能热键后说出指令。
- 支持文本修改、续写、删除、总结等文本操作。
- 支持常用快捷键调用。
- 支持应用启动。
- 支持窗口操作。
- 支持记忆库读取、保存、删除和列表。
- 支持更细的处理中状态提示。

### Windows 托盘和主窗口

- 托盘菜单支持打开主窗口。
- 支持中文和英文界面切换。
- 托盘菜单会跟随语言设置切换。
- 支持语音转文字热键配置。
- 支持 AI 功能热键配置。
- 支持语音转文字开关。
- 支持原文/微润色模式切换。
- 支持开机自启动注册和取消。
- 支持历史记录、记忆库、快捷键等配置入口。
- 托盘操作会通过提示框反馈结果。

### 记忆库

记忆库用于保存短文本片段，例如邮箱、地址、常用话术等。

它不是聊天记忆，也不是用户画像系统。它只负责保存、读取、删除用户明确提供的文本片段。

### AI 意图训练闭环

当前已经搭好基础框架：

- 客户端采集本地意图判断样本。
- 上传工具把样本上传到训练服务器。
- 训练服务器保存样本。
- 服务端支持人工标注。
- 后续可基于已标注样本训练本地意图模型。

## 安装

需要 Python 3.11 或更高版本。

```powershell
git clone https://github.com/wangqioo/voice-keyboard.git
cd voice-keyboard
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
copy config.yaml.example config.yaml
```

macOS 或 Linux：

```bash
git clone https://github.com/wangqioo/voice-keyboard.git
cd voice-keyboard
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp config.yaml.example config.yaml
```

然后编辑 `config.yaml`，配置语音识别和大模型服务。

运行时也可以使用用户目录配置：

```text
~/.voice-keyboard/config.yaml
```

如果该文件存在，会优先于仓库内的 `config.yaml`。

## 启动客户端

### Windows 源码启动

企业电脑如果不能运行未授信 EXE，建议使用源码方式启动。

```powershell
.\.venv\Scripts\python -m agent.main --no-serial
```

不显示主窗口，用于调试：

```powershell
.\.venv\Scripts\python -u -m agent.main --no-serial --no-ui
```

列出麦克风设备：

```powershell
.\.venv\Scripts\python -m agent.main --list-devices
```

### macOS / Linux

```bash
.venv/bin/python -m agent.main --no-serial
```

列出麦克风设备：

```bash
.venv/bin/python -m agent.main --list-devices
```

macOS 需要授予必要系统权限：

- 麦克风权限
- 辅助功能权限
- 输入监听权限

## 配置说明

主要配置文件是 `config.yaml`。

常见字段：

- `stt`：语音转文字使用的语音识别配置。
- `ai_stt`：AI 指令模式可选的独立语音识别配置。
- `polish_stt`：微润色相关语音识别配置。
- `llm`：AI 指令、润色、改写、生成文本使用的大模型配置。
- `audio`：录音模式、热键、麦克风、VAD 等设置。
- `typing`：文字输入和快捷键执行相关设置。

常见热键配置示例：

```yaml
audio:
  mode: ptt
  ptt_key: shift_r
  ai_key: alt_r
  device: auto
```

真实 API-Key 不应该提交到仓库。建议通过本地配置、环境变量或企业密钥管理系统注入。

## 训练服务

训练服务用于收集和标注意图识别样本，为后续训练本地意图模型做准备。

安装服务端依赖：

```powershell
pip install -r requirements-server.txt
```

启动训练服务：

```powershell
$env:INTENT_TRAINING_DATABASE_URL = "sqlite:///./intent_training.db"
$env:INTENT_TRAINING_UPLOAD_TOKEN = "change-me"
uvicorn training_server.api:app --host 0.0.0.0 --port 8000
```

上传本地样本：

```powershell
python tools/upload_intent_samples.py --server http://SERVER:8000 --token change-me
```

只检查样本数量，不上传：

```powershell
python tools/upload_intent_samples.py --dry-run
```

更多说明见 [docs/intent-training-server.md](docs/intent-training-server.md)。

## 命令行模式

无桌面环境或 SSH 环境可以使用 headless CLI。它只录音并输出识别结果，不会输入到当前输入框。

```powershell
.\.venv\Scripts\python -m agent.cli --list-devices
.\.venv\Scripts\python -m agent.cli --once
.\.venv\Scripts\python -m agent.cli --once --seconds 5
.\.venv\Scripts\python -m agent.cli --loop
```

macOS / Linux：

```bash
.venv/bin/python -m agent.cli --list-devices
.venv/bin/python -m agent.cli --once
.venv/bin/python -m agent.cli --once --seconds 5
.venv/bin/python -m agent.cli --loop
```

## 运行测试

Windows：

```powershell
python -m unittest discover -s test
python -m compileall -q agent training_server tools test
```

macOS / Linux：

```bash
scripts/test-local.sh
python -m compileall -q agent training_server tools test
```

部分测试需要系统权限、真实输入框或可用的桌面环境，日常开发优先跑非交互式单元测试。

## 打包和发布

平台打包文件位于：

- `packaging/windows/`
- `packaging/macos/`
- `packaging/linux/`

企业电脑可能无法运行未授信 EXE。正式发布时建议走企业可信发布或签名流程。

## 后续开发方向

当前最重要的后续工作：

1. 完成样本标注后台。
2. 积累真实意图判断样本。
3. 增加样本导出和训练数据集生成。
4. 训练第一版本地意图模型。
5. 把本地模型接回 Windows 客户端。
6. 持续优化托盘、主窗口、快捷键和记忆库配置体验。

详细路线见 [docs/stage-development-plan.md](docs/stage-development-plan.md)。

## 许可证

MIT
