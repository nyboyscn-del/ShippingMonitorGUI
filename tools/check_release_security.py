from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from safe_print import safe_print


BLOCKED_FILE_MARKERS = (
    "private_key",
    "private_key_prod.pem",
    "private_key_dev.pem",
    "license_keys",
    "license_code_generator.py",
    "issued_licenses.csv",
    "trial_state",
    "trial_state.json",
)
BLOCKED_ROOT_DIRECTORIES = ("backup", "data", "logs", "recordings")
BLOCKED_DIRECTORY_NAMES = ("evidence_packages", "license_keys")
REQUIRED_WEB_FILES = (
    Path("web/lan_query/index.html"),
    Path("web/lan_query/style.css"),
    Path("web/lan_query/app.js"),
)
REQUIRED_ERP_TEMPLATE_FILES = (
    Path("erp_import_template.csv"),
    Path("erp_import_template.xlsx"),
)
PRIVATE_KEY_BLOCK_PATTERNS = (
    re.compile(
        rb"-----BEGIN PRIVATE KEY-----\s+[A-Za-z0-9+/=\s]+-----END PRIVATE KEY-----",
        re.DOTALL,
    ),
    re.compile(
        rb"-----BEGIN RSA PRIVATE KEY-----\s+[A-Za-z0-9+/=\s]+-----END RSA PRIVATE KEY-----",
        re.DOTALL,
    ),
)


def iter_files(root: Path):
    if not root.exists():
        return
    for path in root.rglob("*"):
        if path.is_file():
            yield path


def check_release(root: Path) -> list[str]:
    findings: list[str] = []
    for required in REQUIRED_WEB_FILES:
        candidates = (root / required, root / "_internal" / required)
        if not any(candidate.is_file() for candidate in candidates):
            findings.append(f"required LAN query web file missing: {required}")
    for required in REQUIRED_ERP_TEMPLATE_FILES:
        candidates = (
            root / "templates" / required,
            root / "_internal" / "templates" / required,
        )
        if not any(candidate.is_file() for candidate in candidates):
            findings.append(f"required ERP template missing: templates/{required}")

    for path in root.rglob("*"):
        if not path.is_dir():
            continue
        relative = path.relative_to(root)
        if path.name.lower() in BLOCKED_DIRECTORY_NAMES:
            findings.append(f"blocked sensitive directory: {relative}")
        elif len(relative.parts) == 1 and path.name.lower() in BLOCKED_ROOT_DIRECTORIES:
            findings.append(f"blocked runtime directory: {relative}")

    for path in iter_files(root):
        relative = path.relative_to(root)
        lowered = str(relative).lower()
        name = path.name.lower()
        if name == "license.json":
            findings.append(f"legacy release license file: {relative}")
            continue
        if name.startswith("license_state") and name.endswith(".json"):
            findings.append(f"local activation state file: {relative}")
            continue
        if name.startswith("trial_state") and name.endswith(".json"):
            findings.append(f"local trial state file: {relative}")
            continue
        if path.suffix.lower() == ".pem":
            findings.append(f"blocked PEM file: {relative}")
            continue
        if any(marker in lowered for marker in BLOCKED_FILE_MARKERS):
            findings.append(f"blocked file marker: {relative}")
            continue
        try:
            content = path.read_bytes()
        except OSError as exc:
            findings.append(f"read failed: {relative}: {exc}")
            continue
        if any(pattern.search(content) for pattern in PRIVATE_KEY_BLOCK_PATTERNS):
            findings.append(f"blocked private key content: {relative}")

    config_candidates = (
        root / "config" / "config.json",
        root / "_internal" / "config" / "config.json",
    )
    existing_configs = [path for path in config_candidates if path.is_file()]
    if not existing_configs:
        findings.append("packaged config status: MISSING")
    for config_path in existing_configs:
        relative = config_path.relative_to(root)
        try:
            config = json.loads(config_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            findings.append(f"lan_query_token status: MASKED (unreadable config: {relative})")
            continue
        token = str(config.get("lan_query_token", "") or "").strip()
        if token:
            findings.append(f"lan_query_token status: CONFIGURED ({relative})")
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description="Check ShippingMonitorGUI release output for supplier-only license secrets.")
    parser.add_argument("--root", default="dist", help="Release output directory to inspect.")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    if not root.exists():
        safe_print(f"FAIL: release path does not exist: {root}")
        return 1

    findings = check_release(root)
    if findings:
        safe_print("FAIL: sensitive supplier files or key material were found.")
        for finding in findings:
            safe_print("- " + finding)
        return 1

    safe_print(f"PASS: release security checks passed under {root}; lan_query_token status: EMPTY")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
