param([string]$TeXBin, [switch]$UseBundledTeX, [string]$TeXInstallDir, [switch]$InstallTeX, [switch]$NoTeXDownload, [switch]$NoShortcut, [switch]$ChooseTeX, [ValidateSet('auto','existing','essentials','full')][string]$TeXChoice='auto')
$ErrorActionPreference = 'Stop'
$appRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $appRoot 'Dependencies\python\python.exe'
if (-not (Test-Path -LiteralPath $python)) { throw 'Extract the complete G-Whiz folder before running setup. Included Python is missing.' }
$taskProfilePath=Join-Path $appRoot 'Data\edition.json'
if((Test-Path -LiteralPath $taskProfilePath) -and ((Get-Content -LiteralPath $taskProfilePath -Raw|ConvertFrom-Json).edition -eq 'math135-instructor')) { & (Join-Path $PSScriptRoot 'Setup G-Whiz.ps1') @PSBoundParameters; return }
$texArgs = @('-I','-B',(Join-Path $appRoot 'App\tex_setup.py'),'--root',$appRoot,'--configure')
if ($TeXBin) { $texArgs += @('--bin',$TeXBin) }
if ($UseBundledTeX) { $texArgs += '--bundled' }
$texJson = & $python @texArgs
if ($LASTEXITCODE -ne 0) {
    if ($TeXBin) { throw 'The selected TeX Live folder is missing a compiler or required package. Check -TeXBin or run setup without it to install TeX Live.' }
    if ($UseBundledTeX) { throw 'This package does not include a usable TeX Live. Run setup without -UseBundledTeX to reuse or download it.' }
    if ($NoTeXDownload) { throw 'No usable TeX Live was found. Run setup without -NoTeXDownload to install it.' }
    Write-Host ''
    Write-Host 'No usable TeX Live installation was found.'
    Write-Host 'G-Whiz can download the official TeX Live installer and install TeX Live for you.'
    Write-Host 'This requires Internet and several GB of free space. The first installation can take a long time.'
    Write-Host 'Later G-Whiz updates will reuse this installation.'
    if (-not $InstallTeX) {
        $answer = Read-Host 'Download and install TeX Live now? [Y/n]'
        if ($answer -and $answer -notmatch '^(?i)y(es)?$') { throw 'Setup stopped. Run Install G-Whiz again when you are ready.' }
    }
    $installArgs = @('-I','-B',(Join-Path $appRoot 'App\tex_install.py'),'--root',$appRoot)
    if ($TeXInstallDir) { $installArgs += @('--destination',$TeXInstallDir) }
    & $python @installArgs
    if ($LASTEXITCODE -ne 0) { throw 'TeX Live installation did not finish. See the message above. Existing installations and saved G-Whiz work were kept.' }
    $texJson = & $python @texArgs
    if ($LASTEXITCODE -ne 0) { throw 'TeX Live could not be verified. Run setup with -TeXBin followed by its bin folder.' }
}
$tex = $texJson | ConvertFrom-Json
Write-Host $tex.message
& $python -I -B (Join-Path $appRoot 'App\check_install.py') --root $appRoot
if ($LASTEXITCODE -ne 0) { throw 'A required component is missing. Extract all files from the G-Whiz package and rerun setup.' }
$displayName = 'G-Whiz'
$iconName = 'g-whiz.ico'
$profilePath = Join-Path $appRoot 'Data\edition.json'
if (-not (Test-Path -LiteralPath $profilePath)) { $profilePath = Join-Path $appRoot 'edition.json' }
if (Test-Path -LiteralPath $profilePath) {
    $taskEditionProfile = Get-Content -LiteralPath $profilePath -Raw | ConvertFrom-Json
    if ($taskEditionProfile.display_name) { $displayName = $taskEditionProfile.display_name }
    if ($taskEditionProfile.theme -eq 'rutgers') { $iconName = 'g-whiz-instructor.ico' }
}
if (-not $NoShortcut -and (-not $taskEditionProfile -or $taskEditionProfile.edition -ne 'math135-instructor')) {
$shortcutShell = New-Object -ComObject WScript.Shell
$shortcut = $shortcutShell.CreateShortcut((Join-Path $appRoot ($displayName + '.lnk')))
$shortcut.TargetPath = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
$shortcut.Arguments = '-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "' + (Join-Path $appRoot 'App\Launch.ps1') + '" -Desktop'
$shortcut.WorkingDirectory = $appRoot
$shortcut.IconLocation = Join-Path $appRoot ('App\static\' + $iconName)
$shortcut.Description = 'Open ' + $displayName
$shortcut.Save()
}
Write-Host ''
Write-Host "$displayName is ready."
Write-Host 'The app opens in its own desktop window. No separate PDF reader or Python installation is needed.'
