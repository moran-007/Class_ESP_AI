param(
    [string]$ArduinoCli = 'arduino-cli',
    [ValidateSet('uart', 'native-usb')][string]$Transport = 'native-usb',
    [ValidateSet(38, 48)][int]$BuiltinRgbPin = 48,
    [string]$BuildDirectory = '',
    [string]$Esptool = (Join-Path $env:LOCALAPPDATA 'Arduino15/packages/esp32/tools/esptool_py/5.3.1/esptool.exe')
)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
if (!$BuildDirectory) {
    $buildName = if ($BuiltinRgbPin -eq 48) { $Transport } else { "$Transport-rgb$BuiltinRgbPin" }
    $BuildDirectory = Join-Path $projectRoot "build\$buildName"
}
$installedCores = & $ArduinoCli core list --format json | ConvertFrom-Json
if ($LASTEXITCODE -ne 0) { throw 'Cannot query Arduino cores.' }
if (!($installedCores.platforms | Where-Object { $_.id -eq 'esp32:esp32' -and $_.installed_version -eq '3.3.12' })) {
    throw 'Install the verified esp32:esp32@3.3.12 core before building.'
}
$installedLibraries = & $ArduinoCli lib list --format json | ConvertFrom-Json
if ($LASTEXITCODE -ne 0) { throw 'Cannot query Arduino libraries.' }
$jsonLibrary = $installedLibraries.installed_libraries | Where-Object { $_.library.name -eq 'ArduinoJson' -and $_.library.version -eq '7.4.3' } | Select-Object -First 1
if (!$jsonLibrary) { throw 'Install the verified ArduinoJson@7.4.3 library before building.' }
$displayDependencies = [ordered]@{
    'Adafruit GFX Library' = '1.12.6'
    'Adafruit ST7735 and ST7789 Library' = '1.11.0'
    'Adafruit BusIO' = '1.17.4'
    'U8g2_for_Adafruit_GFX' = '1.8.0'
}
$displayLibraries = @()
foreach ($name in $displayDependencies.Keys) {
    $library = $installedLibraries.installed_libraries | Where-Object { $_.library.name -eq $name -and $_.library.version -eq $displayDependencies[$name] } | Select-Object -First 1
    if (!$library) { throw "Install the verified $name@$($displayDependencies[$name]) library before building." }
    $displayLibraries += $library.library.install_dir
}
$cdc = if ($Transport -eq 'native-usb') { 'cdc' } else { 'default' }
$fqbn = "esp32:esp32:esp32s3:USBMode=hwcdc,CDCOnBoot=$cdc,FlashSize=16M,PartitionScheme=fatflash,PSRAM=opi"
$compileArguments = @('compile', '--fqbn', $fqbn, '--build-path', $BuildDirectory, '--build-property', 'upload.maximum_size=3145728', '--build-property', "compiler.cpp.extra_flags=-DAI_MAKER_RGB_PIN=$BuiltinRgbPin", '--library', $jsonLibrary.library.install_dir)
foreach ($directory in $displayLibraries) { $compileArguments += @('--library', $directory) }
$compileArguments += (Join-Path $PSScriptRoot 'ai_maker_s3')
& $ArduinoCli @compileArguments
if ($LASTEXITCODE -ne 0) { throw 'ESP32-S3 compilation failed.' }
$table = Join-Path $BuildDirectory 'ai_maker_s3.ino.partitions.bin'
$app = Join-Path $BuildDirectory 'ai_maker_s3.ino.bin'
if ((Get-Item -LiteralPath $app).Length -gt 0x300000) { throw 'App exceeds 3 MiB partition size.' }
if ((Get-FileHash -LiteralPath (Join-Path $BuildDirectory 'partitions.csv')).Hash -ne (Get-FileHash -LiteralPath (Join-Path $PSScriptRoot 'ai_maker_s3/partitions.csv')).Hash) { throw 'Build did not use the teaching partition table.' }
# Arduino's generic flash recipe places boot_app0 at 0xe000, inside this layout's NVS.
# Replace generated flash instructions and merged image with this project's layout.
if (!(Test-Path -LiteralPath $Esptool)) { throw 'Set -Esptool to the ESP32 Arduino esptool executable.' }
$boot = Join-Path $BuildDirectory 'ai_maker_s3.ino.bootloader.bin'
$merged = Join-Path $BuildDirectory 'ai_maker_s3.ino.merged.bin'
& $Esptool --chip esp32s3 merge-bin -o $merged --pad-to-size 16MB 0x0 $boot 0x8000 $table 0x10000 $app
if ($LASTEXITCODE -ne 0) { throw 'The blank-board reference image could not be built.' }
@('0x0 ai_maker_s3.ino.bootloader.bin', '0x8000 ai_maker_s3.ino.partitions.bin', '0x10000 ai_maker_s3.ino.bin') | Set-Content -LiteralPath (Join-Path $BuildDirectory 'flash_args') -Encoding ascii
New-Item -ItemType Directory -Path $BuildDirectory -Force | Out-Null
$manifest = [ordered]@{
    firmware_family = 'ai-maker-s3'
    firmware_version = '0.8.0'
    protocol_version = 1
    fqbn = $fqbn
    core_version = '3.3.12'
    arduinojson_version = '7.4.3'
    display_dependencies = $displayDependencies
    transport = $Transport
    builtin_rgb_pin = $BuiltinRgbPin
    partition_layout = 'class-16m-factory-dual-ota-v1'
    factory_offset = '0x10000'
    app_slot_bytes = 3145728
    merged_blank_board_only = $true
    ota_transfer_implemented = $false
    hardware_tested = $false
    artifacts = @(Get-ChildItem -LiteralPath $BuildDirectory -Filter 'ai_maker_s3.ino*.bin' | ForEach-Object {
        [ordered]@{name=$_.Name; bytes=$_.Length; sha256=(Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()}
    })
}
$manifest | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $BuildDirectory 'build-manifest.json') -Encoding utf8
Write-Output "Build verified: $BuildDirectory. No upload or device connection was performed."
