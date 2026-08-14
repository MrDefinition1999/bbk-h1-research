param(
  [string]$QemuExe = "work\rebuild\tmp\qemu-build-h1-x64-2\qemu-system-mipsel.exe",
  [string]$MsysRoot = "work\rebuild\tools\msys2-20260611\msys64",
  [string]$OutputBin = "emulator\windows-x86_64\bin",
  [string]$PythonExe = "work\rebuild\venv\Scripts\python.exe",
  [switch]$PruneStale
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot

function Resolve-RepositoryPath([string]$Path, [bool]$MustExist = $true) {
  if ([System.IO.Path]::IsPathRooted($Path)) {
    $full = [System.IO.Path]::GetFullPath($Path)
  } else {
    $full = [System.IO.Path]::GetFullPath((Join-Path $repoRoot $Path))
  }
  $repoPrefix = $repoRoot.TrimEnd("\") + "\"
  if (-not $full.StartsWith($repoPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "path is outside the repository: $full"
  }
  if ($MustExist -and -not (Test-Path -LiteralPath $full)) {
    throw "required path not found: $full"
  }
  return $full
}

function Assert-X64Pe([string]$Path) {
  $stream = [System.IO.File]::OpenRead($Path)
  try {
    $reader = [System.IO.BinaryReader]::new($stream)
    if ($reader.ReadUInt16() -ne 0x5A4D) {
      throw "not a PE file (missing MZ header): $Path"
    }
    $stream.Position = 0x3C
    $peOffset = $reader.ReadUInt32()
    if ($peOffset -gt ($stream.Length - 6)) {
      throw "invalid PE header offset: $Path"
    }
    $stream.Position = $peOffset
    if ($reader.ReadUInt32() -ne 0x00004550) {
      throw "not a PE file (missing PE signature): $Path"
    }
    $machine = $reader.ReadUInt16()
    if ($machine -ne 0x8664) {
      throw ("expected x86-64 PE machine 0x8664, found 0x{0:X4}: {1}" -f $machine, $Path)
    }
  } finally {
    $stream.Dispose()
  }
}

function Get-ImportedDlls([string]$Objdump, [string]$Path) {
  $output = & $Objdump -p $Path
  if ($LASTEXITCODE -ne 0) {
    throw "objdump failed for $Path"
  }
  $names = foreach ($line in $output) {
    $match = [regex]::Match($line, "^\s*DLL Name:\s*(.+?)\s*$")
    if ($match.Success) {
      $match.Groups[1].Value
    }
  }
  return @($names | Sort-Object -Unique)
}

function Invoke-IsolatedQemu([string]$Exe, [string]$Arguments) {
  $start = [System.Diagnostics.ProcessStartInfo]::new()
  $start.FileName = $Exe
  $start.Arguments = $Arguments
  $start.WorkingDirectory = Split-Path -Parent $Exe
  $start.UseShellExecute = $false
  $start.RedirectStandardOutput = $true
  $start.RedirectStandardError = $true
  $start.EnvironmentVariables["PATH"] = "$env:SystemRoot\System32"
  $process = [System.Diagnostics.Process]::Start($start)
  $stdout = $process.StandardOutput.ReadToEnd()
  $stderr = $process.StandardError.ReadToEnd()
  $process.WaitForExit()
  if ($process.ExitCode -ne 0) {
    throw "QEMU failed in isolated PATH with exit code $($process.ExitCode): $stderr"
  }
  return $stdout
}

$qemuPath = Resolve-RepositoryPath $QemuExe
$msysPath = Resolve-RepositoryPath $MsysRoot
$outputPath = Resolve-RepositoryPath $OutputBin $false
$pythonPath = Resolve-RepositoryPath $PythonExe
$ucrtBin = Join-Path $msysPath "ucrt64\bin"
$objdump = Join-Path $ucrtBin "objdump.exe"
$strip = Join-Path $ucrtBin "strip.exe"
$sanitizer = Join-Path $repoRoot "scripts\sanitize_binary_paths.py"
$auditor = Join-Path $repoRoot "scripts\audit_release_secrets.py"

foreach ($required in @($objdump, $strip, $sanitizer, $auditor)) {
  if (-not (Test-Path -LiteralPath $required -PathType Leaf)) {
    throw "required tool not found: $required"
  }
}
Assert-X64Pe $qemuPath

$staging = Join-Path $repoRoot "work\rebuild\tmp\qemu-runtime-x64-$PID"
$staging = Resolve-RepositoryPath $staging $false
if (Test-Path -LiteralPath $staging) {
  throw "refusing to replace an existing staging directory: $staging"
}
New-Item -ItemType Directory -Path $staging | Out-Null

try {
  $stagedQemu = Join-Path $staging "qemu-system-mipsel.exe"
  Copy-Item -LiteralPath $qemuPath -Destination $stagedQemu
  $previousSourceDateEpoch = $env:SOURCE_DATE_EPOCH
  try {
    $env:SOURCE_DATE_EPOCH = "0"
    & $strip --strip-all $stagedQemu
    if ($LASTEXITCODE -ne 0) {
      throw "failed to strip QEMU"
    }
  } finally {
    $env:SOURCE_DATE_EPOCH = $previousSourceDateEpoch
  }
  Assert-X64Pe $stagedQemu

  $pending = [System.Collections.Generic.Queue[string]]::new()
  $pending.Enqueue($stagedQemu)
  $visited = @{}
  while ($pending.Count -gt 0) {
    $binary = $pending.Dequeue()
    $key = [System.IO.Path]::GetFileName($binary).ToLowerInvariant()
    if ($visited.ContainsKey($key)) {
      continue
    }
    $visited[$key] = $true
    foreach ($dll in Get-ImportedDlls $objdump $binary) {
      $dllKey = $dll.ToLowerInvariant()
      if ($visited.ContainsKey($dllKey)) {
        continue
      }
      $source = Join-Path $ucrtBin $dll
      if (Test-Path -LiteralPath $source -PathType Leaf) {
        $destination = Join-Path $staging $dll
        if (-not (Test-Path -LiteralPath $destination)) {
          Copy-Item -LiteralPath $source -Destination $destination
          Assert-X64Pe $destination
        }
        $pending.Enqueue($destination)
        continue
      }
      $systemDll = Join-Path "$env:SystemRoot\System32" $dll
      if (-not (Test-Path -LiteralPath $systemDll -PathType Leaf) -and
          $dllKey -notlike "api-ms-win-*.dll") {
        throw "cannot resolve imported DLL $dll required by $binary"
      }
    }
  }

  $releaseFiles = @(Get-ChildItem -LiteralPath $staging -File | Sort-Object Name)
  & $pythonPath $sanitizer --in-place @($releaseFiles.FullName)
  if ($LASTEXITCODE -ne 0) {
    throw "binary path sanitizer failed"
  }
  foreach ($file in $releaseFiles) {
    Assert-X64Pe $file.FullName
  }

  $version = Invoke-IsolatedQemu $stagedQemu "--version"
  if ($version -notmatch "QEMU emulator version 11\.0\.0") {
    throw "unexpected QEMU version output: $version"
  }
  $machines = Invoke-IsolatedQemu $stagedQemu "-machine help"
  if ($machines -notmatch "(?m)^bbkh1\s") {
    throw "the staged QEMU does not expose the bbkh1 machine"
  }

  & $pythonPath $auditor @($releaseFiles.FullName)
  if ($LASTEXITCODE -ne 0) {
    throw "release privacy audit failed"
  }

  New-Item -ItemType Directory -Path $outputPath -Force | Out-Null
  foreach ($file in $releaseFiles) {
    Copy-Item -LiteralPath $file.FullName -Destination (Join-Path $outputPath $file.Name) -Force
  }
  if ($PruneStale) {
    $expected = @{}
    foreach ($file in $releaseFiles) {
      $expected[$file.Name.ToLowerInvariant()] = $true
    }
    foreach ($file in Get-ChildItem -LiteralPath $outputPath -File) {
      if (-not $expected.ContainsKey($file.Name.ToLowerInvariant())) {
        Remove-Item -LiteralPath $file.FullName -Force
        Write-Host "removed stale runtime file: $($file.Name)"
      }
    }
  }

  $finalQemu = Join-Path $outputPath "qemu-system-mipsel.exe"
  $finalVersion = Invoke-IsolatedQemu $finalQemu "--version"
  $hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $finalQemu).Hash
  Write-Host ($finalVersion.Trim())
  Write-Host "runtime_files=$($releaseFiles.Count)"
  Write-Host "qemu_sha256=$hash"
} finally {
  if (Test-Path -LiteralPath $staging) {
    Remove-Item -LiteralPath $staging -Recurse -Force
  }
}
