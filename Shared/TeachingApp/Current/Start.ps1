param([switch]$NoBrowser,[switch]$NoTeXDownload,[switch]$Setup,[string]$TeXBin,[string]$TeXInstallDir,[switch]$InstallTeX,[ValidateSet('auto','existing','essentials','full')][string]$TeXChoice='auto')
$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
$taskPython = Join-Path $taskRoot 'Dependencies\python\python.exe'
$taskMarker = Join-Path $taskRoot 'Data\Setup\windows.json'
if (-not (Test-Path -LiteralPath $taskPython)) { throw 'Extract the complete G-Whiz folder before opening it.' }
if ($Setup -or -not (Test-Path -LiteralPath $taskMarker)) {
    Write-Host 'First-time setup: checking the tools G-Whiz needs.'
    & (Join-Path $PSScriptRoot 'Install G-Whiz.ps1') -NoTeXDownload:$NoTeXDownload -TeXBin $TeXBin -TeXInstallDir $TeXInstallDir -InstallTeX:$InstallTeX -TeXChoice $TeXChoice -ChooseTeX:$Setup
    if (-not $?) { throw 'Setup did not finish. Open G-Whiz on Windows again to retry.' }
    New-Item -ItemType Directory -Path (Split-Path -Parent $taskMarker) -Force | Out-Null
    '{"ready":true}' | Set-Content -LiteralPath $taskMarker -Encoding utf8
}
if (-not $NoBrowser) { & (Join-Path $PSScriptRoot 'Launch.ps1')  }
