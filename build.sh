#!/usr/bin/env bash
set -e

echo "============================================================"
echo " 구매영수증 사진 삽입기 - 빌드"
echo "============================================================"
echo

if ! command -v python3 &> /dev/null; then
    echo "[ERROR] python3을 찾을 수 없습니다. Python 3.10+ 설치 후 다시 시도하세요."
    exit 1
fi

echo "[1/4] 의존성 설치..."
python3 -m pip install --upgrade pip
python3 -m pip install PySide6 Pillow pyinstaller

echo
echo "[2/4] 이전 빌드 정리..."
rm -rf build dist

echo
echo "[3/4] PyInstaller 실행..."
python3 -m PyInstaller build.spec --clean --noconfirm

echo
echo "[4/4] 완료!"
echo
echo "결과: dist/구매영수증_사진삽입기"
echo

# 결과 폴더 열기 (Mac만)
if [[ "$OSTYPE" == "darwin"* ]]; then
    open dist
fi
