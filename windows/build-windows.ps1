param(
    [string]$PythonCommand = "py -3.12",
    [switch]$Clean
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
$BuildRoot = Join-Path $Root "build-windows"
$Venv = Join-Path $BuildRoot ".venv"
$Kit = Join-Path $BuildRoot "nokia-xg040gmd-windows-x64"
$Zip = Join-Path $BuildRoot "nokia-xg040gmd-windows-x64.zip"

if ($Clean -and (Test-Path $BuildRoot)) {
    Remove-Item -Recurse -Force $BuildRoot
}
New-Item -ItemType Directory -Force -Path $BuildRoot | Out-Null

$PythonParts = $PythonCommand -split " "
$PythonExe = $PythonParts[0]
$PythonArgs = @()
if ($PythonParts.Count -gt 1) {
    $PythonArgs = $PythonParts[1..($PythonParts.Count - 1)]
}

& $PythonExe @PythonArgs -m venv $Venv
$VenvPython = Join-Path $Venv "Scripts\python.exe"
& $VenvPython -m pip install --upgrade pip
& $VenvPython -m pip install "pyinstaller==6.21.0"

Push-Location $Root
try {
    & $VenvPython -m PyInstaller `
        --noconfirm `
        --clean `
        --onefile `
        --name nokia-xg040gmd-tools `
        --paths $Root `
        --add-data "$Root\router;router" `
        --distpath "$BuildRoot\dist" `
        --workpath "$BuildRoot\pyinstaller" `
        --specpath "$BuildRoot" `
        "$Root\tools\nokia_tools.py"
}
finally {
    Pop-Location
}

if (Test-Path $Kit) {
    Remove-Item -Recurse -Force $Kit
}
New-Item -ItemType Directory -Force -Path $Kit | Out-Null
Copy-Item "$BuildRoot\dist\nokia-xg040gmd-tools.exe" $Kit
Copy-Item "$Root\windows\README_WINDOWS_RU.md" $Kit
Copy-Item "$Root\LICENSE" $Kit

if (Test-Path $Zip) {
    Remove-Item -Force $Zip
}
Compress-Archive -Path "$Kit\*" -DestinationPath $Zip -CompressionLevel Optimal

Write-Host "Built: $Zip"
Write-Host "Executable: $Kit\nokia-xg040gmd-tools.exe"
