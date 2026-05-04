"""
photo_zip_maker.py — 사진 여러 장을 300KB 이하로 압축한 뒤 ZIP으로 묶는 모듈.

GUI에서 호출:
    from photo_zip_maker import create_photo_zip
    result = create_photo_zip(image_paths, output_zip, progress_cb)
"""

from __future__ import annotations
import zipfile
import tempfile
import shutil
from pathlib import Path
from typing import Callable

from hwpx_inserter import compress_image


def create_photo_zip(image_paths: list[Path],
                     output_zip: Path,
                     progress_cb: Callable[[int, str], None] = None) -> dict:
    """
    이미지 여러 장을 각각 300KB 이하로 압축한 뒤 하나의 ZIP 파일로 묶음.
    
    파라미터:
        image_paths: 원본 이미지 경로 리스트 (1~20장)
        output_zip: 결과 .zip 파일 경로
        progress_cb: (퍼센트, 메시지) 콜백
    
    반환: {
        'photo_count': int,
        'total_size': int,           # 압축 후 총 크기
        'zip_size': int,
        'photos': [{name, original_size, compressed_size, dimensions}, ...]
    }
    """
    if not image_paths:
        raise ValueError("이미지가 1장 이상 필요합니다.")
    if len(image_paths) > 20:
        raise ValueError("이미지는 최대 20장까지 가능합니다.")
    
    def report(pct, msg):
        if progress_cb:
            progress_cb(pct, msg)
    
    # 임시 폴더에서 압축한 뒤 ZIP에 담기
    work_dir = Path(tempfile.mkdtemp(prefix="photo_zip_"))
    try:
        results = []
        compressed_files = []
        
        for i, src in enumerate(image_paths, start=1):
            pct = int((i - 1) / len(image_paths) * 80)
            report(pct, f"사진 {i}/{len(image_paths)} 압축 중...")
            
            # 출력 파일명: 영수증_01.jpg, 영수증_02.jpg, ...
            seq = str(i).zfill(2)
            out_name = f"사진_{seq}.jpg"
            out_path = work_dir / out_name
            
            original_size = src.stat().st_size
            info = compress_image(src, out_path)
            
            compressed_files.append((out_path, out_name))
            results.append({
                'name': out_name,
                'original_name': src.name,
                'original_size': original_size,
                'compressed_size': info['final_size'],
                'final_dimensions': info['final_dimensions'],
                'quality': info['quality_used'],
            })
        
        # ZIP으로 묶기
        report(85, "ZIP 파일 생성 중...")
        if output_zip.exists():
            output_zip.unlink()
        
        with zipfile.ZipFile(output_zip, 'w', zipfile.ZIP_DEFLATED) as zf:
            # README 텍스트도 함께
            readme = (
                "구매영수증 사진 삽입기에서 추출한 사진들입니다.\n\n"
                f"총 {len(results)}장 (각 사진 약 300KB 이하로 압축)\n"
                "원본 이미지의 EXIF 회전 정보가 적용되어 있습니다.\n\n"
                "제작: 평택소방서 김명주\n"
            )
            zf.writestr("README.txt", readme.encode('utf-8'))
            
            for fpath, arcname in compressed_files:
                zf.write(fpath, arcname)
        
        zip_size = output_zip.stat().st_size
        total_compressed = sum(r['compressed_size'] for r in results)
        
        report(100, "완료")
        return {
            'photo_count': len(results),
            'total_size': total_compressed,
            'zip_size': zip_size,
            'photos': results,
        }
    finally:
        # 임시 폴더 정리
        if work_dir.exists():
            shutil.rmtree(work_dir, ignore_errors=True)
