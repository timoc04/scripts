# reset-all-hids.ps1 — reset ALLE HID devices (toetsenbord/muis inclusief)
# Run as Administrator

$ErrorActionPreference = 'SilentlyContinue'

# Eventjes wachten tot USB/HID klaar is na boot
Start-Sleep -Seconds 10

# Lijst alle HID devices
$hids = Get-PnpDevice -Class HIDClass | Where-Object { $_.InstanceId -ne $null }

if (-not $hids) { Write-Host "Geen HID devices gevonden."; exit 0 }

Write-Host "Reset $($hids.Count) HID devices..."

foreach ($d in $hids) {
  try {
    Disable-PnpDevice -InstanceId $d.InstanceId -Confirm:$false | Out-Null
    Start-Sleep -Milliseconds 700
    Enable-PnpDevice  -InstanceId $d.InstanceId -Confirm:$false | Out-Null
  } catch {
    # probeer in elk geval te heractiveren
    try { Enable-PnpDevice -InstanceId $d.InstanceId -Confirm:$false | Out-Null } catch {}
  }
}

Write-Host "Klaar."