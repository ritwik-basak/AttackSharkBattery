from __future__ import annotations

import threading
import time
from dataclasses import dataclass

import pystray
from PIL import Image, ImageDraw, ImageFont

from .battery import open_battery_readers, read_battery_once

LOW_BATTERY_PERCENT = 20
REFRESH_SECONDS = 60


@dataclass
class TrayState:
    battery: int | None = None
    status: str = "Starting"
    notified_low: bool = False
    stop_requested: bool = False


def main() -> None:
    state = TrayState()
    icon = pystray.Icon(
        "attack-shark-battery",
        icon=_make_icon(None),
        title="Attack Shark X11 Battery",
        menu=pystray.Menu(
            pystray.MenuItem(lambda _: _menu_status(state), None, enabled=False),
            pystray.MenuItem("Refresh", lambda _: _refresh(icon, state)),
            pystray.MenuItem("Quit", lambda _: _quit(icon, state)),
        ),
    )

    worker = threading.Thread(target=_update_loop, args=(icon, state), daemon=True)
    worker.start()
    icon.run()


def _update_loop(icon: pystray.Icon, state: TrayState) -> None:
    while not state.stop_requested:
        _refresh(icon, state)
        for _ in range(REFRESH_SECONDS):
            if state.stop_requested:
                return
            time.sleep(1)


def _refresh(icon: pystray.Icon, state: TrayState) -> None:
    readers = open_battery_readers()
    try:
        battery = read_battery_once(readers, timeout=5) if readers else None
    finally:
        for reader in readers:
            reader.close()

    state.battery = battery
    if battery is None:
        state.status = "Battery unknown"
    else:
        state.status = f"Battery {battery}%"

    icon.title = f"Attack Shark X11 - {state.status}"
    icon.icon = _make_icon(battery)
    icon.update_menu()

    if battery is not None and battery <= LOW_BATTERY_PERCENT and not state.notified_low:
        state.notified_low = True
        icon.notify(f"Attack Shark X11 battery is {battery}%", "Low battery")
    elif battery is not None and battery > LOW_BATTERY_PERCENT:
        state.notified_low = False


def _quit(icon: pystray.Icon, state: TrayState) -> None:
    state.stop_requested = True
    icon.stop()


def _menu_status(state: TrayState) -> str:
    return state.status


def _make_icon(battery: int | None) -> Image.Image:
    image = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    fill = _battery_color(battery)
    outline = (235, 235, 235, 255)
    draw.rounded_rectangle((8, 18, 52, 46), radius=4, outline=outline, width=3)
    draw.rectangle((53, 26, 58, 38), fill=outline)

    if battery is None:
        draw.line((18, 24, 42, 40), fill=(230, 230, 230, 255), width=5)
        draw.line((42, 24, 18, 40), fill=(230, 230, 230, 255), width=5)
        return image

    width = max(2, int(38 * max(0, min(battery, 100)) / 100))
    draw.rectangle((11, 21, 11 + width, 43), fill=fill)

    label = str(battery)
    font = ImageFont.load_default()
    bbox = draw.textbbox((0, 0), label, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]
    draw.text(
        ((64 - text_width) / 2, (64 - text_height) / 2 - 1),
        label,
        fill=(0, 0, 0, 255),
        font=font,
    )
    return image


def _battery_color(battery: int | None) -> tuple[int, int, int, int]:
    if battery is None:
        return (110, 110, 110, 255)
    if battery <= LOW_BATTERY_PERCENT:
        return (220, 60, 55, 255)
    if battery <= 50:
        return (235, 185, 45, 255)
    return (75, 180, 95, 255)


if __name__ == "__main__":
    main()

