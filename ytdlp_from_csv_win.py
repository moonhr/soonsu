#!/usr/bin/env python3
import csv
import os
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
import threading
import time

# 실행 파일/스크립트 기준 경로
BASE_DIR = Path(getattr(sys, '_MEIPASS', Path(__file__).parent)).resolve()
CONCURRENCY = 3

# 게시글 캡션 파일명(하나만 유지)
CAPTION_FILENAME = "게시물.txt"

# 일시중지 제어 이벤트: set() = 실행, clear() = 일시중지
RUN_EVENT = threading.Event()
RUN_EVENT.set()

# 완전 중단 이벤트: set() 되면 모든 작업 즉시 종료
CANCEL_EVENT = threading.Event()

# 기본 브라우저 쿠키 사용
USE_BROWSER_COOKIES = os.environ.get("YTDLP_BROWSER", "chrome")  # "chrome" | "edge" | "safari" | "none"

# GUI/CLI 로그 콜백 (기본은 print)
LOG_FN = lambda msg: print(msg)
def log(msg: str) -> None:
    try:
        LOG_FN(str(msg))
    except Exception:
        try:
            print(str(msg))
        except Exception:
            pass


def sanitize(path_part: str) -> str:
    """파일/폴더 이름에 쓸 수 없는 문자 정리"""
    return re.sub(r'[\\/:*?"<>|]+', '_', (path_part or '').strip())


def load_id_name_map(map_path: Path | None = None) -> dict:
    """
    1열=id, 2열=사람이름 형태의 CSV를 읽어 id→이름 매핑 반환.
    기본 파일명은 BASE_DIR/순수계정.csv. 없으면 빈 dict.
    """
    if map_path is None:
        map_path = BASE_DIR / "순수계정.csv"
    mapping = {}
    try:
        with open(map_path, "r", encoding="utf-8-sig", newline="") as f:
            reader = csv.reader(f)
            for row in reader:
                if not row or len(row) < 2:
                    continue
                uid = (row[0] or "").strip()
                name = (row[1] or "").strip()
                if uid:
                    mapping[uid] = name
    except FileNotFoundError:
        pass
    except Exception as e:
        log(f"[warn] ID-Name 매핑 로드 실패: {e}")
    return mapping


def resolve_ytdlp_bin() -> str:
    """PyInstaller 패키징된 경우와 일반 실행 모두 지원"""
    if getattr(sys, 'frozen', False):
        base_path = Path(sys._MEIPASS)
    else:
        base_path = Path(__file__).parent

    is_windows = os.name == 'nt'
    if is_windows:
        local = base_path / "yt-dlp.exe"
        if local.exists():
            return str(local)
        return "yt-dlp.exe"
    else:
        local = base_path / "yt-dlp"
        if local.exists():
            return str(local)
        return "yt-dlp"


def normalize_date(raw: str) -> str:
    if not raw:
        return datetime.now().strftime("%y.%m.%d")
    text = raw.strip()

    m = re.search(r"\(([^\)]+)\)", text)
    if m:
        inner = m.group(1).strip()
        try:
            return normalize_date(inner)
        except Exception:
            pass

    m = re.search(r"(20\d{2})[^0-9]?\s*(\d{1,2})[^0-9]?\s*(\d{1,2})", text)
    if m:
        y4 = int(m.group(1)); mm = int(m.group(2)); dd = int(m.group(3))
        return f"{y4 % 100:02d}.{mm:02d}.{dd:02d}"

    m = re.search(r"(\d{2})\s*년?[^0-9]?\s*(\d{1,2})\s*월?[^0-9]?\s*(\d{1,2})", text)
    if m:
        y2 = int(m.group(1)); mm = int(m.group(2)); dd = int(m.group(3))
        return f"{y2:02d}.{mm:02d}.{dd:02d}"

    m = re.search(r"^(\d{2})[./-](\d{1,2})[./-](\d{1,2})$", text)
    if m:
        y2 = int(m.group(1)); mm = int(m.group(2)); dd = int(m.group(3))
        return f"{y2:02d}.{mm:02d}.{dd:02d}"

    m = re.search(r"^(\d{1,2})[./-](\d{1,2})$", text)
    if m:
        now = datetime.now(); mm = int(m.group(1)); dd = int(m.group(2))
        return f"{now.year % 100:02d}.{mm:02d}.{dd:02d}"

    m = re.search(r"(\d{1,2})\s*월\s*(\d{1,2})\s*일?", text)
    if m:
        now = datetime.now(); mm = int(m.group(1)); dd = int(m.group(2))
        return f"{now.year % 100:02d}.{mm:02d}.{dd:02d}"

    m = re.search(r"(\d{1,2})\s*월\s*(\d{1,2})", text)
    if m:
        now = datetime.now(); mm = int(m.group(1)); dd = int(m.group(2))
        return f"{now.year % 100:02d}.{mm:02d}.{dd:02d}"

    m = re.search(r"^(\d{1,2})\s+(\d{1,2})\s*일?$", text)
    if m:
        now = datetime.now(); mm = int(m.group(1)); dd = int(m.group(2))
        return f"{now.year % 100:02d}.{mm:02d}.{dd:02d}"

    return datetime.now().strftime("%y.%m.%d")


def _read_text_safe(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8").strip()
    except Exception:
        return ""


def ensure_caption_txt(out_dir: Path) -> None:
    """
    게시글 캡션을 txt로 보장한다.
    1) yt-dlp가 생성한 *.description을 *.txt로 바꾼다.
    """
    try:
        for p in out_dir.glob("*.description"):
            target = p.with_suffix(".txt")
            try:
                if target.exists():
                    target.unlink()
            except Exception:
                pass
            try:
                p.rename(target)
            except Exception:
                pass
    except Exception:
        pass


def consolidate_caption_to_single(out_dir: Path) -> None:
    """
    폴더 내 캡션을 하나의 CAPTION_FILENAME로 통합한다.
    - 오직 사용자가 입력한 캡션만 저장(메타 없음)
    - 우선순위: *.description 내용
    - 통합 후 CAPTION_FILENAME만 남기고 나머지 *.txt / *.description은 삭제.
    """
    caption = ""

    try:
        for p in out_dir.glob("*.description"):
            txt = _read_text_safe(p)
            if txt:
                caption = txt
                break
    except Exception:
        pass

    target = out_dir / CAPTION_FILENAME
    try:
        target.write_text(caption, encoding="utf-8")
    except Exception:
        pass

    try:
        for tp in out_dir.glob("*.txt"):
            if tp.name != CAPTION_FILENAME:
                try:
                    tp.unlink()
                except Exception:
                    pass
        for dp in out_dir.glob("*.description"):
            try:
                dp.unlink()
            except Exception:
                pass
    except Exception:
        pass


def run_yt_dlp(url: str, out_dir: Path, ytdlp_bin: str) -> int:
    out_dir.mkdir(parents=True, exist_ok=True)

    # 중단 요청 시 즉시 종료
    if CANCEL_EVENT.is_set():
        return 2

    # 일시중지 상태면 대기
    while not RUN_EVENT.is_set():
        if CANCEL_EVENT.is_set():
            return 2
        time.sleep(0.2)

    cmd = [
        ytdlp_bin,
        "-P", str(out_dir),
        "-o", "%(title)s [%(id)s].%(ext)s",
        "--no-overwrites",
        "--retries", "10",
        "--fragment-retries", "10",
        "-N", "8",
        "--write-description",
    ]
    if USE_BROWSER_COOKIES and USE_BROWSER_COOKIES.lower() != "none":
        cmd += ["--cookies-from-browser", USE_BROWSER_COOKIES]
    cmd.append(url)

    # 실시간 로그 파이프
    log(f"▶ 시작: {url}")
    output_lines = []
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
        if proc.stdout:
            for line in proc.stdout:
                line = line.rstrip("\n")
                output_lines.append(line)
                if line:
                    log(line)
        proc.wait()
        output = "\n".join(output_lines)
    except Exception as e:
        log(f"[error] 프로세스 실행 실패: {e}")
        return 1

    # 캡션 파일 보장 및 단일화
    ensure_caption_txt(out_dir)
    consolidate_caption_to_single(out_dir)

    if proc.returncode == 0:
        log("✅ 1차 시도 완료")
    else:
        log(f"⚠️ 1차 시도 오류 (코드: {proc.returncode})")

    # 1차 시도 결과 점검: 비디오/이미지 파일 존재 여부 확인
    video_exts = (".mp4", ".mov", ".webm", ".mkv")
    image_exts = (".jpg", ".jpeg", ".png", ".webp")
    has_video = any(p.suffix.lower() in video_exts for p in out_dir.iterdir() if p.is_file())
    has_image = any(p.suffix.lower() in image_exts for p in out_dir.iterdir() if p.is_file())

    # 폴백 필요 조건:
    # - 프로세스 실패했거나
    # - 출력에 'No video formats found' 유사 메시지가 있거나
    # - 성공이더라도 실제 비디오/이미지 산출물이 전혀 없을 때(사진 게시글일 수 있음)
    fallback_markers = (
        "No video formats found",
        "no video formats",
        "requested format not available",
    )
    need_fallback = (proc.returncode != 0) \
        or any(m.lower() in (output or "").lower() for m in fallback_markers) \
        or (not has_video and not has_image)

    # 일시중지 상태면 대기 (폴백 전)
    while not RUN_EVENT.is_set():
        if CANCEL_EVENT.is_set():
            return 2
        time.sleep(0.2)

    # 필요 시 이미지/썸네일 폴백 (사진 게시글 포함)
    if need_fallback:
        img_cmd = [
            ytdlp_bin,
            "-P", str(out_dir),
            "-o", "%(title)s [%(id)s].%(ext)s",
            "--skip-download",
            "--write-thumbnail",
            "--write-all-thumbnails",
            "--write-description",
            "--convert-thumbnails", "jpg",
        ]
        if USE_BROWSER_COOKIES and USE_BROWSER_COOKIES.lower() != "none":
            img_cmd += ["--cookies-from-browser", USE_BROWSER_COOKIES]
        img_cmd.append(url)

        log("[yt-dlp:image-fallback] 썸네일 모드로 재시도")
        img_lines = []
        try:
            img_proc = subprocess.Popen(img_cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
            if img_proc.stdout:
                for line in img_proc.stdout:
                    line = line.rstrip("\n")
                    img_lines.append(line)
                    if line:
                        log(line)
            img_proc.wait()
        except Exception as e:
            log(f"[error] 이미지 폴백 실패: {e}")
            return 1

        # 폴백에서도 캡션 보장 및 단일화
        ensure_caption_txt(out_dir)
        consolidate_caption_to_single(out_dir)

        if img_proc.returncode == 0:
            log("🖼️ 사진/썸네일 폴백 완료")
        else:
            log(f"❌ 폴백 실패 (코드: {img_proc.returncode})")
        return img_proc.returncode

    return proc.returncode


def parse_csv_and_jobs(csv_path: Path):
    jobs = []
    with open(csv_path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f)
        header_skipped = False
        for row in reader:
            if not header_skipped:
                header_skipped = True
                continue
            if not row or len(row) < 4:
                continue
            url = (row[1] or "").strip()
            user_id = (row[2] or "").strip()
            date_raw = (row[3] or "").strip()
            if not url or not user_id:
                continue
            date_norm = normalize_date(date_raw)
            jobs.append((url, user_id, date_norm))
    return jobs


def main():
    if len(sys.argv) < 2:
        print("사용법: ytdlp_from_csv_win.py <csv_path> [map_csv_path] [browser]")
        print("browser: chrome | edge | safari | none (기본 chrome)")
        print("예시1) ytdlp_from_csv_win.py 작업.csv")
        print("예시2) ytdlp_from_csv_win.py 작업.csv 순수계정.csv")
        print("예시3) ytdlp_from_csv_win.py 작업.csv 순수계정.csv chrome")
        print("예시4) ytdlp_from_csv_win.py 작업.csv none")
        sys.exit(1)

    csv_path = Path(sys.argv[1])
    map_csv_path = None
    if len(sys.argv) > 2:
        arg2 = sys.argv[2]
        if arg2.lower() in ("chrome", "edge", "safari", "none"):
            globals()["USE_BROWSER_COOKIES"] = arg2.lower()
        else:
            map_csv_path = Path(arg2)
            if len(sys.argv) > 3:
                globals()["USE_BROWSER_COOKIES"] = sys.argv[3].lower()

    if not csv_path.exists():
        print(f"CSV 파일이 존재하지 않습니다: {csv_path}")
        sys.exit(1)

    jobs = parse_csv_and_jobs(csv_path)
    if not jobs:
        print("다운로드할 항목이 없습니다.")
        return

    print(f"총 {len(jobs)}건 처리 예정.")
    ytdlp_bin = resolve_ytdlp_bin()
    id_name = load_id_name_map(map_csv_path)

    futures = []
    with ThreadPoolExecutor(max_workers=CONCURRENCY) as executor:
        for url, user_id, ymd in jobs:
            display = id_name.get(user_id, "undefine")
            folder = sanitize(f"{user_id}_{display}")
            out_dir = BASE_DIR / folder / ymd
            futures.append(executor.submit(run_yt_dlp, url, out_dir, ytdlp_bin))

        success = 0
        for fut in as_completed(futures):
            rc = fut.result()
            if rc == 0:
                success += 1

    print(f"완료: {success}/{len(jobs)} 성공")


if __name__ == "__main__":
    # 인자 없으면 GUI 제공
    if len(sys.argv) == 1:
        try:
            import tkinter as tk
            from tkinter import filedialog, ttk, messagebox

            app = tk.Tk()
            app.title("Soonsu Instagram Downloader (Windows)")
            app.geometry("780x600")

            # 설명 라벨
            desc = tk.Label(
                app,
                text=(
                    "CSV 컬럼 구조(좌→우): 번호, 링크, ID, 날짜, ...\n"
                    "예시: 1, https://www.instagram.com/p/XXXX/, some_id, 10월 20일\n"
                    "저장 구조: <저장위치>/<ID_이름>/<yy.mm.dd>/...  (이름 매핑은 '순수계정.csv' 1열=id, 2열=이름)\n"
                    "캡션 파일은 '게시물.txt'로 저장됩니다.\n"
                    "버튼: 시작 / 일시중지 / 재개 / 중단 / 입력 비우기"
                ),
                anchor="w", justify="left"
            )
            desc.pack(fill="x", padx=12, pady=(10, 6))

            # 작업 CSV 선택
            file_frame = tk.Frame(app)
            file_frame.pack(fill="x", padx=12, pady=6)
            csv_path_var = tk.StringVar()
            tk.Label(file_frame, text="작업 CSV:").pack(side="left")
            entry = tk.Entry(file_frame, textvariable=csv_path_var)
            entry.pack(side="left", fill="x", expand=True, padx=8)

            def update_preview(rows):
                for item in preview.get_children():
                    preview.delete(item)
                for row in rows:
                    row = (row + [""] * 5)[:5]
                    preview.insert("", "end", values=row)

            def choose_file():
                path = filedialog.askopenfilename(
                    title="작업 CSV 선택",
                    filetypes=[("CSV Files", "*.csv"), ("All Files", "*.*")]
                )
                if path:
                    csv_path_var.set(path)
                    try:
                        with open(path, "r", encoding="utf-8-sig", newline="") as f:
                            reader = csv.reader(f)
                            rows = []
                            for i, row in enumerate(reader):
                                rows.append(row)
                                if i >= 9:
                                    break
                        update_preview(rows)
                    except Exception as e:
                        messagebox.showerror("오류", f"CSV 읽기 실패: {e}")

            tk.Button(file_frame, text="찾기", command=choose_file).pack(side="left")

            # 매핑 CSV 선택 (선택)
            map_frame = tk.Frame(app)
            map_frame.pack(fill="x", padx=12, pady=6)
            map_path_var = tk.StringVar()
            default_map = BASE_DIR / "순수계정.csv"
            if default_map.exists():
                map_path_var.set(str(default_map))
            tk.Label(map_frame, text="ID-이름 매핑 CSV(선택):").pack(side="left")
            map_entry = tk.Entry(map_frame, textvariable=map_path_var)
            map_entry.pack(side="left", fill="x", expand=True, padx=8)

            def choose_map_file():
                path = filedialog.askopenfilename(
                    title="ID-이름 매핑 CSV 선택",
                    filetypes=[("CSV Files", "*.csv"), ("All Files", "*.*")]
                )
                if path:
                    map_path_var.set(path)

            tk.Button(map_frame, text="찾기", command=choose_map_file).pack(side="left")

            # 저장 위치 선택
            save_frame = tk.Frame(app)
            save_frame.pack(fill="x", padx=12, pady=6)
            save_path_var = tk.StringVar(value=str(BASE_DIR))
            tk.Label(save_frame, text="저장 위치:").pack(side="left")
            save_entry = tk.Entry(save_frame, textvariable=save_path_var)
            save_entry.pack(side="left", fill="x", expand=True, padx=8)

            def choose_save_dir():
                path = filedialog.askdirectory(
                    title="저장할 폴더 선택",
                    initialdir=save_path_var.get() if save_path_var.get() else None
                )
                if path:
                    save_path_var.set(path)

            tk.Button(save_frame, text="찾기", command=choose_save_dir).pack(side="left")

            # 브라우저 라디오 버튼
            browser_frame = tk.Frame(app)
            browser_frame.pack(fill="x", padx=12, pady=6)
            tk.Label(browser_frame, text="브라우저 쿠키:").pack(side="left")
            browser_var = tk.StringVar(value=USE_BROWSER_COOKIES)
            for name in ["chrome", "edge", "safari", "none"]:
                ttk.Radiobutton(browser_frame, text=name, value=name, variable=browser_var).pack(side="left", padx=6)

            # 미리보기 테이블
            preview = ttk.Treeview(app, columns=("c1", "c2", "c3", "c4", "c5"), show="headings", height=8)
            for i, title in enumerate(["col1", "col2", "col3", "col4", "col5"], start=1):
                preview.heading(f"c{i}", text=title)
                preview.column(f"c{i}", width=140, anchor="w")
            preview.pack(fill="x", padx=12, pady=(6, 6))

            # 로그
            log_widget = tk.Text(app, height=12)
            log_widget.pack(fill="both", expand=True, padx=12, pady=(6, 6))

            def append_log(text: str):
                def _do():
                    log_widget.insert("end", text + "\n")
                    log_widget.see("end")
                try:
                    app.after(0, _do)
                except Exception:
                    pass

            # 실행 버튼들
            btn_frame = tk.Frame(app)
            btn_frame.pack(fill="x", padx=12, pady=(0, 10))

            def run_task():
                csv_path = csv_path_var.get().strip()
                if not csv_path:
                    messagebox.showwarning("경고", "작업 CSV 파일을 선택하세요.")
                    return
                if not Path(csv_path).exists():
                    messagebox.showerror("오류", "작업 CSV 파일이 존재하지 않습니다.")
                    return

                save_dir = save_path_var.get().strip()
                if not save_dir:
                    messagebox.showwarning("경고", "저장 위치를 선택하세요.")
                    return
                save_dir_path = Path(save_dir)
                try:
                    save_dir_path.mkdir(parents=True, exist_ok=True)
                except Exception as e:
                    messagebox.showerror("오류", f"저장 위치 생성 실패: {e}")
                    return

                globals()["USE_BROWSER_COOKIES"] = browser_var.get().lower()

                def worker():
                    try:
                        # GUI 로그로 라우팅
                        globals()["LOG_FN"] = append_log

                        jobs = parse_csv_and_jobs(Path(csv_path))
                        append_log(f"총 {len(jobs)}건 처리 시작...")
                        append_log(f"저장 위치: {save_dir_path}")
                        ytdlp_bin = resolve_ytdlp_bin()

                        # 선택된 매핑 CSV 사용
                        map_path_str = map_path_var.get().strip()
                        map_path = Path(map_path_str) if map_path_str else None
                        id_name = load_id_name_map(map_path)

                        success = 0
                        with ThreadPoolExecutor(max_workers=CONCURRENCY) as executor:
                            futures = []
                            CANCEL_EVENT.clear()

                            # 제출
                            for url, user_id, ymd in jobs:
                                if CANCEL_EVENT.is_set():
                                    break
                                display = id_name.get(user_id, "undefine")
                                folder = sanitize(f"{user_id}_{display}")
                                out_dir = save_dir_path / folder / ymd
                                futures.append(executor.submit(run_yt_dlp, url, out_dir, ytdlp_bin))

                            # 수집
                            for fut in as_completed(futures):
                                if CANCEL_EVENT.is_set():
                                    break
                                rc = fut.result()
                                if rc == 0:
                                    success += 1

                            if CANCEL_EVENT.is_set():
                                try:
                                    executor.shutdown(cancel_futures=True)
                                except TypeError:
                                    executor.shutdown(wait=False)
                                append_log("⛔ 사용자에 의해 작업이 중단되었습니다.")

                        append_log(f"완료: {success}/{len(jobs)} 성공")
                        messagebox.showinfo("완료", f"완료: {success}/{len(jobs)} 성공")
                    except Exception as e:
                        append_log(f"오류: {e}")
                        messagebox.showerror("오류", str(e))
                    finally:
                        # 기본 로거로 환원
                        globals()["LOG_FN"] = lambda m: print(m)

                threading.Thread(target=worker, daemon=True).start()

            ttk.Button(btn_frame, text="시작", command=run_task).pack(side="left")

            # 완전 중단 버튼
            def stop_all():
                CANCEL_EVENT.set()
                RUN_EVENT.set()  # 일시중지 상태였다면 해제하여 빠르게 종료
                append_log("⛔ 작업 완전 중단 요청")
                try:
                    messagebox.showinfo("중단", "작업 중단을 요청했습니다. 잠시 후 정리됩니다.")
                except Exception:
                    pass

            ttk.Button(btn_frame, text="중단", command=stop_all).pack(side="left", padx=6)

            # 일시중지/재개
            is_paused = {"value": False}

            def toggle_pause():
                if is_paused["value"]:
                    RUN_EVENT.set()
                    is_paused["value"] = False
                    append_log("▶ 재개")
                    pause_btn.config(text="일시중지")
                else:
                    RUN_EVENT.clear()
                    is_paused["value"] = True
                    append_log("⏸ 일시중지")
                    pause_btn.config(text="재개")

            pause_btn = ttk.Button(btn_frame, text="일시중지", command=toggle_pause)
            pause_btn.pack(side="left", padx=6)

            # 입력 비우기
            def clear_inputs():
                csv_path_var.set("")
                map_path_var.set("")
                save_path_var.set(str(BASE_DIR))
                for item in preview.get_children():
                    preview.delete(item)
                append_log("🧹 입력을 비웠습니다.")

            ttk.Button(btn_frame, text="입력 비우기", command=clear_inputs).pack(side="left", padx=6)

            app.mainloop()
        except Exception:
            # GUI 불가 시 CLI 폴백
            main()
    else:
        main()