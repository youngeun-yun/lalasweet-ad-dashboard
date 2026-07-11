# -*- coding: utf-8 -*-
"""
단쉐(SK) 시간대별 성과 수집 → Google Sheets (단쉐_시간대별_원본)
- 기본: 오늘(KST) 수집 / HOURLY_SINCE·HOURLY_UNTIL 환경변수 지정 시 해당 범위 백필
- (날짜 × 시간 × 캠페인 × 광고그룹 × 소재) 단위로 누적 저장
- 수집 범위에 해당하는 날짜 행만 교체, 다른 날짜는 보존
- 저장소 커밋 없음 (시트에 직접 기록)
"""
import os, sys, time, json, datetime
import requests
import gspread
from google.oauth2.service_account import Credentials

ACCESS_TOKEN    = os.environ["META_ACCESS_TOKEN"]
AD_ACCOUNT_ID   = os.environ["META_AD_ACCOUNT_ID"]
SPREADSHEET_ID  = os.environ["SPREADSHEET_ID"]
GCP_SA_JSON     = os.environ["GCP_SERVICE_ACCOUNT_JSON"]
SLACK_BOT_TOKEN = os.environ.get("SLACK_BOT_TOKEN", "")
SLACK_USER_ID   = os.environ.get("SLACK_USER_ID", "")

API_VERSION = "v21.0"
BASE        = f"https://graph.facebook.com/{API_VERSION}"
SHEET_NAME  = "단쉐_시간대별_원본"
HEADER      = ["날짜", "시간", "캠페인명", "광고그룹명", "소재명",
               "노출", "클릭", "광고비", "구매", "수집시각"]

KST = datetime.timezone(datetime.timedelta(hours=9))

def log(msg):
    stamp = datetime.datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{stamp}] {msg}")

def send_slack(text):
    if not SLACK_BOT_TOKEN:
        return
    try:
        r = requests.post(
            "https://slack.com/api/chat.postMessage",
            headers={"Authorization": f"Bearer {SLACK_BOT_TOKEN}"},
            json={"channel": SLACK_USER_ID, "text": text},
            timeout=30,
        ).json()
        if not r.get("ok"):
            log(f"슬랙 전송 실패: {r}")
    except Exception as e:
        log(f"슬랙 전송 예외: {e}")

def die(msg):
    log(f"!!! 실패: {msg}")
    send_slack(f":x: *단쉐 시간대별 수집 실패*\n• 사유: {msg}")
    sys.exit(1)

RETRY_DELAYS = [10, 30, 60, 120]

def api_call(method, url, **kw):
    last = None
    for attempt, delay in enumerate([0] + RETRY_DELAYS):
        if delay:
            log(f"   재시도 대기 {delay}s... (시도 {attempt}/{len(RETRY_DELAYS)})")
            time.sleep(delay)
        try:
            resp = requests.request(method, url, timeout=180, **kw)
            data = resp.json()
        except Exception as e:
            last = f"네트워크/파싱 오류: {e}"
            log(f"   {last} -> 재시도")
            continue
        if "error" not in data:
            return data
        err  = data["error"]
        last = err
        code = err.get("code")
        transient = bool(err.get("is_transient")) or code in (1, 2, 4, 17, 341, 613, 80000, 80003, 80004)
        log(f"   API 오류(code {code}): {err.get('message')} -> {'재시도' if transient else '영구 오류, 중단'}")
        if not transient:
            die(f"영구 API 오류: {err}")
    die(f"재시도 모두 소진: {last}")

# ── 수집 범위 ─────────────────────────────────────────────────
today = datetime.datetime.now(KST).date()
since = os.environ.get("HOURLY_SINCE", "").strip() or str(today)
until = os.environ.get("HOURLY_UNTIL", "").strip() or str(today)
log(f"수집 범위: {since} ~ {until} (시간대별, SK 소재)")

# ── Meta 인사이트 (시간대별 breakdown) ────────────────────────
fields = "campaign_name,adset_name,ad_name,impressions,spend,inline_link_clicks,actions"
filtering = [
    {"field": "impressions", "operator": "GREATER_THAN", "value": 0},
    {"field": "ad.name",     "operator": "CONTAIN",      "value": "SK"},
]
params = {
    "level":          "ad",
    "fields":         fields,
    "breakdowns":     json.dumps(["hourly_stats_aggregated_by_advertiser_time_zone"]),
    "time_range":     json.dumps({"since": since, "until": until}),
    "time_increment": 1,
    "filtering":      json.dumps(filtering),
    "access_token":   ACCESS_TOKEN,
}

run = api_call("POST", f"{BASE}/{AD_ACCOUNT_ID}/insights", data=params)
report_id = run.get("report_run_id")
if not report_id:
    die(f"report_run_id 없음: {run}")
log(f"리포트 작업 생성: {report_id}")

while True:
    s  = api_call("GET", f"{BASE}/{report_id}", params={"access_token": ACCESS_TOKEN})
    st = s.get("async_status")
    log(f"  {s.get('async_percent_completion')}% / {st}")
    if st == "Job Completed":
        break
    if st in ("Job Failed", "Job Skipped"):
        die(f"리포트 작업 실패: {s}")
    time.sleep(5)

rows = []
url  = f"{BASE}/{report_id}/insights"
qp   = {"limit": 500, "access_token": ACCESS_TOKEN}
page = 0
while url:
    resp  = api_call("GET", url, params=qp)
    batch = resp.get("data", [])
    rows.extend(batch)
    page += 1
    paging = resp.get("paging", {})
    url = paging.get("next")
    qp  = {}
    log(f"  페이지 {page}: +{len(batch)}행 (누적 {len(rows)}행)")

# ── 행 변환 ───────────────────────────────────────────────────
PURCHASE_TYPES = [
    "offsite_conversion.fb_pixel_purchase", "omni_purchase",
    "purchase", "onsite_web_purchase",
]

def purchase_val(actions):
    d = {a.get("action_type"): a.get("value") for a in actions or []}
    for t in PURCHASE_TYPES:
        if t in d:
            try:
                return int(float(d[t]))
            except (TypeError, ValueError):
                return 0
    return 0

collected_at = datetime.datetime.now(KST).strftime("%Y-%m-%d %H:%M")
out = []
for r in rows:
    hour_raw = str(r.get("hourly_stats_aggregated_by_advertiser_time_zone", ""))
    try:
        hour = int(hour_raw[:2])
    except ValueError:
        continue
    out.append([
        r.get("date_start", ""),
        hour,
        r.get("campaign_name", ""),
        r.get("adset_name", ""),
        r.get("ad_name", ""),
        int(float(r.get("impressions", 0) or 0)),
        int(float(r.get("inline_link_clicks", 0) or 0)),
        float(r.get("spend", 0) or 0),
        purchase_val(r.get("actions")),
        collected_at,
    ])
log(f"변환 완료: {len(out)}행")

# ── Google Sheets 기록 (수집 범위 날짜 행 교체) ────────────────
creds = Credentials.from_service_account_info(
    json.loads(GCP_SA_JSON),
    scopes=["https://spreadsheets.google.com/feeds",
            "https://www.googleapis.com/auth/drive"],
)
client = gspread.authorize(creds)
spreadsheet = client.open_by_key(SPREADSHEET_ID)
try:
    sheet = spreadsheet.worksheet(SHEET_NAME)
except gspread.WorksheetNotFound:
    sheet = spreadsheet.add_worksheet(title=SHEET_NAME, rows=1000, cols=len(HEADER))
    sheet.update([HEADER])

existing = sheet.get_all_values()
keep = []
if len(existing) > 1:
    for row in existing[1:]:
        if not row or not row[0]:
            continue
        if since <= row[0] <= until:
            continue  # 수집 범위 날짜는 새 데이터로 교체
        keep.append(row)

def sort_key(row):
    try:
        return (str(row[0]), int(float(row[1])))
    except (ValueError, IndexError):
        return (str(row[0]) if row else "", 0)

merged = keep + [[str(v) for v in r] for r in out]
merged.sort(key=sort_key)

sheet.clear()
sheet.update([HEADER] + merged, value_input_option="USER_ENTERED")
log(f"시트 기록 완료: 교체 {len(out)}행 / 보존 {len(keep)}행 / 총 {len(merged)}행 -> {SHEET_NAME}")
