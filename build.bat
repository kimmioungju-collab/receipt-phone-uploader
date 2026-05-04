@echo off
chcp 65001 > nul
echo ============================================================
echo  구매영수증 사진 삽입기 - Windows 빌드
echo ============================================================
echo.

REM 가상환경 권장 — 없으면 시스템에 설치
where python >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Python을 찾을 수 없습니다. Python 3.10+ 설치 후 다시 시도하세요.
    pause
    exit /b 1
)

echo [1/4] 의존성 설치...
python -m pip install --upgrade pip
python -m pip install PySide6 Pillow pyinstaller
if errorlevel 1 (
    echo [ERROR] 의존성 설치 실패
    pause
    exit /b 1
)

echo.
echo [2/4] 이전 빌드 정리...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

echo.
echo [3/4] PyInstaller 실행...
python -m PyInstaller build.spec --clean --noconfirm
if errorlevel 1 (
    echo [ERROR] 빌드 실패
    pause
    exit /b 1
)

echo.
echo [4/4] 완료!
echo.
echo 결과: dist\구매영수증_사진삽입기.exe
echo.

REM 결과 폴더 열기
explorer dist
pause
