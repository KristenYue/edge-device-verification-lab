$ErrorActionPreference = "Stop"

$vsRoot = "C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools"
$cmake = Join-Path $vsRoot "Common7\IDE\CommonExtensions\Microsoft\CMake\CMake\bin\cmake.exe"
$ninja = Join-Path $vsRoot "Common7\IDE\CommonExtensions\Microsoft\CMake\Ninja\ninja.exe"
$vcvars = Join-Path $vsRoot "VC\Auxiliary\Build\vcvars64.bat"

if (-not (Test-Path -LiteralPath $cmake)) { throw "Bundled Visual Studio CMake not found" }
if (-not (Test-Path -LiteralPath $ninja)) { throw "Bundled Visual Studio Ninja not found" }
if (-not (Test-Path -LiteralPath $vcvars)) { throw "Visual C++ environment script not found" }

$root = Split-Path -Parent $PSScriptRoot
$build = Join-Path $root "build"
$command = "`"$vcvars`" && `"$cmake`" -S `"$root`" -B `"$build`" -G Ninja -DCMAKE_MAKE_PROGRAM=`"$ninja`" -DCMAKE_BUILD_TYPE=Release -DCMAKE_TRY_COMPILE_CONFIGURATION=Release && `"$cmake`" --build `"$build`" && `"$cmake`" --build `"$build`" --target test"
cmd.exe /d /s /c $command
if ($LASTEXITCODE -ne 0) { throw "C++ build or tests failed with exit code $LASTEXITCODE" }

Write-Output (Join-Path $build "edge_device_simulator.exe")


