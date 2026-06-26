# Linux 打包（待实现）

当前状态：**未实现**。源码可在 Linux（X11 会话）上以 `.venv/bin/python -m agent.main --no-serial` 直接运行，但尚未打包成可分发产物。

## 计划工具栈

- **AppImage**（首选）：单文件、不依赖发行版包管理器
- 备选：`.deb` (debian/ubuntu) / `.rpm` (fedora) / Flatpak

## 占位结构（实现时填入）

```
packaging/linux/
├── README.md         ← 本文件
├── build-appimage.sh ← AppImage 构建脚本
├── voice-keyboard.desktop
└── icon.png
```

## 待解决问题

- **Wayland 不支持**：`pynput` 在 Wayland 下无法做全局热键，需要回退 X11 或集成 `evdev` / `uinput`
- **uinput 权限**：`/dev/uinput` 需要用户加入 `input` 组，或安装 udev 规则
- **音频后端**：PulseAudio / PipeWire 兼容测试
- **辅助功能 API**：通过 `xdotool` 或 `ydotool` 打字（取决于会话类型）
