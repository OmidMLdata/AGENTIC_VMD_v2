# vmd-agent for Windows: one command. Needs Docker Desktop (WSL2 backend). Same as start.sh.
#   .\start.ps1             start everything and open the chat
#   .\start.ps1 down        stop it
# STATUS: NEVER RUN (no Windows or Docker where this was written).
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
if (-not $env:MODEL)    { $env:MODEL = "granite4.1:8b" }
if (-not $env:DATA_DIR) { $env:DATA_DIR = (Join-Path $PSScriptRoot "data") }
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
  Write-Error "Docker is not installed. Install Docker Desktop: https://docs.docker.com/get-docker/"; exit 1 }
docker info *> $null
if ($LASTEXITCODE -ne 0) { Write-Error "Docker is installed but not running. Start Docker Desktop and run this again."; exit 1 }
$files = @("-f", "docker/chat.compose.yml")
if ($args.Count -gt 0 -and $args[0] -eq "down") { docker compose @files down; exit 0 }
New-Item -ItemType Directory -Force -Path $env:DATA_DIR | Out-Null
if (Get-ChildItem docker/vmd-dist -Filter "vmd*.tar.gz" -ErrorAction SilentlyContinue) {
  $env:VMD_TARGET = "with-vmd"; Write-Host "VMD tarball found: building the image with VMD (must not be shared)."
} else {
  $env:VMD_TARGET = "runtime"; Write-Host "No VMD tarball in docker/vmd-dist/: using the built-in renderer."
}
if ((Get-Command nvidia-smi -ErrorAction SilentlyContinue) -and ((docker info 2>$null) -match "nvidia")) {
  $files += @("-f", "docker/chat.gpu.yml"); Write-Host "NVIDIA GPU found: the model will use it."
} else { Write-Host "No GPU available to Docker: the model runs on the CPU (slower)." }
docker compose @files up -d ollama
$have = docker compose @files exec -T ollama ollama list 2>$null | Select-String -Pattern ("^" + [regex]::Escape($env:MODEL))
if (-not $have) { Write-Host "Downloading model $($env:MODEL) (several GB, first time only)..."; docker compose @files exec -T ollama ollama pull $env:MODEL }
docker compose @files build vmd-agent
Write-Host "`nReady. Your files go in: $($env:DATA_DIR)"
docker compose @files run --rm vmd-agent chat @args
