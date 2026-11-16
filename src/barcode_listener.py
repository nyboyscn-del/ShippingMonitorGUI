from __future__ import annotations

import logging
from collections.abc import Callable

from safe_print import safe_print


BarcodeCallback = Callable[[str, str], None]
PROMPT = "tracking> "


def print_status_with_prompt(message: str) -> None:
    safe_print(f"\n{message}\n{PROMPT}", end="", flush=True)


class BarcodeListener:
    def __init__(self, disable_duplicate_scan: bool = False):
        self.disable_duplicate_scan = disable_duplicate_scan
        self._seen: set[str] = set()

    def handle_input(self, value: str, callback: BarcodeCallback, source: str = "keyboard") -> bool:
        tracking_number = value.strip()
        if not tracking_number:
            return False

        if self.disable_duplicate_scan and tracking_number in self._seen:
            logging.info("Duplicate tracking number ignored: %s", tracking_number)
            safe_print(f"Duplicate tracking number ignored: {tracking_number}")
            return False

        self._seen.add(tracking_number)
        callback(tracking_number, source)
        return True

    def listen_forever(self, callback: BarcodeCallback) -> None:
        safe_print("Scanner listener started. Scan or type a tracking number and press Enter. Type q to exit.")
        while True:
            value = input(PROMPT).strip()
            if value.lower() in {"q", "quit", "exit"}:
                break
            self.handle_input(value, callback, source="keyboard")
