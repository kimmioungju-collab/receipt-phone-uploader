"""
tmpfiles_client.py — tmpfiles.org에서 매니페스트와 사진을 다운로드.

폰에서 사진 3장을 업로드하면 그 URL들을 묶은 manifest.json도 함께 업로드되고,
manifest의 URL에서 추출한 코드(예: "35541093")만 PC에 입력하면
이 코드로 매니페스트와 사진들을 모두 다운로드한다.

tmpfiles.org URL 구조:
    http://tmpfiles.org/35541093/test.json    ← 폰이 받은 URL
    http://tmpfiles.org/dl/35541093/test.json ← 직접 다운로드 URL
"""

from __future__ import annotations
import json
import urllib.request
import urllib.parse
import urllib.error
import re
from pathlib import Path
from typing import Callable


def code_to_manifest_url(code: str, filename: str = "manifest.json") -> str:
    """코드 → 매니페스트 다운로드 URL."""
    return f"http://tmpfiles.org/dl/{code.strip()}/{filename}"


def normalize_url(url: str) -> str:
    """tmpfiles.org URL을 dl 형식으로 변환.
    
    http://tmpfiles.org/35541093/photo.jpg
    → http://tmpfiles.org/dl/35541093/photo.jpg
    """
    # 이미 /dl/ 들어있으면 그대로
    if '/dl/' in url:
        return url
    return url.replace('tmpfiles.org/', 'tmpfiles.org/dl/', 1)


def download_bytes(url: str, timeout: int = 30) -> bytes:
    """URL에서 바이너리 다운로드."""
    req = urllib.request.Request(
        url, headers={'User-Agent': 'Mozilla/5.0 ReceiptInserter/1.0'}
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def fetch_manifest(code: str) -> dict:
    """코드로 매니페스트 JSON 다운로드.
    
    반환: {
      "createdAt": "2026-04-28T...",
      "photos": [
        {"slot": 1, "url": "...", "originalName": "..."},
        ...
      ]
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
    
    try:
        manifest = json.loads(data)
    except json.JSONDecodeError:
        raise ValueError(f"받은 데이터가 매니페스트가 아닙니다.")
    
    if 'photos' not in manifest:
        raise ValueError("매니페스트 형식이 올바르지 않습니다.")
    photo_count = len(manifest.get('photos', []))
    if photo_count < 1 or photo_count > 20:
        raise ValueError(
            f"매니페스트의 사진 수가 비정상입니다 ({photo_count}장)."
        )
    
    return manifest


def download_photo(url: str, dest: Path,
                   progress_cb: Callable[[int, int], None] = None) -> Path:
    """사진 1장 다운로드 (진행률 콜백 지원)."""
    download_url = normalize_url(url)
    req = urllib.request.Request(
        download_url,
        headers={'User-Agent': 'Mozilla/5.0 ReceiptInserter/1.0'}
    )
    
    with urllib.request.urlopen(req, timeout=60) as resp:
        total = int(resp.headers.get('Content-Length', 0))
        chunks = []
        downloaded = 0
        while True:
            chunk = resp.read(8192)
            if not chunk:
                break
            chunks.append(chunk)
            downloaded += len(chunk)
            if progress_cb and total > 0:
                progress_cb(downloaded, total)
    
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(b''.join(chunks))
    return dest


def is_valid_code(code: str) -> bool:
    """tmpfiles.org 코드 형식 검증 (숫자 6-10자리)."""
    return bool(re.match(r'^\d{6,10}$', code.strip()))
