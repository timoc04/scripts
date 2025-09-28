# reset-hid-nfc.ps1  —  herinitialiseert HID/USB devices en Smart Card service
# Run as Administrator

$ErrorActionPreference = 'SilentlyContinue'

# 0) Eventuele kleine wachttijd zodat USB init klaar is
Start-Sleep -Seconds 10

# 1) Smart Card service zacht herstarten
sc.exe stop SCardSvr | Out-Null
sc.exe start SCardSvr | Out-Null

# 2) Eerst USB hubs kort resetten (hier hangen de HID devices vaak onder)
$usbHubPatterns = @(
  '^USB\\ROOT_HUB',                 # Root hubs
  '^USB\\VID_',                     # Concreet USB devices
  'USB-hoofdhub',                   # NL naam
  'Samengesteld USB-apparaat'       # Composite device
)

$usbTargets = Get-PnpDevice | Where-Object {
  ($_.InstanceId -match $usbHubPatterns[0]) -or
  ($_.InstanceId -match $usbHubPatterns[1]) -or
  ($_.FriendlyName -match $usbHubPatterns[2]) -or
  ($_.FriendlyName -match $usbHubPatterns[3])
}

foreach ($d in $usbTargets) {
  try {
    Disable-PnpDevice -InstanceId $d.InstanceId -Confirm:$false
    Start-Sleep -Milliseconds 700
    Enable-PnpDevice  -InstanceId $d.InstanceId -Confirm:$false
  } catch {}
}

# 3) Dan specifiek de HID-devices die jij in Apparaatbeheer ziet
$hidNamesExact = @(
  'HID-compatibel touchscreen',
  'HID-compatibel, door leverancier gedefinieerd apparaat',
  'USB-invoerapparaat'
)

# Pak alle HID-class devices en filter op bovenstaande NL-namen
$hidTargets = Get-PnpDevice -Class HIDClass | Where-Object {
  $hidNamesExact -contains $_.FriendlyName -or $_.FriendlyName -match 'HID-compatibel|USB-invoer'
}

foreach ($d in $hidTargets) {
  try {
    Disable-PnpDevice -InstanceId $d.InstanceId -Confirm:$false
    Start-Sleep -Milliseconds 700
    Enable-PnpDevice  -InstanceId $d.InstanceId -Confirm:$false
  } catch {}
}

# 4) Kleine pauze en klaar
Start-Sleep -Seconds 2