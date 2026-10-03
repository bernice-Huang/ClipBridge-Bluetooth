$ErrorActionPreference = 'Stop'
$cbProject = $PSScriptRoot
$cbPython = Join-Path $cbProject '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $cbPython)) {
    & py -3.12 -m venv (Join-Path $cbProject '.venv')
    if ($LASTEXITCODE -ne 0) { throw 'Python 3.12 is required.' }
}
& $cbPython -m pip install -r (Join-Path $cbProject 'requirements.txt')
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
& $cbPython -X utf8 (Join-Path $cbProject 'windows\diagnose.py') --advertise
if ($LASTEXITCODE -ne 0) { throw 'Bluetooth adapter probe failed.' }
Write-Host 'Ready. Double-click Start-ClipBridge-BLE.cmd.'
