# reset-needed-hids.ps1 — reset alleen relevante HID's (geen kb/muis)

# Zelf elevatie naar Administrator (nodig voor Disable/Enable)
$IsAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()
).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $IsAdmin) {
  Start-Process powershell -Verb RunAs -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`""
  exit
}

$ErrorActionPreference = 'SilentlyContinue'
Import-Module PnpDevice -ErrorAction SilentlyContinue

# Even wachten tot USB/HID klaar is
Start-Sleep -Seconds 8

# Alleen deze HID-namen resetten:
$include = @(
  'HID-compatibel touchscreen',
  'HID-compatibel, door leverancier gedefinieerd apparaat',
  'USB-invoerapparaat'
)

# Deze NIET resetten:
$exclude = @(
  'HID-toetsenbordapparaat',  # NL keyboard
  'HID Keyboard',             # EN keyboard
  'HID-compatibele muis',     # NL mouse
  'HID-compliant mouse'       # EN mouse
)

# Kandidaten selecteren
$targets = Get-PnpDevice -Class HIDClass | Where-Object {
  $_.FriendlyName -and
  ($include | ForEach-Object { $_ -eq $PSItem.FriendlyName -or $PSItem.FriendlyName -match $_ }) -contains $true -and
  -not (($exclude | ForEach-Object { $PSItem.FriendlyName -match $_ }) -contains $true)
}

# Resetten
foreach ($d in $targets) {
  try {
    Disable-PnpDevice -InstanceId $d.InstanceId -Confirm:$false
    Start-Sleep -Milliseconds 700
    Enable-PnpDevice  -InstanceId $d.InstanceId -Confirm:$false
  } catch {}
}