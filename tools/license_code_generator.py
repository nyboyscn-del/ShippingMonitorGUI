from __future__ import annotations

import argparse
import csv
import hashlib
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

try:
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding, rsa
except ImportError:  # pragma: no cover - validated by supplier CLI message
    hashes = None
    serialization = None
    padding = None
    rsa = None


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from license_code_manager import (  # noqa: E402
    CODE_PREFIX,
    DEFAULT_FEATURES,
    LICENSE_VERSION,
    PRODUCT,
    _b64url_encode,
    _canonical_json_bytes,
    normalize_machine_code,
)


KEY_DIR = PROJECT_ROOT / "tools" / "license_keys"
PRIVATE_KEY_PROD_PATH = KEY_DIR / "private_key_prod.pem"
PUBLIC_KEY_PROD_PATH = KEY_DIR / "public_key_prod.pem"
PRIVATE_KEY_DEV_PATH = KEY_DIR / "private_key_dev.pem"
PUBLIC_KEY_DEV_PATH = KEY_DIR / "public_key_dev.pem"
ISSUED_LICENSES_PATH = PROJECT_ROOT / "tools" / "issued_licenses.csv"


def require_cryptography() -> None:
    if serialization is None or padding is None or hashes is None or rsa is None:
        raise RuntimeError("cryptography dependency is unavailable; RSA authorization code generation cannot run.")


def ensure_dev_keys() -> tuple[Path, Path]:
    require_cryptography()
    KEY_DIR.mkdir(parents=True, exist_ok=True)
    if PRIVATE_KEY_DEV_PATH.exists() and PUBLIC_KEY_DEV_PATH.exists():
        return PRIVATE_KEY_DEV_PATH, PUBLIC_KEY_DEV_PATH

    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    PRIVATE_KEY_DEV_PATH.write_bytes(
        private_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    PUBLIC_KEY_DEV_PATH.write_bytes(
        private_key.public_key().public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )
    print("[WARN] New development RSA keys were generated.")
    print("[WARN] Embed the matching public key into src/license_code_manager.py before using these codes.")
    return PRIVATE_KEY_DEV_PATH, PUBLIC_KEY_DEV_PATH


def select_key_paths(use_dev_key: bool) -> tuple[Path, str]:
    require_cryptography()
    if use_dev_key:
        private_path, _public_path = ensure_dev_keys()
        return private_path, "dev"
    if not PRIVATE_KEY_PROD_PATH.exists():
        raise FileNotFoundError("请先生成正式生产密钥 private_key_prod.pem")
    return PRIVATE_KEY_PROD_PATH, "prod"


def _now_local() -> datetime:
    return datetime.now().astimezone()


def _parse_expires_at(value: str) -> str:
    text = value.strip().replace("Z", "+00:00")
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        raise ValueError("--expires-at must include a timezone.")
    return parsed.isoformat()


def build_payload(args: argparse.Namespace) -> dict[str, Any]:
    issued_at = _now_local()
    if args.edition == "permanent":
        if args.days is not None or args.expires_at:
            raise ValueError("Permanent authorization must not use --days or --expires-at.")
        expires_at = None
    elif args.expires_at:
        expires_at = _parse_expires_at(args.expires_at)
    elif args.days is not None:
        expires_at = (issued_at + timedelta(days=args.days)).isoformat()
    else:
        raise ValueError("Trial and standard authorization require --days or --expires-at.")

    return {
        "license_version": LICENSE_VERSION,
        "product": PRODUCT,
        "machine_code": normalize_machine_code(args.machine_code),
        "customer": args.customer.strip(),
        "edition": args.edition,
        "issued_at": issued_at.isoformat(),
        "expires_at": expires_at,
        "features": dict(DEFAULT_FEATURES),
        "notes": args.notes.strip(),
    }


def sign_payload(payload: dict[str, Any], use_dev_key: bool = False) -> tuple[str, str]:
    require_cryptography()
    private_path, key_type = select_key_paths(use_dev_key)
    private_key = serialization.load_pem_private_key(private_path.read_bytes(), password=None)
    payload_bytes = _canonical_json_bytes(payload)
    signature = private_key.sign(
        payload_bytes,
        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
        hashes.SHA256(),
    )
    code = f"{CODE_PREFIX}.{_b64url_encode(payload_bytes)}.{_b64url_encode(signature)}"
    return code, key_type


def append_issue_record(payload: dict[str, Any], code_hash: str, key_type: str) -> None:
    ISSUED_LICENSES_PATH.parent.mkdir(parents=True, exist_ok=True)
    fields = ["issued_at", "customer", "machine_code", "edition", "expires_at", "code_hash", "notes", "key_type"]
    if ISSUED_LICENSES_PATH.exists():
        with ISSUED_LICENSES_PATH.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames and "key_type" not in reader.fieldnames:
                old_rows = list(reader)
                with ISSUED_LICENSES_PATH.open("w", encoding="utf-8", newline="") as target:
                    writer = csv.DictWriter(target, fieldnames=fields)
                    writer.writeheader()
                    for row in old_rows:
                        row["key_type"] = ""
                        writer.writerow({field: row.get(field, "") for field in fields})
    write_header = not ISSUED_LICENSES_PATH.exists()
    with ISSUED_LICENSES_PATH.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        if write_header:
            writer.writeheader()
        writer.writerow(
            {
                "issued_at": payload["issued_at"],
                "customer": payload["customer"],
                "machine_code": payload["machine_code"],
                "edition": payload["edition"],
                "expires_at": payload["expires_at"] or "",
                "code_hash": code_hash,
                "notes": payload["notes"],
                "key_type": key_type,
            }
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Supplier-only ShippingMonitorGUI license generator")
    parser.add_argument("--machine-code", required=True, help="Target machine SHA256 code.")
    parser.add_argument("--customer", required=True, help="Customer display name.")
    parser.add_argument("--edition", choices=("trial", "standard", "permanent"), required=True)
    parser.add_argument("--days", type=int, help="Days from issued_at until expiry.")
    parser.add_argument("--expires-at", help="Explicit ISO expiry timestamp with timezone.")
    parser.add_argument("--notes", default="", help="Optional supplier note for issue record.")
    parser.add_argument("--dev-key", action="store_true", help="Explicitly use the development private key.")
    args = parser.parse_args(argv)

    try:
        payload = build_payload(args)
        authorization_code, key_type = sign_payload(payload, use_dev_key=args.dev_key)
    except Exception as exc:  # noqa: BLE001
        print(f"error={exc}", file=sys.stderr)
        return 1

    code_hash = hashlib.sha256(authorization_code.encode("utf-8")).hexdigest()
    append_issue_record(payload, code_hash, key_type)
    print("authorization_code=" + authorization_code)
    print("customer=" + payload["customer"])
    print("edition=" + payload["edition"])
    print("expires_at=" + (payload["expires_at"] or "--"))
    print("code_hash=" + code_hash)
    print("key_type=" + key_type)
    print("issued_licenses=" + str(ISSUED_LICENSES_PATH))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
