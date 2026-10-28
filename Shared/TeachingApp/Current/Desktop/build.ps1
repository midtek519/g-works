$ErrorActionPreference = 'Stop'
$compilerPath = Join-Path $env:WINDIR 'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
$versionSource = Join-Path $env:TEMP ('gworks-desktop-version-' + [Guid]::NewGuid().ToString('N') + '.cs')
try {
    '[assembly:System.Reflection.AssemblyVersion("1.0.0.3")][assembly:System.Reflection.AssemblyFileVersion("1.0.0.3")][assembly:System.Reflection.AssemblyInformationalVersion("1.0.0-beta.3")]' | Set-Content -LiteralPath $versionSource -Encoding UTF8
    $chromePath = Join-Path $PSScriptRoot 'GWorks.Chrome.dll'
    & $compilerPath /nologo /target:library /optimize+ "/out:$chromePath" /reference:System.Drawing.dll /reference:System.Windows.Forms.dll (Join-Path $PSScriptRoot 'NativeChrome.cs') $versionSource
    if ($LASTEXITCODE -ne 0) { throw 'Shared desktop compilation failed.' }
    & $compilerPath /nologo /target:library /optimize+ "/out:$(Join-Path $PSScriptRoot 'GWorks.Branding.dll')" "/reference:$chromePath" /reference:System.Drawing.dll /reference:System.Windows.Forms.dll /reference:System.Core.dll (Join-Path $PSScriptRoot 'NativeBranding.cs') $versionSource
    if ($LASTEXITCODE -ne 0) { throw 'Shared branding compilation failed.' }
} finally {
    Remove-Item -LiteralPath $versionSource -ErrorAction SilentlyContinue
}
