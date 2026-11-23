"""
한국은행 ECOS API에서 일별 시장금리를 받아 data/rates.csv로 저장합니다.

- 국고채 3년, 국고채 10년, 회사채(무보증 3년) AA-
- 스프레드(bp): 장단기(10Y-3Y), 회사채 크레딧(AA- - 국고 3Y)

사용법
  python collect.py          # 데이터 수집
  python collect.py --list   # 통계표 817Y002의 항목코드 목록 출력(코드 확인용)

환경변수 ECOS_API_KEY 에 인증키가 있어야 합니다.
"""
import os
import sys
import datetime as dt

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

    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    df.to_csv(OUT_PATH, float_format="%.3f")
    last = df.index.max().date()
    print(f"저장 완료: {OUT_PATH} ({len(df)}행, 최신 {last})")


if __name__ == "__main__":
    main()
