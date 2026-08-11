# -*- coding: utf-8 -*-
"""
라라스윗 광고 대시보드
Streamlit + Plotly | 데이터 소스: Google Sheets (통합RD_원본)
"""
import html as _html
import re
import time
import uuid
import requests
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
    [data-testid="stSidebarNav"] { display: none; }
    [data-testid="stSidebar"] h2 { font-size: 0.95rem !important; margin-bottom: 0.2rem; }
    [data-testid="stSidebar"] p,
    [data-testid="stSidebar"] label,
    [data-testid="stSidebar"] .stMarkdown p { font-size: 0.75rem !important; }
    [data-testid="stSidebar"] [data-testid="stMultiSelect"] { font-size: 0.75rem; }
    [data-testid="stSidebar"] button { font-size: 0.75rem !important; }
    [data-testid="stSidebar"] .stCaption { font-size: 0.68rem !important; }
    div[data-testid="stTabs"] button { font-size: 0.9rem; font-weight: 500; }
    .stButton button p { white-space: nowrap; }
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
# --- 단쉐 스킴 기준일 ---
SK_SCHEME1_START = pd.Timestamp("2026-06-24")
SK_SCHEME1_END   = pd.Timestamp("2026-06-26")
SK_SCHEME2_START = pd.Timestamp("2026-06-27")
SK_SCHEME2_END   = pd.Timestamp("2026-06-30")
SK_SCHEME3_START = pd.Timestamp("2026-07-01")
SK_SCHEME3_END   = pd.Timestamp("2026-07-05")
SK_SCHEME4_START = pd.Timestamp("2026-07-06")  # 4차 스킴: 종료일 미정 (이후 전체)
# --- 블트하 노출 가중목 ---
BT_GOAL_IMP   = 22_000_000
BT_GOAL_START = pd.Timestamp("2026-07-15")
BT_GOAL_END   = pd.Timestamp("2026-07-31")
# --- 신규소재 집행일자별 성과 기준일 (블트하·팝콘 공통) ---
NEW_CREATIVE_START = "260720"
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
def render_pinned_total_table(df: pd.DataFrame, compact: bool = False) -> None:
    _tw = "100%"
    if compact:
        _hl_map  = {"광고비": "background:#FFF9F1;", "CPA": "background:#F2F6FC;"}
        _hlh_map = {"광고비": "background:#FFF3E4;color:#9A5B1F;", "CPA": "background:#EAF1FB;color:#2D5586;"}
        col_extra  = [_hl_map.get(str(c), "") for c in df.columns]
        head_extra = [_hlh_map.get(str(c), "") for c in df.columns]
        colgroup = "<colgroup><col>" + '<col style="width:8.5%">' * (len(df.columns) - 1) + "</colgroup>"
    else:
        col_extra  = ["" for _ in df.columns]
        head_extra = ["" for _ in df.columns]
        colgroup = ""
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
        f'<th style="{th}{head_extra[i]}" onclick="sortTbl(\'{tid}\',{i})" data-order="">'
        f'{_esc(col)} <span style="color:#bbb;font-size:0.7rem">&#x21C5;</span></th>'
        for i, col in enumerate(df.columns)
    )
    bdy = "".join(
        "<tr>" + "".join(f'<td style="{td}{col_extra[j]}">{_esc(v)}</td>'
                         for j, v in enumerate(row)) + "</tr>"
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
        f'<table id="{tid}" style="width:{_tw}; border-collapse:collapse;">{colgroup}'
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
def hr_perf_row(label: str, d: pd.DataFrame, key_col: str = "구분") -> dict:
    """perf_row + CPM (시간대별 테이블용)"""
    r = perf_row(label, d, key_col=key_col)
    s = d["광고비 (KRW)"].sum()
    i = d["노출"].sum()
    r["CPM"] = f"{int(s / i * 1000):,}" if i > 0 else "0"
    return r
def render_tree_table(groups, total_row, cols) -> None:
    """접기/펼치기 트리 테이블 (CSS 체크박스 방식, iframe 미사용).
    페이지 흐름에 직접 렌더링되어 접힌 상태에선 공백이 없고,
    펼치면 그만큼 아래 콘텐츠가 자연스럽게 밀려난다.
    groups: [(부모라벨, 부모행dict, [(자식라벨, 자식행dict), ...]), ...]
    total_row: 총합계 행 dict / cols: 컬럼 순서 (첫 컬럼 = 구분)
    """
    tid  = "tt" + uuid.uuid4().hex[:8]
    th   = ("padding:7px 10px;text-align:left;background:#f0f2f6;"
            "border-bottom:2px solid #ddd;font-size:0.82rem;white-space:nowrap;")
    tdp  = "padding:6px 10px;border-bottom:1px solid #eee;font-size:0.82rem;white-space:nowrap;"
    tdc1 = ("padding:5px 10px 5px 28px;border-bottom:1px solid #f5f5f5;"
            "font-size:0.80rem;white-space:nowrap;color:#555;background:#fafcff;")
    tdcn = ("padding:5px 10px;border-bottom:1px solid #f5f5f5;"
            "font-size:0.80rem;white-space:nowrap;color:#555;background:#fafcff;")
    tft  = (f"padding:6px 10px;font-size:0.82rem;white-space:nowrap;"
            f"background:{TOTAL_BG};color:{TOTAL_FG};font-weight:{TOTAL_FONT};"
            f"border-top:2px solid #ddd;")
    css = (
        f"<style>"
        f"#{tid} tr.ttc{{display:none;}}"
        f"#{tid} span.tti::before{{content:'▶';font-size:0.7rem;color:#888;}}"
        f"#{tid} label{{cursor:pointer;display:block;margin:0;font-weight:inherit;}}"
        + "".join(
            f"#{tid} tr.ttp{i}:has(input:checked) ~ tr.ttc{i}{{display:table-row;}}"
            f"#{tid} tr.ttp{i}:has(input:checked) span.tti::before{{content:'▼';}}"
            for i in range(len(groups))
        )
        + "</style>"
    )
    hdr = "".join(f'<th style="{th}">{_esc(c)}</th>' for c in cols)
    body = ""
    for i, (plabel, prow, children) in enumerate(groups):
        cb = f"{tid}cb{i}"
        first = (f'<td style="{tdp}padding:0;">'
                 f'<label for="{cb}" style="padding:6px 10px;">'
                 f'<input type="checkbox" id="{cb}" style="display:none;">'
                 f'<span class="tti" style="display:inline-block;width:14px;"></span>'
                 f'{_esc(plabel)}</label></td>')
        rest = "".join(f'<td style="{tdp}">{_esc(prow[c])}</td>' for c in cols[1:])
        body += f'<tr class="ttp{i}">{first}{rest}</tr>'
        for clabel, crow in children:
            c1 = f'<td style="{tdc1}">{_esc(clabel)}</td>'
            cr = "".join(f'<td style="{tdcn}">{_esc(crow[c])}</td>' for c in cols[1:])
            body += f'<tr class="ttc ttc{i}">{c1}{cr}</tr>'
    ftd = "".join(f'<td style="{tft}">{_esc(total_row[c])}</td>' for c in cols)
    html = (
        css
        + '<div style="overflow-x:auto;border-radius:8px;border:1px solid #e0e0e0;">'
        f'<table id="{tid}" style="width:100%;border-collapse:collapse;">'
        f'<thead><tr>{hdr}</tr></thead>'
        f'<tbody>{body}</tbody>'
        f'<tfoot><tr>{ftd}</tr></tfoot>'
        '</table></div>'
    )
    st.markdown(html, unsafe_allow_html=True)
def render_tree_table3(groups, total_row, cols, compact: bool = False) -> None:
    """3단계 접기/펼치기 트리 테이블 (부모 → 자식 → 손자, CSS 체크박스 방식).
    groups: [(부모라벨, 부모행, [(자식라벨, 자식행, [(손자라벨, 손자행), ...]), ...]), ...]
    """
    tid  = "tt" + uuid.uuid4().hex[:8]
    th   = ("padding:7px 10px;text-align:left;background:#f0f2f6;"
            "border-bottom:2px solid #ddd;font-size:0.82rem;white-space:nowrap;")
    tdp  = "padding:6px 10px;border-bottom:1px solid #eee;font-size:0.82rem;white-space:nowrap;"
    tdc1 = ("border-bottom:1px solid #f5f5f5;"
            "font-size:0.80rem;white-space:nowrap;color:#555;background:#fafcff;")
    tdcn = ("padding:5px 10px;border-bottom:1px solid #f5f5f5;"
            "font-size:0.80rem;white-space:nowrap;color:#555;background:#fafcff;")
    tdg1 = ("padding:4px 10px 4px 46px;border-bottom:1px solid #f8f8f8;"
            "font-size:0.78rem;white-space:nowrap;color:#777;background:#f4f8fd;")
    tdgn = ("padding:4px 10px;border-bottom:1px solid #f8f8f8;"
            "font-size:0.78rem;white-space:nowrap;color:#777;background:#f4f8fd;")
    tft  = (f"padding:6px 10px;font-size:0.82rem;white-space:nowrap;"
            f"background:{TOTAL_BG};color:{TOTAL_FG};font-weight:{TOTAL_FONT};"
            f"border-top:2px solid #ddd;")
    css_rules = [
        f"#{tid} tr.ttc{{display:none;}}",
        f"#{tid} span.tti::before{{content:'▶';font-size:0.7rem;color:#888;}}",
        f"#{tid} label{{cursor:pointer;display:block;margin:0;font-weight:inherit;}}",
    ]
    for i, (_, _, children) in enumerate(groups):
        css_rules.append(f"#{tid} tr.ttp{i}:has(input:checked) ~ tr.ttq{i}{{display:table-row;}}")
        css_rules.append(f"#{tid} tr.ttp{i}:has(input:checked) span.tti::before{{content:'▼';}}")
        for j in range(len(children)):
            css_rules.append(
                f"#{tid} tr.ttp{i}:has(input:checked) ~ tr.ttq{i}_{j}:has(input:checked)"
                f" ~ tr.ttg{i}_{j}{{display:table-row;}}")
            css_rules.append(f"#{tid} tr.ttq{i}_{j}:has(input:checked) span.tti::before{{content:'▼';}}")
    css = "<style>" + "".join(css_rules) + "</style>"
    hl  = {"광고비": "background:#FFF9F1;", "CPA": "background:#F2F6FC;"} if compact else {}
    hlh = {"광고비": "background:#FFF3E4;color:#9A5B1F;", "CPA": "background:#EAF1FB;color:#2D5586;"} if compact else {}
    colgr = ("<colgroup><col>" + '<col style="width:8.5%">' * (len(cols) - 1) + "</colgroup>") if compact else ""
    hdr = "".join(f'<th style="{th}{hlh.get(c, "")}">{_esc(c)}</th>' for c in cols)
    body = ""
    for i, (plabel, prow, children) in enumerate(groups):
        cbp = f"{tid}p{i}"
        first = (f'<td style="{tdp}padding:0;">'
                 f'<label for="{cbp}" style="padding:6px 10px;">'
                 f'<input type="checkbox" id="{cbp}" style="display:none;">'
                 f'<span class="tti" style="display:inline-block;width:14px;"></span>'
                 f'{_esc(plabel)}</label></td>')
        rest = "".join(f'<td style="{tdp}{hl.get(c, "")}">{_esc(prow[c])}</td>' for c in cols[1:])
        body += f'<tr class="ttp{i}">{first}{rest}</tr>'
        for j, (clabel, crow, grands) in enumerate(children):
            cbq = f"{tid}q{i}_{j}"
            cfirst = (f'<td style="{tdc1}padding:0;">'
                      f'<label for="{cbq}" style="padding:5px 10px 5px 28px;">'
                      f'<input type="checkbox" id="{cbq}" style="display:none;">'
                      f'<span class="tti" style="display:inline-block;width:14px;"></span>'
                      f'{_esc(clabel)}</label></td>')
            crest = "".join(f'<td style="{tdcn}{hl.get(c, "")}">{_esc(crow[c])}</td>' for c in cols[1:])
            body += f'<tr class="ttc ttq{i} ttq{i}_{j}">{cfirst}{crest}</tr>'
            for glabel, grow in grands:
                g1 = f'<td style="{tdg1}">{_esc(glabel)}</td>'
                gr = "".join(f'<td style="{tdgn}{hl.get(c, "")}">{_esc(grow[c])}</td>' for c in cols[1:])
                body += f'<tr class="ttc ttg{i}_{j}">{g1}{gr}</tr>'
    ftd = "".join(f'<td style="{tft}">{_esc(total_row[c])}</td>' for c in cols)
    html = (
        css
        + '<div style="overflow-x:auto;border-radius:8px;border:1px solid #e0e0e0;">'
        f'<table id="{tid}" style="width:100%;border-collapse:collapse;">{colgr}'
        f'<thead><tr>{hdr}</tr></thead>'
        f'<tbody>{body}</tbody>'
        f'<tfoot><tr>{ftd}</tr></tfoot>'
        '</table></div>'
    )
    st.markdown(html, unsafe_allow_html=True)
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
def daily_tree_table(d: pd.DataFrame, with_cpm: bool = False) -> None:
    """일별 광고비 테이블 — 일자 클릭 시 광고 유형별(V/I) 성과 펼침"""
    _pr = hr_perf_row if with_cpm else perf_row
    _cols = (["일", "광고비", "노출", "링크 클릭", "구매", "CTR", "CPC"]
             + (["CPM"] if with_cpm else []) + ["CVR", "CPA"])
    _vi_label = {"V": "V (영상)", "I": "I (이미지)"}
    groups = []
    for _dt in sorted(d["날짜"].dt.date.unique()):
        _sub = d[d["날짜"].dt.date == _dt]
        _kids = []
        for _vi, _vi_sub in _sub.groupby(_sub["영상/이미지 구분"].astype(str).str.strip().str.upper()):
            _lb = _vi_label.get(_vi, _vi if _vi else "(미분류)")
            _kids.append((_lb, _pr(_lb, _vi_sub, key_col="일"),
                          _vi_sub["광고비 (KRW)"].sum()))
        _kids.sort(key=lambda x: x[2], reverse=True)
        groups.append((str(_dt), _pr(str(_dt), _sub, key_col="일"),
                       [(_a, _r) for _a, _r, _ in _kids]))
    render_tree_table(groups, _pr("총합계", d, key_col="일"), _cols)

def cpm_summary_table(d: pd.DataFrame, group_col: str, first_col: str) -> None:
    """CPM 포함 그룹별 요약 테이블 (광고비 내림차순 + 총합계 고정)"""
    _cols = [first_col, "광고비", "노출", "링크 클릭", "구매", "CTR", "CPC", "CPM", "CVR", "CPA"]
    rows = []
    for _g, _sub in d.groupby(group_col):
        if not str(_g).strip():
            continue
        rows.append((hr_perf_row(str(_g), _sub, key_col=first_col), _sub["광고비 (KRW)"].sum()))
    rows.sort(key=lambda x: x[1], reverse=True)
    out = [r for r, _ in rows] + [hr_perf_row("총합계", d, key_col=first_col)]
    render_pinned_total_table(pd.DataFrame(out)[_cols])
def render_new_creative_table(d: pd.DataFrame) -> None:
    """신규소재 집행일자별 성과 (집행시작일 ≥ NEW_CREATIVE_START, CPM 포함).
    집행시작일별 그룹 → 집행일 클릭 시 소재명별 성과 펼침 (2단 트리).
    전달받은 d의 사이드바 필터가 그대로 반영된다."""
    _cols = ["집행시작일", "광고비", "노출", "링크 클릭", "구매", "CTR", "CPC", "CPM", "CVR", "CPA"]
    dd = d.copy()
    if "집행시작일" in dd.columns:
        dd = dd[
            dd["집행시작일"].astype(str).str.match(r"^\d{6}$") &
            (dd["집행시작일"].astype(str) >= NEW_CREATIVE_START)
        ]
    else:
        dd = dd.iloc[0:0]
    if dd.empty:
        st.info(f"집행시작일 {NEW_CREATIVE_START} 이후 소재 데이터가 없습니다.")
        return
    _groups = []
    for _sd in sorted(dd["집행시작일"].astype(str).unique()):
        _sub = dd[dd["집행시작일"].astype(str) == _sd]
        _ads = [
            (_an,
             hr_perf_row(_an, _sub[_sub["소재명"] == _an], key_col="집행시작일"),
             _sub[_sub["소재명"] == _an]["광고비 (KRW)"].sum())
            for _an in _sub["소재명"].unique()
        ]
        _ads.sort(key=lambda x: x[2], reverse=True)
        _groups.append((
            _sd,
            hr_perf_row(_sd, _sub, key_col="집행시작일"),
            [(_a, _r) for _a, _r, _ in _ads],
        ))
    render_tree_table(_groups, hr_perf_row("총합계", dd, key_col="집행시작일"), _cols)
def banner_segments(ad_name: str) -> list:
    """소재명 9번째 토큰(parts[8])을 온점 분해해 배너 세부 조각 반환.
    예: '[26.07]F_I_PC치_..._.피드_이니1.맛강조.스토리형.__권미정_...'
        → parts[8]='이니1.맛강조.스토리형.' → ['이니1', '맛강조', '스토리형']
    마지막 조각 = 배너 포맷(스토리형/댓글형), 마지막-1 = 소구점(맛강조/페포/대세감)
    """
    parts = str(ad_name).split("_")
    if len(parts) < 9:
        return []
    return [s for s in parts[8].split(".") if s.strip()]
def render_banner_table(d: pd.DataFrame, kind: str) -> None:
    """배너(I) 소재의 포맷별/소구점별 성과 (그룹 클릭 → 소재별 펼침, CPM 포함).
    kind: 'format' = 마지막 조각(스토리형/댓글형) / 'appeal' = 마지막-1 조각(맛강조/페포/대세감)
    """
    _label = "배너 포맷" if kind == "format" else "소구점"
    _cols = [_label, "광고비", "노출", "링크 클릭", "구매", "CTR", "CPC", "CPM", "CVR", "CPA"]
    dd = d[d["영상/이미지 구분"].astype(str).str.strip().str.upper() == "I"].copy()
    if dd.empty:
        st.info("배너(I) 소재 데이터가 없습니다.")
        return
    _need = 1 if kind == "format" else 2
    def _pick(_n):
        _segs = banner_segments(_n)
        return _segs[-_need] if len(_segs) >= _need + 1 else "(미분류)"
    dd["_SEG"] = dd["소재명"].apply(_pick)
    _groups = []
    for _g, _sub in dd.groupby("_SEG"):
        _ads = [
            (_an,
             hr_perf_row(_an, _sub[_sub["소재명"] == _an], key_col=_label),
             _sub[_sub["소재명"] == _an]["광고비 (KRW)"].sum())
            for _an in _sub["소재명"].unique()
        ]
        _ads.sort(key=lambda x: x[2], reverse=True)
        _groups.append((
            str(_g),
            hr_perf_row(str(_g), _sub, key_col=_label),
            [(_a, _r) for _a, _r, _ in _ads],
            _sub["광고비 (KRW)"].sum(),
        ))
    _groups.sort(key=lambda x: x[3], reverse=True)
    render_tree_table(
        [(_g2[0], _g2[1], _g2[2]) for _g2 in _groups],
        hr_perf_row("총합계", dd, key_col=_label),
        _cols,
    )
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
# 데이터 업데이트 (GitHub Actions 트리거)
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
    """refresh.yml 워크플로우 실행 요청. 성공 시 (True, ''), 실패 시 (False, 사유)"""
    url = (f"https://api.github.com/repos/{GH_OWNER}/{GH_REPO}"
           f"/actions/workflows/{REFRESH_WORKFLOW}/dispatches")
    try:
        r = requests.post(url, headers=_gh_headers(),
                          json={"ref": "main", "inputs": {"mode": mode}}, timeout=30)
    except Exception as e:
        return False, f"요청 실패: {e}"
    if r.status_code == 204:
        return True, ""
    return False, f"HTTP {r.status_code}: {r.text[:300]}"

def latest_refresh_run():
    """refresh.yml의 가장 최근 실행 정보 (없으면 None)"""
    url = (f"https://api.github.com/repos/{GH_OWNER}/{GH_REPO}"
           f"/actions/workflows/{REFRESH_WORKFLOW}/runs")
    try:
        r = requests.get(url, headers=_gh_headers(),
                         params={"per_page": 1}, timeout=30)
        runs = r.json().get("workflow_runs", [])
        return runs[0] if runs else None
    except Exception:
        return None

@st.cache_data(ttl=300, show_spinner=False)
def last_collection_time():
    """가장 최근 수집 성공 시각 (정기 수집·버튼 업데이트·백필 포함, 5분 캐시)"""
    if "github_token" not in st.secrets:
        return None
    latest = None
    for wf in ["daily_report.yml", "refresh.yml", "backfill.yml"]:
        try:
            r = requests.get(
                f"https://api.github.com/repos/{GH_OWNER}/{GH_REPO}"
                f"/actions/workflows/{wf}/runs",
                headers=_gh_headers(),
                params={"status": "success", "per_page": 1}, timeout=15)
            runs = r.json().get("workflow_runs", [])
            if runs:
                t = pd.to_datetime(runs[0]["updated_at"])
                if latest is None or t > latest:
                    latest = t
        except Exception:
            continue
    return latest

def _data_freshness_line():
    """'데이터 기준일 · 마지막 수집' 표시 문자열"""
    try:
        d = df["날짜"].max().date()
    except Exception:
        return ""
    today_kst = pd.Timestamp.now(tz="Asia/Seoul").date()
    diff = (today_kst - d).days
    if diff == 0:
        base = f"{d.month}/{d.day} (오늘)"
    elif diff == 1:
        base = f"{d.month}/{d.day} (어제)"
    else:
        base = str(d)
    line = f"🕐 데이터 기준일 **{base}**"
    t = last_collection_time()
    if t is not None:
        t_kst = t.tz_convert("Asia/Seoul")
        day = "오늘 " if t_kst.date() == today_kst else f"{t_kst.month}/{t_kst.day} "
        line += f" · 마지막 수집 **{day}{t_kst.strftime('%H:%M')}**"
    return line

def _start_refresh(mode, label):
    ok, err = trigger_refresh(mode)
    if ok:
        st.session_state["refresh_active"] = True
        st.session_state["refresh_started"] = time.time()
        st.session_state["refresh_label"] = label
        st.session_state.pop("refresh_msg", None)
    else:
        st.session_state["refresh_msg"] = f"❌ 실행 요청 실패: {err}"
    st.rerun()

def _render_refresh_status():
    """진행 상태 표시. 진행 중이면 fragment로 10초마다 자동 갱신되고,
    완료 감지 시 캐시를 지우고 전체 대시보드를 자동 반영한다."""
    if not st.session_state.get("refresh_active"):
        msg = st.session_state.get("refresh_msg")
        if msg:
            st.markdown(msg)
        line = _data_freshness_line()
        if line:
            st.caption(line)
        return
    started = st.session_state.get("refresh_started", time.time())
    label   = st.session_state.get("refresh_label", "")
    elapsed = int(time.time() - started)
    run = latest_refresh_run()
    run_is_current = False
    if run is not None:
        try:
            created = pd.to_datetime(run.get("created_at")).timestamp()
            run_is_current = created >= started - 60
        except Exception:
            run_is_current = False
    if run_is_current and run.get("status") == "completed":
        st.session_state["refresh_active"] = False
        if run.get("conclusion") == "success":
            st.cache_data.clear()
            done_at = pd.Timestamp.now(tz="Asia/Seoul").strftime("%H:%M")
            st.session_state["refresh_msg"] = f"✅ {label} 업데이트 완료 — 대시보드에 반영됨 ({done_at})"
        else:
            st.session_state["refresh_msg"] = (f"❌ {label} 업데이트 실패 — "
                                               f"[Actions 로그 확인]({run.get('html_url')})")
        st.rerun(scope="app")
    elif elapsed > 900:
        st.session_state["refresh_active"] = False
        st.session_state["refresh_msg"] = ("⏱ 15분이 지나도 완료되지 않아 자동 확인을 중단했어요. "
                                           "GitHub Actions에서 상태를 확인해주세요.")
        st.rerun(scope="app")
    else:
        st.markdown(f"⏳ **{label} 업데이트 진행 중** ({elapsed // 60}분 {elapsed % 60}초 경과) "
                    f"— 완료되면 자동 반영됩니다")

def render_update_buttons():
    if "github_token" not in st.secrets:
        st.caption("⚙️ 업데이트 버튼을 사용하려면 Streamlit secrets에 `github_token`을 추가해주세요.")
        return
    active = st.session_state.get("refresh_active", False)
    c1, c2, c3 = st.columns([1.3, 1.6, 5.1], gap="small", vertical_alignment="center")
    if c1.button("📥 전일자 업데이트", disabled=active,
                 help="어제 데이터를 다시 수집해 최신 수치로 교체합니다 (약 2~4분 소요)"):
        _start_refresh("yesterday", "전일자")
    if c2.button("⚡ 실시간 업데이트 (오늘)", disabled=active,
                 help="오늘 데이터를 수집합니다. 당일 수치는 잠정치이며 계속 변합니다 (약 2~4분 소요)"):
        _start_refresh("today", "실시간")
    with c3:
        if active:
            st.fragment(_render_refresh_status, run_every=10)()
        else:
            _render_refresh_status()
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


GFA_PARSE_COLS = [
    "제작월", "채널구분", "영상/이미지 구분", "제품코드", "광고종류",
    "스킴명", "대분류 포맷", "소분류 연출",
    "배리에이션 여부", "지면 유형", "상세연출(소재구분)", "프로젝트",
    "파트 구분", "마케터", "집행시작일", "본부 구분", "PD/디자이너",
]
def parse_ad_name_gfa(ad_name: str) -> dict:
    """파일명 생성기 규칙 파싱 (build_rd.py parse_ad_name과 동일 로직).
    GFA는 시트 원본을 대시보드가 직접 읽으므로 여기서 파싱한다.
    예: [26.08]GF_I_BT칩_전환_블트칩출시_혜택강조형_크래커_.배너_트러플풍미부터.1250_560__최나영_260806_제과_김수정
    """
    result = {c: "" for c in GFA_PARSE_COLS}
    if not isinstance(ad_name, str) or not ad_name.startswith("["):
        return result
    parts = ad_name.split("_")
    if len(parts) < 3:
        return result
    try:
        m = re.match(r"(\[.+?\])(.*)", parts[0])
        if m:
            result["제작월"] = m.group(1)
            result["채널구분"] = m.group(2)   # GFA는 'GF'
        if len(parts) > 1: result["영상/이미지 구분"] = parts[1]
        if len(parts) > 2: result["제품코드"] = parts[2]
        if len(parts) > 3: result["광고종류"] = parts[3]
        if len(parts) > 4: result["스킴명"] = parts[4]
        if len(parts) > 5: result["대분류 포맷"] = parts[5]
        if len(parts) > 6: result["소분류 연출"] = parts[6]
        if len(parts) > 7:
            kl = parts[7].split(".", 1)
            result["배리에이션 여부"] = kl[0]
            result["지면 유형"] = kl[1] if len(kl) > 1 else ""
        if len(parts) > 8:
            mn = parts[8].split(".", 1)
            result["상세연출(소재구분)"] = mn[0]
            result["프로젝트"] = mn[1] if len(mn) > 1 else ""
        if len(parts) > 9:  result["파트 구분"] = parts[9]
        if len(parts) > 10: result["마케터"] = parts[10]
        if len(parts) > 11: result["집행시작일"] = parts[11]
        if len(parts) > 12: result["본부 구분"] = parts[12]
        if len(parts) > 13: result["PD/디자이너"] = "_".join(parts[13:])
    except Exception:
        pass
    return result
@st.cache_data(ttl=3600, show_spinner="GFA 데이터 불러오는 중...")
def load_gfa_data() -> pd.DataFrame:
    """구글시트 'GFA_원본' 탭(네이버 GFA 리포트 붙여넣기)을 통합RD 스키마로 변환.
    - 전환수 = '구매완료 수' (메타/틱톡의 purchase 기준과 통일. GFA 기본 '결과'는 장바구니 포함)
    - 매출 (KRW) = '총 전환매출액' (= 구매완료 전환매출액)
    - 광고비 = '총비용' (VAT 제외 기준)
    - 매일 누적 붙여넣기 대비: 날짜+캠페인+광고그룹+소재 키로 중복 제거(keep="last")
    """
    try:
        creds = Credentials.from_service_account_info(
            dict(st.secrets["gcp_service_account"]),
            scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"],
        )
        gc = gspread.authorize(creds)
        ws = gc.open_by_key(st.secrets["spreadsheet_id"]).worksheet("GFA_원본")
        raw = pd.DataFrame(ws.get_all_records())
    except Exception:
        return pd.DataFrame()
    if raw.empty:
        return pd.DataFrame()

    def _num(col):
        if col not in raw.columns:
            return pd.Series([0] * len(raw))
        return pd.to_numeric(
            raw[col].astype(str).str.replace(",", "").str.replace("%", "").str.strip(),
            errors="coerce",
        ).fillna(0)

    g = pd.DataFrame({
        "날짜": pd.to_datetime(
            raw.get("기간", pd.Series([""] * len(raw))).astype(str)
               .str.strip().str.rstrip(".").str.replace(".", "-", regex=False),
            errors="coerce",
        ),
        "매체": "GFA",
        "캠페인명": raw.get("캠페인 이름", ""),
        "광고그룹명": raw.get("광고 그룹 이름", ""),
        "소재명": raw.get("광고 소재 이름", ""),
        "노출": _num("노출수"),
        "클릭": _num("클릭수"),
        "광고비 (KRW)": _num("총비용"),
        "전환수": _num("구매완료 수"),
        "매출 (KRW)": _num("총 전환매출액"),
    })
    g = g.dropna(subset=["날짜"])
    if g.empty:
        return pd.DataFrame()
    # 누적 붙여넣기로 같은 행이 반복될 수 있어 최신 것만 남김
    g = g.drop_duplicates(subset=["날짜", "캠페인명", "광고그룹명", "소재명"], keep="last")
    # 소재명 파싱 (메타와 동일 규칙: [26.08]GF_I_BT칩_...)
    parsed = pd.DataFrame([parse_ad_name_gfa(n) for n in g["소재명"]], index=g.index)
    g = pd.concat([g, parsed], axis=1)
    # 파생 지표
    g["CTR (%)"]   = (g["클릭"] / g["노출"].replace(0, float("nan")) * 100).fillna(0).round(4)
    g["CPC (KRW)"] = (g["광고비 (KRW)"] / g["클릭"].replace(0, float("nan"))).fillna(0).round()
    g["CPA (KRW)"] = (g["광고비 (KRW)"] / g["전환수"].replace(0, float("nan"))).fillna(0).round()
    g["연"] = g["날짜"].dt.year.astype(str)
    g["월"] = g["날짜"].dt.month.astype(str).str.zfill(2)
    g["일"] = g["날짜"].dt.day.astype(str).str.zfill(2)
    return g.sort_values("날짜")


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


@st.cache_data(ttl=300, show_spinner="시간대별 데이터 불러오는 중...")
def load_hourly_data(sheet_name: str) -> pd.DataFrame:
    """시간대별 시트 로드 (5분 캐시)"""
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
    # 기존 헬퍼(perf_row, calc_kpi) 재사용을 위한 컬럼 별칭
    dfh["광고비 (KRW)"] = dfh["광고비"]
    dfh["전환수"] = dfh["구매"]
    return dfh


try:
    df = load_data()
except Exception as e:
    st.error(f"❌ 데이터를 불러오지 못했어요: `{e}`")
    st.info("👉 `.streamlit/secrets.toml` 설정을 확인해주세요.")
    st.stop()

if df.empty:
    st.warning("시트에 데이터가 없어요.")
    st.stop()

# --- GFA(네이버 성과형 DA) 합산: GFA_원본 시트를 직접 읽어 매체 하나로 추가 ---
# 시트에 붙여넣으면 캐시 만료(1시간) 또는 사이드바 🔄 새로고침 시 즉시 반영됨
if "매출 (KRW)" not in df.columns:
    df["매출 (KRW)"] = 0
try:
    _gfa = load_gfa_data()
except Exception:
    _gfa = pd.DataFrame()
if not _gfa.empty:
    df = pd.concat([df, _gfa], ignore_index=True).sort_values("날짜")
df["매출 (KRW)"] = pd.to_numeric(df["매출 (KRW)"], errors="coerce").fillna(0)

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
    st.markdown("**🗓 집행시작일**")
    _startdate_opts = valid_opts(df, "집행시작일") if "집행시작일" in df.columns else []
    sel_startdate = st.multiselect("집행시작일", _startdate_opts,
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
if sel_startdate and "집행시작일" in df.columns:
    mask &= df["집행시작일"].astype(str).isin(sel_startdate)
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
render_update_buttons()
tab1, tab7, tab2, tab9, tab8, tab6 = st.tabs(["📊 전체 요약", "🖤 블트하 요약", "🍿 팝콘 요약", "🟩 GFA 요약", "⏰ 블트하 시간대별", "⏰ 팝콘 시간대별"])
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
        view_mode = st.radio("보기", ["테이블", "그래프"], horizontal=True,
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
        daily_tree_table(fdf)
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
    fdf_pc = fdf[
        fdf["제품코드"].astype(str).str.contains("PC", na=False)
        | fdf["캠페인명"].astype(str).str.contains("팝콘", na=False)
    ].copy()
    if fdf_pc.empty:
        st.warning("팝콘(PC) 데이터가 없어요. 사이드바 필터를 확인해주세요.")
    else:
        # 치즈팝콘(제품코드 PC치) — KR별·배너 포맷별·소구점별 테이블 공용
        fdf_cheese_all = fdf_pc[fdf_pc["제품코드"].astype(str).str.contains("PC치", na=False)].copy()
        render_kpi(calc_kpi(fdf_pc))
        st.markdown("---")
        # 1. 일별 광고비 테이블
        st.markdown("**📊 일별 광고비 & CPA**")
        daily_tree_table(fdf_pc)
        st.markdown("---")
        # 2. 이벤트별 성과
        st.markdown("**🎪 이벤트별 성과**")
        event_tbl = build_summary_table(fdf_pc, "스킴명")
        event_tbl = event_tbl.rename(columns={"스킴명": "이벤트명"})
        _ev_total = event_tbl[event_tbl["이벤트명"] == "총합계"]
        _ev_data  = event_tbl[event_tbl["이벤트명"] != "총합계"].sort_values("광고비", ascending=False)
        event_tbl = pd.concat([_ev_data, _ev_total], ignore_index=True)
        render_pinned_total_table(style_summary(event_tbl, "이벤트명"))
        st.markdown("---")
        # 3. 치즈팝콘 KR별 성과 (제품코드 PC치, 광고세트명 KR1/KR2 → 클릭 시 소재별)
        st.markdown("**🧀 치즈팝콘 KR별 성과**")
        fdf_cheese = fdf_cheese_all.copy()
        if fdf_cheese.empty:
            st.info("치즈팝콘(제품코드 PC치) 데이터가 없습니다.")
        else:
            def _cheese_kr(_adset):
                _m = re.search(r"KR\d+", str(_adset))
                return _m.group(0) if _m else "(기타)"
            # 1차: 광고세트명에서 KR 추출
            fdf_cheese["_KR"] = fdf_cheese["광고그룹명"].apply(_cheese_kr)
            # 2차 보정: 동일 소재를 수동+ASC에 더블세팅하면 ASC 광고세트명엔 KR 표기가 없어
            #   (기타)로 빠짐. 광고세트명으로 KR이 잡힌 소재들에서 (소재명 → KR) 매핑을 만들고,
            #   같은 소재명이 (기타)에 있으면 그 KR로 채운다.
            #   (같은 소재명이 KR1·KR2 양쪽에 걸친 모호한 경우엔 (기타) 유지)
            _known = fdf_cheese[fdf_cheese["_KR"] != "(기타)"]
            _creative_kr = {}
            for _cn, _grp in _known.groupby("소재명"):
                _krs = set(_grp["_KR"].unique())
                if len(_krs) == 1:
                    _creative_kr[_cn] = next(iter(_krs))
            _etc = fdf_cheese["_KR"] == "(기타)"
            if _etc.any() and _creative_kr:
                fdf_cheese.loc[_etc, "_KR"] = fdf_cheese.loc[_etc, "소재명"].map(
                    lambda _n: _creative_kr.get(_n, "(기타)")
                )
            _crk_cols = ["KR 구분", "광고비", "노출", "링크 클릭", "구매", "CTR", "CPC", "CPM", "CVR", "CPA"]
            _crk_groups = []
            for _crk, _crk_sub in fdf_cheese.groupby("_KR"):
                _crk_ads = [
                    (_an,
                     hr_perf_row(_an, _crk_sub[_crk_sub["소재명"] == _an], key_col="KR 구분"),
                     _crk_sub[_crk_sub["소재명"] == _an]["광고비 (KRW)"].sum())
                    for _an in _crk_sub["소재명"].unique()
                ]
                _crk_ads.sort(key=lambda x: x[2], reverse=True)
                _crk_groups.append((
                    str(_crk),
                    hr_perf_row(str(_crk), _crk_sub, key_col="KR 구분"),
                    [(_a, _r) for _a, _r, _ in _crk_ads],
                ))
            def _crk_sort_key(_lbl):
                _mm = re.match(r"KR(\d+)", _lbl)
                return (0, int(_mm.group(1))) if _mm else (1, 0)
            _crk_groups.sort(key=lambda g: _crk_sort_key(g[0]))
            render_tree_table(
                _crk_groups,
                hr_perf_row("총합계", fdf_cheese, key_col="KR 구분"),
                _crk_cols,
            )
        st.markdown("---")
        # 4. 영상 포맷별 성과 (광고유형 V, 대분류 포맷 → 소분류 연출 → 소재명)
        st.markdown("**🎞 영상 포맷별 성과**")
        fdf_pcv = fdf_pc[fdf_pc["영상/이미지 구분"].astype(str).str.strip().str.upper() == "V"].copy()
        fdf_pcv = fdf_pcv[fdf_pcv["대분류 포맷"].astype(str).str.strip() != ""]
        if fdf_pcv.empty:
            st.info("영상(V) 소재 데이터가 없습니다.")
        else:
            _pcv_cols = ["영상 포맷", "광고비", "노출", "링크 클릭", "구매", "CTR", "CPC", "CPM", "CVR", "CPA"]
            _pcv_groups = []
            for _pcv_fmt, _pcv_sub in fdf_pcv.groupby("대분류 포맷"):
                if not str(_pcv_fmt).strip():
                    continue
                _pcv_kids = []
                for _pcv_dt, _pcv_ssub in _pcv_sub.groupby("소분류 연출"):
                    _pcv_label = str(_pcv_dt).strip() or "(미분류)"
                    _pcv_ads = [
                        (_an,
                         hr_perf_row(_an, _pcv_ssub[_pcv_ssub["소재명"] == _an], key_col="영상 포맷"),
                         _pcv_ssub[_pcv_ssub["소재명"] == _an]["광고비 (KRW)"].sum())
                        for _an in _pcv_ssub["소재명"].unique()
                    ]
                    _pcv_ads.sort(key=lambda x: x[2], reverse=True)
                    _pcv_kids.append((
                        _pcv_label,
                        hr_perf_row(_pcv_label, _pcv_ssub, key_col="영상 포맷"),
                        [(_a, _r) for _a, _r, _ in _pcv_ads],
                        _pcv_ssub["광고비 (KRW)"].sum(),
                    ))
                _pcv_kids.sort(key=lambda x: x[3], reverse=True)
                _pcv_groups.append((
                    str(_pcv_fmt),
                    hr_perf_row(str(_pcv_fmt), _pcv_sub, key_col="영상 포맷"),
                    [(_a, _r, _k) for _a, _r, _k, _ in _pcv_kids],
                    _pcv_sub["광고비 (KRW)"].sum(),
                ))
            _pcv_groups.sort(key=lambda x: x[3], reverse=True)
            render_tree_table3(
                [(_g2[0], _g2[1], _g2[2]) for _g2 in _pcv_groups],
                hr_perf_row("총합계", fdf_pcv, key_col="영상 포맷"),
                _pcv_cols,
            )
        st.markdown("---")
        # 5. 치즈팝콘 배너 포맷별 성과 (PC치 I 소재, 소재명 parts[8] 마지막 조각 = 스토리형/댓글형)
        st.markdown("**🖼 치즈팝콘 배너 포맷별 성과**")
        render_banner_table(fdf_cheese_all, "format")
        st.markdown("---")
        # 6. 치즈팝콘 소구점별 성과 (PC치 I 소재, 소재명 parts[8] 마지막-1 조각 = 맛강조/페포/대세감)
        st.markdown("**💬 치즈팝콘 소구점별 성과**")
        render_banner_table(fdf_cheese_all, "appeal")
        st.markdown("---")
        # 7. 신규소재 집행일자별 성과 (집행시작일 260720~, 집행일 클릭 시 소재명 펼침)
        st.markdown(f"**🗓 신규소재 집행일자별 성과 (집행시작일 {NEW_CREATIVE_START}~)**")
        render_new_creative_table(fdf_pc)

# --- TAB 4: 단쉐 요약 (2026-07-24 숨김: st.tabs에서 제외, 데이터·코드 보존. 복원 시 이 줄을 'with tab4:'로 되돌리고 st.tabs에 재추가) ---
if False:  # 단쉐 요약 탭 숨김
    fdf_sk = fdf[fdf["캠페인명"].astype(str).str.contains("단백질|단쉐", na=False)].copy()
    if fdf_sk.empty:
        st.warning("단쉐(캠페인명에 단백질/단쉐 포함) 데이터가 없어요. 사이드바 필터를 확인해주세요.")
    else:
        render_kpi(calc_kpi(fdf_sk))
        st.markdown("---")

        # 1. 일별 광고비 & CPA
        st.markdown("**📊 일별 광고비 & CPA**")
        daily_tree_table(fdf_sk)
        st.markdown("---")

        # 2. 스킴별 성과 (사이드바 필터와 무관하게 전체 기간 기준)
        st.markdown("**📋 스킴별 성과**")
        st.caption("사이드바 필터와 무관하게 전체 기간 데이터 기준입니다.")
        df_sk_all = df[df["캠페인명"].astype(str).str.contains("단백질|단쉐", na=False)].copy()
        sk_s1 = df_sk_all[(df_sk_all["날짜"] >= SK_SCHEME1_START) & (df_sk_all["날짜"] <= SK_SCHEME1_END)]
        sk_s2 = df_sk_all[(df_sk_all["날짜"] >= SK_SCHEME2_START) & (df_sk_all["날짜"] <= SK_SCHEME2_END)]
        sk_s3 = df_sk_all[(df_sk_all["날짜"] >= SK_SCHEME3_START) & (df_sk_all["날짜"] <= SK_SCHEME3_END)]
        sk_s4 = df_sk_all[df_sk_all["날짜"] >= SK_SCHEME4_START]
        sk_total = pd.concat([sk_s1, sk_s2, sk_s3, sk_s4])
        sk1_label = f"1차 스킴({SK_SCHEME1_START.strftime('%m/%d')}~{SK_SCHEME1_END.strftime('%m/%d')})"
        sk2_label = f"2차 스킴({SK_SCHEME2_START.strftime('%m/%d')}~{SK_SCHEME2_END.strftime('%m/%d')})"
        sk3_label = f"3차 스킴({SK_SCHEME3_START.strftime('%m/%d')}~{SK_SCHEME3_END.strftime('%m/%d')})"
        sk4_label = f"4차 스킴({SK_SCHEME4_START.strftime('%m/%d')}~)"
        sk_period_df = pd.DataFrame([
            perf_row(sk1_label, sk_s1),
            perf_row(sk2_label, sk_s2),
            perf_row(sk3_label, sk_s3),
            perf_row(sk4_label, sk_s4),
            perf_row("총합계", sk_total),
        ])
        render_pinned_total_table(sk_period_df)
        st.markdown("---")

        # 3. 제품코드별 성과
        st.markdown("**📦 제품코드별 성과**")
        prodcode_tbl = build_summary_table(fdf_sk, "제품코드")
        _pc_total = prodcode_tbl[prodcode_tbl["제품코드"] == "총합계"]
        _pc_data  = prodcode_tbl[prodcode_tbl["제품코드"] != "총합계"].sort_values("광고비", ascending=False)
        prodcode_tbl = pd.concat([_pc_data, _pc_total], ignore_index=True)
        render_pinned_total_table(style_summary(prodcode_tbl, "제품코드"))
        st.markdown("---")

        # 3. 프로모션별 성과 (이벤트명 기준)
        st.markdown("**🎪 프로모션별 성과**")
        promo_tbl = build_summary_table(fdf_sk, "스킴명")
        promo_tbl = promo_tbl.rename(columns={"스킴명": "이벤트명"})
        _pr_total = promo_tbl[promo_tbl["이벤트명"] == "총합계"]
        _pr_data  = promo_tbl[promo_tbl["이벤트명"] != "총합계"].sort_values("광고비", ascending=False)
        promo_tbl = pd.concat([_pr_data, _pr_total], ignore_index=True)
        render_pinned_total_table(style_summary(promo_tbl, "이벤트명"))

        st.markdown("---")

        # 4. 영상 포맷별 성과 (광고유형 V, 대분류 포맷 → 소분류 연출 → 소재명)
        st.markdown("**🎞 영상 포맷별 성과**")
        fdf_vf = fdf_sk[fdf_sk["영상/이미지 구분"].astype(str).str.strip().str.upper() == "V"].copy()
        fdf_vf = fdf_vf[fdf_vf["대분류 포맷"].astype(str).str.strip() != ""]
        if fdf_vf.empty:
            st.info("영상(V) 소재 데이터가 없습니다.")
        else:
            _vf_cols = ["영상 포맷", "광고비", "노출", "링크 클릭", "구매", "CTR", "CPC", "CVR", "CPA"]
            _vf_groups = []
            for _vf_fmt, _vf_sub in fdf_vf.groupby("대분류 포맷"):
                if not str(_vf_fmt).strip():
                    continue
                _vf_kids = []
                for _vf_dt, _vf_ssub in _vf_sub.groupby("소분류 연출"):
                    _vf_label = str(_vf_dt).strip() or "(미분류)"
                    _vf_ads = [
                        (_an,
                         perf_row(_an, _vf_ssub[_vf_ssub["소재명"] == _an], key_col="영상 포맷"),
                         _vf_ssub[_vf_ssub["소재명"] == _an]["광고비 (KRW)"].sum())
                        for _an in _vf_ssub["소재명"].unique()
                    ]
                    _vf_ads.sort(key=lambda x: x[2], reverse=True)
                    _vf_kids.append((
                        _vf_label,
                        perf_row(_vf_label, _vf_ssub, key_col="영상 포맷"),
                        [(_a, _r) for _a, _r, _ in _vf_ads],
                        _vf_ssub["광고비 (KRW)"].sum(),
                    ))
                _vf_kids.sort(key=lambda x: x[3], reverse=True)
                _vf_groups.append((
                    str(_vf_fmt),
                    perf_row(str(_vf_fmt), _vf_sub, key_col="영상 포맷"),
                    [(_a, _r, _k) for _a, _r, _k, _ in _vf_kids],
                    _vf_sub["광고비 (KRW)"].sum(),
                ))
            _vf_groups.sort(key=lambda x: x[3], reverse=True)
            render_tree_table3(
                [(_g[0], _g[1], _g[2]) for _g in _vf_groups],
                perf_row("총합계", fdf_vf, key_col="영상 포맷"),
                _vf_cols,
            )

        st.markdown("---")

        # 5. 신규 소재 성과 (집행시작일 260706 이후, 시작일 → 소재명 펼침)
        st.markdown("**🗓 신규 소재 성과 (집행시작일 260706~)**")
        NEW_START_DATE = "260706"
        fdf_ns = fdf_sk.copy()
        if "집행시작일" in fdf_ns.columns:
            fdf_ns = fdf_ns[
                fdf_ns["집행시작일"].astype(str).str.match(r"^\d{6}$") &
                (fdf_ns["집행시작일"].astype(str) >= NEW_START_DATE)
            ]
        else:
            fdf_ns = fdf_ns.iloc[0:0]
        if fdf_ns.empty:
            st.info(f"집행시작일 {NEW_START_DATE} 이후 소재 데이터가 없습니다.")
        else:
            _ns_cols = ["집행시작일", "광고비", "노출", "링크 클릭", "구매", "CTR", "CPC", "CVR", "CPA"]
            _ns_groups = []
            for _sd in sorted(fdf_ns["집행시작일"].astype(str).unique()):
                _sd_sub = fdf_ns[fdf_ns["집행시작일"].astype(str) == _sd]
                _ns_ads = [
                    (_an,
                     perf_row(_an, _sd_sub[_sd_sub["소재명"] == _an], key_col="집행시작일"),
                     _sd_sub[_sd_sub["소재명"] == _an]["광고비 (KRW)"].sum())
                    for _an in _sd_sub["소재명"].unique()
                ]
                _ns_ads.sort(key=lambda x: x[2], reverse=True)
                _ns_groups.append((
                    _sd,
                    perf_row(_sd, _sd_sub, key_col="집행시작일"),
                    [(_a, _r) for _a, _r, _ in _ns_ads],
                ))
            render_tree_table(_ns_groups,
                              perf_row("총합계", fdf_ns, key_col="집행시작일"),
                              _ns_cols)

# =============================================================
# 시간대별 탭 공통 렌더링
# =============================================================
def render_hourly_tab(sheet_name: str, kp: str) -> None:
    dfh = load_hourly_data(sheet_name)
    if dfh.empty:
        st.info(f"시간대별 데이터가 아직 없습니다. 1시간마다 자동 수집되며, "
                f"첫 수집 후 시트({sheet_name})가 생성되면 표시됩니다.")
        return
    _h_dates = sorted(dfh["날짜"].dt.strftime("%Y-%m-%d").unique().tolist(), reverse=True)
    c_hd, _c_sp = st.columns([2, 3], vertical_alignment="center")
    with c_hd:
        sel_h_dates = st.multiselect(
            "날짜 선택 (복수 선택 시 시간대별 합산 — 요일 패턴 비교용)",
            _h_dates, default=[_h_dates[0]], key=f"{kp}_dates")
    _dh = dfh if not sel_h_dates else dfh[dfh["날짜"].dt.strftime("%Y-%m-%d").isin(sel_h_dates)]
    if _dh.empty:
        st.warning("선택한 날짜에 데이터가 없습니다.")
        return
    render_kpi(calc_kpi(_dh))
    st.markdown("---")

    # 1. 시간대 → 캠페인 → 광고세트 트리
    st.markdown("**⏰ 시간대별 성과** (시간대 클릭 → 캠페인 → 광고세트)")
    if "수집시각" in dfh.columns:
        _h_last = dfh["수집시각"].astype(str).max()
        st.caption(f"🕐 마지막 수집: {_h_last} · 1시간마다 자동 갱신 · "
                   f"Meta 리포팅 특성상 최근 1시간 안팎 지연 가능")
    _hr_cols = ["시간대", "광고비", "노출", "링크 클릭", "구매", "CTR", "CPC", "CPM", "CVR", "CPA"]
    _hr_groups = []
    for _hr in sorted(_dh["시간"].unique()):
        _hr_sub = _dh[_dh["시간"] == _hr]
        _hr_camps = []
        for _cp, _cp_sub in _hr_sub.groupby("캠페인명"):
            _cp_sets = []
            for _as, _as_sub in _cp_sub.groupby("광고그룹명"):
                _cp_sets.append((str(_as),
                                 hr_perf_row(str(_as), _as_sub, key_col="시간대"),
                                 _as_sub["광고비 (KRW)"].sum()))
            _cp_sets.sort(key=lambda x: x[2], reverse=True)
            _hr_camps.append((str(_cp),
                              hr_perf_row(str(_cp), _cp_sub, key_col="시간대"),
                              [(_a, _r) for _a, _r, _ in _cp_sets],
                              _cp_sub["광고비 (KRW)"].sum()))
        _hr_camps.sort(key=lambda x: x[3], reverse=True)
        _hr_groups.append((f"{int(_hr):02d}시",
                           hr_perf_row(f"{int(_hr):02d}시", _hr_sub, key_col="시간대"),
                           [(_a, _r, _k) for _a, _r, _k, _ in _hr_camps]))
    render_tree_table3(_hr_groups, hr_perf_row("총합계", _dh, key_col="시간대"),
                       _hr_cols, compact=True)
    st.markdown("---")

    # 2. 캠페인/세트/소재별 시간대 추이 (3단 연쇄 멀티셀렉트)
    st.markdown("**📈 캠페인·세트·소재별 시간대 추이**")
    st.caption("각 단계 복수 선택 가능, 비우면 전체 · 박스 클릭 후 타이핑하면 검색 · "
               "상위 선택을 바꾸면 범위 밖 하위 선택은 자동 해제")

    def _spend_order(d, col):
        return (d.groupby(col)["광고비 (KRW)"].sum()
                .sort_values(ascending=False).index.astype(str).tolist())

    c_cp, c_as, c_ad = st.columns(3)
    _k_cp, _k_as, _k_ad = f"{kp}_hr_camps", f"{kp}_hr_sets", f"{kp}_hr_ads"
    _cp_opts = _spend_order(_dh, "캠페인명")
    if _k_cp in st.session_state:
        st.session_state[_k_cp] = [v for v in st.session_state[_k_cp] if v in _cp_opts]
    with c_cp:
        _sel_cp = st.multiselect("캠페인", _cp_opts, placeholder="전체", key=_k_cp)
    _d1 = _dh if not _sel_cp else _dh[_dh["캠페인명"].astype(str).isin(_sel_cp)]

    _as_opts = _spend_order(_d1, "광고그룹명")
    if _k_as in st.session_state:
        st.session_state[_k_as] = [v for v in st.session_state[_k_as] if v in _as_opts]
    with c_as:
        _sel_as = st.multiselect("광고세트", _as_opts, placeholder="전체", key=_k_as)
    _d2 = _d1 if not _sel_as else _d1[_d1["광고그룹명"].astype(str).isin(_sel_as)]

    _ad_opts = _spend_order(_d2, "소재명")
    if _k_ad in st.session_state:
        st.session_state[_k_ad] = [v for v in st.session_state[_k_ad] if v in _ad_opts]
    with c_ad:
        _sel_ad = st.multiselect("소재", _ad_opts, placeholder="전체", key=_k_ad)
    _de = _d2 if not _sel_ad else _d2[_d2["소재명"].astype(str).isin(_sel_ad)]

    if _de.empty:
        st.info("선택 조건에 데이터가 없습니다.")
    else:
        _tr_cols = ["시간", "광고비", "노출", "링크 클릭", "구매", "CTR", "CPC", "CPM", "CVR", "CPA"]
        _tr_rows = [hr_perf_row(f"{int(_hr):02d}시", _de[_de["시간"] == _hr], key_col="시간")
                    for _hr in sorted(_de["시간"].unique())]
        _tr_rows.append(hr_perf_row("총합계", _de, key_col="시간"))
        render_pinned_total_table(pd.DataFrame(_tr_rows)[_tr_cols], compact=True)

# --- TAB 5: 단쉐 시간대별 (2026-07-24 숨김: st.tabs에서 제외, 데이터·코드 보존. 복원 시 이 줄을 'with tab5:'로 되돌리고 st.tabs에 재추가) ---
if False:  # 단쉐 시간대별 탭 숨김
    render_hourly_tab("단쉐_시간대별_원본", "sk")

# --- TAB 6: 팝콘 시간대별 ---
with tab6:
    render_hourly_tab("팝콘_시간대별_원본", "pc")

# --- TAB 7: 블트하 요약 ---
with tab7:
    fdf_bt = fdf[
        fdf["제품코드"].astype(str).str.contains("BT", na=False)
        | fdf["캠페인명"].astype(str).str.contains("블트하", na=False)
    ].copy()
    if fdf_bt.empty:
        st.warning("블트하(제품코드 BT) 데이터가 없어요. 사이드바 필터를 확인해주세요.")
    else:
        render_kpi(calc_kpi(fdf_bt))
        st.markdown("---")

        # 0. 가중목 현황 (블트하 노출 목표 트래킹)
        st.markdown(f"**🎯 가중목 현황** ({BT_GOAL_START.strftime('%m/%d')}~{BT_GOAL_END.strftime('%m/%d')} · 노출 목표 {BT_GOAL_IMP:,})")
        st.caption("사이드바 필터와 무관하게 전체 데이터 기준 · 당일 수치는 실시간 업데이트 후 반영됩니다.")
        _g = df[
            df["제품코드"].astype(str).str.contains("BT", na=False)
            | df["캠페인명"].astype(str).str.contains("블트하", na=False)
        ]
        _g = _g[(_g["날짜"] >= BT_GOAL_START) & (_g["날짜"] <= BT_GOAL_END)]
        _g_imp  = int(_g["노출"].sum())
        _g_rate = _g_imp / BT_GOAL_IMP * 100
        _g_days_total  = (BT_GOAL_END - BT_GOAL_START).days + 1
        _g_daily_goal  = round(BT_GOAL_IMP / _g_days_total)
        _g_today = pd.Timestamp(pd.Timestamp.now(tz="Asia/Seoul").strftime("%Y-%m-%d"))
        _g_days_passed = min(max((_g_today - BT_GOAL_START).days + 1, 0), _g_days_total)
        _g_pace = _g_days_passed / _g_days_total * 100
        gc1, gc2, gc3, gc4, gc5 = st.columns(5)
        gc1.metric("🎯 목표 노출", f"{BT_GOAL_IMP:,}")
        gc2.metric("📆 목표 일별 노출", f"{_g_daily_goal:,}")
        gc3.metric("👁 누적 노출", f"{_g_imp:,}")
        gc4.metric("📈 달성률", f"{_g_rate:.1f}%", f"{_g_rate - _g_pace:+.1f}%p (일자 진척률 대비)")
        gc5.metric("📅 일자 진척률", f"{_g_pace:.1f}%", f"{_g_days_passed}일차 / {_g_days_total}일", delta_color="off")
        if 0 < _g_days_passed < _g_days_total:
            _g_proj = int(_g_imp / _g_days_passed * _g_days_total)
            _g_need = int((BT_GOAL_IMP - _g_imp) / (_g_days_total - _g_days_passed)) if BT_GOAL_IMP > _g_imp else 0
            st.caption(f"이 추세면 기간 말 약 {_g_proj:,} 노출 예상 · 목표 달성까지 남은 기간 일평균 {_g_need:,} 노출 필요")
        elif _g_days_passed >= _g_days_total:
            st.caption(f"기간 종료 — 최종 노출 {_g_imp:,} (달성률 {_g_rate:.1f}%)")
        st.markdown("---")

        # 1. 일별 광고비 & CPA
        st.markdown("**📊 일별 광고비 & CPA**")
        daily_tree_table(fdf_bt, with_cpm=True)
        st.markdown("---")

        # 2. 매체별 성과 (Meta/TikTok)
        st.markdown("**📺 매체별 성과**")
        cpm_summary_table(fdf_bt, "매체", "매체")
        st.markdown("---")

        # 3. 제품코드별 성과
        st.markdown("**📦 제품코드별 성과**")
        cpm_summary_table(fdf_bt, "제품코드", "제품코드")
        st.markdown("---")

        # 4. KR별 성과 (I: 소분류 연출 그대로 / V: 소분류 연출의 온점 이후 텍스트)
        st.markdown("**🔤 KR별 성과** (클릭하면 소재별 상세)")
        fdf_kr = fdf_bt.copy()

        def _kr_label(_row):
            _dt = str(_row["소분류 연출"]).strip()
            if not _dt or _dt == "nan":
                return ""
            _vi = str(_row["영상/이미지 구분"]).strip().upper()
            if _vi == "V" and "." in _dt:
                return _dt.rsplit(".", 1)[-1].strip()
            return _dt

        fdf_kr["_KR"] = fdf_kr.apply(_kr_label, axis=1)
        fdf_kr = fdf_kr[fdf_kr["_KR"] != ""]
        if fdf_kr.empty:
            st.info("KR 구분이 있는 소재 데이터가 없습니다.")
        else:
            _kr_cols = ["KR 구분", "광고비", "노출", "링크 클릭", "구매", "CTR", "CPC", "CPM", "CVR", "CPA"]
            _kr_groups = []
            for _kr, _kr_sub in fdf_kr.groupby("_KR"):
                _kr_ads = [
                    (_an,
                     hr_perf_row(_an, _kr_sub[_kr_sub["소재명"] == _an], key_col="KR 구분"),
                     _kr_sub[_kr_sub["소재명"] == _an]["광고비 (KRW)"].sum())
                    for _an in _kr_sub["소재명"].unique()
                ]
                _kr_ads.sort(key=lambda x: x[2], reverse=True)
                _kr_groups.append((
                    str(_kr),
                    hr_perf_row(str(_kr), _kr_sub, key_col="KR 구분"),
                    [(_a, _r) for _a, _r, _ in _kr_ads],
                    _kr_sub["광고비 (KRW)"].sum(),
                ))
            _kr_groups.sort(key=lambda x: x[3], reverse=True)
            render_tree_table(
                [(_g2[0], _g2[1], _g2[2]) for _g2 in _kr_groups],
                hr_perf_row("총합계", fdf_kr, key_col="KR 구분"),
                _kr_cols,
            )
        st.markdown("---")

        # 5. 영상 포맷별 성과 (광고유형 V, 대분류 포맷 → 소분류 연출 → 소재명)
        st.markdown("**🎞 영상 포맷별 성과**")
        fdf_btv = fdf_bt[fdf_bt["영상/이미지 구분"].astype(str).str.strip().str.upper() == "V"].copy()
        fdf_btv = fdf_btv[fdf_btv["대분류 포맷"].astype(str).str.strip() != ""]
        if fdf_btv.empty:
            st.info("영상(V) 소재 데이터가 없습니다.")
        else:
            _btv_cols = ["영상 포맷", "광고비", "노출", "링크 클릭", "구매", "CTR", "CPC", "CPM", "CVR", "CPA"]
            _btv_groups = []
            for _btv_fmt, _btv_sub in fdf_btv.groupby("대분류 포맷"):
                if not str(_btv_fmt).strip():
                    continue
                _btv_kids = []
                for _btv_dt, _btv_ssub in _btv_sub.groupby("소분류 연출"):
                    _btv_label = str(_btv_dt).strip() or "(미분류)"
                    _btv_ads = [
                        (_an,
                         hr_perf_row(_an, _btv_ssub[_btv_ssub["소재명"] == _an], key_col="영상 포맷"),
                         _btv_ssub[_btv_ssub["소재명"] == _an]["광고비 (KRW)"].sum())
                        for _an in _btv_ssub["소재명"].unique()
                    ]
                    _btv_ads.sort(key=lambda x: x[2], reverse=True)
                    _btv_kids.append((
                        _btv_label,
                        hr_perf_row(_btv_label, _btv_ssub, key_col="영상 포맷"),
                        [(_a, _r) for _a, _r, _ in _btv_ads],
                        _btv_ssub["광고비 (KRW)"].sum(),
                    ))
                _btv_kids.sort(key=lambda x: x[3], reverse=True)
                _btv_groups.append((
                    str(_btv_fmt),
                    hr_perf_row(str(_btv_fmt), _btv_sub, key_col="영상 포맷"),
                    [(_a, _r, _k) for _a, _r, _k, _ in _btv_kids],
                    _btv_sub["광고비 (KRW)"].sum(),
                ))
            _btv_groups.sort(key=lambda x: x[3], reverse=True)
            render_tree_table3(
                [(_g2[0], _g2[1], _g2[2]) for _g2 in _btv_groups],
                hr_perf_row("총합계", fdf_btv, key_col="영상 포맷"),
                _btv_cols,
            )
        st.markdown("---")
        # 6. 신규소재 집행일자별 성과 (집행시작일 260720~, 집행일 클릭 시 소재명 펼침)
        st.markdown(f"**🗓 신규소재 집행일자별 성과 (집행시작일 {NEW_CREATIVE_START}~)**")
        render_new_creative_table(fdf_bt)
        st.markdown("---")
        # 7. 소재별 성과 (항상 블트하 탭 최하단 고정 · 사이드바 필터 반영 · 헤더 클릭 정렬)
        st.markdown("**🎬 소재별 성과**")
        cpm_summary_table(fdf_bt, "소재명", "소재")

# --- TAB 9: GFA 요약 (네이버 성과형 DA) ---
with tab9:
    fdf_gfa = fdf[fdf["매체"].astype(str) == "GFA"].copy()
    if fdf_gfa.empty:
        st.warning("GFA 데이터가 없어요. 구글시트 `GFA_원본` 탭에 리포트를 붙여넣고 "
                   "사이드바의 🔄 데이터 새로고침을 눌러주세요. (사이드바 필터도 확인)")
    else:
        render_kpi(calc_kpi(fdf_gfa))
        st.caption("전환수는 **구매완료 수** 기준(메타/틱톡의 구매 기준과 통일) · 광고비는 총비용(VAT 제외)")
        st.markdown("---")
        # 1. 일별 광고비 & CPA (블트하 탭과 동일 형식, CPM 포함)
        st.markdown("**📊 일별 광고비 & CPA**")
        daily_tree_table(fdf_gfa, with_cpm=True)
        st.markdown("---")

        # 지면 = 캠페인명 마지막 '_' 뒤 (피드/서비스/스채/메인/네트워크)
        # 타겟 = 광고그룹명(세트명) 마지막 '_' 뒤 (all4054/all3039)
        fdf_gfa["_지면"] = (fdf_gfa["캠페인명"].astype(str).str.rsplit("_", n=1).str[-1]
                          .str.strip().replace("", "(미분류)"))
        fdf_gfa["_타겟"] = (fdf_gfa["광고그룹명"].astype(str).str.rsplit("_", n=1).str[-1]
                          .str.strip().replace("", "(미분류)"))
        _gfa_cols_pl = ["지면", "광고비", "노출", "링크 클릭", "구매", "CTR", "CPC", "CPM", "CVR", "CPA"]
        _gfa_cols_tg = ["타겟", "광고비", "노출", "링크 클릭", "구매", "CTR", "CPC", "CPM", "CVR", "CPA"]

        # 2. 지면별 성과 (지면 → 타겟 → 소재명 3단 트리)
        st.markdown("**🗂 지면별 성과** (지면 클릭 → 타겟 → 소재)")
        _pl_groups = []
        for _pl, _pl_sub in fdf_gfa.groupby("_지면"):
            _pl_kids = []
            for _tg, _tg_sub in _pl_sub.groupby("_타겟"):
                _tg_ads = [
                    (_an,
                     hr_perf_row(_an, _tg_sub[_tg_sub["소재명"] == _an], key_col="지면"),
                     _tg_sub[_tg_sub["소재명"] == _an]["광고비 (KRW)"].sum())
                    for _an in _tg_sub["소재명"].unique()
                ]
                _tg_ads.sort(key=lambda x: x[2], reverse=True)
                _pl_kids.append((
                    str(_tg),
                    hr_perf_row(str(_tg), _tg_sub, key_col="지면"),
                    [(_a, _r) for _a, _r, _ in _tg_ads],
                    _tg_sub["광고비 (KRW)"].sum(),
                ))
            _pl_kids.sort(key=lambda x: x[3], reverse=True)
            _pl_groups.append((
                str(_pl),
                hr_perf_row(str(_pl), _pl_sub, key_col="지면"),
                [(_a, _r, _k) for _a, _r, _k, _ in _pl_kids],
                _pl_sub["광고비 (KRW)"].sum(),
            ))
        _pl_groups.sort(key=lambda x: x[3], reverse=True)
        render_tree_table3(
            [(_g2[0], _g2[1], _g2[2]) for _g2 in _pl_groups],
            hr_perf_row("총합계", fdf_gfa, key_col="지면"),
            _gfa_cols_pl,
        )
        st.markdown("---")

        # 3. 타겟별 성과 (타겟 → 소재명 2단 트리)
        st.markdown("**🎯 타겟별 성과** (타겟 클릭 → 소재)")
        _tg_groups = []
        for _tg, _tg_sub in fdf_gfa.groupby("_타겟"):
            _tg_ads = [
                (_an,
                 hr_perf_row(_an, _tg_sub[_tg_sub["소재명"] == _an], key_col="타겟"),
                 _tg_sub[_tg_sub["소재명"] == _an]["광고비 (KRW)"].sum())
                for _an in _tg_sub["소재명"].unique()
            ]
            _tg_ads.sort(key=lambda x: x[2], reverse=True)
            _tg_groups.append((
                str(_tg),
                hr_perf_row(str(_tg), _tg_sub, key_col="타겟"),
                [(_a, _r) for _a, _r, _ in _tg_ads],
                _tg_sub["광고비 (KRW)"].sum(),
            ))
        _tg_groups.sort(key=lambda x: x[3], reverse=True)
        render_tree_table(
            [(_g2[0], _g2[1], _g2[2]) for _g2 in _tg_groups],
            hr_perf_row("총합계", fdf_gfa, key_col="타겟"),
            _gfa_cols_tg,
        )

# --- TAB 8: 블트하 시간대별 ---
with tab8:
    render_hourly_tab("블트하_시간대별_원본", "bt")
