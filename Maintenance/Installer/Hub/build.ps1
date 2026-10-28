$ErrorActionPreference = 'Stop'
$launcherRoot = $PSScriptRoot
$compiler = Join-Path $env:WINDIR 'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
$resources = @('/resource:' + (Join-Path $launcherRoot '../public-key.json') + ',gworks-public-key.json')
foreach ($brand in @('g-works','g-whiz','g-scope','g-vault','g-view','g-rater','g-report','chrome-extensions','settings')) {
    $resources += '/resource:' + (Join-Path $launcherRoot ('Assets/brand-' + $brand + '.png')) + ',Brand.' + $brand + '.png'
}
$arguments = @('/nologo','/target:winexe',('/out:' + (Join-Path $launcherRoot 'G-Works.exe')),('/win32icon:' + (Join-Path $launcherRoot 'g-works.ico'))) + $resources
foreach ($library in @('System.Windows.Forms','System.Drawing','System.Web.Extensions','System.Numerics')) { $arguments += '/reference:' + $library + '.dll' }
foreach ($source in @('Hub.cs','HubArt.cs','ReleaseUpdates.cs')) { $arguments += Join-Path $launcherRoot $source }
& $compiler @arguments
if ($LASTEXITCODE -ne 0) { throw 'Launcher compilation failed.' }
