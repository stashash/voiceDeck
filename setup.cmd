@echo off
rem voiceDeck setup wizard for Windows. Run from the repository root: setup.cmd
rem Execution policy is bypassed for this run only, so the wizard works where .ps1 files are blocked.
setlocal
chcp 65001 >nul
rem Started from PowerShell 7, Windows PowerShell 5.1 inherits its module path and loses Get-FileHash
rem and other built-in cmdlets. Without the variable it builds its own default path.
set "PSModulePath="
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\setup.ps1" %*
set CODE=%ERRORLEVEL%
rem Started by double click: keep the window open so the result can be read.
echo %cmdcmdline% | find /i "/c" >nul && pause
exit /b %CODE%
