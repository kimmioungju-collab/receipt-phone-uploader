"""
tmpfiles_client.py — tmpfiles.org에서 매니페스트와 사진을 다운로드.

폰에서 사진 3장을 업로드하면 그 URL들을 묶은 manifest.json도 함께 업로드되고,
manifest의 URL에서 추출한 코드(예: "35541093")만 PC에 입력하면
이 코드로 매니페스트와 사진들을 모두 다운로드한다.

🔒 보안 (E2E AES-GCM 암호화):
  - 폰에서 PBKDF2-SHA256(10만회)로 passphrase → 256bit AES 키 유도
  - AES-256-GCM으로 사진/매니페스트 암호화 후 업로드
  - 표시 코드 = "{tmp_code}-{passphrase}"  (passphrase는 절대 네트워크 미전송)
  - 형식 (암호문): IV(12B) || ciphertext || GCM_tag(16B)
  - 코드에 "-"가 없으면 평문(레거시) 모드로 동작

tmpfiles.org URL 구조:
    https://tmpfiles.org/35541093/test.json    ← 폰이 받은 URL
    https://tmpfiles.org/dl/35541093/test.json ← 직접 다운로드 URL
"""

from __future__ import annotations
import json
import urllib.request
import urllib.parse
import urllib.error
import re
import hashlib
from pathlib import Path
from typing import Callable, Optional, Tuple


# AES-GCM은 cryptography 패키지로 처리 (PyInstaller 번들에 포함됨)
try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    from cryptography.hazmat.primitives import hashes
    _CRYPTO_OK = True
except ImportError:
    _CRYPTO_OK = False


# ===== 암호화 상수 (폰 페이지의 JS 코드와 반드시 일치해야 함) =====
PBKDF2_SALT = b'receipt-uploader-v1'
PBKDF2_ITERATIONS = 100_000
GCM_IV_BYTES = 12
GCM_TAG_BYTES = 16
PASSPHRASE_ALPHABET = 'ABCDEFGHJKMNPQRSTUVWXYZ23456789'  # 0/O/1/I/L 제외


def _force_https(url: str) -> str:
    """HTTP URL을 HTTPS로 업그레이드 (영수증 사진의 평문 노출 방지)."""
    if url.startswith('http://'):
        return 'https://' + url[len('http://'):]
    return url


def code_to_manifest_url(code: str, filename: str = "manifest.json") -> str:
    """코드 → 매니페스트 다운로드 URL (HTTPS)."""
    return f"https://tmpfiles.org/dl/{code.strip()}/{filename}"


def normalize_url(url: str) -> str:
    """tmpfiles.org URL을 dl 형식 + HTTPS로 변환."""
    url = _force_https(url)
    if '/dl/' in url:
        return url
    return url.replace('tmpfiles.org/', 'tmpfiles.org/dl/', 1)


def parse_code(input_str: str) -> Tuple[str, Optional[str]]:
    """입력 코드 파싱 → (tmp_code, passphrase or None).

    "35541093-X7K2QM4P"  → ("35541093", "X7K2QM4P")  암호화 모드
    "35541093"           → ("35541093", None)        평문(레거시) 모드
    """
    s = input_str.strip().upper().replace(' ', '')
    m = re.match(r'^(\d{6,10})(?:-([A-Z2-9]{4,32}))?$', s)
    if not m:
        raise ValueError("올바른 코드 형식이 아닙니다.\n예: 35541093-X7K2QM4P 또는 35541093")
    return m.group(1), m.group(2)


def derive_key(passphrase: str) -> bytes:
    """passphrase → 32바이트 AES-256 키 (PBKDF2-SHA256, 10만회).

    폰의 WebCrypto deriveKey와 동일한 파라미터를 사용.
    """
    if not _CRYPTO_OK:
        raise RuntimeError("cryptography 패키지가 없습니다. 평문 모드로만 작동합니다.")
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=PBKDF2_SALT,
        iterations=PBKDF2_ITERATIONS,
    )
    return kdf.derive(passphrase.encode('utf-8'))


def decrypt_blob(data: bytes, key: bytes) -> bytes:
    """AES-GCM 암호문 → 평문.

    형식: IV(12) || ciphertext+tag
    cryptography의 AESGCM.decrypt는 ciphertext 끝에 16바이트 태그가 붙어있는
    형태(WebCrypto와 동일)를 받는다.
    """
    if not _CRYPTO_OK:
        raise RuntimeError("cryptography 패키지가 없습니다.")
    if len(data) < GCM_IV_BYTES + GCM_TAG_BYTES:
        raise ValueError("암호문이 너무 짧습니다 (손상된 파일일 수 있음).")
    iv = data[:GCM_IV_BYTES]
    ct_with_tag = data[GCM_IV_BYTES:]
    aesgcm = AESGCM(key)
    try:
        return aesgcm.decrypt(iv, ct_with_tag, None)
    except Exception as e:
        # InvalidTag = passphrase 틀림 또는 데이터 변조
        raise ValueError(
            "복호화 실패: 비밀번호(코드 뒷부분)가 틀렸거나 데이터가 손상됐습니다."
        ) from e


def download_bytes(url: str, timeout: int = 30) -> bytes:
    """URL에서 바이너리 다운로드."""
    req = urllib.request.Request(
        url, headers={'User-Agent': 'Mozilla/5.0 ReceiptInserter/1.0'}
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def fetch_manifest(code: str, passphrase: Optional[str] = None) -> dict:
    """코드로 매니페스트 JSON 다운로드 (passphrase 있으면 복호화).

    반환: {
      "createdAt": "...",
      "photos": [{"slot": 1, "url": "...", "originalName": "..."}, ...],
      "encrypted": True/False  # 암호화 모드면 True
    }
    """
    url = code_to_manifest_url(code)
    try:
        data = download_bytes(url)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise ValueError(
                f"코드 {code}에 해당하는 데이터를 찾을 수 없습니다.\n"
                f"60분이 지났거나 잘못된 코드일 수 있습니다."
            )
        raise

    # 암호화 모드: 다운로드 데이터를 먼저 복호화
    if passphrase:
        key = derive_key(passphrase)
        try:
            data = decrypt_blob(data, key)
        except ValueError:
            raise

    try:
        manifest = json.loads(data)
    except json.JSONDecodeError:
        if passphrase:
            raise ValueError("복호화는 됐지만 매니페스트 형식이 아닙니다.")
        raise ValueError(
            "받은 데이터가 매니페스트가 아닙니다.\n"
            "(암호화된 데이터일 수 있습니다 — 코드 뒷부분(-XXXX)도 함께 입력하세요)"
        )

    if 'photos' not in manifest:
        raise ValueError("매니페스트 형식이 올바르지 않습니다.")
    photo_count = len(manifest.get('photos', []))
    if photo_count < 1 or photo_count > 20:
        raise ValueError(
            f"매니페스트의 사진 수가 비정상입니다 ({photo_count}장)."
        )

    manifest['encrypted'] = bool(passphrase)
    return manifest


def download_photo(url: str, dest: Path,
                   progress_cb: Callable[[int, int], None] = None,
                   passphrase: Optional[str] = None,
                   _key_cache: Optional[bytes] = None) -> Path:
    """사진 1장 다운로드 (진행률 콜백 + 선택적 복호화).

    thread-safe: urllib는 각 호출마다 새 connection을 만들므로 안전함.
    여러 스레드에서 동시 호출 가능.

    _key_cache: 키를 미리 유도해두고 넘기면 PBKDF2(10만회)를 매번 안 돌림
                (병렬 다운로드 시 유용)
    """
    download_url = normalize_url(url)
    req = urllib.request.Request(
        download_url,
        headers={
            'User-Agent': 'Mozilla/5.0 ReceiptInserter/1.0',
            'Accept-Encoding': 'gzip',  # 트래픽 절감 (서버가 지원하면)
        }
    )

    # 더 큰 청크 = 시스템 콜 줄여서 처리량 ↑ (특히 병렬 다운로드 시)
    CHUNK_SIZE = 64 * 1024
    with urllib.request.urlopen(req, timeout=60) as resp:
        total = int(resp.headers.get('Content-Length', 0))
        chunks = []
        downloaded = 0
        while True:
            chunk = resp.read(CHUNK_SIZE)
            if not chunk:
                break
            chunks.append(chunk)
            downloaded += len(chunk)
            if progress_cb and total > 0:
                progress_cb(downloaded, total)

    payload = b''.join(chunks)

    # 암호화 모드: 복호화 후 디스크에 평문으로 저장
    if passphrase:
        key = _key_cache if _key_cache is not None else derive_key(passphrase)
        payload = decrypt_blob(payload, key)

    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(payload)
    return dest


def is_valid_code(code: str) -> bool:
    """코드 형식 검증 (숫자 6-10자리, 옵션으로 -PASSPHRASE).

    "35541093"           → True
    "35541093-X7K2QM4P"  → True
    "abc"                → False
    """
    s = code.strip().upper().replace(' ', '')
    return bool(re.match(r'^\d{6,10}(?:-[A-Z2-9]{4,32})?$', s))
