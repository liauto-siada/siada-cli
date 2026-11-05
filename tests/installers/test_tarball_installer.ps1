# Offline regression checks for the Windows installer and generated variants.
param(
    [string]$InstallerPath = (Join-Path $PSScriptRoot "..\..\siada_internal\scripts\install_from_tarball.ps1")
)

$ErrorActionPreference = "Stop"
$InstallerPath = (Resolve-Path $InstallerPath).Path
$source = [IO.File]::ReadAllText($InstallerPath)
$tokens = $null
$parseErrors = $null
$ast = [Management.Automation.Language.Parser]::ParseInput($source, [ref]$tokens, [ref]$parseErrors)
if ($parseErrors.Count) { throw "Installer syntax errors: $parseErrors" }

# Mock only the remote metadata boundary; run the actual installer control flow,
# local version checks, launcher creation, error handler and transcript cleanup.
$download = $ast.Find({
    param($node)
    $node -is [Management.Automation.Language.FunctionDefinitionAst] -and
        $node.Name -eq "Invoke-DownloadText"
}, $true)
if (-not $download) { throw "Installer metadata download function not found" }
$mock = @'
function Invoke-DownloadText {
    param([string]$Url)
    if ($env:SIADA_INSTALLER_TEST_FAIL) { return $null }
    if ($Url -like "*/latest_version-*") { return "0.0.0" }
    if ($Url -like "*/base_version-*") { return "test-base" }
    if ($Url -like "*/app_version-*") { return "test-app" }
    throw "Unexpected metadata request: $Url"
}
'@
$source = $source.Substring(0, $download.Extent.StartOffset) + $mock +
    $source.Substring($download.Extent.EndOffset)
$fixture = Join-Path ([IO.Path]::GetTempPath()) ("siada-installer-test-" + [guid]::NewGuid().ToString("N"))
$null = New-Item -ItemType Directory -Path $fixture
$utf8 = New-Object Text.UTF8Encoding($true)
$shell = Join-Path $env:SystemRoot "System32\WindowsPowerShell\v1.0\powershell.exe"

function Invoke-Probe {
    param([string]$Command, [bool]$Fail, [string]$ScriptFile = "")
    $info = New-Object Diagnostics.ProcessStartInfo
    $info.FileName = $shell
    if ($ScriptFile) {
        $info.Arguments = '-NoProfile -NonInteractive -ExecutionPolicy Bypass -File "' + $ScriptFile + '"'
    } else {
        $encoded = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($Command))
        $info.Arguments = "-NoProfile -NonInteractive -OutputFormat Text -ExecutionPolicy Bypass -EncodedCommand $encoded"
    }
    $info.UseShellExecute = $false
    $info.CreateNoWindow = $true
    $info.RedirectStandardOutput = $true
    $info.RedirectStandardError = $true
    # All filesystem writes and configuration changes belong to the fixture.
    foreach ($key in @($info.EnvironmentVariables.Keys)) {
        if ($key -like "SIADA_*") { $info.EnvironmentVariables.Remove($key) }
    }
    $info.EnvironmentVariables["USERPROFILE"] = $fixture
    $info.EnvironmentVariables["SIADA_INSTALL_DIR"] = $venv
    $info.EnvironmentVariables["SIADA_BIN_DIR"] = $bin
    $info.EnvironmentVariables["SIADA_NO_MODIFY_PATH"] = "1"
    $info.EnvironmentVariables["SIADA_INSTALLER_TEST_FAIL"] = if ($Fail) { "1" } else { "" }
    $process = New-Object Diagnostics.Process
    $process.StartInfo = $info
    try {
        $null = $process.Start()
        $stdout = $process.StandardOutput.ReadToEndAsync()
        $stderr = $process.StandardError.ReadToEndAsync()
        if (-not $process.WaitForExit(20000)) {
            $process.Kill()
            $process.WaitForExit()
            throw "Installer probe timed out (possibly waiting for a key)"
        }
        return [pscustomobject]@{
            ExitCode = $process.ExitCode
            Output = $stdout.GetAwaiter().GetResult() + $stderr.GetAwaiter().GetResult()
        }
    } finally {
        $process.Dispose()
    }
}

try {
    $venv = Join-Path $fixture "venv"
    $bin = Join-Path $fixture "bin"
    $null = New-Item -ItemType Directory -Path $venv
    [IO.File]::WriteAllText((Join-Path $venv ".siada_base_version"), "test-base", $utf8)
    [IO.File]::WriteAllText((Join-Path $venv ".siada_app_version"), "test-app", $utf8)
    $checks = 0
    foreach ($environment in @("prod", "beta", "test")) {
        $scriptFile = Join-Path $fixture ($environment + "_install_from_tarball.ps1")
        # Accept either the source template or an already generated beta/test file.
        $variant = $source -replace '(?m)(^\$SIADA_ENV\s*=.*else \{ ")[^"]+(" \})',
            ('${1}' + $environment + '${2}')
        [IO.File]::WriteAllText($scriptFile, $variant, $utf8)
        $quotedPath = "'" + $scriptFile.Replace("'", "''") + "'"
        $invoke = 'Invoke-Expression ([IO.File]::ReadAllText(' + $quotedPath + '))'

        $success = Invoke-Probe ('$ErrorActionPreference = "Continue"; ' + $invoke +
            '; if ($ErrorActionPreference -ne "Continue") { throw "Caller preference changed" }; Write-Output CALLER_ALIVE') $false
        if ($success.ExitCode -ne 0 -or $success.Output -notmatch "CALLER_ALIVE" -or
            $success.Output -notmatch "already up to date" -or
            $success.Output -notmatch ("Env:\s+" + $environment)) {
            throw "$environment iex success failed: $($success.Output)"
        }
        if (-not (Test-Path (Join-Path $bin "siada-cli.cmd")) -or
            -not (Test-Path (Join-Path $bin "siada-browser.cmd"))) {
            throw "$environment command launchers missing"
        }
        $checks++

        $successFile = Invoke-Probe "" $false $scriptFile
        if ($successFile.ExitCode -ne 0 -or $successFile.Output -notmatch "already up to date") {
            throw "$environment -File success failed: $($successFile.Output)"
        }
        $checks++

        $failure = Invoke-Probe ('$ErrorActionPreference = "Continue"; try { ' + $invoke +
            '; throw "Failure was swallowed" } catch { if ($_ -notmatch "Failed to fetch latest version") { throw }; Write-Output ERROR_CAUGHT }; ' +
            'if ($ErrorActionPreference -ne "Continue") { throw "Caller preference changed" }; Write-Output CALLER_ALIVE') $true
        if ($failure.ExitCode -ne 0 -or $failure.Output -notmatch "ERROR_CAUGHT" -or
            $failure.Output -notmatch "CALLER_ALIVE" -or $failure.Output -notmatch "Installation FAILED") {
            throw "$environment iex failure failed: $($failure.Output)"
        }
        $checks++

        $failureFile = Invoke-Probe "" $true $scriptFile
        if ($failureFile.ExitCode -ne 1 -or $failureFile.Output -notmatch "Installation FAILED") {
            throw "$environment -File failure failed: $($failureFile.Output)"
        }
        $checks++
    }
    Write-Host "Windows installer regression checks: $checks passed"
} finally {
    Remove-Item -LiteralPath $fixture -Recurse -Force -ErrorAction SilentlyContinue
}