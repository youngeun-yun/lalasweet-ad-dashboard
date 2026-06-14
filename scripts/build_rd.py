# -*- coding: utf-8 -*-
"""
메타 + 틱톡 raw CSV → 통합 RD 마스터 CSV
- data/meta_raw_*.csv + data/tiktok_raw_*.csv 읽기
- 소재명 파싱: 파일명 생성기 열 기준 (17컬럼)
- data/통합RD_마스터.csv 에 중복 없이 append (날짜+매체+소재명 키)
"""
import os, glob, re
import pandas as pd

DATA_DIR    = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
MASTER_PATH = os.path.join(DATA_DIR, "통합RD_마스터.csv")

# 통합 RD 최종 컬럼 순서
RD_COLUMNS = [
    # 기본 정보
    "날짜", "매체", "캠페인명", "광고그룹명", "소재명",
    # 파일명 생성기 파싱 (17컬럼)
    "제작월", "채널구분", "영상/이미지 구분", "제품코드", "광고종류",
    "스킴명", "대분류 포맷", "소분류 연출",
    "배리에이션 여부", "지면 유형", "상세연출(소재구분)", "프로젝트",
    "파트 구분", "마케터", "집행시작일", "본부 구분", "PD/디자이너",
    # 성과 지표 (메타+틱톡 공통)
    "노출", "클릭", "CTR (%)", "광고비 (KRW)", "CPC (KRW)", "전환수", "CPA (KRW)",
]

PARSE_COLS = [
    "제작월", "채널구분", "영상/이미지 구분", "제품코드", "광고종류",
    "스킴명", "대분류 포맷", "소분류 연출",
    "배리에이션 여부", "지면 유형", "상세연출(소재구분)", "프로젝트",
    "파트 구분", "마케터", "집행시작일", "본부 구분", "PD/디자이너",
]


def parse_ad_name(ad_name: str) -> dict:
    """
    파일명 생성기 수식 기준 파싱
    예시: [26.06]F_V_PC혼_전환_콘스프맛팝콘출시_신규BP_마미케어BP_var4.릴스_증량후킹.X_2P_박현지_260612_제과_이봄1

    수식: C&D & "_" & E & "_" & F & "_" & G & "_" & H & "_" & I & "_" & J
          & "_" & K & "." & L & "_" & M & "." & N
          & "_" & O & "_" & P & "_" & Q & "_" & R & "_" & S
    """
    result = {col: "" for col in PARSE_COLS}

    if not isinstance(ad_name, str) or not ad_name.startswith("["):
        return result

    parts = ad_name.split("_")
    if len(parts) < 3:
        return result

    try:
        # parts[0] = "[26.06]F"  →  제작월=[26.06], 채널구분=F
        m = re.match(r"(\[.+?\])(.*)", parts[0])
        if m:
            result["제작월"]   = m.group(1)   # [26.06]
            result["채널구분"] = m.group(2)   # F

        if len(parts) > 1:  result["영상/이미지 구분"] = parts[1]   # V
        if len(parts) > 2:  result["제품코드"]         = parts[2]   # PC혼
        if len(parts) > 3:  result["광고종류"]         = parts[3]   # 전환
        if len(parts) > 4:  result["스킴명"]           = parts[4]   # 콘스프맛팝콘출시
        if len(parts) > 5:  result["대분류 포맷"]      = parts[5]   # 신규BP
        if len(parts) > 6:  result["소분류 연출"]      = parts[6]   # 마미케어BP

        if len(parts) > 7:
            # "var4.릴스" → K=var4, L=릴스
            kl = parts[7].split(".", 1)
            result["배리에이션 여부"] = kl[0]
            result["지면 유형"]      = kl[1] if len(kl) > 1 else ""

        if len(parts) > 8:
            # "증량후킹.X" → M=증량후킹, N=X
            mn = parts[8].split(".", 1)
            result["상세연출(소재구분)"] = mn[0]
            result["프로젝트"]          = mn[1] if len(mn) > 1 else ""

        if len(parts) > 9:  result["파트 구분"]  = parts[9]
        if len(parts) > 10: result["마케터"]     = parts[10]
        if len(parts) > 11: result["집행시작일"] = parts[11]
        if len(parts) > 12: result["본부 구분"]  = parts[12]
        if len(parts) > 13: result["PD/디자이너"] = "_".join(parts[13:])

    except Exception:
        pass

    return result


def load_raw(pattern: str, media: str) -> pd.DataFrame:
    files = sorted(glob.glob(os.path.join(DATA_DIR, pattern)))
    if not files:
        return pd.DataFrame()
    frames = []
    for f in files:
        df = pd.read_csv(f, encoding="utf-8-sig")
        if df.empty:
            continue
        df["_media"] = media
        frames.append(df)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def to_rd_rows(raw: pd.DataFrame, media: str) -> pd.DataFrame:
    records = []
    for _, row in raw.iterrows():
        ad_name  = str(row.get("ad_name", ""))
        parsed   = parse_ad_name(ad_name)

        spend    = float(row.get("spend", 0) or 0)
        clicks   = int(float(row.get("clicks", 0) or 0))
        imps     = int(float(row.get("impressions", 0) or 0))
        convs    = int(float(row.get("conversions", 0) or 0))

        ctr = round(clicks / imps * 100, 4) if imps > 0 else 0   # % 로 저장
        cpc = round(spend / clicks)          if clicks > 0 else 0
        cpa = round(spend / convs)           if convs > 0 else 0

        rec = {
            "날짜":       str(row.get("date", "")),
            "매체":       media,
            "캠페인명":   row.get("campaign_name", ""),
            "광고그룹명": row.get("adset_name", ""),
            "소재명":     ad_name,
        }
        rec.update(parsed)
        rec.update({
            "노출":          imps,
            "클릭":          clicks,
            "CTR (%)":       ctr,
            "광고비 (KRW)":  spend,
            "CPC (KRW)":     cpc,
            "전환수":        convs,
            "CPA (KRW)":     cpa,
        })
        records.append(rec)
    return pd.DataFrame(records, columns=RD_COLUMNS) if records else pd.DataFrame(columns=RD_COLUMNS)


# ── 실행 ──────────────────────────────────────────────────────
meta_raw   = load_raw("meta_raw_*.csv",   "Meta")
tiktok_raw = load_raw("tiktok_raw_*.csv", "TikTok")

new_df = pd.concat(
    [to_rd_rows(meta_raw, "Meta"), to_rd_rows(tiktok_raw, "TikTok")],
    ignore_index=True,
)

if new_df.empty:
    print("빌드할 새 데이터 없음 -> 종료")
    exit(0)

# 기존 마스터 로드
if os.path.exists(MASTER_PATH):
    master = pd.read_csv(MASTER_PATH, encoding="utf-8-sig", dtype=str)
else:
    master = pd.DataFrame(columns=RD_COLUMNS)

# 중복 제거: 날짜 + 매체 + 소재명 기준
existing_keys = set(zip(
    master["날짜"].astype(str),
    master["매체"].astype(str),
    master["소재명"].astype(str),
)) if not master.empty else set()

new_df = new_df[~new_df.apply(
    lambda r: (str(r["날짜"]), str(r["매체"]), str(r["소재명"])) in existing_keys,
    axis=1,
)]

result = pd.concat([master, new_df], ignore_index=True)
result.to_csv(MASTER_PATH, index=False, encoding="utf-8-sig")
print(f"통합 RD 완료: +{len(new_df)}행 추가 -> 총 {len(result)}행 ({MASTER_PATH})")
