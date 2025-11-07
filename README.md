## 실행 방법 (yt-dlp + CSV 자동 다운로드)

아래 명령을 순서대로 실행하세요. macOS 기준입니다.

### 1) 필수 도구 설치

```bash
brew install yt-dlp ffmpeg
```

### 2) 가상환경 생성 및 활성화

```bash
cd "/Users/moonhyerim/soonsu"
python3 -m venv .venv
source .venv/bin/activate
python -V
```

### 3) 스크립트 실행 (CSV → ID/날짜 폴더로 저장)

Chrome 쿠키 사용(권장):

```bash
python /Users/moonhyerim/soonsu/ytdlp_from_csv.py \
  "/Users/moonhyerim/soonsu/순수링크.csv" chrome
```

Safari 쿠키 사용(전체 디스크 접근 권한 필요):

```bash
python /Users/moonhyerim/soonsu/ytdlp_from_csv.py \
  "/Users/moonhyerim/soonsu/순수링크.csv" safari
```

쿠키 없이 공개 게시물만 시도:

```bash
python /Users/moonhyerim/soonsu/ytdlp_from_csv.py \
  "/Users/moonhyerim/soonsu/순수링크.csv" none
```

### 저장 구조

```
/Users/moonhyerim/soonsu/<ID>/<yy.mm.dd>/<제목> [<post_id>].<ext>
```

메모

- 사진 게시물(영상 포맷 없음)은 자동으로 이미지(JPG) 저장으로 폴백됩니다.
- `ffmpeg`가 있으면 더 다양한 포맷/품질을 자동 선택합니다.

---

## Windows 사용자 가이드 (초보자용)

파이썬이 설치되어 있지 않은 사용자를 위한 완전 초보자 가이드입니다.

### 1단계: Python 설치하기

1. **Python 공식 웹사이트 접속**

   - 브라우저에서 `https://www.python.org/downloads/` 접속
   - 페이지가 자동으로 Windows용 최신 버전 다운로드 버튼을 보여줍니다

2. **Python 설치 프로그램 다운로드**

   - "Download Python 3.x.x" 버튼 클릭 (버전 번호는 최신 버전에 따라 다름)
   - 다운로드 폴더에 `python-3.x.x-amd64.exe` 파일이 다운로드됩니다

3. **Python 설치 실행**

   - 다운로드한 파일을 더블클릭하여 실행
   - ✅ **중요: "Add Python to PATH" 체크박스를 반드시 체크하세요!**
   - "Install Now" 클릭하여 설치 진행
   - 설치 완료 후 "Close" 버튼 클릭

4. **Python 설치 확인**
   - Windows 키를 눌러 "cmd" 입력 후 Enter (명령 프롬프트 열기)
   - 다음 명령어 입력 후 Enter:
     ```
     python --version
     ```
   - `Python 3.x.x` 같은 버전이 출력되면 설치 성공!

### 2단계: 필요한 파일 준비하기

1. **프로젝트 파일 다운로드**

   - 이 GitHub 저장소의 모든 파일을 다운로드하거나
   - `ytdlp_from_csv_win.py` 파일을 준비합니다

2. **yt-dlp.exe 다운로드**

   - 브라우저에서 `https://github.com/yt-dlp/yt-dlp/releases` 접속
   - 최신 버전의 "Assets" 클릭
   - `yt-dlp.exe` 파일 다운로드
   - 다운로드한 `yt-dlp.exe`를 프로젝트 폴더에 복사

3. **ffmpeg.exe 다운로드 (선택사항, 권장)**
   - 브라우저에서 `https://www.gyan.dev/ffmpeg/builds/` 접속
   - "ffmpeg-release-essentials.zip" 다운로드
   - 압축 해제 후 `bin` 폴더 안의 `ffmpeg.exe`를 찾아서
   - 프로젝트 폴더에 복사

### 3단계: PyInstaller 설치하기

1. **명령 프롬프트 열기**

   - Windows 키 + R 누르기
   - `cmd` 입력 후 Enter

2. **프로젝트 폴더로 이동**

   - 예시: 프로젝트가 `C:\Users\사용자명\Desktop\soonsu`에 있다면

   ```
   cd C:\Users\사용자명\Desktop\soonsu
   ```

   - (실제 경로로 변경하세요)

3. **PyInstaller 설치**
   - 다음 명령어들을 순서대로 입력 (각 줄 입력 후 Enter):
   ```
   python -m pip install --upgrade pip
   python -m pip install pyinstaller
   ```
   - 설치가 완료될 때까지 기다립니다 (1-2분 소요)

### 4단계: 실행 파일(exe) 만들기

1. **명령 프롬프트에서 빌드 명령 실행**

   - 프로젝트 폴더에 `yt-dlp.exe`와 `ffmpeg.exe`가 있는지 확인
   - 다음 명령어를 한 줄로 입력 (한 줄이 너무 길면 복사해서 붙여넣기):

   ```
   python -m PyInstaller --onefile --name soonsu-downloader --add-binary "yt-dlp.exe;." --add-binary "ffmpeg.exe;." ytdlp_from_csv_win.py
   ```

   - 빌드가 완료될 때까지 기다립니다 (2-5분 소요)

2. **생성된 파일 확인**
   - 프로젝트 폴더에 `dist` 폴더가 생성됩니다
   - `dist` 폴더 안에 `soonsu-downloader.exe` 파일이 생성되었는지 확인

**✅ 중요: `soonsu-downloader.exe` 파일 하나만 있으면 됩니다!**

- 빌드할 때 `--add-binary` 옵션으로 `yt-dlp.exe`와 `ffmpeg.exe`가 exe 파일 안에 포함되었습니다
- 다른 PC로 복사하거나 배포할 때 `soonsu-downloader.exe` 파일 하나만 있으면 됩니다
- 추가 파일(yt-dlp.exe, ffmpeg.exe 등)은 필요하지 않습니다

### 4-1단계: 배포용 패키지 준비하기 (선택사항)

팀원이나 다른 사용자에게 배포하려면 다음을 준비하세요:

1. **exe 파일 준비**

   - `dist` 폴더의 `soonsu-downloader.exe` 파일 복사

2. **배포용 폴더 만들기 (선택사항)**

   ```
   soonsu-downloader/
   ├── soonsu-downloader.exe  (필수)
   ├── 사용설명서.txt          (선택)
   └── 예시_순수링크.csv       (선택, 예시 파일)
   ```

3. **ZIP 파일로 압축하여 배포**
   - 위 폴더를 ZIP으로 압축
   - 이메일, 클라우드 스토리지, 파일 공유 등으로 배포

**📦 배포 시 포함할 내용 예시:**

```
soonsu-downloader.zip
├── soonsu-downloader.exe
└── 사용설명서.txt
```

**사용설명서.txt 예시:**

```
순수 인스타그램 다운로더 사용법

1. soonsu-downloader.exe 파일을 더블클릭하세요.

2. CSV 파일 준비:
   - 번호, 링크, ID, 날짜 형식의 CSV 파일이 필요합니다
   - 예시:
     1, https://www.instagram.com/p/XXXX/, some_id, 10월 20일

3. 프로그램 실행:
   - CSV 파일 선택 버튼으로 CSV 파일 선택
   - 저장 위치 선택 버튼으로 다운로드할 폴더 선택
   - 브라우저 쿠키 선택 (보통 chrome 권장)
   - 시작 버튼 클릭

4. 다운로드 완료 후:
   - 선택한 저장 위치에 <ID>/<날짜>/ 형식으로 파일이 저장됩니다

주의사항:
- Chrome/Edge 브라우저에서 인스타그램에 로그인되어 있어야 합니다
- 인터넷 연결이 필요합니다
```

### 5단계: 프로그램 실행하기 (배포받은 사용자)

**배포받은 사용자는 다음만 하면 됩니다:**

1. **ZIP 파일 압축 해제** (ZIP로 배포한 경우)

   - `soonsu-downloader.zip` 파일을 압축 해제

2. **프로그램 실행**

   - `soonsu-downloader.exe` 파일을 더블클릭
   - **Python 설치 불필요!** 더블클릭만 하면 바로 실행됩니다

3. **GUI에서 사용**
   - GUI 창이 열립니다
   - **CSV 파일 선택**: "CSV 파일" 옆 "찾기" 버튼 클릭하여 CSV 파일 선택
   - **저장 위치 선택**: "저장 위치" 옆 "찾기" 버튼 클릭하여 다운로드할 폴더 선택
   - **브라우저 쿠키 선택**: chrome, edge, safari, none 중 선택 (보통 chrome 권장)
   - **시작 버튼 클릭**: 다운로드 시작!

**명령줄 방식 (고급 사용자):**

- 명령 프롬프트에서:

```
soonsu-downloader.exe "C:\경로\순수링크.csv" chrome
```

### CSV 파일 준비하기

프로그램이 사용할 CSV 파일은 다음 형식이어야 합니다:

```
번호,링크,ID,날짜
1,https://www.instagram.com/p/XXXX/,some_id,10월 20일
2,https://www.instagram.com/p/YYYY/,another_id,11월 15일
```

**컬럼 설명:**

- **번호**: 순번 (무시해도 됨)
- **링크**: 인스타그램 게시물 URL (필수)
- **ID**: 사용자 ID (저장 폴더명으로 사용, 필수)
- **날짜**: 게시 날짜 (저장 폴더명으로 사용, 필수)

**날짜 형식 예시:**

- `10월 20일`
- `2024년 11월 10일`
- `24.11.10`
- `10.14`

### 저장 구조

다운로드된 파일은 다음과 같은 구조로 저장됩니다:

```
<선택한 저장 위치>/
  └── <ID>/
      └── <yy.mm.dd>/
          └── <제목> [<post_id>].mp4
```

**예시:**

```
C:\Downloads\
  └── hair_sora918\
      └── 25.05.15\
          └── Video by hair_sora918 [DJrJ0EFzE3Z].mp4
```

### 문제 해결

**Q: "python이 인식되지 않습니다" 오류**

- Python 설치 시 "Add Python to PATH"를 체크하지 않았을 가능성
- Python을 다시 설치하거나, 환경 변수를 수동으로 설정해야 합니다

**Q: "yt-dlp.exe를 찾을 수 없습니다" 오류**

- 이 오류는 정상적으로 빌드된 경우 발생하지 않아야 합니다
- 만약 발생한다면 빌드를 다시 시도해보세요
- 빌드 시 `--add-binary "yt-dlp.exe;."` 옵션이 제대로 적용되었는지 확인

**Q: 다운로드가 실패합니다**

- Chrome/Edge 브라우저에서 인스타그램에 로그인되어 있는지 확인
- 브라우저 쿠키 선택을 `chrome` 또는 `edge`로 설정
- 일부 게시물은 비공개일 수 있어 다운로드가 불가능할 수 있습니다

**Q: 사진만 다운로드됩니다**

- 일부 게시물은 사진만 있는 경우가 있습니다
- 자동으로 JPG 이미지로 저장됩니다


# 0) 프로젝트 이동 + venv 활성화
cd "/Users/moonhyerim/soonsu"
[ -d .venv ] || python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install --upgrade pip pyinstaller

# 1) yt-dlp(맥용) 준비
[ -f yt-dlp ] || curl -L https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp_macos -o yt-dlp
chmod +x yt-dlp
xattr -d com.apple.quarantine yt-dlp 2>/dev/null || true

# 2) ffmpeg 경로 확보(없으면 설치)
brew list ffmpeg >/dev/null 2>&1 || brew install ffmpeg
FF=$(which ffmpeg)
echo "ffmpeg => $FF"

# 3) 이전 빌드 정리
rm -rf build dist SoonsuDownloader.spec

# 4) 빌드(onendir + windowed 권장)
python3 -m PyInstaller --onedir --windowed --name SoonsuDownloader \
  --add-binary "$(pwd)/yt-dlp:." \
  --add-binary "$FF:." \
  ytdlp_from_csv_win.py

# 5) 실행 확인
open dist/SoonsuDownloader.app