# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec — bản portable My Photo Studio (Windows x64).

Tự chọn binding Qt đang cài giống compat/qt.py (Windows cũ ưu tiên PySide2,
Windows mới ưu tiên PySide6). Chạy qua build_portable.bat, hoặc thủ công:
    .venv310qt5\\Scripts\\python.exe -m PyInstaller --noconfirm --clean ^
        --distpath dist --workpath build\\pyinstaller MyPhotoStudio.spec
"""

import importlib.util
import sys
from pathlib import Path

ROOT = Path(SPECPATH)
ICON = ROOT / "assets" / "app_icon.png"  # do tools/make_app_icon.py sinh ra


def _windows_build() -> int:
    if sys.platform != "win32":
        return 0
    try:
        return int(sys.getwindowsversion().build)
    except AttributeError:
        return 0


def _select_binding() -> str:
    if 0 < _windows_build() < 14393:
        preferred = ["PySide2", "PySide6"]
    else:
        preferred = ["PySide6", "PySide2"]
    for name in preferred:
        if importlib.util.find_spec(name) is not None:
            return name
    raise SystemExit("Không tìm thấy PySide2 hoặc PySide6 để đóng gói.")


QT = _select_binding()
OTHER_QT = "PySide6" if QT == "PySide2" else "PySide2"
UNUSED_QT_MODULES = [
    "QtWebEngine",
    "QtWebEngineCore",
    "QtWebEngineWidgets",
    "QtWebChannel",
    "QtQuick",
    "QtQml",
    "QtMultimedia",
    "QtMultimediaWidgets",
    "QtSql",
    "QtTest",
    "QtCharts",
    "QtDataVisualization",
    "QtBluetooth",
    "Qt3DCore",
    "QtNetworkAuth",
]

datas = [
    (str(ROOT / "assets" / "themes" / "dark.qss"), "assets/themes"),
    (str(ROOT / "assets" / "themes" / "light.qss"), "assets/themes"),
]

a = Analysis(
    [str(ROOT / "main.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=[f"{QT}.QtCore", f"{QT}.QtGui", f"{QT}.QtWidgets"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[OTHER_QT, "PyQt5", "PyQt6", "tkinter", "pytest"]
    + [f"{QT}.{name}" for name in UNUSED_QT_MODULES],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="MyPhotoStudio",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(ICON) if ICON.exists() else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="MyPhotoStudio",
)
