$ErrorActionPreference = 'Stop'
$appRoot = $PSScriptRoot
$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) {
  throw 'Python 3.10 or newer was not found in PATH.'
}
& $python.Source -B (Join-Path $appRoot 'h2_emulator.py') @args
exit $LASTEXITCODE
