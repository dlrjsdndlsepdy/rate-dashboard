"""
증시 한눈에 (docs/markets.html)
  1) 주가지수: 코스피 · 코스닥 · 나스닥 · S&P 500 · 니케이 225
  2) 외국인 수급: 코스피 · 코스닥 외국인 순매수(억원)
  3) 환율 · 달러 · 원자재 · 변동성: 원/달러 · 달러인덱스 · WTI · VIX

입력: data/rates.csv (ECOS 주가지수·외국인 순매수), data/us_equity.csv (FRED), data/kr_extra.csv (원/달러)
build_us.py 마지막에 build()가 호출됨.
"""
import json
import math
import os
import datetime as dt

import pandas as pd

ROOT = os.path.dirname(__file__)
D = lambda *p: os.path.join(ROOT, *p)  # noqa: E731

# (키, 이름, 파일, 컬럼, 국기)
INDEXES = [
    ("kospi", "코스피", "rates.csv", "kospi", "🇰🇷"),
    ("kosdaq", "코스닥", "rates.csv", "kosdaq", "🇰🇷"),
    ("nasdaq", "나스닥", "us_equity.csv", "nasdaq", "🇺🇸"),
    ("sp500", "S&P 500", "us_equity.csv", "sp500", "🇺🇸"),
    ("nikkei", "니케이 225", "us_equity.csv", "nikkei", "🇯🇵"),
]
FLOWS = [
    ("foreign_kospi", "외국인 순매수 · 코스피", "rates.csv", "foreign_kospi"),
    ("foreign_kosdaq", "외국인 순매수 · 코스닥", "rates.csv", "foreign_kosdaq"),
]
# (키, 이름, 파일, 컬럼, 단위) 단위: won(원, 변화 원) / idx(변화 %) / usd(달러, 변화 %) / pt(변화 포인트)
MACRO = [
    ("usdkrw", "원/달러 환율", "kr_extra.csv", "usdkrw", "won"),
    ("dxy", "달러인덱스", "us_equity.csv", "dxy", "idx"),
    ("wti", "WTI 유가", "us_equity.csv", "wti", "usd"),
    ("vix", "VIX (공포지수)", "us_equity.csv", "vix", "pt"),
]
BIG_MOVE = 2.0   # 주가지수 하루 ±2% 이상이면 '큰 움직임'


def _load(fname, col):
    p = D("data", fname)
    if not os.path.exists(p):
        return pd.Series(dtype=float)
    df = pd.read_csv(p, parse_dates=["date"]).set_index("date").sort_index()
    return df[col].dropna() if col in df.columns else pd.Series(dtype=float)


def _ret(s, back_date=None, back_n=None):
    if back_n is not None:
        if len(s) <= back_n:
            return float("nan")
        base = s.iloc[-1 - back_n]
    else:
        prev = s[s.index <= back_date]
        if prev.empty:
            return float("nan")
        base = prev.iloc[-1]
    return (s.iloc[-1] / base - 1) * 100


def stats(s: pd.Series) -> dict:
    last, prev = float(s.iloc[-1]), float(s.iloc[-2])
    t = s.index[-1]
    y = s[s.index > t - pd.Timedelta(days=365)]
    hi, lo = float(y.max()), float(y.min())
    m1_base = float(s.iloc[-22]) if len(s) > 21 else float("nan")
    return {
        "date": t.strftime("%Y-%m-%d"), "last": last, "prev": prev, "d1": (last / prev - 1) * 100,
        "w1": _ret(s, back_n=5), "m1": _ret(s, back_n=21), "m1_abs": last - m1_base,
        "ytd": _ret(s, back_date=pd.Timestamp(t.year - 1, 12, 31)),
        "y1": _ret(s, back_date=t - pd.Timedelta(days=365)),
        "hi": hi, "lo": lo, "from_hi": (last / hi - 1) * 100,
        "pos": 100 * (last - lo) / (hi - lo) if hi > lo else 50.0,
        "ma20": float(s.iloc[-20:].mean()), "ma60": float(s.iloc[-60:].mean()),
    }


# ---------------------------------------------------------------------------
# 규칙 기반 한 줄 해석
# ---------------------------------------------------------------------------
def comment_index(st: dict) -> str:
    parts = []
    if st["d1"] >= BIG_MOVE:
        parts.append(f"하루 {st['d1']:+.2f}% 큰 상승")
    elif st["d1"] <= -BIG_MOVE:
        parts.append(f"하루 {st['d1']:+.2f}% 큰 하락")
    a20, a60 = st["last"] > st["ma20"], st["last"] > st["ma60"]
    parts.append("20일·60일 이동평균 위 → 상승 추세" if a20 and a60 else
                 "20일·60일 이동평균 아래 → 하락 추세" if not a20 and not a60 else
                 "20일선 아래·60일선 위 → 중기 상승 속 단기 조정" if a60 else
                 "20일선 위·60일선 아래 → 하락 추세 속 단기 반등")
    if st["pos"] >= 90:
        parts.append("52주 최고가 근처")
    elif st["pos"] <= 10:
        parts.append("52주 최저가 근처")
    elif st["from_hi"] <= -20:
        parts.append(f"52주 최고가 대비 {st['from_hi']:.1f}% (약세장 기준선 −20% 아래)")
    elif st["from_hi"] <= -10:
        parts.append(f"52주 최고가 대비 {st['from_hi']:.1f}% (조정 국면 기준선 −10% 아래)")
    return " · ".join(parts)


def comment_macro(key: str, st: dict) -> str:
    pos = st["pos"]
    zone = " · 1년 고점권" if pos >= 90 else (" · 1년 저점권" if pos <= 10 else "")
    if key == "usdkrw":
        d = st["m1_abs"]
        return (f"1개월 {d:+,.1f}원 → " + ("원화 약세: 외국인 자금 유출 압력, 달러 조달·외화부채 비용 부담" if d > 0 else
                                            "원화 강세: 외국인 자금 유입에 우호적") + zone)
    if key == "dxy":
        return (f"1개월 {st['m1']:+.2f}% → " + ("글로벌 달러 강세: 신흥국 통화·위험자산에 부담" if st["m1"] > 0 else
                                               "글로벌 달러 약세: 신흥국 자금 유입에 우호적") + zone)
    if key == "wti":
        return (f"1개월 {st['m1']:+.2f}% → " + ("유가 상승: 기대인플레이션(BEI)·장기금리 상승 요인" if st["m1"] > 0 else
                                               "유가 하락: 물가 부담 완화 요인") + zone)
    if key == "vix":
        v = st["last"]
        return ("20 미만 '안정' 구간" if v < 20 else "20~30 '경계' 구간" if v < 30 else "30 이상 '공포' 구간") + \
               f" · 1개월 {st['m1_abs']:+.1f}pt"
    return ""


def flow_stats(s: pd.Series) -> dict:
    last = float(s.iloc[-1])
    sign = 1 if last > 0 else -1
    streak = 0
    for v in reversed(s.tolist()):
        if (v > 0 and sign > 0) or (v < 0 and sign < 0):
            streak += 1
        else:
            break
    return {"date": s.index[-1].strftime("%Y-%m-%d"), "last": last, "sum5": float(s.iloc[-5:].sum()),
            "sum20": float(s.iloc[-20:].sum()), "streak": streak, "sign": sign}


def comment_flow(fs: dict) -> str:
    side = "순매수" if fs["sign"] > 0 else "순매도"
    s20 = fs["sum20"]
    trend = ("최근 한 달 외국인 순매수 우위 → 국내 증시·원화에 우호적" if s20 > 0 else
             "최근 한 달 외국인 순매도 우위 → 한미 금리차·환율과 함께 자금 유출 여부 점검")
    return f"{fs['streak']}거래일 연속 {side} · {trend}"


# ---------------------------------------------------------------------------
# HTML
# ---------------------------------------------------------------------------
CSS = """
  :root { --bg:#0f1419; --card:#1a2028; --line:#2a323d; --fg:#e6e9ee; --muted:#8b95a3; --up:#ff6b6b; --down:#4dabf7; --accent:#4dabf7; }
  * { box-sizing:border-box; }
  body { margin:0; font-family:-apple-system,"Apple SD Gothic Neo","Malgun Gothic",sans-serif; background:var(--bg); color:var(--fg); }
  a { color:var(--accent); text-decoration:none; }
  .wrap { max-width:1100px; margin:0 auto; padding:24px 16px 56px; }
  h1 { font-size:22px; margin:0 0 4px; }
  h2 { font-size:17px; margin:28px 0 12px; }
  .sub { color:var(--muted); font-size:13px; margin-bottom:16px; line-height:1.6; }
  .summary { background:var(--card); border:1px solid var(--line); border-radius:12px; padding:14px 16px; margin-bottom:8px;
             display:flex; flex-wrap:wrap; gap:8px 22px; font-size:15px; font-weight:700; font-variant-numeric:tabular-nums; }
  .grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(300px,1fr)); gap:14px; }
  .card { background:var(--card); border:1px solid var(--line); border-radius:12px; padding:16px; }
  .name { font-size:15px; font-weight:700; } .date { color:var(--muted); font-size:12px; margin-left:6px; font-weight:400; }
  .val { font-size:28px; font-weight:800; margin:6px 0 0; font-variant-numeric:tabular-nums; }
  .chg { font-size:14px; font-weight:700; font-variant-numeric:tabular-nums; }
  .up { color:var(--up); } .down { color:var(--down); } .flat { color:var(--muted); }
  table { width:100%; border-collapse:collapse; margin:12px 0 4px; font-size:13px; font-variant-numeric:tabular-nums; }
  th { color:var(--muted); font-weight:400; text-align:center; padding:4px 0; }
  td { text-align:center; padding:4px 0; font-weight:700; }
  .range { margin-top:10px; font-size:12px; color:var(--muted); }
  .bar { height:6px; background:var(--line); border-radius:3px; margin:6px 0 2px; position:relative; }
  .bar i { position:absolute; top:-3px; width:4px; height:12px; border-radius:2px; background:var(--fg); }
  .ends { display:flex; justify-content:space-between; font-size:11px; color:var(--muted); font-variant-numeric:tabular-nums; }
  .cm { margin-top:10px; font-size:13px; line-height:1.55; background:#141a21; border-radius:8px; padding:8px 10px; }
  .chartbox { position:relative; height:160px; margin-top:10px; }
  .ranges { display:flex; gap:6px; margin:12px 0 0; }
  .ranges button { background:var(--card); color:var(--fg); border:1px solid var(--line); border-radius:8px; padding:6px 12px; cursor:pointer; font-size:13px; }
  .ranges button.on { background:var(--accent); border-color:var(--accent); color:#0b1015; font-weight:700; }
  .foot { color:var(--muted); font-size:12px; margin-top:24px; line-height:1.7; }
"""


def _cls(x):
    return "up" if x > 0.005 else ("down" if x < -0.005 else "flat")


def _arrow(x):
    return "▲" if x > 0.005 else ("▼" if x < -0.005 else "–")


def _pc(x):
    return "n/a" if x is None or math.isnan(x) else f"{x:+.2f}%"


def _eok(x):
    """억원 → 읽기 쉬운 표기 (1조 = 10,000억)."""
    a = abs(x)
    s = f"{a / 10000:,.2f}조" if a >= 10000 else f"{a:,.0f}억"
    return ("+" if x > 0 else "−" if x < 0 else "") + s


def _range_bar(st, fmt):
    return (f'<div class="range">52주 범위 안 위치 · 최고 대비 {_pc(st["from_hi"])}</div>'
            f'<div class="bar"><i style="left:calc({st["pos"]:.0f}% - 2px)"></i></div>'
            f'<div class="ends"><span>최저 {fmt(st["lo"])}</span><span>최고 {fmt(st["hi"])}</span></div>')


def build(built: str = None):
    built = built or dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).strftime("%Y-%m-%d %H:%M KST")
    summary, idx_cards, flow_cards, macro_cards, charts = [], [], [], [], {}

    def keep(key, name, s, kind):
        t = s.iloc[-260:]
        charts[key] = {"name": name, "kind": kind, "date": t.index.strftime("%Y-%m-%d").tolist(),
                       "v": [round(float(x), 4) for x in t],
                       "ma20": [None if pd.isna(x) else round(float(x), 4) for x in s.rolling(20).mean().iloc[-260:]]}

    # 1) 주가지수
    for key, name, fname, col, flag in INDEXES:
        s = _load(fname, col)
        if len(s) < 60:
            continue
        st = stats(s)
        summary.append(f'<span>{flag} {name} <span class="{_cls(st["d1"])}">{_arrow(st["d1"])} {abs(st["d1"]):.2f}%</span></span>')
        rets = "".join(f'<td class="{_cls(v)}">{_pc(v)}</td>' for v in (st["w1"], st["m1"], st["ytd"], st["y1"]))
        idx_cards.append(f"""<div class="card">
  <div class="name">{flag} {name}<span class="date">{st['date']} 기준</span></div>
  <div class="val">{st['last']:,.2f}</div>
  <div class="chg {_cls(st['d1'])}">{_arrow(st['d1'])} {abs(st['last'] - st['prev']):,.2f} ({_pc(st['d1'])}) 전일 대비</div>
  <table><tr><th>1주</th><th>1개월</th><th>연초 대비</th><th>1년</th></tr><tr>{rets}</tr></table>
  {_range_bar(st, lambda v: f"{v:,.2f}")}
  <div class="cm">{comment_index(st)}</div>
  <div class="chartbox"><canvas id="c_{key}"></canvas></div></div>""")
        keep(key, name, s, "line")

    # 2) 외국인 수급
    for key, name, fname, col in FLOWS:
        s = _load(fname, col)
        if len(s) < 20:
            continue
        fs = flow_stats(s)
        flow_cards.append(f"""<div class="card">
  <div class="name">🌐 {name}<span class="date">{fs['date']} 기준</span></div>
  <div class="val {_cls(fs['last'])}">{_eok(fs['last'])}</div>
  <div class="chg flat">하루 순매수 금액 (억원 단위 원자료)</div>
  <table><tr><th>최근 5일 누적</th><th>최근 20일 누적</th><th>연속</th></tr>
    <tr><td class="{_cls(fs['sum5'])}">{_eok(fs['sum5'])}</td><td class="{_cls(fs['sum20'])}">{_eok(fs['sum20'])}</td>
        <td class="{_cls(fs['sign'])}">{fs['streak']}일 {'순매수' if fs['sign'] > 0 else '순매도'}</td></tr></table>
  <div class="cm">{comment_flow(fs)}</div>
  <div class="chartbox"><canvas id="c_{key}"></canvas></div></div>""")
        keep(key, name, s, "bar")

    # 3) 환율·달러·원자재·변동성
    fmts = {"won": lambda v: f"{v:,.1f}원", "idx": lambda v: f"{v:,.2f}", "usd": lambda v: f"${v:,.2f}", "pt": lambda v: f"{v:.2f}"}
    for key, name, fname, col, unit in MACRO:
        s = _load(fname, col)
        if len(s) < 60:
            continue
        st = stats(s)
        f = fmts[unit]
        diff = st["last"] - st["prev"]
        chg = (f"{abs(diff):,.1f}원 ({_pc(st['d1'])})" if unit == "won" else
               f"{abs(diff):.2f}pt" if unit == "pt" else _pc(st["d1"]).lstrip("+-"))
        if key == "usdkrw":
            summary.append(f'<span>💱 원/달러 {st["last"]:,.1f} <span class="{_cls(diff)}">{_arrow(diff)} {abs(diff):,.1f}</span></span>')
        macro_cards.append(f"""<div class="card">
  <div class="name">{name}<span class="date">{st['date']} 기준</span></div>
  <div class="val">{f(st['last'])}</div>
  <div class="chg {_cls(diff)}">{_arrow(diff)} {chg} 전일 대비</div>
  {_range_bar(st, f)}
  <div class="cm">{comment_macro(key, st)}</div>
  <div class="chartbox"><canvas id="c_{key}"></canvas></div></div>""")
        keep(key, name, s, "line")

    html = f"""<!DOCTYPE html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>증시 한눈에</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<style>{CSS}</style></head>
<body><div class="wrap">
  <h1>📈 증시 한눈에</h1>
  <div class="sub">주가지수 · 외국인 수급 · 환율·달러 · 유가·변동성 · 페이지 생성 {built}<br>
    <a href="index.html">🇰🇷 한국 대시보드</a> · <a href="us.html">🇺🇸 미국 대시보드</a> · <a href="daily.html">🧭 오늘의 해석</a></div>
  <div class="summary">{''.join(summary) or '데이터 준비 중'}</div>
  <div class="ranges" id="ranges"><button data-d="66" class="on">3개월</button><button data-d="130">6개월</button><button data-d="260">1년</button></div>
  <h2>주가지수</h2><div class="grid">{''.join(idx_cards)}</div>
  <h2>외국인 수급</h2><div class="grid">{''.join(flow_cards) or '<div class="sub">데이터 준비 중</div>'}</div>
  <h2>환율 · 달러 · 유가 · 변동성</h2><div class="grid">{''.join(macro_cards)}</div>
  <div class="foot">
    <b>출처</b> · 한국은행 ECOS: 코스피·코스닥, 외국인 순매수(유가증권·코스닥), 원/달러 매매기준율 ·
    FRED: 나스닥(NASDAQCOM), S&P 500(SP500), 니케이 225(NIKKEI225), WTI(DCOILWTICO), 달러인덱스(DTWEXBGS, 연준 광의 무역가중), VIX(VIXCLS).
    모두 하루 이상 늦게 공표돼 카드마다 기준일을 표시해요(달러인덱스는 보통 일주일 정도 늦어요). 실시간 시세가 아니에요.<br>
    <b>읽는 법</b> · 빨강 = 상승·순매수, 파랑 = 하락·순매도 · 점선 = 20일 이동평균 ·
    주가지수 해석: 하루 ±{BIG_MOVE:.0f}% 이상 큰 움직임, 20일·60일 이동평균으로 추세, 52주 최고가 대비 −10% 조정·−20% 약세장 기준선 ·
    외국인 수급: 연속 순매수·순매도 일수, 20일 누적 방향 · VIX: 20 미만 안정, 20~30 경계, 30 이상 공포.<br>
    개인 학습용이며 투자 권유가 아닙니다.
  </div>
</div>
<script>
const S = {json.dumps(charts, ensure_ascii=False)};
Chart.defaults.color = "#8b95a3"; Chart.defaults.borderColor = "#2a323d"; Chart.defaults.font.size = 11;
let range = 66; const charts = [];
function draw() {{
  charts.forEach(c => c.destroy()); charts.length = 0;
  for (const [k, d] of Object.entries(S)) {{
    const el = document.getElementById("c_" + k); if (!el) continue;
    const s = Math.max(0, d.date.length - range), v = d.v.slice(s);
    let ds;
    if (d.kind === "bar") {{
      ds = [{{ type: "bar", label: d.name, data: v, backgroundColor: v.map(x => x >= 0 ? "#ff6b6b" : "#4dabf7") }}];
    }} else {{
      const col = v.at(-1) >= v[0] ? "#ff6b6b" : "#4dabf7";
      ds = [{{ label: d.name, data: v, borderColor: col, backgroundColor: col, borderWidth: 2, tension: .15,
               pointRadius: v.map((_, j) => j === v.length - 1 ? 3 : 0) }},
            {{ label: "20일 이동평균", data: d.ma20.slice(s), borderColor: "#8b95a3", borderDash: [4, 4], borderWidth: 1, pointRadius: 0 }}];
    }}
    charts.push(new Chart(el, {{ type: d.kind === "bar" ? "bar" : "line",
      data: {{ labels: d.date.slice(s), datasets: ds }},
      options: {{ responsive: true, maintainAspectRatio: false, interaction: {{ mode: "index", intersect: false }},
        plugins: {{ legend: {{ display: false }} }}, scales: {{ x: {{ ticks: {{ maxTicksLimit: 4 }} }} }} }} }}));
  }}
}}
document.querySelectorAll("#ranges button").forEach(b => b.onclick = () => {{
  document.querySelectorAll("#ranges button").forEach(x => x.classList.remove("on")); b.classList.add("on"); range = +b.dataset.d; draw(); }});
draw();
</script>
</body></html>"""
    os.makedirs(D("docs"), exist_ok=True)
    with open(D("docs", "markets.html"), "w", encoding="utf-8") as f:
        f.write(html)
    print(f"증시 페이지 생성: docs/markets.html (지수 {len(idx_cards)} · 수급 {len(flow_cards)} · 기타 {len(macro_cards)})")


if __name__ == "__main__":
    build()
