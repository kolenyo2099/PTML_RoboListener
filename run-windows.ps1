$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$backendPort = if ($env:BACKEND_PORT) { $env:BACKEND_PORT } else { '8000' }
$frontendPort = if ($env:FRONTEND_PORT) { $env:FRONTEND_PORT } else { '5173' }
$children = @()

function Fail([string]$message) { throw "RoboListener: $message" }
function Test-PortFree([int]$port) {
    $listener = [System.Net.Sockets.TcpListener]::new([Net.IPAddress]::Loopback, $port)
    try { $listener.Start(); return $true } catch { return $false } finally { $listener.Stop() }
}
function Stop-Children {
    foreach ($child in $children) {
        if ($child -and -not $child.HasExited) {
            & taskkill.exe /PID $child.Id /T /F 2>$null | Out-Null
        }
    }
}

try {
    if (-not (Get-Command python -ErrorAction SilentlyContinue)) { Fail 'Python 3.10 or newer is required. Install it from https://www.python.org/downloads/ and enable Add Python to PATH.' }
    if (-not (Get-Command npm -ErrorAction SilentlyContinue)) { Fail 'Node.js and npm are required. Install the current LTS release from https://nodejs.org/.' }
    foreach ($value in @($backendPort, $frontendPort)) {
        $parsed = 0
        if (-not [int]::TryParse($value, [ref]$parsed) -or $parsed -lt 1 -or $parsed -gt 65535) { Fail 'BACKEND_PORT and FRONTEND_PORT must be between 1 and 65535.' }
    }
    if ($backendPort -eq $frontendPort) { Fail 'Backend and frontend ports must be different.' }

    Set-Location $root
    if (-not (Test-Path '.venv\Scripts\python.exe') -or -not (Test-Path 'frontend\node_modules\vite\bin\vite.js')) {
        Write-Host 'First-time setup is needed; installing project dependencies...'
        & (Join-Path $root 'setup-windows.ps1')
        if ($LASTEXITCODE -ne 0) { Fail 'Dependency setup failed. Review the setup error above.' }
    }
    foreach ($portText in @($backendPort, $frontendPort)) {
        if (-not (Test-PortFree ([int]$portText))) { Fail "Port $portText is already in use. Stop the other app or set BACKEND_PORT / FRONTEND_PORT to free ports." }
    }

    $env:BACKEND_PORT = $backendPort
    $backendArgs = '-m uvicorn app.main:app --app-dir "' + (Join-Path $root 'backend') + '" --host 127.0.0.1 --port ' + $backendPort
    $backend = Start-Process -FilePath (Join-Path $root '.venv\Scripts\python.exe') -ArgumentList $backendArgs -WorkingDirectory $root -NoNewWindow -PassThru
    $children += $backend
    $node = (Get-Command node -ErrorAction Stop).Source
    $viteScript = Join-Path $root 'frontend\node_modules\vite\bin\vite.js'
    $frontendArgs = '"' + $viteScript + '" --host 127.0.0.1 --port ' + $frontendPort + ' --strictPort'
    $frontend = Start-Process -FilePath $node -ArgumentList $frontendArgs -WorkingDirectory (Join-Path $root 'frontend') -NoNewWindow -PassThru
    $children += $frontend

    $appUrl = "http://127.0.0.1:$frontendPort"
    Write-Host 'RoboListener is starting...'
    $ready = $false
    for ($i = 0; $i -lt 60; $i++) {
        if ($backend.HasExited) { Fail 'The backend stopped during startup. Check the error above.' }
        if ($frontend.HasExited) { Fail 'The frontend stopped during startup. Check the error above.' }
        try {
            Invoke-WebRequest -Uri $appUrl -TimeoutSec 2 -UseBasicParsing | Out-Null
            Invoke-WebRequest -Uri "http://127.0.0.1:$backendPort/openapi.json" -TimeoutSec 2 -UseBasicParsing | Out-Null
            $ready = $true; break
        } catch { Start-Sleep -Seconds 1 }
    }
    if (-not $ready) { Fail 'RoboListener did not become ready within 60 seconds. Check the service errors above.' }
    Write-Host "RoboListener is ready: $appUrl"
    Write-Host "Backend: http://127.0.0.1:$backendPort"
    Write-Host 'Keep this window open while using RoboListener. Press Ctrl+C to stop it.'
    Start-Process $appUrl
    while (-not $backend.HasExited -and -not $frontend.HasExited) { Start-Sleep -Seconds 2 }
    Fail 'A service stopped. RoboListener is shutting down; check the messages above.'
} catch {
    Write-Host $_.Exception.Message -ForegroundColor Red
    exit 1
} finally {
    Stop-Children
}
