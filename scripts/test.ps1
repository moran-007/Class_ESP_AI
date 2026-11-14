param([string]$Python = 'python', [string]$Compiler = 'g++', [string]$ArduinoCli = 'arduino-cli', [ValidateSet(38,48)][int]$BuiltinRgbPin = 48, [switch]$IncludeExamples)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
& (Join-Path $PSScriptRoot 'build_native.ps1') -Compiler $Compiler -ArduinoCli $ArduinoCli -BuiltinRgbPin $BuiltinRgbPin
$previousPythonPath = $env:PYTHONPATH
$previousNative = $env:AI_MAKER_NATIVE
$previousExamples = $env:AI_MAKER_TEST_EXAMPLES
try {
    $env:PYTHONPATH = Join-Path $projectRoot 'sdk\python\src'
    $env:AI_MAKER_NATIVE = Join-Path $projectRoot 'build-native\ai_maker_native.exe'
    $env:AI_MAKER_TEST_EXAMPLES = if ($IncludeExamples) { '1' } else { '0' }
    & $Python -m unittest discover -s (Join-Path $projectRoot 'sdk\python\tests') -v
    if ($LASTEXITCODE -ne 0) { throw 'Python SDK or native integration tests failed.' }
    & $Python -m unittest discover -s (Join-Path $projectRoot 'tests\configuration') -v
    if ($LASTEXITCODE -ne 0) { throw 'Shared configuration or guide tests failed.' }
    & $Python -m unittest discover -s (Join-Path $projectRoot 'editor\tests') -v
    if ($LASTEXITCODE -ne 0) { throw 'Editor HTTP tests failed.' }
} finally {
    $env:PYTHONPATH = $previousPythonPath
    $env:AI_MAKER_NATIVE = $previousNative
    $env:AI_MAKER_TEST_EXAMPLES = $previousExamples
}
