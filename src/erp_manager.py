from __future__ import annotations

import csv
from pathlib import Path
from typing import Iterable

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, PatternFill


ERP_IMPORT_FIELDS = [
    "order_no",
    "tracking_number",
    "shop_name",
    "buyer_name",
    "sku",
    "product_name",
    "quantity",
    "remark",
]

ERP_EXPORT_FIELDS = [
    "order_no",
    "tracking_number",
    "record_time",
    "source",
    "shop_name",
    "buyer_name",
    "sku",
    "product_name",
    "quantity",
    "avi_path",
    "mp4_path",
    "label_image_path",
    "evidence_package_path",
    "shared_storage_path",
    "status",
    "remark",
]

FORMULA_PREFIXES = ("=", "+", "-", "@")


def safe_spreadsheet_text(value: object) -> str:
    text = "" if value is None else str(value).strip()
    if text.lstrip().startswith(FORMULA_PREFIXES):
        return "'" + text
    return text


class ERPManager:
    def __init__(self, storage_path: str | Path) -> None:
        self.storage_path = Path(storage_path)

    def import_orders(self, source_path: str | Path) -> dict[str, object]:
        source = Path(source_path)
        if source.suffix.lower() not in {".csv", ".xlsx"}:
            raise ValueError("ERP 导入仅支持 CSV 或 XLSX 文件")
        if not source.is_file():
            raise FileNotFoundError(f"ERP 导入文件不存在：{source}")

        rows = self._read_csv(source) if source.suffix.lower() == ".csv" else self._read_excel(source)
        if not rows:
            raise ValueError("ERP 导入文件没有数据")
        if "order_no" not in rows[0]:
            raise ValueError("ERP 导入缺少必需字段：order_no")
        missing_fields = [field for field in ERP_IMPORT_FIELDS if field not in rows[0]]

        imported: list[dict[str, str]] = []
        skipped = 0
        for raw in rows:
            record = {field: safe_spreadsheet_text(raw.get(field, "")) for field in ERP_IMPORT_FIELDS}
            if not record["order_no"]:
                skipped += 1
                continue
            record["tracking_number"] = record["tracking_number"].replace("\r", "").replace("\n", "").replace("\t", "").upper()
            imported.append(record)
        if not imported:
            raise ValueError("ERP 导入没有有效订单：order_no 不能为空")

        existing = {row["order_no"]: row for row in self.load_orders() if row.get("order_no")}
        for record in imported:
            existing[record["order_no"]] = record
        self._save_orders(existing.values())
        return {
            "imported": len(imported),
            "skipped": skipped,
            "total": len(existing),
            "missing_fields": missing_fields,
        }

    def load_orders(self) -> list[dict[str, str]]:
        if not self.storage_path.is_file():
            return []
        rows = self._read_excel(self.storage_path)
        return [
            {field: safe_spreadsheet_text(row.get(field, "")) for field in ERP_IMPORT_FIELDS}
            for row in rows
            if safe_spreadsheet_text(row.get("order_no", ""))
        ]

    def export_evidence_results(
        self,
        results: list[dict[str, str]],
        output_path: str | Path,
    ) -> Path:
        output = Path(output_path)
        if output.suffix.lower() not in {".csv", ".xlsx"}:
            raise ValueError("ERP 留证结果仅支持 CSV 或 XLSX 文件")

        orders = self.load_orders()
        by_tracking = {
            row["tracking_number"].upper(): row
            for row in orders
            if row.get("tracking_number")
        }
        by_order = {row["order_no"]: row for row in orders if row.get("order_no")}
        export_rows: list[dict[str, str]] = []
        for result in results:
            tracking = safe_spreadsheet_text(result.get("tracking_number", "")).upper()
            order_no = safe_spreadsheet_text(result.get("order_no", ""))
            order = by_tracking.get(tracking) or by_order.get(order_no) or {}
            export_rows.append(
                {
                    "order_no": order.get("order_no", order_no),
                    "tracking_number": tracking,
                    "record_time": result.get("record_time", result.get("time", "")),
                    "source": result.get("source", ""),
                    "shop_name": order.get("shop_name", ""),
                    "buyer_name": order.get("buyer_name", ""),
                    "sku": order.get("sku", ""),
                    "product_name": order.get("product_name", ""),
                    "quantity": order.get("quantity", ""),
                    "avi_path": result.get("avi_path", ""),
                    "mp4_path": result.get("mp4_path", ""),
                    "label_image_path": result.get("label_image_path", ""),
                    "evidence_package_path": result.get("evidence_package_path", ""),
                    "shared_storage_path": result.get("shared_storage_path", ""),
                    "status": result.get("status", ""),
                    "remark": result.get("remark", order.get("remark", "")),
                }
            )

        output.parent.mkdir(parents=True, exist_ok=True)
        if output.suffix.lower() == ".csv":
            self._write_csv(output, ERP_EXPORT_FIELDS, export_rows)
        else:
            self._write_excel(output, ERP_EXPORT_FIELDS, export_rows, "evidence_results")
        return output

    @staticmethod
    def generate_template(output_path: str | Path) -> Path:
        output = Path(output_path)
        if output.suffix.lower() not in {".csv", ".xlsx"}:
            raise ValueError("ERP 模板仅支持 CSV 或 XLSX 文件")
        sample = {
            "order_no": "DEMO-ORDER-001",
            "tracking_number": "SF1234567890",
            "shop_name": "示例店铺",
            "buyer_name": "示例客户",
            "sku": "SKU-DEMO-001",
            "product_name": "示例商品",
            "quantity": "1",
            "remark": "仅为模板示例，请替换",
        }
        output.parent.mkdir(parents=True, exist_ok=True)
        if output.suffix.lower() == ".csv":
            ERPManager._write_csv(output, ERP_IMPORT_FIELDS, [sample])
        else:
            ERPManager._write_excel(output, ERP_IMPORT_FIELDS, [sample], "erp_orders")
        return output

    def _save_orders(self, rows: Iterable[dict[str, str]]) -> None:
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        self._write_excel(self.storage_path, ERP_IMPORT_FIELDS, list(rows), "erp_orders")

    @staticmethod
    def _read_csv(path: Path) -> list[dict[str, str]]:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if not reader.fieldnames:
                return []
            headers = [str(field or "").strip() for field in reader.fieldnames]
            return [
                {
                    header: safe_spreadsheet_text(row.get(original, ""))
                    for original, header in zip(reader.fieldnames, headers)
                    if header
                }
                for row in reader
            ]

    @staticmethod
    def _read_excel(path: Path) -> list[dict[str, str]]:
        workbook = load_workbook(path, read_only=True, data_only=False, keep_links=False)
        try:
            sheet = workbook.active
            rows = sheet.iter_rows(values_only=True)
            headers = [str(value or "").strip() for value in next(rows, ())]
            return [
                {
                    header: safe_spreadsheet_text(row[index] if index < len(row) else "")
                    for index, header in enumerate(headers)
                    if header
                }
                for row in rows
            ]
        finally:
            workbook.close()

    @staticmethod
    def _write_csv(path: Path, fields: list[str], rows: Iterable[dict[str, str]]) -> None:
        with path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(fields)
            for row in rows:
                writer.writerow([safe_spreadsheet_text(row.get(field, "")) for field in fields])

    @staticmethod
    def _write_excel(
        path: Path,
        fields: list[str],
        rows: Iterable[dict[str, str]],
        sheet_name: str,
    ) -> None:
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = sheet_name
        sheet.append(fields)
        for row in rows:
            sheet.append([safe_spreadsheet_text(row.get(field, "")) for field in fields])
        header_fill = PatternFill("solid", fgColor="1F4E78")
        for cell in sheet[1]:
            cell.font = Font(color="FFFFFF", bold=True)
            cell.fill = header_fill
        sheet.freeze_panes = "A2"
        sheet.auto_filter.ref = sheet.dimensions
        for column in sheet.columns:
            longest = max((len(str(cell.value or "")) for cell in column), default=0)
            sheet.column_dimensions[column[0].column_letter].width = min(max(longest + 2, 12), 36)
        workbook.save(path)
        workbook.close()
