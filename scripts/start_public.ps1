# Starts the app (127.0.0.1 only) and ngrok, prints the shareable URL, stops both on exit.
# ASCII only on purpose: Windows PowerShell 5.1 reads a BOM-less file as ANSI.
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path -Parent $PSScriptRoot)
$port = if ($env:JOB_RAG_PORT) { $env:JOB_RAG_PORT } else { '5000' }
$env:JOB_RAG_PORT = $port
$env:JOB_RAG_LOCAL_OPEN = '1'   # open from this laptop without the access code; tunnel traffic still needs it
$env:JOB_RAG_HOST = '127.0.0.1'   # never the LAN: only ngrok reaches the app
$api = 'http://127.0.0.1:4040/api/tunnels'

# Default: no access code. Set JOB_RAG_REQUIRE_CODE=1 to make a random one (public visitors still hit the hourly answer limit).
if ($env:JOB_RAG_REQUIRE_CODE -eq '1' -and -not $env:JOB_RAG_ACCESS_CODE) {
    $env:JOB_RAG_ACCESS_CODE = (& python -c "import secrets;print(secrets.token_urlsafe(9))").Trim()
}
# Owner PIN (self-use mode): read from the git-ignored file selfdata\owner_pin.txt when the variable is not already set.
if (-not $env:JOB_RAG_OWNER_PIN) {
    $pinFile = Join-Path $PSScriptRoot '..\selfdata\owner_pin.txt'
    if (Test-Path $pinFile) { $env:JOB_RAG_OWNER_PIN = (Get-Content $pinFile -Raw -Encoding UTF8).Trim() }
}
$code = $env:JOB_RAG_ACCESS_CODE
if ($code -and $code.Length -lt 8) { Write-Host 'JOB_RAG_ACCESS_CODE must be at least 8 characters.'; exit 1 }
$ngrok = Get-Command ngrok -ErrorAction SilentlyContinue
if (-not $ngrok) { Write-Host 'ngrok was not found on PATH.'; exit 1 }
try { Invoke-RestMethod $api -TimeoutSec 2 | Out-Null; $busy = $true } catch { $busy = $false }
if ($busy) { Write-Host 'Another ngrok is already running (port 4040 answers). Close it first.'; exit 1 }

$procs = @()
try {
    # Same console window, so closing the window ends the children too; the finally block covers Ctrl+C and errors.
    $app = Start-Process python -ArgumentList '-X', 'utf8', 'app.py' -NoNewWindow -PassThru
    $procs += $app
    Write-Host 'Loading model and index (takes a few minutes)...'
    $local = if ($code) { "http://127.0.0.1:$port/?k=$code" } else { "http://127.0.0.1:$port/" }
    $ready = $false
    for ($i = 0; $i -lt 450 -and -not $ready; $i++) {   # up to about 15 minutes
        if ($app.HasExited) { throw 'The app stopped. See the messages above.' }
        try {
            $r = Invoke-WebRequest $local -UseBasicParsing -TimeoutSec 5
            if ($r.StatusCode -eq 200 -and $r.Content -notmatch 'http-equiv=refresh') {
                if ($r.Content -match 'class=status') { throw 'The app failed to start. See the page text above.' }
                $ready = $true
            }
        } catch [System.Net.WebException] { }
        if (-not $ready) { Start-Sleep -Seconds 2 }
    }
    if (-not $ready) { throw 'Warm-up did not finish in time.' }

    $ng = Start-Process $ngrok.Source -ArgumentList 'http', "127.0.0.1:$port", '--log=stdout' -NoNewWindow -PassThru
    $procs += $ng
    $url = $null
    for ($i = 0; $i -lt 30 -and -not $url; $i++) {
        if ($ng.HasExited) { throw 'ngrok stopped. See the messages above.' }
        try {
            $t = Invoke-RestMethod $api -TimeoutSec 2
            $m = @($t.tunnels | Where-Object { $_.public_url -like 'https://*' -and $_.config.addr -like "*:$port" })
            if ($m.Count -gt 0) { $url = $m[0].public_url }
        } catch { }
        if (-not $url) { Start-Sleep -Seconds 1 }
    }
    if (-not $url) { throw 'ngrok did not report a public URL within 30 seconds.' }

    Write-Host ''
    Write-Host 'Share this address:'
    if ($code) { Write-Host "  $url/?k=$code" } else { Write-Host "  $url/" }
    Write-Host 'First visit on the free ngrok plan shows a warning page: tap Visit Site.'
    Write-Host 'Close this window or press Ctrl+C to stop.'
    while (-not $app.HasExited -and -not $ng.HasExited) { Start-Sleep -Seconds 2 }
    Write-Host 'A process ended; shutting down.'
}
catch { Write-Host "ERROR: $($_.Exception.Message)" }
finally {
    foreach ($p in $procs) {
        if (-not $p.HasExited) { cmd /c "taskkill /T /F /PID $($p.Id) >nul 2>&1" }
    }
}
