$ErrorActionPreference = "Stop"

. (Join-Path (
    Split-Path -Parent $PSScriptRoot
) "tools\project\wiki_run.ps1")
$script:WikiAddress = "127.0.0.1:18081"

$firstServer = Start-WikiServer
$secondServer = $null
try {
    Wait-WikiServerReady `
        -Server $firstServer `
        -Url "http://127.0.0.1:18081/" `
        -TimeoutSeconds 15
    $firstId = $firstServer.Id
    Stop-WikiProcessTree -ServerProcessId $firstId
    $firstServer = $null

    $secondServer = Start-WikiServer
    Wait-WikiServerReady `
        -Server $secondServer `
        -Url "http://127.0.0.1:18081/" `
        -TimeoutSeconds 15
    if ($secondServer.Id -eq $firstId) {
        throw "The hard reset did not create a new process."
    }

    Write-Host (
        "Runtime hard-reset smoke test passed: " +
        "$firstId -> $($secondServer.Id)"
    )
}
finally {
    if ($null -ne $firstServer -and -not $firstServer.HasExited) {
        Stop-WikiProcessTree -ServerProcessId $firstServer.Id
    }
    if ($null -ne $secondServer -and -not $secondServer.HasExited) {
        Stop-WikiProcessTree -ServerProcessId $secondServer.Id
    }
}
