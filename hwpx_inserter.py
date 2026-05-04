"""
hwpx_inserter.py — .hwpx 표 셀에 이미지를 비율 유지하며 삽입하는 코어 모듈.

GUI에서 호출해서 쓸 수 있도록 비즈니스 로직만 담음.
"""

from __future__ import annotations
import shutil
import zipfile
import hashlib
import base64
import random
from pathlib import Path
from xml.etree import ElementTree as ET
from PIL import Image

NS = {
    'ha':   'http://www.hancom.co.kr/hwpml/2011/app',
    'hp':   'http://www.hancom.co.kr/hwpml/2011/paragraph',
    'hp10': 'http://www.hancom.co.kr/hwpml/2016/paragraph',
    'hh':   'http://www.hancom.co.kr/hwpml/2011/head',
    'hc':   'http://www.hancom.co.kr/hwpml/2011/core',
    'hs':   'http://www.hancom.co.kr/hwpml/2011/section',
    'opf':  'http://www.idpf.org/2007/opf/',
}
for prefix, uri in NS.items():
    ET.register_namespace(prefix, uri)

# 한컴 단위 변환
PX_TO_HWPUNIT = 75              # 96 DPI 기준 (7200/96)
HWPUNIT_PER_MM = 7200 / 25.4

# 가운데 정렬 paraPr ID — 구매영수증.hwpx 템플릿 기준
CENTER_ALIGN_PARA_ID = '19'


def px_to_hu(px: int) -> int:
    return px * PX_TO_HWPUNIT


def hu_to_mm(hu: int) -> float:
    return hu / HWPUNIT_PER_MM


def calc_fit_size(org_w: int, org_h: int,
                  cell_w: int, cell_h: int,
                  margin_ratio: float = 0.96) -> tuple[int, int]:
    """이미지 비율 유지하며 셀에 맞는 최대 크기 (HWPUNIT)."""
    avail_w = cell_w * margin_ratio
    avail_h = cell_h * margin_ratio
    scale = min(avail_w / org_w, avail_h / org_h)
    return int(org_w * scale), int(org_h * scale)


def make_hashkey(file_path: Path) -> str:
    """한컴 manifest의 hashkey (MD5의 base64)."""
    md5 = hashlib.md5(file_path.read_bytes()).digest()
    return base64.b64encode(md5).decode('ascii')


def compress_image(src: Path, dest: Path,
                   max_bytes: int = 300 * 1024,
                   max_dimension: int = 2000) -> dict:
    """
    이미지를 JPEG로 변환하여 저장 (300KB 이하 목표).
    
    1. EXIF Orientation을 실제 픽셀에 적용
    2. 해상도 다운스케일 (긴 변이 max_dimension 초과 시)
    3. quality 단계적으로 낮춰가며 max_bytes 이하로 압축
    
    반환: {'final_size', 'quality_used', 'final_dimensions', 'original_dimensions'}
    """
    from PIL import ImageOps
    from io import BytesIO
    
    with Image.open(src) as img:
        original_size = img.size
        
        # 1. EXIF 회전 적용
        fixed = ImageOps.exif_transpose(img)
        
        # 2. RGB로 변환 (JPEG는 RGB만 지원)
        if fixed.mode != 'RGB':
            fixed = fixed.convert('RGB')
        
        # 3. 해상도 다운스케일 (긴 변 기준)
        max_side = max(fixed.size)
        if max_side > max_dimension:
            scale = max_dimension / max_side
            new_w = int(fixed.size[0] * scale)
            new_h = int(fixed.size[1] * scale)
            fixed = fixed.resize((new_w, new_h), Image.LANCZOS)
        
        # 4. quality 단계적으로 낮춰가며 압축
        used_quality = 90
        size = 0
        for quality in (90, 80, 70, 60, 50, 40, 30):
            buf = BytesIO()
            fixed.save(buf, format='JPEG', quality=quality, optimize=True)
            size = buf.tell()
            used_quality = quality
            if size <= max_bytes:
                break
        else:
            # quality 30까지 내려도 큰 경우, 해상도 추가 축소
            while size > max_bytes and max(fixed.size) > 600:
                new_w = int(fixed.size[0] * 0.85)
                new_h = int(fixed.size[1] * 0.85)
                fixed = fixed.resize((new_w, new_h), Image.LANCZOS)
                buf = BytesIO()
                fixed.save(buf, format='JPEG', quality=70, optimize=True)
                size = buf.tell()
                used_quality = 70
        
        # 5. 디스크에 저장
        buf.seek(0)
        dest.write_bytes(buf.read())
        
        return {
            'final_size': size,
            'quality_used': used_quality,
            'final_dimensions': fixed.size,
            'original_dimensions': original_size,
        }


class HwpxImageInserter:
    """구매영수증.hwpx 템플릿에 이미지 3장을 비율 유지·가운데 정렬로 삽입."""
    
    # 헤더(0,0) 제외한 데이터 셀 좌표
    TARGET_CELLS = [(1, 0), (1, 1), (2, 0)]
    
    def __init__(self, template: Path, output: Path):
        self.template = Path(template)
        self.output = Path(output)
        self.work = self.output.parent / f"_work_{self.output.stem}"
    
    def __enter__(self):
        if self.work.exists():
            shutil.rmtree(self.work)
        self.work.mkdir(parents=True)
        with zipfile.ZipFile(self.template, 'r') as zf:
            zf.extractall(self.work)
        
        self.section_path = self.work / 'Contents/section0.xml'
        self.hpf_path     = self.work / 'Contents/content.hpf'
        self.bindata_dir  = self.work / 'BinData'
        self.bindata_dir.mkdir(exist_ok=True)
        return self
    
    def __exit__(self, *_):
        if self.output.exists():
            self.output.unlink()
        with zipfile.ZipFile(self.output, 'w', zipfile.ZIP_DEFLATED) as zf:
            mt = self.work / 'mimetype'
            if mt.exists():
                zf.write(mt, 'mimetype', zipfile.ZIP_STORED)
            for p in sorted(self.work.rglob('*')):
                if p.is_file() and p.name != 'mimetype':
                    arc = p.relative_to(self.work).as_posix()
                    zf.write(p, arc)
        shutil.rmtree(self.work)
    
    def collect_target_cells(self):
        tree = ET.parse(self.section_path)
        root = tree.getroot()
        tbl = root.find('.//hp:tbl', NS)
        if tbl is None:
            raise RuntimeError("표를 찾을 수 없습니다.")
        
        cell_map = {}
        for tr in tbl.findall('hp:tr', NS):
            for tc in tr.findall('hp:tc', NS):
                addr = tc.find('hp:cellAddr', NS)
                cell_map[(int(addr.get('rowAddr')),
                          int(addr.get('colAddr')))] = tc
        
        targets = []
        for (row, col) in self.TARGET_CELLS:
            tc = cell_map.get((row, col))
            if tc is None:
                raise RuntimeError(f"셀({row},{col}) 없음")
            sz = tc.find('hp:cellSz', NS)
            mg = tc.find('hp:cellMargin', NS)
            w, h = int(sz.get('width')), int(sz.get('height'))
            ml = int(mg.get('left', 0) or 0)
            mr = int(mg.get('right', 0) or 0)
            mt = int(mg.get('top', 0) or 0)
            mb = int(mg.get('bottom', 0) or 0)
            targets.append({
                'element': tc, 'row': row, 'col': col,
                'inner_w': w - ml - mr, 'inner_h': h - mt - mb,
            })
        return targets, tree
    
    def add_binary_files(self, image_paths: list[Path]) -> list[dict]:
        result = []
        for i, img in enumerate(image_paths, start=1):
            # 모든 이미지를 JPEG로 통일 (압축 효율 + 한컴 호환성)
            ext = 'jpg'
            bin_name = f"image{i}.{ext}"
            target_path = self.bindata_dir / bin_name
            
            # EXIF 회전 적용 + 300KB 이하로 압축하여 JPEG로 저장
            self._normalize_and_save(img, target_path)
            
            with Image.open(target_path) as pim:
                px_w, px_h = pim.size
            
            result.append({
                'src_path':  img,
                'bin_path':  target_path,
                'bin_name':  bin_name,
                'item_id':   f'image{i}',
                'ext':       ext,
                'mime':      'image/jpg',
                'px_w':      px_w, 'px_h': px_h,
                'org_w_hu':  px_to_hu(px_w),
                'org_h_hu':  px_to_hu(px_h),
            })
        return result
    
    @staticmethod
    def _normalize_and_save(src: Path, dest: Path,
                             max_bytes: int = 300 * 1024,
                             max_dimension: int = 2000):
        """모듈 함수 compress_image의 wrapper."""
        compress_image(src, dest, max_bytes, max_dimension)
    
    def register_in_hpf(self, bin_files: list[dict]):
        tree = ET.parse(self.hpf_path)
        manifest = tree.getroot().find('opf:manifest', NS)
        for bf in bin_files:
            item = ET.SubElement(manifest, f'{{{NS["opf"]}}}item')
            item.set('id', bf['item_id'])
            item.set('href', f'BinData/{bf["bin_name"]}')
            item.set('media-type', bf['mime'])
            item.set('isEmbeded', '1')
            item.set('hashkey', make_hashkey(bf['bin_path']))
        tree.write(self.hpf_path, xml_declaration=True, encoding='UTF-8')
    
    def create_pic_element(self, pic_id: int, instid: int,
                           bf: dict, cur_w: int, cur_h: int,
                           shape_comment: str) -> ET.Element:
        hp, hc = NS['hp'], NS['hc']
        org_w, org_h = bf['org_w_hu'], bf['org_h_hu']
        scale_x, scale_y = cur_w / org_w, cur_h / org_h
        
        pic = ET.Element(f'{{{hp}}}pic')
        for k, v in [
            ('id', str(pic_id)), ('zOrder', '0'),
            ('numberingType', 'PICTURE'), ('textWrap', 'SQUARE'),
            ('textFlow', 'BOTH_SIDES'), ('lock', '0'),
            ('dropcapstyle', 'None'), ('href', ''),
            ('groupLevel', '0'), ('instid', str(instid)),
            ('reverse', '0'),
        ]:
            pic.set(k, v)
        
        ET.SubElement(pic, f'{{{hp}}}offset', {'x': '0', 'y': '0'})
        ET.SubElement(pic, f'{{{hp}}}orgSz',
                      {'width': str(org_w), 'height': str(org_h)})
        ET.SubElement(pic, f'{{{hp}}}curSz',
                      {'width': str(cur_w), 'height': str(cur_h)})
        ET.SubElement(pic, f'{{{hp}}}flip',
                      {'horizontal': '0', 'vertical': '0'})
        ET.SubElement(pic, f'{{{hp}}}rotationInfo', {
            'angle': '0',
            'centerX': str(cur_w // 2), 'centerY': str(cur_h // 2),
            'rotateimage': '1',
        })
        
        rend = ET.SubElement(pic, f'{{{hp}}}renderingInfo')
        for tag, m in [
            ('transMatrix', (1, 0, 0, 0, 1, 0)),
            ('scaMatrix',   (scale_x, 0, 0, 0, scale_y, 0)),
            ('rotMatrix',   (1, 0, 0, 0, 1, 0)),
        ]:
            mat = ET.SubElement(rend, f'{{{hc}}}{tag}')
            for i, v in enumerate(m, start=1):
                mat.set(f'e{i}',
                        f'{v:g}' if isinstance(v, float) else str(v))
        
        ET.SubElement(pic, f'{{{hc}}}img', {
            'binaryItemIDRef': bf['item_id'],
            'bright': '0', 'contrast': '0',
            'effect': 'REAL_PIC', 'alpha': '0',
        })
        
        rect = ET.SubElement(pic, f'{{{hp}}}imgRect')
        for i, (x, y) in enumerate([
            (0, 0), (org_w, 0), (org_w, org_h), (0, org_h)
        ]):
            ET.SubElement(rect, f'{{{hc}}}pt{i}',
                          {'x': str(x), 'y': str(y)})
        
        ET.SubElement(pic, f'{{{hp}}}imgClip', {
            'left': '0', 'right': str(org_w),
            'top': '0', 'bottom': str(org_h),
        })
        ET.SubElement(pic, f'{{{hp}}}inMargin',
                      {'left': '0', 'right': '0',
                       'top': '0', 'bottom': '0'})
        ET.SubElement(pic, f'{{{hp}}}imgDim',
                      {'dimwidth': str(org_w),
                       'dimheight': str(org_h)})
        ET.SubElement(pic, f'{{{hp}}}effects')
        
        ET.SubElement(pic, f'{{{hp}}}sz', {
            'width': str(cur_w), 'widthRelTo': 'ABSOLUTE',
            'height': str(cur_h), 'heightRelTo': 'ABSOLUTE',
            'protect': '0',
        })
        ET.SubElement(pic, f'{{{hp}}}pos', {
            'treatAsChar': '1', 'affectLSpacing': '0',
            'flowWithText': '1', 'allowOverlap': '0',
            'holdAnchorAndSO': '0',
            'vertRelTo': 'PARA', 'horzRelTo': 'PARA',
            'vertAlign': 'TOP', 'horzAlign': 'LEFT',
            'vertOffset': '0', 'horzOffset': '0',
        })
        ET.SubElement(pic, f'{{{hp}}}outMargin',
                      {'left': '0', 'right': '0',
                       'top': '0', 'bottom': '0'})
        
        sc = ET.SubElement(pic, f'{{{hp}}}shapeComment')
        sc.text = shape_comment
        return pic
    
    def insert_into_cell(self, cell: dict, bf: dict,
                         pic_id: int, instid: int):
        tc = cell['element']
        sub_list = tc.find('hp:subList', NS)
        p = sub_list.find('hp:p', NS)
        if p is None:
            raise RuntimeError(f"셀 ({cell['row']},{cell['col']}) 단락 없음")
        
        # 가로/세로 가운데 정렬
        p.set('paraPrIDRef', CENTER_ALIGN_PARA_ID)
        sub_list.set('vertAlign', 'CENTER')
        
        cur_w, cur_h = calc_fit_size(
            bf['org_w_hu'], bf['org_h_hu'],
            cell['inner_w'], cell['inner_h'],
        )
        
        shape_comment = (
            f"그림입니다.\n"
            f"원본 그림의 이름: {bf['src_path'].name}\n"
            f"원본 그림의 크기: 가로 {bf['px_w']}pixel, "
            f"세로 {bf['px_h']}pixel"
        )
        
        run = p.find('hp:run', NS)
        if run is None:
            run = ET.SubElement(p, f'{{{NS["hp"]}}}run')
            run.set('charPrIDRef', '0')
        
        pic = self.create_pic_element(
            pic_id, instid, bf, cur_w, cur_h, shape_comment
        )
        run.append(pic)
        ET.SubElement(run, f'{{{NS["hp"]}}}t')
        
        return cur_w, cur_h
    
    def process(self, image_paths: list[Path],
                progress_cb=None) -> dict:
        """
        이미지 3장을 템플릿에 삽입.
        progress_cb: 진행률 콜백 (0~100, 메시지)
        반환: 삽입 결과 dict
        """
        def report(pct, msg):
            if progress_cb:
                progress_cb(pct, msg)
        
        if len(image_paths) != 3:
            raise ValueError("이미지는 정확히 3장이어야 합니다.")
        
        report(10, "표 셀 분석 중...")
        cells, section_tree = self.collect_target_cells()
        
        report(30, "이미지 파일 복사 중...")
        bin_files = self.add_binary_files(image_paths)
        
        report(50, "메타데이터 등록 중...")
        self.register_in_hpf(bin_files)
        
        report(70, "셀에 그림 삽입 중...")
        pic_id_base = 1074270550
        instid_base = random.randint(500000, 600000)
        
        results = []
        for i, (cell, bf) in enumerate(zip(cells, bin_files)):
            cw, ch = self.insert_into_cell(
                cell, bf,
                pic_id=pic_id_base + i,
                instid=instid_base + i,
            )
            results.append({
                'cell': (cell['row'], cell['col']),
                'image': bf['src_path'].name,
                'size_mm': (hu_to_mm(cw), hu_to_mm(ch)),
            })
        
        report(90, "파일 저장 중...")
        section_tree.write(
            self.section_path, xml_declaration=True, encoding='UTF-8'
        )
        
        report(100, "완료")
        return {'cells': results}


def insert_images(template: Path, images: list[Path],
                  output: Path, progress_cb=None) -> dict:
    """간편 함수 - GUI에서 한 줄로 호출."""
    with HwpxImageInserter(template, output) as ins:
        return ins.process(images, progress_cb)
