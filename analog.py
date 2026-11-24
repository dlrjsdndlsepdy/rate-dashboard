"""
과거 유사 국면 찾기 (사례 학습용)

방법
  1) 오늘의 '시장 상태'를 5개 숫자로 요약
       장단기 스프레드(10Y−3Y), 회사채 크레딧 스프레드, CP−CD 스프레드   ← 수준
       국고 3년 20영업일 변화(bp), 코스피 20영업일 변화(%)               ← 최근 흐름
  2) 각 숫자를 전체 기간 기준으로 표준화(z-score)해 단위 차이를 없앰
  3) 과거 날짜 중 오늘과의 거리(유클리드)가 가장 가까운 날을 고름
       - 최근 120영업일은 제외 (지금 국면 자체가 잡히는 것 방지)
       - 고른 날짜끼리 40영업일 이상 떨어지게 (같은 국면 중복 방지)
  4) 그날 이후 20영업일 동안 실제로 어떻게 움직였는지 보여줌

과거 흐름이 반복된다는 보장은 없어요. '이런 상태에서 과거엔 이런 일이 있었다'를 공부하는 도구예요.
"""
import math

import pandas as pd

FEATURES = [  # (컬럼, 이름, 단위)
    ("term_spread_bp", "10Y−3Y", "bp"),
    ("corp_spread_bp", "회사채 스프레드", "bp"),
    ("cp_cd_spread_bp", "CP−CD", "bp"),
    ("ktb3_chg20", "국고 3년 20일 변화", "bp"),
    ("kospi_chg20", "코스피 20일 변화", "%"),
]
AHEAD = 20
EXCLUDE_RECENT = 120
GAP = 40
EPISODES = [  # (시작, 끝, 이름) — 알려진 국면에 이름표
    ("2020-02-20", "2020-04-30", "코로나19 충격"),
    ("2022-09-26", "2022-12-31", "레고랜드 사태·단기자금시장 경색"),
    ("2022-06-01", "2022-09-25", "글로벌 급격한 긴축"),
    ("2023-10-01", "2023-11-15", "미 장기금리 급등(10년 5% 근접)"),
    ("2024-08-01", "2024-08-15", "엔 캐리 청산 급락"),
]


def _frame(df: pd.DataFrame) -> pd.DataFrame:
    f = pd.DataFrame(index=df.index)
    for c in ["term_spread_bp", "corp_spread_bp", "cp_cd_spread_bp"]:
        f[c] = df[c] if c in df.columns else float("nan")
    f["ktb3_chg20"] = (df["ktb3"] - df["ktb3"].shift(20)) * 100
    if "kospi" in df.columns:
        k = df["kospi"].ffill()
        f["kospi_chg20"] = (k / k.shift(20) - 1) * 100
    else:
        f["kospi_chg20"] = float("nan")
    return f


def _episode(d):
    for a, b, name in EPISODES:
        if pd.Timestamp(a) <= d <= pd.Timestamp(b):
            return name
    return ""


def find(df: pd.DataFrame, k: int = 3):
    df = df.sort_index()
    f = _frame(df)
    cols = [c for c, _, _ in FEATURES if f[c].notna().sum() > 300]
    if len(cols) < 3:
        return None
    today = f.index[-1]
    if f.loc[today, cols].isna().any():  # 오늘 값이 비면(주가 공표 지연 등) 마지막으로 다 있는 날
        ok = f[cols].dropna()
        if not len(ok):
            return None
        today = ok.index[-1]
    z = (f[cols] - f[cols].mean()) / f[cols].std()
    pos = f.index.get_loc(today)
    cand = z.iloc[: max(0, pos - EXCLUDE_RECENT)].dropna()
    cand = cand[cand.index.map(lambda d: f.index.get_loc(d) + AHEAD < len(f))]
    if len(cand) < 50:
        return None
    dist = ((cand - z.loc[today]) ** 2).sum(axis=1).pow(0.5).sort_values()
    picks = []
    for d, v in dist.items():
        if all(abs(f.index.get_loc(d) - f.index.get_loc(p)) >= GAP for p, _ in picks):
            picks.append((d, v))
        if len(picks) == k:
            break
    out = []
    for d, v in picks:
        i = f.index.get_loc(d)
        j = i + AHEAD
        after = {
            "국고 3년": (df["ktb3"].iloc[j] - df["ktb3"].iloc[i]) * 100,
            "10Y−3Y": df["term_spread_bp"].iloc[j] - df["term_spread_bp"].iloc[i],
            "회사채 스프레드": df["corp_spread_bp"].iloc[j] - df["corp_spread_bp"].iloc[i],
            "CP−CD": df["cp_cd_spread_bp"].iloc[j] - df["cp_cd_spread_bp"].iloc[i],
        }
        if "kospi" in df.columns:
            k0, k1 = df["kospi"].ffill().iloc[i], df["kospi"].ffill().iloc[j]
            after["코스피"] = (k1 / k0 - 1) * 100 if k0 else float("nan")
        out.append({"date": d, "dist": v, "vals": f.loc[d, cols], "after": after, "episode": _episode(d)})
    return {"today": today, "today_vals": f.loc[today, cols], "cols": cols, "picks": out}


def _fmt(v, unit):
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return "-"
    return f"{v:+.1f}{unit}" if unit in ("bp", "%") else f"{v:.1f}"


def section(df: pd.DataFrame) -> str:
    r = find(df)
    if not r:
        return ""
    names = {c: (n, u) for c, n, u in FEATURES}
    head = "".join(f"<th>{names[c][0]}</th>" for c in r["cols"])
    def row(label, vals):
        return f"<tr><td>{label}</td>" + "".join(
            f"<td>{vals[c]:.1f}{names[c][1]}</td>" if not pd.isna(vals[c]) else "<td>-</td>" for c in r["cols"]) + "</tr>"
    rows = row(f"<b>기준일 {r['today']:%Y-%m-%d}</b>", r["today_vals"])
    for p in r["picks"]:
        rows += row(f"{p['date']:%Y-%m-%d}" + (f" <span class='muted'>({p['episode']})</span>" if p["episode"] else ""), p["vals"])
    after_keys = list(r["picks"][0]["after"].keys())
    ah = "".join(f"<th>{k}</th>" for k in after_keys)
    ar = "".join(
        f"<tr><td>{p['date']:%Y-%m-%d}</td>" + "".join(
            f"<td>{_fmt(p['after'][k], '%' if k == '코스피' else 'bp')}</td>" for k in after_keys) + "</tr>"
        for p in r["picks"])
    # 방향 일치도 → 한 줄 요약 (사실: 과거 데이터 집계)
    ups = [p["after"]["회사채 스프레드"] for p in r["picks"] if not math.isnan(p["after"]["회사채 스프레드"])]
    k3 = [p["after"]["국고 3년"] for p in r["picks"]]
    summ = (f"<span class='tg t-f'>사실</span> 비슷했던 {len(r['picks'])}번 중 20영업일 뒤 국고 3년이 오른 경우 "
            f"{sum(1 for x in k3 if x > 0)}번, 회사채 스프레드가 벌어진 경우 {sum(1 for x in ups if x > 0)}번이었어요.")
    return f"""<h2 id="analog">🕰️ 과거 유사 국면</h2>
<div class="card">
  <div class="muted" style="margin-bottom:6px">오늘의 커브·크레딧·단기자금·최근 흐름이 가장 비슷했던 과거 날짜예요 (최근 6개월 제외).</div>
  <div style="overflow-x:auto"><table><tr><th></th>{head}</tr>{rows}</table></div>
  <div style="margin:10px 0 4px"><b>그 뒤 20영업일 동안의 실제 변화</b></div>
  <div style="overflow-x:auto"><table><tr><th>유사일</th>{ah}</tr>{ar}</table></div>
  <div style="margin-top:8px;font-size:13px">{summ}</div>
  <div class="as">방법: 5개 지표를 표준화해 거리가 가장 가까운 날(서로 40영업일 이상 간격). 과거 흐름이 반복된다는 보장은 없어요 — 사례 학습용이에요.</div>
</div>"""
