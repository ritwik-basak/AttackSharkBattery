from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import hid


@dataclass(frozen=True)
class HidDeviceInfo:
    path: str
    vendor_id: int
    product_id: int
    serial_number: str | None
    release_number: int | None
    manufacturer_string: str | None
    product_string: str | None
    usage_page: int | None
    usage: int | None
    interface_number: int | None

    @classmethod
    def from_hidapi(cls, raw: dict[str, Any]) -> "HidDeviceInfo":
        return cls(
            path=_decode_path(raw.get("path")),
            vendor_id=int(raw.get("vendor_id") or 0),
            product_id=int(raw.get("product_id") or 0),
            serial_number=raw.get("serial_number"),
            release_number=raw.get("release_number"),
            manufacturer_string=raw.get("manufacturer_string"),
            product_string=raw.get("product_string"),
            usage_page=raw.get("usage_page"),
            usage=raw.get("usage"),
            interface_number=raw.get("interface_number"),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "vendor_id": f"0x{self.vendor_id:04x}",
            "product_id": f"0x{self.product_id:04x}",
            "manufacturer": self.manufacturer_string,
            "product": self.product_string,
            "serial_number": self.serial_number,
            "release_number": _hex_or_none(self.release_number),
            "usage_page": _hex_or_none(self.usage_page),
            "usage": _hex_or_none(self.usage),
            "interface_number": self.interface_number,
            "path": self.path,
        }

    @property
    def is_vendor_specific(self) -> bool:
        return self.usage_page is not None and 0xFF00 <= self.usage_page <= 0xFFFF

    def matches_text(self, needle: str) -> bool:
        haystack = " ".join(
            value or ""
            for value in (
                self.manufacturer_string,
                self.product_string,
                self.serial_number,
                self.path,
            )
        ).lower()
        return needle.lower() in haystack


def enumerate_devices(match: str | None = None) -> list[HidDeviceInfo]:
    devices = [HidDeviceInfo.from_hidapi(item) for item in hid.enumerate()]
    if match:
        devices = [device for device in devices if device.matches_text(match)]
    return sorted(
        devices,
        key=lambda item: (
            item.vendor_id,
            item.product_id,
            item.interface_number if item.interface_number is not None else -1,
            item.usage_page if item.usage_page is not None else -1,
            item.usage if item.usage is not None else -1,
            item.path,
        ),
    )


def find_device(
    *,
    path: str | None = None,
    vendor_id: int | None = None,
    product_id: int | None = None,
    interface_number: int | None = None,
    usage_page: int | None = None,
    usage: int | None = None,
) -> HidDeviceInfo:
    if path:
        for device in enumerate_devices():
            if device.path == path:
                return device
        raise ValueError("No HID device matched the provided path.")

    if vendor_id is None or product_id is None:
        raise ValueError("Provide either --path or both --vid and --pid.")

    matches = [
        device
        for device in enumerate_devices()
        if device.vendor_id == vendor_id
        and device.product_id == product_id
        and (interface_number is None or device.interface_number == interface_number)
        and (usage_page is None or device.usage_page == usage_page)
        and (usage is None or device.usage == usage)
    ]
    if not matches:
        raise ValueError("No HID device matched the provided VID/PID/interface filters.")
    if len(matches) > 1:
        details = ", ".join(
            f"interface={device.interface_number}, usage_page={_hex_or_none(device.usage_page)}, "
            f"usage={_hex_or_none(device.usage)}"
            for device in matches
        )
        raise ValueError(
            "Multiple HID interfaces matched. Add --interface, --usage-page, --usage, or --path. "
            f"Matches: {details}"
        )
    return matches[0]


def open_device(device: HidDeviceInfo) -> hid.device:
    handle = hid.device()
    handle.open_path(device.path.encode("utf-8"))
    handle.set_nonblocking(True)
    return handle


def bytes_to_hex(data: bytes | list[int]) -> str:
    return " ".join(f"{byte:02x}" for byte in data)


def _decode_path(value: object) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value or "")


def _hex_or_none(value: int | None) -> str | None:
    if value is None:
        return None
    return f"0x{value:04x}"
