# vmd-agent installer for Windows. Paste ONE line into PowerShell (search "PowerShell" in the Start menu):
#
#   powershell -ExecutionPolicy Bypass -c "irm https://raw.githubusercontent.com/OmidMLdata/AGENTIC_VMD_v2/main/install.ps1 | iex"
#
# Everything goes into ONE folder (default %USERPROFILE%\vmd-agent; set VMD_AGENT_HOME to choose another):
# uv, Python, vmd-agent and its packages, settings, and (if you choose it) a private copy of the Ollama
# model server with its models. No administrator rights, nothing system-wide, no PATH edits.
# To remove everything: delete that folder.
#
# STATUS: NEVER RUN. No Windows machine, uv or GitHub access was available where this was written.
$ErrorActionPreference = "Stop"
$Source = if ($env:VMD_AGENT_SOURCE) { $env:VMD_AGENT_SOURCE } else { "https://github.com/OmidMLdata/AGENTIC_VMD_v2/archive/refs/heads/main.zip" }
$Python = if ($env:VMD_AGENT_PYTHON) { $env:VMD_AGENT_PYTHON } else { "3.12" }
$Home_ = if ($env:VMD_AGENT_HOME) { $env:VMD_AGENT_HOME } else { Join-Path $env:USERPROFILE "vmd-agent" }

function Say($m) { Write-Host ""; Write-Host "==> $m" }
function Die($m) { Write-Host ""; Write-Host "vmd-agent installer: $m" -ForegroundColor Red; exit 1 }

New-Item -ItemType Directory -Force -Path (Join-Path $Home_ "bin"), (Join-Path $Home_ "internal-bin"), (Join-Path $Home_ "uv") | Out-Null
$env:VMD_AGENT_HOME = $Home_
# Point every uv setting inside the one folder, so uv never writes anywhere else.
$env:UV_INSTALL_DIR = Join-Path $Home_ "uv"
$env:UV_UNMANAGED_INSTALL = Join-Path $Home_ "uv"
$env:UV_NO_MODIFY_PATH = "1"
$env:UV_CACHE_DIR = Join-Path $Home_ "cache"
$env:UV_TOOL_DIR = Join-Path $Home_ "tools"
$env:UV_TOOL_BIN_DIR = Join-Path $Home_ "internal-bin"
$env:UV_PYTHON_INSTALL_DIR = Join-Path $Home_ "python"
$env:UV_PYTHON_BIN_DIR = Join-Path $Home_ "internal-bin"
$uv = Join-Path $Home_ "uv\uv.exe"

if (-not (Test-Path $uv)) {
  Say "Step 1 of 3: fetching uv into $Home_\uv (a small tool that manages Python for you)"
  try { Invoke-RestMethod https://astral.sh/uv/install.ps1 | Invoke-Expression }
  catch { Die "could not fetch uv. See https://docs.astral.sh/uv/getting-started/installation/ and run this again." }
}
if (-not (Test-Path $uv)) { Die "uv was fetched but is not at $uv. Please report this." }

Say "Step 2 of 3: installing vmd-agent into $Home_ (downloads Python and packages; it can take a few minutes)"
& $uv tool install --python $Python --force "vmd-agent[server] @ $Source"
if ($LASTEXITCODE -ne 0) { Die "installing vmd-agent failed (see the message above). Check your internet connection and try again." }

# A launcher that always sets the folder, so settings and downloads stay inside it.
$run = Join-Path $Home_ "bin\vmd-agent.cmd"
Set-Content -Path $run -Encoding ASCII -Value "@echo off`r`nset VMD_AGENT_HOME=$Home_`r`n`"$Home_\internal-bin\vmd-agent.exe`" %*"

Say "Step 3 of 3: setup"
& $run setup

Write-Host ""
Write-Host "Done. Next time run:  $run"
Write-Host "To remove everything, delete the folder:  $Home_"
