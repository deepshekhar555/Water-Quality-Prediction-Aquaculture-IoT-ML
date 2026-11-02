"""Non-blocking USB serial input for the project's ESP32/Arduino CSV stream."""

from __future__ import annotations

import csv
import io
from collections import deque
from datetime import datetime, timezone
from typing import Any


FIRMWARE_HEADERS = [
    "sample_id",
    "timestamp_ms",
    "pH",
    "temperature_c",
    "turbidity_ntu",
]


class SketchCSVDecoder:
    """Decode the header and rows emitted by sketch_aquaculture_copy_*.ino."""

    def __init__(self) -> None:
        self.headers: list[str] | None = None
        self.invalid_lines = 0

    @staticmethod
    def _key(value: str) -> str:
        return "".join(character for character in value.casefold() if character.isalnum())

    def feed_line(self, line: str) -> dict[str, Any] | None:
        try:
            fields = next(csv.reader(io.StringIO(line.strip())))
        except (csv.Error, StopIteration):
            self.invalid_lines += 1
            return None

        if not fields or not any(field.strip() for field in fields):
            return None

        keys = {self._key(field) for field in fields}
        if "timestampms" in keys and ("ph" in keys or "phact" in keys):
            self.headers = [field.strip() for field in fields]
            return None

        if self.headers is None:
            if len(fields) != len(FIRMWARE_HEADERS):
                self.invalid_lines += 1
                return None
            headers = FIRMWARE_HEADERS
        else:
            headers = self.headers

        if len(fields) != len(headers):
            self.invalid_lines += 1
            return None
        return dict(zip(headers, (field.strip() for field in fields)))


def available_serial_ports() -> list[tuple[str, str]]:
    """Return available serial port names and descriptions."""
    from serial.tools import list_ports

    return [(port.device, port.description) for port in list_ports.comports()]


class SerialTelemetryReader:
    """Own a non-blocking serial port and retain the latest decoded rows."""

    def __init__(self, max_rows: int = 1000) -> None:
        self.decoder = SketchCSVDecoder()
        self.rows: deque[dict[str, Any]] = deque(maxlen=max_rows)
        self.connection = None
        self.port: str | None = None
        self.error: str | None = None
        self._text_buffer = ""

    @property
    def connected(self) -> bool:
        return self.connection is not None and self.connection.is_open

    def connect(self, port: str, baud_rate: int = 9600) -> None:
        import serial

        self.disconnect()
        self.connection = serial.Serial(port, baudrate=baud_rate, timeout=0)
        self.port = port
        self.error = None
        self._text_buffer = ""

    def disconnect(self) -> None:
        if self.connection is not None:
            self.connection.close()
        self.connection = None
        self.port = None

    def poll(self, max_bytes: int = 16_384) -> int:
        """Read available bytes without waiting and return the number of new rows."""
        if not self.connected:
            return 0

        try:
            available = min(self.connection.in_waiting, max_bytes)
            if not available:
                return 0
            self._text_buffer += self.connection.read(available).decode("utf-8", errors="replace")
        except Exception as error:
            self.error = str(error)
            self.disconnect()
            return 0

        added_rows = 0
        while "\n" in self._text_buffer:
            line, self._text_buffer = self._text_buffer.split("\n", 1)
            record = self.decoder.feed_line(line.rstrip("\r"))
            if record is not None:
                record["received_at"] = datetime.now(timezone.utc).isoformat()
                self.rows.append(record)
                added_rows += 1
        return added_rows
