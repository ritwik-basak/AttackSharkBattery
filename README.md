# Attack Shark X11 Battery Utility

Experimental Windows tooling for finding and decoding the battery report from an
Attack Shark X11 wireless mouse without opening the official Attack Shark software.

The protocol can differ between Linux and Windows, so the first step is discovery:
enumerate HID interfaces, identify likely vendor-specific interfaces, and log raw
reports before writing a battery decoder.

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
```

If `hidapi` fails to install, install Microsoft Visual C++ Build Tools or try the
latest Python 3.13 wheel published for `hidapi`.

## Build a Windows App

To create a standalone tray executable:

```powershell
.\build-windows.ps1
```

The built app will be in:

```powershell
.\dist\AttackSharkBattery.exe
```

For people who do not use VS Code or Python, the easiest release flow is:

1. Build `AttackSharkBattery.exe`.
2. Zip the `dist` output.
3. Upload the zip to GitHub Releases.
4. Tell users to download, unzip, and run the EXE.

If you want it to start automatically after login, the app already has an
`autostart enable` command that can be run once on the user's machine.

## Phase 1: HID Enumeration

Print every HID interface:

```powershell
attack-shark-battery enumerate
```

Filter to likely Attack Shark devices by name:

```powershell
attack-shark-battery enumerate --match shark
```

Prefer JSON when sharing output:

```powershell
attack-shark-battery enumerate --json > hid-devices.json
```

Look for vendor-specific interfaces where `usage_page` is often `0xff00` or another
`0xffxx` value. The normal mouse interface is usually not the one that exposes
battery data.

## Phase 2: HID Packet Logging

After choosing a device path from enumeration, log input reports:

```powershell
attack-shark-battery log --path "<device path>"
```

You can also open by VID/PID and optional interface number:

```powershell
attack-shark-battery log --vid 0x3554 --pid 0xf58a --interface 1
```

Move the mouse, let it idle, connect/disconnect charging, or open the official
software while logging. Save the output and compare repeating bytes with known
Linux reports.

If no passive input reports appear, probe feature and input reports:

```powershell
attack-shark-battery probe --vid 0x1d57 --pid 0xfa60 --interface 2 --usage-page 0x0001 --usage 0x0080 --kind both --end-id 0xff
```

Try the other interface 2 collections from `enumerate` as well. Feature reports
are often used for device state on Windows when interrupt reads stay quiet.

## Phase 3: Battery Reading

Read the current battery percentage:

```powershell
attack-shark-battery battery
```

Watch for battery changes:

```powershell
attack-shark-battery battery --watch
```

On the tested X11 receiver, Windows exposes the battery packet on:

- VID/PID: `0x1d57:0xfa60`
- Interface: `2`
- Usage Page: `0x000a`
- Usage: `0x0000`
- Packet: `03 55 40 01 XX`, where `XX` is the battery percentage.

## Phase 4: Tray App

Start the tray utility:

```powershell
attack-shark-battery-tray
```

The tray app refreshes every 60 seconds, uses a green/yellow/red battery icon,
updates the tooltip, and sends one low-battery notification at 20% or below.

Enable startup after Windows login:

```powershell
attack-shark-battery autostart enable
```

Check or disable startup:

```powershell
attack-shark-battery autostart status
attack-shark-battery autostart disable
```

## Current Status

- Phase 1 HID enumeration: implemented.
- Phase 2 raw packet logging and feature/input probing: implemented as CLI experiments.
- Phase 3 battery decoding: implemented for the observed Windows HID packet.
- Phase 4 tray utility: implemented.
- Phase 5 PyInstaller packaging: added as `build-windows.ps1`.
