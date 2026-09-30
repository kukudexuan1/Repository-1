@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo 正在启动 设计仿真助手（前端 + 后端）...

REM 优先用 conda 的 edp 环境。conda run 无需先 init shell，最稳妥。
where conda >nul 2>nul
if %errorlevel%==0 (
    conda run -n edp --no-capture-output python -m app.frontend_launcher %*
    goto :end
)

REM 找不到 conda 时，尝试常见安装位置。
for %%C in (
    "%USERPROFILE%\anaconda3\Scripts\conda.exe"
    "%USERPROFILE%\miniconda3\Scripts\conda.exe"
    "%USERPROFILE%\Anaconda3\Scripts\conda.exe"
    "%USERPROFILE%\Miniconda3\Scripts\conda.exe"
    "C:\ProgramData\anaconda3\Scripts\conda.exe"
    "C:\ProgramData\miniconda3\Scripts\conda.exe"
) do (
    if exist %%C (
        %%C run -n edp --no-capture-output python -m app.frontend_launcher %*
        goto :end
    )
)

echo [错误] 未找到 conda。请先激活 edp 环境后手动运行：
echo     conda activate edp
echo     python -m app.frontend_launcher

:end
pause
