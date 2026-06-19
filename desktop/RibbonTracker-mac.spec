# -*- mode: python ; coding: utf-8 -*-
#
# PyInstaller spec for the Ribbon Tracker desktop app (macOS .app).
# IDENTICAL to RibbonTracker.spec (Windows) except the trailing BUNDLE() step
# that turns the COLLECT directory into a double-clickable .app. See the
# comment block at the top of RibbonTracker.spec for the toolchain pins.
#
# This Mac build is for local de-risking AND for Mac techs. The Windows CI
# BOOT SELF-TEST in build-windows.yml remains the authoritative check for the
# Windows download.

import os
from PyInstaller.utils.hooks import (
    collect_all, collect_submodules, collect_data_files,
)

APP_NAME = "RibbonTracker"
SPEC_DIR = os.path.dirname(os.path.abspath(SPEC))
REPO_ROOT = os.path.dirname(SPEC_DIR)

block_cipher = None

# altair -> jsonschema -> rfc3987_syntax (.lark) + jsonschema_specifications
# (.json metaschemas): collect_all grabs their DATA files, without which
# `import altair` raises FileNotFoundError in the frozen app.
_to_collect = ["streamlit", "altair", "numpy", "openpyxl",
               "jsonschema", "jsonschema_specifications", "referencing",
               "rfc3987_syntax"]
_optional = ["pyarrow", "pandas", "matplotlib"]

datas, binaries, hiddenimports = [], [], []

for name in _to_collect + _optional:
    try:
        d, b, h = collect_all(name)
        datas += d
        binaries += b
        hiddenimports += h
    except Exception as e:
        print(f"[spec] skip collect_all({name}): {e}")

hiddenimports += collect_submodules("pkg_resources")
hiddenimports += collect_submodules("setuptools")
datas += collect_data_files("pkg_resources")

for name in ("jaraco.text", "jaraco.functools", "jaraco.context",
             "more_itertools", "packaging", "platformdirs", "appdirs",
             "ordered_set"):
    try:
        d, b, h = collect_all(name)
        datas += d
        binaries += b
        hiddenimports += h
    except Exception as e:
        print(f"[spec] skip collect_all({name}): {e}")

hiddenimports += [
    "ribbon_parser",
    "error_reporter",
    "tkinter",
    "tkinter.filedialog",
    "streamlit.web.cli",
    "streamlit.runtime",
    "streamlit.runtime.scriptrunner.magic_funcs",
]

datas += [(os.path.join(REPO_ROOT, "ribbon_parser.py"), ".")]
datas += [(os.path.join(REPO_ROOT, "error_reporter.py"), ".")]
datas += [(os.path.join(REPO_ROOT, "ribbon_tracker_app.py"), ".")]
_webhook_cfg = os.path.join(SPEC_DIR, "_webhook.cfg")
if os.path.exists(_webhook_cfg):
    datas += [(_webhook_cfg, ".")]

excludes = ["weasyprint", "cairocffi", "pango", "gobject", "PyQt5", "PyQt6",
            "PySide2", "PySide6", "reportlab"]

a = Analysis(
    [os.path.join(SPEC_DIR, "launcher.py")],
    pathex=[REPO_ROOT, SPEC_DIR],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=APP_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
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
    name=APP_NAME,
)

app = BUNDLE(
    coll,
    name=f"{APP_NAME}.app",
    icon=None,                       # drop a .icns here to brand it later
    bundle_identifier="com.lakeosoyoos.ribbontracker",
    info_plist={
        "CFBundleName": APP_NAME,
        "CFBundleDisplayName": "Ribbon Tracker",
        "CFBundleShortVersionString": "1.0.0",
        "CFBundleVersion": "1.0.0",
        "NSHighResolutionCapable": True,
        "LSUIElement": False,
    },
)
