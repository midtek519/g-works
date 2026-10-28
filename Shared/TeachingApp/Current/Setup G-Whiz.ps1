param([string]$TeXBin,[switch]$UseBundledTeX,[string]$TeXInstallDir,[switch]$InstallTeX,[switch]$NoTeXDownload,[switch]$NoShortcut,[switch]$ChooseTeX,[ValidateSet('auto','existing','essentials','full')][string]$TeXChoice='auto')
$ErrorActionPreference='Stop'
$taskRoot=Split-Path -Parent $PSScriptRoot
$taskPython=Join-Path $taskRoot 'Dependencies\python\python.exe'
$taskProbe=@('-I','-B',(Join-Path $PSScriptRoot 'instructor_tex.py'),'--root',$taskRoot)
if($UseBundledTeX){$TeXBin=Join-Path $taskRoot 'Dependencies\texlive\bin\windows'}
if($TeXBin){$taskProbe+=@('--bin',$TeXBin);if($TeXChoice -eq 'auto'){$TeXChoice='existing'}}
$taskJson=& $taskPython @taskProbe
$taskFound=$taskJson|ConvertFrom-Json
if(-not $taskFound){throw 'The compiler check could not start. See the setup error above.'}
$taskAllowInstall=$false
if($TeXChoice -eq 'auto' -and $taskFound.usable -and (-not $ChooseTeX -or $NoTeXDownload)){$TeXChoice='existing'}
if($TeXChoice -eq 'auto'){
    if($NoTeXDownload){throw 'No verified compiler was found. Run setup without -NoTeXDownload to choose or repair one.'}
    if($InstallTeX){$TeXChoice='essentials'}else{
        Write-Host ''
        Write-Host 'G-Whiz PDF setup'
        Write-Host '1. Use an existing TeX Live or MiKTeX installation; check/install its required packages.'
        Write-Host '2. G-Whiz Essentials (recommended): a smaller TeX Live installation for G-Whiz.'
        Write-Host '3. Full TeX Live: the comprehensive installation; larger download and longer setup.'
        if($taskFound.bin){Write-Host ('Found: '+$taskFound.distribution+' in '+$taskFound.bin)}
        $taskAnswer=Read-Host 'Choose 1, 2, or 3 [2]'
        $TeXChoice=switch($taskAnswer){'1'{'existing';break}'3'{'full';break}'2'{'essentials';break}''{'essentials';break}default{throw 'Choose 1, 2, or 3. Run G-Whiz on Windows again to retry.'}}
        $taskAllowInstall=$TeXChoice -eq 'existing'
    }
}
if($TeXChoice -eq 'existing'){
    if(-not $taskFound.bin){
        if($NoTeXDownload){throw 'Choose an installed compiler with -TeXBin followed by its bin folder.'}
        $TeXBin=Read-Host 'Enter the TeX Live or MiKTeX bin folder containing pdflatex.exe'
        if(-not $TeXBin){throw 'No folder selected.'}
        $taskProbe+=@('--bin',$TeXBin)
    }
    $taskConfigure=$taskProbe+@('--configure')
    if(($InstallTeX -or $taskAllowInstall) -and -not $NoTeXDownload){$taskConfigure+='--install-missing'}
    Write-Host 'Checking required packages, fonts, and three sample PDFs...'
    $taskJson=& $taskPython @taskConfigure
    if($LASTEXITCODE -ne 0){
        $taskFailure=$taskJson|ConvertFrom-Json
        Write-Host $taskFailure.message
        if($NoTeXDownload -or $InstallTeX -or $taskAllowInstall){throw 'Compiler setup did not pass. Existing documents and settings were kept.'}
        $taskAnswer=Read-Host 'Allow setup to install missing required packages and retry? [Y/n]'
        if($taskAnswer -and $taskAnswer -notmatch '^(?i)y(es)?$'){throw 'Setup stopped. Run it again to choose G-Whiz Essentials.'}
        $taskJson=& $taskPython @taskConfigure '--install-missing'
        if($LASTEXITCODE -ne 0){throw (($taskJson|ConvertFrom-Json).message)}
    }
}else{
    if($NoTeXDownload){throw 'This choice downloads TeX Live. Remove -NoTeXDownload or choose an existing installation.'}
    $taskInstall=@('-I','-B',(Join-Path $PSScriptRoot 'tex_install.py'),'--root',$taskRoot,'--variant',$TeXChoice)
    if($TeXInstallDir){$taskInstall+=@('--destination',$TeXInstallDir)}
    & $taskPython @taskInstall
    if($LASTEXITCODE -ne 0){throw 'Installation did not finish. Existing installations and saved work were kept.'}
    $taskJson=& $taskPython @taskProbe '--configure'
    if($LASTEXITCODE -ne 0){throw (($taskJson|ConvertFrom-Json).message)}
}
Write-Host (($taskJson|ConvertFrom-Json).message)
& $taskPython -I -B (Join-Path $PSScriptRoot 'check_install.py') --root $taskRoot
if($LASTEXITCODE -ne 0){throw 'A required component is missing. See the message above.'}
Write-Host 'G-Whiz is ready. Future launches reuse this installation.'
