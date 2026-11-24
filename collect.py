"""
한국은행 ECOS API에서 일별 시장금리를 받아 data/rates.csv로 저장합니다.

- 국고채 3년, 국고채 10년, 회사채(무보증 3년) AA-
- 스프레드(bp): 장단기(10Y-3Y), 회사채 크레딧(AA- - 국고 3Y)
- KOFIA 시가평가기준수익률(민평): 여전채 AA- 3년, 여전채 스프레드(같은 민평 국고 3년 대비)

사용법
  python collect.py          # 데이터 수집
  python collect.py --list   # 통계표 817Y002의 항목코드 목록 출력(코드 확인용)

환경변수 ECOS_API_KEY 에 인증키가 있어야 합니다.
"""
import os
import sys
import datetime as dt
import time

import pandas as pd
import requests

API_KEY = os.environ.get("ECOS_API_KEY", "").strip()
BASE = "https://ecos.bok.or.kr/api"
STAT_CODE = "817Y002"          # 시장금리(일별)
START_DATE = "20200101"        # 이 날짜부터 매번 전체를 다시 받아옴(과거 유사 국면 분석용으로 2020년부터)
KOFIA_START = "2024-01-01"     # KOFIA 민평은 이 날짜부터만 수집(서버 부담·실행 시간)

# 컬럼명: (ECOS 항목코드, 표시 이름)
ITEMS = {
    "ktb3":    ("010200000", "국고채 3년"),
    "ktb10":   ("010210000", "국고채 10년"),
    "corp_aa": ("010300000", "회사채 AA- 3년"),
    "ktb30":   ("010230000", "국고채 30년"),
    "cd91":    ("010502000", "CD 91일"),
    "cp91":    ("010503000", "CP 91일"),
    # 커브 확장 (없어도 진행)
    "ktb1":    ("010190000", "국고채 1년"),
    "ktb2":    ("010195000", "국고채 2년"),
    "ktb5":    ("010200001", "국고채 5년"),
    "ktb20":   ("010220000", "국고채 20년"),
    "msb1":    ("010400001", "통안증권 1년"),
    "msb2":    ("010400002", "통안증권 2년"),
    "bok_rate": ("0101000", "한국은행 기준금리", "722Y001"),
    # 주식(위험자산) — 통계표 802Y001 주식시장(일)
    "kospi":   ("0001000", "코스피", "802Y001"),
    "kosdaq":  ("0089000", "코스닥", "802Y001"),
    "foreign_kospi":  ("0030000", "외국인 순매수(코스피, 억원)", "802Y001"),
    "foreign_kosdaq": ("0113000", "외국인 순매수(코스닥, 억원)", "802Y001"),
}

OUT_PATH = os.path.join(os.path.dirname(__file__), "data", "rates.csv")


def _get(url: str) -> dict:
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    return r.json()


def list_items() -> None:
    js = _get(f"{BASE}/StatisticItemList/{API_KEY}/json/kr/1/200/{STAT_CODE}")
    rows = js.get("StatisticItemList", {}).get("row", [])
    if not rows:
        print("항목을 못 받았습니다:", js)
        return
    for x in rows:
        print(x.get("ITEM_CODE"), "|", x.get("ITEM_NAME"), "|", x.get("CYCLE"))


def fetch_retry(*args, tries: int = 3) -> pd.Series:
    """일시적 서버 오류에 대비해 최대 3번 시도 (5초, 10초 간격)."""
    for k in range(tries):
        try:
            return fetch(*args)
        except Exception as e:  # noqa: BLE001
            if k == tries - 1:
                raise
            print(f"  재시도 {k + 1}/{tries - 1}: {e}")
            time.sleep(5 * (k + 1))


def fetch(item_code: str, start: str, end: str, stat: str = STAT_CODE) -> pd.Series:
    url = (f"{BASE}/StatisticSearch/{API_KEY}/json/kr/1/100000/"
           f"{stat}/D/{start}/{end}/{item_code}")
    js = _get(url)
    if "StatisticSearch" not in js:
        raise RuntimeError(
            f"ECOS 응답 오류(항목 {item_code}): {js.get('RESULT', js)}\n"
            f"→ 'python collect.py --list'로 항목코드를 확인하세요."
        )
    rows = js["StatisticSearch"]["row"]
    print(f"  {item_code} = {rows[0].get('ITEM_NAME1')} ({len(rows)}일치)")
    data = {}
    for x in rows:
        v = x.get("DATA_VALUE")
        if v in (None, "", "-"):
            continue
        data[pd.to_datetime(x["TIME"], format="%Y%m%d")] = float(v)
    return pd.Series(data).sort_index()


# ---------------------------------------------------------------------------
# KOFIA 채권정보센터: 채권시가평가기준수익률(민평, 평가사 평균) 일자별
# ---------------------------------------------------------------------------
KOFIA_URL = "https://www.kofiabond.or.kr/proframeWeb/XMLSERVICES/"
KOFIA_PATH = os.path.join(os.path.dirname(__file__), "data", "kofia.csv")
# 잔존만기 태그: val1=3월 val2=6월 val3=9월 val4=1년 val5=1.5년 val6=2년 val7=2.5년
#                val8=3년 val9=4년 val10=5년 val11=7년 val12=10년 … val16=50년
KOFIA_ROWS = [                 # (sigaBrnCd, 만기 태그, 컬럼명)
    ("6010123", "val8",  "yeojeon_aa"),      # 금융채 II(금융기관채) 무보증 AA- = 여전채(카드·캐피탈채) AA-
    ("6010123", "val4",  "yeojeon_aa_1y"),
    ("6010123", "val10", "yeojeon_aa_5y"),
    ("6010131", "val8",  "yeojeon_a_plus"),  # 금융채 II 무보증 A+ = 중소형 캐피탈급
    ("1010000", "val8",  "ktb3_mp"),         # 국고채권 (같은 민평 기준으로 스프레드 계산용)
    ("1010000", "val4",  "ktb1_mp"),
    ("1010000", "val10", "ktb5_mp"),
    ("5030110", "val8",  "bank_aaa"),        # 금융채 I(은행채) 무보증 AAA (시중은행채)
    ("5030110", "val4",  "bank_aaa_1y"),
    ("7010123", "val8",  "corp_aa_mp"),      # 회사채 I(공모) 무보증 AA- (민평)
    ("7010133", "val8",  "corp_a_minus"),    # 회사채 I(공모) 무보증 A-
    ("7010211", "val8",  "corp_bbb_plus"),   # 회사채 I(공모) 무보증 BBB+
]
KOFIA_COLS = [c for _, _, c in KOFIA_ROWS]
KOFIA_SCHEMA = 4             # KOFIA_ROWS를 바꾸면 1 올리기 → 과거 날짜 재수집
KOFIA_MAX_CALLS = 900         # 1회 실행당 최대 조회 일수(첫 실행 백필 포함)


def _kofia_day(session: requests.Session, ymd: str) -> dict:
    import xml.etree.ElementTree as ET

    body = f"""<?xml version="1.0" encoding="utf-8"?>
<message>
  <proframeHeader>
    <pfmAppName>BIS-KOFIABOND</pfmAppName>
    <pfmSvcName>BISBndSrtPrcSrchSO</pfmSvcName>
    <pfmFnName>selectDay</pfmFnName>
  </proframeHeader>
  <systemHeader></systemHeader>
<BISBndSrtPrcDayDTO><standardDt>{ymd}</standardDt><reportCompCd>A20000</reportCompCd><applyGbCd>C00</applyGbCd><val1>A10002</val1><val2>A10003</val2><val3>A10004</val3><val4>A10005</val4><val5>A10006</val5></BISBndSrtPrcDayDTO>
</message>
"""
    r = session.post(KOFIA_URL, data=body.encode("utf-8"), timeout=30)
    r.raise_for_status()
    root = ET.fromstring(r.content)
    out = {}
    for row in root.iter("BISBndSrtPrcDayDTO"):
        code = (row.findtext("sigaBrnCd") or "").strip()
        for c, tag, col in KOFIA_ROWS:
            if c == code:
                v = (row.findtext(tag) or "").strip()
                if v:
                    out[col] = float(v)
    return out


def update_kofia(dates: pd.DatetimeIndex) -> pd.DataFrame:
    """ECOS에 데이터가 있는 영업일 중 kofia.csv에 아직 없는 날만 조회해 누적 저장."""
    if os.path.exists(KOFIA_PATH):
        have = pd.read_csv(KOFIA_PATH, parse_dates=["date"]).set_index("date")
    else:
        have = pd.DataFrame(columns=KOFIA_COLS)
        have.index.name = "date"

    # 수집 항목이 바뀌면(KOFIA_SCHEMA 증가) 기존 날짜도 한 번 다시 채움
    for c in KOFIA_COLS + ["schema"]:
        if c not in have.columns:
            have[c] = float("nan")
    complete = have.index[have["schema"] == KOFIA_SCHEMA]
    todo = [d for d in dates if d not in complete and d >= pd.Timestamp(KOFIA_START)][-KOFIA_MAX_CALLS:]
    print(f"KOFIA 수집: 신규 {len(todo)}일")

    s = requests.Session()
    s.headers.update({
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "Referer": "https://www.kofiabond.or.kr/",
        "User-Agent": "Mozilla/5.0 (rate-dashboard; personal study)",
    })
    new = {}
    for i, d in enumerate(todo):
        try:
            vals = _kofia_day(s, d.strftime("%Y%m%d"))
        except Exception as e:  # noqa: BLE001
            if i == 0 and not new:
                raise  # 첫 요청부터 실패하면 접속 자체가 안 되는 것
            print(f"  {d.date()} 실패: {e}")
            continue
        if vals:
            vals["schema"] = KOFIA_SCHEMA
            new[d] = vals
        time.sleep(0.25)       # 서버 부담 줄이기
        if (i + 1) % 100 == 0:
            print(f"  …{i + 1}/{len(todo)}")

    if new:
        add = pd.DataFrame.from_dict(new, orient="index")
        add.index.name = "date"
        have = pd.concat([have, add])
        have = have[~have.index.duplicated(keep="last")].sort_index()
        os.makedirs(os.path.dirname(KOFIA_PATH), exist_ok=True)
        have.to_csv(KOFIA_PATH, float_format="%.3f")
    if len(have):
        print(f"  여전채 AA- 3년 최신: {have.index.max().date()} = {have['yeojeon_aa'].iloc[-1]}")
    return have


KOFIA_SPREADS = {   # 컬럼 = (A − B) × 100 bp
    "yeojeon_spread_bp":    ("yeojeon_aa", "ktb3_mp"),
    "yeojeon_grade_bp":     ("yeojeon_a_plus", "yeojeon_aa"),
    "corp_a_spread_bp":     ("corp_a_minus", "ktb3_mp"),
    "corp_grade_a_bp":      ("corp_a_minus", "corp_aa_mp"),
    "corp_grade_bbb_bp":    ("corp_bbb_plus", "corp_aa_mp"),
    # 여전채 만기별 · 은행채
    "yeojeon_spread_1y_bp": ("yeojeon_aa_1y", "ktb1_mp"),
    "yeojeon_spread_5y_bp": ("yeojeon_aa_5y", "ktb5_mp"),
    "yeojeon_term_bp":      ("yeojeon_aa_5y", "yeojeon_aa_1y"),
    "bank_spread_bp":       ("bank_aaa", "ktb3_mp"),
    "yeojeon_bank_bp":      ("yeojeon_aa", "bank_aaa"),
}


def add_kofia_spreads(df: pd.DataFrame) -> None:
    for col, (a, b) in KOFIA_SPREADS.items():
        if {a, b} <= set(df.columns):
            df[col] = ((df[a] - df[b]) * 100).round(1)


def main() -> None:
    if not API_KEY:
        sys.exit("ECOS_API_KEY 환경변수가 비어 있습니다.")

    if "--list" in sys.argv:
        list_items()
        return

    today = dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).strftime("%Y%m%d")
    print(f"ECOS 수집: {START_DATE} ~ {today}")

    prev = pd.read_csv(OUT_PATH, parse_dates=["date"]).set_index("date") if os.path.exists(OUT_PATH) else None
    series = {}
    for col, v in ITEMS.items():
        try:
            series[col] = fetch_retry(v[0], START_DATE, today, *v[2:])
        except Exception as e:  # noqa: BLE001
            if prev is not None and col in prev.columns:
                print(f"[경고] {col} 수집 실패 → 지난번 저장값 유지: {e}")
                series[col] = prev[col].dropna()
            elif col in ("ktb3", "ktb10"):
                raise   # 핵심 지표가 아예 없으면 진행 불가
            else:
                print(f"[경고] {col} 수집 실패, 이번엔 제외: {e}")
    bok = series.pop("bok_rate", None)
    df = pd.DataFrame(series).dropna(how="all")
    df = df[df["ktb3"].notna()]          # 금리 영업일 기준
    df.index.name = "date"
    if bok is not None and len(bok):
        df["bok_rate"] = bok.sort_index().reindex(df.index, method="ffill")

    # 스프레드(bp)
    df["term_spread_bp"] = ((df["ktb10"] - df["ktb3"]) * 100).round(1)
    df["corp_spread_bp"] = ((df["corp_aa"] - df["ktb3"]) * 100).round(1)
    df["ultra_spread_bp"] = ((df["ktb30"] - df["ktb10"]) * 100).round(1)   # 10-30년 (보험 ALM)
    df["cp_cd_spread_bp"] = ((df["cp91"] - df["cd91"]) * 100).round(1)     # 단기 신용경색 지표
    if {"msb1", "bok_rate"} <= set(df.columns):                                # 금리 기대
        df["msb1_policy_bp"] = ((df["msb1"] - df["bok_rate"]) * 100).round(1)
    if {"ktb2", "bok_rate"} <= set(df.columns):
        df["ktb2_policy_bp"] = ((df["ktb2"] - df["bok_rate"]) * 100).round(1)

    # KOFIA 민평 (실패해도 ECOS 데이터는 그대로 저장)
    try:
        kofia = update_kofia(df.index)
    except Exception as e:  # noqa: BLE001
        print(f"[경고] KOFIA 수집 실패: {e}")
        kofia = None
        if os.path.exists(KOFIA_PATH):   # 지난번까지 쌓인 값으로라도 지표 유지
            print("  → 저장된 kofia.csv 값으로 진행")
            kofia = pd.read_csv(KOFIA_PATH, parse_dates=["date"]).set_index("date")
    if kofia is not None:
        df = df.join(kofia.drop(columns=["schema"], errors="ignore"), how="left")
        add_kofia_spreads(df)

    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    df.to_csv(OUT_PATH, float_format="%.3f")
    last = df.index.max().date()
    print(f"저장 완료: {OUT_PATH} ({len(df)}행, 최신 {last})")


if __name__ == "__main__":
    main()
