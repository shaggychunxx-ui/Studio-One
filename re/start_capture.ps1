# Capture UCNET traffic with Windows netsh (no Wireshark required).
# Run elevated for best results:
#   powershell -ExecutionPolicy Bypass -File re\start_capture.ps1
#
# Then connect Fender Studio Pro Remote from a phone/tablet on the same LAN.
# Stop with: netsh trace stop

$ErrorActionPreference = "Stop"
$outDir = Join-Path $PSScriptRoot "captures"
New-Item -ItemType Directory -Force -Path $outDir | Out-Null
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$etl = Join-Path $outDir "ucnet_$stamp.etl"

Write-Host "Starting netsh trace -> $etl"
Write-Host "Filter: UDP/TCP ports 47809 and common session ports"
Write-Host "Connect the official Remote app now, exercise transport/faders, then run:"
Write-Host "  netsh trace stop"

# Capture IPv4 UDP/TCP. Provider Microsoft-Windows-TCPIP is always available.
netsh trace start capture=yes report=disabled maxSize=512 `
  traceFile="$etl" `
  provider=Microsoft-Windows-TCPIP level=5 `
  Ethernet.Type=IPv4

Write-Host "Trace running. ETL will be at: $etl"
