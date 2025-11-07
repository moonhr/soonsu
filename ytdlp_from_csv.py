#!/usr/bin/env python3
import csv
import os
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path


BASE_DIR = Path("/Users/moonhyerim/soonsu")
CSV_PATH = BASE_DIR / "정샘물_ID .csv"
CONCURRENCY = 3
USE_BROWSER_COOKIES = os.environ.get("YTDLP_BROWSER", "chrome")  # "safari" | "chrome" | "none"


def normalize_date(raw: str) -> str:
    """
    다양한 한국어/축약 날짜를 yy.mm.dd 형식으로 변환.
    괄호 안 날짜가 있으면 우선 사용, 연도 없으면 올해 기준.
    예: '2024년 11월 10일'->'24.11.10', '24.6.29'->'24.06.29', '10월 20일'->'<올해>.10.20',
        '10.14'->'<올해>.10.14', '2일전(11월1일)'->'<올해>.11.01'
    """

    if not raw:
        return datetime.now().strftime("%y.%m.%d")

    text = raw.strip()

    # 괄호 안 날짜 우선
    m = re.search(r"\(([^\)]+)\)", text)
    if m:
        inner = m.group(1).strip()
        try:
            return normalize_date(inner)
        except Exception:
            pass

    # 1) 4자리 연도
    m = re.search(r"(20\d{2})[^0-9]?\s*(\d{1,2})[^0-9]?\s*(\d{1,2})", text)
    if m:
        y4 = int(m.group(1))
        mm = int(m.group(2))
        dd = int(m.group(3))
        return f"{y4 % 100:02d}.{mm:02d}.{dd:02d}"

    # 2) 2자리 연도 명시
    m = re.search(r"(\d{2})\s*년?[^0-9]?\s*(\d{1,2})\s*월?[^0-9]?\s*(\d{1,2})", text)
    if m:
        y2 = int(m.group(1))
        mm = int(m.group(2))
        dd = int(m.group(3))
        return f"{y2:02d}.{mm:02d}.{dd:02d}"

    # 3) 24.6.29 형태
    m = re.search(r"^(\d{2})[./-](\d{1,2})[./-](\d{1,2})$", text)
    if m:
        y2 = int(m.group(1))
        mm = int(m.group(2))
        dd = int(m.group(3))
        return f"{y2:02d}.{mm:02d}.{dd:02d}"

    # 4) 10.14 형태(연도 없음 -> 올해)
    m = re.search(r"^(\d{1,2})[./-](\d{1,2})$", text)
    if m:
        now = datetime.now()
        mm = int(m.group(1))
        dd = int(m.group(2))
        return f"{now.year % 100:02d}.{mm:02d}.{dd:02d}"

    # 5) '10월 20일' 또는 '10월 20'
    m = re.search(r"(\d{1,2})\s*월\s*(\d{1,2})\s*일?", text)
    if m:
        now = datetime.now()
        mm = int(m.group(1))
        dd = int(m.group(2))
        return f"{now.year % 100:02d}.{mm:02d}.{dd:02d}"

    # 6) '7월 5' (일 생략) 대응
    m = re.search(r"(\d{1,2})\s*월\s*(\d{1,2})", text)
    if m:
        now = datetime.now()
        mm = int(m.group(1))
        dd = int(m.group(2))
        return f"{now.year % 100:02d}.{mm:02d}.{dd:02d}"

    # 7) '10 30일' / '10 30'
    m = re.search(r"^(\d{1,2})\s+(\d{1,2})\s*일?$", text)
    if m:
        now = datetime.now()
        mm = int(m.group(1))
        dd = int(m.group(2))
        return f"{now.year % 100:02d}.{mm:02d}.{dd:02d}"

    # 기본: 오늘 날짜
    return datetime.now().strftime("%y.%m.%d")


def run_yt_dlp(url: str, out_dir: Path) -> int:
    out_dir.mkdir(parents=True, exist_ok=True)

    cmd = [
        "yt-dlp",
        "-P", str(out_dir),
        "-o", "%(title)s [%(id)s].%(ext)s",
        "--no-overwrites",
        "--retries", "10",
        "--fragment-retries", "10",
        "-N", "8",
    ]

    if USE_BROWSER_COOKIES and USE_BROWSER_COOKIES.lower() != "none":
        cmd += ["--cookies-from-browser", USE_BROWSER_COOKIES]

    cmd.append(url)

    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    output = proc.stdout or ""
    print(f"[yt-dlp] {url}\n" + output)

    # 동영상 포맷이 없으면(사진 게시물) 썸네일 저장으로 폴백
    if proc.returncode != 0 and "No video formats found" in output:
        img_cmd = [
            "yt-dlp",
            "-P", str(out_dir),
            "-o", "%(title)s [%(id)s].%(ext)s",
            "--skip-download",
            "--write-thumbnail",
            "--convert-thumbnails", "jpg",
        ]
        if USE_BROWSER_COOKIES and USE_BROWSER_COOKIES.lower() != "none":
            img_cmd += ["--cookies-from-browser", USE_BROWSER_COOKIES]
        img_cmd.append(url)
        img_proc = subprocess.run(img_cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        print("[yt-dlp:image-fallback]\n" + (img_proc.stdout or ""))
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
            # Columns: 번호, 링크, ID, 날짜, ...
            url = (row[1] or "").strip()
            user_id = (row[2] or "").strip()
            date_raw = (row[3] or "").strip()
            if not url or not user_id:
                continue
            date_norm = normalize_date(date_raw)
            jobs.append((url, user_id, date_norm))
    return jobs


def main():
    csv_path = CSV_PATH
    browser_choice = USE_BROWSER_COOKIES
    # CLI: ytdlp_from_csv.py [csv_path] [browser]
    if len(sys.argv) > 1:
        csv_path = Path(sys.argv[1])
    if len(sys.argv) > 2:
        browser_choice = sys.argv[2].lower()
        globals()["USE_BROWSER_COOKIES"] = browser_choice
    if not csv_path.exists():
        print(f"CSV 파일이 존재하지 않습니다: {csv_path}")
        sys.exit(1)

    jobs = parse_csv_and_jobs(csv_path)
    if not jobs:
        print("다운로드할 항목이 없습니다.")
        return

    print(f"총 {len(jobs)}건 처리 예정.")

    futures = []
    with ThreadPoolExecutor(max_workers=CONCURRENCY) as executor:
        for url, user_id, ymd in jobs:
            out_dir = BASE_DIR / user_id / ymd
            futures.append(executor.submit(run_yt_dlp, url, out_dir))

        success = 0
        for fut in as_completed(futures):
            rc = fut.result()
            if rc == 0:
                success += 1

    print(f"완료: {success}/{len(jobs)} 성공")


if __name__ == "__main__":
    main()


