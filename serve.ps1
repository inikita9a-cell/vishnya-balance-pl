# Single-origin built frontend + API + HTTPS link from this Windows PC.
param([switch]$Setup, [string]$DataRoot = '', [int]$Port = 8000, [switch]$NoInstall)
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root
$Python = Join-Path $Root '.venv-web\Scripts\python.exe'
if (-not (Test-Path $Python)) {
    py -3.14 -m venv .venv-web
    if ($LASTEXITCODE -ne 0) { throw 'Python 3.14 is required. Install it before starting the web server.' }
}
if (-not $NoInstall) {
    & $Python -m pip install -r requirements.txt
    if ($LASTEXITCODE -ne 0) { throw 'Python dependencies could not be installed.' }
}
# Module execution makes backend imports resolve from the repository root.
if ($Setup) {
    $Options = @('-m','tools.web_server','setup')
    if ($DataRoot) { $Options += @('--data-root',$DataRoot) }
    & $Python @Options
} else {
    $Options = @('-m','tools.web_server','run','--port',"$Port")
    if ($NoInstall) { $Options += '--no-install' }
    & $Python @Options
}
if ($LASTEXITCODE -ne 0) { throw 'Web server command failed. See ERROR above.' }
