# -*- mode: python ; coding: utf-8 -*-
import os
import sys

from PyInstaller.utils.hooks import collect_all

aaf_datas, aaf_binaries, aaf_hidden = collect_all("aaf2")

ffmpeg = os.environ.get("VEAPER_FFMPEG", "")
if not ffmpeg or not os.path.isfile(ffmpeg):
    raise SystemExit("VEAPER_FFMPEG is not set to an FFmpeg binary. Run build_standalone.py.")

icon = "icons/veaper.icns" if sys.platform == "darwin" else "icons/veaper.ico"

a = Analysis(
    ["Veaper.py"],
    pathex=[],
    binaries=[(ffmpeg, ".")] + aaf_binaries,
    datas=[("icons", "icons")] + aaf_datas,
    hiddenimports=aaf_hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["moviepy", "numpy", "PIL", "imageio", "imageio_ffmpeg"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe_kwargs = dict(
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
    icon=icon,
    name="Veaper",
)

if sys.platform == "darwin":
    exe = EXE(
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        **exe_kwargs,
    )
    coll = COLLECT(
        exe,
        a.binaries,
        a.datas,
        strip=False,
        upx=False,
        upx_exclude=[],
        name="Veaper",
    )
    app = BUNDLE(
        coll,
        name="Veaper.app",
        icon=icon,
        bundle_identifier="net.filipelopes.veaper",
        info_plist={
            "CFBundleName": "Veaper",
            "CFBundleDisplayName": "Veaper",
            "CFBundleShortVersionString": "1.2.0",
            "CFBundleVersion": "1.2.0",
            "NSHighResolutionCapable": True,
            "CFBundleDocumentTypes": [
                {
                    "CFBundleTypeName": "Advanced Authoring Format",
                    "CFBundleTypeRole": "Viewer",
                    "LSHandlerRank": "Alternate",
                    "CFBundleTypeExtensions": ["aaf"],
                }
            ],
        },
    )
else:
    exe = EXE(
        pyz,
        a.scripts,
        a.binaries,
        a.datas,
        [],
        **exe_kwargs,
    )
