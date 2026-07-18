from __future__ import annotations

import time
from dataclasses import dataclass

from .hid_tools import HidDeviceInfo, enumerate_devices, open_device

BATTERY_SIGNATURE = bytes([0x03, 0x55, 0x40, 0x01])
ATTACK_SHARK_X11_WIRELESS_VID = 0x1D57
ATTACK_SHARK_X11_WIRELESS_PID = 0xFA60


@dataclass(frozen=True)
class BatteryReader:
    device: HidDeviceInfo
    handle: object

    def close(self) -> None:
        self.handle.close()


def find_battery_in_report(report: list[int]) -> int | None:
    data = bytes(report)
    offset = data.find(BATTERY_SIGNATURE)
    if offset == -1 or offset + len(BATTERY_SIGNATURE) >= len(data):
        return None

    percent = data[offset + len(BATTERY_SIGNATURE)]
    if 0 <= percent <= 100:
        return percent
    return None


def open_battery_readers(
    vid: int = ATTACK_SHARK_X11_WIRELESS_VID,
    pid: int = ATTACK_SHARK_X11_WIRELESS_PID,
) -> list[BatteryReader]:
    devices = [
        device
        for device in enumerate_devices()
        if device.vendor_id == vid
        and device.product_id == pid
        and device.interface_number == 2
        and device.usage_page in (0x000A, 0x000B)
        and device.usage == 0x0000
    ]

    readers: list[BatteryReader] = []
    for device in devices:
        try:
            readers.append(BatteryReader(device=device, handle=open_device(device)))
        except OSError:
            pass
    return readers


def read_battery_once(readers: list[BatteryReader], timeout: float | None = 5) -> int | None:
    deadline = None if timeout is None else time.monotonic() + timeout
    while deadline is None or time.monotonic() < deadline:
        for reader in readers:
            try:
                report = reader.handle.read(64)
            except OSError:
                report = []

            battery = find_battery_in_report(report)
            if battery is not None:
                return battery

            # The 0x000b collection mirrors recent packets in feature report 0x0a.
            if reader.device.usage_page == 0x000B:
                try:
                    report = reader.handle.get_feature_report(0x0A, 64)
                except OSError:
                    report = []

                battery = find_battery_in_report(report)
                if battery is not None:
                    return battery

        time.sleep(0.02)
    return None

