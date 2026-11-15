from __future__ import annotations

import importlib.util
import shutil
import subprocess
import sys
from pathlib import Path


MIN_PYTHON = (3, 10)
PROJECT_ROOT = Path(__file__).resolve().parents[1]
USB_FFMPEG_DIR = PROJECT_ROOT / "tools" / "ffmpeg"

PYTHON_PACKAGES = [
    ("PyQt5", "PyQt5", "PyQt5"),
    ("opencv-python", "cv2", "opencv-python"),
    ("numpy", "numpy", "numpy"),
    ("pandas", "pandas", "pandas"),
    ("openpyxl", "openpyxl", "openpyxl"),
    ("pyinstaller", "PyInstaller", "pyinstaller"),
]


def print_header(title: str) -> None:
    print()
    print("=" * 70)
    print(title)
    print("=" * 70)


def check_python_version() -> bool:
    print_header("Python version")
    version = sys.version_info
    print(f"Current Python: {version.major}.{version.minor}.{version.micro}")
    if version < MIN_PYTHON:
        required = ".".join(str(part) for part in MIN_PYTHON)
        print(f"[ERROR] Python {required}+ is required.")
        print("Please install a supported Python version and add it to PATH.")
        return False
    print("[OK] Python version is supported.")
    return True


def module_installed(module_name: str) -> bool:
    return importlib.util.find_spec(module_name) is not None


def install_package(package_name: str) -> bool:
    command = [sys.executable, "-m", "pip", "install", "--user", package_name]
    print(f"[INSTALL] {' '.join(command)}")
    result = subprocess.run(command)
    if result.returncode != 0:
        print(f"[ERROR] Failed to install {package_name}.")
        return False
    print(f"[OK] Installed {package_name}.")
    return True


def check_python_packages(auto_install: bool = True) -> bool:
    print_header("Python packages")
    all_ok = True
    for label, module_name, package_name in PYTHON_PACKAGES:
        if module_installed(module_name):
            print(f"[OK] {label} is installed.")
            continue

        print(f"[MISSING] {label} is not installed.")
        if auto_install:
            if not install_package(package_name):
                all_ok = False
        else:
            all_ok = False
    return all_ok


def find_usb_ffmpeg() -> Path | None:
    candidates = [
        USB_FFMPEG_DIR / "ffmpeg.exe",
        USB_FFMPEG_DIR / "bin" / "ffmpeg.exe",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def check_ffmpeg() -> bool:
    print_header("FFmpeg")
    path_ffmpeg = shutil.which("ffmpeg")
    if path_ffmpeg:
        print("[OK] FFmpeg: found")
        print(f"Path: {path_ffmpeg}")
        return True

    usb_ffmpeg = find_usb_ffmpeg()
    if usb_ffmpeg:
        print("[OK] FFmpeg: found")
        print(f"Path: {usb_ffmpeg}")
        print("You can add this folder to PATH if command line ffmpeg is needed.")
        return True

    print("[WARN] FFmpeg: not found in PATH or tools\\ffmpeg.")
    print("MP4 generation will use the OpenCV mp4v fallback.")
    print("OpenCV mp4v compatibility can be weaker than FFmpeg H.264.")
    print("For FFmpeg support, place ffmpeg.exe at one of these paths:")
    print(f"  {USB_FFMPEG_DIR / 'ffmpeg.exe'}")
    print(f"  {USB_FFMPEG_DIR / 'bin' / 'ffmpeg.exe'}")
    return True


def main() -> int:
    print_header("ShippingMonitorGUI dependency check")
    print(f"Project root: {PROJECT_ROOT}")
    ok = True
    ok = check_python_version() and ok
    ok = check_python_packages(auto_install=True) and ok
    ok = check_ffmpeg() and ok

    print_header("Summary")
    if ok:
        print("[OK] Dependency check completed.")
        return 0
    print("[ERROR] Dependency check failed.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
