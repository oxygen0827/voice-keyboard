"""Local application launch discovery and execution."""

from __future__ import annotations

from dataclasses import dataclass
import os
import plistlib
from pathlib import Path
import subprocess
import time
if os.name == "nt":
    import ctypes
    import ctypes.wintypes
    import winreg
else:
    ctypes = None
    winreg = None

from agent.app_launch_presets import MACOS_APP_LAUNCH_PRESETS


@dataclass(frozen=True)
class ApplicationLaunchSpec:
    bundle_id: str = ""
    app_name: str = ""
    path: str = ""
    windows: str = ""
    linux: str = ""


CUSTOM_APP_LAUNCHES: dict[str, ApplicationLaunchSpec] = {}
APP_LAUNCH_ACTION_PREFIXES = ("\u6253\u5f00", "\u5207\u6362\u5230")
MACOS_APP_SEARCH_DIRS = (
    "/Applications",
    os.path.expanduser("~/Applications"),
    "/System/Applications",
    "/System/Applications/Utilities",
)
WINDOWS_APP_SEARCH_DIRS = (
    os.path.join(os.environ.get("APPDATA", ""), "Microsoft", "Windows", "Start Menu", "Programs"),
    os.path.join(os.environ.get("ProgramData", ""), "Microsoft", "Windows", "Start Menu", "Programs"),
)
WINDOWS_APP_EXECUTABLE_ALIASES = {
    "Google Chrome": ("chrome.exe",),
    "Microsoft Word": ("winword.exe",),
    "Microsoft Excel": ("excel.exe",),
    "Microsoft PowerPoint": ("powerpnt.exe",),
    "Lark": ("Lark.exe", "Feishu.exe"),
    "WeChat": ("Weixin.exe", "WeChat.exe"),
    "WPS Office": ("wps.exe", "wpsoffice.exe"),
}
WINDOWS_APP_NO_RELAUNCH = {"WeChat"}
WINDOWS_APP_PROCESS_ALIASES = {
    "Google Chrome": ("chrome.exe",),
    "Microsoft Word": ("winword.exe",),
    "Microsoft Excel": ("excel.exe",),
    "Microsoft PowerPoint": ("powerpnt.exe",),
    "Lark": ("Lark.exe", "Feishu.exe"),
    "WeChat": ("Weixin.exe", "WeChat.exe"),
    "WPS Office": ("wps.exe", "wpsoffice.exe"),
}
DYNAMIC_APP_LAUNCH_CACHE: tuple[float, dict[str, ApplicationLaunchSpec]] | None = None
DYNAMIC_APP_LAUNCH_CACHE_SECONDS = 60.0
COMMON_APP_LAUNCH_ALIASES = {
    "Google Chrome": ("谷歌浏览器", "Chrome", "谷歌"),
    "Lark": ("飞书",),
    "WeChat": ("微信",),
    "NeteaseMusic": ("网易云音乐", "网易云"),
    "NetEaseMusic": ("网易云音乐", "网易云"),
    "TencentMeeting": ("腾讯会议",),
    "wpsoffice": ("WPS",),
    "iTerm": ("终端",),
    "iTerm2": ("终端",),
    "Terminal": ("终端",),
    "Stocks": ("股市", "股票"),
}


def load_app_launches(app_launches) -> None:
    CUSTOM_APP_LAUNCHES.clear()
    if not isinstance(app_launches, dict):
        return
    for name, spec in app_launches.items():
        if not isinstance(name, str) or not name.strip():
            continue
        parsed = parse_app_launch_spec(spec)
        if parsed is None:
            print(f"[typer] 忽略应用启动动作 {name!r}: 必须是字符串或映射")
            continue
        CUSTOM_APP_LAUNCHES[name.strip()] = parsed


def app_launch(name: str, os_name: str, blocked_names: set[str] | None = None) -> ApplicationLaunchSpec | None:
    if blocked_names and name in blocked_names:
        return None
    launches = app_launches_for_system(os_name)
    spec = launches.get(name)
    if spec is not None:
        return spec
    lowered = name.lower()
    for action, candidate in launches.items():
        if action.lower() == lowered:
            return candidate
    return None


def app_launches_for_system(os_name: str) -> dict[str, ApplicationLaunchSpec]:
    launches: dict[str, ApplicationLaunchSpec] = {}
    if os_name == "Darwin":
        for name, spec in MACOS_APP_LAUNCH_PRESETS.items():
            parsed = parse_app_launch_spec(spec)
            if parsed is not None:
                launches[name] = parsed
        for name, spec in discover_macos_app_launches().items():
            launches.setdefault(name, spec)
    elif os_name == "Windows":
        discovered = discover_windows_app_launches()
        for name, spec in MACOS_APP_LAUNCH_PRESETS.items():
            parsed = parse_app_launch_spec(spec)
            if parsed is not None and (parsed.windows or parsed.app_name):
                launches[name] = ApplicationLaunchSpec(
                    app_name=parsed.app_name,
                    windows=windows_launch_target_for_spec(name, parsed, discovered),
                )
    launches.update(CUSTOM_APP_LAUNCHES)
    return app_launches_with_switch_aliases(launches)



def app_launches_with_switch_aliases(
    launches: dict[str, ApplicationLaunchSpec],
) -> dict[str, ApplicationLaunchSpec]:
    expanded = dict(launches)
    for name, spec in launches.items():
        target = app_launch_target_from_action(name)
        if target:
            for prefix in APP_LAUNCH_ACTION_PREFIXES:
                expanded.setdefault(f"{prefix}{target}", spec)
    return expanded


def app_launch_target_from_action(action_name: str) -> str:
    for prefix in APP_LAUNCH_ACTION_PREFIXES:
        if action_name.startswith(prefix):
            return action_name[len(prefix):]
    return ""

def launch_application(spec: ApplicationLaunchSpec, os_name: str) -> bool:
    if os_name == "Darwin":
        if spec.bundle_id:
            subprocess.Popen(["open", "-b", spec.bundle_id])
            return True
        if spec.path:
            subprocess.Popen(["open", spec.path])
            return True
        if spec.app_name:
            subprocess.Popen(["open", "-a", spec.app_name])
            return True
        return False
    if os_name == "Windows":
        if activate_running_windows_application(spec):
            return True
        if spec.app_name in WINDOWS_APP_NO_RELAUNCH and windows_process_running(windows_process_names_for_spec(spec)):
            print(f"[typer] Windows app already running; skipped relaunch: {spec.app_name}")
            return True
        target = spec.windows or spec.app_name
        if target:
            if os.path.exists(target) and hasattr(os, "startfile"):
                os.startfile(target)
            else:
                subprocess.Popen(["cmd", "/c", "start", "", target])
            return True
        return False
    target = spec.linux or spec.app_name
    if target:
        subprocess.Popen(target, shell=True)
        return True
    return False



def activate_running_windows_application(spec: ApplicationLaunchSpec) -> bool:
    if os.name != "nt" or ctypes is None:
        return False
    process_names = windows_process_names_for_spec(spec)
    if not process_names:
        return False
    hwnd = find_windows_app_window(process_names)
    if not hwnd:
        return False
    user32 = ctypes.windll.user32
    SW_RESTORE = 9
    user32.ShowWindow(hwnd, SW_RESTORE)
    return bool(user32.SetForegroundWindow(hwnd))


def windows_process_names_for_spec(spec: ApplicationLaunchSpec) -> set[str]:
    names = {
        name.lower()
        for name in WINDOWS_APP_PROCESS_ALIASES.get(spec.app_name, ())
        if name
    }
    for target in (spec.windows, spec.app_name):
        if target and target.lower().endswith(".exe"):
            names.add(Path(target).name.lower())
    return names



def windows_process_running(process_names: set[str]) -> bool:
    if os.name != "nt" or ctypes is None or not process_names:
        return False
    kernel32 = ctypes.windll.kernel32
    snapshot = kernel32.CreateToolhelp32Snapshot(0x00000002, 0)
    invalid_handle = ctypes.c_void_p(-1).value
    if snapshot == invalid_handle:
        return False

    class PROCESSENTRY32W(ctypes.Structure):
        _fields_ = [
            ("dwSize", ctypes.wintypes.DWORD),
            ("cntUsage", ctypes.wintypes.DWORD),
            ("th32ProcessID", ctypes.wintypes.DWORD),
            ("th32DefaultHeapID", ctypes.c_void_p),
            ("th32ModuleID", ctypes.wintypes.DWORD),
            ("cntThreads", ctypes.wintypes.DWORD),
            ("th32ParentProcessID", ctypes.wintypes.DWORD),
            ("pcPriClassBase", ctypes.wintypes.LONG),
            ("dwFlags", ctypes.wintypes.DWORD),
            ("szExeFile", ctypes.wintypes.WCHAR * 260),
        ]

    entry = PROCESSENTRY32W()
    entry.dwSize = ctypes.sizeof(PROCESSENTRY32W)
    try:
        if not kernel32.Process32FirstW(snapshot, ctypes.byref(entry)):
            return False
        while True:
            if entry.szExeFile.lower() in process_names:
                return True
            if not kernel32.Process32NextW(snapshot, ctypes.byref(entry)):
                return False
    finally:
        kernel32.CloseHandle(snapshot)

def find_windows_app_window(process_names: set[str]):
    user32 = ctypes.windll.user32
    found = {"hwnd": 0}

    callback_type = ctypes.WINFUNCTYPE(
        ctypes.wintypes.BOOL,
        ctypes.wintypes.HWND,
        ctypes.wintypes.LPARAM,
    )

    @callback_type
    def callback(hwnd, _lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        pid = ctypes.wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        image_name = windows_process_image_name(int(pid.value))
        if image_name and Path(image_name).name.lower() in process_names:
            found["hwnd"] = hwnd
            return False
        return True

    user32.EnumWindows(callback, 0)
    return found["hwnd"]


def windows_process_image_name(pid: int) -> str:
    if not pid or ctypes is None:
        return ""
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return ""
    try:
        size = ctypes.wintypes.DWORD(32768)
        buffer = ctypes.create_unicode_buffer(size.value)
        if kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
            return buffer.value
        return ""
    finally:
        kernel32.CloseHandle(handle)

def discover_macos_app_launches() -> dict[str, ApplicationLaunchSpec]:
    global DYNAMIC_APP_LAUNCH_CACHE
    now = time.monotonic()
    if (
        DYNAMIC_APP_LAUNCH_CACHE is not None
        and now - DYNAMIC_APP_LAUNCH_CACHE[0] < DYNAMIC_APP_LAUNCH_CACHE_SECONDS
    ):
        return dict(DYNAMIC_APP_LAUNCH_CACHE[1])

    launches: dict[str, ApplicationLaunchSpec] = {}
    for directory in MACOS_APP_SEARCH_DIRS:
        root = Path(directory).expanduser()
        for app_path in iter_macos_app_bundles(root):
            spec = macos_app_launch_spec_from_bundle(app_path)
            for label in macos_app_launch_labels(spec, app_path):
                action = f"打开{label}"
                launches.setdefault(action, spec)
    DYNAMIC_APP_LAUNCH_CACHE = (now, launches)
    return dict(launches)



def discover_windows_app_launches() -> dict[str, ApplicationLaunchSpec]:
    launches: dict[str, ApplicationLaunchSpec] = {}
    for root_name in WINDOWS_APP_SEARCH_DIRS:
        if not root_name:
            continue
        root = Path(root_name)
        if not root.exists():
            continue
        for shortcut in iter_windows_shortcuts(root):
            spec = ApplicationLaunchSpec(
                app_name=shortcut.stem,
                windows=str(shortcut),
            )
            for label in windows_shortcut_labels(shortcut):
                launches.setdefault(f"打开{label}", spec)
    return launches


def iter_windows_shortcuts(root: Path):
    try:
        yield from root.rglob("*.lnk")
    except OSError:
        return


def windows_shortcut_labels(shortcut: Path) -> tuple[str, ...]:
    labels: list[str] = []
    for label in (shortcut.stem, shortcut.name.removesuffix(".lnk")):
        if label and label not in labels:
            labels.append(label)
    for alias in COMMON_APP_LAUNCH_ALIASES.get(shortcut.stem, ()):
        if alias not in labels:
            labels.append(alias)
    return tuple(labels)


def windows_launch_target_for_spec(
    action_name: str,
    spec: ApplicationLaunchSpec,
    discovered: dict[str, ApplicationLaunchSpec] | None = None,
) -> str:
    if spec.windows:
        return spec.windows
    discovered = discovered or discover_windows_app_launches()
    for label in windows_launch_labels_for_spec(action_name, spec):
        found = discovered.get(f"打开{label}")
        if found is not None and found.windows:
            return found.windows
    for exe_name in WINDOWS_APP_EXECUTABLE_ALIASES.get(spec.app_name, ()):
        target = windows_app_path(exe_name)
        if target:
            return target
    return spec.app_name


def windows_launch_labels_for_spec(
    action_name: str,
    spec: ApplicationLaunchSpec,
) -> tuple[str, ...]:
    labels: list[str] = []
    if action_name.startswith("打开"):
        labels.append(action_name.removeprefix("打开"))
    if spec.app_name and spec.app_name not in labels:
        labels.append(spec.app_name)
    for alias in COMMON_APP_LAUNCH_ALIASES.get(spec.app_name, ()):
        if alias not in labels:
            labels.append(alias)
    return tuple(labels)


def windows_app_path(exe_name: str) -> str:
    if winreg is None:
        return ""
    subkey = fr"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\{exe_name}"
    for root in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        try:
            with winreg.OpenKey(root, subkey) as key:
                value, _value_type = winreg.QueryValueEx(key, "")
                if isinstance(value, str) and value.strip():
                    return value.strip()
        except OSError:
            continue
    return ""

def iter_macos_app_bundles(root: Path):
    if not root.exists():
        return
    stack: list[tuple[Path, int]] = [(root, 0)]
    while stack:
        directory, depth = stack.pop()
        try:
            children = list(directory.iterdir())
        except OSError:
            continue
        for child in children:
            if child.name.endswith(".app") and child.is_dir():
                yield child
                continue
            if depth < 2 and child.is_dir():
                stack.append((child, depth + 1))


def macos_app_launch_spec_from_bundle(app_path: Path) -> ApplicationLaunchSpec:
    bundle_id = ""
    app_name = app_path.stem
    info_path = app_path / "Contents" / "Info.plist"
    try:
        with info_path.open("rb") as f:
            info = plistlib.load(f)
        bundle_id = str(info.get("CFBundleIdentifier") or "").strip()
        app_name = str(
            info.get("CFBundleDisplayName")
            or info.get("CFBundleName")
            or app_name
        ).strip()
    except Exception:
        pass
    return ApplicationLaunchSpec(
        bundle_id=bundle_id,
        app_name=app_name or app_path.stem,
        path=str(app_path),
    )


def macos_app_launch_labels(
    spec: ApplicationLaunchSpec,
    app_path: Path,
) -> tuple[str, ...]:
    labels: list[str] = []
    for label in (spec.app_name, app_path.stem):
        if label and label not in labels:
            labels.append(label)
    for alias in COMMON_APP_LAUNCH_ALIASES.get(spec.app_name, ()):
        if alias not in labels:
            labels.append(alias)
    return tuple(labels)


def parse_app_launch_spec(spec) -> ApplicationLaunchSpec | None:
    if isinstance(spec, str):
        value = spec.strip()
        if not value:
            return None
        if "." in value and " " not in value and "/" not in value:
            return ApplicationLaunchSpec(bundle_id=value)
        return ApplicationLaunchSpec(app_name=value, windows=value, linux=value)
    if not isinstance(spec, dict):
        return None
    bundle_id = string_config_value(
        spec,
        "macos_bundle_id",
        "bundle_id",
        "bundle",
    )
    app_name = string_config_value(
        spec,
        "macos_name",
        "app_name",
        "name",
    )
    windows = string_config_value(spec, "windows", "windows_command")
    linux = string_config_value(spec, "linux", "linux_command")
    path = string_config_value(spec, "macos_path", "path")
    parsed = ApplicationLaunchSpec(
        bundle_id=bundle_id,
        app_name=app_name,
        path=path,
        windows=windows,
        linux=linux,
    )
    return parsed if any((bundle_id, app_name, path, windows, linux)) else None


def string_config_value(config: dict, *keys: str) -> str:
    for key in keys:
        value = config.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""
