from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from typing import Sequence

from .hid_tools import HidDeviceInfo, bytes_to_hex, enumerate_devices, find_device, open_device

BATTERY_SIGNATURE = bytes([0x03, 0x55, 0x40, 0x01])
ATTACK_SHARK_X11_WIRELESS_VID = 0x1D57
ATTACK_SHARK_X11_WIRELESS_PID = 0xFA60


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="attack-shark-battery",
        description="HID discovery and packet logging for the Attack Shark X11 mouse.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    enumerate_parser = subparsers.add_parser("enumerate", help="List HID devices.")
    enumerate_parser.add_argument("--match", help="Filter by manufacturer, product, serial, or path.")
    enumerate_parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    enumerate_parser.set_defaults(func=_run_enumerate)

    log_parser = subparsers.add_parser("log", help="Read and print raw HID input reports.")
    log_parser.add_argument("--path", help="Exact HID device path from the enumerate command.")
    log_parser.add_argument("--vid", type=_parse_int, help="Vendor ID, for example 0x3554.")
    log_parser.add_argument("--pid", type=_parse_int, help="Product ID, for example 0xf58a.")
    log_parser.add_argument("--interface", type=int, help="Optional HID interface number.")
    log_parser.add_argument("--usage-page", type=_parse_int, help="Optional HID usage page filter.")
    log_parser.add_argument("--usage", type=_parse_int, help="Optional HID usage filter.")
    log_parser.add_argument("--read-size", type=int, default=64, help="Input report size to read.")
    log_parser.add_argument("--interval", type=float, default=0.05, help="Idle sleep in seconds.")
    log_parser.add_argument("--duration", type=float, help="Stop after this many seconds.")
    log_parser.set_defaults(func=_run_log)

    probe_parser = subparsers.add_parser("probe", help="Probe HID feature/input reports.")
    _add_device_filters(probe_parser)
    probe_parser.add_argument(
        "--kind",
        choices=("feature", "input", "both"),
        default="feature",
        help="Report API to probe.",
    )
    probe_parser.add_argument("--start-id", type=_parse_int, default=0, help="First report ID.")
    probe_parser.add_argument("--end-id", type=_parse_int, default=0x20, help="Last report ID.")
    probe_parser.add_argument("--size", type=int, default=64, help="Maximum report length.")
    probe_parser.add_argument(
        "--show-empty",
        action="store_true",
        help="Also print all-zero successful reports.",
    )
    probe_parser.add_argument(
        "--show-errors",
        action="store_true",
        help="Print failed report IDs as well as successful ones.",
    )
    probe_parser.set_defaults(func=_run_probe)

    battery_parser = subparsers.add_parser("battery", help="Read the Attack Shark X11 battery percent.")
    battery_parser.add_argument(
        "--vid",
        type=_parse_int,
        default=ATTACK_SHARK_X11_WIRELESS_VID,
        help="Vendor ID.",
    )
    battery_parser.add_argument(
        "--pid",
        type=_parse_int,
        default=ATTACK_SHARK_X11_WIRELESS_PID,
        help="Product ID.",
    )
    battery_parser.add_argument("--timeout", type=float, default=5, help="Seconds to wait.")
    battery_parser.add_argument(
        "--watch",
        action="store_true",
        help="Continue printing battery changes until Ctrl+C.",
    )
    battery_parser.set_defaults(func=_run_battery)

    watch_parser = subparsers.add_parser(
        "watch",
        help="Open matching HID collections and watch input/feature data for battery packets.",
    )
    watch_parser.add_argument("--vid", type=_parse_int, required=True, help="Vendor ID.")
    watch_parser.add_argument("--pid", type=_parse_int, required=True, help="Product ID.")
    watch_parser.add_argument("--interface", type=int, help="Optional HID interface number.")
    watch_parser.add_argument("--read-size", type=int, default=64, help="Input report size to read.")
    watch_parser.add_argument("--duration", type=float, default=30, help="Watch duration in seconds.")
    watch_parser.add_argument("--interval", type=float, default=0.02, help="Idle sleep in seconds.")
    watch_parser.add_argument(
        "--feature-ids",
        default="0x04,0x05,0x06,0x07,0x08,0x09,0x0a,0x0b,0x0c,0x10,0x22",
        help="Comma-separated feature report IDs to poll for changes.",
    )
    watch_parser.set_defaults(func=_run_watch)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except KeyboardInterrupt:
        print("\nStopped.")
        return 130
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


def _run_enumerate(args: argparse.Namespace) -> int:
    devices = enumerate_devices(match=args.match)
    if args.json:
        print(json.dumps([device.as_dict() for device in devices], indent=2))
        return 0

    if not devices:
        print("No HID devices found.")
        return 0

    for index, device in enumerate(devices, start=1):
        marker = " vendor-specific" if device.is_vendor_specific else ""
        print(f"[{index}]{marker}")
        print(f"  VID/PID:        0x{device.vendor_id:04x}:0x{device.product_id:04x}")
        print(f"  Manufacturer:   {device.manufacturer_string or '-'}")
        print(f"  Product:        {device.product_string or '-'}")
        print(f"  Serial:         {device.serial_number or '-'}")
        print(f"  Release:        {_format_hex(device.release_number)}")
        print(f"  Usage Page:     {_format_hex(device.usage_page)}")
        print(f"  Usage:          {_format_hex(device.usage)}")
        print(f"  Interface No.:  {_format_int(device.interface_number)}")
        print(f"  Path:           {device.path}")
        print()
    return 0


def _run_log(args: argparse.Namespace) -> int:
    device = find_device(
        path=args.path,
        vendor_id=args.vid,
        product_id=args.pid,
        interface_number=args.interface,
        usage_page=args.usage_page,
        usage=args.usage,
    )
    print(
        "Opening "
        f"0x{device.vendor_id:04x}:0x{device.product_id:04x} "
        f"interface={_format_int(device.interface_number)} "
        f"usage_page={_format_hex(device.usage_page)} usage={_format_hex(device.usage)}"
    )
    print("Press Ctrl+C to stop.")

    deadline = time.monotonic() + args.duration if args.duration else None
    handle = open_device(device)
    try:
        while deadline is None or time.monotonic() < deadline:
            report = handle.read(args.read_size)
            if report:
                timestamp = datetime.now().isoformat(timespec="milliseconds")
                print(f"{timestamp} len={len(report):03d} {bytes_to_hex(report)}")
            else:
                time.sleep(args.interval)
    finally:
        handle.close()
    return 0


def _run_probe(args: argparse.Namespace) -> int:
    device = find_device(
        path=args.path,
        vendor_id=args.vid,
        product_id=args.pid,
        interface_number=args.interface,
        usage_page=args.usage_page,
        usage=args.usage,
    )
    print(
        "Opening "
        f"0x{device.vendor_id:04x}:0x{device.product_id:04x} "
        f"interface={_format_int(device.interface_number)} "
        f"usage_page={_format_hex(device.usage_page)} usage={_format_hex(device.usage)}"
    )

    kinds = ("feature", "input") if args.kind == "both" else (args.kind,)
    handle = open_device(device)
    try:
        for report_id in range(args.start_id, args.end_id + 1):
            for kind in kinds:
                try:
                    if kind == "feature":
                        report = handle.get_feature_report(report_id, args.size)
                    else:
                        report = handle.get_input_report(report_id, args.size)
                except OSError as exc:
                    if args.show_errors:
                        print(f"{kind:7} id=0x{report_id:02x} error={exc}")
                    continue

                if not report:
                    continue
                has_payload = any(byte != 0 for byte in report)
                if has_payload or args.show_empty:
                    print(
                        f"{kind:7} id=0x{report_id:02x} "
                        f"len={len(report):03d} {bytes_to_hex(report)}"
                    )
    finally:
        handle.close()
    return 0


def _run_battery(args: argparse.Namespace) -> int:
    readers = _open_battery_readers(args.vid, args.pid)
    if not readers:
        raise ValueError("Could not open any likely X11 battery HID collection.")

    timeout = None if args.watch else args.timeout
    last_battery: int | None = None
    try:
        while True:
            battery = _read_battery_once(readers, timeout=timeout)
            if battery is None:
                print("Battery: unknown")
                return 2
            if battery != last_battery:
                print(f"Battery: {battery}%")
                last_battery = battery
            if not args.watch:
                return 0
            time.sleep(1)
    finally:
        for _, handle in readers:
            handle.close()


def _open_battery_readers(vid: int, pid: int) -> list[tuple[HidDeviceInfo, object]]:
    # Windows exposes the interrupt battery packet on this collection for the X11 receiver.
    preferred = [
        device
        for device in enumerate_devices()
        if device.vendor_id == vid
        and device.product_id == pid
        and device.interface_number == 2
        and device.usage_page in (0x000A, 0x000B)
        and device.usage == 0x0000
    ]
    readers = []
    for device in preferred:
        try:
            readers.append((device, open_device(device)))
        except OSError:
            pass
    return readers


def _read_battery_once(
    readers: list[tuple[HidDeviceInfo, object]],
    *,
    timeout: float | None,
) -> int | None:
    deadline = None if timeout is None else time.monotonic() + timeout
    while deadline is None or time.monotonic() < deadline:
        for device, handle in readers:
            try:
                report = handle.read(64)
            except OSError:
                report = []
            battery = _find_battery(report)
            if battery is not None:
                return battery

            if device.usage_page == 0x000B:
                try:
                    report = handle.get_feature_report(0x0A, 64)
                except OSError:
                    report = []
                battery = _find_battery(report)
                if battery is not None:
                    return battery
        time.sleep(0.02)
    return None


def _run_watch(args: argparse.Namespace) -> int:
    devices = [
        device
        for device in enumerate_devices()
        if device.vendor_id == args.vid
        and device.product_id == args.pid
        and (args.interface is None or device.interface_number == args.interface)
    ]
    if not devices:
        raise ValueError("No HID devices matched the provided VID/PID/interface filters.")

    handles: list[tuple[HidDeviceInfo, object]] = []
    for device in devices:
        try:
            handles.append((device, open_device(device)))
            print(f"Opened { _device_label(device) }")
        except OSError as exc:
            print(f"Skipped { _device_label(device) }: {exc}")

    if not handles:
        raise ValueError("No matching HID collection could be opened.")

    feature_ids = _parse_int_list(args.feature_ids)
    last_features: dict[tuple[str, int], list[int]] = {}
    deadline = time.monotonic() + args.duration
    print("Watching now. Move/click the mouse, place it on/off the dock, or plug/unplug charging.")
    try:
        while time.monotonic() < deadline:
            for device, handle in handles:
                _read_input_once(device, handle, args.read_size)
                for report_id in feature_ids:
                    _read_feature_change_once(device, handle, report_id, args.read_size, last_features)
            time.sleep(args.interval)
    finally:
        for _, handle in handles:
            handle.close()
    return 0


def _read_input_once(device: HidDeviceInfo, handle: object, read_size: int) -> None:
    try:
        report = handle.read(read_size)
    except OSError:
        return
    if report:
        _print_report("input", device, None, report)


def _read_feature_change_once(
    device: HidDeviceInfo,
    handle: object,
    report_id: int,
    read_size: int,
    last_features: dict[tuple[str, int], list[int]],
) -> None:
    try:
        report = handle.get_feature_report(report_id, read_size)
    except OSError:
        return
    if not report:
        return

    key = (device.path, report_id)
    previous = last_features.get(key)
    if previous == report:
        return
    last_features[key] = report
    _print_report("feature", device, report_id, report)


def _print_report(kind: str, device: HidDeviceInfo, report_id: int | None, report: list[int]) -> None:
    timestamp = datetime.now().isoformat(timespec="milliseconds")
    battery = _find_battery(report)
    battery_text = f" BATTERY={battery}%" if battery is not None else ""
    report_id_text = "" if report_id is None else f" id=0x{report_id:02x}"
    print(
        f"{timestamp} {kind}{report_id_text} { _device_label(device) } "
        f"len={len(report):03d} {bytes_to_hex(report)}{battery_text}"
    )


def _find_battery(report: list[int]) -> int | None:
    data = bytes(report)
    offset = data.find(BATTERY_SIGNATURE)
    if offset == -1 or offset + len(BATTERY_SIGNATURE) >= len(data):
        return None
    percent = data[offset + len(BATTERY_SIGNATURE)]
    if 0 <= percent <= 100:
        return percent
    return None


def _device_label(device: HidDeviceInfo) -> str:
    return (
        f"interface={_format_int(device.interface_number)} "
        f"usage_page={_format_hex(device.usage_page)} usage={_format_hex(device.usage)}"
    )


def _parse_int_list(value: str) -> list[int]:
    if not value.strip():
        return []
    return [_parse_int(item.strip()) for item in value.split(",") if item.strip()]


def _add_device_filters(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--path", help="Exact HID device path from the enumerate command.")
    parser.add_argument("--vid", type=_parse_int, help="Vendor ID, for example 0x3554.")
    parser.add_argument("--pid", type=_parse_int, help="Product ID, for example 0xf58a.")
    parser.add_argument("--interface", type=int, help="Optional HID interface number.")
    parser.add_argument("--usage-page", type=_parse_int, help="Optional HID usage page filter.")
    parser.add_argument("--usage", type=_parse_int, help="Optional HID usage filter.")


def _parse_int(value: str) -> int:
    return int(value, 0)


def _format_hex(value: int | None) -> str:
    if value is None:
        return "-"
    return f"0x{value:04x}"


def _format_int(value: int | None) -> str:
    if value is None:
        return "-"
    return str(value)


if __name__ == "__main__":
    raise SystemExit(main())
