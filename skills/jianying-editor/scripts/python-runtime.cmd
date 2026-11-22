@echo off
setlocal
set "JY_SKILL_ROOT=%~dp0.."
set "PATH=%USERPROFILE%\.local\share\ops-skills-20261114\tools\ffmpeg\bin;%PATH%"
"%USERPROFILE%\.local\share\video-edit-runtimes\jianying-editor\Scripts\python.exe" -X utf8 -B %*
exit /b %errorlevel%
