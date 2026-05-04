"""
phone_receive_dialog.py — 폰에서 받은 코드를 입력해서 사진 받기.

흐름:
1. 폰 페이지 URL의 QR코드 표시 (헴이 폰에서 스캔)
2. 폰에서 사진 업로드 끝나면 6-10자리 숫자 코드를 보여줌
3. 헴이 그 코드를 PC에 입력
4. PC가 매니페스트 + 사진 3장 다운로드 → 슬롯에 자동 채움
"""

from __future__ import annotations
import shutil
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from io import BytesIO

from PySide6.QtCore import Qt, Signal, QThread
from PySide6.QtGui import QPixmap, QImage, QFont, QClipboard
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QMessageBox, QApplication, QFrame, QLineEdit, QProgressBar,
)

import qrcode

from tmpfiles_client import (
    fetch_manifest, download_photo, is_valid_code, parse_code, derive_key,
)


class DownloadWorker(QThread):
    """매니페스트 + 사진 3장 다운로드를 백그라운드로."""
    
    progress = Signal(int, str)   # 0~100, 메시지
    photo_ready = Signal(int, Path, str)  # slot_num, local_path, original_name
    finished_ok = Signal()
    failed = Signal(str)
    
    def __init__(self, code: str, dest_dir: Path, passphrase: str | None = None):
        super().__init__()
        self.code = code
        self.dest_dir = dest_dir
        self.passphrase = passphrase  # None이면 평문 모드(레거시)
        self._key_cache: bytes | None = None  # PBKDF2 결과 캐싱 (병렬 호출 최적화)

    # 동시 다운로드 워커 수 (매니페스트의 사진 수까지만 사용)
    MAX_PARALLEL = 4

    def _download_one(self, photo: dict, index: int) -> tuple[int, Path, str]:
        """사진 1장 다운로드 + 복호화 (스레드 풀에서 병렬 호출됨)."""
        slot_num = photo.get('slot', index + 1)
        url = photo['url']
        original_name = photo.get('originalName', f'photo{slot_num}.jpg')

        ext = '.jpg'
        if '.' in original_name:
            ext = '.' + original_name.rsplit('.', 1)[-1].lower()

        local_path = self.dest_dir / f"phone_slot{slot_num}{ext}"
        # download_photo는 thread-safe — 각 스레드가 자체 urlopen 사용
        # _key_cache 전달 → PBKDF2(10만회) 재계산 회피 (이미 유도해둔 키 재사용)
        download_photo(
            url, local_path,
            passphrase=self.passphrase,
            _key_cache=self._key_cache,
        )
        return slot_num, local_path, original_name

    def run(self):
        try:
            mode_str = "🔒 암호화" if self.passphrase else "평문(레거시)"
            self.progress.emit(5, f"매니페스트 다운로드 중... [{mode_str}]")
            manifest = fetch_manifest(self.code, self.passphrase)
            photos = manifest['photos']

            # 암호화 모드: 키를 한 번만 유도해 모든 다운로드 스레드에서 공유
            # (PBKDF2 10만회 = 약 100~300ms — 매번 하면 누적 비용 큼)
            if self.passphrase:
                self._key_cache = derive_key(self.passphrase)
            total = len(photos)
            if total == 0:
                self.progress.emit(100, "완료 (사진 없음)")
                self.finished_ok.emit()
                return

            action = "복호화" if self.passphrase else "다운로드"
            workers = min(self.MAX_PARALLEL, total)
            self.progress.emit(
                10,
                f"사진 {total}장 병렬 {action} 시작 ({workers}개 동시)..."
            )

            # 스레드 풀로 병렬 다운로드 — 워커 수 = min(MAX_PARALLEL, photo 수)
            done_lock = threading.Lock()
            done_count = [0]  # nonlocal counter (mutable)

            with ThreadPoolExecutor(
                max_workers=workers,
                thread_name_prefix='phone-dl'
            ) as executor:
                futures = {
                    executor.submit(self._download_one, p, i): (p, i)
                    for i, p in enumerate(photos)
                }

                for fut in as_completed(futures):
                    photo, idx = futures[fut]
                    slot_num = photo.get('slot', idx + 1)
                    try:
                        slot_num, local_path, original_name = fut.result()
                    except Exception as e:
                        # 1장이라도 실패하면 나머지 취소
                        for f in futures:
                            f.cancel()
                        raise RuntimeError(
                            f"사진 {slot_num} {action} 실패: {e}"
                        ) from e

                    # 슬롯 채우기 (UI 업데이트 — Signal은 thread-safe)
                    self.photo_ready.emit(slot_num, local_path, original_name)

                    # 진행률 업데이트
                    with done_lock:
                        done_count[0] += 1
                        completed = done_count[0]
                    pct = 10 + int((completed / total) * 85)
                    self.progress.emit(
                        pct,
                        f"사진 {action} 중... ({completed}/{total} 완료)"
                    )

            self.progress.emit(100, "완료")
            self.finished_ok.emit()
        except Exception as e:
            self.failed.emit(str(e))


class PhoneReceiveDialog(QDialog):
    """폰에서 받기 다이얼로그."""
    
    photo_ready = Signal(int, Path)  # slot_num, local_path (메인에 전달)
    
    def __init__(self, parent, phone_page_url: str):
        super().__init__(parent)
        self.phone_page_url = phone_page_url
        self.download_dir = Path(tempfile.mkdtemp(prefix="receipt_phone_"))
        self.worker: DownloadWorker | None = None
        
        self._build_ui()
    
    def _build_ui(self):
        self.setWindowTitle("📱 폰에서 사진 받기")
        self.setMinimumSize(420, 640)
        self.setModal(True)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 18, 24, 18)
        layout.setSpacing(10)
        
        # ── 1단계 안내 ──
        step1 = QLabel("1️⃣  폰에서 QR코드 스캔 또는 주소 입력")
        step1.setStyleSheet("font-size: 13px; font-weight: 600; color: #1e293b;")
        layout.addWidget(step1)
        
        # QR 코드
        qr_label = QLabel()
        qr_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        qr_pixmap = self._make_qr_pixmap(self.phone_page_url, size=200)
        qr_label.setPixmap(qr_pixmap)
        qr_label.setStyleSheet(
            "background: white; border: 1px solid #e2e8f0; "
            "border-radius: 8px; padding: 8px;"
        )
        layout.addWidget(qr_label, 0, Qt.AlignmentFlag.AlignCenter)
        
        # URL + 복사 버튼
        url_row = QHBoxLayout()
        url_row.setSpacing(6)
        url_label = QLabel(self.phone_page_url)
        url_label.setStyleSheet(
            "font-size: 11px; color: #475569; "
            "background: #f8fafc; border: 1px solid #e2e8f0; "
            "border-radius: 4px; padding: 6px 10px;"
        )
        url_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        url_row.addWidget(url_label, 1)
        copy_btn = QPushButton("복사")
        copy_btn.setFixedSize(50, 26)
        copy_btn.setAutoDefault(False)
        copy_btn.clicked.connect(self._copy_url)
        url_row.addWidget(copy_btn)
        layout.addLayout(url_row)
        
        # ── 구분선 ──
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet("background: #e2e8f0;")
        line.setFixedHeight(1)
        layout.addWidget(line)
        
        # ── 2단계 ──
        step2 = QLabel("2️⃣  폰에서 받은 코드 입력")
        step2.setStyleSheet(
            "font-size: 13px; font-weight: 600; color: #1e293b; margin-top: 4px;"
        )
        layout.addWidget(step2)
        
        hint = QLabel("폰에서 사진 업로드 완료 후 표시되는 숫자 코드를 입력하세요.")
        hint.setStyleSheet("font-size: 11px; color: #64748b;")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        
        # 코드 입력
        code_row = QHBoxLayout()
        code_row.setSpacing(8)
        
        self.code_input = QLineEdit()
        self.code_input.setPlaceholderText("예: 35541093-X7K2QM4P (또는 평문 모드: 35541093)")
        self.code_input.setStyleSheet(
            "QLineEdit { font-size: 22px; font-weight: bold; "
            "padding: 10px 14px; border: 2px solid #cbd5e1; "
            "border-radius: 6px; letter-spacing: 3px; "
            "font-family: 'Courier New', monospace; }"
            "QLineEdit:focus { border-color: #2563eb; }"
        )
        self.code_input.setMaxLength(48)  # 숫자(10) + 하이픈 + passphrase(최대 32) + 여유
        self.code_input.textChanged.connect(self._on_code_changed)
        self.code_input.returnPressed.connect(self._on_receive_clicked)
        code_row.addWidget(self.code_input, 1)
        
        self.receive_btn = QPushButton("받기")
        self.receive_btn.setFixedHeight(48)
        self.receive_btn.setMinimumWidth(80)
        self.receive_btn.setStyleSheet(
            "QPushButton { background: #2563eb; color: white; "
            "font-weight: bold; font-size: 14px; border: none; "
            "border-radius: 6px; }"
            "QPushButton:hover { background: #1d4ed8; }"
            "QPushButton:disabled { background: #94a3b8; }"
        )
        self.receive_btn.setEnabled(False)
        self.receive_btn.setDefault(True)         # 엔터 눌렀을 때 이 버튼이 동작
        self.receive_btn.setAutoDefault(True)
        self.receive_btn.clicked.connect(self._on_receive_clicked)
        code_row.addWidget(self.receive_btn)
        layout.addLayout(code_row)
        
        # 진행률 바
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setVisible(False)
        self.progress.setStyleSheet(
            "QProgressBar { height: 18px; border-radius: 4px; "
            "background: #f1f5f9; text-align: center; font-size: 11px; }"
            "QProgressBar::chunk { background: #2563eb; border-radius: 4px; }"
        )
        layout.addWidget(self.progress)
        
        self.status_label = QLabel("")
        self.status_label.setStyleSheet("font-size: 11px; color: #475569;")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)
        
        layout.addStretch()
        
        # 닫기 버튼
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self.close_btn = QPushButton("닫기")
        self.close_btn.setFixedHeight(32)
        self.close_btn.setMinimumWidth(90)
        self.close_btn.setDefault(False)          # 엔터에 반응하지 않게
        self.close_btn.setAutoDefault(False)
        self.close_btn.clicked.connect(self.reject)
        btn_row.addWidget(self.close_btn)
        layout.addLayout(btn_row)
    
    def _make_qr_pixmap(self, url: str, size: int = 200) -> QPixmap:
        qr = qrcode.QRCode(
            version=None,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=10,
            border=2,
        )
        qr.add_data(url)
        qr.make(fit=True)
        pil_img = qr.make_image(fill_color="black", back_color="white")
        buf = BytesIO()
        pil_img.save(buf, format='PNG')
        buf.seek(0)
        qimg = QImage.fromData(buf.read(), 'PNG')
        return QPixmap.fromImage(qimg).scaled(
            size, size,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
    
    def _copy_url(self):
        QApplication.clipboard().setText(self.phone_page_url)
        self.status_label.setText("주소가 복사되었습니다")
    
    def _on_code_changed(self, text: str):
        # 허용 문자만 남기기 (숫자, A-Z, 하이픈)
        allowed = ''.join(
            c for c in text.upper()
            if c.isdigit() or ('A' <= c <= 'Z') or c == '-'
        )
        if allowed != text:
            self.code_input.setText(allowed)
            return

        valid = is_valid_code(text)
        self.receive_btn.setEnabled(valid)

    def _on_receive_clicked(self):
        raw = self.code_input.text().strip()
        if not is_valid_code(raw):
            QMessageBox.warning(self, "코드 오류", "올바른 코드 형식이 아닙니다.")
            return

        # 코드 파싱: tmp_code + (옵션) passphrase
        try:
            tmp_code, passphrase = parse_code(raw)
        except ValueError as e:
            QMessageBox.warning(self, "코드 오류", str(e))
            return

        # UI 잠금
        self.code_input.setEnabled(False)
        self.receive_btn.setEnabled(False)
        self.progress.setVisible(True)
        self.progress.setValue(0)

        # 백그라운드 시작
        self.worker = DownloadWorker(tmp_code, self.download_dir, passphrase)
        self.worker.progress.connect(self._on_progress)
        self.worker.photo_ready.connect(self._on_photo_ready)
        self.worker.finished_ok.connect(self._on_finished)
        self.worker.failed.connect(self._on_failed)
        self.worker.start()
    
    def _on_progress(self, pct: int, msg: str):
        self.progress.setValue(pct)
        self.status_label.setText(msg)
    
    def _on_photo_ready(self, slot_num: int, local_path: Path, original_name: str):
        # 메인 윈도우에 전달
        self._received_count = getattr(self, '_received_count', 0) + 1
        self.photo_ready.emit(slot_num, local_path)
    
    def _on_finished(self):
        self.status_label.setText(f"✅ 사진 {self._received_count}장을 모두 받았습니다.")
        # 약간 지연 후 자동 닫기
        from PySide6.QtCore import QTimer
        QTimer.singleShot(800, self.accept)
    
    def _on_failed(self, error: str):
        self.code_input.setEnabled(True)
        self.receive_btn.setEnabled(True)
        self.progress.setVisible(False)
        self.status_label.setText("")
        QMessageBox.warning(self, "다운로드 실패", error)
    
    def _stop_worker_safely(self):
        """워커 안전 종료. terminate() 대신 quit()+wait() 사용 (자원 누수 방지)."""
        if self.worker and self.worker.isRunning():
            self.worker.quit()
            if not self.worker.wait(2000):
                # 정상 종료 실패 시에만 강제 종료
                self.worker.terminate()
                self.worker.wait(1000)

    def _cleanup_download_dir(self):
        """다운로드 임시 폴더 정리 (디스크 누수 방지)."""
        try:
            if self.download_dir and self.download_dir.exists():
                shutil.rmtree(self.download_dir, ignore_errors=True)
        except Exception:
            pass

    def reject(self):
        self._stop_worker_safely()
        # 취소 시 받은 사진은 메인이 아직 못 가져갔을 수 있으므로 폴더 유지
        # (메인 윈도우가 photo_ready로 받은 파일은 이미 자기 임시폴더로 옮긴 상태)
        super().reject()

    def accept(self):
        if self.worker and self.worker.isRunning():
            self.worker.wait(2000)
        super().accept()

    def closeEvent(self, event):
        self._stop_worker_safely()
        super().closeEvent(event)
