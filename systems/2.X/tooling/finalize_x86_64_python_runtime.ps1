param(
  [string]$MsysRoot = "work\rebuild\tools\msys2-20260611\msys64",
  [string]$OutputRoot = "emulator\windows-x86_64\python"
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

function Invoke-IsolatedPython([string]$Exe) {
  $start = [System.Diagnostics.ProcessStartInfo]::new()
  $start.FileName = $Exe
  $start.Arguments = '-I -B -c "import argparse,hashlib,json,socket,subprocess,threading,webbrowser,sys; print(sys.version); print(''portable-imports=ok'')"'
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
    throw "portable Python failed with exit code $($process.ExitCode): $stderr"
  }
  if ($stdout -notmatch "portable-imports=ok") {
    throw "portable Python did not complete its import probe: $stdout"
  }
  return $stdout
}

$msysPath = Resolve-RepositoryPath $MsysRoot
$outputPath = Resolve-RepositoryPath $OutputRoot $false
$expectedOutput = Join-Path $repoRoot "emulator\windows-x86_64\python"
if (-not $outputPath.Equals($expectedOutput, [System.StringComparison]::OrdinalIgnoreCase)) {
  throw "refusing to prune an unexpected Python output directory: $outputPath"
}

$ucrtBin = Join-Path $msysPath "ucrt64\bin"
$sourceLib = Join-Path $msysPath "ucrt64\lib\python3.14"
$objdump = Join-Path $ucrtBin "objdump.exe"
$sanitizer = Join-Path $repoRoot "scripts\sanitize_binary_paths.py"
$auditor = Join-Path $repoRoot "scripts\audit_release_secrets.py"
$bootstrapPython = Join-Path $ucrtBin "python.exe"
foreach ($required in @($sourceLib, $objdump, $sanitizer, $auditor, $bootstrapPython)) {
  if (-not (Test-Path -LiteralPath $required)) {
    throw "required Python runtime input not found: $required"
  }
}

$staging = Join-Path $repoRoot "work\rebuild\tmp\python-runtime-x64-$PID"
$staging = Resolve-RepositoryPath $staging $false
if (Test-Path -LiteralPath $staging) {
  throw "refusing to replace an existing staging directory: $staging"
}
New-Item -ItemType Directory -Path $staging | Out-Null

try {
  foreach ($name in @(
    "python.exe", "python3.exe", "python3.14.exe", "pythonw.exe",
    "python3w.exe", "libpython3.dll", "libpython3.14.dll"
  )) {
    $source = Join-Path $ucrtBin $name
    if (Test-Path -LiteralPath $source -PathType Leaf) {
      Copy-Item -LiteralPath $source -Destination (Join-Path $staging $name)
    }
  }

  $destinationLib = Join-Path $staging "Lib\python3.14"
  $excludedTopLevel = @(
    "Tools", "__phello__", "config-3.14", "ensurepip", "idlelib",
    "pydoc_data", "site-packages", "test", "tkinter", "turtledemo", "venv"
  )
  $excludedFiles = @(
    "_sysconfigdata__win32_.py", "_sysconfig_vars__win32_.json",
    "build-details.json"
  )
  foreach ($source in Get-ChildItem -LiteralPath $sourceLib -File -Recurse) {
    $relative = $source.FullName.Substring($sourceLib.Length).TrimStart("\")
    $topLevel = $relative.Split("\")[0]
    if ($source.FullName -match "\\__pycache__\\" -or
        $source.Extension.ToLowerInvariant() -in @(".pyc", ".pyo") -or
        $topLevel -in $excludedTopLevel -or
        $source.Name -in $excludedFiles -or
        ($topLevel -eq "lib-dynload" -and $source.BaseName -match "^(_test|_tkinter|_xx|xx)")) {
      continue
    }
    $destination = Join-Path $destinationLib $relative
    $parent = Split-Path -Parent $destination
    if (-not (Test-Path -LiteralPath $parent)) {
      New-Item -ItemType Directory -Path $parent -Force | Out-Null
    }
    Copy-Item -LiteralPath $source.FullName -Destination $destination
  }

  $pending = [System.Collections.Generic.Queue[string]]::new()
  foreach ($binary in Get-ChildItem -LiteralPath $staging -File -Recurse | Where-Object {
    $_.Extension.ToLowerInvariant() -in @(".exe", ".dll", ".pyd")
  }) {
    Assert-X64Pe $binary.FullName
    $pending.Enqueue($binary.FullName)
  }
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

  $releasePeFiles = @(Get-ChildItem -LiteralPath $staging -File -Recurse | Where-Object {
    $_.Extension.ToLowerInvariant() -in @(".exe", ".dll", ".pyd")
  })
  & $bootstrapPython $sanitizer --in-place @($releasePeFiles.FullName)
  if ($LASTEXITCODE -ne 0) {
    throw "binary path sanitizer failed"
  }
  foreach ($file in $releasePeFiles) {
    Assert-X64Pe $file.FullName
  }

  $stagedPython = Join-Path $staging "python.exe"
  $probe = Invoke-IsolatedPython $stagedPython
  & $bootstrapPython $auditor $staging
  if ($LASTEXITCODE -ne 0) {
    throw "release privacy audit failed"
  }

  New-Item -ItemType Directory -Path $outputPath -Force | Out-Null
  $expected = @{}
  foreach ($file in Get-ChildItem -LiteralPath $staging -File -Recurse) {
    $relative = $file.FullName.Substring($staging.Length).TrimStart("\")
    $expected[$relative.ToLowerInvariant()] = $true
    $destination = Join-Path $outputPath $relative
    $parent = Split-Path -Parent $destination
    if (-not (Test-Path -LiteralPath $parent)) {
      New-Item -ItemType Directory -Path $parent -Force | Out-Null
    }
    Copy-Item -LiteralPath $file.FullName -Destination $destination -Force
  }

  $removedFiles = 0
  foreach ($file in Get-ChildItem -LiteralPath $outputPath -File -Recurse) {
    $relative = $file.FullName.Substring($outputPath.Length).TrimStart("\")
    if (-not $expected.ContainsKey($relative.ToLowerInvariant())) {
      Remove-Item -LiteralPath $file.FullName -Force
      $removedFiles++
    }
  }
  foreach ($directory in Get-ChildItem -LiteralPath $outputPath -Directory -Recurse |
      Sort-Object { $_.FullName.Length } -Descending) {
    if (-not (Get-ChildItem -LiteralPath $directory.FullName -Force)) {
      Remove-Item -LiteralPath $directory.FullName -Force
    }
  }

  $finalProbe = Invoke-IsolatedPython (Join-Path $outputPath "python.exe")
  $fileCount = (Get-ChildItem -LiteralPath $outputPath -File -Recurse).Count
  $cacheCount = (Get-ChildItem -LiteralPath $outputPath -Directory -Recurse |
    Where-Object { $_.Name -eq "__pycache__" }).Count
  if ($cacheCount -ne 0) {
    throw "portable Python still contains $cacheCount cache directories"
  }
  Write-Host ($finalProbe.Trim())
  Write-Host "runtime_files=$fileCount"
  Write-Host "runtime_pe_files=$($releasePeFiles.Count)"
  Write-Host "removed_stale_files=$removedFiles"
} finally {
  if (Test-Path -LiteralPath $staging) {
    Remove-Item -LiteralPath $staging -Recurse -Force
  }
}
