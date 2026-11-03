# -*- coding: utf-8 -*-
"""
GFA 클라우드 수집기 (GitHub Actions, 매시간)
────────────────────────────────────────────────────────────
- NAVER_STATE_JSON(Secret)으로 네이버 세션 주입 → 당일 포함 최근 N일 GFA 리포트 다운로드
- 구글시트 'GFA_원본' 탭에 반영 (수집 기간 행은 교체, 나머지 보존 + 컬럼 합집합)
- 각 행에 '수집시각'(KST) 기록 → 봇이 "GFA HH시 기준" 표시에 사용
- PC RPA(gfa_collect.py)를 대체. 시트 반영 로직은 동일.

환경변수:
  NAVER_STATE_JSON          (필수) 네이버 세션(storageState) JSON 내용
  GCP_SERVICE_ACCOUNT_JSON  (필수) 구글 서비스계정 JSON 내용
  SPREADSHEET_ID            (선택) 기본값 아래 하드코딩
  AD_ACCOUNT_ID             (선택) 기본 12357
  SHEET_TAB                 (선택) 기본 GFA_원본
  DAYS_BACK                 (선택) 기본 2 → (오늘-2 ~ 오늘) 3일 창 (누락분 자동 복구)
────────────────────────────────────────────────────────────
"""
import os, sys, re, time, zipfile, datetime, shutil

BASE = os.path.dirname(os.path.abspath(__file__))
DL_DIR = os.path.join(BASE, "_dl")
SHOT_DIR = os.path.join(BASE, "screenshots")
STATE_PATH = os.path.join(BASE, "naver_state.json")

AD_ACCOUNT_ID = os.environ.get("AD_ACCOUNT_ID", "12357").strip()
SHEET_TAB = os.environ.get("SHEET_TAB", "GFA_원본").strip()
SPREADSHEET_ID = os.environ.get(
    "SPREADSHEET_ID", "16IkobW7-6-XT7KOvY4MyX7ype35MIaVpGI7Xhb7XESQ").strip()
DAYS_BACK = int(os.environ.get("DAYS_BACK", "2"))
REPORT_WAIT_SEC = 480
POLL = 8

SHOW_COLS = (
    "result,sales_per_result,sales,schedule,imp_count,cpm,click_count,cpc,ctr,"
    "conv_count,install_conv_count,iap_conv_count,wishlist_conv_count,purchase_conv_count,"
    "join_conv_count,cart_conv_count,reserve_conv_count,subscribe_conv_count,"
    "schedule_conv_count,content_conv_count,level_conv_count,tutorial_conv_count,"
    "etc_conv_count,etc02_conv_count,etc03_conv_count,etc04_conv_count,etc05_conv_count,"
    "etc06_conv_count,etc07_conv_count,etc08_conv_count,etc09_conv_count,etc10_conv_count,"
    "conv_sales_krw,purchase_conv_sales_krw,join_conv_sales_krw,cart_conv_sales_krw,"
    "reserve_conv_sales_krw,install_conv_sales_krw,iap_conv_sales_krw,wishlist_conv_sales_krw,"
    "subscribe_conv_sales_krw,schedule_conv_sales_krw,content_sales_krw,level_conv_sales_krw,"
    "tutorial_conv_sales_krw,etc_conv_sales_krw,etc02_conv_sales_krw,etc03_conv_sales_krw,"
    "etc04_conv_sales_krw,etc05_conv_sales_krw,etc06_conv_sales_krw,etc07_conv_sales_krw,"
    "etc08_conv_sales_krw,etc09_conv_sales_krw,etc10_conv_sales_krw,"
    "cvr,sales_per_conversion,roas,purchase_roas"
)


def log(m):
    print(m, flush=True)


def kst_now():
    return datetime.datetime.utcnow() + datetime.timedelta(hours=9)


def shot(page, name):
    try:
        os.makedirs(SHOT_DIR, exist_ok=True)
        page.screenshot(path=os.path.join(SHOT_DIR, name + ".png"), full_page=True)
    except Exception:
        pass


def report_url(acc, since, until):
    from urllib.parse import quote
    return (
        f"https://ads.naver.com/manage/ad-accounts/{acc}/da/report/performance"
        f"?adUnit=CREATIVE&page=1&filterOptions=%5B%5D"
        f"&showColList={quote(SHOW_COLS, safe='')}"
        f"&dateRange={since.isoformat()}%2C{until.isoformat()}"
        f"&dateUnit=DAY&placeUnit=TOTAL&audience=TOTAL"
    )


def click_first(page, selectors, what, timeout=8000):
    for sel in selectors:
        try:
            loc = sel(page)
            loc.wait_for(state="visible", timeout=timeout)
            loc.click()
            log(f"   클릭: {what}")
            return True
        except Exception:
            continue
    return False


def click_exact(page, text, what, timeout=15000, prefer_last=False):
    pat = re.compile(rf"^\s*{re.escape(text)}\s*$")

    def pick(loc):
        return loc.last if prefer_last else loc.first

    cands = [
        lambda p: p.get_by_role("button", name=text, exact=True),
        lambda p: pick(p.locator("button").filter(has_text=pat)),
        lambda p: p.get_by_role("link", name=text, exact=True),
        lambda p: pick(p.locator("a").filter(has_text=pat)),
        lambda p: pick(p.get_by_text(pat)),
    ]
    return click_first(page, cands, what, timeout)


def is_list_modal_open(page):
    for t in ["파일 생성 일시", "요청 일시", "전체 선택"]:
        try:
            if page.get_by_text(re.compile(rf"^\s*{t}\s*$")).last.is_visible():
                return True
        except Exception:
            continue
    return False


def download_report(since, until):
    from playwright.sync_api import sync_playwright
    shutil.rmtree(DL_DIR, ignore_errors=True)
    os.makedirs(DL_DIR, exist_ok=True)
    zip_path = None
    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=True, args=["--disable-blink-features=AutomationControlled"])
        ctx = browser.new_context(
            storage_state=STATE_PATH, accept_downloads=True,
            viewport={"width": 1600, "height": 1000},
            locale="ko-KR", timezone_id="Asia/Seoul",
            user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/127.0.0.0 Safari/537.36"),
        )
        page = ctx.new_page()
        try:
            url = report_url(AD_ACCOUNT_ID, since, until)
            log(f"리포트 접속: {since} ~ {until}")
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(5000)
            if "nid.naver.com" in page.url or "login" in page.url.lower():
                shot(page, "login_required")
                raise RuntimeError(
                    "세션 만료 — 네이버 로그인 필요. PC에서 export_state.bat 다시 실행 후 "
                    "GitHub Secret(NAVER_STATE_JSON) 갱신 필요.")
            try:
                page.wait_for_load_state("networkidle", timeout=90000)
            except Exception:
                pass
            page.wait_for_timeout(3000)
            try:
                page.mouse.wheel(0, 20000); page.wait_for_timeout(1500)
            except Exception:
                pass
            if is_list_modal_open(page):
                click_exact(page, "확인", "열려있던 목록 닫기", timeout=8000, prefer_last=True)
                page.wait_for_timeout(1500)
            if not click_exact(page, "다운로드 요청", "다운로드 요청", timeout=90000):
                shot(page, "no_request_btn")
                raise RuntimeError("'다운로드 요청' 버튼을 찾지 못함")
            page.wait_for_timeout(2000)
            click_exact(page, "확인", "요청 확인", timeout=20000, prefer_last=True)
            page.wait_for_timeout(3000)
            if is_list_modal_open(page):
                click_exact(page, "확인", "요청목록 닫기", timeout=8000, prefer_last=True)
            log("리포트 생성 대기 중...")
            started = datetime.datetime.now()
            deadline = time.time() + REPORT_WAIT_SEC
            EXACT_DL = re.compile(r"^\s*다운로드\s*$")
            while time.time() < deadline:
                if not is_list_modal_open(page):
                    click_exact(page, "다운로드 요청 목록", "요청 목록 열기", timeout=15000)
                    page.wait_for_timeout(2500)
                links = page.get_by_text(EXACT_DL)
                try:
                    n = links.count()
                except Exception:
                    n = 0
                log(f"   완료된 리포트 {n}건")
                clicked = False
                if n > 0:
                    for i in range(min(n, 3)):
                        try:
                            with page.expect_download(timeout=90000) as di:
                                links.nth(i).click()
                            d = di.value
                            zip_path = os.path.join(DL_DIR, d.suggested_filename or "report.zip")
                            d.save_as(zip_path)
                            log(f"   다운로드 완료: {os.path.basename(zip_path)}")
                            clicked = True
                            break
                        except Exception:
                            continue
                if clicked:
                    break
                click_exact(page, "확인", "목록 닫기", timeout=6000, prefer_last=True)
                el = int((datetime.datetime.now() - started).total_seconds())
                log(f"   아직 준비중... ({el}초 경과)")
                page.wait_for_timeout(POLL * 1000)
            shot(page, "after_download")
        except Exception:
            shot(page, "error")
            raise
        finally:
            ctx.close(); browser.close()
    if not zip_path:
        raise RuntimeError(f"{REPORT_WAIT_SEC}초 내 리포트 생성 실패")
    return zip_path


def extract_csv(zip_path):
    with zipfile.ZipFile(zip_path) as z:
        names = [n for n in z.namelist() if n.lower().endswith(".csv")]
        if not names:
            raise RuntimeError(f"zip 안에 CSV 없음: {z.namelist()}")
        z.extract(names[0], DL_DIR)
        return os.path.join(DL_DIR, names[0])


def norm_date(v):
    """'2026.08.08.' → '2026-08-08'"""
    s = str(v).strip().rstrip(".")
    return s.replace(".", "-").replace("/", "-")


def upload_to_sheet(csv_path, since, until):
    import json
    import pandas as pd
    import gspread
    from google.oauth2.service_account import Credentials

    new = pd.read_csv(csv_path, encoding="utf-8-sig", dtype=str).fillna("")
    if new.empty:
        log("수집 결과 0행 — 시트 반영 생략 (해당 기간 집행 없음)")
        return 0
    log(f"수집 결과: {len(new)}행 / {len(new.columns)}컬럼")

    required = ["구매완료 수", "총 전환매출액"]
    missing = [c for c in required if c not in new.columns]
    if missing:
        raise RuntimeError("리포트에 필수 지표 없음: " + ", ".join(missing))

    # 수집시각(KST) 기록 — 봇의 "GFA HH시 기준" 표시용
    collected = kst_now().strftime("%Y-%m-%d %H:%M")
    new["수집시각"] = collected

    sa_raw = os.environ.get("GCP_SERVICE_ACCOUNT_JSON", "").strip()
    if not sa_raw:
        raise RuntimeError("GCP_SERVICE_ACCOUNT_JSON Secret이 비어있음")
    info = json.loads(sa_raw)
    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    creds = Credentials.from_service_account_info(info, scopes=scopes)
    gc = gspread.authorize(creds)
    sh = gc.open_by_key(SPREADSHEET_ID)
    try:
        ws = sh.worksheet(SHEET_TAB)
    except Exception:
        ws = sh.add_worksheet(title=SHEET_TAB, rows=1000, cols=max(30, len(new.columns)))
        log(f"'{SHEET_TAB}' 탭을 새로 만들었습니다.")

    old_vals = ws.get_all_values()
    if old_vals and len(old_vals) > 1:
        old = pd.DataFrame(old_vals[1:], columns=old_vals[0]).fillna("")
        if "기간" in old.columns:
            d = old["기간"].map(norm_date)
            keep = ~d.between(since.isoformat(), until.isoformat())
            removed = int((~keep).sum())
            old = old[keep]
            log(f"기존 시트에서 {since}~{until} 구간 {removed}행 제거 후 교체")
        cols = list(new.columns) + [c for c in old.columns if c not in new.columns]
        old = old.reindex(columns=cols, fill_value="")
        new = new.reindex(columns=cols, fill_value="")
        out = pd.concat([old, new], ignore_index=True)
    else:
        out = new

    ws.clear()
    ws.update([out.columns.tolist()] + out.astype(str).values.tolist(),
              value_input_option="RAW")
    log(f"시트 반영 완료: 총 {len(out)}행 → '{SHEET_TAB}' (수집시각 {collected})")
    return len(new)


def main():
    state = os.environ.get("NAVER_STATE_JSON", "").strip()
    if not state:
        log("FAIL: NAVER_STATE_JSON Secret 비어있음"); sys.exit(1)
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        f.write(state)

    today = kst_now().date()
    since = today - datetime.timedelta(days=DAYS_BACK)
    until = today
    log(f"=== GFA 수집 시작 (KST {kst_now():%Y-%m-%d %H:%M}) : {since} ~ {until} ===")

    zip_path = download_report(since, until)
    csv_path = extract_csv(zip_path)
    n = upload_to_sheet(csv_path, since, until)
    log(f"=== 완료: {n}행 반영 ===")


if __name__ == "__main__":
    main()
