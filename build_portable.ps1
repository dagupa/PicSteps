param(
    [switch]$SkipInstall
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = Join-Path $root ".venv\Scripts\python.exe"
$distRoot = Join-Path $root "dist"
$buildRoot = Join-Path $root "dist_build"
$distDir = Join-Path $buildRoot "PicSteps"

if (-not (Test-Path -LiteralPath $python)) {
    throw "No se encontró el entorno virtual: $python"
}

if (-not $SkipInstall) {
    & $python -m pip install --disable-pip-version-check `
        -r (Join-Path $root "requirements.txt") `
        -r (Join-Path $root "requirements-build.txt")
    if ($LASTEXITCODE -ne 0) {
        throw "No se pudieron instalar las dependencias de compilación."
    }
}

$version = (& $python -c "import picsteps; print(picsteps.__version__)").Trim()
if (-not $version) {
    throw "No se pudo leer la versión de PicSteps."
}

$modelDir = Join-Path $root "packaging\models"
$modelPath = Join-Path $modelDir "silueta.onnx"
$modelLicense = Join-Path $modelDir "LICENSE-silueta.txt"
$modelUrl = "https://github.com/danielgatis/rembg/releases/download/v0.0.0/silueta.onnx"
$modelHash = "75DA6C8D2F8096EC743D071951BE73B4A8BC7B3E51D9A6625D63644F90FFEEDB"

New-Item -ItemType Directory -Force -Path $modelDir | Out-Null
if (-not (Test-Path -LiteralPath $modelPath)) {
    Write-Host "Descargando modelo Silueta (~42 MB)..."
    $temporaryModel = "$modelPath.tmp"
    Invoke-WebRequest -Uri $modelUrl -OutFile $temporaryModel -UseBasicParsing
    Move-Item -LiteralPath $temporaryModel -Destination $modelPath -Force
}
$actualHash = (Get-FileHash -LiteralPath $modelPath -Algorithm SHA256).Hash
if ($actualHash -ne $modelHash) {
    throw "El modelo Silueta no coincide con la huella SHA-256 esperada."
}
if (-not (Test-Path -LiteralPath $modelLicense)) {
    throw "Falta la licencia del modelo: $modelLicense"
}

if (Test-Path -LiteralPath $buildRoot) {
    Remove-Item -LiteralPath $buildRoot -Recurse -Force
}

& $python -m PyInstaller `
    --noconfirm `
    --clean `
    --windowed `
    --name PicSteps `
    --icon (Join-Path $root "assets\picsteps.ico") `
    --version-file (Join-Path $root "packaging\version_info.txt") `
    --distpath $buildRoot `
    --workpath (Join-Path $root "build\pyinstaller") `
    --collect-all onnxruntime `
    --add-data "$modelPath;models" `
    --add-data "$modelLicense;models" `
    --add-data "$root\assets\picsteps.png;assets" `
    --add-data "$root\assets\picsteps.ico;assets" `
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

$zipPath = Join-Path $distRoot "PicSteps-$version-portable.zip"
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

$finalDir = Join-Path $distRoot "PicSteps"
$finalNote = $finalDir
try {
    if (Test-Path -LiteralPath $finalDir) {
        Remove-Item -LiteralPath $finalDir -Recurse -Force
    }
    Copy-Item -LiteralPath $distDir -Destination $finalDir -Recurse -Force
} catch {
    $finalNote = "$distDir (no se pudo actualizar $finalDir porque está bloqueada)"
}

$sizeMb = [math]::Round((Get-Item -LiteralPath $zipPath).Length / 1MB, 1)
Write-Host ""
Write-Host "Portátil generado:" -ForegroundColor Green
Write-Host "  Carpeta: $finalNote"
Write-Host "  ZIP:     $zipPath ($sizeMb MB)"
