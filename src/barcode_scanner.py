"""
摄像头条码/二维码识别模块。

优先使用 pyzbar（如果有安装），
OpenCV BarcodeDetector 作为兜底方案。

支持：EAN-13, EAN-8, UPC-A, UPC-E, Code-128, Code-39,
      ITF, QR Code, DataMatrix 等常见格式。
"""

import time

import cv2

# ── Safe top-level import: catch ALL exceptions ──
PYZBAR_AVAILABLE = False
PYZBAR_IMPORT_ERROR = None
pyzbar = None

try:
    from pyzbar import pyzbar as _pyzbar
    pyzbar = _pyzbar
    PYZBAR_AVAILABLE = True
except Exception as e:
    PYZBAR_AVAILABLE = False
    PYZBAR_IMPORT_ERROR = str(e)
    pyzbar = None
# ────────────────────────────────────────────────


class BarcodeScanner:
    """封装条码检测，带防抖/去重逻辑。"""

    def __init__(self, debounce_sec: float = 5.0):
        self.last_code: str | None = None
        self.last_time: float = 0.0
        self.debounce_sec: float = max(0.5, float(debounce_sec))

        # OpenCV detector — lazy init (avoid crash in __init__)
        self._opencv_detector = None
        self._opencv_detector_tried = False

        # Print backend status ONCE at startup
        self._log_backend_status()

    def _log_backend_status(self) -> None:
        """Print backend status once (called from __init__)."""
        if PYZBAR_AVAILABLE:
            print("[BarcodeScanner] Using pyzbar for barcode detection")
        else:
            if PYZBAR_IMPORT_ERROR:
                print(f"[BarcodeScanner] pyzbar unavailable: {PYZBAR_IMPORT_ERROR}")
            else:
                print("[BarcodeScanner] pyzbar not installed")
            if self._opencv_barcode_available():
                print("[BarcodeScanner] Using OpenCV BarcodeDetector as fallback")
            elif hasattr(cv2, "QRCodeDetector"):
                print("[BarcodeScanner] Using OpenCV QRCodeDetector as fallback")
            else:
                print("[BarcodeScanner] WARNING: No barcode detector available")

    def _opencv_barcode_available(self) -> bool:
        """Check if OpenCV BarcodeDetector is available."""
        if not hasattr(cv2, "barcode"):
            return False
        if not hasattr(cv2.barcode, "BarcodeDetector"):
            return False
        return True

    def _init_opencv_detector(self):
        """Lazy-init OpenCV BarcodeDetector (called on first use)."""
        if self._opencv_detector_tried:
            return
        self._opencv_detector_tried = True
        try:
            if self._opencv_barcode_available():
                self._opencv_detector = cv2.barcode.BarcodeDetector()
        except Exception as e:
            self._opencv_detector = None
            print(f"[BarcodeScanner] OpenCV BarcodeDetector init failed: {e}")

    def get_backend_status(self) -> dict:
        """
        Return backend availability status.
        Called by gui_main.py if it wants to show a hint.
        """
        return {
            "pyzbar_available": PYZBAR_AVAILABLE,
            "pyzbar_error": PYZBAR_IMPORT_ERROR,
            "opencv_barcode_available": self._opencv_barcode_available(),
            "qrcode_available": hasattr(cv2, "QRCodeDetector"),
        }

    def detect(self, frame, apply_debounce: bool = True) -> str | None:
        """
        对一帧图像做条码检测。

        :param frame: BGR numpy array（OpenCV 帧）
        :param apply_debounce: 是否应用内置防抖；调用方自行管理状态锁时传 False
        :return: 识别到的条码字符串；未识别到返回 None
        """
        try:
            if frame is None:
                return None

            code = None

            # 方法1: pyzbar（优先）
            if PYZBAR_AVAILABLE and pyzbar is not None:
                code = self._detect_pyzbar(frame)

            # 方法2: OpenCV BarcodeDetector（兜底）
            if not code:
                code = self._detect_opencv_barcode(frame)

            # 方法3: OpenCV QRCodeDetector（最后兜底）
            if not code:
                code = self._detect_opencv_qrcode(frame)

            if not code:
                return None

            if not apply_debounce:
                print(f"[BarcodeScanner] Barcode detected: {code}")
                return code

            # 防抖：同一条码在 debounce_sec 内不重复触发
            now = time.time()
            if code != self.last_code or now - self.last_time > self.debounce_sec:
                self.last_code = code
                self.last_time = now
                print(f"[BarcodeScanner] Barcode detected: {code}")
                return code
            return None

        except Exception as e:
            print(f"ERROR: Barcode detection failed: {e}")
            return None

    def _detect_pyzbar(self, frame) -> str | None:
        """使用 pyzbar 识别条码/二维码。"""
        try:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            decoded = pyzbar.decode(gray, scan_locations=True)
            if decoded:
                for obj in decoded:
                    data = obj.data.decode("utf-8", errors="replace").strip()
                    if data:
                        return data
            return None
        except Exception as e:
            print(f"[BarcodeScanner] pyzbar error: {e}")
            return None

    def _detect_opencv_barcode(self, frame) -> str | None:
        """使用 OpenCV BarcodeDetector 识别条码。"""
        try:
            self._init_opencv_detector()
            if self._opencv_detector is None:
                return None
            result = self._opencv_detector.detectAndDecode(frame)
            # OpenCV 4.x: returns (ok, decoded_info, decoded_type, corners)
            if len(result) == 4:
                ok, decoded_info, _decoded_type, _corners = result
            else:
                ok, decoded_info, _decoded_type = result
                _corners = None

            if not ok or not decoded_info:
                return None

            code = str(decoded_info[0]).strip() if isinstance(decoded_info, list) else str(decoded_info).strip()
            return code if code else None
        except Exception as e:
            print(f"[BarcodeScanner] OpenCV BarcodeDetector error: {e}")
            return None

    def _detect_opencv_qrcode(self, frame) -> str | None:
        """使用 OpenCV QRCodeDetector 识别二维码（兜底）。"""
        try:
            if not hasattr(cv2, "QRCodeDetector"):
                return None
            detector = cv2.QRCodeDetector()
            data, _points = detector.detectAndDecode(frame)
            if data:
                return str(data).strip()
            return None
        except Exception as e:
            print(f"[BarcodeScanner] OpenCV QRCodeDetector error: {e}")
            return None

    def set_debounce(self, sec: float) -> None:
        """设置防抖间隔（秒）。"""
        self.debounce_sec = max(0.5, float(sec))
