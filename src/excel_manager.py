from __future__ import annotations

import csv
import logging
from datetime import datetime
from pathlib import Path

from openpyxl import Workbook, load_workbook

from query_manager import get_invalid_tracking_reason, normalize_tracking_number


HEADERS = ["time", "tracking_number", "video_path", "source", "remark", "label_image_path"]


class ExcelManager:
    def __init__(self, excel_path: str | Path):
        self.excel_path = Path(excel_path)
        self.excel_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_workbook()

    def _ensure_workbook(self) -> None:
        if self.excel_path.exists():
            workbook = load_workbook(self.excel_path)
            try:
                sheet = workbook.active
                headers = [str(cell.value or "").strip() for cell in sheet[1]]
                if "label_image_path" not in headers:
                    sheet.cell(row=1, column=len(headers) + 1, value="label_image_path")
                    workbook.save(self.excel_path)
                    logging.info("Added label_image_path column: %s", self.excel_path)
            finally:
                workbook.close()
            return

        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "scan_records"
        sheet.append(HEADERS)
        workbook.save(self.excel_path)
        logging.info("Created Excel file: %s", self.excel_path)

    def append_record(
        self,
        tracking_number: str,
        video_path: str | Path,
        source: str = "keyboard",
        remark: str = "",
        timestamp: datetime | None = None,
        label_image_path: str | Path | None = None,
    ) -> str:
        normalized_tracking = normalize_tracking_number(tracking_number)
        invalid_reason = get_invalid_tracking_reason(normalized_tracking)
        if invalid_reason:
            raise ValueError(f"Invalid tracking number: {invalid_reason}")
        timestamp = timestamp or datetime.now()
        row = [
            timestamp.strftime("%Y-%m-%d %H:%M:%S"),
            normalized_tracking,
            str(video_path),
            source,
            remark,
            str(label_image_path or ""),
        ]
        try:
            workbook = load_workbook(self.excel_path)
            sheet = workbook.active
            if sheet.max_row == 0:
                sheet.append(HEADERS)
            sheet.append(row)
            workbook.save(self.excel_path)
            logging.info("Excel record appended: %s", normalized_tracking)
            return "excel"
        except PermissionError:
            logging.exception("Excel file is busy, writing backup CSV record: %s", tracking_number)
            self._append_backup_csv(row)
            print(f"Excel file is busy. Record was saved to backup CSV: {self._backup_csv_path()}")
            return "backup_csv"
        except Exception:
            logging.exception("Failed to append Excel record, writing backup CSV record: %s", tracking_number)
            self._append_backup_csv(row)
            print(f"Excel write failed. Record was saved to backup CSV: {self._backup_csv_path()}")
            return "backup_csv"

    def update_label_image_path(
        self,
        tracking_number: str,
        video_path: str | Path,
        label_image_path: str | Path,
    ) -> bool:
        normalized_tracking = normalize_tracking_number(tracking_number)
        expected_video = str(Path(video_path))
        workbook = load_workbook(self.excel_path)
        try:
            sheet = workbook.active
            headers = [str(cell.value or "").strip() for cell in sheet[1]]
            tracking_column = headers.index("tracking_number") + 1
            video_column = headers.index("video_path") + 1
            label_column = headers.index("label_image_path") + 1
            for row_index in range(sheet.max_row, 1, -1):
                row_tracking = normalize_tracking_number(sheet.cell(row=row_index, column=tracking_column).value)
                row_video = str(sheet.cell(row=row_index, column=video_column).value or "")
                if row_tracking == normalized_tracking and row_video == expected_video:
                    sheet.cell(row=row_index, column=label_column, value=str(label_image_path))
                    workbook.save(self.excel_path)
                    logging.info("Excel label image path updated: %s", normalized_tracking)
                    return True
            return False
        finally:
            workbook.close()

    def _backup_csv_path(self) -> Path:
        return self.excel_path.with_name(self.excel_path.stem + "_backup.csv")

    def _append_backup_csv(self, row: list[str]) -> None:
        backup_path = self._backup_csv_path()
        write_headers = not backup_path.exists()
        with backup_path.open("a", newline="", encoding="utf-8-sig") as handle:
            writer = csv.writer(handle)
            if write_headers:
                writer.writerow(HEADERS)
            writer.writerow(row)
