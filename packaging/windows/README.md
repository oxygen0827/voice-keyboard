# Windows 打包（待实现）

当前状态：**未实现**。源码可在 Windows 上以 `python -m agent.main --no-serial` 直接运行，但尚未打包成独立可执行文件。

## 计划工具栈

- **PyInstaller**（主选）：单文件 .exe 或 onedir 模式
- 安装器：[Inno Setup](https://jrsoftware.org/isinfo.php) 生成 `Voice-Keyboard-Setup.exe`

## 占位结构（实现时填入）

```
packaging/windows/
├── README.md           ← 本文件
├── voice-keyboard.spec ← PyInstaller spec
├── installer.iss       ← Inno Setup 脚本
└── icon.ico
```

## 待解决问题

- 微信 / 钉钉 / 其它 Electron 应用过滤 SendInput Unicode 事件 → 默认 `typing.method: clip`
- 中文键盘右 Alt 名称为 `alt_gr`（非 `alt_r`）
- pynput 全局监听需 UAC 提权？需实测
- VAD（webrtcvad）在 Windows + Python 3.13 暂无预编译，先固定走 PTT 模式
