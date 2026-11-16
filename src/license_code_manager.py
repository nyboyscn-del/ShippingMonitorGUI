from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import logging
import math
import os
import platform
import re
import subprocess
import sys
import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from safe_print import safe_print

try:
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding
except ImportError:  # pragma: no cover - validated by CLI message on machines without cryptography
    InvalidSignature = None
    hashes = None
    serialization = None
    padding = None


PRODUCT = "ShippingMonitorGUI"
LICENSE_VERSION = 1
MACHINE_CODE_VERSION = 1
CODE_PREFIX = "SMG1"
AUTHORIZATION_CODE_PATTERN = re.compile(r"SMG1\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+")
ROLLBACK_TOLERANCE = timedelta(days=1)
PROJECT_ROOT = Path(__file__).resolve().parents[1]
LICENSE_STATE_PATH = PROJECT_ROOT / "config" / "license_state.json"
TRIAL_SCHEMA_VERSION = 1
DEFAULT_TRIAL_DAYS = 30
VALID_EDITIONS = {"trial", "standard", "permanent"}
DEFAULT_FEATURES = {
    "recording": True,
    "query": True,
    "export": True,
    "camera_barcode": False,
}

PUBLIC_KEY_PEM = """-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEA1WYI59Kz0kpxVWamuXDo
iWfN9ZgR/3B2WxcmuorrWGBfMJ//UZsTqeI5skSw5P5gS11BD4l8M1S2qUpupueq
JnCFTQcX/P7CGzO9VeIVDBdclo1lUcoKgrbl89fL+XsPkKlukh/gRidAdxD6kIe+
3uE7jEnzWykHEQlPSKc+HJOe7Bg6hSzwRoF72kcY5dbTT9A1hYSLosLhiQ9Gfym3
CanzohwaDzy5Exrs0tUpPrd9rHtnShEOo7uqD5y+427+bp1Ex4Vjrxq+UyJJr9Xo
MK/ufAG6byzP0XYCpbnnAhbgDJ9KGrhJW5un0zh4E7t+LhPdg9GU8niZk/l2BbkO
yQIDAQAB
-----END PUBLIC KEY-----
"""
PUBLIC_KEY_SHA256 = "8c6d631e897f44fab7a57a2ee7ca335fb2d72854719bdf20bfcba69bd1bdfbd2"


class LicenseCodeError(ValueError):
    """Readable authorization-code parsing error."""


class LicenseStateError(ValueError):
    """Readable local license-state parsing error."""


@dataclass
class LicenseVerifyResult:
    ok: bool
    status: str
    message: str
    payload: dict[str, Any] | None = None
    expires_at: str | None = None
    customer: str | None = None
    edition: str | None = None
    features: dict[str, bool] = field(default_factory=lambda: dict(DEFAULT_FEATURES))


@dataclass
class LicenseStatus:
    ok: bool
    status: str
    message: str
    payload: dict[str, Any] | None = None
    expires_at: str | None = None
    customer: str | None = None
    edition: str | None = None
    features: dict[str, bool] = field(default_factory=lambda: dict(DEFAULT_FEATURES))
    machine_matches: bool | None = None
    state_path: str = str(LICENSE_STATE_PATH)
    trial_days_remaining: int | None = None
    trial_started_at: str | None = None


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso_now() -> str:
    return _now().isoformat()


def _runtime_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return PROJECT_ROOT


def _default_machine_code_cache_path() -> Path:
    return _runtime_root() / "config" / "machine_code_cache.json"


MACHINE_CODE_CACHE_PATH = _default_machine_code_cache_path()
_MACHINE_CODE_CACHE_LOCK = threading.Lock()


def _default_trial_primary_path() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA")
    base = Path(local_app_data) if local_app_data else Path.home() / "AppData" / "Local"
    return base / PRODUCT / "trial_state.json"


def _default_trial_backup_path() -> Path:
    return _runtime_root() / "config" / "trial_state.json"


def _canonical_json_bytes(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _b64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _b64url_decode(value: str, label: str) -> bytes:
    try:
        padded = value + "=" * (-len(value) % 4)
        return base64.urlsafe_b64decode(padded.encode("ascii"))
    except Exception as exc:  # noqa: BLE001
        raise LicenseCodeError(f"{label} is not valid base64url data.") from exc


def _read_registry_machine_guid() -> str:
    if platform.system() != "Windows":
        return ""
    try:
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Cryptography",
            0,
            winreg.KEY_READ | getattr(winreg, "KEY_WOW64_64KEY", 0),
        ) as key:
            value, _value_type = winreg.QueryValueEx(key, "MachineGuid")
            return str(value).strip()
    except Exception:  # noqa: BLE001
        return ""


def _run_hardware_query(command: list[str]) -> str:
    try:
        kwargs: dict[str, Any] = {
            "stdout": subprocess.PIPE,
            "stderr": subprocess.DEVNULL,
            "text": True,
            "timeout": 5,
            "check": False,
        }
        if platform.system() == "Windows":
            kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        completed = subprocess.run(command, **kwargs)
        if completed.returncode != 0:
            return ""
        lines = [line.strip() for line in completed.stdout.splitlines() if line.strip()]
        return lines[0] if lines else ""
    except Exception:  # noqa: BLE001
        return ""


def _powershell_cim_value(class_name: str, property_name: str) -> str:
    if platform.system() != "Windows":
        return ""
    script = (
        f"(Get-CimInstance -ClassName {class_name} -ErrorAction SilentlyContinue | "
        f"Select-Object -First 1 -ExpandProperty {property_name})"
    )
    return _run_hardware_query(["powershell", "-NoProfile", "-Command", script])


def _wmic_value(alias: str, property_name: str) -> str:
    if platform.system() != "Windows":
        return ""
    output = _run_hardware_query(["wmic", alias, "get", property_name, "/value"])
    if "=" in output:
        return output.split("=", 1)[1].strip()
    return ""


def _usable_component(value: str) -> str:
    cleaned = re.sub(r"\s+", " ", str(value or "").strip())
    if not cleaned:
        return ""
    placeholders = {
        "default string",
        "none",
        "not applicable",
        "not available",
        "system serial number",
        "to be filled by o.e.m.",
        "unknown",
    }
    return "" if cleaned.lower() in placeholders else cleaned


def _machine_components() -> dict[str, str]:
    bios_uuid = _powershell_cim_value("Win32_ComputerSystemProduct", "UUID") or _wmic_value("csproduct", "UUID")
    board_serial = _powershell_cim_value("Win32_BaseBoard", "SerialNumber") or _wmic_value(
        "baseboard", "SerialNumber"
    )
    disk_serial = _powershell_cim_value("Win32_DiskDrive", "SerialNumber") or _wmic_value(
        "diskdrive", "SerialNumber"
    )
    cpu_value = (
        _powershell_cim_value("Win32_Processor", "ProcessorId")
        or os.environ.get("PROCESSOR_IDENTIFIER", "")
        or platform.processor()
    )
    values = {
        "machine_guid": _read_registry_machine_guid(),
        "bios_uuid": bios_uuid,
        "board_serial": board_serial,
        "system_disk_serial": disk_serial,
        "cpu_or_hostname": cpu_value or os.environ.get("COMPUTERNAME", "") or platform.node(),
    }
    return {key: _usable_component(value) for key, value in values.items()}


def get_machine_code_info() -> tuple[str, bool, int]:
    components = _machine_components()
    stable_count = sum(bool(value) for key, value in components.items() if key != "cpu_or_hostname")
    payload_lines = [
        f"product={PRODUCT}",
        f"machine_code_version={MACHINE_CODE_VERSION}",
    ]
    for key in sorted(components):
        payload_lines.append(f"{key}={components[key] or '<missing>'}")
    digest = hashlib.sha256("\n".join(payload_lines).encode("utf-8")).hexdigest()
    return digest, stable_count < 2, stable_count


def _read_machine_code_cache() -> str | None:
    try:
        with MACHINE_CODE_CACHE_PATH.open("r", encoding="utf-8") as handle:
            cache = json.load(handle)
        if not isinstance(cache, dict):
            return None
        if cache.get("product") != PRODUCT:
            return None
        if cache.get("machine_code_version") != MACHINE_CODE_VERSION:
            return None
        normalized = normalize_machine_code(str(cache.get("machine_code", "")))
        return normalized
    except Exception:  # noqa: BLE001
        return None


def _write_machine_code_cache(machine_code: str) -> None:
    cache = {
        "product": PRODUCT,
        "machine_code_version": MACHINE_CODE_VERSION,
        "machine_code": machine_code,
        "created_at": _iso_now(),
    }
    try:
        MACHINE_CODE_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        temporary = MACHINE_CODE_CACHE_PATH.with_name(f"{MACHINE_CODE_CACHE_PATH.name}.tmp")
        with temporary.open("w", encoding="utf-8") as handle:
            json.dump(cache, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
        temporary.replace(MACHINE_CODE_CACHE_PATH)
    except OSError:
        return


def get_machine_code() -> str:
    # Cache the hardware fingerprint per machine so startup does not spawn
    # PowerShell queries every time. The fingerprint algorithm is untouched.
    with _MACHINE_CODE_CACHE_LOCK:
        cached = _read_machine_code_cache()
        if cached is not None:
            return cached
        machine_code, _low_stability, _stable_count = get_machine_code_info()
        _write_machine_code_cache(machine_code)
        return machine_code


def normalize_machine_code(machine_code: str) -> str:
    normalized = re.sub(r"[\s-]+", "", str(machine_code or "")).lower()
    if not re.fullmatch(r"[0-9a-f]{64}", normalized):
        raise ValueError("Machine code must be a 64-character SHA256 hexadecimal value.")
    return normalized


def format_machine_code(machine_code: str) -> str:
    normalized = normalize_machine_code(machine_code).upper()
    return "-".join(normalized[index:index + 4] for index in range(0, len(normalized), 4))


def _normalize_authorization_code(code: str) -> str:
    return re.sub(r"\s+", "", str(code or "").strip())


def extract_authorization_code(text: str) -> str:
    raw_text = str(text or "")
    match = AUTHORIZATION_CODE_PATTERN.search(raw_text)
    if match:
        return match.group(0)

    compact_text = _normalize_authorization_code(raw_text)
    match = AUTHORIZATION_CODE_PATTERN.search(compact_text)
    return match.group(0) if match else ""


def _authorization_parts(code: str) -> dict[str, Any]:
    extracted = extract_authorization_code(code)
    if not extracted:
        raise LicenseCodeError("No valid SMG1 authorization code was detected.")
    normalized = _normalize_authorization_code(extracted)
    parts = normalized.split(".")
    if len(parts) != 3 or parts[0] != CODE_PREFIX:
        raise LicenseCodeError("Authorization code format must be SMG1.payload.signature.")
    payload_bytes = _b64url_decode(parts[1], "Authorization payload")
    signature = _b64url_decode(parts[2], "Authorization signature")
    try:
        payload = json.loads(payload_bytes.decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise LicenseCodeError("Authorization payload is not valid JSON.") from exc
    if not isinstance(payload, dict):
        raise LicenseCodeError("Authorization payload must be a JSON object.")
    return {
        "normalized_code": normalized,
        "payload_b64": parts[1],
        "signature_b64": parts[2],
        "payload_bytes": payload_bytes,
        "signature": signature,
        "payload": payload,
    }


def parse_authorization_code(code: str) -> dict[str, Any]:
    return _authorization_parts(code)["payload"]


def _features_from_payload(payload: dict[str, Any]) -> dict[str, bool]:
    features = dict(DEFAULT_FEATURES)
    raw_features = payload.get("features")
    if isinstance(raw_features, dict):
        for key in features:
            if key in raw_features:
                features[key] = bool(raw_features[key])
    return features


def _validate_features(payload: dict[str, Any]) -> dict[str, bool]:
    raw_features = payload.get("features")
    if raw_features is None:
        return dict(DEFAULT_FEATURES)
    if not isinstance(raw_features, dict):
        raise ValueError("features must be a JSON object.")
    for key in DEFAULT_FEATURES:
        if key in raw_features and not isinstance(raw_features[key], bool):
            raise ValueError(f"features.{key} must be true or false.")
    return _features_from_payload(payload)


def _result(
    ok: bool,
    status: str,
    message: str,
    payload: dict[str, Any] | None = None,
    features: dict[str, bool] | None = None,
) -> LicenseVerifyResult:
    payload = payload if isinstance(payload, dict) else None
    return LicenseVerifyResult(
        ok=ok,
        status=status,
        message=message,
        payload=payload,
        expires_at=payload.get("expires_at") if payload else None,
        customer=payload.get("customer") if payload else None,
        edition=payload.get("edition") if payload else None,
        features=features or _features_from_payload(payload or {}),
    )


def _parse_datetime(value: Any, field_name: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be an ISO datetime string.")
    text = value.strip().replace("Z", "+00:00")
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        raise ValueError(f"{field_name} must include a timezone.")
    return parsed.astimezone(timezone.utc)


def _load_public_key():
    if serialization is None or padding is None or hashes is None:
        raise RuntimeError("cryptography dependency is unavailable.")
    digest = hashlib.sha256(PUBLIC_KEY_PEM.encode("ascii")).hexdigest()
    if digest != PUBLIC_KEY_SHA256:
        raise RuntimeError("Public key checksum mismatch.")
    return serialization.load_pem_public_key(PUBLIC_KEY_PEM.encode("ascii"))


def verify_authorization_code(
    code: str,
    current_machine_code: str | None = None,
    now: datetime | None = None,
) -> LicenseVerifyResult:
    try:
        parts = _authorization_parts(code)
    except LicenseCodeError as exc:
        return _result(False, "invalid_format", str(exc))

    payload = parts["payload"]
    features = _features_from_payload(payload)
    if parts["payload_bytes"] != _canonical_json_bytes(payload):
        return _result(False, "invalid_format", "Authorization payload JSON is not canonical.", payload, features)
    try:
        public_key = _load_public_key()
    except Exception as exc:  # noqa: BLE001
        return _result(False, "public_key_error", f"Authorization public key validation failed: {exc}", payload, features)

    try:
        public_key.verify(
            parts["signature"],
            parts["payload_bytes"],
            padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
            hashes.SHA256(),
        )
    except InvalidSignature:
        return _result(False, "invalid_signature", "Authorization signature is invalid.", payload, features)
    except Exception as exc:  # noqa: BLE001
        return _result(False, "invalid_signature", f"Authorization signature verification failed: {exc}", payload, features)

    if payload.get("license_version") != LICENSE_VERSION:
        return _result(False, "invalid_format", "Unsupported authorization license version.", payload, features)
    if payload.get("product") != PRODUCT:
        return _result(False, "product_mismatch", "Authorization code is for a different product.", payload, features)

    edition = payload.get("edition")
    if edition not in VALID_EDITIONS:
        return _result(False, "invalid_format", "Authorization edition is invalid.", payload, features)
    if not isinstance(payload.get("customer"), str) or not payload["customer"].strip():
        return _result(False, "invalid_format", "Authorization customer is missing.", payload, features)
    try:
        _parse_datetime(payload.get("issued_at"), "issued_at")
        features = _validate_features(payload)
    except ValueError as exc:
        return _result(False, "invalid_format", str(exc), payload, features)

    try:
        payload_machine_code = normalize_machine_code(payload.get("machine_code", ""))
        machine_code = normalize_machine_code(current_machine_code or get_machine_code())
    except ValueError as exc:
        return _result(False, "invalid_format", str(exc), payload, features)
    if payload_machine_code != machine_code:
        return _result(False, "machine_mismatch", "Authorization code does not match this machine.", payload, features)

    expires_at = payload.get("expires_at")
    expiry: datetime | None = None
    if expires_at is None:
        if edition != "permanent":
            return _result(False, "invalid_format", "Trial and standard authorization require expires_at.", payload, features)
    else:
        try:
            expiry = _parse_datetime(expires_at, "expires_at")
        except ValueError as exc:
            return _result(False, "invalid_format", str(exc), payload, features)
    if edition in {"trial", "standard"} and expiry is None:
        return _result(False, "invalid_format", "Trial and standard authorization require expires_at.", payload, features)

    verify_time = (now or _now()).astimezone(timezone.utc)
    if expiry is not None and verify_time > expiry:
        return _result(False, "expired", "Authorization has expired.", payload, features)

    return _result(True, "valid", "Authorization code is valid.", payload, features)


def _read_license_state_file(state_path: Path) -> dict[str, Any]:
    with state_path.open("r", encoding="utf-8") as handle:
        state = json.load(handle)
    if not isinstance(state, dict):
        raise LicenseStateError("Local license state is corrupted.")
    return state


def load_license_state(state_path: Path = LICENSE_STATE_PATH) -> dict[str, Any]:
    state_path = Path(state_path)
    if not state_path.exists():
        raise FileNotFoundError(f"License state not found: {state_path}")
    try:
        return _read_license_state_file(state_path)
    except Exception as exc:  # noqa: BLE001
        backup_path = state_path.with_name(state_path.name + ".bak")
        try:
            state = _read_license_state_file(backup_path)
        except Exception:  # noqa: BLE001
            raise LicenseStateError("Local license state is corrupted.") from exc
        logging.warning("Local license state recovered from backup: %s", backup_path)
        return state


def save_license_state(payload: dict[str, Any], state_path: Path = LICENSE_STATE_PATH) -> None:
    state_path = Path(state_path)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = state_path.with_name(state_path.name + ".tmp")
    backup_path = state_path.with_name(state_path.name + ".bak")
    try:
        with temp_path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        if state_path.exists():
            try:
                backup_path.write_bytes(state_path.read_bytes())
            except OSError as exc:
                logging.warning("Could not write license state backup: %s", exc)
        os.replace(temp_path, state_path)
    finally:
        if temp_path.exists():
            try:
                temp_path.unlink()
            except OSError:
                pass


def activate_with_code(code: str) -> LicenseVerifyResult:
    result = verify_authorization_code(code)
    if not result.ok or result.payload is None:
        return result
    parts = _authorization_parts(code)
    state = {
        "machine_code": normalize_machine_code(result.payload["machine_code"]),
        "customer": result.customer,
        "edition": result.edition,
        "expires_at": result.expires_at,
        "activated_at": _iso_now(),
        "authorization_code_hash": hashlib.sha256(parts["normalized_code"].encode("utf-8")).hexdigest(),
        "signature_payload": parts["payload_b64"],
        "signature": parts["signature_b64"],
        "features": result.features,
        "last_seen_time": _iso_now(),
        "license_version": result.payload.get("license_version", LICENSE_VERSION),
    }
    save_license_state(state)
    return result


def _status_from_verify(result: LicenseVerifyResult, machine_matches: bool | None = None) -> LicenseStatus:
    return LicenseStatus(
        ok=result.ok,
        status=result.status,
        message=result.message,
        payload=result.payload,
        expires_at=result.expires_at,
        customer=result.customer,
        edition=result.edition,
        features=result.features,
        machine_matches=machine_matches,
    )


def get_formal_license_status(state_path: Path = LICENSE_STATE_PATH, now: datetime | None = None) -> LicenseStatus:
    try:
        state = load_license_state(state_path)
    except FileNotFoundError:
        return LicenseStatus(False, "state_missing", "Local license state does not exist.")
    except LicenseStateError as exc:
        return LicenseStatus(False, "state_corrupted", str(exc))

    if not isinstance(state.get("signature_payload"), str) or not isinstance(state.get("signature"), str):
        return LicenseStatus(False, "state_corrupted", "Local license state is missing signature data.")

    current_time = (now or _now()).astimezone(timezone.utc)
    try:
        last_seen = _parse_datetime(state.get("last_seen_time"), "last_seen_time")
    except ValueError:
        return LicenseStatus(False, "state_corrupted", "Local license state has invalid last_seen_time.")
    if current_time + ROLLBACK_TOLERANCE < last_seen:
        return LicenseStatus(False, "time_error", "System time is earlier than the last licensed use time.")

    code = f"{CODE_PREFIX}.{state['signature_payload']}.{state['signature']}"
    result = verify_authorization_code(code, now=current_time)
    machine_matches = result.status != "machine_mismatch"
    if result.status == "machine_mismatch":
        machine_matches = False

    state["last_seen_time"] = current_time.isoformat()
    try:
        save_license_state(state, state_path)
    except OSError:
        pass
    return _status_from_verify(result, machine_matches=machine_matches)


class TrialManager:
    def __init__(
        self,
        primary_path: Path | None = None,
        backup_path: Path | None = None,
        machine_code: str | None = None,
        trial_days: int = DEFAULT_TRIAL_DAYS,
        enabled: bool = True,
    ) -> None:
        self.primary_path = Path(primary_path) if primary_path else _default_trial_primary_path()
        self.backup_path = Path(backup_path) if backup_path else _default_trial_backup_path()
        self.machine_code_hash = hashlib.sha256(
            normalize_machine_code(machine_code or get_machine_code()).encode("utf-8")
        ).hexdigest()
        self.trial_days = max(1, int(trial_days))
        self.enabled = bool(enabled)

    @staticmethod
    def _hash_key() -> bytes:
        material = f"{PRODUCT}|{CODE_PREFIX}|{PUBLIC_KEY_SHA256}|auto-trial-v1"
        return hashlib.sha256(material.encode("utf-8")).digest()

    def _state_hash(self, state: dict[str, Any]) -> str:
        signed = {
            "schema_version": state.get("schema_version"),
            "machine_code_hash": state.get("machine_code_hash"),
            "trial_started_at": state.get("trial_started_at"),
            "trial_expires_at": state.get("trial_expires_at"),
            "last_seen_at": state.get("last_seen_at"),
            "trial_days": state.get("trial_days"),
        }
        return hmac.new(self._hash_key(), _canonical_json_bytes(signed), hashlib.sha256).hexdigest()

    @staticmethod
    def _read_state(path: Path) -> dict[str, Any]:
        with path.open("r", encoding="utf-8") as handle:
            state = json.load(handle)
        if not isinstance(state, dict):
            raise ValueError("Trial state is not a JSON object.")
        return state

    def _write_state(self, state: dict[str, Any]) -> int:
        written = 0
        for path in (self.primary_path, self.backup_path):
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                temp_path = path.with_name(path.name + ".tmp")
                with temp_path.open("w", encoding="utf-8") as handle:
                    json.dump(state, handle, ensure_ascii=False, indent=2, sort_keys=True)
                    handle.write("\n")
                temp_path.replace(path)
                written += 1
            except OSError:
                continue
        return written

    def _status(
        self,
        ok: bool,
        status: str,
        message: str,
        state: dict[str, Any] | None = None,
        days_remaining: int | None = None,
    ) -> LicenseStatus:
        return LicenseStatus(
            ok=ok,
            status=status,
            message=message,
            payload=dict(state or {}),
            expires_at=(state or {}).get("trial_expires_at"),
            customer="Auto Trial" if state else None,
            edition="trial" if state else None,
            features=dict(DEFAULT_FEATURES),
            machine_matches=status != "trial_machine_mismatch",
            state_path=str(self.primary_path),
            trial_days_remaining=days_remaining,
            trial_started_at=(state or {}).get("trial_started_at"),
        )

    def _validate_state(
        self,
        state: dict[str, Any],
        current_time: datetime,
        update_last_seen: bool,
    ) -> LicenseStatus:
        required = {
            "schema_version",
            "machine_code_hash",
            "trial_started_at",
            "trial_expires_at",
            "last_seen_at",
            "trial_days",
            "state_hash",
        }
        if not required.issubset(state):
            return self._status(False, "trial_corrupted", "Trial state is missing required fields.", state)
        if state.get("schema_version") != TRIAL_SCHEMA_VERSION:
            return self._status(False, "trial_corrupted", "Trial state schema is not supported.", state)
        if not hmac.compare_digest(str(state.get("state_hash", "")), self._state_hash(state)):
            return self._status(False, "trial_corrupted", "Trial state integrity check failed.", state)
        if state.get("machine_code_hash") != self.machine_code_hash:
            return self._status(False, "trial_machine_mismatch", "Trial state does not belong to this machine.", state)
        try:
            started_at = _parse_datetime(state.get("trial_started_at"), "trial_started_at")
            expires_at = _parse_datetime(state.get("trial_expires_at"), "trial_expires_at")
            last_seen_at = _parse_datetime(state.get("last_seen_at"), "last_seen_at")
        except ValueError:
            return self._status(False, "trial_corrupted", "Trial state contains an invalid timestamp.", state)
        if expires_at <= started_at or int(state.get("trial_days", 0)) <= 0:
            return self._status(False, "trial_corrupted", "Trial state has an invalid duration.", state)
        if current_time + ROLLBACK_TOLERANCE < last_seen_at:
            return self._status(False, "trial_time_error", "System time rollback was detected.", state)
        seconds_left = (expires_at - current_time).total_seconds()
        if seconds_left <= 0:
            return self._status(False, "trial_expired", "The automatic trial has expired.", state, 0)
        days_remaining = max(1, int(math.ceil(seconds_left / 86400)))
        if update_last_seen:
            state["last_seen_at"] = current_time.isoformat()
            state["state_hash"] = self._state_hash(state)
            self._write_state(state)
        return self._status(True, "trial_valid", "The automatic trial is active.", state, days_remaining)

    def get_status(self, now: datetime | None = None, update_last_seen: bool = True) -> LicenseStatus:
        if not self.enabled:
            return self._status(False, "trial_disabled", "Automatic trial is disabled.")
        current_time = (now or _now()).astimezone(timezone.utc)
        existing = [path for path in (self.primary_path, self.backup_path) if path.exists()]
        if not existing:
            return self._status(False, "trial_available", f"Free {self.trial_days}-day trial is available.")

        valid_state: dict[str, Any] | None = None
        first_error: LicenseStatus | None = None
        for path in existing:
            try:
                state = self._read_state(path)
            except Exception:  # noqa: BLE001
                status = self._status(False, "trial_corrupted", "Trial state could not be read.")
            else:
                status = self._validate_state(state, current_time, update_last_seen=False)
            if status.status in {"trial_valid", "trial_expired", "trial_time_error"}:
                valid_state = state
                break
            if first_error is None:
                first_error = status

        if valid_state is None:
            return first_error or self._status(False, "trial_corrupted", "Trial state is invalid.")
        status = self._validate_state(valid_state, current_time, update_last_seen=update_last_seen)
        if status.status in {"trial_valid", "trial_expired"}:
            self._write_state(valid_state)
        return status

    def start_trial(self, now: datetime | None = None) -> LicenseStatus:
        current = self.get_status(now=now, update_last_seen=True)
        if current.status != "trial_available":
            return current
        current_time = (now or _now()).astimezone(timezone.utc)
        expires_at = current_time + timedelta(days=self.trial_days)
        state = {
            "schema_version": TRIAL_SCHEMA_VERSION,
            "machine_code_hash": self.machine_code_hash,
            "trial_started_at": current_time.isoformat(),
            "trial_expires_at": expires_at.isoformat(),
            "last_seen_at": current_time.isoformat(),
            "trial_days": self.trial_days,
        }
        state["state_hash"] = self._state_hash(state)
        if self._write_state(state) <= 0:
            return self._status(False, "trial_write_error", "Trial state could not be saved.", state)
        status = self._validate_state(state, current_time, update_last_seen=False)
        status.payload = dict(status.payload or {})
        status.payload["_just_started"] = True
        status.message = f"Automatic {self.trial_days}-day trial started."
        return status


def get_license_status(
    state_path: Path = LICENSE_STATE_PATH,
    now: datetime | None = None,
    trial_manager: TrialManager | None = None,
    trial_enabled: bool = True,
    trial_days: int = DEFAULT_TRIAL_DAYS,
) -> LicenseStatus:
    formal_status = get_formal_license_status(state_path=state_path, now=now)
    if formal_status.ok and formal_status.status == "valid":
        return formal_status
    manager = trial_manager or TrialManager(trial_days=trial_days, enabled=trial_enabled)
    return manager.get_status(now=now)


def is_recording_allowed(
    start_trial: bool = False,
    trial_enabled: bool = True,
    trial_days: int = DEFAULT_TRIAL_DAYS,
    state_path: Path = LICENSE_STATE_PATH,
    trial_manager: TrialManager | None = None,
    now: datetime | None = None,
) -> tuple[bool, str, LicenseStatus]:
    formal_status = get_formal_license_status(state_path=state_path, now=now)
    if formal_status.ok and formal_status.status == "valid":
        status = formal_status
    else:
        manager = trial_manager or TrialManager(trial_days=trial_days, enabled=trial_enabled)
        status = manager.start_trial(now=now) if start_trial else manager.get_status(now=now)
    if status.status == "trial_valid":
        return (
            True,
            f"\u8bd5\u7528\u5269\u4f59 {status.trial_days_remaining or 0} \u5929\uff0c\u53ef\u4ee5\u5f00\u59cb\u5f55\u50cf\u3002",
            status,
        )
    trial_messages = {
        "trial_available": "\u53ef\u514d\u8d39\u8bd5\u7528 30 \u5929\uff0c\u70b9\u51fb\u201c\u5f00\u59cb\u201d\u540e\u81ea\u52a8\u5f00\u542f\u3002",
        "trial_expired": "\u8bd5\u7528\u5df2\u5230\u671f\uff0c\u8bf7\u8054\u7cfb\u4f9b\u5e94\u5546\u6fc0\u6d3b\u3002",
        "trial_time_error": "\u68c0\u6d4b\u5230\u7cfb\u7edf\u65f6\u95f4\u5f02\u5e38\uff0c\u8bf7\u6821\u51c6\u7535\u8111\u65f6\u95f4\u540e\u91cd\u8bd5\u3002",
        "trial_corrupted": "\u8bd5\u7528\u72b6\u6001\u5f02\u5e38\uff0c\u8bf7\u8054\u7cfb\u4f9b\u5e94\u5546\u3002",
        "trial_machine_mismatch": "\u8bd5\u7528\u72b6\u6001\u4e0e\u672c\u673a\u4e0d\u5339\u914d\uff0c\u8bf7\u8054\u7cfb\u4f9b\u5e94\u5546\u3002",
        "trial_write_error": "\u65e0\u6cd5\u521b\u5efa\u8bd5\u7528\u72b6\u6001\uff0c\u8bf7\u68c0\u67e5\u5f53\u524d\u7528\u6237\u7684\u5199\u5165\u6743\u9650\u3002",
        "trial_disabled": "\u5f53\u524d\u672a\u542f\u7528\u81ea\u52a8\u8bd5\u7528\uff0c\u8bf7\u8054\u7cfb\u4f9b\u5e94\u5546\u6fc0\u6d3b\u3002",
    }
    if status.status in trial_messages:
        return False, trial_messages[status.status], status
    messages = {
        "state_missing": "软件尚未激活，请先完成授权激活。",
        "state_corrupted": "本地授权状态损坏，请重新激活。",
        "invalid_format": "本地授权状态无效，请重新激活。",
        "invalid_signature": "本地授权签名无效，请重新激活。",
        "machine_mismatch": "授权码不属于本机，请复制本机机器码重新获取授权码。",
        "expired": "授权已过期，请联系供应商续期。",
        "time_error": "检测到系统时间异常，请校准电脑时间后重试。",
        "public_key_error": "授权模块校验失败，请联系供应商。",
        "product_mismatch": "授权码不属于当前软件，请联系供应商。",
    }
    if not status.ok or status.status != "valid":
        return False, messages.get(status.status, "当前授权无效，请重新激活。"), status
    if not bool(status.features.get("recording", DEFAULT_FEATURES["recording"])):
        blocked = LicenseStatus(
            False,
            "recording_disabled",
            "Recording feature is disabled by authorization.",
            payload=status.payload,
            expires_at=status.expires_at,
            customer=status.customer,
            edition=status.edition,
            features=status.features,
            machine_matches=status.machine_matches,
        )
        return False, "当前授权未开通录像功能。", blocked
    return True, "授权有效，可以开始录像。", status


def _print_result(result: LicenseVerifyResult | LicenseStatus) -> None:
    safe_print(f"ok={result.ok}")
    safe_print(f"status={result.status}")
    safe_print(f"message={result.message}")
    safe_print(f"customer={result.customer or '--'}")
    safe_print(f"edition={result.edition or '--'}")
    safe_print(f"expires_at={result.expires_at or '--'}")
    if isinstance(result, LicenseStatus):
        machine_text = "--" if result.machine_matches is None else str(result.machine_matches)
        safe_print(f"machine_matches={machine_text}")
    safe_print("features=" + json.dumps(result.features, ensure_ascii=False, sort_keys=True))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="ShippingMonitorGUI offline authorization core CLI")
    commands = parser.add_mutually_exclusive_group(required=True)
    commands.add_argument("--machine-code", action="store_true", help="Print this machine code.")
    commands.add_argument("--status", action="store_true", help="Read and verify local license state.")
    commands.add_argument("--verify", metavar="CODE", help="Verify an authorization code.")
    commands.add_argument("--activate", metavar="CODE", help="Activate and save a valid authorization code.")
    args = parser.parse_args(argv)

    if args.machine_code:
        machine_code, low_stability, stable_count = get_machine_code_info()
        safe_print(f"machine_code={machine_code}")
        safe_print(f"machine_code_display={format_machine_code(machine_code)}")
        safe_print(f"stable_component_count={stable_count}")
        safe_print(f"low_stability_warning={low_stability}")
        return 0
    if args.status:
        result = get_license_status()
        _print_result(result)
        return 0 if result.ok else 1
    if args.verify:
        result = verify_authorization_code(args.verify)
        _print_result(result)
        return 0 if result.ok else 1

    result = activate_with_code(args.activate)
    _print_result(result)
    if result.ok:
        safe_print(f"license_state={LICENSE_STATE_PATH}")
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
