param([string]$ArduinoCli='arduino-cli', [ValidateSet('uart','native-usb')][string]$Transport='native-usb', [ValidateSet(38,48)][int]$BuiltinRgbPin=48)
$ErrorActionPreference='Stop'
$projectRoot=Split-Path -Parent $PSScriptRoot
$coreList=& $ArduinoCli core list --format json | ConvertFrom-Json
if($LASTEXITCODE -ne 0 -or !($coreList.platforms | Where-Object {$_.id -eq 'esp32:esp32' -and $_.installed_version -eq '3.3.12'})){throw 'Arduino-ESP32 3.3.12 is required.'}
$buildName=if($Transport -eq 'uart'){'led-diagnostic'}else{'led-diagnostic-native-usb'}
$buildDirectory=Join-Path $projectRoot "build\$buildName"
$cdc=if($Transport -eq 'native-usb'){'cdc'}else{'default'}
$fqbn="esp32:esp32:esp32s3:USBMode=hwcdc,CDCOnBoot=$cdc,FlashSize=16M,PartitionScheme=fatflash,PSRAM=opi"
& $ArduinoCli compile --fqbn $fqbn --build-path $buildDirectory --build-property "compiler.cpp.extra_flags=-DAI_MAKER_RGB_PIN=$BuiltinRgbPin" (Join-Path $PSScriptRoot 'led_diagnostic')
if($LASTEXITCODE -ne 0){throw 'Diagnostic build failed.'}
$diagnosticImage=Get-Item -LiteralPath (Join-Path $buildDirectory 'led_diagnostic.ino.bin')
$metadata=[ordered]@{
    firmware_family='ai-maker-led-diagnostic'
    transport=$Transport
    default_boot_pin=$BuiltinRgbPin
    default_boot_mode='rgb_solid'
    rgb_value_per_component=24
    teaching_sdk_compatible=$false
    fqbn=$fqbn
    image_bytes=$diagnosticImage.Length
    image_sha256=(Get-FileHash -LiteralPath $diagnosticImage.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
    hardware_tested=$false
}
$metadata | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $buildDirectory 'diagnostic-manifest.json') -Encoding utf8
Write-Output "Diagnostic built at $buildDirectory. This is not teaching SDK firmware. Nothing uploaded."
