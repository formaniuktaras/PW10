param(
    [string]$PythonPath = "python"
)

Write-Host "Building InventoryLite..."

# Check python
try {
    & $PythonPath --version | Out-Null
} catch {
    Write-Error "Python not found. Install Python 3.12."; exit 1
}

$venvPath = ".\.venv"
if (-Not (Test-Path $venvPath)) {
    & $PythonPath -m venv $venvPath
}

. "$venvPath/Scripts/Activate.ps1"

python -m pip install --upgrade pip
python -m pip install -r requirements.txt

$iconBase64 = Get-Content -Raw "icons/app_ico_base64.txt"
[IO.File]::WriteAllBytes("icons/app.ico", [Convert]::FromBase64String($iconBase64))

$iconPath = "icons/app.ico"
$fontArgs = ""
if (Test-Path "./assets/fonts/DejaVuSans.ttf") {
    $fontArgs = "--add-data \"assets/fonts/DejaVuSans.ttf;assets/fonts\""
    if (Test-Path "./assets/fonts/DejaVuSans-Bold.ttf") {
        $fontArgs = "$fontArgs --add-data \"assets/fonts/DejaVuSans-Bold.ttf;assets/fonts\""
    }
}

$cmd = "pyinstaller --onefile --noconsole --name InventoryLite --icon $iconPath $fontArgs app.py --collect-submodules inventorylite"
Write-Host "Running: $cmd"
Invoke-Expression $cmd

if (Test-Path "dist/InventoryLite.exe") {
    Write-Host "Build complete: $(Resolve-Path dist/InventoryLite.exe)"
} else {
    Write-Error "Build failed"
    exit 1
}
