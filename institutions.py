"""
금융기관별 브리핑 (캐피탈 · 보험 · 은행) + 해석 로직 페이지(docs/logic.html)

구조
  1) 항목별 점수: 우호 +1 / 중립 0 / 부담 −1   (방향 = 5영업일 누적 변화, 수준 = 1년 중 위치 0~100)
  2) 신호등: 합계 ≥ +2 🟢 우호, ≤ −2 🔴 부담, 그 사이 🟡 중립
  3) 체크포인트: 카드 지표 중 '전일 변화 ÷ 1년 일간 변화 표준편차'가 가장 큰 것

문장 태그: 사실(공표 데이터·단순 계산) / 근사(이론 공식으로 추정) / 해석(시장의 표준적 읽기)
아래 상수만 고치면 카드 계산과 로직 페이지 설명이 함께 바뀜.
"""
import math
import os

import pandas as pd

ROOT = os.path.dirname(__file__)

# ---------------------------------------------------------------------------
# 설정값 (가정·문턱값)
# ---------------------------------------------------------------------------
INS_DURATION = 15      # 보험 자산 듀레이션 가정(년) — 평가손익 근사용
WIN = 260              # 1년 ≈ 260영업일
N5 = 5                 # 방향 판단 기간(영업일)
GREEN, RED = 2, -2     # 신호등 합계 기준

# 항목 정의: (ID, 이름, 판단 방식, 우호 조건, 부담 조건, 태그, 근거·가정)
#   방식 'd5'  : 5영업일 누적 변화(bp 또는 %)로 판단
#   방식 'pos' : 1년 중 위치(0~100)로 판단
SPEC = {
    "capital": {
        "title": "🏦 캐피탈", "q": "싸고 안정적으로 조달할 수 있는가",
        "items": [
            ("C1", "조달금리 방향 (여전채 AA− 3년, 5일 변화)", "d5", "≤ −3bp", "≥ +3bp", "사실",
             "캐피탈사는 예금이 없어 여전채가 조달 원가의 기준이에요."),
            ("C2", "업권 신용 평가 (여전채 AA− 스프레드, 1년 위치)", "pos", "≤ 20", "≥ 80", "사실·해석",
             "국고 대비 가산금리가 높을수록 시장이 업권을 더 위험하게 본다는 뜻이에요 (신용위험 프리미엄)."),
            ("C3", "단기 차환 여건 (CP−CD, 1년 위치)", "pos", "≤ 20", "≥ 80", "사실·해석",
             "CP는 캐피탈·PF 유동화의 단기 조달 수단이에요. 은행 대비 가산금리가 높으면 차환 부담이 커요."),
            ("C4", "중소형사 차별화 (여전채 A+ − AA−, 5일 변화)", "d5", "≤ −2bp", "≥ +2bp", "사실·해석",
             "민평 등급 간격은 평가사가 천천히 조정해 잘 안 움직여서 문턱값을 작게 잡았어요."),
            ("C5", "시장 기준 대출 마진 여력 (A− 회사채 − 여전채 AA−, 1년 위치)", "pos", "≥ 80", "≤ 20", "근사",
             "대출 가격 = 조달비용 + 차주 신용스프레드라는 가격결정 논리로 만든 시장 기준 근사예요. 실제 대출금리가 아니에요."),
        ],
        "assume": ["조달금리는 여전채 AA− 3년으로 대표 (회사별 등급·만기 구성·CP 비중은 다름)",
                   "마진 여력은 A− 회사채 금리로 대출금리를 근사한 값 (실제 대출은 차주·담보·만기별 협상)"],
    },
    "insurance": {
        "title": "🛡️ 보험", "q": "장기로 높은 금리에 운용할 수 있는가",
        "items": [
            ("I1", "신규 투자수익률 (국고 30년, 1년 위치)", "pos", "≥ 70", "≤ 30", "사실·해석",
             "금리가 높을 때 사야 장기 부채를 만족시키는 운용수익을 확보하기 쉬워요."),
            ("I2", f"자산 측 평가손익 근사 (−{INS_DURATION}년 × 국고 30년 5일 변화)", "d5", "30년물 ≤ −3bp (평가이익)",
             "30년물 ≥ +3bp (평가손실)", "근사",
             "수정듀레이션 근사(ΔP/P ≈ −D·Δy). 볼록성 무시. 부채도 함께 재평가돼(IFRS17·K-ICS) 실제 순효과는 자산·부채 듀레이션 차이에 달려 있어요."),
            ("I3", "초장기물 가격 부담 (30Y−10Y, 1년 위치)", "pos", "≥ 80", "≤ 20", "사실·해석",
             "30년물이 10년물보다 상대적으로 낮으면(스프레드 축소·역전) 초장기물을 비싸게 사야 해요."),
            ("I4", "해외채 헤지 매력 (환헤지 비용 근사, 1년 위치)", "pos", "≤ 20", "≥ 80", "근사",
             "커버드 금리평가(CIP): 헤지 비용 ≈ 미 3개월 − 한국 CD 91일. 외환스왑 베이시스·헤지 만기는 무시했어요."),
        ],
        "assume": [f"자산 듀레이션 {INS_DURATION}년 가정 (회사마다 다름)",
                   "평가손익은 자산 측만 계산 — 부채 재평가에 따른 상쇄 효과는 반영하지 않음",
                   "신규 투자수익률은 국고 30년으로 대표 (실제는 회사채·대체투자 혼합)",
                   "환헤지 비용은 단기 금리차 근사 (미국 값은 공표된 최근 값)"],
    },
    "bank": {
        "title": "🏛️ 은행", "q": "이자 수익 환경과 기업여신 건전성은 어떤가",
        "items": [
            ("B1", "예대 마진 환경 참고 (국고 10Y−3Y, 1년 위치)", "pos", "≥ 70", "≤ 30", "해석",
             "만기변환 이론의 참고 지표예요. 국내 은행은 변동금리 대출 비중이 커서 NIM과의 연결은 약한 편이에요."),
            ("B2", "변동금리 대출 기준 (CD 91일, 5일 변화)", "d5", "≥ +3bp", "≤ −3bp", "사실·해석",
             "CD 연동 기업대출·변동금리 대출은 금리 상승 시 이자수익이 먼저 늘어나는 구조예요. 차주 부담은 B4·B5에서 따로 봐요."),
            ("B3", "단기 자금시장 (CP−CD, 1년 위치)", "pos", "—", "≥ 80", "사실·해석",
             "단기 자금시장 경색은 은행의 유동성 관리와 기업 자금 수요 변화로 이어져요."),
            ("B4", "기업여신 건전성 (A− 크레딧 스프레드, 1년 위치)", "pos", "≤ 20", "≥ 80", "사실·해석",
             "중견기업급 신용 프리미엄이 높을수록 기업여신의 신용위험이 커지는 환경이에요."),
            ("B5", "차주 신용 선행 (코스피, 5일 변화)", "d5", "—", "≤ −5%", "해석",
             "머튼 모형: 주가 하락은 기업 신용 악화의 선행 신호예요."),
        ],
        "assume": ["장단기 금리차는 NIM이 아닌 '환경 참고 지표' (실제 NIM은 예금·대출금리 차이, 코픽스, 경쟁에 좌우)",
                   "CD는 CD 연동 기업대출·변동금리 대출 기준 (가계 주담대는 코픽스·은행채 연동이 많음)"],
    },
}

TAG_DESC = [
    ("사실", "공표된 데이터 그대로이거나 단순 계산(뺄셈, 누적, 1년 중 위치)"),
    ("근사", "이론 공식으로 추정한 값. 무시한 항목을 함께 적어요"),
    ("해석", "시장에서 통용되는 표준적 읽기. 그날의 원인을 확인한 사실은 아니에요"),
]


# ---------------------------------------------------------------------------
# 계산 도우미
# ---------------------------------------------------------------------------
def _s(df, c):
    return df[c].dropna() if c in df.columns else pd.Series(dtype=float)


def _pos(s):
    w = s.iloc[-WIN:]
    return float("nan") if len(w) < 20 else round(100 * (w < w.iloc[-1]).sum() / (len(w) - 1))


def _d5(s, mult=100.0, pct=False):
    if len(s) <= N5:
        return float("nan")
    a, b = s.iloc[-1 - N5], s.iloc[-1]
    return (b / a - 1) * 100 if pct else (b - a) * mult


def _z(s, mult=100.0, pct=False):
    """오늘 변화 ÷ 1년 일간 변화 표준편차 (체크포인트용)."""
    if len(s) < 30:
        return float("nan"), float("nan")
    ch = (s.pct_change() * 100 if pct else s.diff() * mult).dropna().iloc[-WIN:]
    sd = ch.std()
    return (abs(ch.iloc[-1]) / sd if sd > 0 else float("nan")), float(ch.iloc[-1])


def _bp(x, unit="bp", nd=1):
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "n/a"
    return ("+" if x > 0 else "−" if x < 0 else "±") + f"{abs(x):.{nd}f}{unit}"


def _sc_pos(p, good_hi, hi=80, lo=20):
    """1년 위치 점수. good_hi=True면 높을수록 우호."""
    if math.isnan(p):
        return 0
    if p >= hi:
        return 1 if good_hi else -1
    if p <= lo:
        return -1 if good_hi else 1
    return 0


def _sc_d5(x, th, good_up):
    if math.isnan(x) or abs(x) < th:
        return 0
    return (1 if x > 0 else -1) * (1 if good_up else -1)


def _date(s):
    return s.index[-1].strftime("%m/%d") if len(s) else "-"


def _hedge(df):
    """환헤지 비용 근사 시계열(bp): 미 3개월(공표된 최근 값) − 한국 CD 91일."""
    p = os.path.join(ROOT, "data", "us.csv")
    if not os.path.exists(p) or "cd91" not in df.columns:
        return pd.Series(dtype=float)
    us = pd.read_csv(p, parse_dates=["date"]).set_index("date").sort_index()
    if "ust3m" not in us.columns:
        return pd.Series(dtype=float)
    u = us[["ust3m"]].dropna().copy()
    u.index = u.index + pd.Timedelta(days=1)
    k = df[["cd91"]].dropna().sort_index()
    m = pd.merge_asof(k, u.sort_index(), left_index=True, right_index=True, direction="backward")
    return ((m["ust3m"] - m["cd91"]) * 100).dropna()


# ---------------------------------------------------------------------------
# 기관별 평가
# ---------------------------------------------------------------------------
def _capital(df):
    ye, sp, cpcd = _s(df, "yeojeon_aa"), _s(df, "yeojeon_spread_bp"), _s(df, "cp_cd_spread_bp")
    gr = _s(df, "yeojeon_grade_bp")
    mg = ((df["corp_a_minus"] - df["yeojeon_aa"]) * 100).dropna() if {"corp_a_minus", "yeojeon_aa"} <= set(df.columns) else pd.Series(dtype=float)
    out = []
    if len(ye):
        d = _d5(ye)
        out.append(("C1", _sc_d5(d, 3, good_up=False),
                    f"`사실` 여전채 AA− {ye.iloc[-1]:.3f}% (5일 {_bp(d)}) → `해석` " +
                    ("조달 원가 하락" if d <= -3 else "조달 원가 상승" if d >= 3 else "조달 원가 큰 변화 없음")))
    if len(sp):
        p = _pos(sp)
        out.append(("C2", _sc_pos(p, good_hi=False),
                    f"`사실` 여전채 AA− 스프레드 {sp.iloc[-1]:.1f}bp, 1년 위치 {p:.0f} → `해석` " +
                    ("시장이 업권 신용을 경계하는 구간" if p >= 80 else "업권 신용 평가 양호한 구간" if p <= 20 else "업권 신용 평가 평균 수준")))
    if len(cpcd):
        p = _pos(cpcd)
        out.append(("C3", _sc_pos(p, good_hi=False),
                    f"`사실` CP−CD {cpcd.iloc[-1]:.0f}bp, 1년 위치 {p:.0f} → `해석` " +
                    ("단기 차환 부담 큰 구간" if p >= 80 else "단기 차환 여건 양호" if p <= 20 else "단기 차환 여건 평균 수준")))
    if len(gr):
        d = _d5(gr, mult=1.0)
        out.append(("C4", _sc_d5(d, 2, good_up=False),
                    f"`사실` 여전채 A+ − AA− {gr.iloc[-1]:.1f}bp (5일 {_bp(d)}) → `해석` " +
                    ("중소형사 조달 부담 상대적 확대" if d >= 2 else "등급 간 격차 완화" if d <= -2 else "등급 간 격차 유지")))
    if len(mg):
        p = _pos(mg)
        out.append(("C5", _sc_pos(p, good_hi=True),
                    f"`근사` 시장 기준 마진 여력 {mg.iloc[-1]:.0f}bp, 1년 위치 {p:.0f} → `해석` " +
                    ("대출 마진 확보에 유리한 환경" if p >= 80 else "대출 마진 압박 방향" if p <= 20 else "마진 환경 평균 수준")))
    series = {"여전채 AA−": (ye, 100, False), "여전채 스프레드": (sp, 1, False), "CP−CD": (cpcd, 1, False), "A+−AA−": (gr, 1, False)}
    return out, series


def _insurance(df):
    k30, k10, us_ = _s(df, "ktb30"), _s(df, "ktb10"), _s(df, "ultra_spread_bp")
    hg = _hedge(df)
    out = []
    if len(k30):
        p = _pos(k30)
        out.append(("I1", _sc_pos(p, good_hi=True, hi=70, lo=30),
                    f"`사실` 국고 30년 {k30.iloc[-1]:.3f}%, 1년 위치 {p:.0f} → `해석` " +
                    ("신규 장기 투자에 유리한 금리 수준" if p >= 70 else "신규 투자수익률 낮은 구간" if p <= 30 else "신규 투자수익률 평균 수준")))
        d = _d5(k30)
        val = -INS_DURATION * d / 100
        out.append(("I2", _sc_d5(-d, 3, good_up=True),
                    f"`근사` 국고 30년 5일 {_bp(d)} → 자산 측 평가손익 약 {_bp(val, '%', 2)} (듀레이션 {INS_DURATION}년 가정, 부채 재평가로 일부 상쇄)"))
    if len(us_):
        p = _pos(us_)
        out.append(("I3", _sc_pos(p, good_hi=True),
                    f"`사실` 30Y−10Y {us_.iloc[-1]:.1f}bp, 1년 위치 {p:.0f} → `해석` " +
                    ("초장기물 상대적으로 저렴" if p >= 80 else "초장기물 상대적으로 비쌈 (ALM 매입 경쟁)" if p <= 20 else "초장기물 가격 평균 수준")))
    if len(hg) > 20:
        p = _pos(hg)
        out.append(("I4", _sc_pos(p, good_hi=False),
                    f"`근사` 환헤지 비용 약 {hg.iloc[-1]:.0f}bp, 1년 위치 {p:.0f} → `해석` " +
                    ("헤지 후 해외채 매력 낮은 구간" if p >= 80 else "헤지 후 해외채 매력 높은 구간" if p <= 20 else "헤지 비용 평균 수준")))
    series = {"국고 30년": (k30, 100, False), "국고 10년": (k10, 100, False), "30Y−10Y": (us_, 1, False)}
    return out, series


def _bank(df):
    ts, cd, cpcd, asp, ks = (_s(df, c) for c in ["term_spread_bp", "cd91", "cp_cd_spread_bp", "corp_a_spread_bp", "kospi"])
    out = []
    if len(ts):
        p = _pos(ts)
        out.append(("B1", _sc_pos(p, good_hi=True, hi=70, lo=30),
                    f"`사실` 국고 10Y−3Y {ts.iloc[-1]:.1f}bp, 1년 위치 {p:.0f} → `해석` 예대 마진 환경(참고): " +
                    ("우호적" if p >= 70 else "불리한 방향" if p <= 30 else "보통")))
    if len(cd):
        d = _d5(cd)
        out.append(("B2", _sc_d5(d, 3, good_up=True),
                    f"`사실` CD 91일 {cd.iloc[-1]:.2f}% (5일 {_bp(d)}) → `해석` " +
                    ("변동금리 대출 금리 상승 → 이자수익 증가 방향" if d >= 3 else "변동금리 대출 금리 하락 → 이자수익 감소 방향" if d <= -3 else "대출 기준금리 큰 변화 없음")))
    if len(cpcd):
        p = _pos(cpcd)
        out.append(("B3", -1 if p >= 80 else 0,
                    f"`사실` CP−CD {cpcd.iloc[-1]:.0f}bp, 1년 위치 {p:.0f} → `해석` " +
                    ("단기 자금시장 긴장: 유동성 관리 강화 필요" if p >= 80 else "단기 자금시장 안정")))
    if len(asp):
        p = _pos(asp)
        out.append(("B4", _sc_pos(p, good_hi=False),
                    f"`사실` A− 크레딧 스프레드 {asp.iloc[-1]:.1f}bp, 1년 위치 {p:.0f} → `해석` " +
                    ("기업여신 신용위험 경계 구간" if p >= 80 else "기업여신 신용 환경 양호" if p <= 20 else "기업여신 신용 환경 평균 수준")))
    if len(ks) > N5:
        d = _d5(ks, pct=True)
        out.append(("B5", -1 if d <= -5 else 0,
                    f"`사실` 코스피 5일 {_bp(d, '%', 2)} ({_date(ks)} 기준) → `해석` " +
                    ("주가 급락: 차주 신용 악화의 선행 신호 (머튼 모형)" if d <= -5 else "차주 신용 선행 신호 없음")))
    series = {"CD 91일": (cd, 100, False), "10Y−3Y": (ts, 1, False), "A− 스프레드": (asp, 1, False), "코스피": (ks, 1, True)}
    return out, series


def _light(total):
    return ("🟢", "우호") if total >= GREEN else ("🔴", "부담") if total <= RED else ("🟡", "중립")


def _checkpoint(series, ref):
    best = None
    for name, (s, mult, pct) in series.items():
        z, ch = _z(s, mult, pct)
        if not math.isnan(z) and (best is None or z > best[0]):
            best = (z, name, ch, pct, s.index[-1])
    if not best:
        return "데이터 부족"
    z, name, ch, pct, d = best
    when = "" if d == ref else f" ({d:%m/%d} 기준, 데이터 공표 지연)"
    return f"{name} 전일 대비 {_bp(ch, '%' if pct else 'bp', 2 if pct else 1)}{when} — 평소 하루 변동폭의 {z:.1f}배"


def _md(text):
    """`태그` → 배지 HTML."""
    out = text
    for t, cls in [("사실", "t-f"), ("근사", "t-a"), ("해석", "t-i")]:
        out = out.replace(f"`{t}`", f'<span class="tg {cls}">{t}</span>')
    return out


CSS = """
  .inst { display:grid; grid-template-columns:repeat(auto-fit,minmax(300px,1fr)); gap:12px; }
  .ic { background:var(--card); border:1px solid var(--line); border-radius:12px; padding:14px 16px; }
  .ih { display:flex; justify-content:space-between; align-items:baseline; gap:8px; }
  .ih b { font-size:16px; } .iq { color:var(--muted); font-size:12px; margin:2px 0 8px; }
  .lt { font-size:15px; font-weight:800; white-space:nowrap; }
  .chips { display:flex; flex-wrap:wrap; gap:4px; margin-bottom:8px; }
  .chip { font-size:11px; border:1px solid var(--line); border-radius:999px; padding:1px 8px; color:var(--muted); }
  .chip.p { color:#69db7c; border-color:#2f6b3a; } .chip.n { color:#ff8787; border-color:#7a2f2f; }
  .ic ul { margin:0; padding-left:18px; } .ic li { font-size:13px; margin:5px 0; line-height:1.5; }
  .tg { display:inline-block; font-size:10px; font-weight:700; border-radius:4px; padding:0 5px; margin-right:4px; color:#0b1015; }
  .t-f { background:#69db7c; } .t-a { background:#ffd43b; } .t-i { background:#74c0fc; }
  .cp { margin-top:8px; font-size:13px; background:#141a21; border-radius:8px; padding:6px 10px; }
  .as { margin-top:8px; font-size:11.5px; color:var(--muted); line-height:1.5; }
"""


def section(df: pd.DataFrame) -> str:
    """'오늘의 해석' 페이지에 넣을 기관별 브리핑 HTML."""
    df = df.sort_index()
    html = []
    for key, fn in [("capital", _capital), ("insurance", _insurance), ("bank", _bank)]:
        spec = SPEC[key]
        items, series = fn(df)
        total = sum(sc for _, sc, _ in items)
        icon, word = _light(total)
        chips = "".join(f'<span class="chip {"p" if sc > 0 else "n" if sc < 0 else ""}">{i} {f"{sc:+d}" if sc else "0"}</span>' for i, sc, _ in items)
        lines = "".join(f"<li>{_md(t)}</li>" for _, _, t in items) or "<li>데이터 준비 중</li>"
        html.append(f"""<div class="ic">
  <div class="ih"><b>{spec['title']}</b><span class="lt">{icon} {word} ({total:+d})</span></div>
  <div class="iq">{spec['q']}</div>
  <div class="chips">{chips}</div>
  <ul>{lines}</ul>
  <div class="cp">📍 체크포인트: {_checkpoint(series, df.index.max())}</div>
  <div class="as">이 카드의 가정: {' · '.join(spec['assume'])}</div>
</div>""")
    return (f'<h2 id="inst">🏢 금융기관별 브리핑</h2>'
            f'<div class="muted" style="margin-bottom:10px">점수·신호등·태그의 기준은 <a href="logic.html">🧩 해석 로직 페이지</a>에 모두 공개돼 있어요.</div>'
            f'<div class="inst">{"".join(html)}</div>')


# ---------------------------------------------------------------------------
# 해석 로직 페이지 (docs/logic.html)
# ---------------------------------------------------------------------------
def logic_page(built: str) -> str:
    blocks = []
    for key in ["capital", "insurance", "bank"]:
        sp = SPEC[key]
        rows = "".join(f"<tr><td>{i}</td><td>{n}</td><td>{'5일 변화' if m == 'd5' else '1년 위치'}</td>"
                       f"<td class='g'>{g}</td><td class='r'>{r}</td><td>{t}</td><td class='why'>{w}</td></tr>"
                       for i, n, m, g, r, t, w in sp["items"])
        blocks.append(f"""<h2 id="{key}">{sp['title']} — {sp['q']}</h2>
<div class="tw"><table><tr><th>ID</th><th>항목</th><th>기준</th><th>우호 +1</th><th>부담 −1</th><th>태그</th><th>근거 · 가정</th></tr>{rows}</table></div>
<div class="as"><b>이 카드의 가정</b><ul>{''.join(f'<li>{a}</li>' for a in sp['assume'])}</ul></div>""")
    tags = "".join(f'<li><span class="tg {c}">{t}</span>{d}</li>' for (t, d), c in zip(TAG_DESC, ["t-f", "t-a", "t-i"]))
    return f"""<!DOCTYPE html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>해석 로직</title>
<style>
  :root {{ --bg:#0f1419; --card:#1a2028; --line:#2a323d; --fg:#e6e9ee; --muted:#8b95a3; --accent:#4dabf7; }}
  * {{ box-sizing:border-box; }} body {{ margin:0; font-family:-apple-system,"Apple SD Gothic Neo","Malgun Gothic",sans-serif; background:var(--bg); color:var(--fg); line-height:1.65; }}
  .wrap {{ max-width:1000px; margin:0 auto; padding:24px 16px 64px; }} a {{ color:var(--accent); text-decoration:none; }}
  h1 {{ font-size:24px; margin:8px 0 4px; }} h2 {{ font-size:18px; margin:34px 0 10px; }}
  .sub {{ color:var(--muted); font-size:14px; margin-bottom:18px; }}
  .card {{ background:var(--card); border:1px solid var(--line); border-radius:12px; padding:14px 18px; margin-bottom:12px; font-size:14px; }}
  .tw {{ overflow-x:auto; }} table {{ width:100%; border-collapse:collapse; font-size:13px; min-width:760px; }}
  th {{ text-align:left; color:var(--muted); font-weight:600; padding:6px; border-bottom:1px solid var(--line); }}
  td {{ padding:7px 6px; border-bottom:1px solid var(--line); vertical-align:top; }}
  td:first-child {{ font-weight:800; }} td.g {{ color:#69db7c; white-space:nowrap; }} td.r {{ color:#ff8787; white-space:nowrap; }}
  td.why {{ color:#c5ccd6; }}
  .as {{ font-size:13px; color:var(--muted); margin-top:8px; }} .as ul {{ margin:4px 0; }}
  .tg {{ display:inline-block; font-size:11px; font-weight:700; border-radius:4px; padding:0 6px; margin-right:6px; color:#0b1015; }}
  .t-f {{ background:#69db7c; }} .t-a {{ background:#ffd43b; }} .t-i {{ background:#74c0fc; }}
  ol li, ul li {{ margin:4px 0; }}
</style></head>
<body><div class="wrap">
  <div><a href="daily.html#inst">← 🧭 오늘의 해석 (기관별 브리핑)</a> · <a href="index.html">대시보드</a> · <a href="guide.html">📘 지표 가이드</a></div>
  <h1>🧩 해석 로직</h1>
  <div class="sub">금융기관별 브리핑 카드가 어떤 기준으로 점수를 매기고 해석하는지 정리한 페이지예요. 실제 계산 코드와 같은 설정값으로 자동 생성돼요. · 갱신 {built}</div>

  <h2>1. 공통 구조</h2>
  <div class="card"><ol>
    <li><b>항목별 점수</b>: 해당 기관에 우호면 <b>+1</b>, 부담이면 <b>−1</b>, 그 사이면 <b>0</b>.
      방향은 <b>{N5}영업일 누적 변화</b>(하루짜리 노이즈를 피하려고), 수준은 <b>1년 중 위치</b>(최근 약 {WIN}영업일 중 오늘보다 낮았던 날의 비율, 0=1년 최저·100=1년 최고)로 판단해요.</li>
    <li><b>신호등</b>: 점수 합계 <b>{GREEN:+d} 이상 🟢 우호</b>, <b>{RED:+d} 이하 🔴 부담</b>, 그 사이 <b>🟡 중립</b>.</li>
    <li><b>체크포인트</b>: 카드 지표 중 <b>전일 변화 ÷ 최근 1년 일간 변화 표준편차</b>가 가장 큰 항목. 평소 대비 가장 크게 움직인 것을 뽑아요.</li>
  </ol></div>

  <h2>2. 문장 태그</h2>
  <div class="card"><ul style="list-style:none;padding-left:0">{tags}</ul></div>
  {''.join(blocks)}

  <h2>3. 근거 이론과 근사의 범위</h2>
  <div class="card"><ul>
    <li><b>이론적으로 맞는 근사</b>: 수정듀레이션 근사(볼록성 무시), 커버드 금리평가(외환스왑 베이시스 무시), 신용위험 프리미엄(유동성 프리미엄 혼재), 머튼 모형, 기간 프리미엄·만기변환.</li>
    <li><b>한국 현실에 맞게 표현을 조정한 것</b>: 보험 평가손익은 '자산 측'만, 은행 장단기 금리차는 NIM이 아닌 '환경 참고 지표', CD는 'CD 연동 기업대출·변동금리 대출' 기준.</li>
    <li><b>판단(이론 아님)</b>: 점수 문턱값과 신호등 기준은 설계자의 판단이에요. 이 페이지에 모두 공개하고, 코드 맨 위 설정값으로 바꿀 수 있어요.</li>
  </ul></div>

  <h2>4. 한계</h2>
  <div class="card"><ul>
    <li>NIM, K-ICS 비율, 연체율, PF 익스포저 같은 <b>회사 실적 지표는 분기 공시 자료</b>라 매일 데이터로 반영할 수 없어요. 시장금리로 방향만 추정해요.</li>
    <li>점수는 '그 기관에 시장 환경이 우호적인가'를 보여줄 뿐, 특정 회사의 실적이나 건전성을 판단하지 않아요.</li>
    <li>미국 값(환헤지 비용 계산용)과 주가는 1~2일 늦게 공표돼 기준일이 다를 수 있어요.</li>
  </ul></div>
  <p class="as">개인 학습용 자동 해석이며 투자 권유가 아닙니다.</p>
</div></body></html>"""


def write_logic(docs: str, built: str):
    with open(os.path.join(docs, "logic.html"), "w", encoding="utf-8") as f:
        f.write(logic_page(built))
