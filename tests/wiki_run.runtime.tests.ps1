$ErrorActionPreference = "Stop"

. (Join-Path (
    Split-Path -Parent $PSScriptRoot
) "tools\project\wiki_run.ps1")
$script:WikiAddress = "127.0.0.1:18081"

function Wait-TestWikiReady {
    foreach ($attempt in 1..40) {
        try {
            $response = Invoke-WebRequest `
                -UseBasicParsing `
                -Uri "http://127.0.0.1:18081/" `
                -TimeoutSec 1
            if ($response.StatusCode -eq 200) {
                return
            }
        }
        catch {
        }
        Start-Sleep -Milliseconds 250
    }
    throw "The test Wiki server did not become ready."
}

$firstServer = Start-WikiServer
$secondServer = $null
try {
    Wait-TestWikiReady
    $firstId = $firstServer.Id
    Stop-WikiProcessTree -ServerProcessId $firstId
    $firstServer = $null

    $secondServer = Start-WikiServer
    Wait-TestWikiReady
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
