param(
    [string]$ArduinoCli = 'arduino-cli',
    [ValidateSet('uart', 'native-usb')][string]$Transport = 'native-usb',
    [ValidateSet(38, 48)][int]$BuiltinRgbPin = 48,
    [string]$BuildDirectory = ''
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
$compileArguments = @('compile', '--fqbn', $fqbn, '--build-path', $BuildDirectory, '--build-property', "compiler.cpp.extra_flags=-DAI_MAKER_RGB_PIN=$BuiltinRgbPin", '--library', $jsonLibrary.library.install_dir)
foreach ($directory in $displayLibraries) { $compileArguments += @('--library', $directory) }
$compileArguments += (Join-Path $PSScriptRoot 'ai_maker_s3')
& $ArduinoCli @compileArguments
if ($LASTEXITCODE -ne 0) { throw 'ESP32-S3 compilation failed.' }
New-Item -ItemType Directory -Path $BuildDirectory -Force | Out-Null
$manifest = [ordered]@{
    firmware_family = 'ai-maker-s3'
    firmware_version = '0.5.0'
    protocol_version = 1
    fqbn = $fqbn
    core_version = '3.3.12'
    arduinojson_version = '7.4.3'
    display_dependencies = $displayDependencies
    transport = $Transport
    builtin_rgb_pin = $BuiltinRgbPin
    partition_layout = 'fatflash-16M-reference'
    hardware_tested = $false
    artifacts = @(Get-ChildItem -LiteralPath $BuildDirectory -Filter '*.bin' | ForEach-Object {
        [ordered]@{name=$_.Name; bytes=$_.Length; sha256=(Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()}
    })
}
$manifest | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $BuildDirectory 'build-manifest.json') -Encoding utf8
Write-Output "Build verified: $BuildDirectory. No upload or device connection was performed."
