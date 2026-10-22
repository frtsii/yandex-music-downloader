[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$appRoot = Join-Path $projectRoot 'app'
$distRoot = Join-Path $projectRoot 'dist'
$stageRoot = Join-Path $distRoot 'YandexMusicDownloader'
$workerDist = Join-Path $projectRoot 'build\worker-dist'

Push-Location $projectRoot
try {
    python -m unittest discover -s tests -v
    if ($LASTEXITCODE -ne 0) { throw 'Backend tests failed.' }

    python -m PyInstaller --noconfirm --clean --onefile `
        --name YandexMusicWorker `
        --distpath $workerDist `
        --workpath (Join-Path $projectRoot 'build\worker') `
        --specpath (Join-Path $projectRoot 'build') `
        worker_main.py
    if ($LASTEXITCODE -ne 0) { throw 'Worker build failed.' }

    Push-Location $appRoot
    try {
        flutter pub get
        flutter analyze
        if ($LASTEXITCODE -ne 0) { throw 'Flutter analysis failed.' }
        flutter build windows --release
        if ($LASTEXITCODE -ne 0) { throw 'Flutter build failed.' }
    } finally {
        Pop-Location
    }

    if (Test-Path $stageRoot) {
        Remove-Item -LiteralPath $stageRoot -Recurse -Force
    }
    New-Item -ItemType Directory -Path $stageRoot -Force | Out-Null

    $flutterRelease = Join-Path $appRoot 'build\windows\x64\runner\Release'
    Copy-Item (Join-Path $flutterRelease '*') $stageRoot -Recurse -Force
    Copy-Item (Join-Path $workerDist 'YandexMusicWorker.exe') $stageRoot -Force

    $redistRoot = 'C:\Program Files (x86)\Microsoft Visual Studio\2022'
    $crtFiles = Get-ChildItem $redistRoot -Recurse -ErrorAction SilentlyContinue `
        -Include msvcp140.dll,vcruntime140.dll,vcruntime140_1.dll |
        Where-Object { $_.FullName -match '\\x64\\Microsoft\.VC14\d*\.CRT\\' } |
        Group-Object Name |
        ForEach-Object { $_.Group | Sort-Object FullName -Descending | Select-Object -First 1 }
    if ($crtFiles.Count -ne 3) {
        throw 'Visual C++ x64 runtime DLLs were not found.'
    }
    $crtFiles | Copy-Item -Destination $stageRoot -Force

    $zipPath = Join-Path $distRoot 'YandexMusicDownloader-portable.zip'
    if (Test-Path $zipPath) { Remove-Item -LiteralPath $zipPath -Force }
    Compress-Archive -Path (Join-Path $stageRoot '*') -DestinationPath $zipPath
    Write-Host "Portable release: $zipPath"
} finally {
    Pop-Location
}
