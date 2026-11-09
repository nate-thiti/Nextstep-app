$ErrorActionPreference = "Stop"

$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$python = Join-Path $projectRoot ".venv\Scripts\python.exe"
$dist = Join-Path $projectRoot "dist"
$build = Join-Path $projectRoot "build\pyinstaller"
$nuitkaBuild = Join-Path $projectRoot "build\nuitka"
$icon = Join-Path $projectRoot "src\nextstep\assets\app-icon.ico"

if (-not (Test-Path -LiteralPath $python)) {
    throw "Virtual environment not found: $python"
}

& $python -m nuitka `
    (Join-Path $projectRoot "src\nextstep\main.py") `
    --follow-imports `
    --enable-plugin=pyside6 `
    --standalone `
    --output-dir=$nuitkaBuild `
    --output-filename=NextStep.exe `
    --windows-console-mode=disable `
    --windows-icon-from-ico=$icon `
    --include-package-data=nextstep `
    --include-module=logging.config `
    --include-raw-dir="$projectRoot\src\nextstep\migrations=nextstep/migrations" `
    --include-qt-plugins=platforminputcontexts `
    --noinclude-qt-translations `
    --noinclude-dlls=*.cpp.o `
    --noinclude-dlls=*.qsb `
    --assume-yes-for-downloads `
    --quiet

$nuitkaDist = Join-Path $nuitkaBuild "main.dist"
$desktopDist = Join-Path $dist "NextStep"
if (-not (Test-Path -LiteralPath $nuitkaDist)) {
    throw "Desktop output was not created: $nuitkaDist"
}
if (Test-Path -LiteralPath $desktopDist) {
    $resolvedDesktopDist = (Resolve-Path -LiteralPath $desktopDist).Path
    $expectedDesktopDist = [System.IO.Path]::GetFullPath($desktopDist)
    if ($resolvedDesktopDist -ne $expectedDesktopDist -or
        (Split-Path -Parent $resolvedDesktopDist) -ne [System.IO.Path]::GetFullPath($dist)) {
        throw "Refusing to replace unexpected desktop output: $resolvedDesktopDist"
    }
    Remove-Item -LiteralPath $resolvedDesktopDist -Recurse -Force
}
Move-Item -LiteralPath $nuitkaDist -Destination $desktopDist

& $python -m PyInstaller `
    --noconfirm `
    --clean `
    --onefile `
    --console `
    --name nextstep-mcp `
    --icon $icon `
    --paths (Join-Path $projectRoot "src") `
    --collect-data nextstep `
    --hidden-import logging.config `
    --add-data "$projectRoot\src\nextstep\migrations;nextstep\migrations" `
    --distpath $dist `
    --workpath (Join-Path $build "mcp") `
    --specpath (Join-Path $build "spec") `
    (Join-Path $projectRoot "src\nextstep\mcp_server\main.py")

$desktopExe = Join-Path $dist "NextStep\NextStep.exe"
$mcpExe = Join-Path $dist "nextstep-mcp.exe"
if (-not (Test-Path -LiteralPath $desktopExe)) {
    throw "Desktop executable was not created: $desktopExe"
}
if (-not (Test-Path -LiteralPath $mcpExe)) {
    throw "MCP executable was not created: $mcpExe"
}

Write-Output "Built: $desktopExe"
Write-Output "Built: $mcpExe"
