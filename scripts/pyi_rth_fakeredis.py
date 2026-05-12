"""
PyInstaller runtime hook for fakeredis
修复 commands.json 文件路径解析问题
"""

import os
import sys

# 只在 PyInstaller 打包环境中执行
if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
    # Monkey-patch fakeredis 的文件路径解析
    # 这个 patch 必须在 fakeredis 被导入之前执行

    # 保存原始的 open 函数
    _original_open = open

    def _patched_open(file, mode="r", *args, **kwargs):
        """
        拦截 fakeredis 对 commands.json 的打开操作
        将相对路径重定向到 sys._MEIPASS
        """
        # 如果文件路径包含 fakeredis 和 commands.json
        if (
            isinstance(file, str)
            and "fakeredis" in file
            and "commands.json" in file
            and not os.path.exists(file)
        ):
            # 尝试在 sys._MEIPASS 中查找
            commands_json_path = os.path.join(
                sys._MEIPASS,
                "fakeredis",
                "commands.json",
            )
            if os.path.exists(commands_json_path):
                print(
                    f"[fakeredis-hook] Redirecting {file} -> {commands_json_path}",
                    file=sys.stderr,
                )
                file = commands_json_path
            else:
                print(
                    f"[fakeredis-hook] WARNING: commands.json not found at {commands_json_path}",
                    file=sys.stderr,
                )

        return _original_open(file, mode, *args, **kwargs)

    # 替换内置的 open 函数
    import builtins

    builtins.open = _patched_open

    print("[fakeredis-hook] Installed open() patch for commands.json", file=sys.stderr)
