[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$ProjectTools = Split-Path -Parent $MyInvocation.MyCommand.Path
$WikiRoot = (Resolve-Path (Join-Path $ProjectTools "..\..")).Path
$MkDocsConfig = Join-Path $ProjectTools "mkdocs.yml"
$WikiPort = 8200
$ResearchAgentPort = 8201
$WikiAddress = "0.0.0.0:$WikiPort"
$LocalUrl = "http://127.0.0.1:$WikiPort/"

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

    # Some managed Windows environments block external process-kill utilities
    # even when the current user owns the target process. Snapshot the process
    # tree and stop it with PowerShell's native process API instead.
    $processes = @(
        Get-CimInstance Win32_Process -ErrorAction SilentlyContinue
    )
    $pendingProcessIds = [System.Collections.Generic.Stack[int]]::new()
    $pendingProcessIds.Push($ServerProcessId)
    $processIds = [System.Collections.Generic.List[int]]::new()
    $seenProcessIds = @{}

    while ($pendingProcessIds.Count -gt 0) {
        $processId = $pendingProcessIds.Pop()
        if ($seenProcessIds.ContainsKey($processId)) {
            continue
        }
        $seenProcessIds[$processId] = $true
        $processIds.Add($processId)

        foreach ($child in $processes) {
            if ([int]$child.ParentProcessId -eq $processId) {
                $pendingProcessIds.Push([int]$child.ProcessId)
            }
        }
    }

    for ($index = $processIds.Count - 1; $index -ge 0; $index--) {
        $processId = $processIds[$index]
        Stop-Process -Id $processId -Force -ErrorAction SilentlyContinue
    }

    try {
        Wait-Process -Id $ServerProcessId -Timeout 5 -ErrorAction Stop
    }
    catch {
        if (Get-Process -Id $ServerProcessId -ErrorAction SilentlyContinue) {
            throw "Wiki server process $ServerProcessId could not be stopped."
        }
    }
}

function Get-ResearchAgentPythonExecutable {
    $candidate = Join-Path $WikiRoot ".venv-agent\Scripts\python.exe"
    if (-not (Test-Path -LiteralPath $candidate)) {
        throw "The project-local AI research environment is missing. Run wiki_run.bat."
    }
    & $candidate -c "import deepagents, langchain_openai, openai_codex" 2>$null
    if ($LASTEXITCODE -ne 0) {
        throw "The project-local AI research environment is incomplete. Run wiki_run.bat."
    }
    return $candidate
}

function Stop-ExistingWikiServers {
    $servers = @(
        Get-CimInstance Win32_Process |
            Where-Object {
                $_.Name -eq "python.exe" -and
                $_.CommandLine -match "mkdocs\s+serve" -and
                $_.CommandLine -match ([regex]::Escape($WikiAddress))
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

function Start-ResearchAgentServer {
    $python = Get-ResearchAgentPythonExecutable
    $startInfo = [System.Diagnostics.ProcessStartInfo]::new()
    $startInfo.FileName = $python
    $startInfo.Arguments = "-m tools.research_agent.server"
    $startInfo.WorkingDirectory = $WikiRoot
    $startInfo.UseShellExecute = $false
    return [System.Diagnostics.Process]::Start($startInfo)
}

function Wait-ResearchAgentReady {
    param(
        [Parameter(Mandatory = $true)]
        [System.Diagnostics.Process]$Server,
        [int]$TimeoutSeconds = 60
    )

    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    while ([DateTime]::UtcNow -lt $deadline) {
        if ($Server.HasExited) {
            throw "AI research server exited before becoming ready with code $($Server.ExitCode)."
        }
        try {
            $response = Invoke-WebRequest `
                -UseBasicParsing `
                -Uri "http://127.0.0.1:$ResearchAgentPort/health" `
                -TimeoutSec 1
            if ($response.StatusCode -eq 200) {
                return
            }
        }
        catch {
            # Python imports can take a few seconds on the first run.
        }
        Start-Sleep -Milliseconds 100
    }
    throw "AI research server did not become ready within $TimeoutSeconds seconds."
}

function Wait-WikiServerReady {
    param(
        [Parameter(Mandatory = $true)]
        [System.Diagnostics.Process]$Server,
        [string]$Url = $LocalUrl,
        [int]$TimeoutSeconds = 60
    )

    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    while ([DateTime]::UtcNow -lt $deadline) {
        if ($Server.HasExited) {
            throw (
                "Wiki server exited before becoming ready " +
                "with code $($Server.ExitCode)."
            )
        }

        try {
            $response = Invoke-WebRequest `
                -UseBasicParsing `
                -Uri $Url `
                -TimeoutSec 1
            if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 400) {
                return
            }
        }
        catch {
            # The server can refuse connections while MkDocs builds the site.
        }
        Start-Sleep -Milliseconds 100
    }

    throw "Wiki server did not become ready within $TimeoutSeconds seconds."
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
        return "http://${LanAddress}:$WikiPort/"
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
        Write-Host "Intranet URL: http://${lanAddress}:$WikiPort/"
    }
    Write-Host "Other users on the same network can open the intranet URL."
    Write-Host "If Windows Firewall asks, allow Python on private networks."
    Write-Host "Press R to hard reset. Press Ctrl+C to stop the wiki."
    Write-Host ""

    $server = $null
    $researchAgent = $null
    $openBrowser = $true
    try {
        Write-Host "Starting the standalone AI research server..."
        $researchAgent = Start-ResearchAgentServer
        Wait-ResearchAgentReady -Server $researchAgent
        while ($true) {
            $server = Start-WikiServer
            if ($openBrowser) {
                Write-Host "Waiting for the wiki server to become ready..."
                Wait-WikiServerReady -Server $server -Url $LocalUrl
                # The AI research API is intentionally loopback-only. Open the
                # local URL while continuing to advertise the read-only LAN URL.
                Start-Process $LocalUrl
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
        if ($null -ne $researchAgent -and -not $researchAgent.HasExited) {
            Stop-WikiProcessTree -ServerProcessId $researchAgent.Id
        }
    }
}

if ($MyInvocation.InvocationName -ne ".") {
    Start-WikiLauncher
}
