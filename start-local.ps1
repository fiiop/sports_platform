$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$pythonPath = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) { throw 'Missing .venv. Follow the installation steps in README.md first.' }
$previewUrl = 'http://127.0.0.1:8000/'
function Test-Preview {
    try { return (Invoke-WebRequest -Uri $previewUrl -UseBasicParsing -TimeoutSec 2).StatusCode -eq 200 }
    catch { return $false }
}
if (-not (Test-Preview)) {
    $logFolder = Join-Path $PSScriptRoot 'artifacts'
    New-Item -ItemType Directory -Path $logFolder -Force | Out-Null
    $serverProcess = Start-Process -FilePath $pythonPath -ArgumentList @('-m','uvicorn','app.main:app','--host','127.0.0.1','--port','8000') -WorkingDirectory $PSScriptRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $logFolder 'local-server.log') -RedirectStandardError (Join-Path $logFolder 'local-server-error.log')
    $ready = $false
    for ($attempt = 0; $attempt -lt 30; $attempt++) {
        if (Test-Preview) { $ready = $true; break }
        if ($serverProcess.HasExited) { break }
        Start-Sleep -Milliseconds 300
    }
    if (-not $ready) { throw 'Server did not start. See artifacts/local-server-error.log.' }
    Write-Host "Local server started (PID $($serverProcess.Id))."
}
Write-Host "Open $previewUrl - do not open the HTML template directly."
Start-Process $previewUrl
