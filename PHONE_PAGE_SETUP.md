# 폰 페이지 GitHub Pages 셋업 가이드

폰에서 사진을 업로드하기 위한 웹페이지를 GitHub Pages에 5분 만에 올리는 방법.

## 한 번만 셋업하면 됩니다

### 1단계: GitHub 접속
https://github.com 로그인 (헴이 이미 가입되어 있는 그 계정).

### 2단계: 새 저장소 만들기
1. 우측 상단 **+ → New repository**
2. **Repository name**: `receipt-phone-uploader` (원하는 이름)
3. **Public** 선택 (GitHub Pages는 Public 저장소만 무료)
4. **Add a README file** 체크 (있어도 되고 없어도 됨)
5. **Create repository** 클릭

### 3단계: 폰 페이지 업로드
1. 만들어진 저장소 페이지에서 **Add file → Upload files** 클릭
2. `phone_page/index.html` 파일을 드래그
3. 페이지 하단에서 **Commit changes** 클릭

### 4단계: GitHub Pages 활성화
1. 저장소 상단 **Settings** 탭
2. 좌측 메뉴 **Pages**
3. **Source**: `Deploy from a branch`
4. **Branch**: `main` / `(root)` 선택
5. **Save** 클릭

### 5단계: URL 확인
1. 1-2분 정도 기다린 후 같은 Pages 페이지 새로고침
2. 상단에 초록색 박스로 표시됨:
   ```
   ✓ Your site is live at https://<헴아이디>.github.io/receipt-phone-uploader/
   ```
3. **이 URL을 복사**해두세요. 이제 PC GUI 코드에서 이걸 사용합니다.

### 6단계: PC GUI에 URL 입력
`main.py` 파일을 열고 다음 줄을 찾으세요:

```python
PHONE_PAGE_URL = "https://YOUR_GITHUB_ID.github.io/receipt-phone-uploader/"
```

→ 이 값을 헴의 실제 URL로 교체:

```python
PHONE_PAGE_URL = "https://kimheim.github.io/receipt-phone-uploader/"
```

저장 후 GUI 다시 실행. 끝!

## 동작 확인

1. 폰 브라우저에서 직접 URL 접속해보기 → 업로드 화면이 나오면 성공
2. PC에서 GUI → **"📱 폰에서 받기"** → QR코드 표시되는지 확인

## 추후 페이지 수정하고 싶을 때

저장소 페이지에서 `index.html` 파일 클릭 → 연필 아이콘 (Edit) → 수정 후 commit.
2-3분 안에 자동 반영됩니다.

## 비용

GitHub Pages Public 저장소: **무제한 무료, 영구**.
