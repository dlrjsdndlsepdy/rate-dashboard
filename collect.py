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
START_DATE = "20240101"        # 이 날짜부터 매번 전체를 다시 받아옴(누락돼도 다음 실행 때 자동 복구)

# 컬럼명: (ECOS 항목코드, 표시 이름)
ITEMS = {
    "ktb3":    ("010200000", "국고채 3년"),
    "ktb10":   ("010210000", "국고채 10년"),
    "corp_aa": ("010300000", "회사채 AA- 3년"),
    "ktb30":   ("010230000", "국고채 30년"),
    "cd91":    ("010502000", "CD 91일"),
    "cp91":    ("010503000", "CP 91일"),
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


def fetch(item_code: str, start: str, end: str) -> pd.Series:
    url = (f"{BASE}/StatisticSearch/{API_KEY}/json/kr/1/100000/"
           f"{STAT_CODE}/D/{start}/{end}/{item_code}")
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
KOFIA_ROWS = {                 # sigaBrnCd → 컬럼명
    "6010123": "yeojeon_aa",   # 금융채 II(금융기관채) 무보증 AA-  = 여전채(카드·캐피탈채) AA-
    "6010131": "yeojeon_a_plus",  # 금융채 II(금융기관채) 무보증 A+ = 중소형 캐피탈급
    "1010000": "ktb3_mp",      # 국고채권 (같은 민평 기준으로 스프레드 계산용)
}
KOFIA_TENOR_TAG = "val8"       # 잔존만기 3년 (val1=3월 … val8=3년 … val16=50년)
KOFIA_SCHEMA = 2              # KOFIA_ROWS를 바꾸면 1 올리기 → 과거 날짜 재수집
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
        if code in KOFIA_ROWS:
            v = (row.findtext(KOFIA_TENOR_TAG) or "").strip()
            if v:
                out[KOFIA_ROWS[code]] = float(v)
    return out


def update_kofia(dates: pd.DatetimeIndex) -> pd.DataFrame:
    """ECOS에 데이터가 있는 영업일 중 kofia.csv에 아직 없는 날만 조회해 누적 저장."""
    if os.path.exists(KOFIA_PATH):
        have = pd.read_csv(KOFIA_PATH, parse_dates=["date"]).set_index("date")
    else:
        have = pd.DataFrame(columns=list(KOFIA_ROWS.values()))
        have.index.name = "date"

    # 수집 항목이 바뀌면(KOFIA_SCHEMA 증가) 기존 날짜도 한 번 다시 채움
    for c in list(KOFIA_ROWS.values()) + ["schema"]:
        if c not in have.columns:
            have[c] = float("nan")
    complete = have.index[have["schema"] == KOFIA_SCHEMA]
    todo = [d for d in dates if d not in complete][-KOFIA_MAX_CALLS:]
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
        have.to_csv(KOFIA_PATH, float_format="%.3f")
    if len(have):
        print(f"  여전채 AA- 3년 최신: {have.index.max().date()} = {have['yeojeon_aa'].iloc[-1]}")
    return have


def main() -> None:
    if not API_KEY:
        sys.exit("ECOS_API_KEY 환경변수가 비어 있습니다.")

    if "--list" in sys.argv:
        list_items()
        return

    today = dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).strftime("%Y%m%d")
    print(f"ECOS 수집: {START_DATE} ~ {today}")

    series = {col: fetch(code, START_DATE, today) for col, (code, _) in ITEMS.items()}
    df = pd.DataFrame(series).dropna(how="all")
    df.index.name = "date"

    # 스프레드(bp)
    df["term_spread_bp"] = ((df["ktb10"] - df["ktb3"]) * 100).round(1)
    df["corp_spread_bp"] = ((df["corp_aa"] - df["ktb3"]) * 100).round(1)
    df["ultra_spread_bp"] = ((df["ktb30"] - df["ktb10"]) * 100).round(1)   # 10-30년 (보험 ALM)
    df["cp_cd_spread_bp"] = ((df["cp91"] - df["cd91"]) * 100).round(1)     # 단기 신용경색 지표

    # KOFIA 여전채 AA- (실패해도 ECOS 데이터는 그대로 저장)
    try:
        kofia = update_kofia(df.index)
        df = df.join(kofia.drop(columns=["schema"], errors="ignore"), how="left")
        df["yeojeon_spread_bp"] = ((df["yeojeon_aa"] - df["ktb3_mp"]) * 100).round(1)
        df["yeojeon_grade_bp"] = ((df["yeojeon_a_plus"] - df["yeojeon_aa"]) * 100).round(1)
    except Exception as e:  # noqa: BLE001
        print(f"[경고] KOFIA 수집 실패, 여전채 없이 진행: {e}")

    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    df.to_csv(OUT_PATH, float_format="%.3f")
    last = df.index.max().date()
    print(f"저장 완료: {OUT_PATH} ({len(df)}행, 최신 {last})")


if __name__ == "__main__":
    main()
