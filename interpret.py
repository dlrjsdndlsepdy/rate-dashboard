"""
규칙 기반 일일 해석 엔진 → docs/daily.html

판정 기준(A)
  - 보합: |변화| < 1bp
  - 이례적 변동: |오늘 변화| > 최근 1년 일간 변화 표준편차 × 2 (2σ)
  - 고점권/저점권: 1년 중 위치 ≥ 90 / ≤ 10
  - 추세: 최근 5영업일 누적 변화와 오늘 방향 비교 (지속 / 되돌림)

해석 규칙(B)  R1~R13 — 아래 RULES_DOC 참고
문턱값을 바꾸고 싶으면 이 파일 맨 위 상수만 고치면 됩니다.
"""
import math

import pandas as pd

import minichart

NOISE_BP = 1.0      # 보합 기준
SIGMA_K = 2.0       # 이례적 변동 기준 (σ 배수)
HI_PCT, LO_PCT = 90, 10
WINDOW = 260        # 1년 ≈ 260영업일
TREND_N = 5         # 추세 판단 기간
HISTORY_N = 20      # 해석 기록 일수

# 컬럼: (표시 이름, 단위)  단위 '%'는 변화량을 bp로 환산
NAMES = {
    "ktb3": ("국고 3년", "%"), "ktb10": ("국고 10년", "%"), "ktb30": ("국고 30년", "%"),
    "corp_aa": ("회사채 AA− 3년", "%"), "cd91": ("CD 91일", "%"), "cp91": ("CP 91일", "%"),
    "yeojeon_aa": ("여전채 AA− 3년", "%"), "yeojeon_a_plus": ("여전채 A+ 3년", "%"),
    "corp_aa_mp": ("회사채 AA−(민평)", "%"), "corp_a_minus": ("회사채 A− 3년", "%"),
    "corp_bbb_plus": ("회사채 BBB+ 3년", "%"),
    "term_spread_bp": ("장단기 스프레드(10Y−3Y)", "bp"), "ultra_spread_bp": ("초장기 스프레드(30Y−10Y)", "bp"),
    "corp_spread_bp": ("회사채 크레딧 스프레드", "bp"), "yeojeon_spread_bp": ("여전채 크레딧 스프레드", "bp"),
    "yeojeon_grade_bp": ("여전채 등급 스프레드(A+−AA−)", "bp"), "cp_cd_spread_bp": ("CP−CD 스프레드", "bp"),
    "corp_a_spread_bp": ("A− 크레딧 스프레드", "bp"), "corp_grade_a_bp": ("등급 스프레드(A−−AA−)", "bp"),
    "corp_grade_bbb_bp": ("등급 스프레드(BBB+−AA−)", "bp"),
}


def _bp(x: float) -> str:
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "n/a"
    s = "+" if x > 0 else ("−" if x < 0 else "±")
    return f"{s}{abs(x):.1f}bp"


def _lvl(col: str, v: float) -> str:
    return f"{v:.3f}%" if NAMES.get(col, ("", "%"))[1] == "%" else f"{v:.1f}bp"


class Day:
    """특정 날짜 t의 지표별 변화·통계를 계산해 두는 도우미."""

    def __init__(self, df: pd.DataFrame, i: int):
        self.df, self.i = df, i
        self.date = df.index[i]

    def has(self, c):
        return c in self.df.columns and not pd.isna(self.df[c].iloc[self.i]) and not pd.isna(self.df[c].iloc[self.i - 1])

    def _scale(self, c):
        return 100.0 if NAMES.get(c, ("", "%"))[1] == "%" else 1.0

    def lvl(self, c):
        return float(self.df[c].iloc[self.i])

    def d(self, c):            # 전일 대비 (bp)
        if not self.has(c):
            return float("nan")
        return (self.df[c].iloc[self.i] - self.df[c].iloc[self.i - 1]) * self._scale(c)

    def d5(self, c):           # 5영업일 누적 (bp)
        j = self.i - TREND_N
        if c not in self.df.columns or j < 0 or pd.isna(self.df[c].iloc[j]) or pd.isna(self.df[c].iloc[self.i]):
            return float("nan")
        return (self.df[c].iloc[self.i] - self.df[c].iloc[j]) * self._scale(c)

    def sigma(self, c):        # 최근 1년 일간 변화 표준편차 (bp)
        s = self.df[c].iloc[max(0, self.i - WINDOW): self.i + 1].diff().dropna() * self._scale(c)
        return float(s.std()) if len(s) > 20 else float("nan")

    def pct(self, c):          # 1년 중 위치 0~100
        s = self.df[c].iloc[max(0, self.i - WINDOW + 1): self.i + 1].dropna()
        if len(s) < 20:
            return float("nan")
        return round(100 * (s < s.iloc[-1]).sum() / (len(s) - 1))


def _dir(x):
    if math.isnan(x) or abs(x) < NOISE_BP:
        return 0
    return 1 if x > 0 else -1


def curve_regime(d3, d10):
    """R1~R5: 국고 3년·10년 변화(bp)로 커브 국면 판단."""
    if math.isnan(d3) or math.isnan(d10):
        return None, None
    a, b = _dir(d3), _dir(d10)
    if a == 0 and b == 0:
        return "보합", "국고 3년·10년 모두 1bp 미만 변동. 뚜렷한 방향성이 없었어요."
    if a <= 0 and b <= 0:
        if d3 < d10:
            return "불 스티프닝 (R1)", "단기 금리가 더 크게 하락 → 기준금리 인하 기대가 커지는 방향이에요."
        return "불 플래트닝 (R2)", "장기 금리가 더 크게 하락 → 경기 둔화 우려나 장기채 수요가 반영된 움직임이에요."
    if a >= 0 and b >= 0:
        if d3 > d10:
            return "베어 플래트닝 (R3)", "단기 금리가 더 크게 상승 → 인상 기대(또는 인하 기대 후퇴)가 반영된 움직임이에요."
        return "베어 스티프닝 (R4)", "장기 금리가 더 크게 상승 → 물가·재정 우려나 해외 금리 상승 영향이 의심되는 움직임이에요."
    if d3 > 0 > d10:
        return "트위스트 (R5)", "단기↑·장기↓ → 단기 긴축 기대와 장기 경기 둔화 전망이 엇갈려요."
    return "트위스트 (R5)", "단기↓·장기↑ → 인하 기대와 장기 물가·재정 우려가 엇갈려요."


def interpret_day(t: Day) -> dict:
    out = {"date": t.date.strftime("%Y-%m-%d"), "facts": [], "signals": [], "flags": [], "sector": {}}

    # ---- 커브 국면 (오늘 + 5일)
    d3, d10 = t.d("ktb3"), t.d("ktb10")
    reg, why = curve_regime(d3, d10)
    reg5, _ = curve_regime(t.d5("ktb3"), t.d5("ktb10"))
    out["regime"], out["regime_why"], out["regime5"] = reg, why, reg5
    if t.has("ktb3"):
        out["facts"].append(f"국고 3년 {t.lvl('ktb3'):.3f}% ({_bp(d3)}), 10년 {t.lvl('ktb10'):.3f}% ({_bp(d10)}), "
                            f"장단기 스프레드 {t.lvl('term_spread_bp'):.1f}bp ({_bp(t.d('term_spread_bp'))})")

    # ---- R6/R7 크레딧 스프레드
    for c in ["corp_spread_bp", "yeojeon_spread_bp", "corp_a_spread_bp"]:
        if not t.has(c):
            continue
        dc = _dir(t.d(c))
        if dc > 0:
            out["signals"].append(("R6", f"{NAMES[c][0]} {_bp(t.d(c))} 확대 → 신용위험 회피, 조달 여건 악화 방향", [c]))
        elif dc < 0:
            out["signals"].append(("R7", f"{NAMES[c][0]} {_bp(t.d(c))} 축소 → 크레딧 선호, 조달 여건 개선 방향", [c]))

    # ---- R8/R9 교차 (국고 vs 회사채 스프레드), 5일 흐름으로 확인
    if t.has("corp_spread_bp") and t.has("ktb3"):
        g, s = _dir(d3), _dir(t.d("corp_spread_bp"))
        g5, s5 = _dir(t.d5("ktb3")), _dir(t.d5("corp_spread_bp"))
        if g < 0 and s > 0:
            conf = "5일 흐름도 같은 방향이라 신호가 강해요." if (g5 < 0 and s5 > 0) else \
                   "단, 하루 단위로는 회사채 금리가 국고채를 늦게 따라가 생기는 착시일 수 있어 5일 흐름으로 확인이 필요해요."
            out["signals"].append(("R8", f"국고 금리 하락 + 회사채 스프레드 확대 → Risk-off(안전자산 선호) 성향. {conf}", ["ktb3", "corp_spread_bp"]))
        elif g > 0 and s < 0:
            conf = "5일 흐름도 같은 방향이에요." if (g5 > 0 and s5 < 0) else \
                   "단, 회사채 금리 반영 지연에 따른 착시일 수 있어요."
            out["signals"].append(("R9", f"국고 금리 상승 + 회사채 스프레드 축소 → Risk-on(위험 선호) 성향. {conf}", ["ktb3", "corp_spread_bp"]))

    # ---- R10 등급 차별화
    for c in ["corp_grade_a_bp", "corp_grade_bbb_bp", "yeojeon_grade_bp"]:
        if not t.has(c):
            continue
        dc = _dir(t.d(c))
        if dc > 0:
            out["signals"].append(("R10", f"{NAMES[c][0]} {_bp(t.d(c))} → 신용 차별화 심화(하위 등급 조달 부담 증가). 민평 등급 간격은 잘 안 움직여 의미 있는 변화예요.", [c]))
        elif dc < 0:
            out["signals"].append(("R10", f"{NAMES[c][0]} {_bp(t.d(c))} → 등급 간 격차 완화", [c]))

    # ---- R11 단기 자금시장
    if t.has("cp_cd_spread_bp"):
        dcc = t.d("cp_cd_spread_bp")
        ye_stable = t.has("yeojeon_spread_bp") and _dir(t.d("yeojeon_spread_bp")) == 0
        if _dir(dcc) > 0 and ye_stable:
            out["signals"].append(("R11", f"CP−CD {_bp(dcc)} 확대 + 여전채 스프레드 보합 → 단기 자금시장 스트레스가 먼저 나타나는 모습. 장기물로 번지는지 관찰이 필요해요.", ["cp_cd_spread_bp", "yeojeon_spread_bp"]))
        elif _dir(dcc) > 0:
            out["signals"].append(("R11", f"CP−CD {_bp(dcc)} 확대 → 기업·비은행 단기 조달 부담 증가", ["cp_cd_spread_bp"]))
        if t.pct("cp_cd_spread_bp") >= HI_PCT:
            out["signals"].append(("R11", f"CP−CD 스프레드 {t.lvl('cp_cd_spread_bp'):.0f}bp, 1년 중 위치 {t.pct('cp_cd_spread_bp'):.0f} → 단기 자금시장 긴장 고점권", ["cp_cd_spread_bp"]))

    # ---- R12 CD vs 국고 3년
    if t.has("cd91") and t.has("ktb3"):
        dcd = t.d("cd91")
        if _dir(dcd) > 0 and dcd > d3:
            out["signals"].append(("R12", f"CD 91일 {_bp(dcd)}로 국고 3년({_bp(d3)})보다 더 올라 → 단기 금리 상승 압력, 변동금리 대출금리 상승 요인", ["cd91", "ktb3"]))

    # ---- R13 초장기
    if t.has("ultra_spread_bp"):
        du, lu = t.d("ultra_spread_bp"), t.lvl("ultra_spread_bp")
        if lu < 0:
            out["signals"].append(("R13", f"30Y−10Y −{abs(lu):.1f}bp로 역전 상태 → 보험·연기금의 초장기물 수요가 강해요.", ["ultra_spread_bp"]))
        elif _dir(du) < 0:
            out["signals"].append(("R13", f"30Y−10Y {_bp(du)} 축소 → 초장기물 수요 강세 방향", ["ultra_spread_bp"]))

    # ---- A. 이례적 변동 / 고점·저점권 / 추세
    for c in NAMES:
        if not t.has(c):
            continue
        dv, sg = t.d(c), t.sigma(c)
        if not math.isnan(sg) and sg > 0 and abs(dv) > SIGMA_K * sg:
            out["flags"].append(("⚡", f"{NAMES[c][0]} {_bp(dv)} — 평소 하루 변동폭(1σ≈{sg:.1f}bp)의 {abs(dv) / sg:.1f}배, 이례적 변동"))
    hi, lo = [], []
    for c in NAMES:
        if not t.has(c):
            continue
        p = t.pct(c)
        if math.isnan(p):
            continue
        if p >= HI_PCT:
            hi.append(f"{NAMES[c][0]} {_lvl(c, t.lvl(c))}({p:.0f})")
        elif p <= LO_PCT:
            lo.append(f"{NAMES[c][0]} {_lvl(c, t.lvl(c))}({p:.0f})")
    if hi:
        out["flags"].append(("▲", "1년 고점권: " + ", ".join(hi)))
    if lo:
        out["flags"].append(("▼", "1년 저점권: " + ", ".join(lo)))

    trends = []
    for c in ["ktb3", "ktb10", "corp_spread_bp", "yeojeon_spread_bp", "cp_cd_spread_bp"]:
        if not t.has(c):
            continue
        a, b = _dir(t.d(c)), _dir(t.d5(c))
        if a and b:
            trends.append(f"{NAMES[c][0]} 5일 {_bp(t.d5(c))} → " + ("추세 지속" if a == b else "오늘은 되돌림"))
    out["trends"] = trends

    # ---- 업권별 시사점
    sec = out["sector"]
    if t.has("yeojeon_aa"):
        s = f"여전채 AA− {_bp(t.d('yeojeon_aa'))}"
        s += " → 장기 조달 비용 하락." if _dir(t.d("yeojeon_aa")) < 0 else (" → 장기 조달 비용 상승." if _dir(t.d("yeojeon_aa")) > 0 else " → 장기 조달 비용 보합.")
        if t.has("cp91"):
            pc = t.pct("cp91")
            s += f" CP 91일 {t.lvl('cp91'):.2f}%(1년 중 위치 {pc:.0f})" + (" — 단기 차환 부담 큰 구간." if pc >= HI_PCT else ".")
        sec["캐피탈"] = s
    if t.has("corp_a_minus"):
        s = f"A− {_bp(t.d('corp_a_minus'))}, BBB+ {_bp(t.d('corp_bbb_plus'))}"
        if t.has("corp_grade_a_bp"):
            g = _dir(t.d("corp_grade_a_bp"))
            s += " → 하위 등급 조달 부담 상대적 확대, 대체 조달(여신·사모 크레딧) 수요 요인." if g > 0 else \
                 (" → 등급 간 격차 완화." if g < 0 else " → 등급 간 격차 유지.")
        sec["기업금융"] = s
    if t.has("ktb30"):
        s = f"국고 30년 {_bp(t.d('ktb30'))}, 30Y−10Y {t.lvl('ultra_spread_bp'):.1f}bp"
        d30 = _dir(t.d("ktb30"))
        s += " → 초장기 금리 하락: 보유채권 평가이익, 신규 투자수익률은 낮아짐." if d30 < 0 else \
             (" → 초장기 금리 상승: 신규 투자수익률 개선, 보유채권 평가손실 요인." if d30 > 0 else " → 초장기 금리 보합.")
        sec["보험"] = s
    if t.has("cd91"):
        s = f"CD 91일 {t.lvl('cd91'):.2f}% ({_bp(t.d('cd91'))})"
        dc = _dir(t.d("cd91"))
        s += " → 변동금리 대출금리 상승 요인." if dc > 0 else (" → 변동금리 대출금리 하락 요인." if dc < 0 else " → 대출 기준금리 보합.")
        if t.has("term_spread_bp"):
            s += f" 장단기 스프레드 {_bp(t.d('term_spread_bp'))}" + (" (커브가 눕는 중 — 예대 만기 미스매치 수익엔 불리한 방향)." if _dir(t.d('term_spread_bp')) < 0 else ".")
        sec["은행"] = s
    return out


RULES_DOC = [
    ("판정 A", "보합", f"전일 대비 변화가 ±{NOISE_BP:.0f}bp 미만이면 방향 없음으로 봐요."),
    ("판정 A", "이례적 변동 ⚡", f"오늘 변화가 최근 1년 일간 변화 표준편차의 {SIGMA_K:.0f}배를 넘으면 표시해요."),
    ("판정 A", "고점권 ▲ / 저점권 ▼", f"1년 중 위치가 {HI_PCT} 이상 / {LO_PCT} 이하."),
    ("판정 A", "추세", f"최근 {TREND_N}영업일 누적 변화와 오늘 방향이 같으면 '추세 지속', 반대면 '되돌림'."),
    ("R1", "불 스티프닝", "3Y·10Y 하락, 3Y가 더 하락 → 기준금리 인하 기대 확대 (기대가설)"),
    ("R2", "불 플래트닝", "3Y·10Y 하락, 10Y가 더 하락 → 경기 둔화 우려·장기채 수요 (기간 프리미엄 축소)"),
    ("R3", "베어 플래트닝", "3Y·10Y 상승, 3Y가 더 상승 → 인상 기대 또는 인하 기대 후퇴"),
    ("R4", "베어 스티프닝", "3Y·10Y 상승, 10Y가 더 상승 → 물가·재정 우려, 해외 금리 영향 (기간 프리미엄 확대)"),
    ("R5", "트위스트", "3Y와 10Y가 반대 방향 → 단기 정책 기대와 장기 전망이 엇갈림"),
    ("R6", "크레딧 스프레드 확대", "회사채·여전채·A− 스프레드 확대 → 신용위험 회피 (신용위험 프리미엄)"),
    ("R7", "크레딧 스프레드 축소", "→ 크레딧 선호, 조달 여건 개선"),
    ("R8", "Risk-off", "국고 금리↓ + 회사채 스프레드↑ → 안전자산 선호. 5일 흐름으로 확인 (회사채 금리 반영 지연 착시 주의)"),
    ("R9", "Risk-on", "국고 금리↑ + 회사채 스프레드↓ → 위험 선호"),
    ("R10", "신용 차별화", "등급 스프레드(A−−AA−, BBB+−AA−, A+−AA−) 확대 → 하위 등급·중소형사 부담 증가"),
    ("R11", "단기 자금시장", "CP−CD 확대(특히 여전채 스프레드는 보합일 때) → 단기 스트레스 선행. 1년 고점권이면 별도 표시"),
    ("R12", "단기 금리 압력", "CD 상승폭 > 국고 3년 상승폭 → 변동금리 대출금리 상승 요인"),
    ("R13", "초장기 수요", "30Y−10Y 축소 또는 역전 → 보험·연기금 초장기물 수요 강세"),
]

CSS = """
  :root { --bg:#0f1419; --card:#1a2028; --line:#2a323d; --fg:#e6e9ee; --muted:#8b95a3; --accent:#4dabf7; --warn:#ffd43b; }
  * { box-sizing:border-box; }
  body { margin:0; font-family:-apple-system,"Apple SD Gothic Neo","Malgun Gothic",sans-serif;
         background:var(--bg); color:var(--fg); line-height:1.65; }
  .wrap { max-width:860px; margin:0 auto; padding:24px 16px 64px; }
  a { color:var(--accent); text-decoration:none; }
  h1 { font-size:24px; margin:8px 0 4px; }
  h2 { font-size:18px; margin:32px 0 10px; }
  .sub { color:var(--muted); font-size:14px; margin-bottom:18px; }
  .card { background:var(--card); border:1px solid var(--line); border-radius:12px; padding:16px 18px; margin-bottom:12px; }
  .regime { font-size:20px; font-weight:800; margin:2px 0 4px; }
  .muted { color:var(--muted); font-size:13px; }
  .tag { display:inline-block; font-size:11px; font-weight:700; color:#0b1015; background:var(--accent);
         border-radius:4px; padding:0 6px; margin-right:6px; }
  ul { margin:6px 0 0; padding-left:20px; } li { margin:4px 0; font-size:14px; }
  .sec b { display:inline-block; min-width:64px; }
  details { background:var(--card); border:1px solid var(--line); border-radius:12px; padding:10px 16px; margin-bottom:8px; }
  summary { cursor:pointer; font-size:14px; }
  table { width:100%; border-collapse:collapse; font-size:13px; }
  td { border-top:1px solid var(--line); padding:7px 6px; vertical-align:top; }
  td:first-child { color:var(--muted); white-space:nowrap; width:64px; }
  td:nth-child(2) { font-weight:700; white-space:nowrap; }
"""


def _block(r: dict, full: bool = True, df: pd.DataFrame = None) -> str:
    """full=True & df가 있으면(오늘 카드) 신호마다 작은 그래프를 붙임."""
    h = []
    if r.get("regime"):
        h.append(f'<div class="muted">커브 국면 (오늘)</div><div class="regime">{r["regime"]}</div>')
        h.append(f'<div>{r["regime_why"]}</div>')
        if r.get("regime5"):
            h.append(f'<div class="muted" style="margin-top:4px">최근 5영업일 기준 국면: {r["regime5"]}</div>')
    if r["facts"]:
        h.append("<ul>" + "".join(f"<li>{x}</li>" for x in r["facts"]) + "</ul>")
    if full and df is not None:
        h.append(minichart.canvas(minichart.chart("KR", df, ["ktb3", "ktb10", "term_spread_bp"], NAMES), height=190))
    if r["signals"]:
        items, seen = [], set()
        for s in r["signals"]:
            k, v = s[0], s[1]
            g = ""
            if full and df is not None and len(s) > 2 and tuple(s[2]) not in seen:
                seen.add(tuple(s[2]))
                g = minichart.canvas(minichart.chart("KR", df, s[2], NAMES))
            items.append(f'<li><span class="tag">{k}</span>{v}{g}</li>')
        h.append('<div class="muted" style="margin-top:12px">해석 신호</div><ul>' + "".join(items) + "</ul>")
    else:
        h.append('<div class="muted" style="margin-top:12px">해석 신호: 규칙에 걸린 뚜렷한 신호가 없었어요.</div>')
    if r["flags"]:
        h.append('<div class="muted" style="margin-top:12px">주목할 수치</div><ul>' +
                 "".join(f"<li>{i} {v}</li>" for i, v in r["flags"]) + "</ul>")
    if full and r.get("trends"):
        h.append('<div class="muted" style="margin-top:12px">5일 추세</div><ul>' +
                 "".join(f"<li>{v}</li>" for v in r["trends"]) + "</ul>")
    if r["sector"]:
        h.append('<div class="muted" style="margin-top:12px">업권별 시사점</div><ul class="sec">' +
                 "".join(f"<li><b>{k}</b>{v}</li>" for k, v in r["sector"].items()) + "</ul>")
    return "".join(h)


def render(df: pd.DataFrame, built: str) -> str:
    df = df.sort_index()
    idxs = list(range(max(1, len(df) - HISTORY_N), len(df)))
    results = [interpret_day(Day(df, i)) for i in idxs][::-1]
    today = results[0]
    hist = "".join(
        f'<details><summary><b>{r["date"]}</b> · {r.get("regime") or "-"} · 신호 {len(r["signals"])}개'
        f'{" · ⚡" if any(i == "⚡" for i, _ in r["flags"]) else ""}</summary>'
        f'<div style="margin-top:8px">{_block(r, full=False)}</div></details>'
        for r in results[1:])
    rules = "".join(f"<tr><td>{a}</td><td>{b}</td><td>{c}</td></tr>" for a, b, c in RULES_DOC)
    return f"""<!DOCTYPE html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>오늘의 해석 · Rates & Spreads Dashboard</title>
<style>{CSS}{minichart.CSS}</style></head>
<body><div class="wrap">
  <div><a href="index.html">← 대시보드</a> · <a href="guide.html">📘 지표 가이드</a> · <a href="us-daily.html">🇺🇸 미국 오늘의 해석</a></div>
  <h1>🧭 오늘의 해석</h1>
  <div class="sub">기준일 <b>{today["date"]}</b> · 페이지 생성 {built} · 아래 '해석 기준'의 규칙을 매일 기계적으로 적용한 결과예요.</div>
  <div class="card">{_block(today, True, df)}</div>
  <div class="muted">⚠️ 숫자의 움직임이 보내는 '신호'를 읽은 것이에요. 원인(금통위, 해외 지표, 수급 등)은 그날 뉴스와 맞춰 확인하세요.</div>
  <h2>최근 {len(results) - 1}영업일 해석 기록</h2>
  {hist}
  <h2 id="rules">해석 기준</h2>
  <div class="card"><table>{rules}</table></div>
  <p class="muted">개인 학습용 자동 해석이며 투자 권유가 아닙니다.</p>
</div>{minichart.script({"KR": df})}</body></html>"""
