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

$intranetUrl = Get-WikiBrowserUrl `
    -LanAddress ([System.Net.IPAddress]::Parse("10.20.30.40"))
if ($intranetUrl -ne "http://10.20.30.40:8000/") {
    throw "The browser must use the detected intranet URL by default."
}

$fallbackUrl = Get-WikiBrowserUrl -LanAddress $null
if ($fallbackUrl -ne $LocalUrl) {
    throw "The browser must fall back to the local URL without a LAN address."
}

Write-Host "wiki_run.ps1 tests passed."
