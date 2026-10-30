param(
    [switch]$SkipInstall
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = Join-Path $root ".venv\Scripts\python.exe"
$distDir = Join-Path $root "dist\PicSteps"

if (-not (Test-Path -LiteralPath $python)) {
    throw "No se encontró el entorno virtual: $python"
}

if (-not $SkipInstall) {
    & $python -m pip install --disable-pip-version-check -r (Join-Path $root "requirements-build.txt")
    if ($LASTEXITCODE -ne 0) {
        throw "No se pudieron instalar las dependencias de compilación."
    }
}

$version = (& $python -c "import picsteps; print(picsteps.__version__)").Trim()
if (-not $version) {
    throw "No se pudo leer la versión de PicSteps."
}

& $python -m PyInstaller `
    --noconfirm `
    --clean `
    --windowed `
    --name PicSteps `
    --icon (Join-Path $root "assets\picsteps.ico") `
    --version-file (Join-Path $root "packaging\version_info.txt") `
    --distpath (Join-Path $root "dist") `
    --workpath (Join-Path $root "build\pyinstaller") `
    (Join-Path $root "main.py")
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller falló con código $LASTEXITCODE."
}

$exe = Join-Path $distDir "PicSteps.exe"
if (-not (Test-Path -LiteralPath $exe)) {
    throw "No se generó el ejecutable esperado: $exe"
}

$readme = Join-Path $root "packaging\LEEME.txt"
if (Test-Path -LiteralPath $readme) {
    Copy-Item -LiteralPath $readme -Destination (Join-Path $distDir "LEEME.txt") -Force
}

$zipPath = Join-Path $root "dist\PicSteps-$version-portable.zip"
if (Test-Path -LiteralPath $zipPath) {
    Remove-Item -LiteralPath $zipPath -Force
}
Add-Type -AssemblyName System.IO.Compression.FileSystem
[System.IO.Compression.ZipFile]::CreateFromDirectory(
    $distDir,
    $zipPath,
    [System.IO.Compression.CompressionLevel]::Optimal,
    $false
)

$sizeMb = [math]::Round((Get-Item -LiteralPath $zipPath).Length / 1MB, 1)
Write-Host ""
Write-Host "Portátil generado:" -ForegroundColor Green
Write-Host "  Carpeta: $distDir"
Write-Host "  ZIP:     $zipPath ($sizeMb MB)"
