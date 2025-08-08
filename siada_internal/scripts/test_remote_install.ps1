#requires -version 5.1
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# Ensure ~/.local/bin exists and add to PATH for this session
$LocalBin = Join-Path $HOME '.local/bin'
if (!(Test-Path $LocalBin)) { New-Item -ItemType Directory -Path $LocalBin | Out-Null }
test:PATH = "$LocalBin;test:PATH"

# Install uv if missing (minimal approach)
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
  Write-Host 'Installing uv...'
  powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
}

# Ensure Python 3.12 is available to uv
uv python install 3.12 | Out-Null

# Create or reuse a dedicated venv
$VenvDir = Join-Path $HOME '.local/share/siada_cli_venv_3.12'
uv venv --python 3.12 "$VenvDir" | Out-Null
$VenvBin = Join-Path $VenvDir 'Scripts'


# Optional: custom index mirror
$IndexArgs = @()
if (test:SIADA_PYPI_INDEX) {
  $IndexArgs += '-i'
  $IndexArgs += test:SIADA_PYPI_INDEX
} else {
  $IndexArgs += '-i'
  $IndexArgs += 'https://pypi.tuna.tsinghua.edu.cn/simple'
}

# Reinstall the wheel into the venv
# Install using venv python/pip without extra checks
# Upgrade pip via uv targeting the venv interpreter
uv pip install --python (Join-Path $VenvBin 'python.exe') --upgrade pip | Out-Null
# Install wheel via uv targeting the venv interpreter
uv pip install --python (Join-Path $VenvBin 'python.exe') --no-cache-dir --force-reinstall "https://bj.bcebos.com/prod-cnhb01-siada/cli-install/test/siada_cli-0.0.1-py3-none-any.whl" @IndexArgs

# Enforce executable name
$BinName = 'siada-cli'

# Place shim into ~/.local/bin (copy .exe)
$ExePath = Join-Path $VenvBin ($BinName + '.exe')
$LinkExe = Join-Path $LocalBin ($BinName + '.exe')
if (Test-Path $ExePath) {
  Copy-Item -Force $ExePath $LinkExe
} else {
  Write-Warning "$ExePath not found; ensure the package provides a console script."
}


Write-Host '**************************************'
Write-Host "siada-cli installed in venv: $VenvDir"
Write-Host "Shim copied to: $LinkExe"
Write-Host 'Next Steps'
Write-Host '1. Add ~/.local/bin to your PATH:'
Write-Host '   For PowerShell (current user):'
Write-Host '   [Environment]::SetEnvironmentVariable("Path", "test:USERPROFILE\.local\bin;" + test:Path, "User")'
Write-Host '   Restart PowerShell to apply.'


