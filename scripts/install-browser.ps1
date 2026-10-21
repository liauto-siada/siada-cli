param([string]$Version = "latest")
$ErrorActionPreference = "Stop"

function Invoke-Checked {
    param([string]$Command, [string[]]$Arguments)
    & $Command @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$Command failed with exit code $LASTEXITCODE" }
}

if ($Version -ne "latest" -and $Version -notmatch '^\d+\.\d+\.\d+((a|b|rc)\d+)?$') {
    throw "Invalid Siada version."
}
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    $LocalBin = Join-Path $env:USERPROFILE ".local\bin"
    $UvPath = Join-Path $LocalBin "uv.exe"
    if (-not (Test-Path $UvPath)) {
        & ([scriptblock]::Create((Invoke-WebRequest -UseBasicParsing "https://astral.sh/uv/install.ps1").Content))
    }
    $env:PATH = "$LocalBin;$env:PATH"
    if (-not (Get-Command uv -ErrorAction SilentlyContinue)) { throw "uv installation failed." }
}
$Package = "siada-cli@latest"
if ($Version -match '(a|b|rc)\d+$') {
    $Release = Invoke-RestMethod "https://test.pypi.org/pypi/siada-cli/$Version/json"
    $Package = ($Release.urls | Where-Object { $_.filename -like "*.whl" } | Select-Object -First 1).url
    if (-not $Package) { throw "Test release wheel was not found." }
} elseif ($Version -ne "latest") {
    $Package = "siada-cli==$Version"
}
Invoke-Checked uv @("tool", "install", "--force", "--python", "python3.12", "--compile", "--with", "pip",
    "--default-index", "https://pypi.org/simple", $Package)
Invoke-Checked uv @("tool", "update-shell")
$ToolBin = & uv tool dir --bin
if ($LASTEXITCODE -ne 0) { throw "Cannot locate uv tool directory." }
$env:PATH = "$ToolBin;$env:PATH"
$Browser = Join-Path $ToolBin "siada-browser.exe"
$SetupArguments = @("setup", "--no-wait", "--host", "127.0.0.1")
if ($Version -ne "latest") {
    $SetupArguments += @("--base-url", "https://github.com/liauto-siada/siada-cli/releases/download/v$Version")
}
Invoke-Checked $Browser $SetupArguments
Invoke-Checked $Browser @("start")
Write-Host "Siada browser service is ready. Return to Chrome to complete login."