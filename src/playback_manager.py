from __future__ import annotations

import os
from pathlib import Path

try:
    import cv2
except ImportError:  # pragma: no cover - depends on local runtime
    cv2 = None


class PlaybackManager:
    def open_video(self, video_path: str | Path) -> Path:
        path = Path(video_path)
        if not path.exists():
            raise FileNotFoundError(f"Video file not found: {path}")
        os.startfile(str(path))
        return path

    def can_read_first_frame(self, video_path: str | Path) -> bool:
        if cv2 is None:
            return False
        path = Path(video_path)
        if not path.exists():
            return False
        capture = cv2.VideoCapture(str(path))
        try:
            ok, frame = capture.read()
            return bool(ok and frame is not None)
        finally:
            capture.release()
