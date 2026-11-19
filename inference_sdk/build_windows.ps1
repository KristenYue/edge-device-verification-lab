param([Parameter(Mandatory=$true)][string]$OrtRoot, [switch]$Wheel)
$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
$repoRoot = Split-Path -Parent $projectRoot
$pythonExe = Join-Path $repoRoot '.venv-sdk\Scripts\python.exe'
$vsRoot = 'C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools'
$vcvars = Join-Path $vsRoot 'VC\Auxiliary\Build\vcvars64.bat'
$cmakeBin = Join-Path $vsRoot 'Common7\IDE\CommonExtensions\Microsoft\CMake\CMake\bin'
$ninjaBin = Join-Path $vsRoot 'Common7\IDE\CommonExtensions\Microsoft\CMake\Ninja'
$resolvedOrt = (Resolve-Path -LiteralPath $OrtRoot).Path
if (-not (Test-Path -LiteralPath (Join-Path $resolvedOrt 'include\onnxruntime_cxx_api.h'))) { throw 'ORT headers missing' }
$env:PATH = "$cmakeBin;$ninjaBin;$env:PATH"
# Fixed executable paths and quoted paths; no destructive shell operations.
$pipAction = if ($Wheel) { "wheel --wheel-dir `"$projectRoot\dist`"" } else { 'install' }
$command = "`"$vcvars`" && `"$pythonExe`" -m pip $pipAction `"$projectRoot`" --no-build-isolation --no-deps --config-settings=cmake.define.ORT_ROOT=`"$resolvedOrt`""
cmd.exe /d /s /c $command
if ($LASTEXITCODE -ne 0) { throw 'Native SDK build failed' }
