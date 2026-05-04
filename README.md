# 구매영수증 사진 삽입기

평택소방서 차량 정비 비용 지급 건의 공문서용 - 사진 3장을 .hwpx 표 셀에 비율 유지하며 자동 삽입.

## 주요 기능

- **드래그앤드롭** + 파일 선택 + **다중 선택(Shift/Ctrl)** 지원
- **📱 폰에서 받기**: QR로 폰 페이지 열기 → 폰에서 사진 업로드 → 코드로 PC 받기
- 비율 유지하며 셀 가운데 정렬로 자동 배치
- 저장 후 한글 자동 실행

## 폴더 구조

```
receipt_inserter/
├─ assets/
│   ├─ template.hwpx              # 빈 구매영수증 템플릿 (내장)
│   └─ icon.ico                    # 앱 아이콘
├─ phone_page/
│   └─ index.html                  # 폰용 업로드 페이지 (GitHub Pages에 올릴 것)
├─ hwpx_inserter.py                 # .hwpx 처리 코어
├─ tmpfiles_client.py               # tmpfiles.org API 클라이언트
├─ phone_receive_dialog.py          # 폰에서 받기 다이얼로그
├─ main.py                          # PySide6 GUI 메인
├─ build.spec / build.bat / .sh
├─ requirements.txt
├─ PHONE_PAGE_SETUP.md              # GitHub Pages 셋업 가이드 ⭐
└─ README.md
```

## 처음 한 번 셋업

폰에서 받기 기능을 쓰려면 GitHub Pages에 폰 페이지를 올려야 합니다.

→ **PHONE_PAGE_SETUP.md** 따라 5분이면 끝.

폰 업로드 안 쓰고 PC 파일만 쓸 거라면 이 단계 건너뛰어도 됩니다.

## 개발 환경에서 실행

```bash
pip install -r requirements.txt
python main.py
```

## .exe 빌드 (Windows)

```cmd
pip install -r requirements.txt
pyinstaller build.spec --clean --noconfirm
```

→ dist\구매영수증_사진삽입기.exe 단일 파일.

## 사용 방법

### 방법 1: PC에서 사진 직접 선택
1. 슬롯 클릭 또는 사진 드래그앤드롭
2. "📂 사진 한번에 선택"으로 3장 한 번에도 가능
3. [한글파일 생성] 클릭 → 저장 → 한글 자동 실행

### 방법 2: 폰에서 사진 보내기 ⭐
1. PC에서 "📱 폰에서 받기" 버튼 클릭 → QR + 페이지 URL 표시
2. 폰 카메라로 QR 스캔 (또는 URL 직접 입력)
3. 폰 페이지에서 사진 3장 선택 → [PC로 보내기] 클릭
4. 폰 화면에 표시되는 **숫자 코드** 확인 (예: 35541387)
5. PC GUI 다이얼로그에 그 코드 입력 → [받기] 클릭
6. PC가 사진 3장을 자동 다운로드 → 슬롯에 채움
7. [한글파일 생성]

## 흐름 요약

```
[폰]                       [tmpfiles.org]              [PC]
LTE 외부망                 익명 임시 파일 보관          사내 일반망
─────                      (60분)                      ─────
GitHub Pages 페이지 접속                                "폰에서 받기" 클릭
사진 3장 업로드      ───→ 사진 1, 2, 3 저장
매니페스트 업로드    ───→ JSON 저장 (코드 발급)
화면에 코드 표시
                                                       코드 입력 → [받기]
                          매니페스트 + 사진       ───→ 자동 다운로드
                                                       슬롯에 자동 채움
```

PC ↔ 폰이 직접 통신 안 함. **tmpfiles.org가 중간 다리**.

## 보안/한계

- tmpfiles.org는 60분 후 파일 자동 삭제
- 파일 크기 100MB까지
- 코드(7-8자리)를 알면 누구나 다운로드 가능 → **민감 사진은 사용 자제**
- 영수증/일반 사진 정도면 문제 없음

## 문제 해결

### "URL 설정 필요" 다이얼로그
main.py 의 PHONE_PAGE_URL 이 기본값. PHONE_PAGE_SETUP.md 따라 수정.

### 폰 업로드 후 코드를 잊었음
60분 안에 다시 업로드하면 됩니다. (다시 새 코드 받음)

### "코드를 찾을 수 없습니다"
- 60분이 지났음 → 다시 업로드
- 코드 잘못 입력 → 폰 화면에서 다시 확인

### .exe 실행 시 바로 닫힘
build.spec 에서 console=False → True로 바꾸고 다시 빌드. 콘솔에 에러 표시.

## 개발자 메모

핵심 발견 (역공학 결과):
- HWPX의 hp:pic 은 한컴 출력을 100% 따라가야 한글에서 열림
- binaryItemIDRef 는 manifest item id 문자열
- 픽셀 → HWPUNIT 변환은 75배 (96 DPI)
- 가운데 정렬은 단락 paraPrIDRef='19' + 셀 vertAlign='CENTER'
- tmpfiles.org는 User-Agent 검증 있음 (Mozilla 헤더 필요)
