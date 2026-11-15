from __future__ import annotations

import hmac
import json
import mimetypes
import re
import threading
from dataclasses import dataclass
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path, PurePosixPath
from typing import Callable
from urllib.parse import parse_qs, quote, unquote, urlparse

from query_manager import (
    QueryManager,
    get_allowed_recording_roots,
    safe_file_under_allowed_roots,
)


_DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_SENSITIVE_PARTS = {
    "src",
    "config",
    "tools",
    "backup",
    "release",
    "dist",
    "license_keys",
}
_SENSITIVE_NAMES = {
    "license.json",
    "license_code_generator.py",
    "issued_licenses.csv",
}


@dataclass(frozen=True)
class LanQueryServerStatus:
    running: bool
    host: str
    port: int


class LanQueryServer:
    def __init__(
        self,
        host: str,
        port: int,
        token: str,
        query_manager: QueryManager,
        allowed_roots: list[str | Path],
        web_root: str | Path,
        logger: Callable[[str], None] | None = None,
    ) -> None:
        self.host = str(host or "0.0.0.0")
        self.port = int(port)
        self.token = str(token)
        self.query_manager = query_manager
        self.allowed_roots = get_allowed_recording_roots(allowed_roots)
        self.web_root = Path(web_root).resolve()
        self.logger = logger
        self._httpd: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> LanQueryServerStatus:
        if self.is_running():
            return self.status()
        if not self.token:
            raise ValueError("LAN query token is empty.")
        if not self.allowed_roots:
            raise ValueError("At least one recordings root is required.")
        if not self.web_root.is_dir():
            raise FileNotFoundError(f"LAN query web root not found: {self.web_root}")

        handler = self._build_handler()
        httpd = ThreadingHTTPServer((self.host, self.port), handler)
        httpd.daemon_threads = True
        self._httpd = httpd
        self.port = int(httpd.server_address[1])
        self._thread = threading.Thread(
            target=httpd.serve_forever,
            name="lan-query-server",
            daemon=True,
        )
        self._thread.start()
        self._log(
            f"LAN query server started: host={self.host}, port={self.port}, "
            f"token={mask_token(self.token)}"
        )
        return self.status()

    def stop(self) -> None:
        httpd = self._httpd
        thread = self._thread
        self._httpd = None
        self._thread = None
        if httpd is not None:
            httpd.shutdown()
            httpd.server_close()
        if thread is not None and thread.is_alive() and threading.current_thread() is not thread:
            thread.join(timeout=3)
        self._log("LAN query server stopped.")

    def is_running(self) -> bool:
        return self._httpd is not None and self._thread is not None and self._thread.is_alive()

    def status(self) -> LanQueryServerStatus:
        return LanQueryServerStatus(self.is_running(), self.host, self.port)

    def _build_handler(self):
        owner = self

        class Handler(BaseHTTPRequestHandler):
            server_version = "ShippingMonitorLAN/1.1"

            def do_GET(self) -> None:
                parsed = urlparse(self.path)
                try:
                    if parsed.path in ("/", "/index.html"):
                        self._send_static("index.html", "text/html; charset=utf-8")
                    elif parsed.path == "/style.css":
                        self._send_static("style.css", "text/css; charset=utf-8")
                    elif parsed.path == "/app.js":
                        self._send_static("app.js", "application/javascript; charset=utf-8")
                    elif parsed.path == "/api/status":
                        if self._require_token(parsed.query):
                            self._send_json(
                                {
                                    "ok": True,
                                    "service": "ShippingMonitorGUI LAN Query",
                                    "readonly": True,
                                }
                            )
                    elif parsed.path == "/api/search":
                        if self._require_token(parsed.query):
                            self._handle_search(parsed.query)
                    elif parsed.path == "/file":
                        if self._require_token(parsed.query):
                            self._handle_file(parsed.query)
                    else:
                        self._send_error_json(HTTPStatus.NOT_FOUND, "Not found.")
                except (BrokenPipeError, ConnectionResetError):
                    return
                except Exception as exc:  # noqa: BLE001
                    owner._log(f"LAN query request failed: {type(exc).__name__}: {exc}")
                    self._send_error_json(HTTPStatus.INTERNAL_SERVER_ERROR, "Request failed.")

            def do_POST(self) -> None:
                self._send_error_json(HTTPStatus.METHOD_NOT_ALLOWED, "Read-only service.")

            do_PUT = do_POST
            do_PATCH = do_POST
            do_DELETE = do_POST

            def log_message(self, format_string: str, *args) -> None:
                owner._log("LAN query HTTP request completed.")

            def _require_token(self, query: str) -> bool:
                supplied = parse_qs(query, keep_blank_values=True).get("token", [""])[0]
                if not hmac.compare_digest(supplied, owner.token):
                    self._send_error_json(HTTPStatus.UNAUTHORIZED, "Invalid token.")
                    return False
                return True

            def _handle_search(self, query: str) -> None:
                params = parse_qs(query, keep_blank_values=True)
                tracking = params.get("q", [""])[0].strip()
                date_from = params.get("date_from", [""])[0].strip()
                date_to = params.get("date_to", [""])[0].strip()
                if not _valid_date(date_from) or not _valid_date(date_to):
                    self._send_error_json(HTTPStatus.BAD_REQUEST, "Date must use YYYY-MM-DD.")
                    return
                results = owner.query_manager.query(
                    tracking_number=tracking,
                    start_date=date_from,
                    end_date=date_to,
                )
                payload = [owner._public_result(result) for result in results]
                self._send_json({"ok": True, "count": len(payload), "results": payload})

            def _handle_file(self, query: str) -> None:
                params = parse_qs(query, keep_blank_values=True)
                file_type = params.get("type", [""])[0].lower()
                encoded_path = params.get("path", [""])[0]
                if file_type not in {"avi", "mp4"}:
                    self._send_error_json(HTTPStatus.BAD_REQUEST, "Invalid file type.")
                    return
                path = owner.resolve_public_path(encoded_path, file_type)
                if path is None or not path.is_file():
                    self._send_error_json(HTTPStatus.NOT_FOUND, "File not found.")
                    return
                self._send_file(path, download=params.get("download", ["0"])[0] == "1")

            def _send_static(self, name: str, content_type: str) -> None:
                target = (owner.web_root / name).resolve()
                if target.parent != owner.web_root or not target.is_file():
                    self._send_error_json(HTTPStatus.NOT_FOUND, "Asset not found.")
                    return
                data = target.read_bytes()
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(data)

            def _send_json(self, payload: dict, status: HTTPStatus = HTTPStatus.OK) -> None:
                data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(data)

            def _send_error_json(self, status: HTTPStatus, message: str) -> None:
                self._send_json({"ok": False, "error": message}, status=status)

            def _send_file(self, path: Path, download: bool) -> None:
                size = path.stat().st_size
                start, end = 0, max(0, size - 1)
                range_header = self.headers.get("Range", "")
                partial = False
                if range_header:
                    match = re.fullmatch(r"bytes=(\d*)-(\d*)", range_header.strip())
                    if not match:
                        self.send_error(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
                        return
                    if match.group(1):
                        start = int(match.group(1))
                    if match.group(2):
                        end = int(match.group(2))
                    if start > end or start >= size:
                        self.send_error(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
                        return
                    end = min(end, size - 1)
                    partial = True

                length = max(0, end - start + 1)
                self.send_response(HTTPStatus.PARTIAL_CONTENT if partial else HTTPStatus.OK)
                content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(length))
                self.send_header("Accept-Ranges", "bytes")
                if partial:
                    self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
                disposition = "attachment" if download else "inline"
                self.send_header(
                    "Content-Disposition",
                    f"{disposition}; filename*=UTF-8''{quote(path.name)}",
                )
                self.end_headers()
                with path.open("rb") as handle:
                    handle.seek(start)
                    remaining = length
                    while remaining > 0:
                        chunk = handle.read(min(1024 * 1024, remaining))
                        if not chunk:
                            break
                        self.wfile.write(chunk)
                        remaining -= len(chunk)

        return Handler

    def _public_result(self, result: dict[str, str]) -> dict[str, object]:
        avi = self._safe_existing_path(result.get("avi_path", ""), ".avi")
        mp4 = self.query_manager.resolve_mp4_path(
            avi or result.get("avi_path", ""),
            result.get("tracking_number", ""),
            recorded_mp4_path=result.get("mp4_path", ""),
        )
        return {
            "tracking_number": result.get("tracking_number", ""),
            "record_time": result.get("time", ""),
            "source": result.get("source", ""),
            "avi_path": self.public_path(avi) if avi else "",
            "mp4_path": self.public_path(mp4) if mp4 else "",
            "avi_exists": bool(avi),
            "mp4_exists": bool(mp4),
        }

    def public_path(self, path: Path) -> str:
        resolved = path.resolve()
        for index, root in enumerate(self.allowed_roots):
            try:
                relative = resolved.relative_to(root)
            except ValueError:
                continue
            return quote(f"{index}/{relative.as_posix()}", safe="/")
        return ""

    def resolve_public_path(self, encoded_path: str, file_type: str) -> Path | None:
        decoded = unquote(encoded_path or "")
        if not decoded or "\\" in decoded:
            return None
        relative = PurePosixPath(decoded)
        if relative.is_absolute() or ".." in relative.parts or len(relative.parts) < 2:
            return None
        try:
            root_index = int(relative.parts[0])
        except ValueError:
            return None
        if root_index < 0 or root_index >= len(self.allowed_roots):
            return None
        tail = relative.parts[1:]
        if self._has_sensitive_parts(tail):
            return None
        target = self.allowed_roots[root_index].joinpath(*tail).resolve()
        try:
            target.relative_to(self.allowed_roots[root_index])
        except ValueError:
            return None
        expected_suffix = f".{file_type}"
        if target.suffix.lower() != expected_suffix:
            return None
        return target

    def _safe_existing_path(self, value: str, suffix: str) -> Path | None:
        return safe_file_under_allowed_roots(value, self.allowed_roots, {suffix})

    @staticmethod
    def _has_sensitive_parts(parts) -> bool:
        lowered = {str(part).lower() for part in parts}
        if lowered & _SENSITIVE_PARTS:
            return True
        for part in lowered:
            if part in _SENSITIVE_NAMES:
                return True
            if part.startswith("license_state") or part.startswith("trial_state"):
                return True
            if part.endswith(".pem"):
                return True
        return False

    def _log(self, message: str) -> None:
        if self.logger is not None:
            try:
                self.logger(message)
            except Exception:  # noqa: BLE001
                return


def mask_token(token: str) -> str:
    value = str(token or "")
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}...{value[-4:]}"


def _valid_date(value: str) -> bool:
    if not value:
        return True
    if not _DATE_PATTERN.fullmatch(value):
        return False
    try:
        datetime.strptime(value, "%Y-%m-%d")
        return True
    except ValueError:
        return False
