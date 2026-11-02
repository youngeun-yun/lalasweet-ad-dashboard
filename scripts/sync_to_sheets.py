# -*- coding: utf-8 -*-
import os, sys, csv, json
import gspread
from google.oauth2.service_account import Credentials

SPREADSHEET_ID = os.environ["SPREADSHEET_ID"]
GCP_SA_JSON = os.environ["GCP_SERVICE_ACCOUNT_JSON"]
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
CSV_PATH = os.path.join(DATA_DIR, "통합RD_마스터.csv")
SHEET_NAME = "통합RD_원본"

# 2026-11-02: build_rd.py 가 이미 시트(통합RD_원본)에 직접 기록한다.
# 이 스크립트는 하위호환용으로 남겨두되, CSV가 없으면 **반드시 스킵**해야 한다.
# (빈/부분 CSV로 시트를 clear() 하면 과거 데이터가 통째로 날아간 사고가 있었음)
if not os.path.exists(CSV_PATH):
    print("CSV 없음 -> 스킵 (build_rd.py 가 이미 시트에 기록함)")
    sys.exit(0)

creds_info = json.loads(GCP_SA_JSON)
creds = Credentials.from_service_account_info(creds_info, scopes=["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"])
client = gspread.authorize(creds)

spreadsheet = client.open_by_key(SPREADSHEET_ID)
try:
    sheet = spreadsheet.worksheet(SHEET_NAME)
except gspread.WorksheetNotFound:
    sheet = spreadsheet.add_worksheet(title=SHEET_NAME, rows=10000, cols=30)

with open(CSV_PATH, encoding="utf-8-sig") as f:
    rows = list(csv.reader(f))

if not rows or len(rows) < 2:
    print("데이터 없음 -> 스킵")
    sys.exit(0)

# 안전장치: 기존 시트보다 행이 급감하면 덮어쓰지 않는다
try:
    existing = len(sheet.get_all_values())
except Exception:
    existing = 0
if existing > 1000 and len(rows) < existing * 0.5:
    print(f"중단: 새 데이터({len(rows)}행)가 기존 시트({existing}행)의 절반 미만 -> 덮어쓰지 않음")
    sys.exit(0)

sheet.clear()
sheet.update(rows, value_input_option="USER_ENTERED")
print(f"동기화 완료: {len(rows)-1}행 -> {SHEET_NAME}")
