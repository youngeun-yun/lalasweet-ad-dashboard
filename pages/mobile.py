# -*- coding: utf-8 -*-
"""
라라스윗 실시간 모바일 페이지
- 업로드 위치: pages/mobile.py (레포 루트에 pages 폴더 생성)
- 접속 주소: 기존 대시보드 주소 뒤에 /mobile
- 데이터: 단쉐_시간대별_원본 / 팝콘_시간대별_원본 (시간대별 시트)
"""
import time
import requests
import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials

st.set_page_config(
    page_title="라라스윗 실시간",
    page_icon="🍬",
    layout="centered",
    initial_sidebar_state="collapsed",
)

st.markdown("""
<style>
    .block-container { padding-top: 2.2rem; padding-bottom: 1rem; max-width: 480px; }
    [data-testid="stMetricValue"] { font-size: 1.25rem; font-weight: 600; }
    [data-testid="stMetricLabel"] { font-size: 0.72rem; color: #888; }
    .stButton button p { white-space: nowrap; }
    footer { visibility: hidden; }
</style>
""", unsafe_allow_html=True)

# =============================================================
# GitHub Actions 트리거 (실시간 업데이트 버튼)
# =============================================================
GH_OWNER         = "youngeun-yun"
GH_REPO          = "lalasweet-ad-dashboard"
REFRESH_WORKFLOW = "refresh.yml"

def _gh_headers():
    return {
        "Authorization": f"Bearer {st.secrets['github_token']}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

def trigger_refresh(mode):
    url = (f"https://api.github.com/repos/{GH_OWNER}/{GH_REPO}"
           f"/actions/workflows/{REFRESH_WORKFLOW}/dispatches")
    try:
        r = requests.post(url, headers=_gh_headers(),
                          json={"ref": "main", "inputs": {"mode": mode}}, timeout=30)
    except Exception as e:
        return False, f"요청 실패: {e}"
    if r.status_code == 204:
        return True, ""
    return False, f"HTTP {r.status_code}: {r.text[:200]}"

def latest_refresh_run():
    url = (f"https://api.github.com/repos/{GH_OWNER}/{GH_REPO}"
           f"/actions/workflows/{REFRESH_WORKFLOW}/runs")
    try:
        r = requests.get(url, headers=_gh_headers(),
                         params={"per_page": 1}, timeout=30)
        runs = r.json().get("workflow_runs", [])
        return runs[0] if runs else None
    except Exception:
        return None

# =============================================================
# 데이터 로드
# =============================================================
@st.cache_data(ttl=300, show_spinner="불러오는 중...")
def load_hourly(sheet_name: str) -> pd.DataFrame:
    creds = Credentials.from_service_account_info(
        dict(st.secrets["gcp_service_account"]),
        scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"],
    )
    gc = gspread.authorize(creds)
    try:
        ws = gc.open_by_key(st.secrets["spreadsheet_id"]).worksheet(sheet_name)
    except Exception:
        return pd.DataFrame()
    dfh = pd.DataFrame(ws.get_all_records())
    if dfh.empty:
        return dfh
    dfh["날짜"] = pd.to_datetime(dfh["날짜"], errors="coerce")
    dfh["시간"] = pd.to_numeric(dfh["시간"], errors="coerce")
    for col in ["노출", "클릭", "광고비", "구매"]:
        if col in dfh.columns:
            dfh[col] = pd.to_numeric(dfh[col], errors="coerce").fillna(0)
    dfh = dfh.dropna(subset=["날짜", "시간"])
    if dfh.empty:
        return dfh
    dfh["시간"] = dfh["시간"].astype(int)
    return dfh

def mobile_table(rows) -> None:
    """총합계 고정 간결 테이블 (모바일용)"""
    cols = list(rows[0].keys())
    th = ("padding:6px 8px;text-align:left;background:#f0f2f6;"
          "border-bottom:2px solid #ddd;font-size:0.76rem;white-space:nowrap;")
    td = "padding:6px 8px;border-bottom:1px solid #eee;font-size:0.8rem;white-space:nowrap;"
    tf = ("padding:6px 8px;font-size:0.8rem;white-space:nowrap;"
          "background:#FFF0E6;color:#B84A00;font-weight:bold;border-top:2px solid #ddd;")
    hdr = "".join(f'<th style="{th}">{c}</th>' for c in cols)
    body = "".join(
        "<tr>" + "".join(f'<td style="{td}">{r[c]}</td>' for c in cols) + "</tr>"
        for r in rows[:-1]
    )
    tot = rows[-1]
    foot = "<tr>" + "".join(f'<td style="{tf}">{tot[c]}</td>' for c in cols) + "</tr>"
    st.markdown(
        '<div style="border:1px solid #e0e0e0;border-radius:8px;overflow:hidden;">'
        '<table style="width:100%;border-collapse:collapse;">'
        f'<thead><tr>{hdr}</tr></thead>'
        f'<tbody>{body}</tbody>'
        f'<tfoot>{foot}</tfoot>'
        '</table></div>',
        unsafe_allow_html=True,
    )

def hour_metrics(d: pd.DataFrame) -> dict:
    s = d["광고비"].sum()
    i = d["노출"].sum()
    c = d["클릭"].sum()
    v = d["구매"].sum()
    return {
        "spend": s, "imp": i, "clk": c, "conv": v,
        "ctr": c / i * 100 if i > 0 else 0,
        "cvr": v / c * 100 if c > 0 else 0,
        "cpc": s / c if c > 0 else 0,
        "cpa": s / v if v > 0 else 0,
    }

# =============================================================
# 화면
# =============================================================
st.markdown("### 🍬 라라스윗 실시간")

PRODUCTS = {"🥐 단쉐": "단쉐_시간대별_원본", "🍿 팝콘": "팝콘_시간대별_원본"}
prod = st.radio("제품", list(PRODUCTS.keys()), horizontal=True,
                label_visibility="collapsed", key="mb_prod")

dfh = load_hourly(PRODUCTS[prod])
if dfh.empty:
    st.info("시간대별 데이터가 아직 없습니다. 수집이 시작되면 표시됩니다.")
    st.stop()

_dates = sorted(dfh["날짜"].dt.strftime("%Y-%m-%d").unique().tolist(), reverse=True)
sel_date = st.selectbox("날짜", _dates, index=0, key="mb_date", label_visibility="collapsed")
d = dfh[dfh["날짜"].dt.strftime("%Y-%m-%d") == sel_date]

_last = dfh["수집시각"].astype(str).max() if "수집시각" in dfh.columns else ""
_today = pd.Timestamp.now(tz="Asia/Seoul").strftime("%Y-%m-%d")
_day_label = f"{sel_date} (오늘)" if sel_date == _today else sel_date
st.caption(f"🕐 {_day_label} · 마지막 수집 {_last} · 1시간마다 자동 갱신")

if d.empty:
    st.warning("선택한 날짜에 데이터가 없습니다.")
    st.stop()

# ── 실시간 업데이트 버튼 (자동 상태 표시 + 자동 반영) ──

def _mb_status():
    if not st.session_state.get("mb_active"):
        if st.session_state.get("mb_msg"):
            st.caption(st.session_state["mb_msg"])
        return
    started = st.session_state.get("mb_started", time.time())
    elapsed = int(time.time() - started)
    run = latest_refresh_run()
    cur = False
    if run is not None:
        try:
            cur = pd.to_datetime(run.get("created_at")).timestamp() >= started - 60
        except Exception:
            cur = False
    if cur and run.get("status") == "completed":
        st.session_state["mb_active"] = False
        if run.get("conclusion") == "success":
            st.cache_data.clear()
            done_at = pd.Timestamp.now(tz="Asia/Seoul").strftime("%H:%M")
            st.session_state["mb_msg"] = f"✅ 업데이트 완료 — 반영됨 ({done_at})"
        else:
            st.session_state["mb_msg"] = "❌ 업데이트 실패 — GitHub Actions 로그를 확인해주세요"
        st.rerun(scope="app")
    elif elapsed > 900:
        st.session_state["mb_active"] = False
        st.session_state["mb_msg"] = "⏱ 완료 확인을 중단했어요. GitHub Actions에서 상태를 확인해주세요."
        st.rerun(scope="app")
    else:
        st.caption(f"⏳ 업데이트 진행 중 ({elapsed // 60}분 {elapsed % 60}초 경과) — 완료되면 자동 반영됩니다")

if "github_token" not in st.secrets:
    st.caption("⚙️ 업데이트 버튼을 사용하려면 Streamlit secrets에 `github_token`을 추가해주세요.")
else:
    _active = st.session_state.get("mb_active", False)
    if st.button("⚡ 실시간 업데이트", disabled=_active, use_container_width=True,
                 help="오늘 데이터를 다시 수집합니다 (약 2~4분 소요, 완료 시 자동 반영)"):
        ok, err = trigger_refresh("today")
        if ok:
            st.session_state["mb_active"] = True
            st.session_state["mb_started"] = time.time()
            st.session_state.pop("mb_msg", None)
        else:
            st.session_state["mb_msg"] = f"❌ 실행 요청 실패: {err}"
        st.rerun()
    if st.session_state.get("mb_active"):
        st.fragment(_mb_status, run_every=10)()
    else:
        _mb_status()

st.markdown("")

k = hour_metrics(d)
_kpi_card = "background:#f7f7f9;border-radius:10px;padding:10px 12px;"
_kpi_lab  = "font-size:0.7rem;color:#888;margin:0;"
_kpi_val  = "font-size:1.15rem;font-weight:600;margin:2px 0 0;color:#222;"
_kpi_items = [
    ("💰 광고비", f"₩{int(k['spend']):,}"),
    ("🛒 구매",   f"{int(k['conv']):,}"),
    ("🎯 CPA",    f"₩{int(k['cpa']):,}"),
    ("📈 CTR",    f"{k['ctr']:.2f}%"),
]
_kpi_cells = "".join(
    f'<div style="{_kpi_card}"><p style="{_kpi_lab}">{_l}</p><p style="{_kpi_val}">{_v}</p></div>'
    for _l, _v in _kpi_items
)
st.markdown(
    f'<div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:6px;">{_kpi_cells}</div>',
    unsafe_allow_html=True,
)

st.markdown("**⏰ 시간대별 성과**")
view = st.radio("지표", ["기본", "효율"], horizontal=True,
                label_visibility="collapsed", key="mb_view")

rows = []
for hr in sorted(d["시간"].unique()):
    m = hour_metrics(d[d["시간"] == hr])
    if view == "기본":
        rows.append({
            "시간":   f"{int(hr):02d}시",
            "광고비": f"₩{int(m['spend']):,}",
            "구매":   f"{int(m['conv']):,}",
            "CPA":   f"₩{int(m['cpa']):,}",
        })
    else:
        rows.append({
            "시간":   f"{int(hr):02d}시",
            "광고비": f"₩{int(m['spend']):,}",
            "CPC":   f"₩{int(m['cpc']):,}",
            "CVR":   f"{m['cvr']:.2f}%",
            "CPA":   f"₩{int(m['cpa']):,}",
        })
if view == "기본":
    rows.append({
        "시간": "총합계",
        "광고비": f"₩{int(k['spend']):,}",
        "구매": f"{int(k['conv']):,}",
        "CPA": f"₩{int(k['cpa']):,}",
    })
else:
    rows.append({
        "시간": "총합계",
        "광고비": f"₩{int(k['spend']):,}",
        "CPC": f"₩{int(k['cpc']):,}",
        "CVR": f"{k['cvr']:.2f}%",
        "CPA": f"₩{int(k['cpa']):,}",
    })
mobile_table(rows)
