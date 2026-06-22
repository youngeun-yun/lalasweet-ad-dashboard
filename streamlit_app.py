# -*- coding: utf-8 -*-
"""
라라스윗 광고 대시보드
Streamlit + Plotly | 데이터 소스: Google Sheets (통합RD_원본)
"""
import html as _html
import re
import uuid
import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import gspread
from google.oauth2.service_account import Credentials
from datetime import date, timedelta
# --- 페이지 설정 ---
st.set_page_config(
    page_title="라라스윗 광고 대시보드",
    page_icon="🍬",
    layout="wide",
    initial_sidebar_state="expanded",
)
# --- 커스텀 CSS ---
st.markdown("""
<style>
    .block-container { padding-top: 3rem; padding-bottom: 1rem; max-width: 1400px; }
    [data-testid="stMetricValue"] { font-size: 1.75rem; font-weight: 600; }
    [data-testid="stMetricLabel"] { font-size: 0.8rem; color: #888; }
    [data-testid="stMetricDelta"] { font-size: 0.85rem; }
    [data-testid="stSidebar"] { background: #fafafa; }
    [data-testid="stSidebar"] h2 { font-size: 0.95rem !important; margin-bottom: 0.2rem; }
    [data-testid="stSidebar"] p,
    [data-testid="stSidebar"] label,
    [data-testid="stSidebar"] .stMarkdown p { font-size: 0.75rem !important; }
    [data-testid="stSidebar"] [data-testid="stMultiSelect"] { font-size: 0.75rem; }
    [data-testid="stSidebar"] button { font-size: 0.75rem !important; }
    [data-testid="stSidebar"] .stCaption { font-size: 0.68rem !important; }
    div[data-testid="stTabs"] button { font-size: 0.9rem; font-weight: 500; }
    .stDataFrame { border-radius: 8px; overflow: hidden; }
    footer { visibility: hidden; }
</style>
""", unsafe_allow_html=True)
# --- 브랜드 컬러 ---
PALETTE = ["#F4845F", "#7BAFD4", "#82C9A7", "#B5A8E0",
           "#F7B97A", "#85C1B2", "#F49AC2", "#A8D5BA"]
BAR_PALETTE = ["#F4845F", "#7BAFD4", "#F7B97A", "#82C9A7",
               "#F49AC2", "#B5A8E0", "#E8A87C", "#85C1B2"]
TOTAL_BG   = "#FFF0E6"
TOTAL_FG   = "#B84A00"
TOTAL_FONT = "bold"
# --- 5P구성 기준일 ---
PC_BEFORE_START = pd.Timestamp("2026-06-01")
PC_BEFORE_END   = pd.Timestamp("2026-06-16")
PC_AFTER_START  = pd.Timestamp("2026-06-17")
PC_AFTER_END    = pd.Timestamp("2026-06-30")
# --- 소재 유형 우선순위 ---
CREATIVE_TYPES = [
    "맛페인포인트.5P소구",
    "메시지검증.5P소구",
    "맛페인포인트",
    "5P소구",
]
# =============================================================
# 헬퍼 함수
# =============================================================
def _esc(v) -> str:
    return _html.escape(str(v))
def render_pinned_total_table(df: pd.DataFrame) -> None:
    tid = "tbl_" + uuid.uuid4().hex[:8]
    first_col = df.columns[0]
    data  = df[df[first_col] != "총합계"].reset_index(drop=True)
    total = df[df[first_col] == "총합계"]
    th = ("padding:7px 10px; text-align:left; background:#f0f2f6;"
          "border-bottom:2px solid #ddd; font-size:0.82rem;"
          "white-space:nowrap; cursor:pointer; user-select:none;")
    td = "padding:6px 10px; border-bottom:1px solid #eee; font-size:0.82rem; white-space:nowrap;"
    tf = (f"padding:6px 10px; font-size:0.82rem; white-space:nowrap;"
          f"background:{TOTAL_BG}; color:{TOTAL_FG}; font-weight:{TOTAL_FONT};"
          f"border-top:2px solid #ddd;")
    hdr = "".join(
        f'<th style="{th}" onclick="sortTbl(\'{tid}\',{i})" data-order="">'
        f'{_esc(col)} <span style="color:#bbb;font-size:0.7rem">&#x21C5;</span></th>'
        for i, col in enumerate(df.columns)
    )
    bdy = "".join(
        "<tr>" + "".join(f'<td style="{td}">{_esc(v)}</td>' for v in row) + "</tr>"
        for _, row in data.iterrows()
    )
    ftr = ("".join(
        "<tr>" + "".join(f'<td style="{tf}">{_esc(v)}</td>' for v in row) + "</tr>"
        for _, row in total.iterrows()
    ) if not total.empty else "")
    js = (
        "function sortTbl(tid,col){"
        "var tbl=document.getElementById(tid);"
        "var tbody=tbl.querySelector('tbody');"
        "var ths=tbl.querySelectorAll('thead th');"
        "var asc=ths[col].dataset.order!=='asc';"
        "ths.forEach(function(h){h.dataset.order='';h.querySelector('span').innerHTML='&#x21C5;';});"
        "ths[col].dataset.order=asc?'asc':'desc';"
        "ths[col].querySelector('span').innerHTML=asc?'&#x2191;':'&#x2193;';"
        "var rows=Array.from(tbody.querySelectorAll('tr'));"
        "rows.sort(function(a,b){"
        "var va=a.cells[col].textContent.replace(/[\\u20a9%,\\s]/g,'');"
        "var vb=b.cells[col].textContent.replace(/[\\u20a9%,\\s]/g,'');"
        "var na=parseFloat(va),nb=parseFloat(vb);"
        "if(!isNaN(na)&&!isNaN(nb))return asc?na-nb:nb-na;"
        "return asc?va.localeCompare(vb,'ko'):vb.localeCompare(va,'ko');"
        "});"
        "rows.forEach(function(r){tbody.appendChild(r);});"
        "}"
    )
    html = (
        '<div style="overflow-x:auto; border-radius:8px; border:1px solid #e0e0e0;">'
        f'<table id="{tid}" style="width:100%; border-collapse:collapse;">'
        f'<thead><tr>{hdr}</tr></thead>'
        f'<tbody>{bdy}</tbody>'
        f'<tfoot>{ftr}</tfoot>'
        f'</table></div>'
        f'<script>{js}</script>'
    )
    height = max(150, 52 + len(data) * 34 + (38 if not total.empty else 0))
    components.html(html, height=height, scrolling=False)
def build_summary_table(data: pd.DataFrame, group_col: str, label_fn=None) -> pd.DataFrame:
    grp = (
        data.groupby(group_col)
        .agg(광고비=("광고비 (KRW)", "sum"), 노출=("노출", "sum"),
             링크클릭=("클릭", "sum"), 구매=("전환수", "sum"))
        .reset_index()
    )
    grp["CTR"] = (grp["링크클릭"] / grp["노출"].replace(0, float("nan")) * 100).fillna(0)
    grp["CPC"] = (grp["광고비"] / grp["링크클릭"].replace(0, float("nan"))).fillna(0)
    grp["CVR"] = (grp["구매"] / grp["링크클릭"].replace(0, float("nan")) * 100).fillna(0)
    grp["CPA"] = (grp["광고비"] / grp["구매"].replace(0, float("nan"))).fillna(0)
    tot = grp[["광고비", "노출", "링크클릭", "구매"]].sum()
    grp = pd.concat([grp, pd.DataFrame([{
        group_col:  "총합계",
        "광고비":   tot["광고비"],
        "노출":     tot["노출"],
        "링크클릭": tot["링크클릭"],
        "구매":     tot["구매"],
        "CTR": tot["링크클릭"] / tot["노출"] * 100 if tot["노출"] > 0 else 0,
        "CPC": tot["광고비"] / tot["링크클릭"] if tot["링크클릭"] > 0 else 0,
        "CVR": tot["구매"] / tot["링크클릭"] * 100 if tot["링크클릭"] > 0 else 0,
        "CPA": tot["광고비"] / tot["구매"] if tot["구매"] > 0 else 0,
    }])], ignore_index=True)
    if label_fn:
        grp[group_col] = grp[group_col].apply(lambda x: label_fn(x) if x != "총합계" else x)
    return grp
def style_summary(df: pd.DataFrame, first_col: str) -> pd.DataFrame:
    s = df.copy()
    s["광고비"]   = s["광고비"].apply(lambda x: f"₩{int(x):,}")
    s["노출"]     = s["노출"].apply(lambda x: f"{int(x):,}")
    s["링크클릭"] = s["링크클릭"].apply(lambda x: f"{int(x):,}")
    s["구매"]     = s["구매"].apply(lambda x: f"{int(x):,}")
    s["CTR"]     = s["CTR"].apply(lambda x: f"{x:.2f}%")
    s["CPC"]     = s["CPC"].apply(lambda x: f"{int(x):,}")
    s["CVR"]     = s["CVR"].apply(lambda x: f"{x:.2f}%")
    s["CPA"]     = s["CPA"].apply(lambda x: f"{int(x):,}")
    return s.rename(columns={"링크클릭": "링크 클릭"})
def perf_row(label: str, d: pd.DataFrame, key_col: str = "구분") -> dict:
    s = d["광고비 (KRW)"].sum()
    i = d["노출"].sum()
    c = d["클릭"].sum()
    v = d["전환수"].sum()
    return {
        key_col:     label,
        "광고비":    f"₩{int(s):,}",
        "노출":      f"{int(i):,}",
        "링크 클릭": f"{int(c):,}",
        "구매":      f"{int(v):,}",
        "CTR":      f"{c/i*100:.2f}%" if i > 0 else "0.00%",
        "CPC":      f"{int(s/c):,}" if c > 0 else "0",
        "CVR":      f"{v/c*100:.2f}%" if c > 0 else "0.00%",
        "CPA":      f"{int(s/v):,}" if v > 0 else "0",
    }
def daily_table(d: pd.DataFrame) -> pd.DataFrame:
    grp = (
        d.groupby(d["날짜"].dt.date)
        .agg(spend=("광고비 (KRW)", "sum"), imp=("노출", "sum"),
             clk=("클릭", "sum"), conv=("전환수", "sum"))
        .reset_index().rename(columns={"날짜": "date"})
        .sort_values("date")
    )
    grp["CTR"] = (grp["clk"] / grp["imp"].replace(0, float("nan")) * 100).fillna(0)
    grp["CPC"] = (grp["spend"] / grp["clk"].replace(0, float("nan"))).fillna(0)
    grp["CVR"] = (grp["conv"] / grp["clk"].replace(0, float("nan")) * 100).fillna(0)
    grp["CPA"] = (grp["spend"] / grp["conv"].replace(0, float("nan"))).fillna(0)
    tbl = pd.DataFrame({
        "일":        grp["date"].astype(str),
        "광고비":    grp["spend"].apply(lambda x: f"₩{int(x):,}"),
        "노출":      grp["imp"].apply(lambda x: f"{int(x):,}"),
        "링크 클릭": grp["clk"].apply(lambda x: f"{int(x):,}"),
        "구매":      grp["conv"].apply(lambda x: f"{int(x):,}"),
        "CTR":      grp["CTR"].apply(lambda x: f"{x:.2f}%"),
        "CPC":      grp["CPC"].apply(lambda x: f"{int(x):,}"),
        "CVR":      grp["CVR"].apply(lambda x: f"{x:.2f}%"),
        "CPA":      grp["CPA"].apply(lambda x: f"{int(x):,}"),
    })
    ts, ti, tc, tv = grp["spend"].sum(), grp["imp"].sum(), grp["clk"].sum(), grp["conv"].sum()
    total = pd.DataFrame([{
        "일":        "총합계",
        "광고비":    f"₩{int(ts):,}",
        "노출":      f"{int(ti):,}",
        "링크 클릭": f"{int(tc):,}",
        "구매":      f"{int(tv):,}",
        "CTR":      f"{tc/ti*100:.2f}%" if ti > 0 else "0.00%",
        "CPC":      f"{int(ts/tc):,}" if tc > 0 else "0",
        "CVR":      f"{tv/tc*100:.2f}%" if tc > 0 else "0.00%",
        "CPA":      f"{int(ts/tv):,}" if tv > 0 else "0",
    }])
    return pd.concat([tbl, total], ignore_index=True)
def valid_opts(df: pd.DataFrame, col: str) -> list:
    grp = df.groupby(col)["노출"].sum()
    return sorted([str(v) for v, imp in grp.items()
                   if str(v).strip() != "" and imp > 0])
def week_label(ws) -> str:
    if ws == "총합계":
        return ws
    return f"{ws.strftime('%m/%d')}~{(ws + timedelta(days=6)).strftime('%m/%d')}"
def classify_creative(ad_name: str):
    for t in CREATIVE_TYPES:
        if t in str(ad_name):
            return t
    return None
def calc_kpi(d: pd.DataFrame) -> dict:
    spend = d["광고비 (KRW)"].sum()
    imp   = d["노출"].sum()
    clk   = d["클릭"].sum()
    conv  = d["전환수"].sum()
    return dict(spend=spend, imp=imp, clk=clk, conv=conv,
                ctr=clk / imp * 100 if imp > 0 else 0,
                cpa=spend / conv if conv > 0 else 0)
def fmt_krw(v: float) -> str:
    return f"₩{int(v):,}"
def fmt_num(v: float) -> str:
    return f"{int(v):,}"
def render_kpi(k: dict) -> None:
    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("💰 광고비", fmt_krw(k["spend"]))
    c2.metric("👁 노출",   fmt_num(k["imp"]))
    c3.metric("🖱 클릭",   fmt_num(k["clk"]))
    c4.metric("🛒 전환수", fmt_num(k["conv"]))
    c5.metric("📈 CTR",    f"{k['ctr']:.2f}%")
    c6.metric("🎯 CPA",    fmt_krw(k["cpa"]))
# =============================================================
# 데이터 로드
# =============================================================
@st.cache_data(ttl=3600, show_spinner="데이터 불러오는 중...")
def load_data() -> pd.DataFrame:
    creds = Credentials.from_service_account_info(
        dict(st.secrets["gcp_service_account"]),
        scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"],
    )
    gc = gspread.authorize(creds)
    ws = gc.open_by_key(st.secrets["spreadsheet_id"]).worksheet("통합RD_원본")
    records = ws.get_all_records()
    df = pd.DataFrame(records)
    df["날짜"] = pd.to_datetime(df["날짜"], errors="coerce")
    for col in ["광고비 (KRW)", "노출", "클릭", "전환수", "CTR (%)", "CPA (KRW)",
                "CPC (KRW)", "영상조회 3초+", "ThruPlay"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)
    df = df.dropna(subset=["날짜"])
    df["연"] = df["날짜"].dt.year.astype(str)
    df["월"] = df["날짜"].dt.month.astype(str).str.zfill(2)
    df["일"] = df["날짜"].dt.day.astype(str).str.zfill(2)
    return df.sort_values("날짜")


@st.cache_data(ttl=3600, show_spinner="카페24 데이터 불러오는 중...")
def load_cafe24_data():
    creds = Credentials.from_service_account_info(
        dict(st.secrets["gcp_service_account"]),
        scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"],
    )
    gc = gspread.authorize(creds)
    ss = gc.open_by_key(st.secrets["spreadsheet_id"])

    # 요약 시트
    try:
        ws_s = ss.worksheet("카페24_팝콘_요약")
        df_s = pd.DataFrame(ws_s.get_all_records())
        if not df_s.empty:
            df_s["날짜"] = pd.to_datetime(df_s["날짜"], errors="coerce")
            df_s["팝콘_주문수"] = pd.to_numeric(df_s["팝콘_주문수"], errors="coerce").fillna(0)
            df_s["팝콘_실매출"] = pd.to_numeric(df_s["팝콘_실매출"], errors="coerce").fillna(0)
            df_s = df_s.dropna(subset=["날짜"]).sort_values("날짜").reset_index(drop=True)
    except Exception:
        df_s = pd.DataFrame()

    # 옵션별 시트
    try:
        ws_o = ss.worksheet("카페24_팝콘_옵션별")
        df_o = pd.DataFrame(ws_o.get_all_records())
        if not df_o.empty:
            df_o["날짜"] = pd.to_datetime(df_o["날짜"], errors="coerce")
            # 개입 수 컬럼 숫자 변환
            qty_cols = [c for c in df_o.columns if re.match(r'^\d+개$', c)]
            for c in qty_cols:
                df_o[c] = pd.to_numeric(df_o[c], errors="coerce").fillna(0)
            df_o = df_o.dropna(subset=["날짜"]).sort_values("날짜").reset_index(drop=True)
    except Exception:
        df_o = pd.DataFrame()

    return df_s, df_o


try:
    df = load_data()
except Exception as e:
    st.error(f"❌ 데이터를 불러오지 못했어요: `{e}`")
    st.info("👉 `.streamlit/secrets.toml` 설정을 확인해주세요.")
    st.stop()

if df.empty:
    st.warning("시트에 데이터가 없어요.")
    st.stop()

max_date = df["날짜"].max().strftime("%Y-%m-%d")
# =============================================================
# 사이드바
# =============================================================
with st.sidebar:
    st.markdown("## 🍬 라라스윗 제과 전환광고")
    st.markdown("---")
    _cur_year  = date.today().year
    _cur_month = f"{date.today().month}월"
    st.markdown("**📅 연도**")
    year_opts = sorted(df["날짜"].dt.year.unique().tolist(), reverse=True)
    sel_years = st.multiselect("연도", year_opts,
                               default=[_cur_year] if _cur_year in year_opts else [],
                               placeholder="전체", label_visibility="collapsed")
    st.markdown("**📅 월**")
    avail_months = sorted(df["날짜"].dt.month.unique().tolist())
    month_labels = [f"{m}월" for m in avail_months]
    sel_months = st.multiselect("월", month_labels,
                                default=[_cur_month] if _cur_month in month_labels else [],
                                placeholder="전체", label_visibility="collapsed")
    st.markdown("**📅 일**")
    avail_dates = sorted(df["날짜"].dt.strftime("%Y-%m-%d").unique().tolist())
    sel_dates = st.multiselect("일", avail_dates, placeholder="전체",
                               label_visibility="collapsed")
    st.markdown("**📺 매체**")
    sel_media = st.multiselect("매체", valid_opts(df, "매체"),
                               placeholder="전체", label_visibility="collapsed")
    st.markdown("**🎬 광고유형**")
    sel_adtype = st.multiselect("광고유형", valid_opts(df, "영상/이미지 구분"),
                                placeholder="전체", label_visibility="collapsed")
    st.markdown("**📦 제품코드**")
    sel_prodcode = st.multiselect("제품코드", valid_opts(df, "제품코드"),
                                  placeholder="전체", label_visibility="collapsed")
    st.markdown("**🎪 이벤트명**")
    sel_event = st.multiselect("이벤트명", valid_opts(df, "스킴명"),
                               placeholder="전체", label_visibility="collapsed")
    st.markdown("---")
    if st.button("🔄 데이터 새로고침"):
        st.cache_data.clear()
        st.rerun()
    st.caption(f"최근 업데이트: {max_date}")
# =============================================================
# 필터 적용
# =============================================================
mask = pd.Series([True] * len(df), index=df.index)
if sel_years:
    mask &= df["날짜"].dt.year.isin(sel_years)
if sel_months:
    sel_month_nums = [int(m.replace("월", "")) for m in sel_months]
    mask &= df["날짜"].dt.month.isin(sel_month_nums)
if sel_dates:
    mask &= df["날짜"].dt.strftime("%Y-%m-%d").isin(sel_dates)
if sel_media:
    mask &= df["매체"].astype(str).isin(sel_media)
if sel_adtype:
    mask &= df["영상/이미지 구분"].astype(str).isin(sel_adtype)
if sel_prodcode:
    mask &= df["제품코드"].astype(str).isin(sel_prodcode)
if sel_event:
    mask &= df["스킴명"].astype(str).isin(sel_event)
fdf = df[mask].copy()
# 월별 추이: 연도 필터만 적용
mask_year_only = pd.Series([True] * len(df), index=df.index)
if sel_years:
    mask_year_only &= df["날짜"].dt.year.isin(sel_years)
fdf_year_only = df[mask_year_only].copy()
if fdf.empty:
    st.warning("필터 조건에 맞는 데이터가 없어요. 필터를 조정해주세요.")
    st.stop()
kpi = calc_kpi(fdf)
# =============================================================
# 탭
# =============================================================
tab1, tab2, tab3 = st.tabs(["📊 전체 요약", "🍿 팝콘 요약", "🛒 팝콘 카페24"])
# --- TAB 1: 전체 요약 ---
with tab1:
    render_kpi(kpi)
    st.markdown("---")
    daily_prod = (
        fdf.groupby([fdf["날짜"].dt.date, "제품코드"])
        .agg(spend=("광고비 (KRW)", "sum"))
        .reset_index().rename(columns={"날짜": "date"})
    )
    daily_prod["spend_man"] = daily_prod["spend"] / 10000
    daily_cpa = (
        fdf.groupby(fdf["날짜"].dt.date)
        .agg(spend=("광고비 (KRW)", "sum"), imp=("노출", "sum"),
             clk=("클릭", "sum"), conv=("전환수", "sum"))
        .reset_index().rename(columns={"날짜": "date"})
    )
    daily_cpa["CPA"] = (daily_cpa["spend"] / daily_cpa["conv"].replace(0, float("nan"))).fillna(0)
    daily_cpa["CTR"] = (daily_cpa["clk"] / daily_cpa["imp"].replace(0, float("nan")) * 100).fillna(0)
    daily_cpa["CPC"] = (daily_cpa["spend"] / daily_cpa["clk"].replace(0, float("nan"))).fillna(0)
    daily_cpa["CVR"] = (daily_cpa["conv"] / daily_cpa["clk"].replace(0, float("nan")) * 100).fillna(0)
    prod_codes_sorted = (
        daily_prod.groupby("제품코드")["spend"].sum()
        .sort_values(ascending=False).index.tolist()
    )
    hdr_col, btn_col = st.columns([6, 1])
    with hdr_col:
        st.markdown("**📊 일별 광고비 & CPA**")
    with btn_col:
        view_mode = st.radio("보기", ["그래프", "테이블"], horizontal=True,
                             label_visibility="collapsed", key="daily_view_mode")
    if view_mode == "그래프":
        fig = go.Figure()
        for i, pc in enumerate(prod_codes_sorted):
            d = daily_prod[daily_prod["제품코드"] == pc]
            fig.add_bar(x=d["date"], y=d["spend_man"], name=str(pc),
                        marker_color=BAR_PALETTE[i % len(BAR_PALETTE)], yaxis="y1",
                        hovertemplate=f"<b>{pc}</b><br>날짜: %{{x}}<br>광고비: %{{y:,.0f}}만원<extra></extra>")
        fig.add_scatter(x=daily_cpa["date"], y=daily_cpa["CPA"],
                        name="CPA", mode="lines+markers",
                        line=dict(color="#9B8EC4", width=2.5), marker=dict(size=6), yaxis="y2",
                        hovertemplate="날짜: %{x}<br>CPA: %{y:,.0f}원<extra></extra>")
        fig.update_layout(
            barmode="stack",
            xaxis=dict(title=""),
            yaxis=dict(title="광고비", ticksuffix="만원", tickformat=",",
                       showgrid=True, gridcolor="#f0f0f0"),
            yaxis2=dict(title="CPA (원)", overlaying="y", side="right",
                        showgrid=False, tickformat=",", ticksuffix="원"),
            legend=dict(orientation="h", y=1.10, font=dict(size=11)),
            plot_bgcolor="white", paper_bgcolor="white",
            margin=dict(t=50, b=40), height=400,
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        render_pinned_total_table(daily_table(fdf))
    col_a, col_b = st.columns(2)
    with col_a:
        by_adtype = fdf.groupby("영상/이미지 구분")["광고비 (KRW)"].sum().reset_index()
        fig2 = px.pie(by_adtype, names="영상/이미지 구분", values="광고비 (KRW)",
                      title="소재유형별 광고비 비중 (V/I)", color_discrete_sequence=PALETTE)
        fig2.update_layout(height=300, margin=dict(t=50, b=20),
                           paper_bgcolor="white", plot_bgcolor="white")
        st.plotly_chart(fig2, use_container_width=True)
    with col_b:
        by_media_pie = fdf.groupby("매체")["광고비 (KRW)"].sum().reset_index()
        fig3 = px.pie(by_media_pie, names="매체", values="광고비 (KRW)",
                      title="매체별 광고비 비중", color_discrete_sequence=PALETTE)
        fig3.update_layout(height=300, margin=dict(t=50, b=20),
                           paper_bgcolor="white", plot_bgcolor="white")
        st.plotly_chart(fig3, use_container_width=True)
    st.markdown("---")
    fdf_m = fdf_year_only.copy()
    fdf_m["월"] = fdf_m["날짜"].dt.month
    monthly_tbl = build_summary_table(fdf_m, "월", label_fn=lambda x: f"{int(x):02d}")
    st.markdown("**📅 월별 데이터 추이**")
    render_pinned_total_table(style_summary(monthly_tbl, "월"))
    fdf_w = fdf.copy()
    fdf_w["week_start"] = fdf_w["날짜"].dt.to_period("W").apply(lambda p: p.start_time.date())
    recent_weeks = sorted(fdf_w["week_start"].unique())[-4:]
    fdf_w4 = fdf_w[fdf_w["week_start"].isin(recent_weeks)]
    weekly_tbl = build_summary_table(fdf_w4, "week_start", label_fn=week_label)
    weekly_tbl = weekly_tbl.rename(columns={"week_start": "주차"})
    st.markdown("**📆 주차별 성과 (최근 4주)**")
    render_pinned_total_table(style_summary(weekly_tbl, "주차"))
# --- TAB 2: 팝콘 요약 ---
with tab2:
    fdf_pc = fdf[fdf["제품코드"].astype(str).str.contains("PC", na=False)].copy()
    if fdf_pc.empty:
        st.warning("팝콘(PC) 데이터가 없어요. 사이드바 필터를 확인해주세요.")
    else:
        render_kpi(calc_kpi(fdf_pc))
        st.markdown("---")
        # 1. 일별 광고비 테이블
        st.markdown("**📊 일별 광고비 & CPA**")
        render_pinned_total_table(daily_table(fdf_pc))
        st.markdown("---")
        # 2. 5P구성 성과
        st.markdown("**📋 5P구성 성과**")
        before = fdf_pc[
            (fdf_pc["날짜"] >= PC_BEFORE_START) & (fdf_pc["날짜"] <= PC_BEFORE_END)
        ]
        after = fdf_pc[
            (fdf_pc["날짜"] >= PC_AFTER_START) & (fdf_pc["날짜"] <= PC_AFTER_END)
        ]
        period_total = pd.concat([before, after])
        b_label = f"5p구성 이전({PC_BEFORE_START.strftime('%m/%d')}~{PC_BEFORE_END.strftime('%m/%d')})"
        a_label = f"5p구성 적용({PC_AFTER_START.strftime('%m/%d')}~{PC_AFTER_END.strftime('%m/%d')})"
        period_df = pd.DataFrame([
            perf_row(b_label, before),
            perf_row(a_label, after),
            perf_row("총합계", period_total),
        ])
        render_pinned_total_table(period_df)
        st.markdown("---")
        # 3. 이벤트별 성과
        st.markdown("**🎪 이벤트별 성과**")
        event_tbl = build_summary_table(fdf_pc, "스킴명")
        event_tbl = event_tbl.rename(columns={"스킴명": "이벤트명"})
        _ev_total = event_tbl[event_tbl["이벤트명"] == "총합계"]
        _ev_data  = event_tbl[event_tbl["이벤트명"] != "총합계"].sort_values("광고비", ascending=False)
        event_tbl = pd.concat([_ev_data, _ev_total], ignore_index=True)
        render_pinned_total_table(style_summary(event_tbl, "이벤트명"))
        st.markdown("---")
        # 4. 소재 유형별 성과 (피벗 트리 테이블)
        st.markdown("**🎨 소재 유형별 성과**")
        fdf_pc_c = fdf_pc.copy()
        fdf_pc_c["_유형"] = fdf_pc_c["소재명"].apply(classify_creative)
        _type_data = []
        for t in CREATIVE_TYPES:
            sub = fdf_pc_c[fdf_pc_c["_유형"] == t]
            if not sub.empty:
                _type_data.append((t, sub, sub["광고비 (KRW)"].sum()))
        if _type_data:
            _type_data.sort(key=lambda x: x[2], reverse=True)
            typed_total = fdf_pc_c[fdf_pc_c["_유형"].notna()]
            total_row   = perf_row("총합계", typed_total, key_col="소재 유형")
            _tid  = "ct_" + uuid.uuid4().hex[:8]
            _cols = ["소재 유형", "광고비", "노출", "링크 클릭", "구매",
                     "CTR", "CPC", "CVR", "CPA"]
            _th   = ("padding:7px 10px;text-align:left;background:#f0f2f6;"
                     "border-bottom:2px solid #ddd;font-size:0.82rem;white-space:nowrap;")
            _tdp  = "padding:6px 10px;border-bottom:1px solid #eee;font-size:0.82rem;white-space:nowrap;"
            _tdc1 = ("padding:5px 10px 5px 28px;border-bottom:1px solid #f5f5f5;"
                     "font-size:0.80rem;white-space:nowrap;color:#555;background:#fafcff;")
            _tdcn = ("padding:5px 10px;border-bottom:1px solid #f5f5f5;"
                     "font-size:0.80rem;white-space:nowrap;color:#555;background:#fafcff;")
            _tft  = (f"padding:6px 10px;font-size:0.82rem;white-space:nowrap;"
                     f"background:{TOTAL_BG};color:{TOTAL_FG};font-weight:{TOTAL_FONT};"
                     f"border-top:2px solid #ddd;")
            _hdr = "".join(f'<th style="{_th}">{_esc(c)}</th>' for c in _cols)
            _body    = ""
            _n_child = 0
            for _idx, (_t, _sub, _) in enumerate(_type_data):
                _pid = f"p_{_tid}_{_idx}"
                _pr  = perf_row(_t, _sub, key_col="소재 유형")
                _ico = f'<span id="ico_{_pid}" style="display:inline-block;width:14px;font-size:0.75rem">&#9654;</span>'
                _p1  = f'<td style="{_tdp}cursor:pointer;">{_ico} {_esc(_t)}</td>'
                _pr2 = "".join(f'<td style="{_tdp}">{_esc(_pr[c])}</td>' for c in _cols[1:])
                _body += f'<tr onclick="toggleCT(\'{_pid}\')" style="cursor:pointer;">{_p1}{_pr2}</tr>'
                _ads = [
                    (_an,
                     perf_row(_an, _sub[_sub["소재명"] == _an], key_col="소재 유형"),
                     _sub[_sub["소재명"] == _an]["광고비 (KRW)"].sum())
                    for _an in _sub["소재명"].unique()
                ]
                _ads.sort(key=lambda x: x[2], reverse=True)
                for _an, _ar, _ in _ads:
                    _c1   = f'<td style="{_tdc1}">{_esc(_an)}</td>'
                    _cr   = "".join(f'<td style="{_tdcn}">{_esc(_ar[c])}</td>' for c in _cols[1:])
                    _body += f'<tr class="cc_{_pid}" style="display:none;">{_c1}{_cr}</tr>'
                    _n_child += 1
            _ftd = "".join(f'<td style="{_tft}">{_esc(total_row[c])}</td>' for c in _cols)
            _js  = (
                "function toggleCT(pid){"
                "var rows=document.querySelectorAll('.cc_'+pid);"
                "var ico=document.getElementById('ico_'+pid);"
                "var show=rows.length>0&&rows[0].style.display==='none';"
                "rows.forEach(function(r){r.style.display=show?'':'none';});"
                "if(ico)ico.innerHTML=show?'&#9660;':'&#9654;';}"
            )
            _html = (
                '<div style="overflow-x:auto;border-radius:8px;border:1px solid #e0e0e0;">'
                '<table style="width:100%;border-collapse:collapse;">'
                f'<thead><tr>{_hdr}</tr></thead>'
                f'<tbody>{_body}</tbody>'
                f'<tfoot><tr>{_ftd}</tr></tfoot>'
                '</table></div>'
                f'<script>{_js}</script>'
            )
            _h = max(150, 52 + (len(_type_data) + 1) * 36)
            components.html(_html, height=_h, scrolling=False)
        else:
            st.info("현재 필터 조건에서 해당 소재 유형 데이터가 없습니다.")

# --- TAB 3: 팝콘 카페24 ---
with tab3:
    try:
        df_c24_s, df_c24_o = load_cafe24_data()
    except Exception as e:
        st.error(f"❌ 카페24 데이터를 불러오지 못했어요: `{e}`")
        st.stop()

    # 사이드바 연도·월·일 필터 적용
    def _filter_c24(d: pd.DataFrame) -> pd.DataFrame:
        if d.empty:
            return d
        m = pd.Series([True] * len(d), index=d.index)
        if sel_years:
            m &= d["날짜"].dt.year.isin(sel_years)
        if sel_months:
            nums = [int(x.replace("월", "")) for x in sel_months]
            m &= d["날짜"].dt.month.isin(nums)
        if sel_dates:
            m &= d["날짜"].dt.strftime("%Y-%m-%d").isin(sel_dates)
        return d[m].copy()

    df_s = _filter_c24(df_c24_s)
    df_o = _filter_c24(df_c24_o)

    if df_s.empty:
        st.warning("카페24 팝콘 데이터가 없어요. 사이드바 필터를 확인해주세요.")
    else:
        # ── 섹션 1: 일별 주문 요약 테이블 ──────────────────────────
        st.markdown("**📦 일별 주문 요약**")
        _s_rows = []
        for _, row in df_s.iterrows():
            _s_rows.append({
                "날짜":      row["날짜"].strftime("%Y-%m-%d"),
                "주문수":    f"{int(row['팝콘_주문수']):,}",
                "실매출(원)": f"₩{int(row['팝콘_실매출']):,}",
            })
        _s_total = {
            "날짜":      "총합계",
            "주문수":    f"{int(df_s['팝콘_주문수'].sum()):,}",
            "실매출(원)": f"₩{int(df_s['팝콘_실매출'].sum()):,}",
        }
        _s_rows.append(_s_total)
        render_pinned_total_table(pd.DataFrame(_s_rows))

        st.markdown("---")

        # ── 섹션 2: 개입별 구매 비중 ───────────────────────────────
        st.markdown("**📊 개입별 구매 비중**")

        if df_o.empty:
            st.info("옵션별 데이터가 없습니다.")
        else:
            qty_cols = sorted(
                [c for c in df_o.columns if re.match(r'^\d+개$', c)],
                key=lambda x: int(re.search(r'\d+', x).group()),
            )

            # 날짜별 합산 (상품 135+161 통합)
            df_agg = df_o.groupby("날짜")[qty_cols].sum().reset_index().sort_values("날짜")
            df_agg["합계"] = df_agg[qty_cols].sum(axis=1)
            df_agg["date_str"] = df_agg["날짜"].dt.strftime("%m/%d")

            # 100% 누적 바 차트
            fig_opt = go.Figure()
            for i, c in enumerate(qty_cols):
                pct = (df_agg[c] / df_agg["합계"].replace(0, float("nan")) * 100).fillna(0)
                fig_opt.add_bar(
                    x=df_agg["date_str"],
                    y=pct,
                    name=c,
                    marker_color=BAR_PALETTE[i % len(BAR_PALETTE)],
                    hovertemplate=(
                        f"<b>{c}</b><br>"
                        "날짜: %{x}<br>"
                        "비중: %{y:.1f}%<br>"
                        "주문수: " + df_agg[c].astype(int).astype(str) + "건"
                        "<extra></extra>"
                    ),
                )
            fig_opt.update_layout(
                barmode="stack",
                xaxis=dict(title=""),
                yaxis=dict(title="비중 (%)", ticksuffix="%", range=[0, 100],
                           showgrid=True, gridcolor="#f0f0f0"),
                legend=dict(orientation="h", y=1.12, font=dict(size=11)),
                plot_bgcolor="white", paper_bgcolor="white",
                margin=dict(t=50, b=40), height=350,
            )
            st.plotly_chart(fig_opt, use_container_width=True)

            # 상세 테이블: 날짜 | 10개(건·%) | 15개(건·%) | ... | 합계
            _o_rows = []
            for _, row in df_agg.iterrows():
                r = {"날짜": row["날짜"].strftime("%Y-%m-%d")}
                for c in qty_cols:
                    cnt = int(row[c])
                    pct = cnt / row["합계"] * 100 if row["합계"] > 0 else 0
                    r[c] = f"{cnt:,} ({pct:.1f}%)"
                r["합계"] = f"{int(row['합계']):,}"
                _o_rows.append(r)

            # 총합계 행
            _tot = {"날짜": "총합계"}
            _grand = df_agg["합계"].sum()
            for c in qty_cols:
                _cnt = int(df_agg[c].sum())
                _pct = _cnt / _grand * 100 if _grand > 0 else 0
                _tot[c] = f"{_cnt:,} ({_pct:.1f}%)"
            _tot["합계"] = f"{int(_grand):,}"
            _o_rows.append(_tot)

            render_pinned_total_table(pd.DataFrame(_o_rows))
