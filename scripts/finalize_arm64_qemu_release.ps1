param(
  [string]$QemuExe = "work\tools\qemu-11.0.0\build-h1-arm64-release-winpath\qemu-system-mipsel.exe",
  [string]$KovBda = "h1-bda-sdk\build\H1KOVPlus-emulator.bda",
  [string]$LlvmStrip = ""
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot

function Resolve-RepositoryPath([string]$Path) {
  if ([System.IO.Path]::IsPathRooted($Path)) {
    return [System.IO.Path]::GetFullPath($Path)
  }
  return [System.IO.Path]::GetFullPath((Join-Path $repoRoot $Path))
}

function Assert-Arm64Pe([string]$Path) {
  $stream = [System.IO.File]::OpenRead($Path)
  try {
    $reader = [System.IO.BinaryReader]::new($stream)
    if ($reader.ReadUInt16() -ne 0x5A4D) {
      throw "not a PE executable (missing MZ header): $Path"
    }
    $stream.Position = 0x3C
    $peOffset = $reader.ReadUInt32()
    if ($peOffset -gt ($stream.Length - 6)) {
      throw "invalid PE header offset in $Path"
    }
    $stream.Position = $peOffset
    if ($reader.ReadUInt32() -ne 0x00004550) {
      throw "not a PE executable (missing PE signature): $Path"
    }
    $machine = $reader.ReadUInt16()
    if ($machine -ne 0xAA64) {
      throw ("expected ARM64 PE machine 0xAA64, found 0x{0:X4}: {1}" -f $machine, $Path)
    }
  } finally {
    $stream.Dispose()
  }
}

function Find-LlvmStrip([string]$RequestedPath) {
  $candidates = @()
  if ($RequestedPath) {
    $candidates += $RequestedPath
  }
  $candidates += "R:\clangarm64\bin\llvm-strip.exe"
  $command = Get-Command llvm-strip.exe -ErrorAction SilentlyContinue
  if ($command) {
    $candidates += $command.Source
  }
  foreach ($candidate in $candidates) {
    if ($candidate -and (Test-Path -LiteralPath $candidate -PathType Leaf)) {
      return (Resolve-Path -LiteralPath $candidate).Path
    }
  }
  throw "llvm-strip.exe not found; pass -LlvmStrip with the ARM64-capable LLVM tool path"
}

$qemuPath = Resolve-RepositoryPath $QemuExe
$bdaPath = Resolve-RepositoryPath $KovBda
$sanitizer = Join-Path $repoRoot "scripts\sanitize_binary_paths.py"
$auditor = Join-Path $repoRoot "scripts\audit_release_secrets.py"

foreach ($required in @($qemuPath, $bdaPath, $sanitizer, $auditor)) {
  if (-not (Test-Path -LiteralPath $required -PathType Leaf)) {
    throw "required file not found: $required"
  }
}

Assert-Arm64Pe $qemuPath
$stripPath = Find-LlvmStrip $LlvmStrip
$beforeSize = (Get-Item -LiteralPath $qemuPath).Length

& $stripPath --strip-all $qemuPath
if ($LASTEXITCODE -ne 0) {
  throw "llvm-strip failed with exit code $LASTEXITCODE"
}
Assert-Arm64Pe $qemuPath

python $sanitizer --in-place $qemuPath
if ($LASTEXITCODE -ne 0) {
  throw "binary path sanitizer failed with exit code $LASTEXITCODE"
}

python $auditor $qemuPath $bdaPath
if ($LASTEXITCODE -ne 0) {
  throw "release privacy audit failed with exit code $LASTEXITCODE"
}

$afterSize = (Get-Item -LiteralPath $qemuPath).Length
$qemuHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $qemuPath).Hash
$bdaHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $bdaPath).Hash

Write-Host ("ARM64 QEMU finalized: {0} -> {1} bytes" -f $beforeSize, $afterSize)
Write-Host "ARM64 QEMU SHA-256: $qemuHash"
Write-Host "KOV emulator BDA SHA-256: $bdaHash"
