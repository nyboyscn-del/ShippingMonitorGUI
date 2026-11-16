from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from safe_print import safe_print


PROJECT_DIR = Path(__file__).resolve().parents[1]
LOG_FILE = PROJECT_DIR / "tools" / "logs" / "auto_build_and_run.log"
DEFAULT_USB_TARGET_DIR = Path(r"E:\ShippingMonitorGUI_USB")

APP_DIR_NAME = "ShippingMonitorGUI"
DIST_APP_DIR = PROJECT_DIR / "dist" / APP_DIR_NAME
REQUIRED_CONFIG_FILES = [
    "config/config.json",
    "config/config.example.json",
]
DEPENDENCY_SCRIPT = PROJECT_DIR / "tools" / "check_dependencies.py"
SECURITY_SCRIPT = PROJECT_DIR / "tools" / "check_release_security.py"
BUILD_SCRIPT = PROJECT_DIR / "build_exe.bat"
EXE_RELATIVE_PATH = Path(APP_DIR_NAME) / "ShippingMonitorGUI.exe"


def log(message: str) -> None:
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}"
    safe_print(line)
    with LOG_FILE.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def run_command(command: list[str], *, shell: bool = False) -> None:
    log("RUN: " + (" ".join(command) if not shell else str(command)))
    result = subprocess.run(
        command if not shell else " ".join(command),
        cwd=PROJECT_DIR,
        shell=shell,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    if result.stdout:
        safe_print(result.stdout, end="")
        with LOG_FILE.open("a", encoding="utf-8") as handle:
            handle.write(result.stdout)
    if result.returncode != 0:
        raise RuntimeError(f"Command failed with exit code {result.returncode}: {command}")


def check_python() -> None:
    version = sys.version_info
    log(f"Python version: {version.major}.{version.minor}.{version.micro}")
    if version < (3, 10):
        raise RuntimeError("Python 3.10+ is required.")


def check_dependencies() -> None:
    if not DEPENDENCY_SCRIPT.exists():
        raise FileNotFoundError(f"Dependency script not found: {DEPENDENCY_SCRIPT}")
    run_command([sys.executable, str(DEPENDENCY_SCRIPT)])


def check_ffmpeg() -> None:
    ffmpeg_path = shutil.which("ffmpeg")
    if ffmpeg_path:
        log(f"FFmpeg found in PATH: {ffmpeg_path}")
        return
    usb_ffmpeg_candidates = [
        PROJECT_DIR / "tools" / "ffmpeg" / "ffmpeg.exe",
        PROJECT_DIR / "tools" / "ffmpeg" / "bin" / "ffmpeg.exe",
    ]
    for candidate in usb_ffmpeg_candidates:
        if candidate.exists():
            log(f"FFmpeg found in tools folder: {candidate}")
            return
    log("FFmpeg not found. OpenCV MP4V conversion remains available.")


def build_exe() -> None:
    if not BUILD_SCRIPT.exists():
        raise FileNotFoundError(f"Build script not found: {BUILD_SCRIPT}")
    run_command(["cmd", "/c", "set AUTO_MODE=1&&build_exe.bat"])
    exe_path = DIST_APP_DIR / "ShippingMonitorGUI.exe"
    if not exe_path.exists():
        raise FileNotFoundError(f"Build finished but EXE was not found: {exe_path}")
    log(f"Build completed: {exe_path}")


def copy_customer_package(target: Path) -> Path:
    if not DIST_APP_DIR.is_dir():
        raise FileNotFoundError(f"Build output folder was not found: {DIST_APP_DIR}")

    destination = target / APP_DIR_NAME
    if destination.exists():
        shutil.rmtree(destination)
    target.mkdir(parents=True, exist_ok=True)
    shutil.copytree(DIST_APP_DIR, destination)
    log(f"Copied customer package: {DIST_APP_DIR} -> {destination}")
    return destination


def prepare_usb_package(target: Path) -> None:
    if not target.drive or not Path(target.drive + "\\").exists():
        raise RuntimeError(f"USB target drive was not found: {target.drive or target}")

    log(f"Preparing USB package: {target}")
    destination = copy_customer_package(target)

    for relative in REQUIRED_CONFIG_FILES:
        required = destination / relative
        if not required.exists():
            raise FileNotFoundError(f"Missing required config file: {required}")

    exe_path = target / EXE_RELATIVE_PATH
    if not exe_path.exists():
        raise FileNotFoundError(f"Missing EXE in USB package: {exe_path}")

    if not SECURITY_SCRIPT.exists():
        raise FileNotFoundError(f"Release security script not found: {SECURITY_SCRIPT}")
    run_command([sys.executable, str(SECURITY_SCRIPT), "--root", str(destination)])
    log(f"USB package verified: {target}")


def start_exe(target: Path) -> None:
    exe_path = target / EXE_RELATIVE_PATH
    if not exe_path.exists():
        raise FileNotFoundError(f"EXE not found: {exe_path}")
    log(f"Starting EXE: {exe_path}")
    subprocess.Popen([str(exe_path)], cwd=exe_path.parent)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Package the ShippingMonitorGUI customer build to USB.")
    parser.add_argument("--target", default=str(DEFAULT_USB_TARGET_DIR), help="USB target folder.")
    parser.add_argument("--build", action="store_true", help="Build EXE before copying.")
    parser.add_argument("--start", action="store_true", help="Start the USB EXE after copying.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    target = Path(args.target)
    try:
        log("=" * 60)
        log("ShippingMonitorGUI USB package started.")
        log(f"Project: {PROJECT_DIR}")
        log(f"Target: {target}")
        check_python()
        check_dependencies()
        check_ffmpeg()
        if args.build:
            build_exe()
        prepare_usb_package(target)
        log(f"USB package completed, output folder: {target}")
        if args.start:
            start_exe(target)
        return 0
    except Exception as exc:
        log(f"ERROR: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
