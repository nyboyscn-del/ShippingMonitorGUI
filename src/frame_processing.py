"""Shared frame processing for the GUI preview and the recording thread.

Both consumers must see the same calibration and watermark result. The only
difference is that the recorder has to keep the writer dimensions, so its
calibration call passes ``target_size`` and the preview passes ``None``.
"""

from __future__ import annotations

from datetime import datetime

from camera_manager import cv2


def _config_value(config, name: str, default):
    if config is None:
        return default
    return getattr(config, name, default)


def _config_bool(config, name: str, default: bool) -> bool:
    return bool(_config_value(config, name, default))


def _config_int(config, name: str, default: int) -> int:
    try:
        return int(_config_value(config, name, default))
    except (TypeError, ValueError):
        return int(default)


def _config_float(config, name: str, default: float) -> float:
    try:
        return float(_config_value(config, name, default))
    except (TypeError, ValueError):
        return float(default)


def parse_bgr_color(value, fallback: tuple[int, int, int] = (0, 255, 0)) -> tuple[int, int, int]:
    text = str(value or "").strip()
    if text.startswith("#") and len(text) == 7:
        try:
            red = int(text[1:3], 16)
            green = int(text[3:5], 16)
            blue = int(text[5:7], 16)
            return blue, green, red
        except ValueError:
            pass
    return fallback


def apply_camera_calibration(frame, config, target_size: tuple[int, int] | None = None):
    """Apply brightness/contrast and the configured ROI crop to ``frame``.

    ``target_size`` is only used by the recorder: cropping changes the frame
    dimensions while ``cv2.VideoWriter`` keeps the size selected at open time,
    so the cropped frame has to be resized back. Preview passes ``None`` and
    therefore never pays for the resize.
    """
    if cv2 is None or config is None or frame is None:
        return frame
    if not _config_bool(config, "camera_calibration_enabled", False):
        return frame

    alpha = 1.0 + _config_float(config, "camera_calibration_contrast", 0) / 100.0
    beta = _config_float(config, "camera_calibration_brightness", 0)
    if alpha != 1.0 or beta != 0.0:
        frame = cv2.convertScaleAbs(frame, alpha=alpha, beta=beta)

    if not _config_bool(config, "camera_calibration_roi_enabled", False):
        return frame

    roi_x = _config_int(config, "camera_calibration_roi_x", 0)
    roi_y = _config_int(config, "camera_calibration_roi_y", 0)
    roi_w = _config_int(config, "camera_calibration_roi_w", 0)
    roi_h = _config_int(config, "camera_calibration_roi_h", 0)
    height, width = frame.shape[:2]
    if roi_w <= 0 or roi_h <= 0 or roi_x < 0 or roi_y < 0:
        return frame
    if roi_x + roi_w > width or roi_y + roi_h > height:
        return frame

    frame = frame[roi_y:roi_y + roi_h, roi_x:roi_x + roi_w]
    if target_size is not None and (frame.shape[1], frame.shape[0]) != tuple(target_size):
        frame = cv2.resize(frame, tuple(target_size), interpolation=cv2.INTER_LINEAR)
    return frame


def apply_watermark(
    frame,
    *,
    text: str,
    font_scale: float = 0.9,
    color: str = "#00FF00",
    opacity: float = 0.75,
    position: str = "top_left",
    timestamp: datetime | None = None,
):
    """Blend a two-line watermark over the text block, never the full frame."""
    if cv2 is None or frame is None:
        return frame

    display_text = str(text or "").strip() or "--"
    now_text = (timestamp or datetime.now()).strftime("%Y-%m-%d %H:%M:%S")
    lines = [display_text, now_text]

    font = cv2.FONT_HERSHEY_SIMPLEX
    font_scale = max(0.3, float(font_scale))
    thickness = max(1, int(round(font_scale * 2)))
    outline_thickness = thickness + 2
    line_gap = max(8, int(12 * font_scale))
    margin = max(16, int(24 * font_scale))
    bgr = parse_bgr_color(color)
    alpha = max(0.0, min(1.0, float(opacity)))

    sizes = [cv2.getTextSize(line, font, font_scale, thickness)[0] for line in lines]
    block_width = max(width for width, _height in sizes)
    block_height = sum(height for _width, height in sizes) + line_gap * (len(lines) - 1)

    x, y = _watermark_origin(
        frame.shape[1],
        frame.shape[0],
        block_width,
        block_height,
        margin,
        position,
    )

    padding = outline_thickness + 2
    x0 = max(0, x - padding)
    y0 = max(0, y - padding)
    x1 = min(frame.shape[1], x + block_width + padding)
    y1 = min(frame.shape[0], y + block_height + padding)
    target = frame[y0:y1, x0:x1]
    overlay = target.copy()

    current_y = y
    for index, line in enumerate(lines):
        _text_width, text_height = sizes[index]
        baseline_y = current_y + text_height
        cv2.putText(
            overlay,
            line,
            (x - x0, baseline_y - y0),
            font,
            font_scale,
            (0, 0, 0),
            outline_thickness,
            cv2.LINE_AA,
        )
        cv2.putText(
            overlay,
            line,
            (x - x0, baseline_y - y0),
            font,
            font_scale,
            bgr,
            thickness,
            cv2.LINE_AA,
        )
        current_y += text_height + line_gap

    cv2.addWeighted(overlay, alpha, target, 1 - alpha, 0, dst=target)
    return frame


def apply_watermark_for_config(frame, config, tracking_number: str = ""):
    """Preview entry point: honour ``watermark_enabled`` and watermark_* keys."""
    if cv2 is None or config is None or not _config_bool(config, "watermark_enabled", True):
        return frame
    text = str(_config_value(config, "watermark_text", "") or "").strip()
    if not text:
        text = str(tracking_number or "").strip()
    return apply_watermark(
        frame,
        text=text,
        font_scale=_config_float(config, "watermark_font_scale", 0.9),
        color=_config_value(config, "watermark_color", "#00FF00"),
        opacity=_config_float(config, "watermark_opacity", 0.75),
        position=_config_value(config, "watermark_position", "top_left"),
    )


def _watermark_origin(
    frame_width: int,
    frame_height: int,
    block_width: int,
    block_height: int,
    margin: int,
    position: str,
) -> tuple[int, int]:
    if position == "top_right":
        return max(margin, frame_width - block_width - margin), margin
    if position == "bottom_left":
        return margin, max(margin, frame_height - block_height - margin)
    if position == "bottom_right":
        return (
            max(margin, frame_width - block_width - margin),
            max(margin, frame_height - block_height - margin),
        )
    return margin, margin