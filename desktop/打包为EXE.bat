@echo off
rem 海外仓管理看板 - 桌面版打包脚本
rem 需要网络可访问 GitHub(或配置镜像)。产物在 dist\ 目录。

cd /d "%~dp0"

rem 如果还没有安装依赖，先安装
if not exist node_modules\electron\dist\electron.exe (
  echo [1/3] 安装 Electron...
  set ELECTRON_MIRROR=https://npmmirror.com/mirrors/electron/
  call npm.cmd install
  echo.
)

echo [2/3] 预填 electron-builder 二进制缓存(NPMMIRROR)...
set ELECTRON_BUILDER_BINARIES_MIRROR=https://npmmirror.com/mirrors/electron-builder-binaries/
set CSC_IDENTITY_AUTO_DISCOVERY=false

echo [3/3] 打包 Windows x64 安装程序...
call npx.cmd electron-builder --win --x64 --config.win.signAndEditExecutable=false

if %errorlevel%==0 (
  echo.
  echo 打包完成！安装程序在 dist\ 目录：
  dir /b dist\*.exe 2>nul
) else (
  echo.
  echo 打包失败。若卡在"下载 GitHub 资源"说明网络无法直连 GitHub，
  echo 请配置代理后重试，或仅在能访问此项目的机器上运行本脚本。
)
pause