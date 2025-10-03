# reset-hids.ps1 — reset alleen relevante HID-apparaten (geen muis/toetsenbord)
# Run as Administrator

$ErrorActionPreference = 'SilentlyContinue'

# Welke HID-namen WEL resetten (NL + brede match)
$include = @(
  'HID-compatibel touchscreen',
  'HID-compatibel, door leverancier gedefinieerd apparaat',
  'USB-invoerapparaat'
)

# Welke HID-namen NIET resetten (input blijft bruikbaar)
$exclude = @(
  'HID-toetsenbordapparaat',   # NL keyboard
  'HID Keyboard',              # EN keyboard
  'HID-compliant mouse',       # EN mouse
  'HID-compatibele muis'       # NL mouse
)

# Kandidaten ophalen binnen HIDClass
$targets = Get-PnpDevice -Class HIDClass |
  Where-Object {
    $_.Status -ne 'Error' -and
    $_.FriendlyName -ne $null -and
    ($include | ForEach-Object { $_ -eq $PSItem.FriendlyName -or $PSItem.FriendlyName -match $_ }) -contains $true -and
    -not (($exclude | ForEach-Object { $PSItem.FriendlyName -match $_ }) -contains $true)
  }

# Reset
foreach ($d in $targets) {
  try {
    Disable-PnpDevice -InstanceId $d.InstanceId -Confirm:$false
    Start-Sleep -Milliseconds 700
    Enable-PnpDevice  -InstanceId $d.InstanceId -Confirm:$false
  } catch {}
}