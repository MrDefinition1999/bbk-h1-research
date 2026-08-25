[CmdletBinding(SupportsShouldProcess = $true)]
param()

$ErrorActionPreference = "Stop"
Add-Type -AssemblyName Microsoft.VisualBasic

$Workspace = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$WorkspacePrefix = $Workspace.TrimEnd([System.IO.Path]::DirectorySeparatorChar) + [System.IO.Path]::DirectorySeparatorChar

# These are derived, reproducible, duplicated, or obsolete artifacts. Canonical
# V1/V2 images, private inputs, public component repositories, and deliverables
# are intentionally absent from this list.
$RelativeTargets = @(
    "backups\BBK-H1-essential-source-and-research-sanitized-2026-08-05.zip",
    "backups\BBK-H1-essential-source-and-research-sanitized-2026-08-06.zip",
    "system-recovery-h1.elf.i64",
    "h1-bda-sdk\.pytest_cache",
    "h1-bda-sdk\build",
    "work\emulator",
    "work\rebuild\tools",
    "work\rebuild\tmp",
    "work\rebuild\qemu-gpg",
    "work\rebuild\msys2-base-x86_64-20260611.sfx.exe",
    "work\rebuild\qemu-11.0.0.tar.xz",
    "work\rebuild\qemu-11.0.0.tar.xz.sig",
    "work\rebuild\qemu-release-key.asc",
    "work\rebuild\firmware",
    "work\rebuild\qemu-11.0.0",
    "work\rebuild\qemu-11.0.0-build-bbk9588-win",
    "work\rebuild\python-deps",
    "work\rebuild\runtime-backups",
    "work\v2-mission-full-expanded.raw",
    "work\v2-mission-full-expanded-template.raw",
    "work\v2-mission-full-expanded-6144.raw",
    "work\v2-mission-full-expanded-template-6144.raw",
    "work\v2-mission-biologytest.raw",
    "work\v2-v1-game-compat-assets-test.raw",
    "work\v2-v1-game-compat-test.raw",
    "work\v2-mission-pettemplate.raw",
    "work\v2-mission-initfix.raw",
    "work\v2-mission-full-native.raw",
    "work\v2-mission-full-expanded-root",
    "work\v2-pc-indexed",
    "work\v2-v1-game-compat-release",
    "work\kov-analysis",
    "work\kov-release",
    "work\kov-release-final",
    "work\captures",
    "work\v2-mission-loader-debug",
    "work\v2-mission-loader-external-debug",
    "work\analysis\qemu-system-mipsel-before-aic-final-drain.exe",
    "work\analysis\firmware\h1-project-layout.tmp.elf",
    "work\analysis\hzk-test.bin",
    "work\analysis\hzk-assets-test.bin",
    "work\analysis\h2-encrypted-test-clip.avi",
    "work\analysis\v1-ad-video.avi",
    "work\analysis\v1-robinsons-video.avi",
    "work\analysis\v1-v2-flying-video-compat-v2.bda",
    "work\analysis\v1-v2-flying-video-compat-v2.json",
    "work\analysis\v1-v2-flying-video-compat-v3.bda",
    "work\analysis\v1-v2-flying-video-compat-v3.json",
    "work\analysis\v2-native-flying-video-base40.elf",
    "work\analysis\v2-native-flying-video.metadata.json",
    "work\analysis\v2-native-flying-video.payload",
    "work\analysis\v2-video-arm64-baseline-raw.json",
    "work\analysis\v2-video-arm64-tail-raw.json",
    "work\analysis\v2-video-full-playback-raw.json",
    "work\analysis\v2-video-patched-full-raw.json",
    "work\analysis\v2-video-post-end-raw.json",
    "work\v2-emulator\old-player.bin"
)

function Resolve-SafeTarget([string] $RelativePath) {
    $FullPath = [System.IO.Path]::GetFullPath((Join-Path $Workspace $RelativePath))
    if (-not $FullPath.StartsWith($WorkspacePrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "cleanup target escaped workspace: $FullPath"
    }
    if ($FullPath -eq $Workspace) {
        throw "refusing workspace root cleanup"
    }
    return $FullPath
}

function Get-PathBytes([string] $Path) {
    if ([System.IO.File]::Exists($Path)) {
        return [System.IO.FileInfo]::new($Path).Length
    }
    if ([System.IO.Directory]::Exists($Path)) {
        return (Get-ChildItem -LiteralPath $Path -File -Recurse -Force -ErrorAction SilentlyContinue |
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

# Runtime caches may be regenerated anywhere under the local research tree.
Get-ChildItem -LiteralPath $Workspace -Directory -Recurse -Force -ErrorAction SilentlyContinue |
    Where-Object {
        $_.Name -in @("__pycache__", ".pytest_cache") -and
        $_.FullName -notlike "$Workspace\.git*" -and
        $_.FullName -notlike "$Workspace\systems*" -and
        $_.FullName -notlike "$Workspace\work\publication*"
    } |
    ForEach-Object { $Targets.Add($_.FullName) }

# Visual/debug captures and logs are reproducible transients.  Preserve IDA
# databases: their annotations are primary reverse-engineering state needed by
# later research even when the original input can be re-extracted.
$GeneratedExtensions = @(".png", ".frame", ".rgba", ".log")
foreach ($Area in @("work\analysis", "work\v2-emulator")) {
    $AreaPath = Resolve-SafeTarget $Area
    if (Test-Path -LiteralPath $AreaPath) {
        Get-ChildItem -LiteralPath $AreaPath -File -Recurse -Force -ErrorAction SilentlyContinue |
            Where-Object { $_.Extension.ToLowerInvariant() -in $GeneratedExtensions } |
            ForEach-Object { $Targets.Add($_.FullName) }
    }
}

# Early navigation screenshots were also written directly under work/.
$WorkPath = Resolve-SafeTarget "work"
Get-ChildItem -LiteralPath $WorkPath -File -Force -ErrorAction SilentlyContinue |
    Where-Object { $_.Extension.ToLowerInvariant() -in $GeneratedExtensions } |
    ForEach-Object { $Targets.Add($_.FullName) }

$Targets = $Targets | Sort-Object -Unique
$ProtectedRoots = @(
    (Resolve-SafeTarget "work\private"),
    (Resolve-SafeTarget "work\publication"),
    (Resolve-SafeTarget "references\official"),
    (Resolve-SafeTarget "deliverables"),
    (Resolve-SafeTarget "systems")
)

$Selected = [System.Collections.Generic.List[object]]::new()
foreach ($Target in $Targets) {
    if ($ProtectedRoots | Where-Object { $Target.StartsWith($_, [System.StringComparison]::OrdinalIgnoreCase) }) {
        throw "cleanup target entered protected root: $Target"
    }
    # Skip children when an explicit parent directory is already selected.
    if ($Selected | Where-Object { $Target.StartsWith(($_.Path.TrimEnd('\') + '\'), [System.StringComparison]::OrdinalIgnoreCase) }) {
        continue
    }
    $Selected.Add([PSCustomObject]@{ Path = $Target; Bytes = Get-PathBytes $Target })
}

$TotalBytes = ($Selected | Measure-Object -Property Bytes -Sum).Sum
Write-Output ("selected={0} bytes={1} gib={2:N3}" -f $Selected.Count, $TotalBytes, ($TotalBytes / 1GB))

foreach ($Item in $Selected) {
    if ($PSCmdlet.ShouldProcess($Item.Path, "move to Windows Recycle Bin")) {
        Send-ToRecycleBin $Item.Path
        if (Test-Path -LiteralPath $Item.Path) {
            throw "target still exists after recycle operation: $($Item.Path)"
        }
        Write-Output ("recycled={0} bytes={1}" -f $Item.Path.Substring($WorkspacePrefix.Length), $Item.Bytes)
    }
}

Write-Output ("reclaimed_gib={0:N3}" -f ($TotalBytes / 1GB))
