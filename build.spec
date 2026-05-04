# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec — 슬림 빌드 (사용 안 하는 Qt 모듈 대량 제외 + UPX 압축).
"""
from pathlib import Path

block_cipher = None

# 사용하는 Qt 모듈: QtCore, QtGui, QtWidgets 만 필요.
EXCLUDED_QT = [
    'PySide6.QtNetwork', 'PySide6.QtQml', 'PySide6.QtQuick',
    'PySide6.QtQuickWidgets', 'PySide6.QtQuick3D',
    'PySide6.QtWebEngineCore', 'PySide6.QtWebEngineWidgets',
    'PySide6.QtWebEngineQuick', 'PySide6.QtWebChannel',
    'PySide6.QtWebSockets', 'PySide6.QtWebView',
    'PySide6.QtMultimedia', 'PySide6.QtMultimediaWidgets',
    'PySide6.QtPdf', 'PySide6.QtPdfWidgets',
    'PySide6.QtSvg', 'PySide6.QtSvgWidgets',
    'PySide6.QtCharts', 'PySide6.QtDataVisualization',
    'PySide6.QtLocation', 'PySide6.QtPositioning',
    'PySide6.QtTest', 'PySide6.QtSql',
    'PySide6.QtBluetooth', 'PySide6.QtNfc',
    'PySide6.QtSerialPort', 'PySide6.QtSerialBus',
    'PySide6.QtSensors', 'PySide6.QtRemoteObjects',
    'PySide6.QtScxml', 'PySide6.QtStateMachine',
    'PySide6.QtTextToSpeech', 'PySide6.QtDesigner',
    'PySide6.QtHelp', 'PySide6.QtUiTools',
    'PySide6.Qt3DAnimation', 'PySide6.Qt3DCore',
    'PySide6.Qt3DExtras', 'PySide6.Qt3DInput',
    'PySide6.Qt3DLogic', 'PySide6.Qt3DRender',
    'PySide6.QtAxContainer', 'PySide6.QtConcurrent',
    'PySide6.QtNetworkAuth', 'PySide6.QtPrintSupport',
    'PySide6.QtOpenGL', 'PySide6.QtOpenGLWidgets',
    'PySide6.QtSpatialAudio', 'PySide6.QtHttpServer',
    'PySide6.QtGraphs', 'PySide6.QtGraphsWidgets',
]

EXCLUDED_PY = [
    'tkinter', 'unittest', 'pydoc', 'doctest', 'pdb',
    'distutils', 'setuptools', 'pkg_resources',
    'numpy', 'scipy', 'pandas', 'matplotlib',
    'IPython', 'jupyter', 'notebook', 'pytest', 'sphinx',
    'wheel', 'pip', 'lib2to3', 'curses', 'sqlite3',
    'xml.dom', 'xmlrpc', 'http.server', 'email',
]

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('assets/template.hwpx', 'assets'),
        ('assets/icon.ico', 'assets'),
    ],
    hiddenimports=[
        # cryptography 패키지의 동적 임포트 (AES-GCM 복호화용)
        'cryptography.hazmat.primitives.ciphers.aead',
        'cryptography.hazmat.primitives.kdf.pbkdf2',
        'cryptography.hazmat.primitives.hashes',
        'cryptography.hazmat.backends.openssl',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=EXCLUDED_QT + EXCLUDED_PY,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

# binaries/datas에서 사용 안 하는 Qt DLL을 한 번 더 필터링
def _is_unwanted(name: str) -> bool:
    n = name.lower().replace('\\', '/').rsplit('/', 1)[-1]
    full = name.lower().replace('\\', '/')
    UNWANTED_DLL_PREFIX = (
        'qt6network', 'qt6qml', 'qt6quick', 'qt6quick3d', 'qt6quickwidgets',
        'qt6webengine', 'qt6webchannel', 'qt6websockets', 'qt6webview',
        'qt6multimedia', 'qt6pdf', 'qt6svg', 'qt6charts', 'qt6datavisualization',
        'qt6location', 'qt6positioning', 'qt6test', 'qt6sql', 'qt6bluetooth',
        'qt6nfc', 'qt6serialport', 'qt6serialbus', 'qt6sensors',
        'qt6remoteobjects', 'qt6scxml', 'qt6statemachine', 'qt6texttospeech',
        'qt6designer', 'qt6help', 'qt6uitools', 'qt63d', 'qt6axcontainer',
        'qt6concurrent', 'qt6networkauth', 'qt6printsupport', 'qt6opengl',
        'qt6spatialaudio', 'qt6httpserver', 'qt6graphs', 'qt6quicktest',
        'qt6virtualkeyboard', 'qt6shadertools',
    )
    UNWANTED_DIR = (
        '/qml/', '/qmltooling/', '/networkinformation/',
        '/multimedia/', '/multimediawidgets/', '/sqldrivers/', '/tls/',
        '/printsupport/', '/sceneparsers/', '/geometryloaders/',
        '/renderplugins/', '/position/', '/canbus/',
        '/webengine', '/pdf/', '/wayland', '/iconengines/',
        '/generic/', '/networkaccess/', '/imageformats/qsvg',
    )
    if any(n.startswith(p) for p in UNWANTED_DLL_PREFIX):
        return True
    if any(p in full for p in UNWANTED_DIR):
        return True
    if 'opengl32sw.dll' in n:
        return True
    if 'd3dcompiler' in n:
        return True
    return False

a.binaries = [b for b in a.binaries if not _is_unwanted(b[0])]
a.datas = [d for d in a.datas if not _is_unwanted(d[0])]

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
    upx_exclude=[
        'vcruntime140.dll',
        'python311.dll', 'python312.dll', 'python313.dll',
        # cryptography의 OpenSSL DLL은 UPX 압축 시 손상될 수 있음
        'libcrypto-3.dll', 'libssl-3.dll',
        'libcrypto-3-x64.dll', 'libssl-3-x64.dll',
        '_rust.pyd',  # cryptography의 Rust 백엔드
    ],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='assets/icon.ico',
)
