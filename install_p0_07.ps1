param(
  [Parameter(Mandatory = $true)]
  [string]$RepoRoot
)
$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$repo = (Resolve-Path -LiteralPath $RepoRoot).Path
$files = @(
  'engine/check_row_ids.py',
  'engine/checks_service.py',
  'backend/api/check_apps_api.py',
  'backend/api/checks_api.py',
  'frontend/src/api/types.ts',
  'frontend/src/api/real.ts',
  'frontend/src/pages/checks/Checks.tsx',
  'tests/test_check_apps.py',
  'tests/test_check_apps_p007.py'
)
$backup = Join-Path (Split-Path -Parent $repo) ((Split-Path -Leaf $repo) + '_p0_07_backup')
foreach ($rel in $files) {
  $winRel = $rel.Replace('/', [IO.Path]::DirectorySeparatorChar)
  $src = Join-Path (Join-Path $here 'overlay') $winRel
  $dest = Join-Path $repo $winRel
  if (!(Test-Path -LiteralPath $src)) { throw "Не найден файл пакета: $src" }
  $parent = Split-Path -Parent $dest
  New-Item -ItemType Directory -Force -Path $parent | Out-Null
  if (Test-Path -LiteralPath $dest) {
    $backupPath = Join-Path $backup $winRel
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $backupPath) | Out-Null
    Copy-Item -LiteralPath $dest -Destination $backupPath -Force
  }
  Copy-Item -LiteralPath $src -Destination $dest -Force
  Write-Host "P0-07: $rel"
}
$main = Join-Path $repo 'backend/main.py'
if (Test-Path -LiteralPath $main) {
  $content = [IO.File]::ReadAllText($main)
  if (!$content.Contains('check_apps_api.router')) {
    $old = $content
    # The known backend/main.py registers a tuple of routers.
    $content = $content.Replace('checks_api.router)', 'checks_api.router, check_apps_api.router)')
    if (!$content.Contains('check_apps_api.router')) {
      Write-Warning 'Добавьте вручную app.include_router(check_apps_api.router) в backend/main.py'
    } else {
      if (!$content.Contains('check_apps_api' + [Environment]::NewLine)) {
        # The known import form is: from .api import ..., checks_api
        $content = [Regex]::Replace($content, '(from \.api import [^\r\n]*?\bchecks_api\b)(?!\s*,\s*check_apps_api)', '$1, check_apps_api', 1)
      }
      if (!$content.Contains('check_apps_api')) { throw 'Импорт check_apps_api не зарегистрирован' }
      $backupPath = Join-Path $backup 'backend/main.py'
      New-Item -ItemType Directory -Force -Path (Split-Path -Parent $backupPath) | Out-Null
      [IO.File]::WriteAllText($backupPath, $old)
      [IO.File]::WriteAllText($main, $content)
      Write-Host 'P0-07: backend/main.py (router added)'
    }
  }
}
Write-Host 'Готово. Проверьте git diff и выполните тесты из README.'
