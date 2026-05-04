"""
main.py — 구매영수증 사진 삽입기 (PySide6 GUI)

두 가지 모드 지원:
1. 한글파일 생성 — 사진 3장을 .hwpx 표 셀에 비율 유지 삽입
2. 사진 ZIP — 사진 1~20장을 각 300KB 이하로 압축해 ZIP 저장

폰에서 받기 기능 공통 사용 가능.

제작: 평택소방서 김명주
"""

from __future__ import annotations
import sys
import traceback
from pathlib import Path

from PySide6.QtCore import Qt, Signal, QThread
from PySide6.QtGui import (
    QPixmap, QDragEnterEvent, QDropEvent, QIcon, QImage,
)
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QFileDialog, QMessageBox, QProgressBar,
    QFrame, QStatusBar, QRadioButton, QButtonGroup, QScrollArea,
    QDialog, QGridLayout,
)

from hwpx_inserter import insert_images
from photo_zip_maker import create_photo_zip
from phone_receive_dialog import PhoneReceiveDialog


APP_NAME = "구매영수증 사진 삽입기"
APP_VERSION = "v1.1"
APP_AUTHOR = "평택소방서 김명주"


def resource_path(rel: str) -> Path:
    if hasattr(sys, '_MEIPASS'):
        return Path(sys._MEIPASS) / rel
    return Path(__file__).parent / rel


TEMPLATE_PATH = resource_path('assets/template.hwpx')
ICON_PATH = resource_path('assets/icon.ico')
SUPPORTED_EXTS = {'.jpg', '.jpeg', '.png', '.bmp', '.gif', '.webp'}

PHONE_PAGE_URL = "https://kimmioungju-collab.github.io/receipt-phone-uploader/"

MODE_HWP = 'hwp'
MODE_ZIP = 'zip'
MAX_PHOTOS_ZIP = 20


# ─────────────────────────────────────────────────────────────────
# 이미지 슬롯
# ─────────────────────────────────────────────────────────────────
class ImageSlot(QFrame):
    image_changed = Signal()
    multi_files_dropped = Signal(list)
    
    def __init__(self, slot_label: str, parent=None):
        super().__init__(parent)
        self.slot_label = slot_label
        self.image_path: Path | None = None
        
        self.setAcceptDrops(True)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setMinimumSize(140, 140)
        self._update_style(empty=True)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(2)
        
        self.preview = QLabel()
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setMinimumHeight(100)
        self.preview.setText(f"📷\n{slot_label}")
        self.preview.setStyleSheet("color: #888; font-size: 11px; padding: 6px;")
        layout.addWidget(self.preview, 1)
        
        self.filename = QLabel("")
        self.filename.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.filename.setStyleSheet("color: #555; font-size: 10px;")
        self.filename.setWordWrap(True)
        layout.addWidget(self.filename)
        
        self.clear_btn = QPushButton("✕", self)
        self.clear_btn.setFixedSize(20, 20)
        self.clear_btn.setStyleSheet(
            "QPushButton { font-size: 11px; color: #c00; "
            "border: none; background: rgba(255,255,255,0.85); "
            "border-radius: 10px; }"
            "QPushButton:hover { background: #fee; }"
        )
        self.clear_btn.clicked.connect(self.clear_image)
        self.clear_btn.hide()
    
    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.clear_btn.move(self.width() - 24, 4)
    
    def _update_style(self, empty: bool, drag_over: bool = False):
        if drag_over:
            border, bg = "2px dashed #2563eb", "#eff6ff"
        elif empty:
            border, bg = "2px dashed #cbd5e1", "#fafafa"
        else:
            border, bg = "1px solid #94a3b8", "#ffffff"
        self.setStyleSheet(
            f"ImageSlot {{ border: {border}; "
            f"border-radius: 6px; background: {bg}; }}"
        )
    
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if self.clear_btn.isVisible() and self.clear_btn.geometry().contains(event.pos()):
                return
            self._open_file_dialog()
        super().mousePressEvent(event)
    
    def _open_file_dialog(self):
        exts = " ".join(f"*{e}" for e in SUPPORTED_EXTS)
        fname, _ = QFileDialog.getOpenFileName(
            self, f"{self.slot_label} 선택", "", f"이미지 ({exts})"
        )
        if fname:
            self.set_image(Path(fname))
    
    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            if any(self._is_image(u.toLocalFile()) for u in urls):
                event.acceptProposedAction()
                self._update_style(empty=self.image_path is None, drag_over=True)
    
    def dragLeaveEvent(self, event):
        self._update_style(empty=self.image_path is None)
    
    def dropEvent(self, event: QDropEvent):
        urls = event.mimeData().urls()
        image_paths = [Path(u.toLocalFile()) for u in urls
                       if self._is_image(u.toLocalFile())]
        if len(image_paths) == 1:
            self.set_image(image_paths[0])
            event.acceptProposedAction()
        elif len(image_paths) > 1:
            self.multi_files_dropped.emit(image_paths)
            event.acceptProposedAction()
        self._update_style(empty=self.image_path is None)
    
    @staticmethod
    def _is_image(path_str: str) -> bool:
        return Path(path_str).suffix.lower() in SUPPORTED_EXTS
    
    def set_image(self, path: Path):
        self.image_path = path
        pixmap = self._load_pixmap_with_exif(path)
        if pixmap and not pixmap.isNull():
            scaled = pixmap.scaled(
                self.preview.width() - 8, self.preview.height() - 8,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self.preview.setPixmap(scaled)
        self.filename.setText(path.name)
        self.clear_btn.show()
        self.clear_btn.raise_()
        self._update_style(empty=False)
        self.image_changed.emit()
    
    @staticmethod
    def _load_pixmap_with_exif(path: Path):
        try:
            from PIL import Image, ImageOps
            from io import BytesIO
            with Image.open(path) as img:
                fixed = ImageOps.exif_transpose(img)
                if fixed.mode not in ('RGB', 'RGBA'):
                    fixed = fixed.convert('RGB')
                buf = BytesIO()
                fixed.save(buf, format='PNG')
                buf.seek(0)
                qimg = QImage.fromData(buf.read(), 'PNG')
                return QPixmap.fromImage(qimg)
        except Exception:
            return QPixmap(str(path))
    
    def clear_image(self):
        self.image_path = None
        self.preview.clear()
        self.preview.setText(f"📷\n{self.slot_label}")
        self.filename.setText("")
        self.clear_btn.hide()
        self._update_style(empty=True)
        self.image_changed.emit()


# ─────────────────────────────────────────────────────────────────
# 워커 스레드
# ─────────────────────────────────────────────────────────────────
class HwpWorker(QThread):
    progress = Signal(int, str)
    finished_ok = Signal(dict)
    failed = Signal(str)
    
    def __init__(self, template, images, output):
        super().__init__()
        self.template, self.images, self.output = template, images, output
    
    def run(self):
        try:
            result = insert_images(
                self.template, self.images, self.output,
                progress_cb=lambda p, m: self.progress.emit(p, m),
            )
            self.finished_ok.emit(result)
        except Exception as e:
            # 사용자에겐 간결한 메시지만, 풀 traceback은 stderr로 (개발자 디버깅용)
            traceback.print_exc()
            self.failed.emit(f"{type(e).__name__}: {e}")


class ZipWorker(QThread):
    progress = Signal(int, str)
    finished_ok = Signal(dict)
    failed = Signal(str)
    
    def __init__(self, images, output):
        super().__init__()
        self.images, self.output = images, output
    
    def run(self):
        try:
            result = create_photo_zip(
                self.images, self.output,
                progress_cb=lambda p, m: self.progress.emit(p, m),
            )
            self.finished_ok.emit(result)
        except Exception as e:
            # 사용자에겐 간결한 메시지만, 풀 traceback은 stderr로 (개발자 디버깅용)
            traceback.print_exc()
            self.failed.emit(f"{type(e).__name__}: {e}")


# ─────────────────────────────────────────────────────────────────
# About 다이얼로그
# ─────────────────────────────────────────────────────────────────
class AboutDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("프로그램 정보")
        self.setFixedSize(360, 280)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(8)
        
        if ICON_PATH.exists():
            icon_label = QLabel()
            icon_label.setPixmap(QPixmap(str(ICON_PATH)).scaled(
                64, 64, Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            ))
            icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(icon_label)
        
        title = QLabel(APP_NAME)
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size: 16px; font-weight: bold;")
        layout.addWidget(title)
        
        version = QLabel(APP_VERSION)
        version.setAlignment(Qt.AlignmentFlag.AlignCenter)
        version.setStyleSheet("font-size: 12px; color: #64748b;")
        layout.addWidget(version)
        
        layout.addSpacing(8)
        
        author = QLabel(f"제작: {APP_AUTHOR}")
        author.setAlignment(Qt.AlignmentFlag.AlignCenter)
        author.setStyleSheet("font-size: 13px; color: #1e293b; font-weight: 500;")
        layout.addWidget(author)
        
        desc = QLabel(
            "차량 정비 비용 지급 건의용 한글파일 생성 +\n"
            "사진 일괄 압축(JPEG, 각 300KB 이하) ZIP 저장 도구"
        )
        desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        desc.setStyleSheet("font-size: 11px; color: #64748b; padding-top: 4px;")
        desc.setWordWrap(True)
        layout.addWidget(desc)
        
        layout.addStretch()
        
        ok_btn = QPushButton("확인")
        ok_btn.setFixedHeight(30)
        ok_btn.setMinimumWidth(80)
        ok_btn.clicked.connect(self.accept)
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_row.addWidget(ok_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)


# ─────────────────────────────────────────────────────────────────
# 메인 윈도우
# ─────────────────────────────────────────────────────────────────
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} {APP_VERSION}")
        self.setMinimumSize(820, 700)
        if ICON_PATH.exists():
            self.setWindowIcon(QIcon(str(ICON_PATH)))
        
        self.mode = MODE_HWP
        self.zip_slots: list[ImageSlot] = []
        self.worker = None
        
        self._build_ui()
        self._check_template()
    
    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(20, 14, 20, 14)
        layout.setSpacing(10)
        
        # 헤더
        header_row = QHBoxLayout()
        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        title = QLabel(APP_NAME)
        title.setStyleSheet("font-size: 18px; font-weight: bold; color: #1e293b;")
        title_box.addWidget(title)
        sub = QLabel(f"{APP_VERSION}  ·  제작: {APP_AUTHOR}")
        sub.setStyleSheet("color: #64748b; font-size: 11px;")
        title_box.addWidget(sub)
        header_row.addLayout(title_box)
        header_row.addStretch()
        
        self.about_btn = QPushButton("ⓘ")
        self.about_btn.setFixedSize(28, 28)
        self.about_btn.setStyleSheet(
            "QPushButton { font-size: 14px; color: #475569; "
            "border: 1px solid #e2e8f0; border-radius: 14px; background: white; }"
            "QPushButton:hover { background: #f1f5f9; }"
        )
        self.about_btn.setAutoDefault(False)
        self.about_btn.clicked.connect(lambda: AboutDialog(self).exec())
        header_row.addWidget(self.about_btn)
        layout.addLayout(header_row)
        
        # 모드 선택
        mode_box = QFrame()
        mode_box.setStyleSheet(
            "QFrame { background: #f8fafc; border: 1px solid #e2e8f0; "
            "border-radius: 6px; }"
        )
        mode_layout = QHBoxLayout(mode_box)
        mode_layout.setContentsMargins(12, 6, 12, 6)
        
        mode_label = QLabel("모드:")
        mode_label.setStyleSheet(
            "font-size: 12px; color: #475569; font-weight: 500; "
            "background: transparent; border: none;"
        )
        mode_layout.addWidget(mode_label)
        
        self.mode_group = QButtonGroup(self)
        self.rb_hwp = QRadioButton("📄 한글파일 생성 (3장)")
        self.rb_zip = QRadioButton(f"📦 사진만 ZIP (1~{MAX_PHOTOS_ZIP}장, 각 300KB)")
        self.rb_hwp.setChecked(True)
        for rb in (self.rb_hwp, self.rb_zip):
            rb.setStyleSheet(
                "QRadioButton { font-size: 12px; padding: 2px 8px; "
                "background: transparent; border: none; }"
            )
            rb.toggled.connect(self._on_mode_changed)
            self.mode_group.addButton(rb)
            mode_layout.addWidget(rb)
        mode_layout.addStretch()
        layout.addWidget(mode_box)
        
        # 액션 버튼들
        action_row = QHBoxLayout()
        action_row.addStretch()
        
        self.multi_select_btn = QPushButton("📂 사진 한번에 선택")
        self.multi_select_btn.setFixedHeight(32)
        self.multi_select_btn.setStyleSheet(
            "QPushButton { background: #f1f5f9; border: 1px solid #cbd5e1; "
            "border-radius: 4px; padding: 0 14px; font-size: 12px; }"
            "QPushButton:hover { background: #e2e8f0; }"
        )
        self.multi_select_btn.setAutoDefault(False)
        self.multi_select_btn.clicked.connect(self._on_multi_select)
        action_row.addWidget(self.multi_select_btn)
        
        self.phone_btn = QPushButton("📱 폰에서 받기")
        self.phone_btn.setFixedHeight(32)
        self.phone_btn.setStyleSheet(
            "QPushButton { background: #ecfdf5; border: 1px solid #86efac; "
            "color: #166534; border-radius: 4px; padding: 0 14px; font-size: 12px; }"
            "QPushButton:hover { background: #d1fae5; }"
        )
        self.phone_btn.setAutoDefault(False)
        self.phone_btn.clicked.connect(self._on_phone_upload)
        action_row.addWidget(self.phone_btn)
        action_row.addStretch()
        layout.addLayout(action_row)
        
        # HWP 모드 슬롯 (가로 3개)
        self.hwp_widget = QWidget()
        hwp_layout = QHBoxLayout(self.hwp_widget)
        hwp_layout.setContentsMargins(0, 0, 0, 0)
        hwp_layout.setSpacing(8)
        self.slot1 = ImageSlot("사진 1 (좌측 위)")
        self.slot2 = ImageSlot("사진 2 (우측 위)")
        self.slot3 = ImageSlot("사진 3 (아래 큰 칸)")
        for s in (self.slot1, self.slot2, self.slot3):
            hwp_layout.addWidget(s, 1)
            s.image_changed.connect(self._update_button_state)
            s.multi_files_dropped.connect(self._distribute_files)
        layout.addWidget(self.hwp_widget, 1)
        
        # ZIP 모드 슬롯 (그리드, 스크롤 가능)
        self.zip_widget = QScrollArea()
        self.zip_widget.setWidgetResizable(True)
        self.zip_widget.setStyleSheet(
            "QScrollArea { border: 1px solid #e2e8f0; border-radius: 6px; }"
        )
        zip_inner = QWidget()
        self.zip_grid = QGridLayout(zip_inner)
        self.zip_grid.setContentsMargins(8, 8, 8, 8)
        self.zip_grid.setSpacing(8)
        self.zip_widget.setWidget(zip_inner)
        layout.addWidget(self.zip_widget, 1)
        self.zip_widget.hide()
        
        cols = 5
        for i in range(MAX_PHOTOS_ZIP):
            slot = ImageSlot(f"사진 {i+1}")
            slot.setFixedSize(140, 140)
            slot.image_changed.connect(self._update_button_state)
            slot.multi_files_dropped.connect(self._distribute_files)
            row, col = divmod(i, cols)
            self.zip_grid.addWidget(slot, row, col)
            self.zip_slots.append(slot)
        
        # 진행률
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)
        
        # 하단 버튼
        bottom_row = QHBoxLayout()
        bottom_row.addStretch()
        
        self.clear_all_btn = QPushButton("전체 비우기")
        self.clear_all_btn.setFixedHeight(36)
        self.clear_all_btn.setAutoDefault(False)
        self.clear_all_btn.clicked.connect(self._clear_all)
        bottom_row.addWidget(self.clear_all_btn)
        
        self.generate_btn = QPushButton("한글파일 생성")
        self.generate_btn.setFixedHeight(36)
        self.generate_btn.setMinimumWidth(180)
        self.generate_btn.setStyleSheet(
            "QPushButton { background: #2563eb; color: white; "
            "font-weight: bold; border-radius: 4px; padding: 0 16px; }"
            "QPushButton:hover { background: #1d4ed8; }"
            "QPushButton:disabled { background: #94a3b8; }"
        )
        self.generate_btn.clicked.connect(self._on_generate)
        self.generate_btn.setEnabled(False)
        bottom_row.addWidget(self.generate_btn)
        layout.addLayout(bottom_row)
        
        self.setStatusBar(QStatusBar())
        self.statusBar().showMessage("사진 3장을 모두 추가하면 생성 가능")
    
    def _check_template(self):
        if not TEMPLATE_PATH.exists():
            QMessageBox.critical(
                self, "템플릿 없음",
                f"내장 템플릿 파일을 찾을 수 없습니다:\n{TEMPLATE_PATH}"
            )
    
    def _on_mode_changed(self, checked):
        if not checked:
            return
        self.mode = MODE_HWP if self.rb_hwp.isChecked() else MODE_ZIP
        if self.mode == MODE_HWP:
            self.hwp_widget.show()
            self.zip_widget.hide()
            self.generate_btn.setText("한글파일 생성")
        else:
            self.hwp_widget.hide()
            self.zip_widget.show()
            self.generate_btn.setText("ZIP으로 저장")
        self._update_button_state()
    
    def _current_slots(self) -> list[ImageSlot]:
        if self.mode == MODE_HWP:
            return [self.slot1, self.slot2, self.slot3]
        return self.zip_slots
    
    def _filled_paths(self) -> list[Path]:
        return [s.image_path for s in self._current_slots() if s.image_path]
    
    def _update_button_state(self):
        n = len(self._filled_paths())
        if self.mode == MODE_HWP:
            self.generate_btn.setEnabled(n == 3)
            self.statusBar().showMessage(
                "준비 완료 - [한글파일 생성] 클릭" if n == 3
                else f"사진 {n}/3 추가됨"
            )
        else:
            self.generate_btn.setEnabled(1 <= n <= MAX_PHOTOS_ZIP)
            self.statusBar().showMessage(
                "사진을 1장 이상 추가하세요" if n == 0
                else f"사진 {n}/{MAX_PHOTOS_ZIP}장 추가됨"
            )
    
    def _clear_all(self):
        for s in self._current_slots():
            s.clear_image()
    
    def _on_multi_select(self):
        exts = " ".join(f"*{e}" for e in SUPPORTED_EXTS)
        files, _ = QFileDialog.getOpenFileNames(
            self, "사진 선택", "", f"이미지 파일 ({exts})"
        )
        if not files:
            return
        self._distribute_files([Path(f) for f in files])
    
    def _distribute_files(self, files: list[Path]):
        slots = self._current_slots()
        max_count = len(slots)
        
        if len(files) > max_count:
            QMessageBox.information(
                self, "안내",
                f"{len(files)}장 선택됨 - 앞 {max_count}장만 사용합니다."
            )
            files = files[:max_count]
        
        if self.mode == MODE_HWP:
            for slot, fpath in zip(slots, files):
                slot.set_image(fpath)
        else:
            empty_slots = [s for s in slots if s.image_path is None]
            if not empty_slots:
                empty_slots = slots
            for slot, fpath in zip(empty_slots, files):
                slot.set_image(fpath)
    
    def _on_phone_upload(self):
        if "YOUR_GITHUB_ID" in PHONE_PAGE_URL:
            QMessageBox.warning(
                self, "URL 설정 필요",
                "main.py 의 PHONE_PAGE_URL을 GitHub Pages 주소로 교체하세요."
            )
            return
        dialog = PhoneReceiveDialog(self, PHONE_PAGE_URL)
        dialog.photo_ready.connect(self._on_phone_photo_received)
        dialog.exec()
    
    def _on_phone_photo_received(self, slot_num: int, local_path: Path):
        if self.mode == MODE_HWP:
            slots = {1: self.slot1, 2: self.slot2, 3: self.slot3}
            slot = slots.get(slot_num)
            if slot:
                slot.set_image(local_path)
                self.statusBar().showMessage(f"폰에서 사진 {slot_num} 받음")
            else:
                # 4장 이상은 한글 모드에선 사용 안 함
                self.statusBar().showMessage(
                    f"사진 {slot_num}은 한글 모드에서 사용 안 함 (3장까지만)"
                )
        else:
            if 1 <= slot_num <= MAX_PHOTOS_ZIP:
                self.zip_slots[slot_num - 1].set_image(local_path)
                self.statusBar().showMessage(f"폰에서 사진 {slot_num} 받음")
    
    def _on_generate(self):
        if self.mode == MODE_HWP:
            self._generate_hwp()
        else:
            self._generate_zip()
    
    def _generate_hwp(self):
        default = str(Path.home() / "Desktop" / "구매영수증.hwpx")
        out, _ = QFileDialog.getSaveFileName(
            self, "한글파일 저장", default, "한글 표준 문서 (*.hwpx)"
        )
        if not out:
            return
        out_path = Path(out)
        if out_path.suffix.lower() != '.hwpx':
            out_path = out_path.with_suffix('.hwpx')
        
        self._set_busy(True)
        self.worker = HwpWorker(TEMPLATE_PATH, self._filled_paths(), out_path)
        self.worker.progress.connect(self._on_progress)
        self.worker.finished_ok.connect(
            lambda r: self._on_hwp_finished(out_path, r)
        )
        self.worker.failed.connect(self._on_failed)
        self.worker.start()
    
    def _generate_zip(self):
        default = str(Path.home() / "Desktop" / "사진모음.zip")
        out, _ = QFileDialog.getSaveFileName(
            self, "ZIP 파일 저장", default, "ZIP (*.zip)"
        )
        if not out:
            return
        out_path = Path(out)
        if out_path.suffix.lower() != '.zip':
            out_path = out_path.with_suffix('.zip')
        
        self._set_busy(True)
        self.worker = ZipWorker(self._filled_paths(), out_path)
        self.worker.progress.connect(self._on_progress)
        self.worker.finished_ok.connect(
            lambda r: self._on_zip_finished(out_path, r)
        )
        self.worker.failed.connect(self._on_failed)
        self.worker.start()
    
    def _set_busy(self, busy: bool):
        n = len(self._filled_paths())
        ok = (n == 3) if self.mode == MODE_HWP else (1 <= n <= MAX_PHOTOS_ZIP)
        self.generate_btn.setEnabled(not busy and ok)
        for w in (self.clear_all_btn, self.multi_select_btn,
                  self.phone_btn, self.rb_hwp, self.rb_zip):
            w.setEnabled(not busy)
        for s in self._current_slots():
            s.setEnabled(not busy)
        self.progress_bar.setVisible(busy)
        self.progress_bar.setValue(0)
    
    def _on_progress(self, pct: int, msg: str):
        self.progress_bar.setValue(pct)
        self.statusBar().showMessage(msg)
    
    def _on_hwp_finished(self, out_path: Path, result: dict):
        self._set_busy(False)
        self.progress_bar.setValue(100)
        self._open_file(out_path)
        size_kb = out_path.stat().st_size / 1024
        self.statusBar().showMessage(f"완료 - {out_path.name} ({size_kb:.0f}KB)")
        QMessageBox.information(
            self, "완료",
            f"한글파일 생성 후 자동으로 열었습니다.\n\n"
            f"{out_path}\n파일 크기: {size_kb:.0f}KB"
        )
    
    def _on_zip_finished(self, out_path: Path, result: dict):
        self._set_busy(False)
        self.progress_bar.setValue(100)
        self._open_folder(out_path.parent)
        zip_kb = result['zip_size'] / 1024
        avg_kb = (result['total_size'] / result['photo_count']) / 1024
        self.statusBar().showMessage(f"완료 - {out_path.name} ({zip_kb:.0f}KB)")
        QMessageBox.information(
            self, "완료",
            f"ZIP 파일을 만들었습니다.\n\n"
            f"위치: {out_path}\n"
            f"사진 수: {result['photo_count']}장\n"
            f"평균 크기: {avg_kb:.0f}KB / 사진\n"
            f"ZIP 크기: {zip_kb:.0f}KB"
        )
    
    def _on_failed(self, error: str):
        self._set_busy(False)
        self.progress_bar.setVisible(False)
        QMessageBox.critical(self, "오류", f"파일 생성 중 오류:\n\n{error}")
        self.statusBar().showMessage("오류 발생")
    
    @staticmethod
    def _open_file(path: Path):
        import subprocess, platform, os
        try:
            if platform.system() == 'Windows':
                os.startfile(str(path))
            elif platform.system() == 'Darwin':
                subprocess.Popen(['open', str(path)])
            else:
                subprocess.Popen(['xdg-open', str(path)])
        except Exception:
            pass
    
    @staticmethod
    def _open_folder(path: Path):
        import subprocess, platform
        try:
            if platform.system() == 'Windows':
                subprocess.Popen(['explorer', str(path)])
            elif platform.system() == 'Darwin':
                subprocess.Popen(['open', str(path)])
            else:
                subprocess.Popen(['xdg-open', str(path)])
        except Exception:
            pass


def main():
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(APP_AUTHOR)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
