$uri = "http://127.0.0.1:8088/health"
$maxTries = 12
$delaySec = 5
for ($i = 1; $i -le $maxTries; $i++) {
  try {
    $h = Invoke-RestMethod -Uri $uri -TimeoutSec 5 -ErrorAction Stop
    Write-Host "TRY $i : $($h | ConvertTo-Json -Compress)"
    if ($h.status -eq 'ready') {
      Write-Host "READY"
      exit 0
    }
  } catch {
    Write-Host "TRY $i : not ready ($($_.Exception.Message))"
  }
  Start-Sleep -Seconds $delaySec
}
Write-Host "TIMEOUT"
exit 1
