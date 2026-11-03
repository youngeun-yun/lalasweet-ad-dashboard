# -*- coding: utf-8 -*-
"""
GFA 클라우드 수집 테스트 (GitHub Actions 전용)
────────────────────────────────────────────────────────────
목적: NAVER_STATE_JSON(Secret)으로 네이버 세션을 주입해, 미국 IP(깃헙 러너)에서
      네이버 GFA 리포트를 '당일 포함' 기준으로 실제 다운로드까지 되는지 검증.
      → 구글시트에는 쓰지 않음. CSV 컬럼/행만 확인 후 PASS/FAIL 출력.
      → 스크린샷은 screenshots/ 에 저장(아티팩트 업로드용).

환경변수:
  NAVER_STATE_JSON  (필수) : export_naver_state.py 로 만든 naver_state.json 내용 전체
  AD_ACCOUNT_ID     (선택) : 기본 12357

종료코드: 0=PASS, 2=세션거부(로그인튕김), 3=버튼못찾음, 4=생성타임아웃, 그외=오류
────────────────────────────────────────────────────────────
"""
import os, sys, re, time, zipfile, datetime, csv

BASE = os.path.dirname(os.path.abspath(__file__))
DL_DIR = os.path.join(BASE, "_dl")
SHOT_DIR = os.path.join(BASE, "screenshots")
STATE_PATH = os.path.join(BASE, "naver_state.json")
AD_ACCOUNT_ID = os.environ.get("AD_ACCOUNT_ID", "12357").strip()
REPORT_WAIT_SEC = 420
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


def main():
    state = os.environ.get("NAVER_STATE_JSON", "").strip()
    if not state:
        log("FAIL: NAVER_STATE_JSON Secret이 비어있음"); sys.exit(1)
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        f.write(state)
    os.makedirs(DL_DIR, exist_ok=True)

    # 깃헙 러너는 UTC → KST(+9h) 기준 날짜로 보정. 당일 포함 위해 전일~당일 2일 조회.
    today = (datetime.datetime.utcnow() + datetime.timedelta(hours=9)).date()
    since = today - datetime.timedelta(days=1)
    until = today

    from playwright.sync_api import sync_playwright
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
            log(f"[1] 리포트 접속 ({since} ~ {until}, 당일 포함)...")
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(5000)
            shot(page, "01_after_goto")

            if "nid.naver.com" in page.url or "login" in page.url.lower():
                shot(page, "02_login_redirect")
                log("FAIL(2): 세션 거부됨 — 미국 IP에서 네이버 로그인으로 튕김 (nid.naver.com)")
                log("   → GitHub Actions(미국 IP) 경로 불가. 한국 VM/미니PC 경로로 전환 필요.")
                ctx.close(); browser.close(); sys.exit(2)
            log("[2] 로그인 유지됨 ✓ (리포트 페이지 진입 성공)")

            try:
                page.wait_for_load_state("networkidle", timeout=90000)
            except Exception:
                pass
            page.wait_for_timeout(3000)
            try:
                page.mouse.wheel(0, 20000); page.wait_for_timeout(1500)
            except Exception:
                pass
            shot(page, "03_report_table")

            if is_list_modal_open(page):
                click_exact(page, "확인", "열려있던 목록 닫기", timeout=8000, prefer_last=True)
                page.wait_for_timeout(1500)

            if not click_exact(page, "다운로드 요청", "다운로드 요청", timeout=90000):
                shot(page, "04_no_request_btn")
                log("FAIL(3): '다운로드 요청' 버튼 못 찾음 (UI 변경/권한/미로그인 가능). 스크린샷 확인.")
                ctx.close(); browser.close(); sys.exit(3)
            page.wait_for_timeout(2000)
            click_exact(page, "확인", "요청 확인", timeout=20000, prefer_last=True)
            page.wait_for_timeout(3000)
            if is_list_modal_open(page):
                click_exact(page, "확인", "요청목록 닫기", timeout=8000, prefer_last=True)
            log("[3] 다운로드 요청 수락됨 ✓ — 리포트 생성 대기...")

            deadline = time.time() + REPORT_WAIT_SEC
            started = datetime.datetime.now()
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
            shot(page, "05_after_download")
        except Exception as e:
            shot(page, "99_error")
            log(f"FAIL: 예외 — {type(e).__name__}: {e}")
            ctx.close(); browser.close(); sys.exit(7)
        ctx.close(); browser.close()

    if not zip_path:
        log("FAIL(4): 리포트 생성/다운로드 타임아웃"); sys.exit(4)

    with zipfile.ZipFile(zip_path) as z:
        csvs = [n for n in z.namelist() if n.lower().endswith(".csv")]
        if not csvs:
            log("FAIL(5): zip 안에 CSV 없음"); sys.exit(5)
        z.extract(csvs[0], DL_DIR)
        csv_path = os.path.join(DL_DIR, csvs[0])

    with open(csv_path, encoding="utf-8-sig") as f:
        rows = list(csv.reader(f))
    if not rows:
        log("FAIL(6): CSV 빈 파일"); sys.exit(6)
    header, data = rows[0], rows[1:]
    need = ["구매완료 수", "총 전환매출액", "총비용", "기간", "캠페인 이름"]
    missing = [c for c in need if c not in header]
    log(f"[4] CSV 다운로드 ✓ : {len(data)}행, {len(header)}컬럼")
    if missing:
        log(f"   ⚠️ 필수 컬럼 없음: {missing} → GFA 지표설정(setup_columns) 필요할 수 있음")
    log("")
    log("PASS ✅ : 미국 IP(GitHub Actions)에서 당일 포함 GFA 다운로드까지 성공.")
    if not missing and data:
        ci, gi, ei = header.index("총비용"), header.index("기간"), header.index("캠페인 이름")
        tot, days = 0, set()
        for r in data:
            try:
                tot += int(float(str(r[ci]).replace(",", "") or 0))
            except Exception:
                pass
            if gi < len(r):
                days.add(str(r[gi]).strip())
        log(f"   총비용 합계 ≈ {tot:,}원 / 포함 기간값: {sorted(days)[:5]}")
        log(f"   샘플 캠페인: {data[0][ei] if ei < len(data[0]) else '-'}")


if __name__ == "__main__":
    main()
