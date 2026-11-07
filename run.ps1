# Windows launcher. Ctrl+C stops the frontend and cleans up the backend.
# Usage: .\run.ps1              (backend + frontend)
#        .\run.ps1 -BackendOnly (backend only)
param([switch]$BackendOnly)

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

$Python = Join-Path $Root '.venv\Scripts\python.exe'
if (-not (Test-Path $Python)) {
    py -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Could not create Python virtual environment' }
}

& $Python -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw 'Python dependencies could not be installed' }

if ($BackendOnly -or -not (Test-Path (Join-Path $Root 'frontend\package.json'))) {
    if (-not $BackendOnly) {
        Write-Warning 'frontend/package.json not found; starting backend only.'
    }
    & $Python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
    if ($LASTEXITCODE -ne 0) { throw "Backend exited with code $LASTEXITCODE" }
    return
}

$Backend = $null
try {
    $Backend = Start-Process -FilePath $Python `
        -ArgumentList @('-m', 'uvicorn', 'backend.main:app', '--host', '127.0.0.1', '--port', '8000') `
        -WorkingDirectory $Root -PassThru -NoNewWindow
    Start-Sleep -Seconds 1
    if ($Backend.HasExited) { throw "Backend exited during startup: $($Backend.ExitCode)" }

    Push-Location (Join-Path $Root 'frontend')
    try {
        npm.cmd install
        if ($LASTEXITCODE -ne 0) { throw 'npm install failed' }
        # Keep the frontend process in the foreground; Ctrl+C stops it.
        npm.cmd run dev
        if ($LASTEXITCODE -ne 0) { throw "Frontend exited with code $LASTEXITCODE" }
    } finally {
        Pop-Location
    }
} finally {
    if ($null -ne $Backend -and -not $Backend.HasExited) {
        Stop-Process -Id $Backend.Id -Force -ErrorAction SilentlyContinue
        $Backend.WaitForExit()
    }
}
