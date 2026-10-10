$ErrorActionPreference = 'Stop'
$previewRoot = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$asciiRoot = Join-Path $env:LOCALAPPDATA 'Temp\shiying-android-01a116b2'
if ((Test-Path -LiteralPath $asciiRoot) -and ((Resolve-Path -LiteralPath $asciiRoot).Path)) {
    # The project's existing junction avoids SDK path encoding problems on Windows.
    $resolvedTarget = (Get-Item -LiteralPath $asciiRoot).Target
    if ($resolvedTarget -contains $previewRoot) { $env:SHIYING_BUILD_ROOT = $asciiRoot }
}
$env:PYTHONUTF8 = '1'
try {
    $response = Invoke-WebRequest 'http://127.0.0.1:8787/state' -UseBasicParsing -TimeoutSec 2
    if ($response.StatusCode -eq 200) { exit 0 }
} catch { }
$python = Join-Path $previewRoot '.venv\Scripts\python.exe'
if (!(Test-Path -LiteralPath $python)) { throw 'Configure the project Python environment first; see android/README.md.' }
$script = Join-Path $PSScriptRoot 'preview_server.py'
$logs = Join-Path $previewRoot '.tmp'
New-Item -ItemType Directory -Path $logs -Force | Out-Null
Start-Process -FilePath $python -ArgumentList @('"' + $script + '"') -WorkingDirectory $previewRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $logs 'preview-server.log') -RedirectStandardError (Join-Path $logs 'preview-server-error.log') | Out-Null
