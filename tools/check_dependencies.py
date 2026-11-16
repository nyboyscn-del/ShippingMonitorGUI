from __future__ import annotations

import importlib.metadata
import importlib.util
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from safe_print import safe_print


MIN_PYTHON = (3, 10)
PROJECT_ROOT = Path(__file__).resolve().parents[1]
REQUIREMENTS_FILE = PROJECT_ROOT / "requirements.txt"
USB_FFMPEG_DIR = PROJECT_ROOT / "tools" / "ffmpeg"

PYTHON_PACKAGES = [
    ("PyQt5", "PyQt5", "PyQt5"),
    ("opencv-python", "cv2", "opencv-python"),
    ("numpy", "numpy", "numpy"),
    ("openpyxl", "openpyxl", "openpyxl"),
    ("cryptography", "cryptography", "cryptography"),
    ("pyinstaller", "PyInstaller", "pyinstaller"),
]


def print_header(title: str) -> None:
    safe_print()
    safe_print("=" * 70)
    safe_print(title)
    safe_print("=" * 70)


def check_python_version() -> bool:
    print_header("Python version")
    version = sys.version_info
    safe_print(f"Current Python: {version.major}.{version.minor}.{version.micro}")
    if version < MIN_PYTHON:
        required = ".".join(str(part) for part in MIN_PYTHON)
        safe_print(f"[ERROR] Python {required}+ is required.")
        safe_print("Please install a supported Python version and add it to PATH.")
        return False
    safe_print("[OK] Python version is supported.")
    return True


def load_pinned_requirements() -> dict[str, str]:
    """Read exact ``name==version`` pins from requirements.txt."""
    pins: dict[str, str] = {}
    if not REQUIREMENTS_FILE.is_file():
        return pins
    for raw_line in REQUIREMENTS_FILE.read_text(encoding="utf-8").splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line or line.startswith("-"):
            continue
        name, separator, version = line.partition("==")
        if not separator or not version.strip():
            continue
        pins[name.strip().lower()] = version.strip()
    return pins


def module_installed(module_name: str) -> bool:
    return importlib.util.find_spec(module_name) is not None


def installed_version(distribution_name: str) -> str:
    try:
        return importlib.metadata.version(distribution_name)
    except importlib.metadata.PackageNotFoundError:
        return ""


def install_package(distribution_name: str, version: str) -> bool:
    requirement = f"{distribution_name}=={version}"
    command = [sys.executable, "-m", "pip", "install", "--user", requirement]
    safe_print(f"[INSTALL] {' '.join(command)}")
    result = subprocess.run(command)
    if result.returncode != 0:
        safe_print(f"[ERROR] Failed to install {requirement}.")
        return False
    safe_print(f"[OK] Installed {requirement}.")
    return True


def check_python_packages(auto_install: bool = True) -> bool:
    print_header("Python packages")
    pins = load_pinned_requirements()
    all_ok = True
    for label, module_name, distribution_name in PYTHON_PACKAGES:
        expected = pins.get(distribution_name.lower())
        if not expected:
            safe_print(f"[ERROR] {distribution_name} has no pinned version in requirements.txt.")
            all_ok = False
            continue

        if module_installed(module_name):
            actual = installed_version(distribution_name)
            if actual == expected:
                safe_print(f"[OK] {label} {expected} is installed.")
                continue
            safe_print(f"[MISMATCH] {label} {actual or 'unknown'} != {expected}.")
        else:
            safe_print(f"[MISSING] {label} {expected} is not installed.")

        if auto_install:
            if not install_package(distribution_name, expected):
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
        safe_print("[OK] FFmpeg: found")
        safe_print(f"Path: {path_ffmpeg}")
        return True

    usb_ffmpeg = find_usb_ffmpeg()
    if usb_ffmpeg:
        safe_print("[OK] FFmpeg: found")
        safe_print(f"Path: {usb_ffmpeg}")
        safe_print("You can add this folder to PATH if command line ffmpeg is needed.")
        return True

    safe_print("[WARN] FFmpeg: not found in PATH or tools\\ffmpeg.")
    safe_print("MP4 generation will use the OpenCV mp4v fallback.")
    safe_print("OpenCV mp4v compatibility can be weaker than FFmpeg H.264.")
    safe_print("For FFmpeg support, place ffmpeg.exe at one of these paths:")
    safe_print(f"  {USB_FFMPEG_DIR / 'ffmpeg.exe'}")
    safe_print(f"  {USB_FFMPEG_DIR / 'bin' / 'ffmpeg.exe'}")
    return True


def main() -> int:
    print_header("ShippingMonitorGUI dependency check")
    safe_print(f"Project root: {PROJECT_ROOT}")
    ok = True
    ok = check_python_version() and ok
    ok = check_python_packages(auto_install=True) and ok
    ok = check_ffmpeg() and ok

    print_header("Summary")
    if ok:
        safe_print("[OK] Dependency check completed.")
        return 0
    safe_print("[ERROR] Dependency check failed.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
