param(
  [string]$CleanClone = "work\rebuild\upstream\DingooExtractor-clean",
  [string]$ReferenceRoot = "references\dingoo\DingooExtractor",
  [string]$AssetRoot = "emulator\windows-x86_64\assets\a320",
  [string]$Manifest = "h1-bda-sdk\ports\dingoo_a320\assets\app_manifest.json"
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot

function Resolve-RepositoryPath([string]$Path, [bool]$MustExist = $true) {
  if ([System.IO.Path]::IsPathRooted($Path)) {
    $full = [System.IO.Path]::GetFullPath($Path)
  } else {
    $full = [System.IO.Path]::GetFullPath((Join-Path $repoRoot $Path))
  }
  $prefix = $repoRoot.TrimEnd("\") + "\"
  if (-not $full.StartsWith($prefix, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "path is outside the repository: $full"
  }
  if ($MustExist -and -not (Test-Path -LiteralPath $full)) {
    throw "required path not found: $full"
  }
  return $full
}

$cleanPath = Resolve-RepositoryPath $CleanClone
$referencePath = Resolve-RepositoryPath $ReferenceRoot
$assetPath = Resolve-RepositoryPath $AssetRoot $false
$manifestPath = Resolve-RepositoryPath $Manifest
$manifestData = Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8 | ConvertFrom-Json

$commit = (& git -C $cleanPath rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0 -or $commit -ne $manifestData.upstream_commit) {
  throw "clean DingooExtractor checkout is not the reviewed commit: $commit"
}

foreach ($app in $manifestData.apps) {
  $source = Join-Path (Join-Path $cleanPath "app") $app.source_name
  if (-not (Test-Path -LiteralPath $source -PathType Leaf)) {
    throw "missing reviewed APP: $source"
  }
  $item = Get-Item -LiteralPath $source
  $hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $source).Hash
  if ($item.Length -ne $app.bytes -or $hash -ne $app.sha256) {
    throw "APP manifest mismatch: $($app.source_name)"
  }
}

$trackedFiles = @(& git -c core.quotePath=false -C $cleanPath ls-files)
if ($LASTEXITCODE -ne 0 -or $trackedFiles.Count -eq 0) {
  throw "cannot enumerate the reviewed DingooExtractor checkout"
}
foreach ($relative in $trackedFiles) {
  $nativeRelative = $relative.Replace("/", "\")
  $source = Join-Path $cleanPath $nativeRelative
  $destination = Join-Path $referencePath $nativeRelative
  if (-not (Test-Path -LiteralPath $source -PathType Leaf)) {
    throw "tracked source file is missing: $source"
  }
  $parent = Split-Path -Parent $destination
  if (-not (Test-Path -LiteralPath $parent)) {
    New-Item -ItemType Directory -Path $parent -Force | Out-Null
  }
  Copy-Item -LiteralPath $source -Destination $destination -Force
}

New-Item -ItemType Directory -Path $assetPath -Force | Out-Null
foreach ($app in $manifestData.apps) {
  $source = Join-Path (Join-Path $referencePath "app") $app.source_name
  $destination = Join-Path $assetPath $app.runtime_name
  Copy-Item -LiteralPath $source -Destination $destination -Force
  $hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $destination).Hash
  if ((Get-Item -LiteralPath $destination).Length -ne $app.bytes -or
      $hash -ne $app.sha256) {
    throw "deployed APP verification failed: $($app.runtime_name)"
  }
}

foreach ($relative in $trackedFiles) {
  $nativeRelative = $relative.Replace("/", "\")
  $source = Join-Path $cleanPath $nativeRelative
  $destination = Join-Path $referencePath $nativeRelative
  if (-not (Test-Path -LiteralPath $destination -PathType Leaf) -or
      (Get-FileHash -Algorithm SHA256 -LiteralPath $source).Hash -ne
      (Get-FileHash -Algorithm SHA256 -LiteralPath $destination).Hash) {
    throw "restored tracked file differs from the reviewed commit: $relative"
  }
}

Write-Host "restored_reference_files=$($trackedFiles.Count)"
Write-Host "verified_and_deployed_apps=$($manifestData.apps.Count)"
Write-Host "upstream_commit=$commit"
