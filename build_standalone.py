#!/usr/bin/env python3
"""Build a double-click Veaper app for this computer. No Python needed to run it."""

import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def run(command, **kwargs):
    print("+", " ".join(str(part) for part in command))
    subprocess.run(command, cwd=ROOT, check=True, **kwargs)


def ffmpeg_destination():
    name = "ffmpeg.exe" if sys.platform == "win32" else "ffmpeg"
    return ROOT / "vendor" / name


def install_build_tools():
    run(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--upgrade",
            "pip",
            "pyinstaller",
            "pyaaf2",
            "imageio-ffmpeg",
        ]
    )


def stage_ffmpeg():
    import imageio_ffmpeg

    source = Path(imageio_ffmpeg.get_ffmpeg_exe())
    destination = ffmpeg_destination()
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    destination.chmod(destination.stat().st_mode | 0o755)
    print("Bundled FFmpeg:", destination)
    return destination


def build(ffmpeg_path):
    env = os.environ.copy()
    env["VEAPER_FFMPEG"] = str(ffmpeg_path)
    run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "Veaper.spec"], env=env)


def app_binary():
    if sys.platform == "darwin":
        return ROOT / "dist" / "Veaper.app" / "Contents" / "MacOS" / "Veaper"
    if sys.platform == "win32":
        return ROOT / "dist" / "Veaper.exe"
    return ROOT / "dist" / "Veaper"


def self_check():
    binary = app_binary()
    report = ROOT / "dist" / "self-check.txt"
    if report.exists():
        report.unlink()
    print("+", binary, "--self-check", report)
    completed = subprocess.run([str(binary), "--self-check", str(report)], cwd=ROOT / "dist")
    text = report.read_text(encoding="utf-8") if report.exists() else ""
    if report.exists():
        report.unlink()
    print(text)
    if completed.returncode != 0 or not text.startswith("OK"):
        raise SystemExit("The packaged app failed its self-check.")


def sign_and_zip():
    if sys.platform == "darwin":
        app = ROOT / "dist" / "Veaper.app"
        run(["codesign", "--force", "--deep", "--sign", "-", str(app)])
        archive = ROOT / "dist" / "Veaper-mac.zip"
        if archive.exists():
            archive.unlink()
        run(["ditto", "-c", "-k", "--keepParent", str(app), str(archive)])
        print("\nMac app: %s" % app)
        print("Zip to share: %s" % archive)
        return

    if sys.platform == "win32":
        archive = ROOT / "dist" / "Veaper-windows.zip"
        if archive.exists():
            archive.unlink()
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as bundle:
            bundle.write(ROOT / "dist" / "Veaper.exe", "Veaper.exe")
        print("\nWindows app: %s" % (ROOT / "dist" / "Veaper.exe"))
        print("Zip to share: %s" % archive)
        return

    print("\nApp: %s" % app_binary())


def main():
    if sys.version_info < (3, 9):
        raise SystemExit("Build Veaper with Python 3.9 or newer. On a Mac, Homebrew Python works well.")
    install_build_tools()
    ffmpeg_path = stage_ffmpeg()
    build(ffmpeg_path)
    self_check()
    sign_and_zip()


if __name__ == "__main__":
    main()
