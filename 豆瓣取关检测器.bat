@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"

call :try_run_app
if %errorlevel%==0 goto :done

call :show_python_install_menu
goto :done

:try_run_app
where py >nul 2>nul
if not errorlevel 1 (
  py -3 -c "import sys; raise SystemExit(0 if sys.version_info.major == 3 else 1)" >nul 2>nul
  if not errorlevel 1 (
    py -3 app.py
    exit /b 0
  )
)

where python >nul 2>nul
if not errorlevel 1 (
  python -c "import sys; raise SystemExit(0 if sys.version_info.major == 3 else 1)" >nul 2>nul
  if not errorlevel 1 (
    python app.py
    exit /b 0
  )
)

exit /b 1

:install_with_winget
where winget >nul 2>nul
if errorlevel 1 (
  echo.
  echo 这台 Windows 电脑找不到 winget，无法自动通过命令行安装 Python 3。
  echo 我会打开 Python 官方下载页面，请下载安装后重新双击这个文件。
  start "" "https://www.python.org/downloads/windows/"
  exit /b 1
)

echo.
echo 正在使用 winget 安装 Python 3...
winget install --id Python.Python.3.13 --source winget --exact
exit /b !errorlevel!

:show_python_install_menu
echo.
echo 找不到 Python 3。
echo.
echo 请选择下一步：
echo 1. 使用 winget 自动安装 Python 3
echo 2. 打开 Python 官方下载页面
echo 3. 退出
echo.
set /p choice=请输入 1、2 或 3，然后按回车：

if "%choice%"=="1" (
  call :install_with_winget
  call :try_run_app
  if not errorlevel 1 exit /b 0
  echo.
  echo Python 3 还没有准备好。请安装完成后重新双击这个文件。
  echo 如果手动安装，请勾选 "Add python.exe to PATH"。
  echo.
  pause
  exit /b 1
)

if "%choice%"=="2" (
  start "" "https://www.python.org/downloads/windows/"
  echo.
  echo 下载安装 Python 3 后，请重新双击这个文件。
  echo 安装时请勾选 "Add python.exe to PATH"。
  echo.
  pause
  exit /b 1
)

echo.
echo 已退出。
echo.
pause
exit /b 1

:done
endlocal
