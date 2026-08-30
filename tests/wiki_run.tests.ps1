$ErrorActionPreference = "Stop"

$launcherPath = Join-Path (
    Split-Path -Parent $PSScriptRoot
) "tools\project\wiki_run.ps1"
$tokens = $null
$errors = $null
[System.Management.Automation.Language.Parser]::ParseFile(
    $launcherPath,
    [ref]$tokens,
    [ref]$errors
) | Out-Null
if ($errors.Count -gt 0) {
    throw "wiki_run.ps1 has parser errors: $($errors.Message -join '; ')"
}

. $launcherPath

$cases = @(
    @{ Name = "lowercase r"; Character = [char]"r"; VirtualKeyCode = 0; Expected = $true },
    @{ Name = "uppercase R"; Character = [char]"R"; VirtualKeyCode = 0; Expected = $true },
    @{ Name = "Korean giyeok"; Character = [char]0x3131; VirtualKeyCode = 0; Expected = $true },
    @{ Name = "IME physical R key"; Character = [char]0; VirtualKeyCode = [int][ConsoleKey]::R; Expected = $true },
    @{ Name = "unrelated key"; Character = [char]"x"; VirtualKeyCode = [int][ConsoleKey]::X; Expected = $false }
)

foreach ($case in $cases) {
    $actual = Test-WikiHardResetInput `
        -Character $case.Character `
        -VirtualKeyCode $case.VirtualKeyCode
    if ($actual -ne $case.Expected) {
        throw "$($case.Name): expected $($case.Expected), got $actual"
    }
}

$source = Get-Content -Raw -Encoding UTF8 $launcherPath
if ($source -notmatch "Press R to hard reset\.") {
    throw "The CLI must display the hard-reset key as R."
}
if ($source -cmatch "Press r to hard reset\.") {
    throw "The CLI must not display the lowercase hard-reset alias."
}
if ($source -notmatch 'RedirectStandardInput = \$true') {
    throw "MkDocs must not consume the launcher control key."
}
if ($source -match 'taskkill\.exe') {
    throw "The launcher must not depend on taskkill.exe."
}
if ($source -notmatch 'Stop-Process -Id \$processId -Force') {
    throw "The launcher must use PowerShell-native process termination."
}
if ($source -notmatch 'Wait-WikiServerReady -Server \$server -Url \$LocalUrl') {
    throw "The launcher must wait for HTTP readiness before opening the browser."
}
if ($source -notmatch '(?s)Wait-WikiServerReady -Server \$server -Url \$LocalUrl.*Start-Process \$LocalUrl') {
    throw "The local browser must open only after the wiki and loopback AI server are ready."
}
if ($source -notmatch 'Wait-ResearchAgentReady -Server \$researchAgent') {
    throw "The launcher must wait for the standalone AI research API."
}
if ($source -notmatch '(?s)function Wait-WikiServerReady.*?\[int\]\$TimeoutSeconds = 300') {
    throw "The wiki readiness timeout must cover large SQLite snapshots."
}
if ($source -notmatch '(?s)function Wait-ResearchAgentReady.*?\[int\]\$TimeoutSeconds = 60') {
    throw "The lightweight research API must keep its focused readiness timeout."
}
if ($source -notmatch 'MkDocs is still building the SQLite snapshot') {
    throw "The launcher must report progress during a long initial build."
}
if ($source -match '--quiet') {
    throw "MkDocs startup output must remain visible for diagnostics."
}

$intranetUrl = Get-WikiBrowserUrl `
    -LanAddress ([System.Net.IPAddress]::Parse("10.20.30.40"))
if ($intranetUrl -ne "http://10.20.30.40:8200/") {
    throw "The browser must use the detected intranet URL by default."
}

$fallbackUrl = Get-WikiBrowserUrl -LanAddress $null
if ($fallbackUrl -ne $LocalUrl) {
    throw "The browser must fall back to the local URL without a LAN address."
}

Write-Host "wiki_run.ps1 tests passed."
