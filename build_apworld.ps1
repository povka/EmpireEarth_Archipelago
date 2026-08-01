# Packs world\empire_earth into empire_earth.apworld and installs it into
# Archipelago's custom_worlds folder.
$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$src = Join-Path $root "world\empire_earth"
$out = Join-Path $root "empire_earth.apworld"
$dest = "C:\ProgramData\Archipelago\custom_worlds\empire_earth.apworld"

# Stage a clean copy so __pycache__ never ends up inside the archive.
$stage = Join-Path $env:TEMP ("ee_apworld_" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Force -Path (Join-Path $stage "empire_earth") | Out-Null
Copy-Item -Recurse -Force "$src\*" (Join-Path $stage "empire_earth")
Get-ChildItem -Recurse -Force -Directory (Join-Path $stage "empire_earth") |
    Where-Object { $_.Name -eq "__pycache__" } |
    Remove-Item -Recurse -Force

if (Test-Path $out) { Remove-Item $out -Force }
Compress-Archive -Path (Join-Path $stage "empire_earth") -DestinationPath $out -CompressionLevel Optimal
Remove-Item -Recurse -Force $stage

Copy-Item $out $dest -Force
Write-Host "Built  $out"
Write-Host "Installed to $dest"
