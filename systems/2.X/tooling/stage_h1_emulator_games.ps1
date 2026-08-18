param(
    [string]$RepoRoot = (Split-Path -Parent $PSScriptRoot)
)

$ErrorActionPreference = 'Stop'

$application = "$([char]0x5e94)$([char]0x7528)"
$program = "$([char]0x7a0b)$([char]0x5e8f)"
$data = "$([char]0x6570)$([char]0x636e)"
$systemData = Join-Path $RepoRoot 'work\tmp\h1-final-games-system-data'
$programDir = Join-Path (Join-Path $systemData $application) $program
$dataDir = Join-Path (Join-Path $systemData $application) $data
$buildDir = Join-Path $RepoRoot 'h1-bda-sdk\build'
$releaseRoot = Join-Path $RepoRoot 'deliverables\H1-all-games-real-hardware-2026-08-01\A-root'
$releaseData = Join-Path (Join-Path $releaseRoot $application) $data
$assetDir = Join-Path $RepoRoot 'emulator\windows-x86_64\assets\a320'

$apps = @(
    '7DAYS.APP',
    'ALIBABA.APP',
    'BRICK.APP',
    'BUBBLE.APP',
    'BWFIGHTER.APP',
    'CANDY.APP',
    'DOUDIZHU.APP',
    'DRIFT.APP',
    'LINKLINK.APP',
    'LUBILUBI.APP',
    'PAL.APP',
    'SNAKE.APP',
    'TD1.APP',
    'TD2.APP',
    'TETRIS.APP',
    'XINGTIAN.APP',
    'ZHAOYUN.APP'
)

$bdas = @(
    'H17Days',
    'H1Alibaba',
    'H1Brick',
    'H1Bubble',
    'H1BWFighter',
    'H1Candy',
    'H1Doudizhu',
    'H1Drift',
    'H1KOVPlus',
    'H1LinkLink',
    'H1LubiLubi',
    'H1PAL',
    'H1Snake',
    'H1TD1',
    'H1TD2',
    'H1Tetris',
    'H1Xingtian',
    'H1Zhaoyun'
)

foreach ($required in @($systemData, $programDir, $dataDir, $buildDir, $releaseData)) {
    if (-not (Test-Path -LiteralPath $required -PathType Container)) {
        throw "Required directory is missing: $required"
    }
}

New-Item -ItemType Directory -Force -Path $assetDir | Out-Null

foreach ($app in $apps) {
    $source = Join-Path $releaseData $app
    if (-not (Test-Path -LiteralPath $source -PathType Leaf)) {
        throw "Required game resource is missing: $source"
    }
    Copy-Item -LiteralPath $source -Destination (Join-Path $assetDir $app) -Force

    $nandCopy = Join-Path $dataDir $app
    if (Test-Path -LiteralPath $nandCopy -PathType Leaf) {
        Remove-Item -LiteralPath $nandCopy -Force
    }
}

$kovSource = Join-Path $releaseData 'KOVH1\KOVH1.PAK'
if (-not (Test-Path -LiteralPath $kovSource -PathType Leaf)) {
    throw "Required KOV resource is missing: $kovSource"
}
Copy-Item -LiteralPath $kovSource -Destination (Join-Path $assetDir 'KOVH1.PAK') -Force
$kovNandCopy = Join-Path $dataDir 'KOVH1\KOVH1.PAK'
if (Test-Path -LiteralPath $kovNandCopy -PathType Leaf) {
    Remove-Item -LiteralPath $kovNandCopy -Force
}

foreach ($name in $bdas) {
    $source = Join-Path $buildDir "$name-emulator.bda"
    if (-not (Test-Path -LiteralPath $source -PathType Leaf)) {
        throw "Required emulator BDA is missing: $source"
    }
    Copy-Item -LiteralPath $source -Destination (Join-Path $programDir "$name.bda") -Force
}

Write-Host "Staged $($bdas.Count) emulator BDAs and $($apps.Count + 1) host resources."
