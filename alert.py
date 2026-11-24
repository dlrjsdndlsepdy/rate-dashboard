"""
🔔 알림: 큰 신호가 있는 날만 GitHub 이슈를 만들어 알림(이메일·GitHub 앱)을 받음

알림 조건 (하나라도 해당되면)
  1) 큰 급변 ⚡: 전일 대비 변화가 평소 하루 변동폭(1년 표준편차)의 3배 이상
     (페이지의 ⚡ 표시는 2배 기준 — 알림은 더 드문 것만 보내려고 3배)
  2) 기관 신호등 색 변화: 캐피탈·보험·은행 중 하나라도 🟢/🟡/🔴 바뀜
  3) 내일 한국 시장에 반영될 큰 일정: 금통위·FOMC·미국 CPI·고용

같은 기준일에는 한 번만 보냄 (data/alert_state.txt에 마지막 알림 기준일 저장).
결과: alert.md 파일을 만들면 워크플로가 이슈로 올림. 조건이 없으면 파일을 만들지 않음.
"""
import datetime as dt
import os

import pandas as pd

import events
import institutions
import interpret

ROOT = os.path.dirname(__file__)
STATE = os.path.join(ROOT, "data", "alert_state.txt")
OUT = os.path.join(ROOT, "alert.md")
ALERT_SIGMA = 3
SITE = "https://dlrjsdndlsepdy.github.io/rate-dashboard/daily.html"


def main():
    if os.path.exists(OUT):
        os.remove(OUT)
    df = pd.read_csv(os.path.join(ROOT, "data", "rates.csv"), parse_dates=["date"]).set_index("date").sort_index()
    day = df.index.max()
    last = open(STATE).read().strip() if os.path.exists(STATE) else ""
    if last == f"{day:%Y-%m-%d}":
        print("오늘 기준일 알림은 이미 보냄")
        return

    lines = []
    today = interpret.interpret_day(interpret.Day(df, len(df) - 1))
    t = interpret.Day(df, len(df) - 1)
    for c, (name, unit) in interpret.NAMES.items():
        if not t.has(c):
            continue
        dv, sg = t.d(c), t.sigma(c)
        if sg and sg == sg and abs(dv) >= ALERT_SIGMA * sg:
            lines.append(f"- ⚡ {name} {interpret._chg(c, dv)} — 평소 하루 변동폭의 {abs(dv) / sg:.1f}배")
    now, before = institutions.evaluate(df), institutions.evaluate(df.iloc[:-1])
    for k, (icon, word, total, _) in now.items():
        if before[k][0] != icon:
            lines.append(f"- 🏢 {institutions.SPEC[k]['title']} 신호등 {before[k][0]} → {icon} {word} ({total:+d})")
    nxt = day.date() + dt.timedelta(days=1)
    while nxt.weekday() >= 5:
        nxt += dt.timedelta(days=1)
    for e in events.all_events():
        if e["kr"] == nxt:
            lines.append(f"- 📅 다음 거래일({nxt:%m/%d}) {e['kind']} 반영 — {events.WATCH[e['kind']]}")

    if not lines:
        print("알림 조건 없음")
        return
    body = (f"**기준일 {day:%Y-%m-%d}** · 커브 국면: {today.get('regime') or '-'}\n\n"
            + "\n".join(lines)
            + f"\n\n👉 [오늘의 해석 보기]({SITE})\n\n<sub>자동 생성 알림 · 확인했으면 이슈를 닫아도 돼요.</sub>\n")
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(body)
    with open(STATE, "w") as f:
        f.write(f"{day:%Y-%m-%d}")
    print(f"알림 작성: {len(lines)}건")


if __name__ == "__main__":
    main()
