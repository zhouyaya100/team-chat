@echo off
chcp 65001 >nul
echo ================================
echo   Team Chat - 启动脚本
echo ================================
echo.

cd /d "%~dp0"

echo [1/3] 检查 Python 环境...
python --version >nul 2>&1
if errorlevel 1 (
    echo ❌ 错误：未找到 Python，请先安装 Python 3.8+
    pause
    exit /b 1
)
echo ✅ Python 环境正常

echo.
echo [2/3] 安装依赖...
pip install -r requirements.txt -q
echo ✅ 依赖安装完成

echo.
echo [3/3] 启动服务...
echo.
python app.py

pause
