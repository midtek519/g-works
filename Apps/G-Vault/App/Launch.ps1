param([switch]$Desktop,[switch]$ServiceOnly)
$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
$taskPython = Join-Path $taskRoot 'Dependencies\python\pythonw.exe'
$taskHostPath = Join-Path $PSScriptRoot 'Desktop\desktop.py'
if (-not (Test-Path -LiteralPath $taskPython) -or -not (Test-Path -LiteralPath $taskHostPath)) {
    Add-Type -AssemblyName PresentationFramework
    [System.Windows.MessageBox]::Show('Desktop files are missing. Run G-Works Setup and choose Repair.','G-Works') | Out-Null
    throw 'The G-Works desktop installation is incomplete.'
}
if ($ServiceOnly) {
    & (Join-Path $taskRoot 'Dependencies\python\python.exe') -I -B $taskHostPath --service-only
    exit $LASTEXITCODE
}
Start-Process -FilePath $taskPython -ArgumentList @('-I','-B',('"' + $taskHostPath + '"')) -WorkingDirectory $taskRoot -WindowStyle Hidden | Out-Null
