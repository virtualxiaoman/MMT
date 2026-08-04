@echo off
title LuoTianyi QQ Bot

set ROOT=%~dp0
cd /d %ROOT%

echo Starting LuoTianyi QQ Bot...

%ROOT%venv\Scripts\python.exe -m src.QQ.QQBot_LuoTianyi

if errorlevel 1 (
    echo.
    echo Bot crashed.
    pause
)