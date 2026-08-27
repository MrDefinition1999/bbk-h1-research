[CmdletBinding(SupportsShouldProcess = $true)]
param()

$ErrorActionPreference = "Stop"
Add-Type -AssemblyName Microsoft.VisualBasic

$RepositoryRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$RepositoryPrefix = $RepositoryRoot.TrimEnd(
    [System.IO.Path]::DirectorySeparatorChar
) + [System.IO.Path]::DirectorySeparatorChar

# This one-time cleanup list is intentionally narrow.  It excludes every active
# H1/H2 NAND/eMMC image, firmware input, IDA database, current S1 resource,
# manifest and active rollback journal.
$RelativeTargets = @(
    "work\h2\toolchain-temp\llvm-mingw-20240518-ucrt-aarch64.zip",
    "work\h2\toolchain-temp\zig-aarch64-windows-0.16.0.zip",
    "work\h2\innoextract-1.9-windows.zip",
    "work\h2\s1-resource-test\undo-h1v1-current.sectors.gz",
    "work\h2\derived\qemu-system-mipsel-h2-mission-devices.exe",
    "work\h2\derived\qemu-system-mipsel-h2-mission.exe",
    "work\h2\mission-backup\qemu-system-mipsel-pre-mission-tcu.exe",
    "work\h2\screencheck",
    "work\h2\build-temp",
    "work\h2\h2-qemu-auto-resume.log",
    "work\h2\h2-qemu-diagnose.log",
    "work\h2\h2-qemu-live.log",
    "scripts\__pycache__",
    "systems\2.X\tooling\__pycache__",
    "h1-bda-sdk\h1_bda\__pycache__",
    "h1-bda-sdk\reverse\tools\__pycache__",
    "work\h2\external\BBK9588-shiming\scripts\__pycache__"
)

function Resolve-SafeTarget([string] $RelativePath) {
    $Target = [System.IO.Path]::GetFullPath((Join-Path $RepositoryRoot $RelativePath))
    if (-not $Target.StartsWith(
        $RepositoryPrefix,
        [System.StringComparison]::OrdinalIgnoreCase
    )) {
        throw "cleanup target escaped repository: $Target"
    }
    if ($Target -eq $RepositoryRoot) {
        throw "refusing repository-root cleanup"
    }
    return $Target
}

function Get-PathBytes([string] $Path) {
    if ([System.IO.File]::Exists($Path)) {
        return [System.IO.FileInfo]::new($Path).Length
    }
    if ([System.IO.Directory]::Exists($Path)) {
        return (Get-ChildItem -LiteralPath $Path -File -Recurse -Force |
            Measure-Object -Property Length -Sum).Sum
    }
    return 0
}

function Send-ToRecycleBin([string] $Path) {
    if ([System.IO.Directory]::Exists($Path)) {
        [Microsoft.VisualBasic.FileIO.FileSystem]::DeleteDirectory(
            $Path,
            [Microsoft.VisualBasic.FileIO.UIOption]::OnlyErrorDialogs,
            [Microsoft.VisualBasic.FileIO.RecycleOption]::SendToRecycleBin,
            [Microsoft.VisualBasic.FileIO.UICancelOption]::ThrowException
        )
        return
    }
    if ([System.IO.File]::Exists($Path)) {
        [Microsoft.VisualBasic.FileIO.FileSystem]::DeleteFile(
            $Path,
            [Microsoft.VisualBasic.FileIO.UIOption]::OnlyErrorDialogs,
            [Microsoft.VisualBasic.FileIO.RecycleOption]::SendToRecycleBin,
            [Microsoft.VisualBasic.FileIO.UICancelOption]::ThrowException
        )
    }
}

$Targets = [System.Collections.Generic.List[string]]::new()
foreach ($RelativePath in $RelativeTargets) {
    $Target = Resolve-SafeTarget $RelativePath
    if (Test-Path -LiteralPath $Target) {
        $Targets.Add($Target)
    }
}

# These are terminal screenshots from superseded S1 wrapper attempts.  The
# conclusions and hashes are already recorded in the handoff documentation;
# current manifests, BDAs and journals in the same directory are preserved.
$S1TestRoot = Resolve-SafeTarget "work\h2\s1-resource-test"
if (Test-Path -LiteralPath $S1TestRoot -PathType Container) {
    Get-ChildItem -LiteralPath $S1TestRoot -File -Force |
        Where-Object { $_.Extension.ToLowerInvariant() -in @(".png", ".ppm") } |
        ForEach-Object { $Targets.Add($_.FullName) }
}

$Targets = $Targets | Sort-Object -Unique
$Selected = [System.Collections.Generic.List[object]]::new()
foreach ($Target in $Targets) {
    $Resolved = [System.IO.Path]::GetFullPath($Target)
    if (-not $Resolved.StartsWith(
        $RepositoryPrefix,
        [System.StringComparison]::OrdinalIgnoreCase
    )) {
        throw "resolved target escaped repository: $Resolved"
    }
    $Selected.Add([PSCustomObject]@{
        Path = $Resolved
        Bytes = Get-PathBytes $Resolved
    })
}

$TotalBytes = ($Selected | Measure-Object -Property Bytes -Sum).Sum
Write-Output ("selected={0} bytes={1} mib={2:N2}" -f `
    $Selected.Count, $TotalBytes, ($TotalBytes / 1MB))

foreach ($Item in $Selected) {
    $Relative = $Item.Path.Substring($RepositoryPrefix.Length)
    Write-Output ("target={0} bytes={1}" -f $Relative, $Item.Bytes)
    if ($PSCmdlet.ShouldProcess($Item.Path, "move to Windows Recycle Bin")) {
        Send-ToRecycleBin $Item.Path
        if (Test-Path -LiteralPath $Item.Path) {
            throw "target remains after recycle operation: $($Item.Path)"
        }
        Write-Output ("recycled={0}" -f $Relative)
    }
}

Write-Output ("reclaimed_mib={0:N2}" -f ($TotalBytes / 1MB))
