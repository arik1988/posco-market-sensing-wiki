[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$ProjectTools = Split-Path -Parent $MyInvocation.MyCommand.Path
$WikiRoot = (Resolve-Path (Join-Path $ProjectTools "..\..")).Path
$MkDocsConfig = Join-Path $ProjectTools "mkdocs.yml"
$WikiAddress = "0.0.0.0:8000"
$LocalUrl = "http://127.0.0.1:8000/"

function Get-PythonExecutable {
    $candidates = @()
    if ($env:WIKI_PYTHON) {
        $candidates += $env:WIKI_PYTHON
    }
    $candidates += @(
        (Join-Path $env:LOCALAPPDATA "Programs\Python\Python314\python.exe"),
        (Join-Path $env:LOCALAPPDATA "Programs\Python\Python313\python.exe"),
        (Join-Path $env:USERPROFILE ".openharness-venv\Scripts\python.exe")
    )
    foreach ($root in @(
        (Join-Path $env:LOCALAPPDATA "Programs\Python"),
        $env:ProgramFiles
    )) {
        if (Test-Path -LiteralPath $root) {
            $candidates += @(
                Get-ChildItem -LiteralPath $root -Directory -Filter "Python*" -ErrorAction SilentlyContinue |
                    Sort-Object Name -Descending |
                    ForEach-Object { Join-Path $_.FullName "python.exe" }
            )
        }
    }
    $command = Get-Command python -All -ErrorAction SilentlyContinue
    if ($command) {
        $candidates += @($command | ForEach-Object { $_.Source })
    }

    foreach ($candidate in ($candidates | Where-Object { $_ } | Select-Object -Unique)) {
        if (-not (Test-Path -LiteralPath $candidate)) {
            continue
        }
        & $candidate -c "import sys" 2>$null
        if ($LASTEXITCODE -eq 0) {
            return $candidate
        }
    }
    throw "A working Python 3 interpreter was not found."
}

function Test-WikiHardResetInput {
    param(
        [char]$Character = [char]0,
        [int]$VirtualKeyCode = 0
    )

    return (
        $VirtualKeyCode -eq [int][ConsoleKey]::R -or
        $Character -ceq "r" -or
        $Character -ceq "R" -or
        [int]$Character -eq 0x3131
    )
}

function Stop-WikiProcessTree {
    param([int]$ServerProcessId)

    if ($ServerProcessId -le 0) {
        return
    }
    & taskkill.exe /PID $ServerProcessId /T /F *> $null
}

function Stop-ExistingWikiServers {
    $servers = @(
        Get-CimInstance Win32_Process |
            Where-Object {
                $_.Name -eq "python.exe" -and
                $_.CommandLine -match "mkdocs\s+serve" -and
                $_.CommandLine -match "0\.0\.0\.0:8000"
            }
    )
    foreach ($server in $servers) {
        Stop-WikiProcessTree -ServerProcessId $server.ProcessId
    }
}

function Start-WikiServer {
    $python = Get-PythonExecutable
    $startInfo = [System.Diagnostics.ProcessStartInfo]::new()
    $startInfo.FileName = $python
    $startInfo.Arguments = (
        "-m mkdocs serve -f `"$MkDocsConfig`" " +
        "--quiet --dev-addr $WikiAddress"
    )
    $startInfo.WorkingDirectory = $WikiRoot
    $startInfo.UseShellExecute = $false
    $startInfo.RedirectStandardInput = $true

    return [System.Diagnostics.Process]::Start($startInfo)
}

function Get-WikiLanIPv4Address {
    try {
        return [System.Net.Dns]::GetHostAddresses(
            [System.Net.Dns]::GetHostName()
        ) |
            Where-Object {
                $_.AddressFamily -eq
                    [System.Net.Sockets.AddressFamily]::InterNetwork -and
                -not [System.Net.IPAddress]::IsLoopback($_) -and
                -not $_.ToString().StartsWith("169.254.")
            } |
            Select-Object -First 1
    }
    catch {
        return $null
    }
}

function Get-WikiBrowserUrl {
    param($LanAddress)

    if ($null -ne $LanAddress) {
        return "http://${LanAddress}:8000/"
    }
    return $LocalUrl
}

function Start-WikiLauncher {
    Set-Location $WikiRoot
    Stop-ExistingWikiServers

    $lanAddress = Get-WikiLanIPv4Address
    $browserUrl = Get-WikiBrowserUrl -LanAddress $lanAddress
    Write-Host "Starting the Steel Technology Intelligence wiki..."
    Write-Host "Local URL: $LocalUrl"
    if ($null -ne $lanAddress) {
        Write-Host "Intranet URL: http://${lanAddress}:8000/"
    }
    Write-Host "Other users on the same network can open the intranet URL."
    Write-Host "If Windows Firewall asks, allow Python on private networks."
    Write-Host "Press R to hard reset. Press Ctrl+C to stop the wiki."
    Write-Host ""

    $server = $null
    $openBrowser = $true
    try {
        while ($true) {
            $server = Start-WikiServer
            if ($openBrowser) {
                Start-Process $browserUrl
                $openBrowser = $false
            }

            $resetRequested = $false
            while (-not $server.HasExited) {
                try {
                    if ([Console]::KeyAvailable) {
                        $keyInfo = [Console]::ReadKey($true)
                        if (
                            Test-WikiHardResetInput `
                                -Character $keyInfo.KeyChar `
                                -VirtualKeyCode ([int]$keyInfo.Key)
                        ) {
                            $resetRequested = $true
                            break
                        }
                    }
                }
                catch {
                    # A redirected console cannot provide interactive input.
                }
                Start-Sleep -Milliseconds 100
            }

            if (-not $resetRequested) {
                if ($server.HasExited) {
                    exit $server.ExitCode
                }
                break
            }

            Write-Host "Hard reset requested. Restarting the wiki..."
            Stop-WikiProcessTree -ServerProcessId $server.Id
            Stop-ExistingWikiServers
            $server = $null
        }
    }
    finally {
        if ($null -ne $server -and -not $server.HasExited) {
            Stop-WikiProcessTree -ServerProcessId $server.Id
        }
    }
}

if ($MyInvocation.InvocationName -ne ".") {
    Start-WikiLauncher
}
