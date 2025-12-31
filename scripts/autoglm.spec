# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller 配置文件 - AutoGLM-GUI 后端打包

使用方法:
    cd scripts
    pyinstaller autoglm.spec

输出目录:
    scripts/dist/autoglm-gui/
"""

from pathlib import Path
from PyInstaller.utils.hooks import copy_metadata, collect_data_files

# 项目根目录（SPECPATH 是 spec 文件所在目录，由 PyInstaller 提供）
ROOT_DIR = Path(SPECPATH).parent

block_cipher = None

a = Analysis(
    # 入口点：Python 后端的 __main__.py
    [str(ROOT_DIR / 'AutoGLM_GUI' / '__main__.py')],

    pathex=[],

    # 二进制文件
    binaries=[
        # scrcpy-server 二进制文件（必需）
        (str(ROOT_DIR / 'scrcpy-server-v3.3.3'), '.'),
    ],

    # 数据文件
    datas=[
        # 前端静态文件（必需）
        (str(ROOT_DIR / 'AutoGLM_GUI' / 'static'), 'AutoGLM_GUI/static'),

        # phone_agent 配置文件（prompts, apps 等）
        (str(ROOT_DIR / 'phone_agent' / 'config'), 'phone_agent/config'),

        # ADB Keyboard APK 及许可证文件（自动安装功能）
        (str(ROOT_DIR / 'AutoGLM_GUI' / 'resources' / 'apks'), 'AutoGLM_GUI/resources/apks'),

        # mai_agent 目录（MAI Agent 第三方代码，不修改）
        (str(ROOT_DIR / 'mai_agent'), 'mai_agent'),

        # Package metadata（运行时需要）
        *copy_metadata('fastmcp'),
        *copy_metadata('lupa'),
        *copy_metadata('fakeredis'),

        # fakeredis 数据文件（commands.json 需要在 fakeredis/ 目录下）
        # 使用 collect_data_files 会自动处理正确的路径
        *collect_data_files('fakeredis', include_py_files=False),
    ],

    # 隐藏导入：PyInstaller 无法自动检测的模块
    hiddenimports=[
        # uvicorn 相关
        'uvicorn.logging',
        'uvicorn.loops',
        'uvicorn.loops.auto',
        'uvicorn.loops.asyncio',
        'uvicorn.protocols',
        'uvicorn.protocols.http',
        'uvicorn.protocols.http.auto',
        'uvicorn.protocols.http.h11_impl',
        'uvicorn.protocols.websockets',
        'uvicorn.protocols.websockets.auto',
        'uvicorn.protocols.websockets.websockets_impl',
        'uvicorn.lifespan',
        'uvicorn.lifespan.on',

        # FastAPI 相关
        'fastapi.responses',
        'fastapi.staticfiles',

        # lupa (fakeredis 依赖) - Lua runtime for Python
        'lupa',
        'lupa.lua51',
        'lupa.lua52',
        'lupa.lua53',
        'lupa.lua54',

        # 其他可能需要的模块
        'PIL._tkinter_finder',  # Pillow
    ],

    hookspath=[],
    hooksconfig={},
    # Runtime hooks: 在主程序运行前执行
    runtime_hooks=[
        str(Path(SPECPATH) / 'pyi_rth_utf8.py'),  # UTF-8 编码（Windows）
        str(Path(SPECPATH) / 'pyi_rth_fakeredis.py'),  # fakeredis 路径修复
    ],
    excludes=[
        # 排除不需要的模块以减小体积
        'tkinter',
        'matplotlib',
        # 注意: numpy 被 mai_agent 依赖，不能排除
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(
    a.pure,
    a.zipped_data,
    cipher=block_cipher
)

exe = EXE(
    pyz,
    a.scripts,
    # PyInstaller OPTIONS: 启用 UTF-8 模式 (PEP 540)
    # 注意: PyInstaller 6.9+ 不再受 PYTHONUTF8 环境变量影响
    # 必须在打包时通过 OPTIONS 机制永久启用
    # 参考: https://pyinstaller.org/en/v6.9.0/CHANGES.html
    [('X utf8_mode=1', None, 'OPTION')],
    exclude_binaries=True,
    name='autoglm-gui',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,  # 首次不启用 UPX 压缩，确保稳定性
    console=True,  # 保留控制台窗口便于调试（生产版本可改为 False）
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='autoglm-gui',
)
