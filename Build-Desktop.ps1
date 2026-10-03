$ErrorActionPreference = 'Stop'
$cbRoot = $PSScriptRoot
$cbPython = Join-Path $cbRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $cbPython)) { throw 'Run Setup.ps1 first.' }
Push-Location -LiteralPath $cbRoot
try {
    & $cbPython -m pip install -r (Join-Path $cbRoot 'requirements-build.txt')
    if ($LASTEXITCODE -ne 0) { throw 'Build dependency installation failed.' }
    & $cbPython -m unittest discover -s tests
    if ($LASTEXITCODE -ne 0) { throw 'Tests failed; no release build made.' }
    & $cbPython -m PyInstaller --noconfirm --clean (Join-Path $cbRoot 'ClipBridgeBLE.spec')
    if ($LASTEXITCODE -ne 0) { throw 'EXE build failed.' }
    Write-Host "Built: $cbRoot\dist\ClipBridgeBLE.exe"
} finally { Pop-Location }
