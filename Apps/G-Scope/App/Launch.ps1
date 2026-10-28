param([switch]$Desktop,[switch]$ServiceOnly)
$ErrorActionPreference = 'Stop'
$scopeRoot = Split-Path -Parent $PSScriptRoot
$scopeHost = Join-Path $PSScriptRoot 'Desktop\desktop.py'
$scopePython = Join-Path $scopeRoot 'Dependencies\python\pythonw.exe'
if (-not (Test-Path -LiteralPath $scopePython) -or -not (Test-Path -LiteralPath $scopeHost)) {
    Add-Type -AssemblyName PresentationFramework
    [System.Windows.MessageBox]::Show('G-Scope desktop files are missing. Run G-Works Setup and choose Repair.','G-Scope') | Out-Null
    throw 'The G-Scope installation is incomplete.'
}
if ($ServiceOnly) {
    & (Join-Path $scopeRoot 'Dependencies\python\python.exe') -I -B $scopeHost --service-only
    exit $LASTEXITCODE
}
Start-Process -FilePath $scopePython -ArgumentList @('-I','-B',('"' + $scopeHost + '"')) -WorkingDirectory $scopeRoot -WindowStyle Hidden | Out-Null
