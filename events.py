"""
이벤트 캘린더 — 금통위 · FOMC · 미국 CPI · 미국 고용보고서

일정이 바뀌거나 새해 일정이 나오면 아래 EVENTS 목록만 고치면 됩니다.
  (날짜, 종류, 메모)   날짜는 '발표 기관 현지 날짜'
  - 금통위: 한국 날짜, 오전 9시대 결정 → 그날 한국 시장에 반영
  - FOMC: 미국 동부 날짜(결정일), 오후 2시 발표 = 한국 시간 다음 날 새벽 3~4시 → 다음 날 한국 시장에 반영
  - CPI·고용: 미국 동부 오전 8시 30분 = 한국 시간 같은 날 밤 9시 30분~10시 30분 → 다음 날 한국 시장에 반영

출처(2026-11-24 확인)
  - 금통위: 2026-11-26은 한은 발표 보도, 2027 일정은 2026-10-29 금통위 의결(1/14 보도 확인, 나머지는 정리 자료 기준)
  - FOMC: 연준 2026-11-12 발표 '2027 수정 일정' (10/26-27 회의는 정책 결정 없음, 12월 회의 → 11/16-17로 이동)
  - CPI·고용: 미 노동통계국(BLS) 공표 일정
과거 금리 변경일(차트 세로선)은 기준금리 데이터에서 자동으로 찾습니다.
"""
import datetime as dt

import pandas as pd

BOK, FOMC, CPI, NFP = "금통위", "FOMC", "미국 CPI", "미국 고용"

EVENTS = [
    # ---- 한국은행 금통위 (통화정책방향 결정회의)
    ("2026-11-26", BOK, "2026년 마지막 결정"),
    ("2027-01-14", BOK, ""), ("2027-02-25", BOK, ""), ("2027-04-09", BOK, ""), ("2027-05-27", BOK, ""),
    ("2027-07-15", BOK, ""), ("2027-08-26", BOK, ""), ("2027-10-15", BOK, ""), ("2027-11-25", BOK, ""),
    # ---- FOMC (결정일, 미국 동부)
    ("2024-01-31", FOMC, ""), ("2024-03-20", FOMC, ""), ("2024-05-01", FOMC, ""), ("2024-06-12", FOMC, ""),
    ("2024-07-31", FOMC, ""), ("2024-09-18", FOMC, ""), ("2024-11-07", FOMC, ""), ("2024-12-18", FOMC, ""),
    ("2025-01-29", FOMC, ""), ("2025-03-19", FOMC, ""), ("2025-05-07", FOMC, ""), ("2025-06-18", FOMC, ""),
    ("2025-07-30", FOMC, ""), ("2025-09-17", FOMC, ""), ("2025-10-29", FOMC, ""), ("2025-12-10", FOMC, ""),
    ("2026-01-28", FOMC, ""), ("2026-03-18", FOMC, ""), ("2026-04-29", FOMC, ""), ("2026-06-17", FOMC, ""),
    ("2026-07-29", FOMC, ""), ("2026-09-16", FOMC, ""), ("2026-10-28", FOMC, ""), ("2026-12-09", FOMC, "경제전망(SEP) 포함"),
    ("2027-01-27", FOMC, ""), ("2027-03-17", FOMC, "경제전망(SEP) 포함"), ("2027-04-28", FOMC, ""),
    ("2027-06-09", FOMC, "경제전망(SEP) 포함"), ("2027-07-28", FOMC, ""), ("2027-09-15", FOMC, "경제전망(SEP) 포함"),
    ("2027-11-17", FOMC, "2027년 마지막 결정"),
    # ---- 미국 CPI (발표일, 미국 동부)
    ("2026-12-10", CPI, "11월분"), ("2027-01-13", CPI, "12월분"), ("2027-02-11", CPI, "1월분"),
    ("2027-03-10", CPI, "2월분"), ("2027-04-13", CPI, "3월분"), ("2027-05-12", CPI, "4월분"),
    ("2027-06-10", CPI, "5월분"), ("2027-07-14", CPI, "6월분"), ("2027-08-11", CPI, "7월분"),
    ("2027-09-14", CPI, "8월분"), ("2027-10-14", CPI, "9월분"), ("2027-11-10", CPI, "10월분"), ("2027-12-10", CPI, "11월분"),
    # ---- 미국 고용보고서 (발표일, 미국 동부)
    ("2026-12-04", NFP, "11월분"), ("2027-01-08", NFP, "12월분"), ("2027-02-05", NFP, "1월분"),
    ("2027-03-05", NFP, "2월분"), ("2027-04-02", NFP, "3월분"), ("2027-05-07", NFP, "4월분"),
    ("2027-06-04", NFP, "5월분"), ("2027-07-02", NFP, "6월분"), ("2027-08-06", NFP, "7월분"),
    ("2027-09-03", NFP, "8월분"), ("2027-10-08", NFP, "9월분"), ("2027-11-05", NFP, "10월분"), ("2027-12-03", NFP, "11월분"),
]

KST_TIME = {BOK: "오전 9시대", FOMC: "다음 날 새벽 3~4시", CPI: "밤 9:30~10:30", NFP: "밤 9:30~10:30"}
WATCH = {   # 무엇을 볼지 (시장의 표준적 읽기)
    BOK: "통안 1·2년, 국고 3년 — 결정과 총재 발언이 단기 금리 기대를 바로 바꿔요",
    FOMC: "미 2년·10년, 원/달러 → 다음 날 국고 10년 동조 여부",
    CPI: "미 2년(정책 기대)·10년, BEI → 다음 날 국고채",
    NFP: "미 2년·10년, 달러 → 다음 날 국고채·원/달러",
}
COLOR = {BOK: "#ff8787", FOMC: "#ffd43b", CPI: "#da77f2", NFP: "#63e6be"}


def _kst_today():
    return dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).date()


def kr_effect(date: dt.date, kind: str) -> dt.date:
    """한국 시장에 처음 반영되는 날짜(달력 기준, 주말이면 다음 월요일)."""
    d = date if kind == BOK else date + dt.timedelta(days=1)
    while d.weekday() >= 5:
        d += dt.timedelta(days=1)
    return d


def all_events():
    out = []
    for ds, kind, memo in EVENTS:
        d = dt.date.fromisoformat(ds)
        out.append({"date": d, "kind": kind, "memo": memo, "kr": kr_effect(d, kind)})
    return sorted(out, key=lambda e: e["date"])


def upcoming(days: int = 21, today: dt.date = None):
    today = today or _kst_today()
    return [e for e in all_events() if today <= e["kr"] <= today + dt.timedelta(days=days)]


def rate_changes(df: pd.DataFrame):
    """기준금리 데이터에서 변경일을 찾음 → [(날짜, '인상'/'인하', 새 금리)]."""
    if "bok_rate" not in df.columns:
        return []
    s = df["bok_rate"].dropna()
    ch = s.diff()
    return [(d.date(), "인상" if v > 0 else "인하", s.loc[d]) for d, v in ch.items() if abs(v) > 1e-9]


def chart_lines(df: pd.DataFrame):
    """대시보드 차트 세로선: 과거 기준금리 변경 + FOMC 결정(한국 반영일)."""
    lines = [{"d": d.isoformat(), "t": f"금통위 {w} {r:.2f}%", "c": "#ff8787" if w == "인상" else "#4dabf7"}
             for d, w, r in rate_changes(df)]
    last = df.index.max().date() if len(df) else _kst_today()
    for e in all_events():
        if e["kind"] == FOMC and e["kr"] <= last:
            lines.append({"d": e["kr"].isoformat(), "t": "FOMC", "c": COLOR[FOMC]})
    return sorted(lines, key=lambda x: x["d"])


def reaction_note(day: dt.date):
    """오늘이 어떤 이벤트가 처음 반영된 날인지 → 해석 문장."""
    out = []
    for e in all_events():
        if e["kr"] == day:
            if e["kind"] == BOK:
                out.append("오늘은 금통위 결정일이에요. 단기물(통안·국고 3년) 움직임은 결정·총재 발언의 영향일 가능성이 커요.")
            else:
                out.append(f"오늘은 {e['kind']}({e['date']:%m/%d} 미국 발표) 결과가 처음 반영된 거래일이에요. 국고 10년 움직임을 미국 금리와 함께 보세요.")
    return out


def _dday(e, today):
    n = (e["kr"] - today).days
    return "오늘" if n == 0 else f"D-{n}"


def section(today: dt.date = None) -> str:
    today = today or _kst_today()
    ev = upcoming(21, today)
    if not ev:
        return ""
    rows = "".join(
        f'<tr><td><b>{_dday(e, today)}</b></td><td><span style="color:{COLOR[e["kind"]]}">●</span> {e["kind"]}'
        f'{" · " + e["memo"] if e["memo"] else ""}</td>'
        f'<td>{e["date"]:%m/%d}{"" if e["kind"] == BOK else " (미국)"} · 한국 {KST_TIME[e["kind"]]}</td>'
        f'<td class="muted">{WATCH[e["kind"]]}</td></tr>' for e in ev)
    soon = [e for e in ev if 0 <= (e["kr"] - today).days <= 1]
    warn = ""
    if soon:
        names = ", ".join(f'{"오늘" if e["kr"] == today else "내일"} {e["kind"]}' for e in soon)
        warn = f'<div class="cp" style="margin-bottom:8px">⚠️ {names} — 결과가 반영되는 날은 금리 변동성이 커질 수 있어요.</div>'
    return (f'<h2 id="events">📅 다가오는 일정 (3주)</h2><div class="card">{warn}'
            f'<table>{rows}</table><div class="muted" style="margin-top:6px">D-n은 한국 시장에 반영되는 날 기준이에요. '
            f'미국 일정은 미국 동부 날짜이고, 한국 시장에는 다음 거래일에 반영돼요.</div></div>')
