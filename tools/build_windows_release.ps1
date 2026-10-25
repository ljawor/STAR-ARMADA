# Build the Windows release ZIP on a Windows machine.
#
# This mirrors .github/workflows/release.yml step for step, so the artifact it produces is the
# same one the workflow would upload. It exists because PyInstaller cannot cross-compile: the exe
# and the native DLL have to be produced on Windows with MSVC. Run it from the repository root:
#
#     powershell -ExecutionPolicy Bypass -File tools\build_windows_release.ps1 -Version v1.0.0
#
# Requirements: Windows 10/11 x64, Python 3.11 on PATH, Visual Studio 2022 with the C++ workload
# (the build pins the VS 17 2022 generator and the x64 platform).

param(
    [string]$Version = "",
    [string]$BuildDir = "render_cpp\build-w02"
)

$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path))
$env:CMAKE_GENERATOR = "Visual Studio 17 2022"
$env:CMAKE_GENERATOR_PLATFORM = "x64"

if (-not $Version) {
    $Version = (& .\.venv\Scripts\python.exe -c "from game import __version__; print(__version__)")
    $Version = "v$Version"
}
Write-Host "== building STAR ARMADA $Version"

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    python -m venv .venv
}
& .\.venv\Scripts\python.exe -m pip install --upgrade pip
& .\.venv\Scripts\pip.exe install -r requirements.txt pyinstaller==6.20.0 cmake==3.31.6

Write-Host "== native renderer (Release, tests included)"
& .\.venv\Scripts\python.exe tools\build_native_release.py --build-dir $BuildDir
if ($LASTEXITCODE -ne 0) { throw "native build failed" }

Write-Host "== packaging contract tests"
& .\.venv\Scripts\python.exe -m unittest discover -s tests -p test_release_packaging.py -v
if ($LASTEXITCODE -ne 0) { throw "packaging contract tests failed" }

Write-Host "== frozen app"
Remove-Item -Recurse -Force "build\star_armada", "dist\STAR ARMADA" -ErrorAction SilentlyContinue
& .\.venv\Scripts\pyinstaller.exe star_armada.spec --noconfirm
if ($LASTEXITCODE -ne 0) { throw "pyinstaller failed" }

Write-Host "== frozen native payload"
& .\.venv\Scripts\python.exe tools\build_native_release.py --validate-frozen "dist\STAR ARMADA\_internal"
if ($LASTEXITCODE -ne 0) { throw "frozen payload validation failed" }

Write-Host "== frozen worker probe (no GPU)"
$probe = Join-Path $env:TEMP "native-worker-probe.json"
if (Test-Path $probe) { Remove-Item $probe }
Remove-Item Env:\STAR_ARMADA_CPP_LIBRARY -ErrorAction SilentlyContinue
$exe = (Resolve-Path "dist\STAR ARMADA\STAR ARMADA.exe").Path
& $exe --native-render-worker --probe --output $probe
if ($LASTEXITCODE -ne 0) { throw "frozen worker probe exited $LASTEXITCODE" }
$report = Get-Content $probe -Raw | ConvertFrom-Json
$expected = (Join-Path (Split-Path $exe) "_internal\cpp\armada_embedded.dll")
if ($report.status -ne "ok" -or $report.abi -ne 1 -or -not $report.frozen) {
    throw "probe report is not a frozen ABI-1 worker: $($report | ConvertTo-Json -Compress)"
}
if ((Resolve-Path $report.native_library).Path -ne (Resolve-Path $expected).Path) {
    throw "probe loaded $($report.native_library), expected $expected"
}
$report | ConvertTo-Json

Write-Host "== zip"
$zip = "dist\STAR-ARMADA-$Version-win.zip"
Remove-Item $zip -ErrorAction SilentlyContinue
Compress-Archive -Path "dist\STAR ARMADA\*" -DestinationPath $zip
Get-FileHash $zip -Algorithm SHA256 | Format-List
Write-Host "DONE $zip"
