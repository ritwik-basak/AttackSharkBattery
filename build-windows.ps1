param(
    [switch]$Clean
)

$ErrorActionPreference = "Stop"

if ($Clean) {
    Remove-Item -Recurse -Force .\build, .\dist -ErrorAction SilentlyContinue
}

python -m pip install -e .[tray,build]
python -m PyInstaller `
    --noconfirm `
    --clean `
    --onefile `
    --windowed `
    --name AttackSharkBattery `
    --paths src `
    --collect-all pystray `
    --collect-all PIL `
    --add-data "README.md;." `
    src\attack_shark_battery\tray.py

Write-Host ""
Write-Host "Build complete. See .\dist\AttackSharkBattery.exe"
