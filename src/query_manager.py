from __future__ import annotations

import csv
import json
import logging
import re
import shutil
import sys
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

from openpyxl import Workbook, load_workbook

try:
    import cv2
except ImportError:  # pragma: no cover - depends on local runtime
    cv2 = None

from recording_manager import build_mp4_path, convert_avi_to_mp4


# TESING PREFIXES TO EXCLUDE (test/smoke/demo/debug/auto/dummy)
_TEST_PREFIXES = ("TEST", "DEMO", "SAMPLE", "DEBUG", "SMOKE", "GUI", "AUTO", "DUMMY")
_EVIDENCE_EXTENSIONS = {".avi", ".mp4", ".jpg", ".txt"}
_RECORDING_MEDIA_EXTENSIONS = {".avi", ".mp4", ".jpg", ".jpeg", ".png"}
_EVIDENCE_FORBIDDEN_PARTS = {
    "backup",
    "config",
    "dist",
    "license_keys",
    "release",
    "src",
    "tools",
}
_EVIDENCE_FORBIDDEN_NAMES = {
    "license.json",
    "license_code_generator.py",
    "issued_licenses.csv",
}
_FORMULA_PREFIXES = ("=", "+", "-", "@")


def _safe_export_text(value: object) -> str:
    text = "" if value is None else str(value)
    return "'" + text if text.lstrip().startswith(_FORMULA_PREFIXES) else text


def normalize_tracking_number(value: str) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip().replace("\r", "").replace("\n", "").replace("\t", "").upper()


def get_invalid_tracking_reason(value: str) -> str:
    v = normalize_tracking_number(value)
    if not v:
        return "单号为空"
    for prefix in _TEST_PREFIXES:
        if v.startswith(prefix):
            return f"包含测试标识 {prefix}"
    if re.search(r"[\u4e00-\u9fff]", v):
        return "单号不能包含中文"
    if not re.fullmatch(r"[A-Z0-9]+", v):
        return "单号包含非法字符"
    if len(v) < 8:
        return f"单号过短（{len(v)} 位），至少需要 8 位"
    if len(v) > 32:
        return f"单号过长（{len(v)} 位），最多支持 32 位"
    if v.isdigit():
        if 10 <= len(v) <= 20:
            return ""
        return "纯数字单号应为 10-20 位"
    if not any(char.isdigit() for char in v):
        return "单号必须包含数字"
    return ""


def is_valid_tracking_number(value: str) -> bool:
    """Validate and normalize common logistics tracking-number formats."""
    return get_invalid_tracking_reason(value) == ""


def get_allowed_recording_roots(
    configured_roots: list[str | Path] | tuple[str | Path, ...] | None = None,
) -> tuple[Path, ...]:
    runtime_dir = (
        Path(sys.executable).resolve().parent
        if getattr(sys, "frozen", False)
        else Path(__file__).resolve().parents[1]
    )
    candidates = [runtime_dir / "recordings"]
    candidates.extend(Path(root) for root in (configured_roots or ()))
    roots: list[Path] = []
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved not in roots:
            roots.append(resolved)
    return tuple(roots)


def safe_file_under_allowed_roots(
    value: str | Path,
    allowed_roots: tuple[Path, ...] | list[Path],
    allowed_extensions: set[str] | tuple[str, ...],
) -> Path | None:
    raw = Path(value)
    if not str(value or "").strip() or ".." in raw.parts:
        return None
    candidates = [raw] if raw.is_absolute() else [Path(root) / raw for root in allowed_roots]
    extensions = {extension.lower() for extension in allowed_extensions}
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
        except OSError:
            continue
        if resolved.suffix.lower() not in extensions or not resolved.is_file():
            continue
        for root in allowed_roots:
            try:
                relative = resolved.relative_to(Path(root).resolve())
            except (OSError, ValueError):
                continue
            if QueryManager._is_forbidden_relative_path(relative):
                continue
            return resolved
    return None


@dataclass(frozen=True)
class QueryResult:
    time: str
    tracking_number: str
    avi_path: str
    mp4_path: str
    label_image_path: str
    status: str
    source: str
    remark: str = ""

    def to_json_dict(self) -> dict[str, str]:
        return asdict(self)


class QueryManager:
    def __init__(
        self,
        excel_path: str | Path,
        mp4_folder_name: str = "MP4",
        allowed_roots: list[str | Path] | None = None,
        evidence_output_dir: str | Path | None = None,
    ) -> None:
        self.excel_path = Path(excel_path)
        self.mp4_folder_name = mp4_folder_name or "MP4"
        self.logger = logging.getLogger(__name__)
        runtime_dir = (
            Path(sys.executable).resolve().parent
            if getattr(sys, "frozen", False)
            else Path(__file__).resolve().parents[1]
        )
        self.allowed_roots = get_allowed_recording_roots(allowed_roots)
        output = Path(evidence_output_dir) if evidence_output_dir else runtime_dir / "evidence_packages"
        self.evidence_output_dir = output.resolve()

    def query(
        self,
        tracking_number: str = "",
        start_date: str = "",
        end_date: str = "",
        source: str = "",
    ) -> list[dict[str, str]]:
        needle = normalize_tracking_number(tracking_number)
        source_filter = self._normalize_source(source)
        start = self._parse_date(start_date, end_of_day=False)
        end = self._parse_date(end_date, end_of_day=True)
        self._log(
            "query start: "
            f"excel_path={self.excel_path}, tracking_number={needle or '*'}, "
            f"start_date={start_date or '*'}, end_date={end_date or '*'}, source={source_filter or '*'}"
        )
        if not self.excel_path.exists():
            self._log(f"query source missing: {self.excel_path}")
            return []

        workbook = load_workbook(self.excel_path, read_only=True, data_only=True)
        try:
            sheet = workbook.active
            rows = list(sheet.iter_rows(values_only=True))
        finally:
            workbook.close()
        if not rows:
            self._log(f"query source empty: {self.excel_path}")
            return []

        headers = [str(value or "").strip() for value in rows[0]]
        self._log(f"query source loaded: rows={max(0, len(rows) - 1)}, headers={headers}")
        results: list[dict[str, str]] = []
        raw_count = 0
        valid_count = 0
        for row in rows[1:]:
            record = self._row_to_record(headers, row)
            if not any(value.strip() for value in record.values()):
                continue
            raw_count += 1
            row_tracking = normalize_tracking_number(record.get("tracking_number", ""))
            # Use is_valid_tracking_number to filter test numbers
            if not is_valid_tracking_number(row_tracking):
                continue
            valid_count += 1
            if needle and needle not in row_tracking:
                continue
            row_time = record.get("time", "").strip()
            row_datetime = self._parse_record_time(row_time)
            if start and (row_datetime is None or row_datetime < start):
                continue
            if end and (row_datetime is None or row_datetime > end):
                continue
            row_source = self._normalize_source(record.get("source", ""))
            if source_filter and row_source != source_filter:
                continue

            raw_avi_path = self._record_video_path(record)
            mp4_record_path = record.get("mp4_path", "").strip()
            avi_path = self.resolve_existing_media_path(raw_avi_path, {".avi"})
            mp4_path = self.resolve_mp4_path(
                avi_path or raw_avi_path,
                row_tracking,
                recorded_mp4_path=mp4_record_path,
            )
            raw_label_path = record.get("label_image_path", "").strip()
            label_path = self.resolve_label_image_path(
                avi_path or raw_avi_path,
                recorded_label_path=raw_label_path,
            )
            result = QueryResult(
                time=row_time,
                tracking_number=row_tracking,
                avi_path=str(avi_path) if avi_path else raw_avi_path,
                mp4_path=str(mp4_path) if mp4_path else "",
                label_image_path=str(label_path) if label_path else raw_label_path,
                status="recorded" if avi_path else "missing_avi",
                source=row_source,
                remark=record.get("remark", ""),
            )
            results.append(result.to_json_dict())
        self._log(f"query finished: raw={raw_count}, valid={valid_count}, results={len(results)}")
        return results

    def search_by_tracking_number(self, number: str) -> list[dict[str, str]]:
        self._log(f"search_by_tracking_number: number={number}")
        return self.query(tracking_number=number)

    def search_by_date_range(self, start: str, end: str) -> list[dict[str, str]]:
        self._log(f"search_by_date_range: start={start}, end={end}")
        return self.query(start_date=start, end_date=end)

    def search_by_source(self, source: str) -> list[dict[str, str]]:
        self._log(f"search_by_source: source={source}")
        return self.query(source=source)

    def search_many(self, numbers: list[str]) -> list[dict[str, str]]:
        wanted = {number.strip() for number in numbers if number.strip()}
        if not wanted:
            return []
        return [result for result in self.query() if result.get("tracking_number", "") in wanted]

    def get_video_path(self, number: str) -> dict[str, str]:
        results = self.search_by_tracking_number(number)
        return results[-1] if results else {}

    def query_json(
        self,
        tracking_number: str = "",
        start_date: str = "",
        end_date: str = "",
        source: str = "",
    ) -> str:
        return json.dumps(
            self.query(tracking_number, start_date, end_date, source),
            ensure_ascii=False,
            indent=2,
        )

    def export_csv(self, results: list[dict[str, str]], output_path: str | Path) -> Path:
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)

        headers_cn = [
            "\u65f6\u95f4",
            "\u5355\u53f7",
            "\u72b6\u6001",
            "\u6765\u6e90",
            "AVI\u8def\u5f84",
            "MP4\u8def\u5f84",
            "\u9762\u5355\u622a\u56fe\u8def\u5f84",
            "\u5907\u6ce8",
        ]
        with output.open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.writer(handle)
            writer.writerow(headers_cn)
            for result in results:
                row = [
                    _safe_export_text(result.get("time", "")),
                    _safe_export_text(result.get("tracking_number", "")),
                    _safe_export_text(result.get("status", "")),
                    _safe_export_text(result.get("source", "")),
                    _safe_export_text(result.get("avi_path", "")),
                    _safe_export_text(result.get("mp4_path", "")),
                    _safe_export_text(result.get("label_image_path", "")),
                    _safe_export_text(result.get("remark", "")),
                ]
                writer.writerow(row)
        return output

    def export_excel(self, results: list[dict[str, str]], output_path: str | Path) -> Path:
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "query_results"
        headers_cn = [
            "\u65f6\u95f4",
            "\u5355\u53f7",
            "\u72b6\u6001",
            "\u6765\u6e90",
            "AVI\u8def\u5f84",
            "MP4\u8def\u5f84",
            "\u9762\u5355\u622a\u56fe\u8def\u5f84",
            "\u5907\u6ce8",
        ]
        sheet.append(headers_cn)
        for result in results:
            row = [
                _safe_export_text(result.get("time", "")),
                _safe_export_text(result.get("tracking_number", "")),
                _safe_export_text(result.get("status", "")),
                _safe_export_text(result.get("source", "")),
                _safe_export_text(result.get("avi_path", "")),
                _safe_export_text(result.get("mp4_path", "")),
                _safe_export_text(result.get("label_image_path", "")),
                _safe_export_text(result.get("remark", "")),
            ]
            sheet.append(row)
        # Set tracking number column (column B, index 2) to text format
        from openpyxl.styles import numbers
        for row in range(2, sheet.max_row + 1):
            cell = sheet.cell(row=row, column=2)
            cell.number_format = '@'
        workbook.save(output)
        return output

    def export_json(self, results: list[dict[str, str]], output_path: str | Path) -> Path:
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
        return output

    def create_evidence_package(
        self,
        record: dict[str, str],
    ) -> tuple[Path, dict[str, object]]:
        tracking_number = normalize_tracking_number(record.get("tracking_number", ""))
        if not tracking_number:
            raise ValueError("记录缺少物流单号")
        safe_tracking = re.sub(r"[^A-Z0-9_-]+", "_", tracking_number).strip("_")
        if not safe_tracking:
            raise ValueError("物流单号无法用于证据包目录名")

        record_time = str(record.get("time") or record.get("record_time") or "").strip()
        time_stamp = self._evidence_time_stamp(record_time)
        self.evidence_output_dir.mkdir(parents=True, exist_ok=True)
        package_dir = self._unique_directory(self.evidence_output_dir / f"{safe_tracking}_{time_stamp}")
        package_dir.mkdir(parents=False, exist_ok=False)

        avi_path = self.resolve_existing_media_path(record.get("avi_path", ""), {".avi"})
        mp4_path = self.resolve_mp4_path(
            avi_path or record.get("avi_path", ""),
            tracking_number,
            recorded_mp4_path=record.get("mp4_path", ""),
        )
        label_path = self.resolve_label_image_path(
            avi_path or record.get("avi_path", ""),
            recorded_label_path=record.get("label_image_path", ""),
        )
        source_fields = {
            "AVI": (avi_path, f"{safe_tracking}.avi"),
            "MP4": (mp4_path, f"{safe_tracking}.mp4"),
            "面单截图": (
                label_path,
                f"{safe_tracking}_label{label_path.suffix.lower() if label_path else '.jpg'}",
            ),
        }
        included: dict[str, bool] = {}
        source_paths: dict[str, str] = {}
        notes: list[str] = []

        try:
            for label, (source, destination_name) in source_fields.items():
                raw_path = str(source or "").strip()
                source_paths[label] = raw_path
                if source is None:
                    included[label] = False
                    notes.append(f"{label} 文件不存在")
                    continue
                shutil.copy2(source, package_dir / destination_name)
                included[label] = True

            exported_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            missing_text = "\n".join(f"- {note}" for note in notes) if notes else "- 无"
            summary = (
                f"物流单号：{tracking_number}\n"
                f"记录时间：{record_time or '未记录'}\n"
                f"AVI 是否包含：{'是' if included.get('AVI') else '否'}\n"
                f"MP4 是否包含：{'是' if included.get('MP4') else '否'}\n"
                f"面单截图是否包含：{'是' if included.get('面单截图') else '否'}\n"
                f"原始 AVI 路径：{source_paths.get('AVI') or '未记录'}\n"
                f"原始 MP4 路径：{source_paths.get('MP4') or '未记录'}\n"
                f"原始面单截图路径：{source_paths.get('面单截图') or '未记录'}\n"
                f"导出时间：{exported_at}\n"
                f"缺失文件说明：\n{missing_text}\n"
            )
            readme = (
                "本证据包为物流发货留证材料。\n"
                "AVI 为原始录像。\n"
                "MP4 为便于播放的视频，如存在。\n"
                "label.jpg 为快递面单特写截图，如存在。\n"
                "summary.txt 为记录摘要。\n"
                "文件缺失时以 summary.txt 记录为准。\n"
            )
            (package_dir / "summary.txt").write_text(summary, encoding="utf-8")
            (package_dir / "README.txt").write_text(readme, encoding="utf-8")
        except Exception:
            shutil.rmtree(package_dir, ignore_errors=True)
            raise

        result: dict[str, object] = {
            "avi_included": included.get("AVI", False),
            "mp4_included": included.get("MP4", False),
            "label_included": included.get("面单截图", False),
            "notes": notes,
        }
        return package_dir, result

    def expected_mp4_path(self, avi_path: str | Path, tracking_number: str) -> Path:
        return build_mp4_path(avi_path, tracking_number, self.mp4_folder_name)

    def existing_mp4_path(self, avi_path: str | Path, tracking_number: str) -> Path | None:
        return self.resolve_mp4_path(avi_path, tracking_number)

    def resolve_existing_media_path(
        self,
        value: str | Path,
        allowed_extensions: set[str] | tuple[str, ...] = _RECORDING_MEDIA_EXTENSIONS,
    ) -> Path | None:
        return safe_file_under_allowed_roots(value, self.allowed_roots, allowed_extensions)

    def resolve_mp4_path(
        self,
        avi_path: str | Path,
        tracking_number: str,
        recorded_mp4_path: str | Path = "",
    ) -> Path | None:
        candidates: list[Path] = []
        if str(recorded_mp4_path or "").strip():
            candidates.append(Path(recorded_mp4_path))
        if str(avi_path or "").strip():
            avi = Path(avi_path)
            candidates.extend(
                (
                    avi.with_suffix(".mp4"),
                    self.expected_mp4_path(avi, tracking_number),
                )
            )
        for candidate in candidates:
            resolved = self.resolve_existing_media_path(candidate, {".mp4"})
            if resolved is not None:
                return resolved
        return None

    def resolve_label_image_path(
        self,
        avi_path: str | Path,
        recorded_label_path: str | Path = "",
    ) -> Path | None:
        candidates: list[Path] = []
        if str(recorded_label_path or "").strip():
            candidates.append(Path(recorded_label_path))
        if str(avi_path or "").strip():
            avi = Path(avi_path)
            candidates.extend(
                avi.with_name(f"{avi.stem}_label{suffix}")
                for suffix in (".jpg", ".jpeg", ".png")
            )
        for candidate in candidates:
            resolved = self.resolve_existing_media_path(candidate, {".jpg", ".jpeg", ".png"})
            if resolved is not None:
                return resolved
        return None

    def ensure_mp4(self, avi_path: str | Path, tracking_number: str) -> Path:
        avi = Path(avi_path)
        if not avi.exists():
            raise FileNotFoundError(f"AVI file not found: {avi}")

        mp4 = self.expected_mp4_path(avi, tracking_number)
        if mp4.exists():
            return mp4

        return convert_avi_to_mp4(avi, mp4, logger=self._log)

    _HEADER_ALIASES: dict[str, str] = {
        "\u65f6\u95f4": "time",
        "\u7269\u6d41\u5355\u53f7": "tracking_number",
        "\u89c6\u9891\u8def\u5f84": "video_path",
        "\u6765\u6e90": "source",
        "\u5907\u6ce8": "remark",
    }

    def _row_to_record(self, headers: list[str], row: tuple[object, ...]) -> dict[str, str]:
        record: dict[str, str] = {}
        for index, header in enumerate(headers):
            value = row[index] if index < len(row) else ""
            normalized = self._HEADER_ALIASES.get(header.strip(), header.strip())
            record[normalized] = str(value or "")
        return record

    def _record_video_path(self, record: dict[str, str]) -> str:
        for key in ("avi_path", "video_path", "video", "path"):
            value = record.get(key, "").strip()
            if value:
                return value
        return ""

    def _export_headers(self) -> list[str]:
        return [
            "time",
            "tracking_number",
            "status",
            "source",
            "avi_path",
            "mp4_path",
            "label_image_path",
            "remark",
        ]

    def _validated_evidence_source(self, raw_path: str, expected_extension: str) -> Path:
        resolved = self.resolve_existing_media_path(raw_path, {expected_extension})
        if resolved is not None:
            return resolved
        raise ValueError("路径不在录像白名单内或文件类型不允许")

    def _is_forbidden_evidence_path(self, path: Path) -> bool:
        for root in self.allowed_roots:
            try:
                return self._is_forbidden_relative_path(path.resolve().relative_to(root))
            except ValueError:
                continue
        return True

    @staticmethod
    def _is_forbidden_relative_path(path: Path) -> bool:
        lower_parts = {part.lower() for part in path.parts}
        name = path.name.lower()
        if lower_parts & _EVIDENCE_FORBIDDEN_PARTS:
            return True
        if name in _EVIDENCE_FORBIDDEN_NAMES:
            return True
        if name.startswith("license_state") or name.startswith("trial_state"):
            return True
        return path.suffix.lower() == ".pem"

    @staticmethod
    def _is_relative_to(path: Path, root: Path) -> bool:
        try:
            path.relative_to(root)
            return True
        except ValueError:
            return False

    @staticmethod
    def _evidence_time_stamp(record_time: str) -> str:
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S", "%Y-%m-%d"):
            try:
                return datetime.strptime(record_time, fmt).strftime("%Y%m%d_%H%M%S")
            except ValueError:
                continue
        return datetime.now().strftime("%Y%m%d_%H%M%S")

    @staticmethod
    def _unique_directory(preferred: Path) -> Path:
        if not preferred.exists():
            return preferred
        counter = 1
        while True:
            candidate = preferred.with_name(f"{preferred.name}_{counter:02d}")
            if not candidate.exists():
                return candidate
            counter += 1

    def _normalize_source(self, source: str) -> str:
        value = (source or "").strip().lower()
        mapping = {
            "gui": "GUI",
            "扫码": "扫码",
            "scanner": "扫码",
            "scan": "扫码",
            "手工": "手工",
            "manual": "手工",
            "keyboard": "手工",
        }
        return mapping.get(value, source.strip() if source else "")

    def _log(self, message: str) -> None:
        self.logger.info(message)
        print(f"[QueryManager] {message}")

    def _parse_date(self, value: str, end_of_day: bool = False) -> datetime | None:
        text = (value or "").strip()
        if not text:
            return None
        for fmt in ("%Y-%m-%d", "%Y/%m/%d"):
            try:
                parsed = datetime.strptime(text, fmt)
                if end_of_day:
                    return parsed.replace(hour=23, minute=59, second=59)
                return parsed
            except ValueError:
                continue
        return None

    def _parse_record_time(self, value: str) -> datetime | None:
        text = (value or "").strip()
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S", "%Y-%m-%d"):
            try:
                return datetime.strptime(text, fmt)
            except ValueError:
                continue
        return None
