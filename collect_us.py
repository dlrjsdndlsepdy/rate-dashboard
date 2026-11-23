"""
미국 금리·크레딧(FRED) + 한미 비교용 한국 기준금리·원/달러(ECOS) → data/us.csv, data/kr_extra.csv

환경변수: FRED_API_KEY, ECOS_API_KEY
"""
import os
import sys
import datetime as dt

import pandas as pd
import requests

ROOT = os.path.dirname(__file__)
START = "2024-01-01"

FRED_KEY = os.environ.get("FRED_API_KEY", "").strip()
ECOS_KEY = os.environ.get("ECOS_API_KEY", "").strip()

# 컬럼명: FRED 시리즈 ID
FRED = {
    "ust3m": "DGS3MO",          # 미 국채 3개월
    "ust2": "DGS2",             # 미 국채 2년
    "ust10": "DGS10",           # 미 국채 10년
    "ust30": "DGS30",           # 미 국채 30년
    "fed_upper": "DFEDTARU",    # 연준 기준금리 상단
    "fed_lower": "DFEDTARL",    # 연준 기준금리 하단
    "effr": "DFF",              # 실효 연방기금금리
    "sofr": "SOFR",             # SOFR
    "ig_oas": "BAMLC0A0CM",     # ICE BofA 미국 투자등급 회사채 OAS (%)
    "hy_oas": "BAMLH0A0HYM2",   # ICE BofA 미국 하이일드 OAS (%)
    "tips10": "DFII10",         # 10년 TIPS 실질금리
    "sp500": "SP500",           # S&P 500 지수
    "vix": "VIXCLS",            # VIX (S&P 500 내재변동성, '공포지수')
    "nasdaq": "NASDAQCOM",      # 나스닥 종합지수
    "nikkei": "NIKKEI225",      # 니케이 225
    "wti": "DCOILWTICO",        # WTI 유가 (달러/배럴)
    "dxy": "DTWEXBGS",          # 달러인덱스 (연준 광의 무역가중, 2006.1=100)
}
MARKET_ONLY = ["nasdaq", "nikkei", "wti", "dxy"]   # 증시 페이지 전용(미국 대시보드 데이터에는 넣지 않음)

# ECOS: (통계표, 주기, 항목코드)
ECOS = {
    "bok_rate": ("722Y001", "D", "0101000"),   # 한국은행 기준금리
    "usdkrw": ("731Y001", "D", "0000001"),     # 원/미국달러 매매기준율
}


def fred(series_id: str) -> pd.Series:
    r = requests.get(
        "https://api.stlouisfed.org/fred/series/observations",
        params={"series_id": series_id, "api_key": FRED_KEY, "file_type": "json",
                "observation_start": START},
        timeout=30,
    )
    r.raise_for_status()
    obs = r.json().get("observations", [])
    s = {pd.Timestamp(o["date"]): float(o["value"]) for o in obs if o["value"] not in (".", "")}
    print(f"  FRED {series_id}: {len(s)}개, 최신 {max(s).date() if s else '-'}")
    return pd.Series(s).sort_index()


def ecos(stat: str, cycle: str, item: str) -> pd.Series:
    end = dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).strftime("%Y%m%d")
    url = (f"https://ecos.bok.or.kr/api/StatisticSearch/{ECOS_KEY}/json/kr/1/100000/"
           f"{stat}/{cycle}/{START.replace('-', '')}/{end}/{item}")
    js = requests.get(url, timeout=30).json()
    if "StatisticSearch" not in js:
        raise RuntimeError(f"ECOS 오류 {stat}/{item}: {js.get('RESULT', js)}")
    rows = js["StatisticSearch"]["row"]
    print(f"  ECOS {stat}/{item} = {rows[0].get('ITEM_NAME1')} ({len(rows)}개)")
    return pd.Series({pd.to_datetime(x["TIME"], format="%Y%m%d"): float(x["DATA_VALUE"])
                      for x in rows if x.get("DATA_VALUE") not in (None, "", "-")}).sort_index()


def main() -> None:
    if not FRED_KEY:
        sys.exit("FRED_API_KEY 환경변수가 비어 있습니다.")
    os.makedirs(os.path.join(ROOT, "data"), exist_ok=True)

    print("FRED 수집")
    us = pd.DataFrame({c: fred(sid) for c, sid in FRED.items()})
    # 증시 페이지용: 주가지수는 국채 휴장일(주식시장은 개장)도 빠지지 않게 따로 저장
    eq = us[["sp500", "vix"] + MARKET_ONLY].dropna(how="all")
    eq.index.name = "date"
    eq.to_csv(os.path.join(ROOT, "data", "us_equity.csv"), float_format="%.4f")
    us = us.drop(columns=MARKET_ONLY)
    # 국채 거래일 기준으로 맞추고, 정책금리처럼 매일 있는 시리즈는 그날 값 사용
    us = us[us["ust10"].notna()].copy()
    us[["fed_upper", "fed_lower", "effr", "sofr"]] = us[["fed_upper", "fed_lower", "effr", "sofr"]].ffill()
    us.index.name = "date"

    # 파생 지표
    us["fed_mid"] = (us["fed_upper"] + us["fed_lower"]) / 2
    us["bei10"] = us["ust10"] - us["tips10"]                          # 10년 기대인플레이션(BEI)
    us["s2s10_bp"] = ((us["ust10"] - us["ust2"]) * 100).round(1)      # 2s10s
    us["s3m10_bp"] = ((us["ust10"] - us["ust3m"]) * 100).round(1)     # 3M-10Y
    us["s10s30_bp"] = ((us["ust30"] - us["ust10"]) * 100).round(1)
    us["policy_gap_bp"] = ((us["ust2"] - us["fed_mid"]) * 100).round(1)  # 2년 - 기준금리 중간값
    us["ig_bp"] = (us["ig_oas"] * 100).round(1)
    us["hy_bp"] = (us["hy_oas"] * 100).round(1)
    us["hy_ig_bp"] = (us["hy_bp"] - us["ig_bp"]).round(1)
    us = us.drop(columns=["ig_oas", "hy_oas"])
    us.to_csv(os.path.join(ROOT, "data", "us.csv"), float_format="%.4f")
    print(f"저장: data/us.csv ({len(us)}행, 최신 {us.index.max().date()})")

    # 한미 비교용 한국 데이터 (실패해도 미국 데이터는 유지)
    try:
        if not ECOS_KEY:
            raise RuntimeError("ECOS_API_KEY 없음")
        print("ECOS 수집(한미 비교용)")
        kr = pd.DataFrame({c: ecos(*a) for c, a in ECOS.items()})
        kr.index.name = "date"
        kr.to_csv(os.path.join(ROOT, "data", "kr_extra.csv"), float_format="%.4f")
        print(f"저장: data/kr_extra.csv ({len(kr)}행)")
    except Exception as e:  # noqa: BLE001
        print(f"[경고] 한국 기준금리·환율 수집 실패: {e}")


if __name__ == "__main__":
    main()
