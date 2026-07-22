from __future__ import annotations

import collections
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime

import pystray
import tkinter as tk
from PIL import Image, ImageDraw

from .battery import open_battery_readers, read_battery_once

LOW_BATTERY_PERCENT = 20
REFRESH_SECONDS = 60
HISTORY_LIMIT = 240


@dataclass
class TrayState:
    battery: int | None = None
    status: str = "Starting"
    notified_low: bool = False
    stop_requested: bool = False
    history: collections.deque[tuple[float, int]] = field(
        default_factory=lambda: collections.deque(maxlen=HISTORY_LIMIT)
    )
    history_lock: threading.Lock = field(default_factory=threading.Lock)


def main() -> None:
    state = TrayState()
    icon = pystray.Icon(
        "attack-shark-battery",
        icon=_make_icon(None),
        title="Attack Shark X11 Battery",
        menu=pystray.Menu(
            pystray.MenuItem(lambda _: _menu_status(state), None, enabled=False),
            pystray.MenuItem("Show history", lambda _: _show_history(state)),
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
    if battery is not None:
        with state.history_lock:
            state.history.append((time.time(), battery))
    if battery is None:
        state.status = "Battery unknown"
    else:
        state.status = f"Battery {battery}%"

    icon.title = f"Attack Shark X11 - {_hover_text(state)}"
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
    return _hover_text(state)


def _show_history(state: TrayState) -> None:
    snapshot = _history_snapshot(state)

    def _run_window() -> None:
        root = tk.Tk()
        root.title("Attack Shark X11 Battery History")
        root.geometry("720x420")
        root.minsize(640, 360)
        root.configure(bg="#111418")

        chart = tk.Canvas(root, bg="#111418", highlightthickness=0)
        chart.pack(fill="both", expand=True, padx=12, pady=12)

        info = tk.Label(
            root,
            text=_history_summary(snapshot),
            anchor="w",
            justify="left",
            bg="#111418",
            fg="#e8edf2",
            font=("Segoe UI", 10),
        )
        info.pack(fill="x", padx=12, pady=(0, 10))

        def redraw(_: object | None = None) -> None:
            _draw_history_chart(chart, snapshot)

        root.bind("<Configure>", redraw)
        redraw(None)
        root.mainloop()

    threading.Thread(target=_run_window, daemon=True).start()


def _history_snapshot(state: TrayState) -> list[tuple[float, int]]:
    with state.history_lock:
        return list(state.history)


def _history_summary(samples: list[tuple[float, int]]) -> str:
    if not samples:
        return "No battery samples yet. Wait for the next refresh."
    values = [value for _, value in samples]
    latest_time = datetime.fromtimestamp(samples[-1][0]).strftime("%H:%M:%S")
    return (
        f"Latest: {values[-1]}% at {latest_time}   "
        f"Min: {min(values)}%   Max: {max(values)}%"
    )


def _draw_history_chart(canvas: tk.Canvas, samples: list[tuple[float, int]]) -> None:
    canvas.delete("all")
    width = max(1, canvas.winfo_width())
    height = max(1, canvas.winfo_height())
    pad_left, pad_top, pad_right, pad_bottom = 56, 20, 20, 44
    plot_left = pad_left
    plot_top = pad_top
    plot_right = width - pad_right
    plot_bottom = height - pad_bottom

    if plot_right <= plot_left or plot_bottom <= plot_top:
        return

    # Grid and labels.
    for pct in (0, 25, 50, 75, 100):
        y = plot_bottom - (plot_bottom - plot_top) * pct / 100
        canvas.create_line(plot_left, y, plot_right, y, fill="#26303a")
        canvas.create_text(12, y, text=f"{pct}%", fill="#cfd8e3", anchor="w", font=("Segoe UI", 9))

    canvas.create_line(plot_left, plot_top, plot_left, plot_bottom, fill="#8fa3b5")
    canvas.create_line(plot_left, plot_bottom, plot_right, plot_bottom, fill="#8fa3b5")

    if len(samples) < 2:
        canvas.create_text(
            (plot_left + plot_right) / 2,
            (plot_top + plot_bottom) / 2,
            text="Waiting for more samples...",
            fill="#d8dee9",
            font=("Segoe UI", 11),
        )
        return

    times = [ts for ts, _ in samples]
    values = [value for _, value in samples]
    time_min = min(times)
    time_max = max(times)
    x_span = max(1.0, time_max - time_min)

    def x_for(ts: float) -> float:
        return plot_left + (ts - time_min) / x_span * (plot_right - plot_left)

    def y_for(value: int) -> float:
        return plot_bottom - value / 100 * (plot_bottom - plot_top)

    points: list[float] = []
    for ts, value in samples:
        points.extend([x_for(ts), y_for(value)])
    canvas.create_line(*points, fill="#61d36f", width=3, smooth=True)

    latest_ts, latest_value = samples[-1]
    latest_x = x_for(latest_ts)
    latest_y = y_for(latest_value)
    canvas.create_oval(latest_x - 5, latest_y - 5, latest_x + 5, latest_y + 5, fill="#61d36f", outline="")

    tick_count = min(6, len(samples))
    for index in range(tick_count):
        sample_index = round(index * (len(samples) - 1) / max(1, tick_count - 1))
        ts = samples[sample_index][0]
        x = x_for(ts)
        label = datetime.fromtimestamp(ts).strftime("%H:%M")
        canvas.create_line(x, plot_bottom, x, plot_bottom + 6, fill="#8fa3b5")
        canvas.create_text(x, plot_bottom + 20, text=label, fill="#cfd8e3", font=("Segoe UI", 9))


def _make_icon(battery: int | None) -> Image.Image:
    scale = 4
    image = Image.new("RGBA", (64 * scale, 64 * scale), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    fill = _battery_color(battery)
    outline = (248, 248, 248, 255)
    shell = (18, 21, 24, 255)

    def sbox(box: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
        return tuple(value * scale for value in box)

    # Bold battery body first, then a compact mouse cue so the icon reads at tray size.
    draw.rounded_rectangle(sbox((31, 6, 61, 57)), radius=6 * scale, fill=shell)
    draw.rounded_rectangle(sbox((31, 6, 61, 57)), radius=6 * scale, outline=outline, width=5 * scale)
    draw.rounded_rectangle(sbox((38, 1, 53, 8)), radius=2 * scale, fill=outline)

    inner_left, inner_top, inner_right, inner_bottom = 35, 11, 57, 52
    if battery is None:
        draw.line([(35 * scale, 17 * scale), (57 * scale, 46 * scale)], fill=outline, width=5 * scale)
        draw.line([(57 * scale, 17 * scale), (35 * scale, 46 * scale)], fill=outline, width=5 * scale)
    else:
        clamped = max(0, min(battery, 100))
        inner_height = inner_bottom - inner_top
        fill_height = max(3, int(inner_height * clamped / 100))
        fill_top = inner_bottom - fill_height
        draw.rounded_rectangle(
            sbox((inner_left, fill_top, inner_right, inner_bottom)),
            radius=3 * scale,
            fill=fill,
        )

    draw.rounded_rectangle(sbox((0, 9, 31, 49)), radius=13 * scale, fill=shell, outline=outline, width=5 * scale)
    draw.line(sbox((16, 8, 16, 4)), fill=outline, width=5 * scale)
    draw.rounded_rectangle(sbox((4, 17, 26, 42)), radius=9 * scale, fill=(44, 51, 57, 255))
    draw.line(sbox((13, 20, 13, 30)), fill=fill, width=4 * scale)

    return image.resize((64, 64), Image.Resampling.LANCZOS)


def _battery_color(battery: int | None) -> tuple[int, int, int, int]:
    if battery is None:
        return (110, 110, 110, 255)
    if battery <= LOW_BATTERY_PERCENT:
        return (220, 60, 55, 255)
    if battery <= 50:
        return (235, 185, 45, 255)
    return (75, 180, 95, 255)


def _hover_text(state: TrayState) -> str:
    battery = state.battery
    if battery is None:
        return "Battery unknown"
    return f"Battery {battery}%"


if __name__ == "__main__":
    main()
