"""High-value application launch aliases.

Installed macOS applications are also discovered from local .app bundles at
runtime. These presets keep common spoken names stable when the bundle name is
different from what the user says.
"""

MACOS_APP_LAUNCH_PRESETS: dict[str, dict[str, str]] = {
    "打开飞书": {
        "bundle_id": "com.bytedance.macos.feishu",
        "app_name": "Lark",
    },
    "打开Lark": {
        "bundle_id": "com.bytedance.macos.feishu",
        "app_name": "Lark",
    },
    "打开Word": {
        "bundle_id": "com.microsoft.Word",
        "app_name": "Microsoft Word",
    },
    "打开Excel": {
        "bundle_id": "com.microsoft.Excel",
        "app_name": "Microsoft Excel",
    },
    "打开PowerPoint": {
        "bundle_id": "com.microsoft.Powerpoint",
        "app_name": "Microsoft PowerPoint",
    },
    "打开PPT": {
        "bundle_id": "com.microsoft.Powerpoint",
        "app_name": "Microsoft PowerPoint",
    },
    "打开WPS": {
        "bundle_id": "com.kingsoft.wpsoffice.mac",
        "app_name": "WPS Office",
    },
    "打开谷歌浏览器": {
        "bundle_id": "com.google.Chrome",
        "app_name": "Google Chrome",
    },
    "打开Chrome": {
        "bundle_id": "com.google.Chrome",
        "app_name": "Google Chrome",
    },
    "打开谷歌": {
        "bundle_id": "com.google.Chrome",
        "app_name": "Google Chrome",
    },
}
