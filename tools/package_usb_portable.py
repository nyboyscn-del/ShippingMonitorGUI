from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[1]
LOG_FILE = PROJECT_DIR / "tools" / "logs" / "auto_build_and_run.log"
DEFAULT_USB_TARGET_DIR = Path(r"E:\ShippingMonitorGUI_USB")
REQUIRED_CONFIG_FILES = [
    "config/config.json",
    "config/config.example.json",
    "config/license.json",
]
COPY_DIRS = ["config", "data", "logs", "reports", "tools", "src", "dist"]
COPY_FILES = ["auto_build_and_run.bat", "run_gui_stage1.bat", "build_exe.bat", "package_usb_portable.bat"]
DEPENDENCY_SCRIPT = PROJECT_DIR / "tools" / "check_dependencies.py"
BUILD_SCRIPT = PROJECT_DIR / "build_exe.bat"
EXE_RELATIVE_PATH = Path("dist") / "ShippingMonitorGUI" / "ShippingMonitorGUI.exe"


def log(message: str) -> None:
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}"
    print(line)
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
        print(result.stdout, end="")
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
    exe_path = PROJECT_DIR / EXE_RELATIVE_PATH
    if not exe_path.exists():
        raise FileNotFoundError(f"Build finished but EXE was not found: {exe_path}")
    log(f"Build completed: {exe_path}")


def copy_tree(source: Path, target: Path) -> None:
    if not source.exists():
        target.mkdir(parents=True, exist_ok=True)
        log(f"Source folder missing, created empty target folder: {target}")
        return
    target.mkdir(parents=True, exist_ok=True)
    for item in source.iterdir():
        destination = target / item.name
        if item.is_dir():
            copy_tree(item, destination)
        else:
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, destination)


def prepare_usb_package(target: Path) -> None:
    if not target.drive or not Path(target.drive + "\\").exists():
        raise RuntimeError(f"USB target drive was not found: {target.drive or target}")

    target.mkdir(parents=True, exist_ok=True)
    log(f"Preparing USB package: {target}")

    for folder in COPY_DIRS:
        copy_tree(PROJECT_DIR / folder, target / folder)
        log(f"Copied folder: {folder}")

    for filename in COPY_FILES:
        source = PROJECT_DIR / filename
        if source.exists():
            shutil.copy2(source, target / filename)
            log(f"Copied file: {filename}")

    for relative in REQUIRED_CONFIG_FILES:
        required = target / relative
        if not required.exists():
            raise FileNotFoundError(f"Missing required config file: {required}")

    exe_path = target / EXE_RELATIVE_PATH
    if not exe_path.exists():
        raise FileNotFoundError(f"Missing EXE in USB package: {exe_path}")
    log(f"USB package verified: {target}")


def start_exe(target: Path) -> None:
    exe_path = target / EXE_RELATIVE_PATH
    if not exe_path.exists():
        raise FileNotFoundError(f"EXE not found: {exe_path}")
    log(f"Starting EXE: {exe_path}")
    subprocess.Popen([str(exe_path)], cwd=exe_path.parent)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Package ShippingMonitorGUI USB portable build.")
    parser.add_argument("--target", default=str(DEFAULT_USB_TARGET_DIR), help="USB target folder.")
    parser.add_argument("--build", action="store_true", help="Build EXE before copying.")
    parser.add_argument("--start", action="store_true", help="Start the USB EXE after copying.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    target = Path(args.target)
    try:
        log("=" * 60)
        log("ShippingMonitorGUI USB portable package started.")
        log(f"Project: {PROJECT_DIR}")
        log(f"Target: {target}")
        check_python()
        check_dependencies()
        check_ffmpeg()
        if args.build:
            build_exe()
        prepare_usb_package(target)
        log(f"USB portable package completed, output folder: {target}")
        if args.start:
            start_exe(target)
        return 0
    except Exception as exc:
        log(f"ERROR: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
