#!/usr/bin/env python3
import csv
import os
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

# 실행 파일/스크립트 기준 경로
BASE_DIR = Path(getattr(sys, '_MEIPASS', Path(__file__).parent)).resolve()
CONCURRENCY = 3

# 기본 브라우저 쿠키 사용
USE_BROWSER_COOKIES = os.environ.get("YTDLP_BROWSER", "chrome")  # "chrome" | "edge" | "safari" | "none"

def sanitize(path_part: str) -> str:
    """파일/폴더 이름에 쓸 수 없는 문자 정리"""
    return re.sub(r'[\\/:*?"<>|]+', '_', (path_part or '').strip())

# Helper: build_output_dir
def build_output_dir(base: Path, user_id: str, display: str, ymd: str, occurrence_idx: int) -> Path:
    """
    동일 사용자(user_id)와 동일 날짜(ymd)가 CSV에 여러 번 등장할 때,
    첫 번째는 'yy.mm.dd', 두 번째는 'yy.mm.dd_2', 세 번째는 'yy.mm.dd_3' 형태로
    하위 폴더명을 결정한다.
    """
    folder = sanitize(f"{user_id}_{display}")
    sub = ymd if occurrence_idx <= 1 else f"{ymd}_{occurrence_idx}"
    return base / folder / sub

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
        # 매핑 파일이 없으면 조용히 무시
        pass
    except Exception as e:
        print(f"[warn] ID-Name 매핑 로드 실패: {e}")
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


# Helper import for JSON handling
import json

def ensure_caption_txt(out_dir: Path) -> None:
    """
    게시글 캡션을 txt로 보장한다.
    1) yt-dlp가 생성한 *.description을 *.txt로 바꾼다.
    2) *.description이 없거나 비어 있을 경우, *.info.json의 'description' 값을 읽어
       동일한 베이스 파일명으로 *.txt를 생성한다.
    """
    # 1) 먼저 .description -> .txt 변환
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

    # 2) info.json 기반으로 보강
    try:
        for jp in out_dir.glob("*.info.json"):
            try:
                with open(jp, "r", encoding="utf-8") as jf:
                    meta = json.load(jf)
            except Exception:
                continue
            desc = (meta.get("description") or "").strip()
            if not desc:
                continue
            txt_path = jp.with_suffix(".txt")  # same basename *.txt
            # 이미 txt가 있으면 건너뛰되, 비어 있으면 덮어쓰기
            need_write = True
            if txt_path.exists():
                try:
                    if txt_path.stat().st_size > 0:
                        need_write = False
                except Exception:
                    pass
            if need_write:
                try:
                    with open(txt_path, "w", encoding="utf-8") as tf:
                        tf.write(desc)
                except Exception:
                    pass
    except Exception:
        pass

def rename_description_to_txt(out_dir: Path) -> None:
    # 유지 호환: 기존 이름을 호출하는 곳이 있어도 동작하도록 ensure_caption_txt로 위임
    ensure_caption_txt(out_dir)

def run_yt_dlp(url: str, out_dir: Path, ytdlp_bin: str) -> int:
    out_dir.mkdir(parents=True, exist_ok=True)

    cmd = [
        ytdlp_bin,
        "-P", str(out_dir),
        "-o", "%(title)s [%(id)s].%(ext)s",
        "--no-overwrites",
        "--retries", "10",
        "--fragment-retries", "10",
        "-N", "8",
        "--write-description",
        "--write-info-json",
    ]
    if USE_BROWSER_COOKIES and USE_BROWSER_COOKIES.lower() != "none":
        cmd += ["--cookies-from-browser", USE_BROWSER_COOKIES]
    cmd.append(url)

    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    output = proc.stdout or ""
    print(f"[yt-dlp] {url}\n" + output)

    # 캡션 파일(.txt) 보장 (.description → .txt 변환 + info.json 보강)
    ensure_caption_txt(out_dir)

    if proc.returncode != 0 and "No video formats found" in output:
        img_cmd = [
            ytdlp_bin,
            "-P", str(out_dir),
            "-o", "%(title)s [%(id)s].%(ext)s",
            "--skip-download",
            "--write-thumbnail",
            "--write-description",
            "--write-info-json",
            "--convert-thumbnails", "jpg",
        ]
        if USE_BROWSER_COOKIES and USE_BROWSER_COOKIES.lower() != "none":
            img_cmd += ["--cookies-from-browser", USE_BROWSER_COOKIES]
        img_cmd.append(url)
        img_proc = subprocess.run(img_cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        print("[yt-dlp:image-fallback]\n" + (img_proc.stdout or ""))
        # 폴백 케이스에서도 캡션 보장
        ensure_caption_txt(out_dir)
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
    # 두 번째 인자: 매핑 CSV 또는 브라우저
    if len(sys.argv) > 2:
        arg2 = sys.argv[2]
        if arg2.lower() in ("chrome", "edge", "safari", "none"):
            globals()["USE_BROWSER_COOKIES"] = arg2.lower()
        else:
            map_csv_path = Path(arg2)
            # 세 번째 인자: 브라우저일 수 있음
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

    occ = {}
    futures = []
    with ThreadPoolExecutor(max_workers=CONCURRENCY) as executor:
        for url, user_id, ymd in jobs:
            display = id_name.get(user_id, "undefine")
            key = (user_id, ymd)
            occ[key] = occ.get(key, 0) + 1
            out_dir = build_output_dir(BASE_DIR, user_id, display, ymd, occ[key])
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
            import threading
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
                    "저장 구조: <저장위치>/<ID_이름>/<yy.mm.dd>/...  (이름 매핑은 '순수계정.csv' 1열=id, 2열=이름)"
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
            preview = ttk.Treeview(app, columns=("c1","c2","c3","c4","c5"), show="headings", height=8)
            for i, title in enumerate(["col1","col2","col3","col4","col5"], start=1):
                preview.heading(f"c{i}", text=title)
                preview.column(f"c{i}", width=140, anchor="w")
            preview.pack(fill="x", padx=12, pady=(6, 6))
            def update_preview(rows):
                for item in preview.get_children():
                    preview.delete(item)
                for row in rows:
                    row = (row + [""] * 5)[:5]
                    preview.insert("", "end", values=row)

            # 로그
            log = tk.Text(app, height=12)
            log.pack(fill="both", expand=True, padx=12, pady=(6, 6))
            def append_log(text: str):
                log.insert("end", text + "\n")
                log.see("end")

            # 실행 버튼
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
                        jobs = parse_csv_and_jobs(Path(csv_path))
                        append_log(f"총 {len(jobs)}건 처리 시작...")
                        append_log(f"저장 위치: {save_dir_path}")
                        ytdlp_bin = resolve_ytdlp_bin()
                        # 선택된 매핑 CSV 사용
                        map_path_str = map_path_var.get().strip()
                        map_path = Path(map_path_str) if map_path_str else None
                        id_name = load_id_name_map(map_path)
                        success = 0
                        occ = {}
                        with ThreadPoolExecutor(max_workers=CONCURRENCY) as executor:
                            futures = []
                            for url, user_id, ymd in jobs:
                                display = id_name.get(user_id, "undefine")
                                key = (user_id, ymd)
                                occ[key] = occ.get(key, 0) + 1
                                out_dir = build_output_dir(save_dir_path, user_id, display, ymd, occ[key])
                                futures.append(executor.submit(run_yt_dlp, url, out_dir, ytdlp_bin))
                            for fut in as_completed(futures):
                                rc = fut.result()
                                if rc == 0:
                                    success += 1
                        append_log(f"완료: {success}/{len(jobs)} 성공")
                        messagebox.showinfo("완료", f"완료: {success}/{len(jobs)} 성공")
                    except Exception as e:
                        append_log(f"오류: {e}")
                        messagebox.showerror("오류", str(e))
                threading.Thread(target=worker, daemon=True).start()
            ttk.Button(btn_frame, text="시작", command=run_task).pack(side="left")

            app.mainloop()
        except Exception:
            # GUI 불가 시 CLI 폴백
            main()
    else:
        main()