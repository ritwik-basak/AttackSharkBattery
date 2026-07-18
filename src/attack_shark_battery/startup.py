from __future__ import annotations

import os
import subprocess
import sys
import winreg

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_VALUE_NAME = "AttackSharkBattery"
STARTUP_SCRIPT_NAME = "AttackSharkBattery.vbs"
TASK_NAME = "AttackSharkBattery"


def build_startup_command() -> str:
    pythonw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    launcher = pythonw if os.path.exists(pythonw) else sys.executable
    return f"{_quote(launcher)} -m attack_shark_battery.tray"


def enable_startup(command: str | None = None) -> str:
    command = command or build_startup_command()
    _delete_run_key_value()
    _delete_scheduled_task()

    script_path = _startup_script_path()
    os.makedirs(os.path.dirname(script_path), exist_ok=True)
    with open(script_path, "w", encoding="utf-8") as file:
        file.write('Set shell = CreateObject("WScript.Shell")\n')
        file.write(f'shell.Run "{_escape_vbs_string(command)}", 0, False\n')
    return script_path


def disable_startup() -> bool:
    removed = _delete_run_key_value()
    removed = _delete_scheduled_task() or removed
    script_path = _startup_script_path()
    if os.path.exists(script_path):
        os.remove(script_path)
        removed = True
    return removed


def get_startup_command() -> str | None:
    script_path = _startup_script_path()
    if os.path.exists(script_path):
        return script_path
    return _get_run_key_value()


def _startup_script_path() -> str:
    return os.path.join(
        os.environ["APPDATA"],
        "Microsoft",
        "Windows",
        "Start Menu",
        "Programs",
        "Startup",
        STARTUP_SCRIPT_NAME,
    )


def _get_run_key_value() -> str | None:
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_READ) as key:
        try:
            value, _ = winreg.QueryValueEx(key, RUN_VALUE_NAME)
        except FileNotFoundError:
            return None
    return str(value)


def _delete_run_key_value() -> bool:
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
        try:
            winreg.DeleteValue(key, RUN_VALUE_NAME)
        except FileNotFoundError:
            return False
    return True


def _delete_scheduled_task() -> bool:
    result = subprocess.run(
        ["schtasks.exe", "/Delete", "/TN", TASK_NAME, "/F"],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0


def _quote(value: str) -> str:
    return f'"{value}"'


def _escape_vbs_string(value: str) -> str:
    return value.replace('"', '""')
