$ErrorActionPreference='Stop'
[Console]::InputEncoding=[Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false)
function Reply($value){[Console]::Out.WriteLine(($value|ConvertTo-Json -Compress -Depth 6));[Console]::Out.Flush()}
try {
 Add-Type -AssemblyName System.Runtime.WindowsRuntime
 $null=[Windows.Media.Ocr.OcrEngine,Windows.Foundation,ContentType=WindowsRuntime]
 $null=[Windows.Globalization.Language,Windows.Foundation,ContentType=WindowsRuntime]
 $null=[Windows.Storage.Streams.InMemoryRandomAccessStream,Windows.Storage.Streams,ContentType=WindowsRuntime]
 $null=[Windows.Storage.Streams.DataWriter,Windows.Storage.Streams,ContentType=WindowsRuntime]
 $null=[Windows.Graphics.Imaging.BitmapDecoder,Windows.Foundation,ContentType=WindowsRuntime]
 $null=[Windows.Graphics.Imaging.SoftwareBitmap,Windows.Foundation,ContentType=WindowsRuntime]
 $null=[Windows.Media.Ocr.OcrResult,Windows.Foundation,ContentType=WindowsRuntime]
 $script:asTask=([System.WindowsRuntimeSystemExtensions].GetMethods()|Where-Object { $_.Name -eq 'AsTask' -and $_.IsGenericMethodDefinition -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation'+[char]96+'1' }|Select-Object -First 1)
 function Await($operation,[Type]$type){
  $task=$script:asTask.MakeGenericMethod($type).Invoke($null,@($operation))
  return $task.GetAwaiter().GetResult()
 }
 $language=[Windows.Globalization.Language]::new('en-US')
 $engine=[Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage($language)
 if($null -eq $engine){$engine=[Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages()}
 if($null -eq $engine){throw 'OCR unavailable'}
 Reply @{ready=$true;engine='windows-ocr'}
} catch {Reply @{ready=$false;engine='unavailable'};exit 0}
while($null -ne ($line=[Console]::In.ReadLine())){
 $stream=$null;$writer=$null;$bitmap=$null
 try {
  if($line.Length -gt 8000000){throw 'Input too large'}
  $inputData=$line|ConvertFrom-Json
  $bytes=[Convert]::FromBase64String($inputData.image)
  $stream=[Windows.Storage.Streams.InMemoryRandomAccessStream]::new()
  $writer=[Windows.Storage.Streams.DataWriter]::new($stream)
  $writer.WriteBytes($bytes)
  $null=Await ($writer.StoreAsync()) ([UInt32])
  $writer.DetachStream()|Out-Null;$writer.Dispose();$writer=$null
  $stream.Seek(0)
  $decoder=Await ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
  $bitmap=Await ($decoder.GetSoftwareBitmapAsync([Windows.Graphics.Imaging.BitmapPixelFormat]::Bgra8,[Windows.Graphics.Imaging.BitmapAlphaMode]::Premultiplied)) ([Windows.Graphics.Imaging.SoftwareBitmap])
  $result=Await ($engine.RecognizeAsync($bitmap)) ([Windows.Media.Ocr.OcrResult])
  Reply @{ok=$true;text=[string]$result.Text}
 }catch {Reply @{ok=$false;text=''}}
 finally {
  if($null -ne $bitmap){$bitmap.Dispose()}
  if($null -ne $writer){$writer.Dispose()}
  if($null -ne $stream){$stream.Dispose()}
 }
}
