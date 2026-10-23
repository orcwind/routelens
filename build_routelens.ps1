# 构建轨镜 RouteLens Windows 发布包
# 用法：在仓库根目录执行  powershell -ExecutionPolicy Bypass -File build_routelens.ps1

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

# 版本号以 src/routelens/version.py 为准
$VersionLine = Select-String -Path (Join-Path $Root "src\routelens\version.py") -Pattern 'VERSION\s*=\s*"([^"]+)"' | Select-Object -First 1
if (-not $VersionLine) { throw "VERSION not found in version.py" }
$Version = $VersionLine.Matches[0].Groups[1].Value
$DistName = "RouteLens"
$ZipName = "RouteLens-v$Version-win64.zip"
Write-Host "==> version $Version"

Write-Host "==> install pyinstaller"
python -m pip install -q "pyinstaller>=6.0" customtkinter pystray Pillow

Write-Host "==> preflight: running instance check"
# RouteLens 是便携布局，用户数据(data\)就住在 dist\RouteLens 里；
# 运行中的实例会锁文件，且 clean 会删掉它的数据目录 —— 必须先中止构建。
$running = Get-Process -Name $DistName -ErrorAction SilentlyContinue
if ($running) {
    throw ("RouteLens is running (pid {0}). Close it before building." -f ($running | Select-Object -First 1 -ExpandProperty Id))
}

Write-Host "==> preserve user data (dist\$DistName\data)"
$UserDataDir = Join-Path $Root "dist\$DistName\data"
$UserDataBak = Join-Path $env:TEMP ("routelens_userdata_" + [guid]::NewGuid().ToString("N").Substring(0, 8))
$HadUserData = Test-Path $UserDataDir
if ($HadUserData) {
    Copy-Item $UserDataDir $UserDataBak -Recurse -Force
    Write-Host "    backed up to $UserDataBak"
}

Write-Host "==> clean old build"
if (Test-Path "build") { Remove-Item "build" -Recurse -Force }
if (Test-Path "dist\$DistName") { Remove-Item "dist\$DistName" -Recurse -Force }
if (Test-Path "dist\$ZipName") { Remove-Item "dist\$ZipName" -Force }

Write-Host "==> pyinstaller routelens.spec"
python -m PyInstaller --noconfirm routelens.spec

$OutDir = Join-Path $Root "dist\$DistName"
if (-not (Test-Path (Join-Path $OutDir "RouteLens.exe"))) {
    throw "Build failed: RouteLens.exe not found in $OutDir"
}

# 确保用户可写的数据目录存在（启动后会写 assist.log / routes）
$dataOut = Join-Path $OutDir "data\routelens"
New-Item -ItemType Directory -Force -Path $dataOut | Out-Null

Write-Host "==> zip $ZipName (不含用户数据)"
# 打包时排除 data\：发布包应是干净安装包，用户数据只在构建后的本机 dist 里
$DataStash = Join-Path $OutDir "_data_stash"
$HadLocal = Test-Path (Join-Path $OutDir "data")
if ($HadLocal) {
    if (Test-Path $DataStash) { Remove-Item $DataStash -Recurse -Force }
    Move-Item (Join-Path $OutDir "data") $DataStash
    New-Item -ItemType Directory -Force -Path $dataOut | Out-Null
}
Compress-Archive -Path $OutDir -DestinationPath (Join-Path $Root "dist\$ZipName") -Force
if (Test-Path $DataStash) {
    Remove-Item (Join-Path $OutDir "data") -Recurse -Force
    Move-Item $DataStash (Join-Path $OutDir "data")
}

# 还原构建前备份的用户数据（路线 / 活动进度不因重新构建而丢失）
if ($HadUserData) {
    Copy-Item (Join-Path $UserDataBak "*") (Join-Path $OutDir "data") -Recurse -Force
    Remove-Item $UserDataBak -Recurse -Force
    Write-Host "    user data restored"
}
# 若 _internal 内有静态资源，再复制一份到 exe 旁，方便排查与升级
$internalData = Join-Path $OutDir "_internal\data\routelens"
if (Test-Path $internalData) {
    Copy-Item (Join-Path $internalData "*") $dataOut -Force -ErrorAction SilentlyContinue
}

Write-Host ""
Write-Host "OK"
Write-Host "  Folder: dist\$DistName\RouteLens.exe"
Write-Host "  Zip:    dist\$ZipName"
Write-Host "Upload the zip to GitHub Releases as the player download."
