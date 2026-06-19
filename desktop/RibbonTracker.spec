# -*- mode: python ; coding: utf-8 -*-
#
# PyInstaller spec for the Ribbon Tracker desktop app (Windows .exe).
#
# TOOLCHAIN PINS — every one matters:
#   * Python 3.11 (NOT 3.12). 3.12 removed pkgutil.ImpImporter, which our
#     pinned setuptools 65.5.1 needs at boot. A 3.12 build crashes at launch.
#   * setuptools==65.5.1 — newer setuptools makes pkg_resources strict and
#     crashes the frozen exe ("InvalidVersion: '.../RibbonTracker'").
#   * jaraco.* / more_itertools / packaging / platformdirs / appdirs /
#     ordered_set installed as REAL top-level packages AND collect_all'd here
#     so pkg_resources' extern importer has a runtime fallback.
#
# The Windows CI BOOT SELF-TEST in build-windows.yml is the authoritative
# check for what the tech downloads. A green Mac build does not prove this one
# launches.

import os
from PyInstaller.utils.hooks import (
    collect_all, collect_submodules, collect_data_files,
)

APP_NAME = "RibbonTracker"
SPEC_DIR = os.path.dirname(os.path.abspath(SPEC))
REPO_ROOT = os.path.dirname(SPEC_DIR)

block_cipher = None

# ─── Heavy shells we want to fully bundle ─────────────────────────────
# altair validates Vega-Lite specs through jsonschema, which pulls
# rfc3987_syntax (a .lark grammar) + jsonschema_specifications (.json
# metaschemas). collect_all on these grabs their DATA files — without them
# `import altair` raises FileNotFoundError in the frozen app even though the
# server's /_stcore/health still answers ok.
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

# ─── pkg_resources + setuptools — submodules + data ───────────────────
hiddenimports += collect_submodules("pkg_resources")
hiddenimports += collect_submodules("setuptools")
datas += collect_data_files("pkg_resources")

# ─── vendored packages (also installed top-level via requirements) ────
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

# ─── Explicit hidden imports ──────────────────────────────────────────
hiddenimports += [
    "ribbon_parser",
    "error_reporter",
    "tkinter",
    "tkinter.filedialog",
    "streamlit.web.cli",
    "streamlit.runtime",
    "streamlit.runtime.scriptrunner.magic_funcs",
]

# ─── Bundle our own .py files at the bundle root ──────────────────────
datas += [(os.path.join(REPO_ROOT, "ribbon_parser.py"), ".")]
datas += [(os.path.join(REPO_ROOT, "error_reporter.py"), ".")]
datas += [(os.path.join(REPO_ROOT, "ribbon_tracker_app.py"), ".")]
# Error-report webhook — bundled only if CI wrote it from the repo secret.
_webhook_cfg = os.path.join(SPEC_DIR, "_webhook.cfg")
if os.path.exists(_webhook_cfg):
    datas += [(_webhook_cfg, ".")]

# ─── Excludes ─────────────────────────────────────────────────────────
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
    console=False,           # WINDOWED — no console popup on launch.
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
