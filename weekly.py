"""
🗓️ 주간 요약 → docs/weekly.html

  - 주(월~금) 단위: 그 주 마지막 영업일 값 − 전주 마지막 영업일 값
  - 주간 커브 국면: 주간 국고 3·10년 변화로 R1~R5 판정
  - 그 주에 걸린 규칙 신호 횟수 (일별 해석을 다시 돌려 집계)
  - 기관 신호등: 주말 기준 vs 전주 말 기준
  - 리포트 초안: 이번 주를 4~5문장으로 (FIV 위클리 초안용)
"""
import math
import os

import pandas as pd

import institutions
import interpret

WEEKS = 12
ROWS = [  # (컬럼, 이름, 단위)
    ("ktb3", "국고 3년", "%"), ("ktb10", "국고 10년", "%"), ("ktb30", "국고 30년", "%"),
    ("term_spread_bp", "10Y−3Y", "bp"), ("msb1_policy_bp", "통안 1년 − 기준금리", "bp"),
    ("corp_spread_bp", "회사채 AA− 스프레드", "bp"), ("yeojeon_aa", "여전채 AA− 3년", "%"),
    ("yeojeon_spread_bp", "여전채 스프레드", "bp"), ("yeojeon_bank_bp", "여전채 − 은행채", "bp"),
    ("corp_a_spread_bp", "A− 스프레드", "bp"), ("bank_spread_bp", "은행채 스프레드", "bp"),
    ("cp_cd_spread_bp", "CP − CD", "bp"), ("kospi", "코스피", "idx"), ("kosdaq", "코스닥", "idx"),
]


def _chg(a, b, unit):
    if pd.isna(a) or pd.isna(b):
        return float("nan")
    return (b / a - 1) * 100 if unit == "idx" else (b - a) * (100 if unit == "%" else 1)


def _f(x, unit):
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "-"
    u = "%" if unit == "idx" else "bp"
    return f"{x:+.{2 if unit == 'idx' else 1}f}{u}"


def _lv(x, unit):
    if pd.isna(x):
        return "-"
    return f"{x:,.2f}" if unit == "idx" else f"{x:.3f}%" if unit == "%" else f"{x:.1f}bp"


def weeks(df: pd.DataFrame):
    df = df.sort_index()
    ends = df.groupby(df.index.to_period("W-FRI")).apply(lambda g: g.index.max()).tolist()
    return ends[-(WEEKS + 1):]


def build(df: pd.DataFrame):
    df = df.sort_index()
    ends = weeks(df)
    out = []
    for prev, end in zip(ends[:-1], ends[1:]):
        a, b = df.ffill().loc[prev], df.ffill().loc[end]
        chg = {c: _chg(a.get(c), b.get(c), u) for c, _, u in ROWS if c in df.columns}
        reg, _ = interpret.curve_regime(chg.get("ktb3", float("nan")), chg.get("ktb10", float("nan")))
        days = df.loc[(df.index > prev) & (df.index <= end)].index
        sig = {}
        for d in days:
            r = interpret.interpret_day(interpret.Day(df, df.index.get_loc(d)))
            for tag, _, _ in r["signals"]:
                sig[tag] = sig.get(tag, 0) + 1
        out.append({"start": days.min() if len(days) else end, "end": end, "chg": chg, "lvl": b,
                    "regime": reg, "signals": sig, "inst": institutions.evaluate(df.loc[:end])})
    return out


def draft(w, prev_inst):
    c = w["chg"]
    s = [f"이번 주({w['start']:%m/%d}~{w['end']:%m/%d}) 국고 3년은 {_f(c.get('ktb3'), '%')}, "
         f"10년은 {_f(c.get('ktb10'), '%')} 움직여 커브는 {w['regime'] or '보합'} 흐름이었다."]
    if "msb1_policy_bp" in c and not pd.isna(w["lvl"].get("msb1_policy_bp", float("nan"))):
        lv = w["lvl"]["msb1_policy_bp"]
        s.append(f"통안 1년은 기준금리 대비 {lv:+.0f}bp로 시장은 "
                 + ("인하" if lv <= -15 else "인상" if lv >= 15 else "동결") + " 쪽을 반영하고 있다.")
    cr = [(n, c.get(k)) for k, n, _ in ROWS if k in ("corp_spread_bp", "yeojeon_spread_bp", "corp_a_spread_bp") and not pd.isna(c.get(k, float("nan")))]
    if cr:
        s.append("크레딧 스프레드는 " + ", ".join(f"{n} {_f(v, 'bp')}" for n, v in cr) + "로 "
                 + ("확대되며 신용 경계가 커졌다." if sum(v for _, v in cr) > 3 else
                    "축소되며 크레딧 선호가 이어졌다." if sum(v for _, v in cr) < -3 else "큰 변화가 없었다."))
    if "cp_cd_spread_bp" in c:
        s.append(f"단기자금시장 지표인 CP−CD는 {_lv(w['lvl'].get('cp_cd_spread_bp'), 'bp')}({_f(c['cp_cd_spread_bp'], 'bp')})였다.")
    if "kospi" in c and not pd.isna(c["kospi"]):
        s.append(f"코스피는 주간 {_f(c['kospi'], 'idx')}였다.")
    moved = [f"{institutions.SPEC[k]['title'].split(' ')[-1]} {prev_inst[k][0]}→{v[0]}"
             for k, v in w["inst"].items() if prev_inst and prev_inst[k][0] != v[0]]
    if moved:
        s.append("기관별 신호등은 " + ", ".join(moved) + "으로 바뀌었다.")
    return " ".join(s)


def render(df: pd.DataFrame, built: str) -> str:
    ws = build(df)
    if not ws:
        return "<p>데이터 부족</p>"
    cur, prev = ws[-1], (ws[-2] if len(ws) > 1 else None)
    cols = [(c, n, u) for c, n, u in ROWS if c in df.columns]
    trs = "".join(
        f"<tr><td>{n}</td><td>{_lv(cur['lvl'].get(c), u)}</td>"
        + "".join(f"<td class='{'up' if (w['chg'].get(c) or 0) > 0 else 'down' if (w['chg'].get(c) or 0) < 0 else ''}'>{_f(w['chg'].get(c), u)}</td>"
                  for w in ws[::-1][:4]) + "</tr>"
        for c, n, u in cols)
    th = "".join(f"<th>{w['end']:%m/%d} 주</th>" for w in ws[::-1][:4])
    inst_now = "".join(
        f"<td>{(prev['inst'][k][0] + '→') if prev and prev['inst'][k][0] != v[0] else ''}{v[0]} {v[2]:+d}</td>"
        for k, v in cur["inst"].items())
    sig_txt = ", ".join(f"{k} {v}회" for k, v in sorted(cur["signals"].items(), key=lambda x: (-x[1], x[0]))) or "없음"
    hist = "".join(
        f"<tr><td>{w['start']:%m/%d}~{w['end']:%m/%d}</td><td>{w['regime'] or '보합'}</td>"
        f"<td>{_f(w['chg'].get('ktb3'), '%')}</td><td>{_f(w['chg'].get('ktb10'), '%')}</td>"
        f"<td>{_f(w['chg'].get('corp_spread_bp'), 'bp')}</td><td>{_f(w['chg'].get('kospi'), 'idx')}</td>"
        f"<td>{''.join(v[0] for v in w['inst'].values())}</td><td>{sum(w['signals'].values())}</td></tr>"
        for w in ws[::-1])
    text = draft(cur, prev["inst"] if prev else None)
    return f"""<!DOCTYPE html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>주간 요약 · Rates & Spreads Dashboard</title>
<style>{interpret.CSS}{institutions.CSS}
  .up {{ color:#ff6b6b; }} .down {{ color:#4dabf7; }}
  td, th {{ white-space:nowrap; }}
</style></head>
<body><div class="wrap">
  <div><a href="index.html">← 대시보드</a> · <a href="daily.html">🧭 오늘의 해석</a> · <a href="calc.html">🧮 캐리 계산기</a></div>
  <h1>🗓️ 주간 요약</h1>
  <div class="sub">이번 주 {cur['start']:%Y-%m-%d} ~ {cur['end']:%Y-%m-%d} · 페이지 생성 {built} · 금요일 전에는 '지금까지'의 주간 변화예요.</div>

  <h2>📝 리포트 초안</h2>
  <div class="card"><div id="draft" style="line-height:1.8">{text}</div>
    <button onclick="navigator.clipboard.writeText(document.getElementById('draft').innerText).then(()=>this.textContent='복사됨 ✓')"
      style="margin-top:10px;background:#1f2731;color:#e6e9ee;border:1px solid #2a323d;border-radius:8px;padding:6px 12px;cursor:pointer">초안 복사</button>
    <div class="as">숫자와 규칙으로 만든 뼈대예요. 원인(금통위·미국 지표·수급 뉴스)과 본인 의견을 덧붙여 완성하세요.</div></div>

  <h2>📊 주간 변화 (최근 4주)</h2>
  <div class="card" style="overflow-x:auto"><table><tr><th>지표</th><th>이번 주 수준</th>{th}</tr>{trs}</table>
    <div class="as">금리는 bp, 주가는 % 변화. 각 주의 마지막 영업일과 전주 마지막 영업일 비교.</div></div>

  <h2>🏢 이번 주 기관 신호등 · 신호</h2>
  <div class="card"><table><tr><th>캐피탈</th><th>보험</th><th>은행</th></tr><tr>{inst_now}</tr></table>
    <div style="margin-top:8px;font-size:13px">이번 주 걸린 규칙: {sig_txt}</div></div>

  <h2>🗂️ 최근 {len(ws)}주</h2>
  <div class="card" style="overflow-x:auto"><table>
    <tr><th>주간</th><th>커브 국면</th><th>국고 3년</th><th>국고 10년</th><th>회사채 스프레드</th><th>코스피</th><th>신호등(캐·보·은)</th><th>신호 수</th></tr>{hist}</table></div>
  <p class="muted">개인 학습용 자동 요약이며 투자 권유가 아닙니다.</p>
</div></body></html>"""


def write(docs: str, df: pd.DataFrame, built: str):
    with open(os.path.join(docs, "weekly.html"), "w", encoding="utf-8") as f:
        f.write(render(df, built))
