# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for 구매영수증 사진 삽입기.

빌드:
    pyinstaller build.spec --clean

또는 build.bat (Windows) / build.sh (Mac/Linux) 사용.
"""

from pathlib import Path

block_cipher = None

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[
        # 템플릿 파일을 번들에 포함 (resource_path로 접근)
        ('assets/template.hwpx', 'assets'),
        # 아이콘 (윈도우 타이틀바/작업표시줄에서 사용)
        ('assets/icon.ico', 'assets'),
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # 불필요한 큰 모듈 제외 (용량 절감)
        'tkinter',
        'unittest',
        'pydoc',
        'doctest',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='구매영수증_사진삽입기',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,             # GUI 앱이라 콘솔 숨김
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='assets/icon.ico',    # 사진/영수증 느낌의 아이콘
)
