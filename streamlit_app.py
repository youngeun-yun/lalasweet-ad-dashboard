# -*- coding: utf-8 -*-
"""
라라스윗 광고 대시보드
Streamlit + Plotly | 데이터 소스: Google Sheets (통합RD_원본)
"""
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import gspread
from google.oauth2.service_account import Credentials
import json
from datetime import date, timedelta
import calendar

# ── 페이지 설정 ────────────────────────────────────────────────
st.set_page_config(
    page_title="라라스윗 광고 대시보드",
    page_icon="🍬",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── 커스텀 CSS ─────────────────────────────────────────────────
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

# ── 브랜드 컬러 ────────────────────────────────────────────────
BRAND   = "#F4845F"
META_C  = "#7BAFD4"
PALETTE = ["#F4845F", "#7BAFD4", "#82C9A7", "#B5A8E0",
           "#F7B97A", "#85C1B2", "#F49AC2", "#A8D5BA"]
BAR_PALETTE = ["#F4845F", "#7BAFD4", "#F7B97A", "#82C9A7",
               "#F49AC2", "#B5A8E0", "#E8A87C", "#85C1B2"]

# 총합계 행 하이라이트
TOTAL_BG   = "#FFF0E6"
TOTAL_FG   = "#B84A00"
TOTAL_FONT = "bold"

def style_with_total(df: pd.DataFrame):
    """첫 번째 컬럼 값이 '총합계'인 행에 배경색/굵기 적용"""
    first_col = df.columns[0]
    def row_style(row):
        if row[first_col] == "총합계":
            return [f"background-color: {TOTAL_BG}; font-weight: {TOTAL_FONT}; color: {TOTAL_FG}"] * len(row)
        return [""] * len(row)
    return df.style.apply(row_style, axis=1)


# ── 공통 집계 함수 ─────────────────────────────────────────────
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
    tot = grp[["광고비","노출","링크클릭","구매"]].sum()
    grp = pd.concat([grp, pd.DataFrame([{
        group_col: "총합계",
        "광고비": tot["광고비"], "노출": tot["노출"],
        "링크클릭": tot["링크클릭"], "구매": tot["구매"],
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
    """단일 집계행 딕셔너리 생성 (포맷 완료)"""
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
    """일별 집계 + 총합계 행 반환 (포맷 완료)"""
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


# ── 데이터 로드 ────────────────────────────────────────────────
@st.cache_data(ttl=3600, show_spinner="데이터 불러오는 중…")
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


try:
    df = load_data()
except Exception as e:
    st.error(f"❌ 데이터를 불러오지 못했어요: `{e}`")
    st.info("👉 `.streamlit/secrets.toml` 설정을 확인해주세요.")
    st.stop()

if df.empty:
    st.warning("시트에 데이터가 없어요.")
    st.stop()

# ── 사이드바 필터 ──────────────────────────────────────────────
max_date = df["날짜"].max().strftime("%Y-%m-%d")

with st.sidebar:
    st.markdown("## 🍬 라라스윗 제과 전환광고")
    st.markdown("---")

    def valid_opts(col):
        grp = df.groupby(col)["노출"].sum()
        return sorted([str(v) for v, imp in grp.items()
                       if str(v).strip() != "" and imp > 0])

    st.markdown("**📅 연도**")
    year_opts = sorted(df["날짜"].dt.year.unique().tolist(), reverse=True)
    sel_years = st.multiselect("연도", year_opts, placeholder="전체",
                               label_visibility="collapsed")

    st.markdown("**📅 월**")
    avail_months = sorted(df["날짜"].dt.month.unique().tolist())
    month_labels = [f"{m}월" for m in avail_months]
    sel_months = st.multiselect("월", month_labels, placeholder="전체",
                                label_visibility="collapsed")

    st.markdown("**📅 일**")
    avail_dates = sorted(df["날짜"].dt.strftime("%Y-%m-%d").unique().tolist())
    sel_dates = st.multiselect("일", avail_dates, placeholder="전체",
                               label_visibility="collapsed")

    st.markdown("**📺 매체**")
    media_opts = valid_opts("매체")
    sel_media = st.multiselect("매체", media_opts, placeholder="전체",
                               label_visibility="collapsed")

    st.markdown("**🎬 광고유형**")
    adtype_opts = valid_opts("영상/이미지 구분")
    sel_adtype = st.multiselect("광고유형", adtype_opts, placeholder="전체",
                                label_visibility="collapsed")

    st.markdown("**📦 제품코드**")
    prodcode_opts = valid_opts("제품코드")
    sel_prodcode = st.multiselect("제품코드", prodcode_opts, placeholder="전체",
                                  label_visibility="collapsed")

    st.markdown("**🎪 이벤트명**")
    event_opts = valid_opts("스킴명")
    sel_event = st.multiselect("이벤트명", event_opts, placeholder="전체",
                               label_visibility="collapsed")

    st.markdown("---")
    if st.button("🔄 데이터 새로고침"):
        st.cache_data.clear()
        st.rerun()

    st.caption(f"최근 업데이트: {max_date}")


# ── 필터 적용 ──────────────────────────────────────────────────
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

if fdf.empty:
    st.warning("필터 조건에 맞는 데이터가 없어요. 필터를 조정해주세요.")
    st.stop()


# ── KPI 집계 ───────────────────────────────────────────────────
def calc_kpi(d: pd.DataFrame) -> dict:
    spend = d["광고비 (KRW)"].sum()
    imp   = d["노출"].sum()
    clk   = d["클릭"].sum()
    conv  = d["전환수"].sum()
    return dict(spend=spend, imp=imp, clk=clk, conv=conv,
                ctr=clk/imp*100 if imp > 0 else 0,
                cpa=spend/conv if conv > 0 else 0)

kpi = calc_kpi(fdf)

def fmt_krw(v): return f"₩{int(v):,}"
def fmt_num(v): return f"{int(v):,}"


# ── 공통: KPI 카드 ─────────────────────────────────────────────
def render_kpi(k: dict):
    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("💰 광고비", fmt_krw(k["spend"]))
    c2.metric("👁 노출",   fmt_num(k["imp"]))
    c3.metric("🖱 클릭",   fmt_num(k["clk"]))
    c4.metric("🛒 전환수", fmt_num(k["conv"]))
    c5.metric("📈 CTR",    f"{k['ctr']:.2f}%")
    c6.metric("🎯 CPA",    fmt_krw(k["cpa"]))


# ── 공통: 원본 테이블 ──────────────────────────────────────────
DISPLAY_COLS = ["날짜", "매체", "스킴명", "광고그룹명", "소재명",
                "대분류 포맷", "노출", "클릭", "CTR (%)", "광고비 (KRW)",
                "전환수", "CPA (KRW)"]

def render_table(d: pd.DataFrame, cols=None):
    show = [c for c in (cols or DISPLAY_COLS) if c in d.columns]
    styled = d[show].copy()
    if "날짜" in styled.columns:
        styled["날짜"] = styled["날짜"].dt.strftime("%Y-%m-%d")
    for c in ["광고비 (KRW)", "CPA (KRW)", "CPC (KRW)"]:
        if c in styled.columns:
            styled[c] = styled[c].apply(lambda x: f"₩{x:,.0f}")
    for c in ["CTR (%)"]:
        if c in styled.columns:
            styled[c] = styled[c].apply(lambda x: f"{x:.2f}%")
    st.dataframe(styled, use_container_width=True, hide_index=True)


# ── 탭 ────────────────────────────────────────────────────────
tab1, tab2, tab3, tab4, tab5 = st.tabs(
    ["📊 전체 요약", "🍿 팝콘 요약", "📺 매체별", "🎨 소재별", "📦 제품별"]
)


# ══════════════════════════════════════════════════════════════
# TAB 1: 전체 요약
# ══════════════════════════════════════════════════════════════
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
        st.dataframe(style_with_total(daily_table(fdf)),
                     use_container_width=True, hide_index=True)

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

    fdf_m = fdf.copy()
    fdf_m["월"] = fdf_m["날짜"].dt.month
    monthly_tbl = build_summary_table(fdf_m, "월", label_fn=lambda x: f"{int(x):02d}")
    st.markdown("**📅 월별 데이터 추이**")
    st.dataframe(style_with_total(style_summary(monthly_tbl, "월")),
                 use_container_width=True, hide_index=True,
                 column_config={"월": st.column_config.TextColumn("월", width="small")})

    fdf_w = fdf.copy()
    fdf_w["week_start"] = fdf_w["날짜"].dt.to_period("W").apply(lambda p: p.start_time.date())
    recent_weeks = sorted(fdf_w["week_start"].unique())[-4:]
    fdf_w4 = fdf_w[fdf_w["week_start"].isin(recent_weeks)]

    def week_label(ws):
        if ws == "총합계": return ws
        return f"{ws.strftime('%m/%d')}~{(ws + timedelta(days=6)).strftime('%m/%d')}"

    weekly_tbl = build_summary_table(fdf_w4, "week_start", label_fn=week_label)
    weekly_tbl = weekly_tbl.rename(columns={"week_start": "주차"})
    st.markdown("**📆 주차별 성과 (최근 4주)**")
    st.dataframe(style_with_total(style_summary(weekly_tbl, "주차")),
                 use_container_width=True, hide_index=True,
                 column_config={"주차": st.column_config.TextColumn("주차", width="medium")})


# ══════════════════════════════════════════════════════════════
# TAB 2: 팝콘 요약
# ══════════════════════════════════════════════════════════════
with tab2:
    # 팝콘 필터: 제품코드에 "PC" 포함
    fdf_pc = fdf[fdf["제품코드"].astype(str).str.contains("PC", na=False)].copy()

    if fdf_pc.empty:
        st.warning("팝콘(PC) 데이터가 없어요. 사이드바 필터를 확인해주세요.")
    else:
        render_kpi(calc_kpi(fdf_pc))
        st.markdown("---")

        # ── 1. 일별 광고비 테이블 ─────────────────────────────
        st.markdown("**📊 일별 광고비 & CPA**")
        st.dataframe(style_with_total(daily_table(fdf_pc)),
                     use_container_width=True, hide_index=True)

        st.markdown("---")

        # ── 2. 5P구성 성과 ────────────────────────────────────
        st.markdown("**📋 5P구성 성과**")

        T_BEFORE_END  = pd.Timestamp("2026-06-16")
        T_AFTER_START = pd.Timestamp("2026-06-17")
        T_AFTER_END   = pd.Timestamp("2026-06-30")
        T_BEFORE_START = pd.Timestamp("2026-06-01")

        before = fdf_pc[(fdf_pc["날짜"] >= T_BEFORE_START) & (fdf_pc["날짜"] <= T_BEFORE_END)]
        after  = fdf_pc[(fdf_pc["날짜"] >= T_AFTER_START)  & (fdf_pc["날짜"] <= T_AFTER_END)]

        period_df = pd.DataFrame([
            perf_row("5p구성 이전(6/1~6/16)",   before),
            perf_row("5p구성 적용(6/17~6/30)",  after),
            perf_row("총합계",                   fdf_pc),
        ])
        st.dataframe(style_with_total(period_df),
                     use_container_width=True, hide_index=True)

        st.markdown("---")

        # ── 3. 이벤트별 성과 ──────────────────────────────────
        st.markdown("**🎪 이벤트별 성과**")

        event_tbl = build_summary_table(fdf_pc, "스킴명")
        event_tbl = event_tbl.rename(columns={"스킴명": "이벤트명"})
        st.dataframe(style_with_total(style_summary(event_tbl, "이벤트명")),
                     use_container_width=True, hide_index=True)


# ══════════════════════════════════════════════════════════════
# TAB 3: 매체별
# ══════════════════════════════════════════════════════════════
with tab3:
    render_kpi(kpi)
    st.markdown("---")

    by_media = fdf.groupby("매체").agg(
        spend=("광고비 (KRW)", "sum"), imp=("노출", "sum"),
        clk=("클릭", "sum"), conv=("전환수", "sum"),
    ).reset_index()
    by_media["CTR"] = (by_media["clk"] / by_media["imp"].replace(0, float("nan")) * 100).fillna(0)
    by_media["CPC"] = (by_media["spend"] / by_media["clk"].replace(0, float("nan"))).fillna(0)
    by_media["CPA"] = (by_media["spend"] / by_media["conv"].replace(0, float("nan"))).fillna(0)

    col1, col2 = st.columns(2)
    with col1:
        fig_m1 = px.bar(by_media, x="매체", y="spend", title="매체별 광고비",
                        color="매체", color_discrete_sequence=PALETTE, text_auto=".0f")
        fig_m1.update_layout(height=320, showlegend=False,
                              plot_bgcolor="white", paper_bgcolor="white", yaxis_title="광고비 (KRW)")
        st.plotly_chart(fig_m1, use_container_width=True)
    with col2:
        fig_m2 = px.bar(by_media, x="매체", y="CPA", title="매체별 CPA",
                        color="매체", color_discrete_sequence=PALETTE, text_auto=".0f")
        fig_m2.update_layout(height=320, showlegend=False,
                              plot_bgcolor="white", paper_bgcolor="white", yaxis_title="CPA (KRW)")
        st.plotly_chart(fig_m2, use_container_width=True)

    render_table(fdf.sort_values("날짜", ascending=False).head(300))


# ══════════════════════════════════════════════════════════════
# TAB 4: 소재별
# ══════════════════════════════════════════════════════════════
with tab4:
    render_kpi(kpi)
    st.markdown("---")

    by_creative = fdf.groupby(["대분류 포맷", "영상/이미지 구분"]).agg(
        spend=("광고비 (KRW)", "sum"), imp=("노출", "sum"),
        clk=("클릭", "sum"), conv=("전환수", "sum"),
    ).reset_index()
    by_creative["CTR"] = (by_creative["clk"] / by_creative["imp"].replace(0, float("nan")) * 100).fillna(0)
    by_creative["CPA"] = (by_creative["spend"] / by_creative["conv"].replace(0, float("nan"))).fillna(0)

    fig_c = px.bar(by_creative, x="대분류 포맷", y="spend",
                   color="영상/이미지 구분", title="소재유형별 광고비",
                   barmode="group", color_discrete_sequence=PALETTE, text_auto=".0f")
    fig_c.update_layout(height=350, plot_bgcolor="white", paper_bgcolor="white",
                        yaxis_title="광고비 (KRW)")
    st.plotly_chart(fig_c, use_container_width=True)

    render_table(fdf.sort_values("날짜", ascending=False).head(300))


# ══════════════════════════════════════════════════════════════
# TAB 5: 제품별
# ══════════════════════════════════════════════════════════════
with tab5:
    render_kpi(kpi)
    st.markdown("---")

    by_prod = fdf.groupby("제품코드").agg(
        spend=("광고비 (KRW)", "sum"), imp=("노출", "sum"),
        clk=("클릭", "sum"), conv=("전환수", "sum"),
    ).reset_index()
    by_prod["CTR"] = (by_prod["clk"] / by_prod["imp"].replace(0, float("nan")) * 100).fillna(0)
    by_prod["CPA"] = (by_prod["spend"] / by_prod["conv"].replace(0, float("nan"))).fillna(0)

    col1, col2 = st.columns(2)
    with col1:
        fig_p1 = px.pie(by_prod, names="제품코드", values="spend",
                        title="제품별 광고비 비중", color_discrete_sequence=PALETTE)
        fig_p1.update_layout(height=320, paper_bgcolor="white")
        st.plotly_chart(fig_p1, use_container_width=True)
    with col2:
        fig_p2 = px.bar(by_prod, x="제품코드", y="CPA",
                        title="제품별 CPA", color="제품코드",
                        color_discrete_sequence=PALETTE, text_auto=".0f")
        fig_p2.update_layout(height=320, showlegend=False,
                              plot_bgcolor="white", paper_bgcolor="white", yaxis_title="CPA (KRW)")
        st.plotly_chart(fig_p2, use_container_width=True)

    render_table(fdf.sort_values("날짜", ascending=False).head(300))
