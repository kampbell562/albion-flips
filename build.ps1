# Builds dist\AlbionFlips.zip: the one-file exe plus watchlist.txt and README.txt.
# Needs: pip install pyinstaller
$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$out = Join-Path $root 'dist'
$build = Join-Path $root 'build'

$data = @()
foreach ($f in 'items.txt', 'icon.png', 'icon-64.png', 'icon-30.png') {
    $data += @('--add-data', "$(Join-Path $root $f);.")
}
python -m PyInstaller --noconfirm --onefile --windowed --name AlbionFlips `
    --icon (Join-Path $root 'icon.ico') @data `
    --distpath (Join-Path $build 'exe') --workpath (Join-Path $build 'work') --specpath $build `
    (Join-Path $root 'flip-widget.py')
if ($LASTEXITCODE -ne 0) { throw 'PyInstaller failed' }

$pkg = Join-Path $build 'AlbionFlips'
New-Item -ItemType Directory -Force $pkg | Out-Null
Copy-Item (Join-Path $build 'exe\AlbionFlips.exe') $pkg -Force
Copy-Item (Join-Path $root 'watchlist.txt'), (Join-Path $root 'README.txt') $pkg -Force

New-Item -ItemType Directory -Force $out | Out-Null
Compress-Archive -Path $pkg -DestinationPath (Join-Path $out 'AlbionFlips.zip') -Force
Write-Host "Built $(Join-Path $out 'AlbionFlips.zip')"
