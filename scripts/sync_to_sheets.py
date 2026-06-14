# -*- coding: utf-8 -*-
"""
Google Sheets 동기화 스크립트
통합RD_마스터.csv -> Apps Script 웹 앱 -> Google Sheets
최근 6개월 데이터만 전송 (중복 제거 포함)
"""
import os, sys, csv, json, datetime, requests

WEBAPP_URL = os.environ["SHEETS_WEBAPP_URL"]
SECRET_KEY = os.environ["SHEETS_SECRET_KEY"]
DATA_DIR   = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
CSV_PATH   = os.path.join(DATA_DIR, "통합RD_마스터.csv")

if not os.path.exists(CSV_PATH):
    print(f"CSV 없음: {CSV_PATH} -> 스킵")
    sys.exit(0)

cutoff = (datetime.date.today() - datetime.timedelta(days=180)).isoformat()

rows      = []
headers   = None
dates_set = set()

with open(CSV_PATH, encoding="utf-8-sig") as f:
    reader  = csv.reader(f)
    headers = next(reader)
    for row in reader:
        if row and row[0] >= cutoff:
            rows.append(row)
            dates_set.add(row[0])

print(f"전송 대상: {len(rows)}행 ({len(dates_set)}일치, {cutoff} 이후)")

payload = {
    "secret":  SECRET_KEY,
    "headers": headers,
    "rows":    rows,
    "dates":   list(dates_set),
}

try:
    resp = requests.post(WEBAPP_URL, json=payload, timeout=120)
    resp.raise_for_status()
    data = resp.json()
except Exception as e:
    print(f"전송 실패: {e}")
    sys.exit(1)

if data.get("status") != "ok":
    print(f"Apps Script 오류: {data}")
    sys.exit(1)

print(f"동기화 완료: {data.get('rows_written')}행 전송됨")
