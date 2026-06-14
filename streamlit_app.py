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
    div[data-testid="stTabs"] button { font-size: 0.9rem; font-weight: 500; }
    .stDataFrame { border-radius: 8px; overflow: hidden; }
    footer { visibility: hidden; }
</style>
""", unsafe_allow_html=True)

# ── 브랜드 컬러 ────────────────────────────────────────────────
BRAND   = "#E8500A"
META_C  = "#1877F2"
TIKTOK_C = "#000000"
PALETTE = [BRAND, "#1877F2", "#1D9E75", "#7F77DD", "#D85A30", "#0F6E56"]

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

    # 타입 변환
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


# ── 데이터 로드 (에러 처리) ────────────────────────────────────
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
with st.sidebar:
    st.image("https://via.placeholder.com/160x40/E8500A/ffffff?text=LaraSweet", width=160)
    st.markdown("---")

    # 기간
    min_date = df["날짜"].min().date()
    max_date = df["날짜"].max().date()
    default_start = max(min_date, max_date - timedelta(days=89))

    st.markdown("**📅 기간**")
    col1, col2 = st.columns(2)
    with col1:
        start_date = st.date_input("시작", value=default_start, min_value=min_date, max_value=max_date, label_visibility="collapsed")
    with col2:
        end_date = st.date_input("종료", value=max_date, min_value=min_date, max_value=max_date, label_visibility="collapsed")

    st.markdown("**📺 매체**")
    media_opts = ["전체"] + sorted(df["매체"].dropna().unique().tolist())
    sel_media = st.selectbox("매체", media_opts, label_visibility="collapsed")

    st.markdown("**📢 소재유형**")
    types = ["전체"] + sorted(df["대분류 포맷"].dropna().unique().tolist())
    sel_type = st.selectbox("소재유형", types, label_visibility="collapsed")

    st.markdown("**📦 스킴명**")
    brands = ["전체"] + sorted(df["스킴명"].dropna().unique().tolist())
    sel_brand = st.selectbox("스킴명", brands, label_visibility="collapsed")

    st.markdown("---")
    if st.button("🔄 데이터 새로고침"):
        st.cache_data.clear()
        st.rerun()

    st.caption(f"최근 업데이트: {max_date}")


# ── 필터 적용 ──────────────────────────────────────────────────
mask = (
    (df["날짜"].dt.date >= start_date) &
    (df["날짜"].dt.date <= end_date)
)
if sel_brand != "전체":
    mask &= df["스킴명"] == sel_brand
if sel_type != "전체":
    mask &= df["대분류 포맷"] == sel_type
if sel_media != "전체":
    mask &= df["매체"] == sel_media

fdf = df[mask].copy()

if fdf.empty:
    st.warning("필터 조건에 맞는 데이터가 없어요. 필터를 조정해주세요.")
    st.stop()


# ── KPI 집계 ───────────────────────────────────────────────────
def calc_kpi(d: pd.DataFrame) -> dict:
    spend  = d["광고비 (KRW)"].sum()
    imp    = d["노출"].sum()
    clk    = d["클릭"].sum()
    conv   = d["전환수"].sum()
    ctr    = clk / imp * 100 if imp > 0 else 0
    cpa    = spend / conv if conv > 0 else 0
    return dict(spend=spend, imp=imp, clk=clk, conv=conv, ctr=ctr, cpa=cpa)

kpi = calc_kpi(fdf)


def fmt_krw(v):
    return f"₩{int(v):,}"

def fmt_num(v):
    return f"{int(v):,}"


# ── 탭 ────────────────────────────────────────────────────────
tab1, tab2, tab3, tab4 = st.tabs(["📊 전체 요약", "📺 매체별", "🎨 소재별", "📦 제품별"])


# ── 공통: KPI 카드 ─────────────────────────────────────────────
def render_kpi(kpi: dict):
    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("💰 광고비", fmt_krw(kpi["spend"]))
    c2.metric("👁 노출",   fmt_num(kpi["imp"]))
    c3.metric("🖱 클릭",   fmt_num(kpi["clk"]))
    c4.metric("🛒 전환수", fmt_num(kpi["conv"]))
    c5.metric("📈 CTR",    f"{kpi['ctr']:.2f}%")
    c6.metric("🎯 CPA",    fmt_krw(kpi["cpa"]))


# ── 공통: 정렬된 테이블 ───────────────────────────────────────
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
            styled[c] = styled[c].apply(lambda x: f"₩{int(x):,}")
    for c in ["CTR (%)"]:
        if c in styled.columns:
            styled[c] = styled[c].apply(lambda x: f"{x:.2f}%")
    st.dataframe(styled, use_container_width=True, hide_index=True)


# ══════════════════════════════════════════════════════════════
# TAB 1: 전체 요약
# ══════════════════════════════════════════════════════════════
with tab1:
    render_kpi(kpi)
    st.markdown("---")

    daily = (
        fdf.groupby(fdf["날짜"].dt.date)
        .agg(spend=("광고비 (KRW)", "sum"), conv=("전환수", "sum"),
             clk=("클릭", "sum"), imp=("노출", "sum"))
        .reset_index().rename(columns={"날짜": "date"})
    )

    fig = go.Figure()
    fig.add_bar(
        x=daily["date"], y=daily["spend"] / 1_000_000,
        name="광고비(M)", marker_color=BRAND, opacity=0.75,
        yaxis="y1",
    )
    fig.add_scatter(
        x=daily["date"], y=daily["conv"],
        name="전환수", mode="lines+markers",
        line=dict(color="#1D9E75", width=2),
        marker=dict(size=5), yaxis="y2",
    )
    fig.update_layout(
        title="일별 광고비 & 전환수",
        xaxis=dict(title=""),
        yaxis=dict(title="광고비 (백만원)", ticksuffix="M", showgrid=True, gridcolor="#f0f0f0"),
        yaxis2=dict(title="전환수", overlaying="y", side="right", showgrid=False),
        legend=dict(orientation="h", y=1.08),
        plot_bgcolor="white", paper_bgcolor="white",
        margin=dict(t=60, b=40),
        height=360,
    )
    st.plotly_chart(fig, use_container_width=True)

    col_a, col_b = st.columns(2)
    with col_a:
        by_type = fdf.groupby("대분류 포맷")["광고비 (KRW)"].sum().reset_index()
        fig2 = px.pie(by_type, names="대분류 포맷", values="광고비 (KRW)",
                      title="소재유형별 광고비 비중",
                      color_discrete_sequence=PALETTE)
        fig2.update_layout(height=300, margin=dict(t=50, b=20),
                           paper_bgcolor="white", plot_bgcolor="white")
        st.plotly_chart(fig2, use_container_width=True)

    with col_b:
        by_media = fdf.groupby("매체").agg(
            spend=("광고비 (KRW)", "sum"), conv=("전환수", "sum"),
            clk=("클릭", "sum"), imp=("노출", "sum")
        ).reset_index()
        by_media["CPA"] = (by_media["spend"] / by_media["conv"].replace(0, float("nan"))).fillna(0)
        fig3 = px.bar(by_media, x="매체", y="CPA", title="매체별 CPA 비교",
                      color="매체", color_discrete_map={"Meta": META_C, "TikTok": "#69C9D0"},
                      text_auto=".0f")
        fig3.update_layout(height=300, margin=dict(t=50, b=20), showlegend=False,
                           plot_bgcolor="white", paper_bgcolor="white",
                           yaxis_title="CPA (KRW)")
        st.plotly_chart(fig3, use_container_width=True)

    st.markdown("**📋 상세 데이터**")
    render_table(fdf.sort_values("날짜", ascending=False).head(200))


# ══════════════════════════════════════════════════════════════
# TAB 2: 매체별
# ══════════════════════════════════════════════════════════════
with tab2:
    render_kpi(kpi)
    st.markdown("---")

    by_media_day = (
        fdf.groupby([fdf["날짜"].dt.date, "매체"])
        .agg(spend=("광고비 (KRW)", "sum"), conv=("전환수", "sum"),
             clk=("클릭", "sum"), imp=("노출", "sum"))
        .reset_index().rename(columns={"날짜": "date"})
    )

    col_a, col_b = st.columns(2)
    with col_a:
        fig = px.bar(by_media_day, x="date", y="spend", color="매체",
                     title="매체별 일별 광고비",
                     color_discrete_map={"Meta": META_C, "TikTok": "#69C9D0"},
                     barmode="stack")
        fig.update_layout(height=300, plot_bgcolor="white", paper_bgcolor="white",
                          yaxis_title="광고비 (KRW)", margin=dict(t=50, b=30))
        st.plotly_chart(fig, use_container_width=True)

    with col_b:
        fig = px.line(by_media_day, x="date", y="conv", color="매체",
                      title="매체별 일별 전환수",
                      color_discrete_map={"Meta": META_C, "TikTok": "#69C9D0"},
                      markers=True)
        fig.update_layout(height=300, plot_bgcolor="white", paper_bgcolor="white",
                          yaxis_title="전환수", margin=dict(t=50, b=30))
        st.plotly_chart(fig, use_container_width=True)

    tbl = (
        fdf.groupby("매체")
        .agg(
            광고비=("광고비 (KRW)", "sum"),
            노출=("노출", "sum"),
            클릭=("클릭", "sum"),
            전환수=("전환수", "sum"),
        )
        .reset_index()
    )
    tbl["CTR (%)"] = (tbl["클릭"] / tbl["노출"] * 100).round(2)
    tbl["CPA (KRW)"] = (tbl["광고비"] / tbl["전환수"].replace(0, float("nan"))).fillna(0).astype(int)
    tbl = tbl.rename(columns={"광고비": "광고비 (KRW)"})
    st.markdown("**매체별 집계**")
    st.dataframe(tbl, use_container_width=True, hide_index=True)


# ══════════════════════════════════════════════════════════════
# TAB 3: 소재별
# ══════════════════════════════════════════════════════════════
with tab3:
    render_kpi(kpi)
    st.markdown("---")

    group_by = st.radio("그룹 기준", ["광고그룹명", "소재명", "대분류 포맷"], horizontal=True)

    by_creative = (
        fdf.groupby(group_by)
        .agg(
            광고비=("광고비 (KRW)", "sum"),
            노출=("노출", "sum"),
            클릭=("클릭", "sum"),
            전환수=("전환수", "sum"),
        )
        .reset_index()
    )
    by_creative["CTR (%)"] = (by_creative["클릭"] / by_creative["노출"] * 100).round(2)
    by_creative["CPA (KRW)"] = (
        by_creative["광고비"] / by_creative["전환수"].replace(0, float("nan"))
    ).fillna(0).astype(int)
    by_creative = by_creative.sort_values("광고비", ascending=False)

    top15 = by_creative.head(15)
    fig = px.bar(
        top15, x="광고비", y=group_by,
        orientation="h", title=f"{group_by}별 광고비 Top 15",
        color="CPA (KRW)",
        color_continuous_scale=["#1D9E75", "#FAC775", "#D85A30"],
        text_auto=".3s",
    )
    fig.update_layout(
        height=max(350, len(top15) * 32 + 80),
        plot_bgcolor="white", paper_bgcolor="white",
        margin=dict(t=50, b=30), yaxis_title="",
        coloraxis_colorbar=dict(title="CPA"),
    )
    fig.update_yaxes(autorange="reversed")
    st.plotly_chart(fig, use_container_width=True)

    st.markdown(f"**{group_by}별 전체 집계**")
    tbl = by_creative.rename(columns={"광고비": "광고비 (KRW)"})
    st.dataframe(tbl, use_container_width=True, hide_index=True)


# ══════════════════════════════════════════════════════════════
# TAB 4: 제품별
# ══════════════════════════════════════════════════════════════
with tab4:
    kpi4 = calc_kpi(fdf[fdf["매체"].isin(["Meta", "TikTok"])])
    render_kpi(kpi4)
    st.markdown("---")

    by_brand = (
        fdf.groupby("스킴명")
        .agg(
            광고비=("광고비 (KRW)", "sum"),
            노출=("노출", "sum"),
            클릭=("클릭", "sum"),
            전환수=("전환수", "sum"),
        )
        .reset_index()
    )
    by_brand["CTR (%)"] = (by_brand["클릭"] / by_brand["노출"] * 100).round(2)
    by_brand["CPA (KRW)"] = (
        by_brand["광고비"] / by_brand["전환수"].replace(0, float("nan"))
    ).fillna(0).astype(int)
    by_brand = by_brand.sort_values("광고비", ascending=False)

    col_a, col_b = st.columns(2)
    with col_a:
        fig = px.pie(by_brand.head(10), names="스킴명", values="광고비",
                     title="스킴별 광고비 비중 (Top 10)",
                     color_discrete_sequence=PALETTE)
        fig.update_layout(height=320, paper_bgcolor="white", margin=dict(t=50))
        st.plotly_chart(fig, use_container_width=True)

    with col_b:
        fig = px.bar(by_brand.head(10), x="스킴명", y="CPA (KRW)",
                     title="스킴별 CPA (Top 10)",
                     color_discrete_sequence=[BRAND],
                     text_auto=".0f")
        fig.update_layout(height=320, plot_bgcolor="white", paper_bgcolor="white",
                          margin=dict(t=50, b=60),
                          xaxis=dict(tickangle=-30))
        st.plotly_chart(fig, use_container_width=True)

    st.markdown("**스킴명별 전체 집계**")
    tbl = by_brand.rename(columns={"광고비": "광고비 (KRW)"})
    st.dataframe(tbl, use_container_width=True, hide_index=True)
