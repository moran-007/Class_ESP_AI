param([string]$Compiler = 'g++', [string]$ArduinoCli = 'arduino-cli', [string]$ArduinoJsonSource = '', [ValidateSet(38,48)][int]$BuiltinRgbPin = 48)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
if (!$ArduinoJsonSource) {
    $installedLibraries = & $ArduinoCli lib list --format json | ConvertFrom-Json
    if ($LASTEXITCODE -ne 0) { throw 'Cannot query Arduino libraries.' }
    $jsonLibrary = $installedLibraries.installed_libraries | Where-Object { $_.library.name -eq 'ArduinoJson' -and $_.library.version -eq '7.4.3' } | Select-Object -First 1
    if (!$jsonLibrary) { throw 'ArduinoJson 7.4.3 not found; supply -ArduinoJsonSource.' }
    $ArduinoJsonSource = $jsonLibrary.library.source_dir
}
if (!(Test-Path -LiteralPath (Join-Path $ArduinoJsonSource 'ArduinoJson.h'))) { throw 'ArduinoJsonSource must contain ArduinoJson.h.' }
$coreDirectory = Join-Path $projectRoot 'firmware\ai_maker_s3'
$nativeDirectory = Join-Path $projectRoot 'tests\native'
$outputDirectory = Join-Path $projectRoot 'build-native'
New-Item -ItemType Directory -Path $outputDirectory -Force | Out-Null
$coreSources = @('device_core.cpp', 'device_pages.cpp', 'device_audio.cpp', 'page_model.cpp') | ForEach-Object { Join-Path $coreDirectory $_ }
$coreObjects = @()
foreach ($source in $coreSources) {
    $object = Join-Path $outputDirectory (([IO.Path]::GetFileNameWithoutExtension($source)) + '.o')
    & $Compiler '-std=c++17' '-Wall' '-Wextra' '-Werror' "-DAI_MAKER_RGB_PIN=$BuiltinRgbPin" '-I' $ArduinoJsonSource '-I' $coreDirectory '-c' $source '-o' $object
    if ($LASTEXITCODE -ne 0) { throw "Native compilation failed: $source" }
    $coreObjects += $object
}
foreach ($program in @(@('test_core.cpp', 'test_core.exe'), @('native_main.cpp', 'ai_maker_native.exe'), @('test_display_core.cpp', 'test_display_core.exe'), @('test_page_model.cpp', 'test_page_model.exe'), @('test_pages_core.cpp', 'test_pages_core.exe'), @('test_audio_core.cpp', 'test_audio_core.exe'))) {
    & $Compiler '-std=c++17' '-Wall' '-Wextra' '-Werror' "-DAI_MAKER_RGB_PIN=$BuiltinRgbPin" '-I' $ArduinoJsonSource '-I' $coreDirectory @coreObjects (Join-Path $nativeDirectory $program[0]) '-o' (Join-Path $outputDirectory $program[1])
    if ($LASTEXITCODE -ne 0) { throw "Native compilation failed: $($program[0])" }
}
& (Join-Path $outputDirectory 'test_core.exe')
if ($LASTEXITCODE -ne 0) { throw 'Native core behavior tests failed.' }
& (Join-Path $outputDirectory 'test_display_core.exe')
if ($LASTEXITCODE -ne 0) { throw 'Native display behavior tests failed.' }
& (Join-Path $outputDirectory 'test_page_model.exe')
if ($LASTEXITCODE -ne 0) { throw 'Native page model tests failed.' }
& (Join-Path $outputDirectory 'test_pages_core.exe')
if ($LASTEXITCODE -ne 0) { throw 'Native page runtime tests failed.' }
& (Join-Path $outputDirectory 'test_audio_core.exe')
if ($LASTEXITCODE -ne 0) { throw 'Native audio runtime tests failed.' }
& $Compiler '-std=c++17' '-Wall' '-Wextra' '-Werror' '-I' (Join-Path $nativeDirectory 'rgb_stubs') '-I' $coreDirectory (Join-Path $coreDirectory 'board_rgb.cpp') (Join-Path $nativeDirectory 'test_board_rgb.cpp') '-o' (Join-Path $outputDirectory 'test_board_rgb.exe')
if ($LASTEXITCODE -ne 0) { throw 'RGB driver test compilation failed.' }
& (Join-Path $outputDirectory 'test_board_rgb.exe')
if ($LASTEXITCODE -ne 0) { throw 'RGB driver fault tests failed.' }
& $Compiler '-std=c++17' '-Wall' '-Wextra' '-Werror' '-I' (Join-Path $nativeDirectory 'display_stubs') '-I' $ArduinoJsonSource '-I' $coreDirectory (Join-Path $coreDirectory 'board_display.cpp') (Join-Path $nativeDirectory 'test_board_display.cpp') '-o' (Join-Path $outputDirectory 'test_board_display.exe')
if ($LASTEXITCODE -ne 0) { throw 'Display driver test compilation failed.' }
& (Join-Path $outputDirectory 'test_board_display.exe')
if ($LASTEXITCODE -ne 0) { throw 'Display driver fault tests failed.' }
& $Compiler '-std=c++17' '-Wall' '-Wextra' '-Werror' '-I' (Join-Path $nativeDirectory 'audio_stubs') '-I' $coreDirectory (Join-Path $coreDirectory 'board_audio.cpp') (Join-Path $nativeDirectory 'test_board_audio.cpp') '-o' (Join-Path $outputDirectory 'test_board_audio.exe')
if ($LASTEXITCODE -ne 0) { throw 'Audio driver test compilation failed.' }
& (Join-Path $outputDirectory 'test_board_audio.exe')
if ($LASTEXITCODE -ne 0) { throw 'Audio driver fault tests failed.' }
