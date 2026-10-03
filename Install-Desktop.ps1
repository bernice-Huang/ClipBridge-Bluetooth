param(
    [string]$Destination = [Environment]::GetFolderPath('Desktop'),
    [string]$DataDirectory = (Join-Path ([Environment]::GetFolderPath('LocalApplicationData')) 'ClipBridgeBLE'),
    [switch]$NoStartup
)
$ErrorActionPreference = 'Stop'
function Get-ClipBridgeHash([string]$Path) {
    $cbHasher = [Security.Cryptography.SHA256]::Create()
    $cbInputStream = [IO.File]::OpenRead($Path)
    try { return [BitConverter]::ToString($cbHasher.ComputeHash($cbInputStream)) }
    finally { $cbInputStream.Dispose(); $cbHasher.Dispose() }
}
$cbRoot = [IO.Path]::GetFullPath($PSScriptRoot)
$cbBinary = Join-Path $cbRoot 'ClipBridgeBLE.exe'
if (-not (Test-Path -LiteralPath $cbBinary -PathType Leaf)) { $cbBinary = Join-Path $cbRoot 'dist\ClipBridgeBLE.exe' }
if (-not (Test-Path -LiteralPath $cbBinary -PathType Leaf)) { throw 'No EXE found. Extract the Windows release ZIP, or run Build-Desktop.ps1 first.' }
$cbDestination = [IO.Path]::GetFullPath($Destination)
$cbTarget = [IO.Path]::GetFullPath((Join-Path $cbDestination 'ClipBridgeBLE.exe'))
if ([IO.Path]::GetDirectoryName($cbTarget) -ne $cbDestination.TrimEnd('\')) { throw 'Unexpected destination path.' }
$cbData = [IO.Path]::GetFullPath($DataDirectory)
$cbSession = Join-Path $cbData 'session.json'
$cbLegacy = Join-Path $cbRoot 'session.json'
$cbRunKey = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run'
$cbRunValue = '"' + $cbTarget + '" --startup'
if (-not $NoStartup -and (Test-Path -LiteralPath $cbRunKey)) {
    $cbRunProperty = (Get-ItemProperty -LiteralPath $cbRunKey).PSObject.Properties['ClipBridgeBLE']
    if ($cbRunProperty -and $cbRunProperty.Value -ne $cbRunValue) {
        throw 'An existing ClipBridgeBLE startup entry points elsewhere; disable it in the old app before installing to a new location.'
    }
}

# Every new user gets an independent secret. Never include a real session.json
# in a public ZIP, and never overwrite a malformed existing configuration.
New-Item -ItemType Directory -Path $cbData -Force | Out-Null
if (Test-Path -LiteralPath $cbSession) {
    $cbExistingKey = (Get-Content -Raw -LiteralPath $cbSession | ConvertFrom-Json).key
    if ($cbExistingKey -notmatch '^[0-9a-fA-F]{32}$') { throw 'Existing pairing key is invalid; not overwritten.' }
} else {
    if (Test-Path -LiteralPath $cbLegacy) {
        $cbNewKey = (Get-Content -Raw -LiteralPath $cbLegacy | ConvertFrom-Json).key
        if ($cbNewKey -notmatch '^[0-9a-fA-F]{32}$') { throw 'Legacy pairing key is invalid; not overwritten.' }
    } else {
        $cbRandom = [Security.Cryptography.RandomNumberGenerator]::Create()
        try {
            $cbBytes = New-Object byte[] 16
            $cbRandom.GetBytes($cbBytes)
            $cbNewKey = ([BitConverter]::ToString($cbBytes)).Replace('-', '').ToLowerInvariant()
        } finally { $cbRandom.Dispose() }
    }
    $cbStream = [IO.File]::Open($cbSession, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
    try {
        $cbWriter = New-Object IO.StreamWriter($cbStream, (New-Object Text.UTF8Encoding($false)))
        try { $cbWriter.Write('{"protocol":1,"key":"' + $cbNewKey + '"}') }
        finally { $cbWriter.Dispose() }
    } finally { $cbStream.Dispose() }
}

New-Item -ItemType Directory -Path $cbDestination -Force | Out-Null
if ((Test-Path -LiteralPath $cbTarget) -and $cbBinary -ne $cbTarget) {
    if ((Get-ClipBridgeHash $cbTarget) -ne (Get-ClipBridgeHash $cbBinary)) {
        $cbBackupDir = Join-Path $cbData 'backups'
        New-Item -ItemType Directory -Path $cbBackupDir -Force | Out-Null
        Copy-Item -LiteralPath $cbTarget -Destination (Join-Path $cbBackupDir ('before-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '.exe'))
    }
}
if ($cbBinary -ne $cbTarget) { Copy-Item -LiteralPath $cbBinary -Destination $cbTarget -Force }
if (-not $NoStartup) {
    New-Item -Path $cbRunKey -Force | Out-Null
    New-ItemProperty -LiteralPath $cbRunKey -Name 'ClipBridgeBLE' -Value $cbRunValue -PropertyType String -Force | Out-Null
    $cbApproved = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run'
    if ((Test-Path -LiteralPath $cbApproved) -and
        (Get-ItemProperty -LiteralPath $cbApproved).PSObject.Properties['ClipBridgeBLE']) {
        Remove-ItemProperty -LiteralPath $cbApproved -Name 'ClipBridgeBLE' -ErrorAction SilentlyContinue
    }
}
Write-Host "Installed: $cbTarget"
Write-Host "Private configuration: $cbData (key not printed)"
if ($NoStartup) { Write-Host 'Startup registrations were not changed.' }
else { Write-Host 'Starts at the next Windows sign-in. Only this app startup entry was changed.' }
Write-Host 'Close any previous sender, then open the EXE. No app was launched by this installer.'
